"""M3 Split Button: a primary action with an attached menu trigger.

No pySilver widget composes two independently-clickable, independently-
shaped regions into one visual container before this -- `SpinBox` comes
closest (two icon-button regions flanking a number, `material.py`), and its
`_side_at`/per-side hover tracking is the pattern this reuses directly,
adapted to two *filled* regions rather than two borderless icon buttons.

**Anatomy** (`COMPONENT_SPLIT_BUTTONS.md`'s own measurements, M size): the
two buttons sit 2dp apart; the touching corners are squared to 4dp while
every outer corner stays fully rounded, so the pair still reads as one pill
split in two rather than two separate buttons. Size M only -- XS/S/L/XL are
real M3 variants, the same size ladder `Fab` already models, but a second
ladder here is a materially separate piece of work, not a style tweak.

`text:` is the leading button's label, the primary action. Routing to two
independent handlers -- `handlers.on_leading_click` and
`handlers.on_trailing_click` -- deliberately avoids the reserved
`handlers.on_click` name: `EventDispatcher._invoke` (`runtime/events.py`)
calls a view-declared `on_click:` handler *and*, separately, a widget's own
native `on_click` method if one exists, for every click regardless of which
region it landed in -- tried first, and caught by testing, the same lesson
`Switch`'s own drag support ran into. Routing is therefore done entirely
from `on_pointer_down`/`_up` (mirroring `Switch`'s own fix) using two names
the dispatcher has no built-in opinion about, so exactly one handler fires
per click, for the region actually clicked. The trailing region is a fixed
40dp-wide chevron trigger -- M3's own convention for what it opens ("The
menu should be 4dp from the split button"): a `Menu` overlay, anchored to
this widget's own `name`, opened and closed from `on_trailing_click`.
"""

from __future__ import annotations

from typing import Any, Final

from ..layout import Constraints, EdgeInsets, Padding, Size
from ..spec import WidgetSpec
from ..tree.element import PaintContext
from .base import ButtonElement, _StyledMixin, content_token, measure_text, paint_text
from .material import _state_alpha

__all__ = ["SplitButtonElement"]


class SplitButtonElement(_StyledMixin, Padding):
    """M3 Split Button, M size. See the module docstring."""

    HEIGHT: Final = ButtonElement.HEIGHT
    PAD_X: Final = ButtonElement.PAD_X
    LABEL_ROLE: Final = ButtonElement.LABEL_ROLE
    #: The trailing trigger's own fixed width -- a chevron alone, not a
    #: label, so it does not scale with anything the way the leading side
    #: does.
    TRAILING_WIDTH: Final = 40.0
    GAP: Final = 2.0
    OUTER_RADIUS: Final = HEIGHT / 2
    INNER_RADIUS: Final = 4.0
    CURSOR = "pointer"

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def _label_width(self) -> float:
        label = self._text.strip()
        if not label:
            return 0.0
        return measure_text(label, self.LABEL_ROLE, engine=self.text_engine).width

    def _leading_width(self) -> float:
        return max(self.HEIGHT, self._label_width() + 2 * self.PAD_X)

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = self._leading_width() + self.GAP + self.TRAILING_WIDTH
        return outer.constrain(Size(width, self.HEIGHT))

    # ------------------------------------------------------------- regions

    def _side_at(self, x: float) -> str:
        local = x - self.absolute_rect().x
        return "leading" if local < self._leading_width() else "trailing"

    def on_pointer_move(self, event: Any) -> None:
        side = self._side_at(event.x)
        if self.state.data.get("split_hover") != side:
            self.state.data["split_hover"] = side
            self.mark_needs_paint()

    def on_pointer_leave(self, event: Any) -> None:
        if self.state.data.get("split_hover") is not None:
            self.state.data["split_hover"] = None
            self.mark_needs_paint()

    def on_pointer_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        self.state.data["split_press_side"] = self._side_at(event.x)
        event.capture()

    def on_pointer_up(self, event: Any) -> None:
        if self.effective_disabled:
            return
        pressed_side = self.state.data.pop("split_press_side", None)
        if pressed_side is None or pressed_side != self._side_at(event.x):
            # Not a click on this element at all, or the press and release
            # landed on different regions -- neither counts as a click on
            # either one.
            return
        key = "on_leading_click" if pressed_side == "leading" else "on_trailing_click"
        handler = self.handlers.get(key)
        if handler is not None:
            handler(event)

    # --------------------------------------------------------------- paint

    def _side_alpha(self, side: str) -> float:
        # `_state_alpha` reads `self.state.hovered`/`pressed`/`focused`
        # whole-element, which cannot tell the two regions apart -- gated
        # here by whichever side the pointer is actually over, the same way
        # `SpinBox._side_alpha` scopes its own shared helper per side.
        if self.state.data.get("split_hover") != side:
            return 0.0
        return _state_alpha(self)

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        dpr = ctx.pixel_ratio
        container = ctx.palette.index(style.background or "primary")
        content = content_token(ctx, style, "on_primary")
        leading_w = self._leading_width()

        # Leading region: full radius on its own outer (left) corners,
        # squared on the side touching the trailing region.
        ctx.display_list.add_box(
            absolute.x * dpr,
            absolute.y * dpr,
            leading_w * dpr,
            self.HEIGHT * dpr,
            token=container,
            radii=(
                self.OUTER_RADIUS * dpr,
                self.INNER_RADIUS * dpr,
                self.INNER_RADIUS * dpr,
                self.OUTER_RADIUS * dpr,
            ),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        trailing_x = absolute.x + leading_w + self.GAP
        ctx.display_list.add_box(
            trailing_x * dpr,
            absolute.y * dpr,
            self.TRAILING_WIDTH * dpr,
            self.HEIGHT * dpr,
            token=container,
            radii=(
                self.INNER_RADIUS * dpr,
                self.OUTER_RADIUS * dpr,
                self.OUTER_RADIUS * dpr,
                self.INNER_RADIUS * dpr,
            ),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )

        _emit_state_layer_region(
            ctx,
            absolute.x,
            absolute.y,
            leading_w,
            self.HEIGHT,
            content,
            self._side_alpha("leading"),
        )
        _emit_state_layer_region(
            ctx,
            trailing_x,
            absolute.y,
            self.TRAILING_WIDTH,
            self.HEIGHT,
            content,
            self._side_alpha("trailing"),
        )

        label = self._text.strip()
        if label:
            metrics = measure_text(label, self.LABEL_ROLE, engine=self.text_engine)
            paint_text(
                ctx,
                absolute.x + (leading_w - metrics.width) / 2,
                absolute.y + (self.HEIGHT - metrics.height) / 2,
                label,
                self.LABEL_ROLE,
                content,
            )
        ctx.text.emit_icon(
            ctx.display_list,
            "expand_more",
            x=trailing_x + (self.TRAILING_WIDTH - 24.0) / 2,
            y=absolute.y + (self.HEIGHT - 24.0) / 2,
            size=24.0,
            pixel_ratio=dpr,
            token=content,
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )


def _emit_state_layer_region(
    ctx: PaintContext, x: float, y: float, w: float, h: float, token: int, alpha: float
) -> None:
    if alpha <= 0.001:
        return
    dpr = ctx.pixel_ratio
    ctx.display_list.add_box(
        x * dpr,
        y * dpr,
        w * dpr,
        h * dpr,
        token=token,
        color=(1.0, 1.0, 1.0, alpha),
        clip=ctx.clip,
        clip_radii=ctx.clip_radii,
    )
