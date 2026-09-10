"""The screen-reader bridge.

These cover the conversion from pySilver's semantic tree to AccessKit's, which
is the part checkable without a screen reader attached. What they cannot prove
is that a reader announces any of it -- that was verified by hand against the
live AT-SPI bus, and the result is recorded in the commit and in ARCHITECTURE
rather than pretended at here.

Skipped entirely when `accesskit` is absent: it is an optional extra, and a
missing native wheel is not a failing test.
"""

from __future__ import annotations

import pytest

from pysilver import App, Theme
from pysilver.runtime.accesskit_bridge import available

pytestmark = pytest.mark.skipif(
    available() is not None, reason=f"accesskit unavailable: {available()}"
)

VIEW = {
    "root": {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "go",
                "widget": "Button",
                "text": "Confirm",
                "style": {"width": 130, "height": 40},
                "handlers": {"on_click": "hit"},
            },
            {"name": "agree", "widget": "Checkbox", "value": "true"},
            {"name": "off", "widget": "Button", "text": "Nope", "disabled": "true"},
            {"name": "bar", "widget": "LinearProgress", "value": "0.5"},
        ],
    }
}


def make_app(view: dict = VIEW):
    calls: list[str] = []
    app = App(view, theme=Theme(dark=True))

    def hit(event: object) -> None:
        calls.append("clicked")

    app.handler(hit)
    app.mount()
    app.update()
    return app, calls


@pytest.fixture
def bridge():
    """One adapter, closed afterwards.

    Closing is not tidiness: AccessKit's D-Bus thread calls back into Python
    and panics if it outlives the interpreter, so a test that leaks one takes
    the whole run down at exit. That is how this was found.
    """
    from pysilver.runtime.accesskit_bridge import AccessKitBridge

    with AccessKitBridge(window_title="Test window", toolkit_version="test") as made:
        yield made


def built(app: App, bridge):
    """The TreeUpdate the bridge would push, without needing a reader."""
    app.bind_accessibility(bridge)
    return bridge, bridge._latest


def labelled(update, label: str):
    return next(node for _, node in update.nodes if node.label == label)


# -------------------------------------------------------------- conversion


def test_the_tree_converts_with_a_titled_window_root(bridge) -> None:
    """AccessKit expects the root to be a WINDOW carrying the title. Handing it
    our own root -- a Vertical, which converts to GROUP -- left AT-SPI with
    nothing better to call the application than the process name. Found by
    asking the registry, not by reading the docs.
    """
    import accesskit as ak

    app, _ = make_app()
    _, update = built(app, bridge)
    root = dict(update.nodes)[update.tree.root]
    assert root.role == ak.Role.WINDOW
    assert root.label == "Test window"
    assert len(root.children) == 1, "the whole interface hangs under the window"


def test_roles_map_onto_accesskits_vocabulary(bridge) -> None:
    import accesskit as ak

    app, _ = make_app()
    _, update = built(app, bridge)
    roles = [node.role for _, node in update.nodes]
    assert labelled(update, "Confirm").role == ak.Role.BUTTON
    assert ak.Role.CHECK_BOX in roles
    assert ak.Role.PROGRESS_INDICATOR in roles


def test_state_survives_the_conversion(bridge) -> None:
    import accesskit as ak

    app, _ = make_app()
    _, update = built(app, bridge)
    checkbox = next(n for _, n in update.nodes if n.role == ak.Role.CHECK_BOX)
    assert checkbox.toggled == ak.Toggled.TRUE
    assert labelled(update, "Nope").is_disabled is True


def test_bounds_are_converted_from_origin_size_to_corners(bridge) -> None:
    """pySilver's Rect is x/y/width/height; AccessKit's is x0/y0/x1/y1. Passing
    one for the other would misplace every control, and silently -- all the
    numbers stay plausible."""
    app, _ = make_app()
    _, update = built(app, bridge)
    button = labelled(update, "Confirm")
    assert button.bounds.x1 > button.bounds.x0
    assert button.bounds.y1 > button.bounds.y0
    expected = app.accessibility_tree().find(name="Confirm").bounds
    assert button.bounds.x1 - button.bounds.x0 == pytest.approx(expected.width)


def test_anything_clickable_advertises_the_click_action(bridge) -> None:
    """A tree describing controls nobody can operate is not access."""
    app, _ = make_app()
    _, update = built(app, bridge)
    import accesskit as ak

    assert labelled(update, "Confirm").supports_action(ak.Action.CLICK), (
        "a reader could not activate it"
    )


# ------------------------------------------------------------------ actions


class Request:
    """Stands in for an AccessKit ActionRequest, which is a native type."""

    def __init__(self, target: int) -> None:
        self.target = target


def test_requests_are_queued_rather_than_applied_where_they_arrive(bridge) -> None:
    """AccessKit delivers from its own D-Bus task and pySilver's signals are
    thread affine, so acting on a request inside the callback would raise
    ThreadAffinityError. They queue; the engine thread drains them."""
    app, calls = make_app()
    _, update = built(app, bridge)

    target = next(i for i, node in update.nodes if node.label == "Confirm")
    bridge._requests.append(Request(target))
    assert calls == [], "nothing should have run in the callback"
    app.update()
    assert calls == ["clicked"], "the engine thread drained it"


def test_a_request_for_a_vanished_node_is_ignored(bridge) -> None:
    """Ids are stable within an update and deliberately not across them, so a
    request can name something that is no longer there."""
    app, calls = make_app()
    built(app, bridge)
    bridge._requests.append(Request(9999))
    app.update()
    assert calls == []


def test_draining_takes_each_request_once(bridge) -> None:
    app, _ = make_app()
    built(app, bridge)
    bridge._requests.append(Request(0))
    assert len(bridge.drain()) == 1
    assert bridge.drain() == []


# ------------------------------------------------------------------- limits


def test_available_explains_itself_rather_than_returning_a_bool() -> None:
    """ "Not available" with no reason is the least useful thing an
    accessibility feature can say."""
    reason = available()
    assert reason is None or (isinstance(reason, str) and len(reason) > 20)


def test_a_closed_bridge_stops_pushing(bridge) -> None:
    """It must go quiet rather than raise: the App pushes every frame, and a
    close during teardown should not turn into an exception on the way out."""
    app, _ = make_app()
    app.bind_accessibility(bridge)
    bridge.close()
    assert bridge.closed
    bridge.update(app.accessibility_tree())
    bridge.close()
