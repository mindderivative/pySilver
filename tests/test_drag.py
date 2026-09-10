"""Drag gestures: the scrollbar thumb and the bottom sheet's handle.

Both affordances were drawn long before they responded to anything, which is
the failure these tests exist to prevent recurring: something that looks
draggable and is not.
"""

from __future__ import annotations

import pytest

from pysilver import App, Settings, Theme
from pysilver.layout import Offset
from pysilver.paint import DisplayList
from pysilver.runtime.events import EventType, PointerEvent
from pysilver.widgets.overlays import BottomSheetElement


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def send(app: App, kind: EventType, x: float, y: float) -> None:
    app.dispatcher.post(PointerEvent(kind, x=x, y=y))
    app.dispatcher.drain()
    app.paint(DisplayList())


# ------------------------------------------------------- scrollbar thumb


def scroll_app(rows: int = 20):
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [
                    {
                        "name": "sv",
                        "widget": "ScrollView",
                        "style": {"height": 200, "width": "expand"},
                        "children": [
                            {
                                "name": "col",
                                "widget": "Vertical",
                                "style": {"width": "expand"},
                                "children": [
                                    {
                                        "name": f"r{i}",
                                        "widget": "ListItem",
                                        "text": f"Row {i}",
                                        "style": {"width": "expand"},
                                    }
                                    for i in range(rows)
                                ],
                            }
                        ],
                    }
                ],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=300, height=240),
    )
    app.mount()
    app.paint(DisplayList())
    view = app.root.find("sv")
    return app, view, view.thumb_rect(Offset(0.0, 0.0))


def test_the_thumb_can_be_grabbed_where_it_is_drawn() -> None:
    """Painting and hit testing share one geometry, so a thumb you can see is
    a thumb you can grab."""
    _app, view, (x, y, w, h) = scroll_app()
    assert view.grabs_thumb(x + w / 2, y + h / 2)
    assert not view.grabs_thumb(20.0, 50.0), "the content area counted as the thumb"


def test_the_grab_area_is_wider_than_the_4dp_thumb() -> None:
    """A 4dp target is unusable with a mouse. This is pointer precision, not
    M3's finger-sized touch target."""
    _app, view, (x, y, _w, h) = scroll_app()
    assert view.grabs_thumb(x - 3.0, y + h / 2), "no slop either side of the thumb"


def test_dragging_the_thumb_scrolls_the_view() -> None:
    app, view, (x, y, _w, h) = scroll_app()
    assert view.scroll_offset == 0.0
    send(app, EventType.POINTER_DOWN, x + 1, y + h / 2)
    send(app, EventType.POINTER_MOVE, x + 1, y + h / 2 + 40)
    assert view.scroll_offset > 0.0


def test_the_scroll_view_claims_the_drag_from_the_content_beneath() -> None:
    """The thumb is drawn over the rows, so the press lands on a row. Without
    claiming capture the thumb would move for one frame and then stop."""
    app, view, (x, y, _w, h) = scroll_app()
    send(app, EventType.POINTER_DOWN, x + 1, y + h / 2)
    assert app.dispatcher._captured is view
    assert view.dragging


def test_thumb_travel_maps_to_scroll_travel() -> None:
    """Dragging the thumb the whole track scrolls the whole content."""
    app, view, (x, y, _w, h) = scroll_app()
    track, thumb, _along = view.thumb_geometry()
    send(app, EventType.POINTER_DOWN, x + 1, y + h / 2)
    send(app, EventType.POINTER_MOVE, x + 1, y + h / 2 + (track - thumb))
    assert view.scroll_offset == pytest.approx(view.max_scroll)


def test_releasing_ends_the_drag() -> None:
    app, view, (x, y, _w, h) = scroll_app()
    send(app, EventType.POINTER_DOWN, x + 1, y + h / 2)
    send(app, EventType.POINTER_UP, x + 1, y + h / 2)
    assert not view.dragging
    at_rest = view.scroll_offset
    send(app, EventType.POINTER_MOVE, x + 1, y + h / 2 + 80)
    assert view.scroll_offset == at_rest, "it kept scrolling after release"


def test_a_view_that_does_not_scroll_has_no_thumb_to_grab() -> None:
    _app, view, (x, y, _w, _h) = scroll_app(rows=2)
    assert not view.scrollable
    assert not view.grabs_thumb(x, y)


