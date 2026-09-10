"""M3 Time Picker: Input variant, hour/minute fields plus an AM/PM toggle.

**Input variant only.** The Dial variant -- dragging a clock hand around a
256dp analog face -- is a real M3 variant but a materially separate piece of
work (an entirely different interaction and paint model), deferred the same
way `DatePicker`'s Modal Input and Date Range were.

**A plain widget, not a second overlay type**, for the same reason as
`DatePicker`: M3 calls this a "Modal time picker", but the modality is
`Dialog`'s job. A view places this as `Dialog`'s own child.

**Stepping, not typing.** M3's own anatomy for the Input variant expects a
keyboard caret inside each field -- the entire point of "Input" versus
"Dial". Real digit entry needs `TextField`'s caret/selection/IME machinery
for what would otherwise be a half-built text field wearing this widget's
paint; `SpinBoxElement` (`material.py`) already made and stated this exact
trade for the same reason. Each field is instead a stepper: click its top
half to increment, its bottom half to decrement, wrapping (hour 1-12,
minute 0-59) -- the nearest already-established convention, not a new one.

**Commits immediately, with no separate OK/Cancel step** -- the same stated
simplification `DatePicker` makes, for the same reason: M3's anatomy lists
text buttons for a staged "pick, then confirm" flow this pass does not
build. `value:` is a 24-hour `"HH:MM"` string; clicking any control commits
it and fires `on_change` right away.

**Measurements**: field container 96x72dp and period-selector 52dp are
`COMPONENT_TIME_PICKERS.md`'s own quoted Input figures; the gaps between
elements and the 8dp field corner radius are not quoted (the source's
tables give component sizes, not the space between them) and are pySilver's
own reasonable choice, the same kind of gap `DatePicker`'s 320dp width and
40dp cells already have.
"""

from __future__ import annotations

import datetime
from typing import Any, Final, override

from ..layout import Constraints, EdgeInsets, Padding, Size
from ..runtime.events import ChangeEvent, EventType
from ..spec import WidgetSpec
from ..spec.typescale import TYPE_SCALE
from ..tree.element import PaintContext
from .base import _StyledMixin, content_token, measure_text, paint_text
from .material import HOVER, _box

__all__ = ["TimePickerElement"]

_HEADLINE_ROLE: Final = TYPE_SCALE["headline-small"]
_CAPTION_ROLE: Final = TYPE_SCALE["label-large"]
_DIGIT_ROLE: Final = TYPE_SCALE["display-medium"]
_PERIOD_ROLE: Final = TYPE_SCALE["title-small"]


def _parse_time(value: str) -> datetime.time | None:
    try:
        return datetime.time.fromisoformat(value.strip())
    except ValueError:
        return None


