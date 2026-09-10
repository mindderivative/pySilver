"""Events: hit testing, capture/bubble, hover, focus, pointer capture."""

from __future__ import annotations

import pytest

from pysilver.layout import Constraints, Size
from pysilver.runtime.events import (
    EventDispatcher,
    EventType,
    KeyEvent,
    Phase,
    PointerEvent,
)
from pysilver.spec import parse_view
from pysilver.widgets import build_element

VIEW = {
    "name": "root",
    "widget": "Stack",
    "style": {"width": 200, "height": 200},
    "children": [
        {"name": "under", "widget": "Container", "style": {"width": 200, "height": 200}},
        {
            "name": "over",
            "widget": "Button",
            "style": {"width": 100, "height": 100},
            "handlers": {"on_click": "go"},
        },
    ],
}


@pytest.fixture
def dispatcher():
    root = build_element(parse_view(VIEW).root)
    root.layout(Constraints.tight(Size(200, 200)))
    d = EventDispatcher()
    d.root = root
    return d


# ------------------------------------------------------------- hit testing


def test_hit_path_is_target_then_ancestors(dispatcher) -> None:
    """The path is the target and its ANCESTORS. An occluded sibling that also
    contains the point ('under') is not in it -- it did not receive the event."""
    assert [e.name for e in dispatcher.hit_path(50, 50)] == ["over", "root"]


def test_overlapping_siblings_resolve_to_the_last_painted(dispatcher) -> None:
    """A forward walk would report 'under'; paint order says 'over' won."""
    assert dispatcher.hit_path(50, 50)[0].name == "over"


def test_point_outside_the_top_child_falls_through(dispatcher) -> None:
    assert [e.name for e in dispatcher.hit_path(150, 150)] == ["under", "root"]


def test_point_outside_everything_is_empty(dispatcher) -> None:
    assert dispatcher.hit_path(999, 999) == []


# --------------------------------------------------------------- dispatch


def test_click_reaches_the_handler(dispatcher) -> None:
    calls: list[str] = []
    dispatcher.bind_handlers({"go": lambda e: calls.append("clicked")})
    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=50, y=50))
    dispatcher.post(PointerEvent(EventType.POINTER_UP, x=50, y=50))
    dispatcher.drain()
    assert calls == ["clicked"]


def test_release_elsewhere_is_not_a_click(dispatcher) -> None:
    calls: list[str] = []
    dispatcher.bind_handlers({"go": lambda e: calls.append("clicked")})
    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=50, y=50))
    dispatcher.post(PointerEvent(EventType.POINTER_UP, x=150, y=150))
    dispatcher.drain()
    assert calls == []


def test_phases_run_capture_then_target_then_bubble(dispatcher) -> None:
    seen: list[tuple[str, Phase]] = []
    root = dispatcher.root
    for element in root.walk_elements():
        element.handlers = {
            "on_pointer_down": (lambda e, el=element: seen.append((el.name, e.phase)))
        }
    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=50, y=50))
    dispatcher.drain()
    assert seen == [
        ("root", Phase.CAPTURE),
        ("over", Phase.TARGET),
        ("root", Phase.BUBBLE),
    ]


def test_stop_propagation_during_capture_prevents_the_target(dispatcher) -> None:
    """An ancestor can intercept before the target ever sees the event."""
    seen: list[str] = []
    for element in dispatcher.root.walk_elements():
        if element.name == "root":
            element.handlers = {"on_pointer_down": lambda e: e.stop_propagation()}
        else:
            element.handlers = {"on_pointer_down": (lambda e, el=element: seen.append(el.name))}
    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=50, y=50))
    dispatcher.drain()
    assert seen == [], "target ran despite an ancestor stopping capture"


def test_stop_propagation_at_the_target_prevents_bubbling(dispatcher) -> None:
    seen: list[str] = []
    root = dispatcher.root
    root.handlers = {"on_pointer_down": lambda e: seen.append(f"root:{e.phase.value}")}
    root.find("over").handlers = {"on_pointer_down": lambda e: e.stop_propagation()}
    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=50, y=50))
    dispatcher.drain()
    assert seen == ["root:capture"], "event bubbled after being stopped"


# ------------------------------------------------------------------ hover


def test_hover_enters_and_leaves(dispatcher) -> None:
    dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=50, y=50))
    dispatcher.drain()
    assert dispatcher.root.find("over").state.hovered

    dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=150, y=150))
    dispatcher.drain()
    assert not dispatcher.root.find("over").state.hovered
    assert dispatcher.root.find("under").state.hovered


def test_motion_events_coalesce(dispatcher) -> None:
    """A burst of motion must not queue a burst of work."""
    for i in range(20):
        dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=float(i), y=1.0))
    assert dispatcher.pending == 1


def test_non_motion_events_do_not_coalesce(dispatcher) -> None:
    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=1, y=1))
    dispatcher.post(PointerEvent(EventType.POINTER_UP, x=1, y=1))
    assert dispatcher.pending == 2


# --------------------------------------------------------- press and capture


def test_press_sets_and_clears_state(dispatcher) -> None:
    over = dispatcher.root.find("over")
    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=50, y=50))
    dispatcher.drain()
    assert over.state.pressed
    dispatcher.post(PointerEvent(EventType.POINTER_UP, x=50, y=50))
    dispatcher.drain()
    assert not over.state.pressed


def test_pointer_capture_keeps_events_during_a_drag(dispatcher) -> None:
    """A drag that leaves the element must keep reaching it."""
    moves: list[float] = []
    over = dispatcher.root.find("over")
    over.handlers = {"on_pointer_move": lambda e: moves.append(e.x)}

    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=50, y=50))
    dispatcher.drain()
    dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=180, y=180))
    dispatcher.drain()
    assert moves == [180.0], "capture lost when the pointer left the element"


# ------------------------------------------------------------------ focus


def test_pressing_a_focusable_element_focuses_it(dispatcher) -> None:
    dispatcher.bind_handlers({"go": lambda e: None})
    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=50, y=50))
    dispatcher.drain()
    assert dispatcher.focused.name == "over"


def test_focus_moves_and_clears_state(dispatcher) -> None:
    dispatcher.bind_handlers({"go": lambda e: None})
    over = dispatcher.root.find("over")
    dispatcher.focus(over)
    assert over.state.focused
    dispatcher.focus(None)
    assert not over.state.focused
    assert dispatcher.focused is None


def test_focus_next_cycles(dispatcher) -> None:
    dispatcher.bind_handlers({"go": lambda e: None})
    order = dispatcher.focus_order()
    assert [e.name for e in order] == ["over"]
    assert dispatcher.focus_next().name == "over"
    assert dispatcher.focus_next().name == "over"


def test_keys_go_to_the_focused_element(dispatcher) -> None:
    keys: list[str] = []
    over = dispatcher.root.find("over")
    over.handlers = {"on_key_down": lambda e: keys.append(e.key)}
    dispatcher.focus(over)
    dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Enter"))
    dispatcher.drain()
    assert keys == ["Enter"]


def test_keys_with_no_focus_are_dropped(dispatcher) -> None:
    dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Enter"))
    assert dispatcher.drain() == 1  # handled without error


def test_unregistered_handler_is_reported(dispatcher) -> None:
    missing = dispatcher.bind_handlers({})
    assert any("go" in m for m in missing)
