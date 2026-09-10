"""M3 Carousel: a horizontal strip of items that resize as they scroll.

Two behaviours, and M3 draws the line between them explicitly:

* **uncontained** items "don't change size", and both free and snap scrolling
  suit it -- so this scrolls by pixels, like any horizontal viewport.
* **hero** and **multi_browse** items "automatically change size and snap into
  place to maintain the same layout" -- so these scroll by *item*, and an
  item's width comes from its position in the strip rather than its content.

That second mode is what makes a carousel a carousel rather than a horizontal
list, and it is why this is a widget of its own instead of a styled
`ScrollView`.

**The snap travels.** `position` is a continuous animated value, and every
width and offset is derived from it, so an item promoted from medium to large
grows *as it moves* rather than switching size on arrival -- which is what M3
means by items that "automatically change size and snap into place".

This is the one place a transition invalidates **layout** rather than paint
(`animated(..., invalidates="layout")`): item widths genuinely depend on
position here, so repainting alone would draw the old geometry. It costs one
carousel layout per frame while travelling -- measured at 0.2 ms for six items,
0.8 ms for a hundred, and 2.2 ms for three hundred, against a 16.7 ms frame.
Affordable at any sane carousel length, and the reason `ScrollView` must never
do the same thing.

Item *content* parallaxes as the strip moves -- see `CarouselItemElement`.

Dimensions are quoted from `COMPONENT_CAROUSEL.md`. The medium item width is
the one exception and is marked where it is defined.
"""

from __future__ import annotations

import math
from typing import Any, Final, override

from ..layout import Axis, Constraints, Flex, Offset, Size
from ..runtime.events import WheelEvent
from ..spec import WidgetSpec
from ..tree.element import PaintContext
from .base import _StyledMixin, measure_text, paint_text, paired_content_token
from .material import _box

__all__ = ["CarouselElement", "CarouselItemElement"]

#: "Item corner radius | 28dp"
ITEM_RADIUS: Final = 28.0


