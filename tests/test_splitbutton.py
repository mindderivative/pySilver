"""Split Button: a primary action with an attached menu trigger.

The interesting case this covers is one the M3 catalogue review found the
hard way: a widget with a native `on_click`-named method double-fires
against a view-declared `on_click:` handler, since `EventDispatcher._invoke`
calls both. Routing is done via `on_pointer_down`/`_up` instead, using two
names (`on_leading_click`/`on_trailing_click`) the dispatcher has no
built-in opinion about -- these tests exist specifically to pin that each
region fires exactly once, for the region actually clicked.
"""

from __future__ import annotations

from pysilver import App, Theme
from pysilver.layout import Offset
from pysilver.paint import DisplayList
from pysilver.runtime.events import EventType, PointerEvent
from pysilver.spec import WidgetKind, parse_view
from pysilver.theme import Palette
from pysilver.tree.element import PaintContext
from pysilver.widgets.base import _REGISTRY, ButtonElement, create_element
from pysilver.widgets.splitbutton import SplitButtonElement


def _app(*, calls: list[str] | None = None, **spec):
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [{"name": "sb", "widget": "SplitButton", **spec}],
    }
    app = App(view, theme=Theme(dark=True))
    if calls is not None:
        _handlers(app, calls)
    app.mount()
    app.update()
    return app, app.root.find("sb")


def _click(app: App, x: float, y: float) -> None:
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=x, y=y))
    app.dispatcher.drain()
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=x, y=y))
    app.dispatcher.drain()


def _handlers(app: App, calls: list[str]) -> None:
    def leading(event: object) -> None:
        calls.append("leading")

    def trailing(event: object) -> None:
        calls.append("trailing")

    app.handler(leading)
    app.handler(trailing)


# --------------------------------------------------------------- registered


def test_kind_builds() -> None:
    create_element(parse_view({"name": "x", "widget": "SplitButton"}).root)
    assert WidgetKind.SPLIT_BUTTON in _REGISTRY


def test_is_focusable() -> None:
    from pysilver.runtime.events import FOCUSABLE_KINDS

    assert "SplitButton" in FOCUSABLE_KINDS


# ------------------------------------------------------------------ geometry


def test_height_matches_the_m3_button_height() -> None:
    _, sb = _app(text="Save")
    assert sb.size.height == ButtonElement.HEIGHT == 40.0


def test_width_covers_the_label_plus_the_trailing_trigger() -> None:
    _, short = _app(text="Go")
    _, long = _app(text="A much longer label")
    assert long.size.width > short.size.width
    assert short.size.width == short._leading_width() + short.GAP + short.TRAILING_WIDTH


def test_the_trailing_region_has_a_fixed_width_regardless_of_label() -> None:
    _, short = _app(text="Go")
    _, long = _app(text="A much longer label")
    assert short.TRAILING_WIDTH == long.TRAILING_WIDTH == SplitButtonElement.TRAILING_WIDTH


# -------------------------------------------------------------------- click


def test_clicking_the_leading_region_fires_only_that_handler() -> None:
    calls: list[str] = []
    app, sb = _app(
        calls=calls,
        text="Save",
        handlers={"on_leading_click": "leading", "on_trailing_click": "trailing"},
    )
    rect = sb.absolute_rect()
    _click(app, rect.x + 10, rect.y + 20)
    assert calls == ["leading"]


def test_clicking_the_trailing_region_fires_only_that_handler() -> None:
    calls: list[str] = []
    app, sb = _app(
        calls=calls,
        text="Save",
        handlers={"on_leading_click": "leading", "on_trailing_click": "trailing"},
    )
    rect = sb.absolute_rect()
    _click(app, rect.x + sb.size.width - 5, rect.y + 20)
    assert calls == ["trailing"]


def test_a_press_and_release_on_different_regions_fires_neither() -> None:
    calls: list[str] = []
    app, sb = _app(
        calls=calls,
        text="Save",
        handlers={"on_leading_click": "leading", "on_trailing_click": "trailing"},
    )
    rect = sb.absolute_rect()
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=rect.x + 10, y=rect.y + 20))
    app.dispatcher.drain()
    app.dispatcher.post(
        PointerEvent(EventType.POINTER_UP, x=rect.x + sb.size.width - 5, y=rect.y + 20)
    )
    app.dispatcher.drain()
    assert calls == []


def test_a_disabled_split_button_ignores_clicks() -> None:
    calls: list[str] = []
    app, sb = _app(
        calls=calls, text="Save", disabled="true", handlers={"on_leading_click": "leading"}
    )
    rect = sb.absolute_rect()
    _click(app, rect.x + 10, rect.y + 20)
    assert calls == []


# -------------------------------------------------------------------- paint


def test_painting_does_not_crash() -> None:
    _, sb = _app(text="Save")
    dl = DisplayList()
    ctx = PaintContext(display_list=dl, palette=Palette(Theme(dark=True)))
    sb.paint(ctx, Offset(0.0, 0.0))
    assert dl.view.shape[0] > 0
