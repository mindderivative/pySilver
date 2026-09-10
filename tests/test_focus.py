"""Focus rings and keyboard traversal.

On a pointer-and-keyboard framework keyboard traversal is a primary input path,
so an invisible focus state is a defect rather than a cosmetic gap
(ARCHITECTURE.md §1.2.1).
"""

from __future__ import annotations

import time

import pytest

from pysilver import App, Theme
from pysilver.paint import DisplayList
from pysilver.runtime.events import EventType, KeyEvent, PointerEvent
from pysilver.theme import Palette
from pysilver.tree.element import FOCUS_RING_OFFSET, FOCUS_RING_TOKEN, FOCUS_RING_WIDTH

VIEW = {
    "name": "root",
    "widget": "Vertical",
    "style": {"background": "surface", "padding": 10},
    "children": [
        {
            "name": "row",
            "widget": "Horizontal",
            "style": {"height": 56, "spacing": 16, "cross_alignment": "center"},
            "children": [
                {
                    "name": "btn",
                    "widget": "Button",
                    "text": "Go",
                    "style": {"width": 100, "height": 40},
                },
                {"name": "cb", "widget": "Checkbox"},
                {"name": "rd", "widget": "Radio"},
                {"name": "sw", "widget": "Switch"},
                {"name": "label", "widget": "Text", "text": "not focusable"},
            ],
        }
    ],
}


@pytest.fixture
def app():
    a = App(VIEW, theme=Theme(dark=True))
    a.mount()
    a.update()
    return a


def rings(dl: DisplayList) -> list:
    """Focus-ring instances only.

    Filtering on border width alone is not enough: an unchecked Checkbox,
    Radio, and Switch all draw 2dp borders of their own. The ring is
    identified by its full signature -- 2dp stroke, no fill, secondary token.
    """
    ring_token = Palette(Theme(dark=True)).index(FOCUS_RING_TOKEN)
    return [
        s
        for s in dl.view
        if float(s["params"][0]) == FOCUS_RING_WIDTH
        and float(s["fill"][3]) == 0.0
        and int(s["flags"][2]) == ring_token
    ]


def paint(app) -> DisplayList:
    dl = DisplayList()
    app.paint(dl)
    return dl


# --------------------------------------------------------------- traversal


def test_tab_order_is_document_order(app) -> None:
    assert [e.name for e in app.dispatcher.focus_order()] == ["btn", "cb", "rd", "sw"]


def test_text_is_not_focusable(app) -> None:
    assert "label" not in [e.name for e in app.dispatcher.focus_order()]


def test_controls_are_focusable_without_handlers(app) -> None:
    """A user must be able to Tab to a checkbox whether or not the view wired
    an on_click."""
    assert "cb" in [e.name for e in app.dispatcher.focus_order()]


def test_tab_moves_forward(app) -> None:
    d = app.dispatcher
    for expected in ("btn", "cb", "rd", "sw"):
        d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
        d.drain()
        assert d.focused.name == expected


def test_tab_wraps(app) -> None:
    d = app.dispatcher
    for _ in range(5):
        d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
        d.drain()
    assert d.focused.name == "btn"


def test_shift_tab_moves_backward(app) -> None:
    d = app.dispatcher
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    d.drain()
    assert d.focused.name == "cb"
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab", modifiers=frozenset({"shift"})))
    d.drain()
    assert d.focused.name == "btn"


def test_tab_works_from_nothing_focused(app) -> None:
    """The state an application starts in."""
    d = app.dispatcher
    assert d.focused is None
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    d.drain()
    assert d.focused is not None


def test_escape_clears_focus(app) -> None:
    d = app.dispatcher
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    d.drain()
    d.post(KeyEvent(EventType.KEY_DOWN, key="Escape"))
    d.drain()
    assert d.focused is None


# ------------------------------------------------------------ focus-visible


def test_keyboard_focus_shows_the_ring(app) -> None:
    d = app.dispatcher
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    d.drain()
    assert d.focused.state.focus_visible
    assert len(rings(paint(app))) == 1


def test_clicking_focuses_without_a_ring(app) -> None:
    """Desktop convention. Without this split every click leaves a ring behind."""
    d = app.dispatcher
    r = app.root.find("btn").absolute_rect()
    d.post(PointerEvent(EventType.POINTER_DOWN, x=r.x + 5, y=r.y + 5))
    d.drain()
    assert d.focused.name == "btn"
    assert not d.focused.state.focus_visible
    assert rings(paint(app)) == []