class TimePickerElement(_StyledMixin, Padding):
    """M3 Time Picker, Input variant. See the module docstring."""

    WIDTH: Final = 352.0
    PAD_X: Final = 24.0
    FIELD_WIDTH: Final = 96.0
    FIELD_HEIGHT: Final = 72.0
    SEP_WIDTH: Final = 24.0
    PERIOD_WIDTH: Final = 52.0
    GAP: Final = 12.0
    HEADLINE_HEIGHT: Final = 80.0
    BOTTOM_PAD: Final = 24.0
    CORNER: Final = 8.0
    HEIGHT: Final = HEADLINE_HEIGHT + FIELD_HEIGHT + BOTTOM_PAD
    CURSOR = "pointer"

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)
        now = datetime.datetime.now().time().replace(second=0, microsecond=0)
        self._view = _parse_time(spec.value or "") or now

    @override
    def configure(self) -> None:
        parsed = _parse_time(self._value)
        if parsed is not None:
            self._view = parsed

    def _commit(self, moment: datetime.time) -> None:
        formatted = moment.strftime("%H:%M")
        if formatted == self._value:
            return
        self._value = formatted
        self._view = moment
        handler = self.handlers.get("on_change")
        if handler is not None:
            handler(ChangeEvent(EventType.CHANGE, target=self, value=formatted))
        self.mark_needs_paint()

    def _step_hour(self, direction: int) -> None:
        hour12 = self._view.hour % 12 or 12
        hour12 = (hour12 - 1 + direction) % 12 + 1
        pm = self._view.hour >= 12
        hour24 = (hour12 % 12) + (12 if pm else 0)
        self._commit(self._view.replace(hour=hour24))

    def _step_minute(self, direction: int) -> None:
        minute = (self._view.minute + direction) % 60
        self._commit(self._view.replace(minute=minute))

    def _set_pm(self, pm: bool) -> None:
        hour12 = self._view.hour % 12 or 12
        hour24 = (hour12 % 12) + (12 if pm else 0)
        self._commit(self._view.replace(hour=hour24))

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        return outer.constrain(Size(self.WIDTH, self.HEIGHT))

    # ------------------------------------------------------------- regions

    def _hour_rect(self) -> tuple[float, float, float, float]:
        return (self.PAD_X, self.HEADLINE_HEIGHT, self.FIELD_WIDTH, self.FIELD_HEIGHT)

    def _minute_rect(self) -> tuple[float, float, float, float]:
        x = self.PAD_X + self.FIELD_WIDTH + self.GAP + self.SEP_WIDTH + self.GAP
        return (x, self.HEADLINE_HEIGHT, self.FIELD_WIDTH, self.FIELD_HEIGHT)

    def _period_rect(self) -> tuple[float, float, float, float]:
        mx, _my, mw, _mh = self._minute_rect()
        x = mx + mw + self.GAP
        return (x, self.HEADLINE_HEIGHT, self.PERIOD_WIDTH, self.FIELD_HEIGHT)

    def _target_at(self, x: float, y: float) -> str | None:
        rect = self.absolute_rect()
        local_x, local_y = x - rect.x, y - rect.y
        hx, hy, hw, hh = self._hour_rect()
        if hx <= local_x <= hx + hw and hy <= local_y <= hy + hh:
            return "hour_inc" if local_y < hy + hh / 2 else "hour_dec"
        mx, my, mw, mh = self._minute_rect()
        if mx <= local_x <= mx + mw and my <= local_y <= my + mh:
            return "minute_inc" if local_y < my + mh / 2 else "minute_dec"
        px, py, pw, ph = self._period_rect()
        if px <= local_x <= px + pw and py <= local_y <= py + ph:
            return "am" if local_y < py + ph / 2 else "pm"
        return None

    def on_click(self, event: Any) -> None:
        if self.effective_disabled:
            return
        target = self._target_at(event.x, event.y)
        if target == "hour_inc":
            self._step_hour(1)
        elif target == "hour_dec":
            self._step_hour(-1)
        elif target == "minute_inc":
            self._step_minute(1)
        elif target == "minute_dec":
            self._step_minute(-1)
        elif target == "am":
            self._set_pm(False)
        elif target == "pm":
            self._set_pm(True)

    def on_pointer_move(self, event: Any) -> None:
        target = self._target_at(event.x, event.y)
        if self.state.data.get("time_hover") != target:
            self.state.data["time_hover"] = target
            self.mark_needs_paint()

    def on_pointer_leave(self, event: Any) -> None:
        if self.state.data.get("time_hover") is not None:
            self.state.data["time_hover"] = None
            self.mark_needs_paint()

    # --------------------------------------------------------------- paint

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        dpr = ctx.pixel_ratio
        on_surface = content_token(ctx, style, "on_surface")
        on_variant = ctx.palette.index("on_surface_variant")
        field_bg = ctx.palette.index("surface_container_highest")
        selected_bg = ctx.palette.index("tertiary_container")
        on_selected = ctx.palette.index("on_tertiary_container")
        hovered = self.state.data.get("time_hover")

        ctx.display_list.add_box(
            absolute.x * dpr,
            absolute.y * dpr,
            self.size.width * dpr,
            self.size.height * dpr,
            token=ctx.palette.index(style.background or "surface_container_high"),
            radii=(28.0 * dpr,) * 4,
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        paint_text(
            ctx, absolute.x + 24.0, absolute.y + 16.0, "Select time", _CAPTION_ROLE, on_variant
        )

        pm = self._view.hour >= 12
        hour12 = self._view.hour % 12 or 12
        headline = f"{hour12:02d}:{self._view.minute:02d} {'PM' if pm else 'AM'}"
        paint_text(ctx, absolute.x + 24.0, absolute.y + 40.0, headline, _HEADLINE_ROLE, on_surface)

        self._paint_field(
            ctx, absolute, self._hour_rect(), f"{hour12:02d}", "hour", field_bg, on_surface
        )
        self._paint_field(
            ctx,
            absolute,
            self._minute_rect(),
            f"{self._view.minute:02d}",
            "minute",
            field_bg,
            on_surface,
        )

        sx = self.PAD_X + self.FIELD_WIDTH + self.GAP
        sep_metrics = measure_text(":", _DIGIT_ROLE.size, engine=self.text_engine)
        paint_text(
            ctx,
            absolute.x + sx + (self.SEP_WIDTH - sep_metrics.width) / 2,
            absolute.y + self.HEADLINE_HEIGHT + (self.FIELD_HEIGHT - sep_metrics.height) / 2,
            ":",
            _DIGIT_ROLE,
            on_surface,
        )

        self._paint_period(ctx, absolute, pm, hovered, selected_bg, on_selected, on_variant)

    def _paint_field(
        self,
        ctx: PaintContext,
        absolute: Any,
        rect: tuple[float, float, float, float],
        digits: str,
        name: str,
        bg: int,
        content: int,
    ) -> None:
        x, y, w, h = rect
        ax, ay = absolute.x + x, absolute.y + y
        _box(ctx, ax, ay, w, h, token=bg, radius=self.CORNER)

        hovered = self.state.data.get("time_hover")
        for suffix, cy in ((f"{name}_inc", ay), (f"{name}_dec", ay + h / 2)):
            if hovered == suffix:
                _box(ctx, ax, cy, w, h / 2, token=content, radius=0.0, alpha=HOVER)

        metrics = measure_text(digits, _DIGIT_ROLE.size, engine=self.text_engine)
        paint_text(
            ctx,
            ax + (w - metrics.width) / 2,
            ay + (h - metrics.height) / 2,
            digits,
            _DIGIT_ROLE,
            content,
        )

        dpr = ctx.pixel_ratio
        for icon, cy in (("expand_less", ay + 2.0), ("expand_more", ay + h - 18.0)):
            ctx.text.emit_icon(
                ctx.display_list,
                icon,
                x=ax + (w - 16.0) / 2,
                y=cy,
                size=16.0,
                pixel_ratio=dpr,
                token=content,
                color=(1.0, 1.0, 1.0, 0.6),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )

    def _paint_period(
        self,
        ctx: PaintContext,
        absolute: Any,
        pm: bool,
        hovered: str | None,
        selected_bg: int,
        on_selected: int,
        on_variant: int,
    ) -> None:
        x, y, w, h = self._period_rect()
        ax, ay = absolute.x + x, absolute.y + y
        _box(
            ctx,
            ax,
            ay,
            w,
            h,
            token=selected_bg,
            radius=self.CORNER,
            alpha=0.0,
            border_width=1.0,
            border_token=on_variant,
        )

        for label, is_pm, cy in (("AM", False, ay), ("PM", True, ay + h / 2)):
            selected = pm == is_pm
            if selected:
                _box(ctx, ax, cy, w, h / 2, token=selected_bg, radius=0.0)
            elif hovered == label.lower():
                _box(ctx, ax, cy, w, h / 2, token=on_variant, radius=0.0, alpha=HOVER)
            metrics = measure_text(label, _PERIOD_ROLE.size, engine=self.text_engine)
            paint_text(
                ctx,
                ax + (w - metrics.width) / 2,
                cy + (h / 2 - metrics.height) / 2,
                label,
                _PERIOD_ROLE,
                on_selected if selected else on_variant,
            )