class CarouselElement(_StyledMixin, Flex):
    """The strip. Children are `CarouselItem`s.

    | Attribute | Value |
    |---|---|
    | Leading/trailing padding | 16dp |
    | Top/bottom padding | 8dp |
    | Padding between elements | 8dp |
    | Small item width | 40-56dp |
    | Alignment | vertically centred |
    """

    PAD_X: Final = 16.0
    PAD_Y: Final = 8.0
    GAP: Final = 8.0
    SMALL_MIN: Final = 40.0
    SMALL_MAX: Final = 56.0
    #: **Not sourced.** M3 calls the medium item "dynamic" and gives no figure,
    #: so this is pySilver's choice: twice the largest small item, which keeps
    #: the three sizes visibly distinct.
    MEDIUM: Final = 112.0
    #: Also not sourced -- the spec's size tables are images. Set `height:`.
    HEIGHT: Final = 160.0
    #: Width of an uncontained item that does not set its own.
    UNCONTAINED_WIDTH: Final = 200.0

    #: Item widths by position, for the layouts whose items change size.
    PATTERNS: Final = {
        "hero": ("large", "small"),
        "multi_browse": ("large", "medium", "small"),
    }

    #: M3's suggested pair for movement that "begins and ends on screen" is
    #: either Emphasized/500ms or Standard/300ms. The standard row is the right
    #: one here: a snap is driven by a wheel notch and repeats as fast as the
    #: user turns it, and 500ms of emphasis would queue up behind itself.
    SNAP_DURATION: Final = "medium2"
    SNAP_CURVE: Final = "standard"

    axis = Axis.HORIZONTAL

    def __init__(self, spec: WidgetSpec) -> None:
        Flex.__init__(self, axis=Axis.HORIZONTAL, spacing=self.GAP)
        self.init_element(spec)
        #: Total strip width including padding; set during layout.
        self._extent = 0.0

    @override
    def configure(self) -> None:
        self._spacing = self.GAP

    # ----------------------------------------------------------------- mode

    @property
    def layout_name(self) -> str:
        variant = self.style.variant
        return variant if variant in ("uncontained", "hero", "multi_browse") else "uncontained"

    @property
    def snaps(self) -> bool:
        """M3 recommends snap-scrolling for the layouts whose items resize."""
        return self.layout_name in self.PATTERNS

    # ---------------------------------------------------------------- index

    @property
    def index(self) -> int:
        """Item the carousel is settling on. Only meaningful when snapping."""
        return int(self.state.data.get("carousel_index", 0))

    @property
    def position(self) -> float:
        """Where the strip actually is, between items, mid-snap.

        An integer while at rest; fractional while travelling. Every width and
        offset is derived from this, which is what makes items resize *as they
        move* rather than jumping when they arrive.
        """
        value: float = self.animated(
            "index",
            float(min(self.index, max(0, len(self.children) - 1))),
            duration=self.SNAP_DURATION,
            curve=self.SNAP_CURVE,
            # Item widths depend on this, so it is genuinely a layout change.
            # Affordable only because a carousel holds a handful of items.
            invalidates="layout",
        )
        return value

    def set_index(self, value: int) -> bool:
        """Move to an item, clamped. Returns whether it moved.

        Unlike a scroll offset this marks **layout**, because in a snapping
        carousel an item's width genuinely depends on its position -- that is
        the behaviour M3 is describing. It stays cheap because a carousel holds
        a handful of items, not the thousand rows a `ScrollView` must assume.

        Sets the *destination*; `position` is where the strip actually is while
        it travels there.
        """
        clamped = max(0, min(value, max(0, len(self.children) - 1)))
        if clamped == self.index:
            return False
        self.state.data["carousel_index"] = clamped
        self.mark_needs_layout()
        return True

    @property
    def scroll_x(self) -> float:
        return self.state.scroll.x

    def set_scroll(self, value: float) -> bool:
        """Free pixel scrolling, for the uncontained layout."""
        clamped = max(0.0, min(value, self._max_scroll))
        if clamped == self.state.scroll.x:
            return False
        self.state.scroll = Offset(clamped, self.state.scroll.y)
        self.mark_needs_paint()
        return True

    # --------------------------------------------------------------- events

    def on_wheel(self, event: WheelEvent) -> None:
        """A horizontal strip takes either wheel axis.

        Most desktop mice have only a vertical wheel, so requiring a horizontal
        one would leave the carousel unusable for most users.
        """
        delta = event.dx if event.dx else event.dy
        if delta == 0.0:
            return
        step = 1 if delta > 0 else -1
        moved = (
            self.set_index(self.index + step)
            if self.snaps
            else self.set_scroll(self.scroll_x + delta * 0.5)
        )
        if moved:
            event.stop_propagation()

    #: Drag distance, in logical px, a snapping carousel needs before it
    #: commits to the next/previous item. Not M3-sourced -- the guidelines
    #: describe "swipe through one item at a time" but give no pixel
    #: threshold for a pointer's equivalent of a touch swipe.
    DRAG_INDEX_THRESHOLD: Final = 60.0

    def on_pointer_down(self, event: Any) -> None:
        self.state.data["carousel_drag_x"] = event.x
        self.state.data["carousel_drag_accum"] = 0.0
        event.capture()

    def on_pointer_move(self, event: Any) -> None:
        """Drag-to-scroll, additive to `on_wheel` -- M3's own guidelines
        describe moving through a carousel as swiping, and a pointer's
        direct-manipulation equivalent of a swipe is a drag, not a wheel
        notch. A snapping carousel accumulates drag distance and commits
        one index per `DRAG_INDEX_THRESHOLD` crossed, so a long drag can
        step through several items in one gesture, the same way a fast
        swipe would; an uncontained one just scrolls by the exact pixel
        delta, 1:1 with the pointer, since it is already free scrolling
        and has no items to snap to.
        """
        last_x = self.state.data.get("carousel_drag_x")
        if last_x is None:
            return
        dx = event.x - last_x
        self.state.data["carousel_drag_x"] = event.x
        if not self.snaps:
            self.set_scroll(self.scroll_x - dx)
            return
        accum = self.state.data.get("carousel_drag_accum", 0.0) + dx
        while accum <= -self.DRAG_INDEX_THRESHOLD:
            self.set_index(self.index + 1)
            accum += self.DRAG_INDEX_THRESHOLD
        while accum >= self.DRAG_INDEX_THRESHOLD:
            self.set_index(self.index - 1)
            accum -= self.DRAG_INDEX_THRESHOLD
        self.state.data["carousel_drag_accum"] = accum

    def on_pointer_up(self, event: Any) -> None:
        self.state.data.pop("carousel_drag_x", None)
        self.state.data.pop("carousel_drag_accum", None)

    # --------------------------------------------------------------- layout

    def _slot_width(self, slot_index: int, large: float) -> float:
        """Width of the keyline slot `slot_index` places past the leading edge."""
        if slot_index < 0:
            return self.SMALL_MAX  # already scrolled past the leading edge
        pattern = self.PATTERNS[self.layout_name]
        slot = pattern[min(slot_index, len(pattern) - 1)]
        if slot == "large":
            return large
        return self.MEDIUM if slot == "medium" else self.SMALL_MAX

    def _item_width(self, position: float, large: float) -> float:
        """Width for an item sitting `position` slots past the leading keyline.

        `position` is fractional mid-snap, so the width is interpolated between
        the two slots it lies between. That is the whole resize-as-they-travel
        behaviour: an item promoted from medium to large grows continuously
        rather than switching size on arrival.
        """
        low = math.floor(position)
        t = position - low
        if t == 0.0:
            return self._slot_width(low, large)
        return self._slot_width(low, large) * (1.0 - t) + self._slot_width(low + 1, large) * t

    def _uncontained_width(self, child: Any) -> float:
        style = getattr(child, "style", None)
        if style is not None and style.width.kind == "fixed":
            return float(style.width.value)
        return self.UNCONTAINED_WIDTH

    def _large_width(self, available: float) -> float:
        """Whatever the fixed slots leave over, which is M3's "dynamic"."""
        pattern = self.PATTERNS[self.layout_name]
        fixed = sum(
            self.MEDIUM if slot == "medium" else self.SMALL_MAX
            for slot in pattern
            if slot != "large"
        )
        gaps = self.GAP * (len(pattern) - 1)
        return max(self.SMALL_MAX, available - fixed - gaps)

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else 0.0
        height = outer.max_height if outer.has_bounded_height else self.HEIGHT
        item_height = max(0.0, height - self.PAD_Y * 2)
        available = max(0.0, width - self.PAD_X * 2)

        children = list(self.children)
        if not children:
            self._extent = 0.0
            return outer.constrain(Size(width, height))

        # One width per item, computed before any child is laid out, so each
        # child is measured exactly once.
        if self.snaps:
            large = self._large_width(available)
            where = self.position
            widths = [self._item_width(j - where, large) for j in range(len(children))]
        else:
            # Uncontained items "don't change size": each keeps its own width
            # and the strip scrolls past them.
            widths = [self._uncontained_width(child) for child in children]

        # Cumulative positions, then shift so the current item sits on the
        # leading keyline (snapping) or by the scroll offset (uncontained).
        positions: list[float] = []
        cursor = self.PAD_X
        for w in widths:
            positions.append(cursor)
            cursor += w + self.GAP
        self._extent = cursor - self.GAP + self.PAD_X

        # A snapping layout shifts during layout, because which item sits on
        # the leading keyline is what decides every item's width -- the two
        # cannot be separated. An uncontained layout shifts at paint time
        # instead, via `child_origin`, exactly as `ScrollView` does: its widths
        # do not depend on the offset, so relaying out to scroll would be waste.
        if self.snaps:
            # Interpolate the shift across the same widths, so the strip lands
            # exactly on the keyline at whole positions and travels smoothly
            # between them.
            where = min(max(0.0, self.position), float(len(children) - 1))
            low = min(int(where), len(children) - 1)
            high = min(low + 1, len(children) - 1)
            t = where - low
            shift = positions[low] * (1.0 - t) + positions[high] * t - self.PAD_X
        else:
            shift = 0.0
            # Re-clamp: items may have been removed since the last frame.
            self.state.scroll = Offset(
                min(self.scroll_x, self._max_scroll_for(width)), self.state.scroll.y
            )

        for child, w, x in zip(children, widths, positions, strict=True):
            child.layout(
                Constraints(
                    min_width=w, max_width=w, min_height=item_height, max_height=item_height
                )
            )
            child.offset = Offset(x - shift, self.PAD_Y)  # vertically centred by the padding

        return outer.constrain(Size(width, height))

    def _max_scroll_for(self, width: float) -> float:
        return max(0.0, self._extent - width)

    @property
    def _max_scroll(self) -> float:
        return self._max_scroll_for(self.size.width)

    # ---------------------------------------------------------------- paint

    @override
    def child_origin(self, absolute: Offset) -> Offset:
        """Paint-time translation for the uncontained layout.

        A snapping layout has already positioned its items during layout, so
        there is nothing left to translate.
        """
        if self.snaps:
            return absolute
        return Offset(absolute.x - self.scroll_x, absolute.y)

    CLIPS_CHILDREN = True

    @override
    def child_paint_context(self, ctx: PaintContext, absolute: Any) -> PaintContext:
        """Clip items to the strip, so one scrolled off does not spill out."""
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


