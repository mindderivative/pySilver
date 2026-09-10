"""A freeform drawing surface for application-drawn content.

M3 has nothing named `Canvas` -- checked directly against `M3-References`,
the same way every other ungrounded widget this session was -- so this is
designed from pySilver's own engine primitives instead of a spec. Two of them
were built with exactly this in mind and had no consumer until now:
`DisplayList.add_segment` (oriented lines/capsules) and the `ImageAtlas`
(packed images). `image()` is deliberately not exposed here -- that waits for
the `Image` widget itself to land, so the atlas-loading convention (how a
source is decoded, cached, and keyed) is designed once rather than twice.

**Why a Python callback rather than a declarative shape list.** Everything
else in a view file is data, but a `Canvas` exists precisely for content that
doesn't hold still long enough to be data -- a live chart, a custom gauge, a
data-driven scatter of marks whose count changes every frame. `Shape` already
covers the static case (one regular polygon, declared once); stacking N of
those for something that changes size at runtime would fight reconciliation
rather than use it. Flutter's `CustomPainter` and HTML5's `<canvas>` both
reach the same answer for the same reason, so this follows their shape:
the view names a handler, the handler receives a drawing context, and it
issues primitives against it directly.

**Only primitives the shader already has a branch for are exposed.**
ARCHITECTURE.md 12's single-draw-call rule is what already ruled out
rasterising arbitrary vector paths for `Shape`; the same limit applies here.
A stroked line, a filled rect, a filled circle, a stroked arc, a regular
polygon, and text -- the same vocabulary the rest of the widget set draws
with, just callable directly instead of through a widget's own `paint_self`.
"""

from __future__ import annotations

from typing import Final

import numpy as np

from ..layout import Constraints, EdgeInsets, Offset, Padding, Rect, Size
from ..paint import NO_TOKEN
from ..spec import WidgetSpec
from ..theme import srgb_to_linear
from ..tree.element import PaintContext
from .base import _StyledMixin, measure_text, paint_text

__all__ = ["CanvasContext", "CanvasElement"]

_WHITE: Final = (1.0, 1.0, 1.0, 1.0)
_TRANSPARENT: Final = (0.0, 0.0, 0.0, 0.0)

#: A str names a palette token, resolved through `ctx.palette` so themed
#: content re-tints on a theme switch the same way every other widget's does.
#: A literal RGBA tuple opts out of theming -- for data-driven colour (a
#: chart bar tinted by its value) that has no semantic role to name. Given as
#: the ordinary sRGB values they are meant to look like (`(0.2, 0.2, 0.2,
#: 1.0)` for a dark grey, the same numbers a colour picker would show) --
#: `_linear()` converts every one before it reaches the display list, which
#: wants linear RGBA because the render target is `rgba8unorm-srgb` and
#: encodes on write (ARCHITECTURE.md 5.6.1). Verified empirically, not
#: assumed: an unconverted `color=(0.5, 0.5, 0.5, 1.0)` read back as pixel
#: `(188, 188, 188)`, not `(128, 128, 128)`, before this was caught -- the
#: same double-encoding mistake 5.6.1 already documents for the palette
#: upload path, recurring here on an application's own literal colour.
_Color = str | tuple[float, float, float, float]