def test_tab_after_a_click_restores_the_ring(app) -> None:
    d = app.dispatcher
    r = app.root.find("btn").absolute_rect()
    d.post(PointerEvent(EventType.POINTER_DOWN, x=r.x + 5, y=r.y + 5))
    d.drain()
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    d.drain()
    assert d.focused.state.focus_visible
    assert len(rings(paint(app))) == 1


def test_clicking_does_not_leave_a_state_layer_either(app) -> None:
    """The same click-is-silent convention `rings()` already covers applies
    to the tonal state-layer overlay every M3 widget shares via
    `_emit_state_layer`/`_state_alpha` -- not just the ring. Found live: a
    button kept showing a visible focus tint after a plain mouse click,
    traced to `_state_alpha` reading `state.focused` (true for a click too)
    instead of `state.focus_visible` (true only for keyboard focus)."""
    from pysilver.widgets.material import _state_alpha

    d = app.dispatcher
    r = app.root.find("btn").absolute_rect()
    d.post(PointerEvent(EventType.POINTER_DOWN, x=r.x + 5, y=r.y + 5))
    d.post(PointerEvent(EventType.POINTER_UP, x=r.x + 5, y=r.y + 5))
    d.drain()
    assert d.focused.name == "btn"
    assert _state_alpha(d.focused) == 0.0

    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    d.drain()
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab", modifiers=frozenset({"shift"})))
    d.drain()
    assert d.focused.name == "btn"
    assert d.focused.state.focus_visible
    # The first `_state_alpha` call above already created this element's
    # "state_layer" animation at 0.0; this second target needs real elapsed
    # time to transition (STATE_LAYER_MOTION = short2 = 100ms), and that
    # clock only advances via `update()`'s `motion.tick(dt)` -- called by
    # `app.paint()` (see `paint()` below), never by `_state_alpha` itself.
    for _ in range(4):
        paint(app)
        time.sleep(0.05)
    assert _state_alpha(d.focused) > 0.0


def test_moving_focus_clears_the_previous_ring(app) -> None:
    d = app.dispatcher
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    d.drain()
    first = d.focused
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    d.drain()
    assert not first.state.focus_visible
    assert len(rings(paint(app))) == 1, "two rings drawn at once"


def test_unfocused_tree_draws_no_ring(app) -> None:
    assert rings(paint(app)) == []


# -------------------------------------------------------------- appearance


def test_ring_surrounds_the_control(app) -> None:
    d = app.dispatcher
    d.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    d.drain()
    btn = app.root.find("btn")
    ring = rings(paint(app))[0]
    rect = [float(v) for v in ring["rect"]]
    assert rect[2] == btn.size.width + FOCUS_RING_OFFSET * 2
    assert rect[3] == btn.size.height + FOCUS_RING_OFFSET * 2


@pytest.mark.parametrize(
    ("wid", "expected"),
    [("btn", 22.0), ("cb", 4.0), ("rd", 12.0), ("sw", 18.0)],
)
def test_ring_follows_the_control_shape(app, wid: str, expected: float) -> None:
    """A rectangular ring around a circular control reads as a bug, so the ring
    uses each widget's *effective* radii, not its raw style."""
    app.dispatcher.focus(app.root.find(wid), keyboard=True)
    ring = rings(paint(app))[0]
    assert float(ring["radii"][0]) == pytest.approx(expected)


def test_ring_uses_a_palette_token(app) -> None:
    app.dispatcher.focus(app.root.find("btn"), keyboard=True)
    ring = rings(paint(app))[0]
    assert int(ring["flags"][2]) == Palette(Theme(dark=True)).index(FOCUS_RING_TOKEN)


def test_ring_is_a_stroke_not_a_fill(app) -> None:
    app.dispatcher.focus(app.root.find("btn"), keyboard=True)
    ring = rings(paint(app))[0]
    assert float(ring["fill"][3]) == 0.0


def test_focus_change_does_not_trigger_layout(app) -> None:
    paint(app)
    btn = app.root.find("btn")
    app.dispatcher.focus(btn, keyboard=True)
    assert btn.needs_paint and not btn.needs_layout
