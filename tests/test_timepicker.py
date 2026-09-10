"""Time Picker: hour/minute steppers plus an AM/PM toggle.

Input variant only -- see the module docstring in `timepicker.py` for why
stepping (not typing) is the deliberate simplification here, the same trade
`SpinBox` already made. These tests focus on wraparound, the `value:`/
`on_change` binding, and click routing between the three regions.
"""

from __future__ import annotations

from pysilver import App, Theme
from pysilver.layout import Offset
from pysilver.paint import DisplayList
from pysilver.runtime.events import EventType, PointerEvent
from pysilver.spec import WidgetKind, parse_view
from pysilver.theme import Palette
from pysilver.tree.element import PaintContext
from pysilver.widgets.base import _REGISTRY, create_element
from pysilver.widgets.timepicker import TimePickerElement


def _app(*, calls: list[str] | None = None, **spec):
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [{"name": "tp", "widget": "TimePicker", **spec}],
    }
    app = App(view, theme=Theme(dark=True))
    if calls is not None:

        def changed(event: object) -> None:
            calls.append(event.value)  # type: ignore[attr-defined]

        app.handler(changed)
    app.mount()
    app.update()
    return app, app.root.find("tp")


def _click(app: App, x: float, y: float) -> None:
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=x, y=y))
    app.dispatcher.drain()
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=x, y=y))
    app.dispatcher.drain()


def _click_top(app: App, tp: TimePickerElement, rect: tuple[float, float, float, float]) -> None:
    x, y, w, _h = rect
    abs_rect = tp.absolute_rect()
    _click(app, abs_rect.x + x + w / 2, abs_rect.y + y + 5.0)


def _click_bottom(app: App, tp: TimePickerElement, rect: tuple[float, float, float, float]) -> None:
    x, y, w, h = rect
    abs_rect = tp.absolute_rect()
    _click(app, abs_rect.x + x + w / 2, abs_rect.y + y + h - 5.0)


# --------------------------------------------------------------- registered


def test_kind_builds() -> None:
    create_element(parse_view({"name": "x", "widget": "TimePicker"}).root)
    assert WidgetKind.TIME_PICKER in _REGISTRY


def test_is_focusable() -> None:
    from pysilver.runtime.events import FOCUSABLE_KINDS

    assert "TimePicker" in FOCUSABLE_KINDS


# ------------------------------------------------------------------ geometry


def test_size_is_fixed() -> None:
    _, tp = _app(value="09:30")
    assert (tp.size.width, tp.size.height) == (TimePickerElement.WIDTH, TimePickerElement.HEIGHT)


# ------------------------------------------------------------- initial state


def test_starts_from_the_bound_value() -> None:
    _, tp = _app(value="14:05")
    assert (tp._view.hour, tp._view.minute) == (14, 5)


def test_with_no_value_starts_from_the_current_time() -> None:
    import datetime

    _, tp = _app()
    now = datetime.datetime.now()
    assert (tp._view.hour, tp._view.minute) == (now.hour, now.minute)


def test_a_live_bound_value_also_starts_from_its_own_time() -> None:
    """`value: "{{ ... }}"` is a template, not a literal -- `spec.value` at
    construction time is the raw source string, not the rendered time, so
    `__init__` alone cannot derive the right hour/minute for a bound value
    the way it can for a static literal. `configure()` must run once after
    the binding's first render for this to work at all (`bind()` in
    `tree/element.py`) -- every other test in this file uses a literal
    value and would not catch a regression here."""
    from pysilver import App, Signal, Theme

    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [{"name": "tp", "widget": "TimePicker", "value": "{{ chosen.get() }}"}],
    }
    app = App(view, theme=Theme(dark=True))
    chosen = Signal("14:05", name="chosen")
    app.expose(chosen=chosen)
    app.mount()
    app.update()
    tp = app.root.find("tp")
    assert (tp._view.hour, tp._view.minute) == (14, 5)


# ---------------------------------------------------------------- stepping


def test_clicking_the_top_of_the_hour_field_increments_and_fires_on_change() -> None:
    calls: list[str] = []
    app, tp = _app(calls=calls, value="09:30", handlers={"on_change": "changed"})
    _click_top(app, tp, tp._hour_rect())
    assert tp._value == "10:30"
    assert calls == ["10:30"]


def test_hour_wraps_from_twelve_to_one() -> None:
    app, tp = _app(value="12:00")
    _click_top(app, tp, tp._hour_rect())
    assert tp._value == "13:00"  # 12 PM -> 1 PM, period unchanged


def test_hour_decrement_wraps_from_twelve_to_eleven_without_touching_the_period() -> None:
    app, tp = _app(value="00:00")  # 12 AM
    _click_bottom(app, tp, tp._hour_rect())
    assert tp._value == "11:00"  # hour and period step independently, like two SpinBox fields


def test_clicking_the_bottom_of_the_minute_field_decrements_and_wraps() -> None:
    app, tp = _app(value="09:00")
    _click_bottom(app, tp, tp._minute_rect())
    assert tp._value == "09:59"  # minute wraps on its own; the hour is untouched


def test_minute_increment_wraps_past_fifty_nine() -> None:
    app, tp = _app(value="09:59")
    _click_top(app, tp, tp._minute_rect())
    assert tp._value == "09:00"


def test_clicking_pm_switches_the_period_without_changing_minutes() -> None:
    calls: list[str] = []
    app, tp = _app(calls=calls, value="09:15", handlers={"on_change": "changed"})
    _click_bottom(app, tp, tp._period_rect())
    assert tp._value == "21:15"
    assert calls == ["21:15"]


def test_clicking_am_on_an_already_am_time_does_not_refire() -> None:
    calls: list[str] = []
    app, tp = _app(calls=calls, value="09:15", handlers={"on_change": "changed"})
    _click_top(app, tp, tp._period_rect())
    assert calls == []


def test_a_disabled_time_picker_ignores_clicks() -> None:
    calls: list[str] = []
    app, tp = _app(calls=calls, value="09:15", disabled="true", handlers={"on_change": "changed"})
    _click_top(app, tp, tp._hour_rect())
    assert tp._value == "09:15"
    assert calls == []


# ------------------------------------------------------------------- paint


def test_painting_does_not_crash() -> None:
    _, tp = _app(value="09:15")
    dl = DisplayList()
    ctx = PaintContext(display_list=dl, palette=Palette(Theme(dark=True)))
    tp.paint(ctx, Offset(0.0, 0.0))
    assert dl.view.shape[0] > 0