def _linear(color: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    r, g, b = srgb_to_linear(np.array(color[:3], dtype=np.float64))
    return (float(r), float(g), float(b), color[3])


class CanvasContext:
    """The drawing surface an `on_paint` handler receives.

    Every coordinate is logical px relative to the `Canvas` widget's own
    top-left -- the handler never touches the pixel ratio, which is applied
    once here, exactly as `paint_self` applies it for every other widget.
    `size` is this canvas's own current laid-out size, for a handler that
    wants to fill or centre within it.
    """

    def __init__(self, ctx: PaintContext, origin: Offset, size: Size) -> None:
        self._ctx = ctx
        self._ox = origin.x
        self._oy = origin.y
        self._dpr = ctx.pixel_ratio
        self.size = size

    def _fill(self, color: _Color) -> tuple[tuple[float, float, float, float], int]:
        if isinstance(color, str):
            return _WHITE, self._ctx.palette.index(color)
        return _linear(color), NO_TOKEN

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        thickness: float = 1.0,
        color: _Color = "on_surface",
        opacity: float = 1.0,
    ) -> None:
        """A capsule -- a stroked line with round caps -- between two points."""
        fill, token = self._fill(color)
        d = self._dpr
        self._ctx.display_list.add_segment(
            (self._ox + x1) * d,
            (self._oy + y1) * d,
            (self._ox + x2) * d,
            (self._oy + y2) * d,
            thickness=thickness * d,
            color=fill,
            token=token,
            opacity=opacity,
            clip=self._ctx.clip,
            clip_radii=self._ctx.clip_radii,
        )

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        color: _Color = "on_surface",
        corner_radius: float = 0.0,
        border_width: float = 0.0,
        border_color: _Color | None = None,
        opacity: float = 1.0,
    ) -> None:
        """A filled, optionally rounded and bordered rectangle."""
        fill, token = self._fill(color)
        border_fill, border_token = (
            self._fill(border_color) if border_color is not None else (_TRANSPARENT, NO_TOKEN)
        )
        d = self._dpr
        self._ctx.display_list.add_box(
            (self._ox + x) * d,
            (self._oy + y) * d,
            width * d,
            height * d,
            color=fill,
            token=token,
            radii=(corner_radius * d,) * 4,
            border_width=border_width * d,
            border_color=border_fill,
            border_token=border_token,
            opacity=opacity,
            clip=self._ctx.clip,
            clip_radii=self._ctx.clip_radii,
        )

    def circle(
        self,
        cx: float,
        cy: float,
        radius: float,
        *,
        color: _Color = "on_surface",
        opacity: float = 1.0,
    ) -> None:
        """A filled circle -- a box whose corner radius is its own half-size,
        the same trick `Shape`'s corner-radius-to-maximum morph collapses to."""
        self.rect(
            cx - radius,
            cy - radius,
            radius * 2.0,
            radius * 2.0,
            color=color,
            corner_radius=radius,
            opacity=opacity,
        )

    def arc(
        self,
        cx: float,
        cy: float,
        radius: float,
        *,
        thickness: float,
        start: float,
        sweep: float,
        color: _Color = "on_surface",
        opacity: float = 1.0,
    ) -> None:
        """A stroked ring segment. `start`/`sweep` are radians clockwise from
        12 o'clock -- `add_arc`'s own convention, the one M3's circular
        progress indicator already draws with."""
        fill, token = self._fill(color)
        d = self._dpr
        self._ctx.display_list.add_arc(
            (self._ox + cx - radius) * d,
            (self._oy + cy - radius) * d,
            radius * 2.0 * d,
            radius * 2.0 * d,
            thickness=thickness * d,
            start=start,
            sweep=sweep,
            color=fill,
            token=token,
            opacity=opacity,
            clip=self._ctx.clip,
            clip_radii=self._ctx.clip_radii,
        )

    def polygon(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        sides: float,
        rotation: float = 0.0,
        corner_radius: float = 0.0,
        color: _Color = "on_surface",
        opacity: float = 1.0,
    ) -> None:
        """A regular polygon inscribed in the given box -- `sides` is a float
        for the same reason `Shape.sides` is: a value between whole numbers
        is a real shape, not a rounding error."""
        fill, token = self._fill(color)
        d = self._dpr
        self._ctx.display_list.add_polygon(
            (self._ox + x) * d,
            (self._oy + y) * d,
            width * d,
            height * d,
            sides=sides,
            rotation=rotation,
            corner_radius=corner_radius * d,
            color=fill,
            token=token,
            opacity=opacity,
            clip=self._ctx.clip,
            clip_radii=self._ctx.clip_radii,
        )

    def text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        font_size: float = 14.0,
        color: _Color = "on_surface",
        weight: int = 400,
        max_width: float | None = None,
        alignment: str = "start",
    ) -> None:
        """Shaped text at logical position `(x, y)`, top-left of the block."""
        if isinstance(color, str):
            token = self._ctx.palette.index(color)
            spans = None
        else:
            token = NO_TOKEN
            spans = [(0, len(text), _linear(color))]
        paint_text(
            self._ctx,
            self._ox + x,
            self._oy + y,
            text,
            font_size,
            token,
            max_width=max_width,
            alignment=alignment,
            weight=weight,
            spans=spans,
        )

    def measure_text(
        self,
        text: str,
        *,
        font_size: float = 14.0,
        max_width: float | None = None,
        weight: int = 400,
    ) -> Size:
        """Shaped size of `text`, for a handler that wants to position it
        itself -- centring a label on a data point, for instance."""
        return measure_text(text, font_size, max_width=max_width, weight=weight)