class CarouselItemElement(_StyledMixin, Flex):
    """One item: a 28dp-rounded surface with an optional label.

    Sized entirely by its parent -- an item does not choose its own width in a
    resizing layout, which is the point of the component. `text:` is drawn over
    the bottom of the surface, where M3 puts an item's label.

    **Content parallaxes.** M3: "carousel items move at a different speed than
    their content". The content is laid out wider than the item and panned
    within it as a function of where the item sits in the strip, so it lags
    behind the container as the strip moves. That is a paint-time translation
    -- the same mechanism as scrolling -- so it costs nothing per frame beyond
    the repaint the movement already required.
    """

    RADIUS: Final = ITEM_RADIUS
    LABEL: Final = 14.0
    LABEL_PAD: Final = 12.0
    #: How far the content may pan, as a fraction of the item's width. The
    #: content is oversized by twice this so the pan never exposes an edge.
    #: Not sourced -- M3 describes the effect but gives no figure.
    PARALLAX: Final = 0.12

    axis = Axis.VERTICAL

    def __init__(self, spec: WidgetSpec) -> None:
        Flex.__init__(self, axis=Axis.VERTICAL, spacing=spec.style.spacing)
        self.init_element(spec)

    @override
    def configure(self) -> None:
        self._spacing = self.style.spacing

    @override
    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        radii = self.style.corner_radius
        return radii if any(radii) else (self.RADIUS,) * 4

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        # Takes exactly the box the carousel assigned it.
        size = Size(
            constraints.max_width if constraints.has_bounded_width else 0.0,
            constraints.max_height if constraints.has_bounded_height else 0.0,
        )
        # Content is oversized by the pan range on each side and centred, so
        # panning it never uncovers an edge of the item.
        margin = size.width * self.PARALLAX
        inner = Size(size.width + margin * 2, size.height)
        for child in self.children:
            child.layout(Constraints.loose(inner))
            child.offset = Offset(-margin, 0.0)
        return constraints.constrain(size)

    @property
    def parallax(self) -> float:
        """Horizontal pan of the content, in logical px.

        Derived from where the item sits across the strip: an item at the
        leading edge pans one way, one at the trailing edge the other, and an
        item in the middle not at all. No state and no clock -- it is a pure
        function of position, so it stays exact under a drag.
        """
        parent = self.parent
        if not isinstance(parent, CarouselElement):
            return 0.0
        viewport = parent.size.width
        if viewport <= 0.0 or self.size.width <= 0.0:
            return 0.0
        # The uncontained layout translates its children at paint time, so its
        # scroll offset has to be folded in to get the on-screen position.
        visual_x = float(self.offset.x) - (0.0 if parent.snaps else float(parent.scroll_x))
        centre = visual_x + self.size.width / 2.0
        normalised = (centre - viewport / 2.0) / (viewport / 2.0)
        normalised = max(-1.0, min(1.0, normalised))
        return float(-normalised * self.size.width * self.PARALLAX)

    @override
    def child_origin(self, absolute: Offset) -> Offset:
        return Offset(absolute.x + self.parallax, absolute.y)

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        radii = self.effective_radii
        _box(
            ctx,
            absolute.x,
            absolute.y,
            self.size.width,
            self.size.height,
            token=ctx.palette.index(style.background or "surface_container_high"),
            radius=radii[0],
        )

    @override
    def paint_foreground(self, ctx: PaintContext, absolute: Any) -> None:
        """The label sits **over** the item's visual.

        M3 carousel items hold images, so a label drawn with the background
        would be covered by the very content it captions -- which is exactly
        what happened before this existed.
        """
        style = self.style
        label = self._text.strip()
        if not label or self.size.width < self.LABEL_PAD * 2:
            return
        metrics = measure_text(label, self.LABEL, engine=self.text_engine)
        if metrics.width > self.size.width - self.LABEL_PAD * 2:
            return  # a clipped label is worse than none in a shrinking item
        paint_text(
            ctx,
            absolute.x + self.LABEL_PAD,
            absolute.y + self.size.height - metrics.height - self.LABEL_PAD,
            label,
            self.LABEL,
            paired_content_token(ctx, style, "on_surface"),
        )

    CLIPS_CHILDREN = True

    @override
    def child_paint_context(self, ctx: PaintContext, absolute: Any) -> PaintContext:
        """Clip content to the rounded item -- M3 items hold images."""
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
