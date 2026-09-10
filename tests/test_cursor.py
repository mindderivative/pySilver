"""Cursor shapes.

The backend destroys and recreates a native cursor object on every
`set_cursor` call, so the load-bearing test here is that the App only pushes a
shape when it changes.
"""

from __future__ import annotations

import pytest

from pysilver import App, Settings, Theme
from pysilver.layout import Offset
from pysilver.paint import DisplayList
from pysilver.runtime.events import EventType, PointerEvent
from pysilver.spec import SpecError, parse_view


def hosted(children, size=(300, 340)):
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": children,
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=size[0], height=size[1]),
    )
    app.mount()
    app.paint(DisplayList())
    return app


def cursor_at(app: App, x: float, y: float) -> str:
    app.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=x, y=y))
    app.dispatcher.drain()
    return app.dispatcher.cursor


BUTTON = {"name": "b", "widget": "Button", "text": "Go", "style": {"width": 120, "height": 40}}


# ------------------------------------------------------------ resolution


def test_nothing_in_particular_gets_the_default() -> None:
    app = hosted([{"name": "t", "widget": "Text", "text": "hello", "style": {"height": 30}}])
    assert cursor_at(app, 40, 10) == "default"


def test_something_clickable_gets_the_hand() -> None:
    app = hosted([BUTTON])
    assert cursor_at(app, 50, 20) == "pointer"


@pytest.mark.parametrize("kind", ["Button", "Checkbox", "Radio", "Switch", "Chip", "MenuItem"])
def test_every_interactive_widget_asks_for_the_hand(kind: str) -> None:
    element = __import__("pysilver.widgets", fromlist=["build_element"]).build_element(
        parse_view({"name": "w", "widget": kind}).root
    )
    assert element.cursor_at(0.0, 0.0) == "pointer"


def test_a_disabled_control_says_not_allowed() -> None:
    """It is removed from the *event* path, correctly -- but the cursor is
    feedback, not an event, so it resolves from the unfiltered path."""
    app = hosted([{**BUTTON, "disabled": "true"}])
    assert cursor_at(app, 50, 20) == "not-allowed"


def test_a_disabled_container_reaches_its_children() -> None:
    app = hosted(
        [
            {
                "name": "section",
                "widget": "Vertical",
                "disabled": "true",
                "children": [BUTTON],
            }
        ]
    )
    assert cursor_at(app, 50, 20) == "not-allowed"


def test_a_view_can_override_the_shape() -> None:
    app = hosted([{**BUTTON, "style": {**BUTTON["style"], "cursor": "crosshair"}}])
    assert cursor_at(app, 50, 20) == "crosshair"


def test_the_topmost_opinion_wins() -> None:
    """A button inside a container gets the button's shape, and the container
    keeps its own where the button does not reach.

    The padding matters: a `Container` passes tight constraints, so without it
    the child fills the whole box and there is no container left to hover.
    """
    app = hosted(
        [
            {
                "name": "card",
                "widget": "Container",
                "style": {"width": 200, "height": 80, "padding": 30, "cursor": "crosshair"},
                "children": [BUTTON],
            }
        ]
    )
    assert cursor_at(app, 100, 40) == "pointer", "the button lost its shape"
    assert cursor_at(app, 10, 10) == "crosshair", "the container lost its own shape"


def test_an_unknown_shape_fails_at_load() -> None:
    """Rather than raising from inside a frame, where the backend would."""
    with pytest.raises(SpecError):
        parse_view({"name": "b", "widget": "Button", "style": {"cursor": "wiggle"}})


# ------------------------------------------------------- drag affordances


def scroll_app():
    rows = [
        {"name": f"r{i}", "widget": "ListItem", "text": f"Row {i}", "style": {"width": "expand"}}
        for i in range(20)
    ]
    app = hosted(
        [
            {
                "name": "sv",
                "widget": "ScrollView",
                "style": {"height": 200, "width": "expand"},
                "children": [
                    {
                        "name": "col",
                        "widget": "Vertical",
                        "style": {"width": "expand"},
                        "children": rows,
                    }
                ],
            }
        ]
    )
    view = app.root.find("sv")
    rect = view.absolute_rect()
    return app, view, view.thumb_rect(Offset(rect.x, rect.y))


def test_the_scrollbar_thumb_asks_for_a_resize_cursor() -> None:
    app, _view, (x, y, _w, h) = scroll_app()
    assert cursor_at(app, x + 1, y + h / 2) == "ns-resize"


def test_the_content_beside_it_does_not() -> None:
    """Claiming a resize cursor over the whole viewport would be wrong: the
    content is what the pointer is usually over."""
    app, _view, _rect = scroll_app()
    assert cursor_at(app, 40, 100) == "default"


def test_a_horizontal_view_asks_for_the_other_axis() -> None:
    app = hosted(
        [
            {
                "name": "sv",
                "widget": "ScrollView",
                "style": {"height": 80, "width": 200, "axis": "horizontal"},
                "children": [
                    {
                        "name": "row",
                        "widget": "Horizontal",
                        "children": [
                            {
                                "name": f"c{i}",
                                "widget": "Container",
                                "style": {"width": 80, "height": 40},
                            }
                            for i in range(6)
                        ],
                    }
                ],
            }
        ]
    )
    view = app.root.find("sv")
    rect = view.absolute_rect()
    x, y, w, _h = view.thumb_rect(Offset(rect.x, rect.y))
    assert cursor_at(app, x + w / 2, y + 1) == "ew-resize"