class CanvasElement(_StyledMixin, Padding):
    """A leaf widget whose content comes entirely from an `on_paint` handler.

    The view names it under the existing `handlers:` block -- `on_paint`,
    satisfying `WidgetSpec`'s `on_`-prefix validator like every other handler
    key, resolved through the unmodified `bind_handlers` path. It is called
    with one argument, a `CanvasContext`, the same one-argument convention
    every other handler already has. There is no `Event` to carry one, so
    this widget calls it directly from `paint_self` rather than through
    `EventDispatcher._invoke`.

    **Invalidation is the application's job.** The handler is an opaque
    Python closure; the framework cannot know its output changed without
    calling it, so it is called exactly when this element itself repaints --
    same as every other widget's `paint_self`. An application whose drawing
    depends on state outside the normal binding/reconciliation path calls
    `app.root.find(name).mark_needs_paint()` itself: the same public method
    every element already has, not a new one.
    """

    #: A canvas with no explicit size and no bound from its parent still
    #: needs *something* concrete to draw into -- the lesson
    #: `ButtonElement.HEIGHT`'s docstring exists to avoid relearning, this
    #: codebase's own zero-size-and-draws-nothing trap.
    DEFAULT_SIZE: Final = 200.0
    #: See `TreeItemElement.HIDDEN_EXTENT` / ARCHITECTURE.md 5.8.6: a clip
    #: with either dimension at exact zero reads as "no clip" to the shader,
    #: not "hidden", so a genuinely empty intersection floors to this instead.
    HIDDEN_EXTENT: Final = 0.01
    CLIPS_CHILDREN = True

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        return outer.constrain(
            Size(
                outer.max_width if outer.has_bounded_width else self.DEFAULT_SIZE,
                outer.max_height if outer.has_bounded_height else self.DEFAULT_SIZE,
            )
        )

    def _clipped(self, ctx: PaintContext, absolute: Offset) -> PaintContext:
        dpr = ctx.pixel_ratio
        own = Rect(
            absolute.x * dpr, absolute.y * dpr, self.size.width * dpr, self.size.height * dpr
        )
        clip = own if ctx.clip[2] == 0.0 and ctx.clip[3] == 0.0 else Rect(*ctx.clip).intersect(own)
        width = clip.width if clip.width > 0.0 else self.HIDDEN_EXTENT
        height = clip.height if clip.height > 0.0 else self.HIDDEN_EXTENT
        return PaintContext(
            display_list=ctx.display_list,
            palette=ctx.palette,
            text=ctx.text,
            images=ctx.images,
            pixel_ratio=dpr,
            clip=(clip.x, clip.y, width, height),
            clip_radii=ctx.clip_radii,
        )

    def paint_self(self, ctx: PaintContext, absolute: Offset) -> None:
        super().paint_self(ctx, absolute)
        painter = self.handlers.get("on_paint")
        if painter is None or self.size.is_empty:
            return
        painter(CanvasContext(self._clipped(ctx, absolute), absolute, self.size))
