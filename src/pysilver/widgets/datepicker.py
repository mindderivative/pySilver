"""M3 Date Picker: a calendar month grid for choosing a single date.

Modal variant, single-date selection only -- Modal Input (a typed date with
validation) and Date Range (two handles across the grid) are real M3
variants, each a materially separate piece of work rather than a style
tweak on this one, deferred the same way `Slider`'s own Discrete/Range
variants were.

**A plain widget, not a second overlay type.** M3 anatomy calls this a
"Modal date picker", but the modality itself is `Dialog`'s job -- a view
places this as `Dialog`'s child exactly the way `parts/confirm_dialog_View.yaml`
places `Text`/`Button` inside one, rather than teaching `runtime/overlay.py`
a new overlay shape for what is really just different content.

**Commits immediately on click, with no separate OK/Cancel step.** M3's own
anatomy lists "Text buttons" (OK/Cancel) as part of this widget, but that
implies a staged "pick, then confirm" flow this pass does not build --
clicking a day commits `value:` and fires `on_change` right away, a
deliberate simplification stated here rather than silently applied. An
application wanting a staged flow still gets one for free: `Dialog` is
already dismissable, so "OK" is just closing it once a date has been picked.

**Measurements are not fully sourced.** `COMPONENT_DATE_PICKERS.md`'s modal
size tables are images, the same gap `CircularProgress`'s default diameter
and `Carousel`'s medium item width already have -- 320dp width and 40dp day
cells here are pySilver's own reasonable choice, not a quoted figure, tiling
seven 40dp columns with a little margin either side.

The calendar grid itself is computed with the standard library's `calendar`
module (leap years, month lengths, weekday offsets) rather than by hand --
the one part of this widget with a genuinely correct, boring answer already
available, cited rather than reimplemented.
"""

from __future__ import annotations

import calendar
import datetime
from typing import Any, Final, override

from ..layout import Constraints, EdgeInsets, Padding, Size
from ..runtime.events import ChangeEvent, EventType
from ..spec import WidgetSpec
from ..spec.typescale import TYPE_SCALE
from ..tree.element import PaintContext
from .base import _StyledMixin, content_token, measure_text, paint_text
from .material import HOVER, _box

__all__ = ["DatePickerElement"]

_WEEKDAY_LABELS: Final = ("S", "M", "T", "W", "T", "F", "S")
_HEADLINE_ROLE: Final = TYPE_SCALE["headline-small"]
_LABEL_ROLE: Final = TYPE_SCALE["label-large"]
_BODY_ROLE: Final = TYPE_SCALE["body-medium"]


