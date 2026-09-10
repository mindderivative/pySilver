"""Scrolling: a clipped viewport over content larger than itself.

The whole design rests on one decision: **scrolling is a paint-time
translation, not a relayout.** The content is measured once against unbounded
space on the scroll axis and keeps the offsets layout gave it; changing the
scroll position only changes the origin its subtree is painted from
(`ElementMixin.child_origin`). A wheel notch therefore costs one paint of the
viewport, not a layout pass over every row -- which matters here more than in
most toolkits, because Python is this framework's bottleneck and a relayout per
wheel event would be visible (ARCHITECTURE.md 12).

M3 has no scrollbar spec -- the catalogue mentions only that a scrolling menu
"shows a persistent scrollbar" -- so the indicator's dimensions here are
pySilver's own, and marked as such rather than presented as Material.
"""

from __future__ import annotations

from typing import Any, Final, override

from ..layout import INF, Axis, Constraints, Offset, Padding, Size
from ..runtime.events import PointerEvent, WheelEvent
from ..spec import WidgetSpec
from ..tree.element import PaintContext
from .base import _StyledMixin
from .material import _box

__all__ = ["ScrollViewElement"]


class ScrollViewElement(_StyledMixin, Padding):
    """A viewport that clips one oversized child and scrolls it.

    Wraps a single child, normally a Vertical::

        - name: list
          widget: ScrollView
          style: {height: 300, width: expand}
          children:
            - widget: Vertical
              children: [ ... many rows ... ]

    The viewport **must be bounded on its scroll axis**. A ScrollView that
    shrink-wrapped to its content would be exactly as tall as the thing it is
    supposed to be scrolling, so this raises rather than silently doing
    nothing -- the same choice `Flex` makes for flexible children in unbounded
    space.
    """

    #: Not from M3, which specifies no scrollbar. Sized to read as an indicator
    #: rather than a drag target, since there is no drag handling yet.
    BAR_THICKNESS: Final = 4.0
    BAR_MARGIN: Final = 2.0
    BAR_MIN_LENGTH: Final = 32.0
    BAR_RADIUS: Final = 2.0
    BAR_OPACITY: Final = 0.55

    #: One wheel notch is ~100 units from the backend; scrolling a full 100px
    #: per notch is jarring on a short list, so it is scaled to a line-ish step.
    WHEEL_SCALE: Final = 0.5

    #: How far either side of the 4dp thumb still counts as grabbing it. A 4dp
    #: target is unusable with a mouse, let alone a trackpad -- this is a
    #: pointer-precision allowance, not M3's finger-sized touch target, which
    #: pySilver deliberately does not implement (ARCHITECTURE.md 1.2.1).
    THUMB_GRAB_SLOP: Final = 6.0

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, spec.style.padding)
        self.init_element(spec)
        self._content = Size(0.0, 0.0)
        #: Elements whose *geometry* depends on this view's scroll offset --
        #: a collapsing app bar. Scrolling marks paint on this view alone, so
        #: anything sized from the offset has to be told, and told to relayout.
        self._followers: list[Any] = []

    @override
    def configure(self) -> None:
        self._padding = self.style.padding

    # ----------------------------------------------------------------- axis

    @property
    def axis(self) -> Axis:
        return Axis.HORIZONTAL if self.style.axis == "horizontal" else Axis.VERTICAL

    @property
    def horizontal(self) -> bool:
        return self.axis is Axis.HORIZONTAL

    def _main(self, size: Size) -> float:
        return size.width if self.horizontal else size.height

    # --------------------------------------------------------------- extent

    @property
    def content_size(self) -> Size:
        """Size of the scrolled content, measured against unbounded space."""
        return self._content

    @property
    def max_scroll(self) -> float:
        """How far the content can travel. 0 when it already fits."""
        return self._limit_for(self.size)

    def _limit_for(self, size: Size) -> float:
        """The scrollable extent against a given viewport.

        `_follower_travel()` is added back because a collapsed follower has
        *enlarged* this viewport; without it the extent would shrink as an app
        bar collapses and the two would feed back into each other.
        """
        pad = self._padding
        inset = pad.horizontal if self.horizontal else pad.vertical
        return max(
            0.0,
            self._main(self._content) + inset - self._main(size) + self._follower_travel(),
        )

    @property
    def scroll_offset(self) -> float:
        return self.state.scroll.x if self.horizontal else self.state.scroll.y

    @property
    def scrollable(self) -> bool:
        return self.max_scroll > 0.0

    def set_scroll(self, value: float) -> bool:
        """Move to an absolute offset, clamped. Returns whether it moved.

        Marks paint only. Nothing about the content's geometry has changed, so
        marking layout here would throw away the entire point of the design.
        """
        clamped = max(0.0, min(value, self.max_scroll))
        if clamped == self.scroll_offset:
            return False
        self.state.scroll = (
            Offset(clamped, self.state.scroll.y)
            if self.horizontal
            else Offset(self.state.scroll.x, clamped)
        )
        self.mark_needs_paint()
        self._notify_followers()
        return True

    def _notify_followers(self) -> None:
        for follower in self._followers:
            follower.mark_needs_layout()

    def scroll_by(self, delta: float) -> bool:
        return self.set_scroll(self.scroll_offset + delta)

    def follow(self, element: Any) -> None:
        """Relayout `element` whenever this view scrolls.

        The cost is explicit and local: a followed scroll view relayouts its
        follower every frame it moves. The scrolled *content* is untouched --
        that still travels at paint time.
        """
        if element not in self._followers:
            self._followers.append(element)

    # ---------------------------------------------------------------- events

    # ------------------------------------------------------------ dragging

    def grabs_thumb(self, x: float, y: float) -> bool:
        """Whether a press at this point is a grab of the scrollbar thumb."""
        if not self.scrollable or not self.style.scrollbar:
            return False
        rect = self.absolute_rect()
        tx, ty, tw, th = self.thumb_rect(Offset(rect.x, rect.y))
        slop = self.THUMB_GRAB_SLOP
        return (tx - slop <= x <= tx + tw + slop) and (ty - slop <= y <= ty + th + slop)

    @override
    def cursor_at(self, x: float, y: float) -> str | None:
        """A resize cursor over the thumb only.

        Claiming one over the whole viewport would be wrong: the content is
        what the pointer is usually over, and it has its own opinions.
        """
        if self.grabs_thumb(x, y):
            return "ew-resize" if self.horizontal else "ns-resize"
        return super().cursor_at(x, y)

    @property
    def dragging(self) -> bool:
        return "drag_from" in self.state.data

    def on_pointer_down(self, event: PointerEvent) -> None:
        """Begin a thumb drag, and claim the pointer for it.

        The claim matters: the thumb is drawn over the content, so the press
        lands on whatever row is underneath and capture would go there. Without
        taking it, the thumb would move for exactly one frame and then stop.
        """
        if not self.grabs_thumb(event.x, event.y):
            return
        self.state.data["drag_from"] = event.y if not self.horizontal else event.x
        self.state.data["drag_scroll"] = self.scroll_offset
        event.capture()
        event.stop_propagation()

    def on_pointer_move(self, event: PointerEvent) -> None:
        if not self.dragging:
            return
        track, thumb, _along = self.thumb_geometry()
        travel = track - thumb
        if travel <= 0.0:
            return
        # Thumb travel maps to scroll travel, so the content keeps pace with
        # the pointer instead of running ahead of it.
        moved = (event.x if self.horizontal else event.y) - self.state.data["drag_from"]
        self.set_scroll(self.state.data["drag_scroll"] + moved * (self.max_scroll / travel))

    def on_pointer_up(self, event: PointerEvent) -> None:
        self.state.data.pop("drag_from", None)
        self.state.data.pop("drag_scroll", None)

    def on_wheel(self, event: WheelEvent) -> None:
        """Consume the wheel, but only as far as this viewport can actually go.

        Propagation stops **only if the content moved**. At the end of a list
        the wheel keeps travelling to an enclosing scroll view, which is what
        every desktop toolkit does -- swallowing it unconditionally would trap
        the pointer in a fully-scrolled inner pane.
        """
        delta = event.dx if self.horizontal else event.dy
        if self.scroll_by(delta * self.WHEEL_SCALE):
            event.stop_propagation()

    # ---------------------------------------------------------------- layout

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        bounded = outer.has_bounded_width if self.horizontal else outer.has_bounded_height
        if not bounded:
            axis = "width" if self.horizontal else "height"
            raise ValueError(
                f"ScrollView needs a bounded {axis}; it was given unbounded space, "
                f"so it would size to its content and never scroll. Set style.{axis} "
                f"or place it inside something that constrains it."
            )

        viewport = Size(
            outer.max_width if outer.has_bounded_width else 0.0,
            outer.max_height if outer.has_bounded_height else 0.0,
        )
        pad = self._padding
        child = self.child
        if child is None:
            self._content = Size(0.0, 0.0)
        else:
            # Unbounded along the scroll axis so the content reports its true
            # extent; bounded across it so text wraps to the viewport.
            inner = Constraints(
                min_width=0.0,
                max_width=INF if self.horizontal else max(0.0, viewport.width - pad.horizontal),
                min_height=0.0,
                max_height=max(0.0, viewport.height - pad.vertical) if self.horizontal else INF,
            )
            child.layout(inner)
            child.offset = pad.top_left
            self._content = child.size

        size = outer.constrain(viewport)
        # Content may have shrunk since the last frame -- a hot reload that
        # removed rows can leave the offset past the new end. So can a
        # follower collapsing, which enlarges this viewport and reduces the
        # scrollable extent; followers must be told, or a collapsed app bar
        # would sit stale above a list that is back at its top.
        self.state.scroll = self._clamped_scroll(size)
        return size

    def _follower_travel(self) -> float:
        """How much height this view has *gained* from collapsed followers.

        Subtracted back out of the viewport when measuring the scrollable
        extent, so `max_scroll` is the same whether the app bar above is
        expanded or collapsed.

        Without this the two feed back into each other: collapsing the bar
        enlarges this viewport, which shrinks `max_scroll`, which clamps the
        offset down, which un-collapses the bar. The measured result was a
        list that snapped back to its top with the bar stuck collapsed. Making
        the extent invariant breaks the cycle at its source rather than
        chasing it with invalidations.
        """
        if self.horizontal:
            return 0.0
        return sum(
            max(0.0, float(f.expanded_height) - float(f.current_height))
            for f in self._followers
            if hasattr(f, "expanded_height")
        )

    def _clamped_scroll(self, size: Size) -> Offset:
        limit = self._limit_for(size)
        current = self.state.scroll
        value = current.x if self.horizontal else current.y
        clamped = max(0.0, min(value, limit))
        return Offset(clamped, current.y) if self.horizontal else Offset(current.x, clamped)

    # ----------------------------------------------------------------- paint

    #: Content is clipped to the viewport, so it is hit-tested there too --
    #: a control scrolled just past the edge must not take a click it cannot
    #: show a response to.
    CLIPS_CHILDREN = True

    @override
    def child_origin(self, absolute: Offset) -> Offset:
        """Translate the content. This is the whole scroll mechanism."""
        scroll = self.state.scroll
        return Offset(absolute.x - scroll.x, absolute.y - scroll.y)

    @override
    def child_paint_context(self, ctx: PaintContext, absolute: Any) -> PaintContext:
        """Clip content to the viewport.

        In-shader clipping, not scissor: the display list is one instanced draw
        call, so a scissor rect would have to break the batch (ARCHITECTURE.md
        5.8).
        """
        dpr = ctx.pixel_ratio
        return PaintContext(
            display_list=ctx.display_list,
            palette=ctx.palette,
            text=ctx.text,
            images=ctx.images,
            pixel_ratio=dpr,
            clip=(
                absolute.x * dpr,
                absolute.y * dpr,
                self.size.width * dpr,
                self.size.height * dpr,
            ),
            clip_radii=tuple(r * dpr for r in self.effective_radii),  # type: ignore[arg-type]
        )

    @override
    def paint_foreground(self, ctx: PaintContext, absolute: Any) -> None:
        """The thumb sits over the scrolled content, not under it.

        `paint_self` runs before children (ElementMixin.paint), so drawing the
        thumb there would put it behind every row -- invisible under the first
        opaque one. `paint_foreground` runs after children for exactly this.
        """
        if self.style.scrollbar and self.scrollable:
            self._paint_scrollbar(ctx, absolute)

    def thumb_geometry(self) -> tuple[float, float, float]:
        """(track length, thumb length, thumb offset along the track).

        Shared by painting and hit testing rather than recomputed for each --
        two copies of this would drift, and a thumb you can see but not grab is
        the exact failure that produces.
        """
        track = self._main(self.size) - self.BAR_MARGIN * 2
        if track <= 0.0:
            return (0.0, 0.0, 0.0)
        content = self._main(self._content)
        visible = self._main(self.size)
        thumb = max(self.BAR_MIN_LENGTH, track * (visible / content)) if content else track
        thumb = min(thumb, track)
        progress = (self.scroll_offset / self.max_scroll) if self.max_scroll else 0.0
        return (track, thumb, self.BAR_MARGIN + (track - thumb) * progress)

    def thumb_rect(self, absolute: Any) -> tuple[float, float, float, float]:
        """The thumb in absolute logical coordinates: (x, y, w, h)."""
        _track, thumb, along = self.thumb_geometry()
        if self.horizontal:
            return (
                absolute.x + along,
                absolute.y + self.size.height - self.BAR_THICKNESS - self.BAR_MARGIN,
                thumb,
                self.BAR_THICKNESS,
            )
        return (
            absolute.x + self.size.width - self.BAR_THICKNESS - self.BAR_MARGIN,
            absolute.y + along,
            self.BAR_THICKNESS,
            thumb,
        )

    def _paint_scrollbar(self, ctx: PaintContext, absolute: Any) -> None:
        track, _thumb, _along = self.thumb_geometry()
        if track <= 0.0:
            return
        x, y, w, h = self.thumb_rect(absolute)
        _box(
            ctx,
            x,
            y,
            w,
            h,
            token=ctx.palette.index(self.style.color or "outline_variant"),
            radius=self.BAR_RADIUS,
            alpha=self.BAR_OPACITY,
        )
