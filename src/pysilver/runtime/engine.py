"""Engine: owns the canvas, the wgpu device, and the frame pipeline.

M2 scope -- acquires the device, clears to an MD3 surface colour, and issues the
frame's single instanced draw over the display list. Steps 1-5 of the frame
lifecycle (events, build, layout) arrive with the element tree in M3.

Note what this class does NOT contain: an event loop. rendercanvas owns the
scheduler (ARCHITECTURE.md 5.10) and its 'ondemand' update mode is the dirty
flag. Polling GLFW here would double-pump the event queue.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Final

import wgpu

from ..config import Settings
from ..paint import DisplayList
from ..render import UIPipeline
from ..render.atlas import ImageAtlas
from ..text import TextEngine
from ..theme import Palette, Theme
from .clipboard import GlfwClipboard, clipboard

__all__ = ["Engine"]


#: Frames the surface stays pinned after the last size change. A resize draws
#: synchronously per compositor configure, so this is a handful of frames after
#: the drag stops, not a wall-clock delay.
SETTLE_FRAMES: Final = 3

#: Cap on how often a raw input-driven resize notification is allowed to
#: trigger an eager repaint -- see `_coalesce_resize_paints`. 120 Hz is far
#: above anything a human perceives as a distinct frame, so it costs nothing
#: to feel smooth, but it bounds how large a backlog `glfw.poll_events()` can
#: be made to drain synchronously before the input event underneath it (a
#: mouse-up, say) is even delivered.
RESIZE_REPAINT_MIN_INTERVAL: Final = 1.0 / 120.0


def _coalesce_resize_paints() -> None:
    """Rate-limit `GlfwRenderCanvas._on_size_change`'s eager repaint.

    `glfw.poll_events()` drains every pending native event before returning,
    and rendercanvas documents it as blocking during a resize for exactly
    this reason. Unpatched, every one of those native configure events fires
    `_on_size_change`, which synchronously does a full render for EACH one --
    no coalescing at all, despite rendercanvas's own comment ("we may get
    notified too often, but that's ok, they'll result in a single draw")
    claiming otherwise; that claim does not hold for this backend, which
    calls `_time_to_paint()` synchronously and directly rather than
    scheduling it through an event loop that would naturally collapse
    several requests into one.

    A fast drag can queue native resize events faster than pySilver renders
    them, and the input event that ends the drag (a mouse-up) sits in that
    same native queue, behind all of them -- so `poll_events()` will not
    return, and the app will not even see the mouse-up, until every queued
    resize has been fully rendered. That is a real, measured symptom (the
    2026-09 resize investigation): the window keeps visibly resizing for a
    perceptible stretch after the drag has actually stopped, working through
    a backlog rather than being slow to render any single frame. Confirmed
    the swapchain pin (`_pin_surface`) was not the cause first -- disabling
    `resize_bucket` entirely made no difference -- before finding this.

    **Unrelated to the "never decline a compositor-requested frame" rule**
    the reverted resize throttle established (ARCHITECTURE.md 5.8.1): that
    rule is about not declining a frame the compositor actually asked for.
    This is about not eagerly OFFERING a redraw for every single raw input
    notification when they arrive faster than any display could show them.
    Skipping an intermediate one is safe because every draw re-reads the
    CURRENT true size fresh (`get_physical_size()`), never a stale cached
    one -- so throttling this path can only ever skip drawing a size that a
    later, permitted draw in the same burst already supersedes.

    Patches the class, not an instance: `weakbind` (rendercanvas's own
    wrapper around the glfw callback) captures the underlying function
    object at bind time, which happens inside `GlfwRenderCanvas.__init__` --
    an instance-attribute patch applied after construction would silently
    have no effect. Must therefore run before any `RenderCanvas` is
    constructed. Applied once per process, guarded against double-wrapping
    if more than one `Engine` is created (every golden test does this).
    """
    from rendercanvas.glfw import RenderCanvas

    if getattr(RenderCanvas._on_size_change, "_pysilver_coalesced", False):
        return

    def _throttled(self: Any, *args: Any) -> None:
        self._determine_size()
        now = time.perf_counter()
        last = getattr(self, "_pysilver_last_resize_paint", 0.0)
        if now - last < RESIZE_REPAINT_MIN_INTERVAL:
            return
        self._pysilver_last_resize_paint = now
        if self._is_in_poll_events and not self._is_minimized:
            self._time_to_paint()

    _throttled._pysilver_coalesced = True  # type: ignore[attr-defined]
    RenderCanvas._on_size_change = _throttled


def surface_size_for(
    size: tuple[int, int],
    previous: tuple[int, int],
    settle: int,
    bucket: int,
) -> tuple[tuple[int, int], int]:
    """The size to configure the surface at, and the new settle countdown.

    Separated from `Engine` so the policy is testable without a window: it is
    a decision about integers, and the GPU has no opinion about it.
    """
    if bucket <= 0:
        return size, 0
    if size != previous:
        settle = SETTLE_FRAMES
    elif settle:
        settle -= 1
    if settle:
        return (-(-size[0] // bucket) * bucket, -(-size[1] // bucket) * bucket), settle
    return size, settle


class Engine:
    def __init__(
        self,
        theme: Theme | None = None,
        settings: Settings | None = None,
        canvas: Any | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.palette = Palette(theme or Theme())
        self.canvas = canvas if canvas is not None else self._make_canvas()

        self.adapter = wgpu.gpu.request_adapter_sync(
            power_preference=self.settings.power_preference
        )
        self.device = self.adapter.request_device_sync()

        self.context = self.canvas.get_context("wgpu")
        self.format = self.context.get_preferred_format(self.adapter)
        self.context.configure(device=self.device, format=self.format)
        self._wrap_canvas_close()

        self.pipeline = UIPipeline(self.device, self.format)
        self.display_list = DisplayList()

        self.text = TextEngine(self.device)
        self.pipeline.bind_glyph_atlas(self.text.atlas.texture)

        self.images = ImageAtlas(self.device)
        self.pipeline.bind_image_atlas(self.images.texture)

        #: Fills the display list each frame. M3 replaces this with a walk of
        #: the element tree; until then it is the way to draw anything.
        self.painter: Callable[[DisplayList], None] | None = None

        self._frame_count = 0
        self._instance_count = 0
        self._close_requested = False

        #: Configures the swapchain. Public wgpu-py API ("External code needs
        #: to set the framebuffer size"), reached through rendercanvas's
        #: wrapper; None on a canvas that has no swapchain at all, such as the
        #: offscreen one the golden suite renders through.
        self._set_surface_size = getattr(
            getattr(self.context, "_wgpu_context", None), "set_physical_size", None
        )
        #: Seeded with the real size so the first frame is never mistaken for a
        #: resize -- which is also what keeps offscreen rendering exact.
        self._last_size: tuple[int, int] = tuple(self.canvas.get_physical_size())
        self._settle = 0

    def _make_canvas(self) -> Any:
        from rendercanvas.glfw import RenderCanvas

        _coalesce_resize_paints()
        s = self.settings
        if s.wayland_decorations == "server":
            # Must precede GLFW's init, which rendercanvas defers until the
            # first canvas is constructed -- so this is the last moment it can
            # be set, and setting it after would silently do nothing. The hint
            # is ignored on platforms where it does not apply.
            import glfw

            glfw.init_hint(glfw.WAYLAND_LIBDECOR, glfw.WAYLAND_DISABLE_LIBDECOR)
        canvas = RenderCanvas(
            title=s.title,
            size=(s.width, s.height),
            update_mode=s.update_mode,
            min_fps=s.min_fps,
            max_fps=s.max_fps,
            vsync=s.vsync,
        )
        # A real window means GLFW is initialised, which is all the system
        # clipboard needs. Installed here rather than at import so headless and
        # offscreen use keeps the in-process one, and skipped if an application
        # has already supplied its own -- an explicit choice outranks a default.
        if not clipboard.system_backed:
            clipboard.install(GlfwClipboard())
        return canvas

    def _wrap_canvas_close(self) -> None:
        """Drop this Engine's OWN reference to the wgpu context before the
        canvas destroys its native window, not after.

        `RenderCanvas.close()` -- called automatically the instant the user
        clicks the window's close button, from `_maybe_close()` inside
        `loop.run()`'s own polling, well before `run()`'s
        `finally: self.close()` ever gets a chance to run -- already drops
        the CANVAS's own reference to the wgpu context in the right order
        (context released, then `glfw.destroy_window()`). But `__init__`
        above also keeps its OWN, independent reference (`self.context`),
        and nothing dropped THAT one until `Engine.close()` ran -- by which
        point the native window was already gone. CPython only calls a
        `__del__` once an object's refcount reaches zero, so as long as this
        Engine's reference survived, so did the underlying wgpu surface --
        and releasing a surface whose native window no longer exists is a
        segfault deep in the platform's own windowing/graphics libraries,
        not something Python-level error handling can catch or recover
        from. Confirmed with `faulthandler` on a real crash: `Garbage-
        collecting` at interpreter shutdown, into `wgpu`'s `__del__`, into
        `wgpuSurfaceRelease`, into `libwayland-client`/the Vulkan driver.

        Patched on the canvas INSTANCE, not the class: unlike
        `_coalesce_resize_paints`, there is one canvas per Engine and no
        `weakbind`-style early capture to race, so patching the class would
        buy nothing -- and per-instance means an offscreen canvas, which
        owns no native window and so cannot hit this, is untouched if it
        never calls `close()` at all.
        """
        canvas = self.canvas
        original_close = canvas.close

        def _close() -> None:
            self._release_context()
            original_close()

        canvas.close = _close

    def _release_context(self) -> None:
        """Drop every reference to the wgpu context -- including the
        surface-resize bound method `__init__` derived from it.

        `self._set_surface_size` is a bound method of
        `self.context._wgpu_context` (see `__init__`, "Configures the
        swapchain"), which is a reference to that object independent of
        `self.context` itself. Dropping `self.context` alone leaves the
        actual surface object -- the one whose `__del__` calls
        `wgpuSurfaceRelease` -- alive via that bound method's own
        `__self__`, which is exactly what kept it alive past window
        destruction the first time this was fixed (same crash, same
        `faulthandler` trace, before and after `del self.context` alone).
        """
        context = getattr(self, "context", None)
        if context is not None:
            context.unconfigure()
            del self.context
        self._set_surface_size = None

    @property
    def pixel_ratio(self) -> float:
        """Device pixel ratio. Layout is in logical units; only paint uses this."""
        if self.settings.force_pixel_ratio > 0:
            return self.settings.force_pixel_ratio
        return float(self.canvas.get_pixel_ratio())

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def instance_count(self) -> int:
        """Instances drawn in the last frame -- all in one draw call."""
        return self._instance_count

    def set_theme(self, theme: Theme) -> None:
        """Swap the theme. One buffer upload -- no relayout, no display-list rebuild."""
        self.palette.rebuild(theme)
        self.request_draw()

    def request_draw(self) -> None:
        self.canvas.request_draw()

    # ---------------------------------------------------------------- frame

    def _pin_surface(self) -> None:
        """Hold the swapchain at a coarse size while the window is resizing.

        wgpu reconfigures the surface whenever the size it is told differs from
        the one it is configured at, and reconfiguring tears down and recreates
        the `VkSwapchainKHR`. During a drag that happens on every pixel: 1.35
        to 1.88 ms per frame against 0.043 measured on KDE Plasma, and it is
        the whole of the pointer trailing (ARCHITECTURE.md 5.8.1).

        Rounding the size up to `Settings.resize_bucket` makes the rebuild
        happen once per bucket instead of once per pixel. **The buffer is then
        larger than the window, and the compositor scales it back down** --
        measured, not assumed; it does not crop. That is exactly why nothing
        else here changes: the projection already describes the window
        (`_upload`), so content is drawn across the whole oversized buffer and
        the compositor's squeeze undoes the stretch. Geometry comes out exact.

        The cost is one non-integer resample, which softens text slightly. So
        the pin is released a few frames after the last size change: soft while
        a drag is in flight, when nobody is reading, and pixel-exact the moment
        it stops. Nothing is skipped or throttled -- every frame is still drawn
        and committed, which the reverted throttle proved is not optional.
        """
        if self._set_surface_size is None:
            return
        size = tuple(self.canvas.get_physical_size())
        target, self._settle = surface_size_for(
            size, self._last_size, self._settle, self.settings.resize_bucket
        )
        self._last_size = size
        if target != tuple(self.context._wgpu_context.physical_size):
            self._set_surface_size(*target)

    def request_close(self) -> None:
        """Ask for a graceful shutdown from anywhere, including a click handler.

        Only sets a flag and schedules a frame -- it must NOT close the
        canvas synchronously. A click handler runs from deep inside
        rendercanvas's own event-dispatch call stack, and destroying the
        GLFW window (freeing the native handle the wgpu surface is bound
        to) while that stack is still live segfaults the process outright
        (confirmed: exit code 139, not a clean exit). GLFW's own native
        close button avoids the exact same trap the exact same way -- its
        callback only sets a "should close" flag; the actual
        `glfw.destroy_window()` happens later, from the polling loop, once
        that stack has already unwound. `draw_frame()` below is this
        engine's equivalent safe point: reached fresh from the scheduler on
        a later iteration, never nested inside a handler's own call.
        """
        self._close_requested = True
        self.request_draw()

    def draw_frame(self) -> None:
        """One frame. Steps 6-9 of ARCHITECTURE.md 6; 1-5 arrive in M3.

        Every frame asked for is drawn and presented, including the hundreds a
        second a window resize produces. Skipping one is not the optimisation
        it looks like: a Wayland client is expected to commit a buffer in
        response to a configure, and declining leaves the compositor waiting.
        Measured on KDE Plasma, a throttle that skipped frames dropped a live
        resize from 466 redraws a second to 12 -- see ARCHITECTURE.md 5.8.1.
        """
        if self._close_requested:
            self.canvas.close()
            return
        self._pin_surface()
        self.display_list.clear()
        if self.painter is not None:
            self.painter(self.display_list)
        self._upload()
        encoder = self.device.create_command_encoder()
        render_pass = encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": self.context.get_current_texture().create_view(),
                    "resolve_target": None,
                    "clear_value": self.palette.linear("surface"),
                    "load_op": wgpu.LoadOp.clear,
                    "store_op": wgpu.StoreOp.store,
                }
            ]
        )
        self._draw_ui(render_pass)
        render_pass.end()
        self.device.queue.submit([encoder.finish()])
        self._frame_count += 1
        if self._settle:
            # Nothing else will ask for these. Without them an `ondemand`
            # application stops drawing the moment the drag does, and the
            # surface would stay pinned -- and so slightly soft -- until
            # something unrelated happened to need a frame.
            self.canvas.request_draw()

    def _upload(self) -> None:
        """Palette, globals, and instance uploads (step 7)."""
        if self.palette.dirty:
            self.pipeline.upload_palette(self.palette.data)
            self.palette.mark_uploaded()

        # New glyphs may have been packed during paint; push them before the
        # draw that samples them.
        self.text.atlas.upload()
        self.images.upload()

        width, height = self.canvas.get_physical_size()
        self.pipeline.upload_globals(width, height, self.pixel_ratio)

    def _draw_ui(self, render_pass: Any) -> None:
        """Step 8: the frame's single instanced draw."""
        self._instance_count = self.pipeline.draw(render_pass, self.display_list)

    # ---------------------------------------------------------------- lifecycle

    def run(self, on_frame: Callable[[], None] | None = None) -> None:
        from rendercanvas.glfw import loop

        self.canvas.request_draw(on_frame or self.draw_frame)
        try:
            loop.run()
        finally:
            self.close()

    def close(self) -> None:
        """Release every GPU object, in the order the surface requires.

        Not left to the garbage collector. rendercanvas terminates GLFW from a
        class attribute's `__del__` specifically so that it happens late,
        because "the release of the surface should happen before the
        termination of glfw" -- otherwise the process segfaults on exit
        (rendercanvas/glfw.py, citing pygfx/pygfx#642). An `Engine` reached
        from a module-level `App`, which is how every example is written,
        stays alive until interpreter shutdown and loses that race: closing
        the window destroyed the native window and left a live wgpu surface
        pointing at it.

        So the surface is unconfigured first, then the resources the device
        owns, then the device. Calling this twice is harmless.
        """
        self._release_context()
        if getattr(self, "text", None) is not None:
            self.text.atlas.destroy()
        if getattr(self, "images", None) is not None:
            self.images.destroy()
        pipeline = getattr(self, "pipeline", None)
        if pipeline is not None:
            pipeline.destroy()
            del self.pipeline
        device = getattr(self, "device", None)
        if device is not None:
            device.destroy()
            del self.device
        if getattr(self, "adapter", None) is not None:
            del self.adapter