def _parse_iso(value: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        return None


class DatePickerElement(_StyledMixin, Padding):
    """M3 Date Picker, Modal variant, single date. See the module docstring."""

    WIDTH: Final = 320.0
    CELL: Final = 40.0
    HEADLINE_HEIGHT: Final = 80.0
    NAV_HEIGHT: Final = 48.0
    WEEKDAY_HEIGHT: Final = 32.0
    PAD_X: Final = (WIDTH - CELL * 7) / 2
    ROWS: Final = 6
    CURSOR = "pointer"

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)
        today = datetime.date.today()
        selected = _parse_iso(spec.value or "") or today
        self._view_year = selected.year
        self._view_month = selected.month

    @override
    def configure(self) -> None:
        selected = self._selected()
        if selected is not None:
            self._view_year, self._view_month = selected.year, selected.month

    def _selected(self) -> datetime.date | None:
        return _parse_iso(self._value)

    def _commit(self, date: datetime.date) -> None:
        formatted = date.isoformat()
        if formatted == self._value:
            return
        self._value = formatted
        handler = self.handlers.get("on_change")
        if handler is not None:
            handler(ChangeEvent(EventType.CHANGE, target=self, value=formatted))
        self.mark_needs_paint()

    def _shift_month(self, delta: int) -> None:
        month = self._view_month - 1 + delta
        self._view_year += month // 12
        self._view_month = month % 12 + 1
        self.mark_needs_paint()

    def _weeks(self) -> list[list[int]]:
        """Weeks of the displayed month, `0` marking a day outside it."""
        cal = calendar.Calendar(firstweekday=6)  # Sunday first
        return list(cal.monthdayscalendar(self._view_year, self._view_month))

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        height = (
            self.HEADLINE_HEIGHT + self.NAV_HEIGHT + self.WEEKDAY_HEIGHT + self.CELL * self.ROWS
        )
        return outer.constrain(Size(self.WIDTH, height))

    # ------------------------------------------------------------- pointer

    def _grid_top(self) -> float:
        return self.HEADLINE_HEIGHT + self.NAV_HEIGHT + self.WEEKDAY_HEIGHT

    def _nav_button_at(self, x: float, y: float) -> str | None:
        rect = self.absolute_rect()
        local_x = x - rect.x
        local_y = y - rect.y
        if not (self.HEADLINE_HEIGHT <= local_y < self.HEADLINE_HEIGHT + self.NAV_HEIGHT):
            return None
        if local_x < self.PAD_X + self.CELL:
            return "prev"
        if local_x > self.WIDTH - self.PAD_X - self.CELL:
            return "next"
        return None

    def _day_at(self, x: float, y: float) -> int | None:
        rect = self.absolute_rect()
        local_x = x - rect.x - self.PAD_X
        local_y = y - rect.y - self._grid_top()
        if local_x < 0.0 or local_y < 0.0:
            return None
        col = int(local_x // self.CELL)
        row = int(local_y // self.CELL)
        if not (0 <= col < 7 and 0 <= row < self.ROWS):
            return None
        weeks = self._weeks()
        if row >= len(weeks):
            return None
        day = weeks[row][col]
        return day or None

    def on_click(self, event: Any) -> None:
        if self.effective_disabled:
            return
        nav = self._nav_button_at(event.x, event.y)
        if nav == "prev":
            self._shift_month(-1)
            return
        if nav == "next":
            self._shift_month(1)
            return
        day = self._day_at(event.x, event.y)
        if day is not None:
            self._commit(datetime.date(self._view_year, self._view_month, day))

    def on_pointer_move(self, event: Any) -> None:
        day = self._day_at(event.x, event.y)
        if self.state.data.get("date_hover") != day:
            self.state.data["date_hover"] = day
            self.mark_needs_paint()

    def on_pointer_leave(self, event: Any) -> None:
        if self.state.data.get("date_hover") is not None:
            self.state.data["date_hover"] = None
            self.mark_needs_paint()

    # --------------------------------------------------------------- paint

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        dpr = ctx.pixel_ratio
        on_surface = content_token(ctx, style, "on_surface")
        on_variant = ctx.palette.index("on_surface_variant")
        primary = ctx.palette.index("primary")

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

        self._paint_headline(ctx, absolute, on_variant, on_surface)
        self._paint_nav(ctx, absolute, on_surface)
        self._paint_weekday_header(ctx, absolute, on_variant)
        self._paint_grid(ctx, absolute, on_surface, primary)

    def _paint_headline(
        self, ctx: PaintContext, absolute: Any, caption: int, headline: int
    ) -> None:
        selected = self._selected()
        # `%-d` (non-padded day) is a glibc/macOS strftime extension; Windows'
        # CRT raises ValueError on it outright. Building the day as a plain
        # int sidesteps the platform difference entirely rather than
        # branching on it.
        label = f"{selected.strftime('%a, %b')} {selected.day}" if selected else "Select date"
        paint_text(ctx, absolute.x + 24.0, absolute.y + 16.0, "Select date", _LABEL_ROLE, caption)
        paint_text(ctx, absolute.x + 24.0, absolute.y + 40.0, label, _HEADLINE_ROLE, headline)

    def _paint_nav(self, ctx: PaintContext, absolute: Any, content: int) -> None:
        dpr = ctx.pixel_ratio
        y = absolute.y + self.HEADLINE_HEIGHT
        label = f"{calendar.month_name[self._view_month]} {self._view_year}"
        # The left nav cell occupies [0, PAD_X + CELL] (matching the hit-test
        # boundary below) -- starting the label at PAD_X alone put it right
        # under the chevron_left icon instead of clear of it.
        paint_text(ctx, absolute.x + self.PAD_X + self.CELL, y + 12.0, label, _LABEL_ROLE, content)
        for name, cx in (
            ("chevron_left", absolute.x + self.PAD_X + self.CELL / 2),
            ("chevron_right", absolute.x + self.WIDTH - self.PAD_X - self.CELL / 2),
        ):
            ctx.text.emit_icon(
                ctx.display_list,
                name,
                x=cx - 12.0,
                y=y + self.NAV_HEIGHT / 2 - 12.0,
                size=24.0,
                pixel_ratio=dpr,
                token=content,
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )

    def _paint_weekday_header(self, ctx: PaintContext, absolute: Any, content: int) -> None:
        y = absolute.y + self.HEADLINE_HEIGHT + self.NAV_HEIGHT
        for col, label in enumerate(_WEEKDAY_LABELS):
            metrics = measure_text(label, _BODY_ROLE.size, engine=self.text_engine)
            x = absolute.x + self.PAD_X + col * self.CELL + (self.CELL - metrics.width) / 2
            paint_text(
                ctx, x, y + (self.WEEKDAY_HEIGHT - metrics.height) / 2, label, _BODY_ROLE, content
            )

    def _paint_grid(self, ctx: PaintContext, absolute: Any, on_surface: int, primary: int) -> None:
        today = datetime.date.today()
        selected = self._selected()
        top = absolute.y + self._grid_top()
        hovered = self.state.data.get("date_hover")

        for row, week in enumerate(self._weeks()):
            for col, day in enumerate(week):
                if not day:
                    continue
                cx = absolute.x + self.PAD_X + col * self.CELL + self.CELL / 2
                cy = top + row * self.CELL + self.CELL / 2
                this_date = datetime.date(self._view_year, self._view_month, day)
                is_selected = selected == this_date
                is_today = today == this_date

                if is_selected:
                    _box(
                        ctx,
                        cx - self.CELL / 2 + 2.0,
                        cy - self.CELL / 2 + 2.0,
                        self.CELL - 4.0,
                        self.CELL - 4.0,
                        token=primary,
                        radius=(self.CELL - 4.0) / 2,
                    )
                elif hovered == day:
                    _box(
                        ctx,
                        cx - self.CELL / 2 + 2.0,
                        cy - self.CELL / 2 + 2.0,
                        self.CELL - 4.0,
                        self.CELL - 4.0,
                        token=on_surface,
                        radius=(self.CELL - 4.0) / 2,
                        alpha=HOVER,
                    )
                elif is_today:
                    _box(
                        ctx,
                        cx - self.CELL / 2 + 2.0,
                        cy - self.CELL / 2 + 2.0,
                        self.CELL - 4.0,
                        self.CELL - 4.0,
                        token=primary,
                        radius=(self.CELL - 4.0) / 2,
                        alpha=0.0,
                        border_width=1.0,
                        border_token=primary,
                    )

                label = str(day)
                metrics = measure_text(label, _BODY_ROLE.size, engine=self.text_engine)
                token = (
                    ctx.palette.index("on_primary")
                    if is_selected
                    else (primary if is_today else on_surface)
                )
                paint_text(
                    ctx,
                    cx - metrics.width / 2,
                    cy - metrics.height / 2,
                    label,
                    _BODY_ROLE,
                    token,
                )
