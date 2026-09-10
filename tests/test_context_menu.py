"""Right-click and context menus.

Two pieces: a `CONTEXT_MENU` event synthesised from a secondary press, and an
overlay placement that opens at the pointer rather than against an element.
"""

from __future__ import annotations

import pytest

from pysilver import App, Settings, Signal, Theme
from pysilver.paint import DisplayList
from pysilver.runtime.events import (
    MOUSE_PRIMARY,
    MOUSE_SECONDARY,
    EventType,
    PointerEvent,
)

MENU = {
    "name": "ctx",
    "widget": "Menu",
    "open": "{{ opened.get() }}",
    "style": {"placement": "pointer", "width": 180},
    "children": [
        {"name": "m1", "widget": "MenuItem", "text": "Cut"},
        {"name": "m2", "widget": "MenuItem", "text": "Copy"},
    ],
}


def hosted(*, size=(500, 400), with_menu: bool = True):
    opened = Signal(False)
    fired: list[tuple[float, float]] = []
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [
                    {
                        "name": "canvas",
                        "widget": "Container",
                        "style": {
                            "width": "expand",
                            "height": "expand",
                            "background": "surface_container",
                        },
                        "handlers": {"on_context_menu": "show"},
                    }
                ],
            },
            "overlays": [MENU] if with_menu else [],
        },
        theme=Theme(dark=True),
        settings=Settings(width=size[0], height=size[1]),
    )
    app.expose(opened=opened)

    @app.handler
    def show(event) -> None:
        fired.append((event.x, event.y))
        opened.set(True)

    app.mount()
    app.paint(DisplayList())
    return app, opened, fired


def press(app: App, x: float, y: float, button: int) -> None:
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=x, y=y, button=button))
    app.dispatcher.drain()
    app.paint(DisplayList())


# ------------------------------------------------------------------ event


def test_the_button_numbering_is_the_backends_own() -> None:
    """One-based, checked against rendercanvas rather than assumed: guessing
    this wrong fails silently, since nothing would ever fire."""
    assert (MOUSE_PRIMARY, MOUSE_SECONDARY) == (1, 2)


def test_a_secondary_press_fires_on_context_menu() -> None:
    app, _opened, fired = hosted()
    press(app, 120, 90, MOUSE_SECONDARY)
    assert fired == [(120, 90)]


def test_a_primary_press_does_not() -> None:
    app, _opened, fired = hosted()
    press(app, 120, 90, MOUSE_PRIMARY)
    assert fired == []


def test_a_right_click_does_not_press_focus_or_click() -> None:
    """A button left stuck in its pressed state is the visible bug this
    guards, and it appears the first time anyone right-clicks one."""
    clicks: list[int] = []
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [
                    {
                        "name": "b",
                        "widget": "Button",
                        "text": "Go",
                        "style": {"width": 120, "height": 40},
                        "handlers": {"on_click": "hit"},
                    }
                ],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=300, height=200),
    )

    @app.handler
    def hit(event) -> None:
        clicks.append(1)

    app.mount()
    app.paint(DisplayList())
    button = app.root.find("b")

    press(app, 50, 20, MOUSE_SECONDARY)
    assert not button.state.pressed
    assert not button.state.focused
    assert clicks == []

    # A right-click that lands and lifts over the button must not also fire
    # `on_click` alongside `on_context_menu` -- release is excluded the same
    # way press is, above.
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=50, y=20, button=MOUSE_SECONDARY))
    app.dispatcher.drain()
    assert clicks == [], "a right-click's release fired on_click"

    press(app, 50, 20, MOUSE_PRIMARY)
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=50, y=20, button=MOUSE_PRIMARY))
    app.dispatcher.drain()
    assert clicks == [1], "the primary button stopped working"
    assert button.state.focused


def test_the_event_carries_the_point_that_was_clicked() -> None:
    app, _opened, fired = hosted()
    press(app, 33, 77, MOUSE_SECONDARY)
    assert fired == [(33, 77)]


# -------------------------------------------------------------- placement


def test_a_menu_opens_at_the_pointer() -> None:
    app, _opened, _fired = hosted()
    press(app, 120, 90, MOUSE_SECONDARY)
    entry = app.overlays.visible()[0]
    assert (entry.origin.x, entry.origin.y) == (120, 90)


def test_it_flips_rather_than_running_off_the_edge() -> None:
    app, _opened, _fired = hosted(size=(500, 400))
    press(app, 470, 380, MOUSE_SECONDARY)
    entry = app.overlays.visible()[0]
    size = entry.element.size
    assert entry.origin.x + size.width <= 500
    assert entry.origin.y + size.height <= 400
    assert entry.origin.x < 470 and entry.origin.y < 380, "it did not flip"


def test_a_menu_larger_than_the_window_still_starts_on_screen() -> None:
    app, _opened, _fired = hosted(size=(200, 120))
    press(app, 190, 110, MOUSE_SECONDARY)
    entry = app.overlays.visible()[0]
    assert entry.origin.x >= 0
    assert entry.origin.y >= 0


def test_the_anchor_follows_the_most_recent_right_click() -> None:
    app, opened, _fired = hosted()
    press(app, 100, 100, MOUSE_SECONDARY)
    first = app.overlays.visible()[0].origin
    opened.set(False)
    app.paint(DisplayList())
    press(app, 200, 150, MOUSE_SECONDARY)
    second = app.overlays.visible()[0].origin
    assert (second.x, second.y) != (first.x, first.y)
    assert (second.x, second.y) == (200, 150)


def test_pressing_outside_dismisses_it() -> None:
    """Same rule an anchored overlay follows: a transient surface closes when
    you click away from it."""
    app, _opened, _fired = hosted()
    press(app, 120, 90, MOUSE_SECONDARY)
    assert app.overlays.visible()
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=400, y=350, button=MOUSE_PRIMARY))
    app.dispatcher.drain()
    app.paint(DisplayList())
    assert app.overlays.visible() == []


def test_escape_dismisses_it() -> None:
    from pysilver.runtime.events import KeyEvent

    app, _opened, _fired = hosted()
    press(app, 120, 90, MOUSE_SECONDARY)
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Escape"))
    app.dispatcher.drain()
    app.paint(DisplayList())
    assert app.overlays.visible() == []


def test_pointer_placement_needs_no_anchor_element() -> None:
    """The point of it: a context menu has no element to attach to."""
    from pysilver.spec import parse_view

    view = parse_view(
        {
            "root": {"name": "root", "widget": "Vertical"},
            "overlays": [
                {"name": "m", "widget": "Menu", "open": "true", "style": {"placement": "pointer"}}
            ],
        }
    )
    assert view.overlays[0].style.anchor is None
    assert view.overlays[0].style.placement == "pointer"


def test_an_unknown_placement_still_fails_at_load() -> None:
    from pysilver.spec import SpecError, parse_view

    with pytest.raises(SpecError):
        parse_view({"name": "m", "widget": "Menu", "style": {"placement": "elsewhere"}})