def test_dragging_scrolls_by_paint_not_layout() -> None:
    """The same guarantee wheel scrolling has; a drag must not relayout."""
    app, view, (x, y, _w, h) = scroll_app()
    send(app, EventType.POINTER_DOWN, x + 1, y + h / 2)
    calls: list[int] = []
    original = type(view).perform_layout
    type(view).perform_layout = lambda self, c: (calls.append(1), original(self, c))[1]
    try:
        send(app, EventType.POINTER_MOVE, x + 1, y + h / 2 + 40)
        assert calls == [], "dragging the thumb relaid out"
    finally:
        type(view).perform_layout = original


# ----------------------------------------------------- bottom sheet handle


def sheet_app(*, handle: bool = True):
    app = App(
        {
            "root": {"name": "root", "widget": "Vertical", "style": {"background": "surface"}},
            "overlays": [
                {
                    "name": "sh",
                    "widget": "BottomSheet",
                    "open": "true",
                    "style": {"handle": handle, "modal": True, "scrim": True},
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
    clock = Clock()
    app.clock = clock
    app.mount()
    app.paint(DisplayList())
    entry = app.overlays.entries[0]
    return app, entry, entry.origin.y, clock


def test_the_handle_has_a_48dp_grab_band() -> None:
    """M3: "an optional drag handle with an accessible 48dp hit target". The
    visual is 4dp tall, so without this there is nothing to aim at."""
    _app, entry, top, _clock = sheet_app()
    sheet = entry.element
    assert sheet.grabs_handle(200.0, top + 4.0)
    assert sheet.grabs_handle(200.0, top + BottomSheetElement.HANDLE_TARGET - 1)
    assert not sheet.grabs_handle(200.0, top + BottomSheetElement.HANDLE_TARGET + 20)


def test_a_sheet_without_a_handle_cannot_be_dragged() -> None:
    """Drawing the affordance is what promises the gesture."""
    _app, entry, top, _clock = sheet_app(handle=False)
    assert not entry.element.grabs_handle(200.0, top + 4.0)


def test_dragging_the_handle_moves_the_whole_sheet() -> None:
    app, entry, top, _clock = sheet_app()
    send(app, EventType.POINTER_DOWN, 200, top + 10)
    send(app, EventType.POINTER_MOVE, 200, top + 40)
    assert entry.origin.y == pytest.approx(top + 30)


def test_the_sheet_cannot_be_dragged_upwards() -> None:
    """It is docked to the bottom edge; lifting it would expose the square
    corners that edge exists to hide."""
    app, entry, top, _clock = sheet_app()
    send(app, EventType.POINTER_DOWN, 200, top + 10)
    send(app, EventType.POINTER_MOVE, 200, top - 60)
    assert entry.origin.y == pytest.approx(top)


def test_dragging_past_the_threshold_dismisses_it() -> None:
    app, entry, top, _clock = sheet_app()
    height = entry.element.size.height
    send(app, EventType.POINTER_DOWN, 200, top + 10)
    send(app, EventType.POINTER_MOVE, 200, top + 10 + height)
    send(app, EventType.POINTER_UP, 200, top + 10 + height)
    assert app.overlays.visible() == []


def test_releasing_short_of_the_threshold_settles_back() -> None:
    app, entry, top, clock = sheet_app()
    send(app, EventType.POINTER_DOWN, 200, top + 10)
    send(app, EventType.POINTER_MOVE, 200, top + 30)
    send(app, EventType.POINTER_UP, 200, top + 30)

    assert app.overlays.visible(), "a short drag dismissed it"
    assert entry.origin.y > top, "it jumped back instead of settling"
    frames = 0
    while app.motion.active and frames < 60:
        clock.t += 1 / 60
        app.paint(DisplayList())
        frames += 1
    assert entry.origin.y == pytest.approx(top), "it did not return to rest"
    assert not app.motion.active


def test_clicking_the_handle_closes_the_sheet() -> None:
    """M3 requires a single-pointer alternative: "selecting the drag handle
    should toggle through preset heights or close the sheet"."""
    app, _entry, top, _clock = sheet_app()
    send(app, EventType.POINTER_DOWN, 200, top + 10)
    send(app, EventType.POINTER_UP, 200, top + 10)
    assert app.overlays.visible() == []


def test_pressing_the_body_does_not_drag() -> None:
    app, entry, top, _clock = sheet_app()
    send(app, EventType.POINTER_DOWN, 200, top + 100)
    send(app, EventType.POINTER_MOVE, 200, top + 200)
    assert entry.origin.y == pytest.approx(top)


def test_a_widget_asks_to_close_rather_than_reaching_for_the_host() -> None:
    """Giving a widget the overlay host would let any element reach into the
    runtime; it raises a flag on its own state and the host reads it."""
    app, entry, _top, _clock = sheet_app()
    entry.element.state.data["dismiss_requested"] = True
    app.update()
    assert app.overlays.visible() == []
