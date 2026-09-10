"""The public application object: view + state + handlers + engine.

Ties the four trees together (ARCHITECTURE.md 4) and owns the frame pipeline
described in ARCHITECTURE.md 6.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from .config import Settings
from .layout import OFFSET_ZERO, Constraints, LayoutOwner, Size
from .motion import Ticker
from .motion.animation import MAX_FRAME_DELTA
from .paint import DisplayList
from .render.atlas import ImageAtlas
from .runtime.accessibility import AccessibleNode, Bridge, accessibility_tree
from .runtime.engine import Engine
from .runtime.events import Event, EventDispatcher, EventType, KeyEvent, PointerEvent, WheelEvent
from .runtime.hotreload import HotReloader
from .runtime.overlay import OverlayHost
from .runtime.signals import bind_thread
from .runtime.viewmodel import ViewModel, check_naming
from .spec import SpecError, ViewSpec, load_view, parse_view
from .text import TextEngine
from .theme import Palette, Theme
from .tree.element import PaintContext
from .tree.reconcile import ReconcileStats, reconcile
from .widgets import build_element

__all__ = ["App", "run"]

_POINTER_EVENTS = {
    "pointer_down": EventType.POINTER_DOWN,
    "pointer_up": EventType.POINTER_UP,
    "pointer_move": EventType.POINTER_MOVE,
}

#: Held-key repeat, in seconds. Not sourced from anywhere -- there is no M3
#: spec for keyboard repeat timing -- chosen to read as an ordinary desktop
#: default rather than a jump or a stutter. Needed because `rendercanvas`'s
#: GLFW backend drops every `glfw.REPEAT` action outright (confirmed by
#: reading `glfw.py`'s own `_on_key`: `else: # glfw.REPEAT / return`), so
#: without this, holding Backspace/Delete/an arrow key deletes or moves
#: exactly once and then does nothing until released and pressed again.
#: `_on_char` is unaffected -- GLFW's separate char callback already repeats
#: printable text input on its own, which is why only *action* keys (no
#: `char` event of their own) ever needed this.
KEY_REPEAT_DELAY: Final = 0.5
KEY_REPEAT_INTERVAL: Final = 0.05


class App:
    """A pySilver application."""

    def __init__(
        self,
        view: str | Path | ViewSpec | dict[str, Any],
        *,
        theme: Theme | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.theme = theme or Theme()
        self.palette = Palette(self.theme)

        self._source = Path(view) if isinstance(view, str | Path) else None
        #: Every file the view was assembled from, including fragments pulled
        #: in with `source:`. Hot reload watches all of them.
        self.sources: set[Path] = set()
        self.view = self._load(view)
        self.root = build_element(self.view.root)
        self.layout_owner = LayoutOwner()
        self.root.attach(self.layout_owner)

        self.text = TextEngine()
        self.root.set_text_engine(self.text)

        self.images = ImageAtlas()
        self.root.set_image_atlas(self.images)

        self.motion = Ticker(reduce_motion=self.settings.reduce_motion)
        self.root.set_ticker(self.motion)
        #: Time source for animation, in seconds. Replaceable so that anything
        #: needing a reproducible frame -- a golden image, a timing test -- can
        #: drive time itself instead of racing the wall clock. Without this an
        #: animated baseline advances by however long the test setup took.
        self.clock: Callable[[], float] = time.perf_counter
        #: Last cursor pushed to the canvas. Tracked because the backend
        #: destroys and recreates a native cursor object on every call --
        #: setting it each frame would churn GLFW resources 60 times a second.
        self._cursor = "default"
        self._last_tick: float | None = None
        #: The key currently synthesizing repeats, and how long it has been
        #: held -- see `KEY_REPEAT_DELAY`/`KEY_REPEAT_INTERVAL`. None means no
        #: key is tracked for repeat, either because nothing is held or
        #: because a `key_up` for it already arrived.
        self._repeat_key: str | None = None
        self._repeat_modifiers: frozenset[str] = frozenset()
        self._repeat_elapsed = 0.0
        #: Whether `_repeat_elapsed` is still counting down the initial delay
        #: (False) or is now firing every `KEY_REPEAT_INTERVAL` (True).
        self._repeating = False

        self.overlays = OverlayHost()
        self.overlays.build(
            self.view.overlays, text_engine=self.text, image_atlas=self.images, ticker=self.motion
        )

        self.dispatcher = EventDispatcher()
        self.dispatcher.root = self.root
        self.dispatcher.overlays = self.overlays
        self.root.set_dispatcher(self.dispatcher)

        self.context: dict[str, Any] = {}
        self._handlers: dict[str, Callable[[Any], None]] = {}
        #: view file -> the ViewModel bound to it. One per file: including a
        #: fragment five times gives five copies of the view and one ViewModel.
        self._view_models: dict[str, ViewModel] = {}
        #: Optional platform bridge. None until an application binds one.
        self._a11y: Bridge | None = None
        self.engine: Engine | None = None
        self.reloader: HotReloader | None = None
        self.reload_errors: list[str] = []
        self._mounted = False

    def _load(self, view: str | Path | ViewSpec | dict[str, Any]) -> ViewSpec:
        if isinstance(view, ViewSpec):
            return view
        if isinstance(view, dict):
            return parse_view(view)
        self.sources = set()
        return load_view(view, sources=self.sources)

    # -------------------------------------------------------------- wiring

    def handler(self, fn: Callable[[Any], None]) -> Callable[[Any], None]:
        """Register an event handler by name, for view files to reference."""
        self._handlers[fn.__name__] = fn
        return fn

    def expose(self, **values: Any) -> None:
        """Publish names visible to ``{{ }}`` expressions in every view."""
        self.context.update(values)

    def bind_view_model(self, view: str, model: ViewModel) -> ViewModel:
        """Attach a ViewModel to one view file, by its path from the view root.

        Explicit rather than discovered from the filename: a view file naming
        its own module would let data decide what gets imported, and view files
        are untrusted input here. The application imports its own code and says
        what pairs with what; the `_View.yaml` / `_ViewModel.py` convention is
        then enforced so a mistake is an error rather than a silent no-op.

        This is what lets `app.py` stay an entry point. Signals and handlers
        belong to the view that uses them, including the root view.
        """
        check_naming(view, model)
        model._app = self
        self._view_models[view] = model
        return model

    def _context_for(self, view: str | None) -> dict[str, Any]:
        """Names visible to one view: the application's, then its own on top.

        A nested view can read what the application shares without ceremony,
        and shadow it deliberately where it needs to.
        """
        model = self._view_models.get(view or "")
        if model is None:
            return self.context
        return {**self.context, **model.names()}

    def mount(self) -> None:
        """Resolve handlers and subscribe bindings. Idempotent."""
        scoped = {view: vm.handlers() for view, vm in self._view_models.items()}
        missing = self.dispatcher.bind_handlers(
            self._handlers, extra=self.overlays.elements(), scoped=scoped
        )
        if missing:
            raise SpecError(
                "view references handlers that are not registered:\n  " + "\n  ".join(missing)
            )
        for element in self.root.walk_elements():
            element.bind(self._context_for(element.spec.view))
        self.overlays.bind(self.context, context_for=self._context_for)
        self.root.set_mounter(self._mount_subtree)
        self._mounted = True

    def _mount_subtree(self, subtree_root: Any) -> None:
        """`mount()`'s own per-element work, scoped to one subtree built
        after the initial mount -- see `ElementMixin.mounter`'s docstring for
        why `PageHost` needs this rather than being reachable by `mount()`'s
        own one-time walk. Re-resolves `scoped` freshly each call rather than
        caching it from `mount()`, since a `bind_view_model` call after
        `mount()` (not something this codebase does today, but nothing
        forbids it) would otherwise go stale here silently. Missing handlers
        fail loudly, the same contract `bind_handlers` already has -- a typo
        surfaces the moment the page is first activated, not as a silent
        no-op click.
        """
        scoped = {view: vm.handlers() for view, vm in self._view_models.items()}
        missing: list[str] = []
        for element in subtree_root.walk_elements():
            local = scoped.get(element.spec.view or "", {})
            handlers: dict[str, Callable[[Any], None]] = {}
            for event_key, name in element.spec.handlers.items():
                fn = local.get(name) or self._handlers.get(name)
                if fn is None:
                    label = element.spec.name or element.spec.id
                    missing.append(f"{label}.{event_key} -> {name!r}")
                else:
                    handlers[event_key] = fn
            element.handlers = handlers
            element.bind(self._context_for(element.spec.view))
        if missing:
            raise SpecError(
                "page references handlers that are not registered:\n  " + "\n  ".join(missing)
            )

    # ------------------------------------------------------------ hot reload

    @property
    def view_path(self) -> Path | None:
        """The file this view was loaded from, if any. Dict views have none."""
        return self._source

    def watch(self) -> HotReloader:
        """Start watching the view file for changes.

        Opt-in: a file watcher is unwanted overhead in a shipped application,
        so this is never started automatically unless Settings.hot_reload is on.
        """
        if self._source is None:
            raise ValueError("cannot watch a view that was not loaded from a file")
        # Watch the whole include graph: editing a fragment must reload the
        # view, or `source:` would silently break the best feature there is.
        watched = sorted(self.sources) or [self._source]
        if self.reloader is None or set(self.reloader.paths) != {p.resolve() for p in watched}:
            if self.reloader is not None:
                self.reloader.stop()
            self.reloader = HotReloader(watched)
        self.reloader.start()
        return self.reloader

    def unwatch(self) -> None:
        if self.reloader is not None:
            self.reloader.stop()

    def poll_reload(self) -> int:
        """Apply any pending file changes. Called from the engine thread.

        Returns the number of files reloaded successfully. A rejected reload is
        recorded in `reload_errors` and the previous tree keeps running.
        """
        if self.reloader is None:
            return 0
        # Any file in the include graph changing reloads the ENTRY view, not
        # the file that changed: a fragment is not a view on its own, and
        # loading one directly would fail on its `params:` block.
        entry = self._source
        events = self.reloader.apply(lambda _p: self.reload(entry) if entry else None)
        for event in events:
            if event.error:
                self.reload_errors.append(event.error)
        applied = sum(1 for e in events if not e.error and e.change != "deleted")
        if applied and self.engine is not None:
            self.engine.request_draw()
        return applied

    def reload(self, view: str | Path | ViewSpec | dict[str, Any]) -> ReconcileStats:
        """Swap in a new view, preserving runtime state where ids still match."""
        new_view = self._load(view)
        root, stats = reconcile(self.root, new_view.root, build_element)
        self.root = root
        assert isinstance(stats, ReconcileStats)
        self.view = new_view
        self.root.attach(self.layout_owner)
        self.root.set_text_engine(self.text)
        self.root.set_image_atlas(self.images)
        self.root.set_dispatcher(self.dispatcher)
        self.dispatcher.root = self.root
        self.overlays.build(
            new_view.overlays, text_engine=self.text, image_atlas=self.images, ticker=self.motion
        )
        if self._mounted:
            self.mount()
        return stats

    # ----------------------------------------------------------------- frame

    def _frame_delta(self) -> float:
        """Seconds since the previous frame.

        Measured once per frame and handed to the ticker, rather than sampled
        by whoever asks: a widget reading the clock itself would see a
        different value at layout time than at paint time.
        """
        now = self.clock()
        previous, self._last_tick = self._last_tick, now
        return 0.0 if previous is None else now - previous

    def logical_size(self) -> Size:
        if self.engine is not None:
            w, h = self.engine.canvas.get_logical_size()
            return Size(float(w), float(h))
        return Size(float(self.settings.width), float(self.settings.height))

    def update(self) -> None:
        """Frame steps 1-5: drain events, advance motion, flush signals, relayout."""
        self.poll_reload()
        self.dispatcher.drain()
        dt = self._frame_delta()
        self.motion.tick(dt)
        self._advance_key_repeat(dt)
        self.layout_owner.flush()
        self._drain_accessibility()
        size = self.logical_size()
        self.root.layout(Constraints.tight(size))
        self.overlays.layout(size, self.root)
        self._sync_cursor()

    def _advance_key_repeat(self, dt: float) -> None:
        """Fire a synthetic `key_down` for whatever key is held, once
        `KEY_REPEAT_DELAY` has passed and then every `KEY_REPEAT_INTERVAL`
        after -- see that constant's own comment for why this exists at
        all. A `while` loop rather than a single check, so a delayed frame
        (clamped to `MAX_FRAME_DELTA`, the same clamp `Ticker.tick` already
        uses) still fires every repeat it owes rather than dropping time.
        """
        if self._repeat_key is None:
            return
        self._repeat_elapsed += min(dt, MAX_FRAME_DELTA)
        fired = False
        while self._repeat_key is not None:
            threshold = KEY_REPEAT_INTERVAL if self._repeating else KEY_REPEAT_DELAY
            if self._repeat_elapsed < threshold:
                break
            self._repeat_elapsed -= threshold
            self._repeating = True
            self.dispatcher.post(
                KeyEvent(EventType.KEY_DOWN, key=self._repeat_key, modifiers=self._repeat_modifiers)
            )
            fired = True
        if fired:
            self.dispatcher.drain()

    def _sync_cursor(self) -> None:
        shape = self.dispatcher.cursor
        if shape == self._cursor or self.engine is None:
            return
        # Recorded only after the backend actually accepts it -- a widget
        # returning a name `rendercanvas.CursorShape` does not recognise
        # would otherwise still update `self._cursor`, so the next frame's
        # guard above sees no change and never retries. That is exactly how
        # DockSplit's "col-resize"/"row-resize" (CSS names; the backend's
        # own vocabulary is "ew-resize"/"ns-resize") went unnoticed: one
        # failed call, then permanent, silent no-ops.
        self.engine.canvas.set_cursor(shape)
        self._cursor = shape

    def paint(self, display_list: DisplayList) -> None:
        """Frame step 6: walk the element tree into the display list."""
        self.update()
        ctx = PaintContext(
            display_list=display_list,
            palette=self.palette,
            text=self.text,
            images=self.images,
            pixel_ratio=self.engine.pixel_ratio if self.engine else 1.0,
        )
        self.root.paint(ctx, OFFSET_ZERO)
        self.overlays.paint(ctx, self.palette, self.logical_size())
        if self._a11y is not None:
            # Cheap while nothing is listening: the adapter skips the work when
            # no screen reader is attached, which is what makes a per-frame
            # push affordable rather than needing change detection of its own.
            self._a11y.update(self.accessibility_tree())
        # The legitimate reasons to ask for another frame unprompted. An
        # application with nothing animating and no key held still renders
        # nothing. A held key needs its own frames the same way motion does
        # -- `_advance_key_repeat` only ever runs from inside `update()`,
        # which only runs when a frame is actually drawn.
        if (self.motion.active or self._repeat_key is not None) and self.engine is not None:
            self.engine.request_draw()

    def bind_accessibility(self, bridge: Bridge) -> Bridge:
        """Push this application's semantic tree to a platform adapter.

        Opt-in, like the clipboard's seam: the bridge is a native dependency
        and most applications will not want it. Once bound, the tree is pushed
        whenever a frame is produced, and action requests -- a screen reader
        pressing a button -- are drained on the engine thread.
        """
        self._a11y = bridge
        bridge.update(self.accessibility_tree())
        return bridge

    @property
    def accessibility(self) -> Bridge | None:
        """The bound platform bridge, if an application bound one."""
        return self._a11y

    def _drain_accessibility(self) -> None:
        """Act on what a screen reader asked for, on the engine thread.

        AccessKit delivers requests from its own D-Bus task and pySilver's
        signals are thread affine, so they arrive queued rather than applied.
        Only activation is honoured: it is the one action every clickable role
        advertises, and inventing behaviour for the rest would be guessing at
        what a reader meant.
        """
        bridge = self._a11y
        if bridge is None:
            return
        drain = getattr(bridge, "drain", None)
        target_of = getattr(bridge, "target_of", None)
        if drain is None or target_of is None:
            return
        for request in drain():
            node = target_of(request)
            if node is None or node.key is None:
                continue
            element = self.root.find(node.key) or next(
                (e for e in self.overlays.elements() if e.name == node.key), None
            )
            handler = element.handlers.get("on_click") if element is not None else None
            if handler is not None:
                handler(Event(EventType.CLICK, target=element))

    def accessibility_tree(self) -> AccessibleNode:
        """Snapshot what this interface *means*, for a bridge or for a test.

        Built on demand rather than maintained, so it cannot go stale: `paint`
        calls this every frame once a bridge is bound, but that is cheap
        because `Bridge.update` itself skips the work when nothing is
        listening -- see `runtime/accessibility.py`.
        """
        return accessibility_tree(self.root, self.overlays)

    def set_theme(self, theme: Theme) -> None:
        """One palette upload. No relayout, no display-list rebuild."""
        self.theme = theme
        self.palette.rebuild(theme)
        if self.engine is not None:
            self.engine.palette = self.palette
            self.engine.request_draw()

    # ------------------------------------------------------------- lifecycle

    def attach(self, engine: Engine) -> None:
        # One atlas per application: promote the App's CPU-only text engine to
        # the device rather than leaving the Engine's separate one bound.
        # Engine's own atlases become unreachable the moment their attributes
        # are overwritten below, but the GPU textures they own do not free
        # themselves -- destroyed here, the one place that knows they are
        # being orphaned rather than still in use (unlike `bind_glyph_atlas`/
        # `bind_image_atlas` themselves, which a test can call directly on a
        # texture nothing else has replaced yet, and must not destroy on its
        # behalf).
        old_text, old_images = engine.text, engine.images
        self.text.attach_device(engine.device)
        engine.text = self.text
        engine.pipeline.bind_glyph_atlas(self.text.atlas.texture)
        if old_text is not self.text:
            old_text.atlas.destroy()
        self.images.attach_device(engine.device)
        engine.images = self.images
        engine.pipeline.bind_image_atlas(self.images.texture)
        if old_images is not self.images:
            old_images.destroy()
        engine.palette = self.palette
        engine.painter = self.paint
        engine.canvas.add_event_handler(self._on_canvas_event, "*")
        self.engine = engine
        if not self._mounted:
            self.mount()
        if self.settings.hot_reload and self._source is not None:
            self.watch()

    def _on_canvas_event(self, event: dict[str, Any]) -> None:
        kind = event.get("event_type")
        match kind:
            case _ if kind in _POINTER_EVENTS:
                self.dispatcher.post(
                    PointerEvent(
                        _POINTER_EVENTS[kind],
                        x=float(event.get("x", 0.0)),
                        y=float(event.get("y", 0.0)),
                        button=int(event.get("button", 0) or 0),
                        modifiers=frozenset(event.get("modifiers", ())),
                    )
                )
            case "wheel":
                self.dispatcher.post(
                    WheelEvent(
                        EventType.WHEEL,
                        x=float(event.get("x", 0.0)),
                        y=float(event.get("y", 0.0)),
                        dx=float(event.get("dx", 0.0)),
                        dy=float(event.get("dy", 0.0)),
                        modifiers=frozenset(event.get("modifiers", ())),
                    )
                )
            case "key_down":
                key = str(event.get("key", ""))
                modifiers = frozenset(event.get("modifiers", ()))
                self.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key=key, modifiers=modifiers))
                # A single printable character (len(key) == 1) already repeats
                # correctly on its own via `_on_char` -- GLFW's `_on_key` only
                # lower-cases it when Shift is *not currently* held, so the same
                # physical key can report "J" on press and "j" on release if
                # Shift was let go in between. Tracking those here too, keyed on
                # an exact string match to clear them, left `_repeat_key` stuck
                # forever the moment that happened: a single tap of any shifted
                # letter would repeat indefinitely rather than stop on release.
                # Named action keys ("Backspace", "ArrowLeft", ...) never take
                # that lower-casing branch, so they stay exact and safe to track.
                if len(key) != 1:
                    self._repeat_key = key
                    self._repeat_modifiers = modifiers
                    self._repeat_elapsed = 0.0
                    self._repeating = False
            case "key_up":
                # Cleared unconditionally, not only on a string match against
                # `self._repeat_key` -- the same modifier-dependent renaming
                # above means a match can never be guaranteed, and the failure
                # mode of clearing a key's repeat state a moment early is far
                # safer than the one this replaces (clearing it never, at all).
                self._repeat_key = None
            case "char":
                self.dispatcher.post(KeyEvent(EventType.TEXT, text=str(event.get("data", ""))))
            case _:
                return
        if self.engine is not None:
            self.engine.request_draw()

    def run(self) -> None:
        bind_thread()
        engine = Engine(theme=self.theme, settings=self.settings)
        self.attach(engine)
        try:
            engine.run()
        finally:
            # A platform bridge runs a native thread that calls back into
            # Python; left alive at interpreter shutdown it panics reaching for
            # an interpreter that has finalised. Same shape as the GPU surface
            # outliving its window -- see `Engine.close`.
            close = getattr(self._a11y, "close", None)
            if close is not None:
                close()

    def close(self) -> None:
        """Request a graceful shutdown -- safe to wire to a Quit button, an
        Escape handler, or call from any code holding this App, including
        from inside a click handler.

        Delegates to `Engine.request_close()`, which only flags the request
        and schedules a frame rather than closing the canvas on the spot --
        see that method's docstring for why closing synchronously from a
        handler segfaults the process. The actual close happens from
        `Engine.draw_frame()` on a later, safe call, which is what makes
        rendercanvas's loop notice every canvas is closed and let the
        blocking `loop.run()` inside `Engine.run()` return; from there
        `Engine.run()`'s own `finally` releases GPU resources in the order
        the surface requires, and `run()` above returns normally -- the same
        graceful path a real window-close event already takes.

        A no-op before `run()` has attached an `Engine` -- there is nothing
        to close yet.
        """
        if self.engine is not None:
            self.engine.request_close()


def run(app: App) -> None:
    """Run *app* until its window closes."""
    app.run()