def dock_split_app(*, axis: str | None = None):
    style = {"width": 300, "height": 200}
    if axis is not None:
        style["axis"] = axis
    app = hosted(
        [
            {
                "name": "ds",
                "widget": "DockSplit",
                "style": style,
                "children": [
                    {"name": "a", "widget": "Container", "style": {"background": "surface"}},
                    {"name": "b", "widget": "Container", "style": {"background": "surface"}},
                ],
            }
        ]
    )
    view = app.root.find("ds")
    rect = view.absolute_rect()
    return app, view, rect


def test_a_dock_split_divider_asks_for_a_resize_cursor() -> None:
    """Not "col-resize"/"row-resize" -- those are CSS names this backend's
    own `CursorShape` does not recognise, which used to raise `ValueError`
    from inside `App._sync_cursor()` and silently break cursor updates
    entirely rather than just showing the wrong shape."""
    app, view, rect = dock_split_app()
    x = rect.x + view._divider_main + view.DIVIDER / 2
    y = rect.y + rect.height / 2
    assert cursor_at(app, x, y) == "ew-resize"


def test_a_vertical_dock_split_asks_for_the_other_axis() -> None:
    app, view, rect = dock_split_app(axis="vertical")
    x = rect.x + rect.width / 2
    y = rect.y + view._divider_main + view.DIVIDER / 2
    assert cursor_at(app, x, y) == "ns-resize"


def test_the_panes_beside_a_dock_split_divider_do_not_claim_the_cursor() -> None:
    app, _view, rect = dock_split_app()
    assert cursor_at(app, rect.x + 10, rect.y + rect.height / 2) == "default"


def test_a_node_title_bar_asks_for_a_cursor_without_crashing() -> None:
    """Not "move" -- this backend's `CursorShape` has no move/grab cursor,
    and returning it used to raise `ValueError` from inside
    `App._sync_cursor()` on literally the first frame the pointer sat over
    a node's title bar, the same bug class `DockSplit`'s divider had."""
    app = hosted(
        [
            {
                "name": "graph",
                "widget": "NodeGraph",
                "style": {"width": 400, "height": 300},
                "children": [
                    {"name": "n", "widget": "Node", "text": "N", "style": {"x": 20, "y": 20}},
                ],
            }
        ]
    )
    node = app.root.find("n")
    rect = node.absolute_rect()
    assert cursor_at(app, rect.x + 10, rect.y + 10) == "pointer"


def test_a_sheet_handle_asks_for_a_resize_cursor() -> None:
    app = App(
        {
            "root": {"name": "root", "widget": "Vertical", "style": {"background": "surface"}},
            "overlays": [
                {
                    "name": "sh",
                    "widget": "BottomSheet",
                    "open": "true",
                    "style": {"handle": True, "modal": True},
                    "children": [
                        {
                            "name": "c",
                            "widget": "Container",
                            "style": {"height": 120, "width": "expand"},
                        }
                    ],
                }
            ],
        },
        theme=Theme(dark=True),
        settings=Settings(width=400, height=400),
    )
    app.mount()
    app.paint(DisplayList())
    top = app.overlays.entries[0].origin.y
    assert cursor_at(app, 200, top + 10) == "ns-resize"
    assert cursor_at(app, 200, top + 120) != "ns-resize", "the whole sheet claimed it"


# ---------------------------------------------------------------- applying


def test_the_shape_is_pushed_only_when_it_changes() -> None:
    """The backend destroys and recreates a native cursor on every call, so
    setting it per frame would churn GLFW resources sixty times a second."""
    app = hosted([BUTTON])
    pushed: list[str] = []

    class FakeCanvas:
        def set_cursor(self, shape: str) -> None:
            pushed.append(shape)

        def get_logical_size(self) -> tuple[int, int]:
            return (300, 340)

    class FakeEngine:
        canvas = FakeCanvas()
        pixel_ratio = 1.0

    app.engine = FakeEngine()

    cursor_at(app, 50, 20)  # onto the button
    app.update()
    app.update()
    app.update()  # three frames, unchanged
    assert pushed == ["pointer"], f"pushed {len(pushed)} times for one change"

    cursor_at(app, 280, 330)  # off it again
    app.update()
    assert pushed == ["pointer", "default"]


def test_a_rejected_shape_is_retried_next_frame_rather_than_stuck() -> None:
    """`self._cursor` must record success, not intent: DockSplit once
    returned a name the backend rejected, and because the tracker was
    updated before the (failing) call, the next frame's "unchanged, skip
    it" guard saw no change and never tried again -- a single failure that
    silently broke cursor updates forever, not per-frame."""
    app = hosted([BUTTON])

    class RejectingCanvas:
        def set_cursor(self, shape: str) -> None:
            raise ValueError(f"backend does not know {shape!r}")

        def get_logical_size(self) -> tuple[int, int]:
            return (300, 340)

    class FakeEngine:
        canvas = RejectingCanvas()
        pixel_ratio = 1.0

    app.engine = FakeEngine()
    cursor_at(app, 50, 20)  # onto the button, cursor should become "pointer"

    with pytest.raises(ValueError):
        app.update()
    assert app._cursor != "pointer", "recorded as applied despite the backend rejecting it"

    with pytest.raises(ValueError):
        app.update()  # still retried, not silently skipped as "unchanged"
