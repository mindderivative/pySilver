"""NodeGraph + Node: a pannable surface of draggable, wired nodes.

M3 has no node-graph component -- checked directly, not assumed absent, the
same way every other ungrounded widget this session was.
"""

from __future__ import annotations

import pytest

from pysilver import App, Theme
from pysilver.layout import Constraints, Offset, Size
from pysilver.paint import DisplayList, Kind
from pysilver.runtime.events import FOCUSABLE_KINDS, EventType, KeyEvent, PointerEvent
from pysilver.spec import WidgetKind, parse_view
from pysilver.spec.models import EdgeSpec
from pysilver.tree.reconcile import reconcile
from pysilver.widgets import build_element
from pysilver.widgets.base import _REGISTRY
from pysilver.widgets.nodegraph import NodeElement

LOOSE = Constraints.loose(Size(1000.0, 800.0))


def laid_out(spec: dict, constraints: Constraints = LOOSE):
    element = build_element(parse_view(spec).root)
    element.layout(constraints)
    return element


def node(name: str, x: float, y: float, **kw) -> dict:
    return {"name": name, "widget": "Node", "text": name, "style": {"x": x, "y": y}, **kw}


def graph(*children: dict, edges: list | None = None, style: dict | None = None) -> dict:
    spec: dict = {"name": "g", "widget": "NodeGraph", "children": list(children)}
    if edges is not None:
        spec["edges"] = edges
    if style is not None:
        spec["style"] = style
    return spec


def app(view: dict) -> App:
    a = App({"name": "root", "widget": "Vertical", "children": [view]}, theme=Theme(dark=True))
    a.mount()
    a.update()
    return a


# --------------------------------------------------------------- registered


@pytest.mark.parametrize("kind", ["NodeGraph", "Node"])
def test_kind_builds(kind: str) -> None:
    assert laid_out({"name": "w", "widget": kind}) is not None


def test_every_kind_is_registered() -> None:
    assert set(_REGISTRY) == set(WidgetKind)


# -------------------------------------------------------------------- spec


def test_edge_spec_holds_source_and_target() -> None:
    e = EdgeSpec(source="a.out", target="b.in")
    assert e.source == "a.out"
    assert e.target == "b.in"


def test_inputs_and_outputs_parse_like_classes() -> None:
    e = laid_out(node("n", 0.0, 0.0, inputs="a b", outputs="c"))
    assert e.spec.inputs == ("a", "b")
    assert e.spec.outputs == ("c",)


# --------------------------------------------------------------- Node sizing


def test_node_without_a_child_gets_a_default_size() -> None:
    """The same trap `CanvasElement.DEFAULT_SIZE` exists to avoid: a widget
    with no intrinsic content of its own that lays out 0x0 in unbounded
    space draws nothing, silently."""
    e = laid_out(node("n", 0.0, 0.0), constraints=Constraints.unbounded())
    assert e.size == Size(NodeElement.DEFAULT_WIDTH, NodeElement.DEFAULT_HEIGHT)


def test_node_grows_to_fit_its_child_below_the_title() -> None:
    e = laid_out(
        node(
            "n",
            0.0,
            0.0,
            children=[{"widget": "Container", "style": {"width": 100, "height": 60}}],
        ),
        constraints=Constraints.unbounded(),
    )
    assert e.size == Size(NodeElement.DEFAULT_WIDTH, NodeElement.TITLE_HEIGHT + 60.0)


# ----------------------------------------------------------- Node position


def test_node_position_starts_at_style_x_y() -> None:
    e = laid_out(graph(node("a", 40.0, 20.0)))
    a_node = e.find("a")
    assert a_node.position == Offset(40.0, 20.0)
    assert a_node.offset == Offset(40.0, 20.0)


def test_dragging_the_title_bar_moves_the_node() -> None:
    a = app(graph(node("a", 0.0, 0.0)))
    n = a.root.find("a")
    rect = n.absolute_rect()
    a.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=rect.x + 10, y=rect.y + 10))
    a.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=rect.x + 60, y=rect.y + 40))
    a.dispatcher.drain()
    assert n.position == Offset(50.0, 30.0)


def test_dragging_the_content_area_does_not_move_the_node() -> None:
    a = app(
        graph(
            node(
                "a",
                0.0,
                0.0,
                children=[{"widget": "Container", "style": {"width": 100, "height": 60}}],
            )
        )
    )
    n = a.root.find("a")
    rect = n.absolute_rect()
    below_title = rect.y + NodeElement.TITLE_HEIGHT + 5
    a.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=rect.x + 10, y=below_title))
    a.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=rect.x + 60, y=below_title + 20))
    a.dispatcher.drain()
    assert n.position == Offset(0.0, 0.0)


def test_on_change_carries_the_new_position_once_the_drag_ends() -> None:
    calls: list[str] = []
    view = graph({**node("a", 0.0, 0.0), "handlers": {"on_change": "moved"}})
    a = App({"name": "root", "widget": "Vertical", "children": [view]}, theme=Theme(dark=True))
    a._handlers["moved"] = lambda e: calls.append(e.value)
    a.mount()
    a.update()
    n = a.root.find("a")
    rect = n.absolute_rect()
    a.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=rect.x + 10, y=rect.y + 10))
    a.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=rect.x + 30, y=rect.y + 10))
    a.dispatcher.drain()
    assert calls == [], "on_change must not fire mid-drag"
    a.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=rect.x + 30, y=rect.y + 10))
    a.dispatcher.drain()
    assert calls == ["20.0,0.0"]


def test_arrow_keys_nudge_the_node_and_fire_on_change() -> None:
    calls: list[str] = []
    view = graph({**node("a", 40.0, 40.0), "handlers": {"on_change": "moved"}})
    a = App({"name": "root", "widget": "Vertical", "children": [view]}, theme=Theme(dark=True))
    a._handlers["moved"] = lambda e: calls.append(e.value)
    a.mount()
    a.update()
    n = a.root.find("a")
    a.dispatcher.focus(n)
    a.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Right"))
    a.dispatcher.drain()
    assert n.position == Offset(40.0 + NodeElement.STEP, 40.0)
    assert calls[-1] == f"{40.0 + NodeElement.STEP:.1f},40.0"


def test_reload_does_not_reset_a_dragged_node() -> None:
    root = laid_out(graph(node("a", 0.0, 0.0)))
    root.find("a")._set_position(Offset(99.0, 5.0))
    new_spec = parse_view(graph(node("a", 0.0, 0.0))).root
    result, _ = reconcile(root, new_spec, build_element)
    assert result.find("a").position == Offset(99.0, 5.0)


# ------------------------------------------------------------------- pan


def test_panning_translates_without_relayout() -> None:
    """The central claim of the design, same as `ScrollView`'s own: panning
    is a paint-time translation, not a relayout."""
    a = app(graph(node("a", 40.0, 40.0), style={"width": 400, "height": 300}))
    g = a.root.find("g")
    n = a.root.find("a")
    rect = g.absolute_rect()
    empty_x, empty_y = rect.x + 350, rect.y + 250  # away from the node
    calls: list[int] = []
    original = type(g).perform_layout
    type(g).perform_layout = lambda self, c: (calls.append(1), original(self, c))[1]
    try:
        a.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=empty_x, y=empty_y))
        a.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=empty_x - 30, y=empty_y - 10))
        a.dispatcher.drain()
        assert calls == [], "panning triggered a layout pass"
    finally:
        type(g).perform_layout = original
    assert g.state.scroll == Offset(30.0, 10.0)
    assert n.offset == Offset(40.0, 40.0)  # the node's own world position is unmoved


def test_clicking_a_node_does_not_pan_the_background() -> None:
    a = app(graph(node("a", 40.0, 40.0), style={"width": 400, "height": 300}))
    g = a.root.find("g")
    n = a.root.find("a")
    rect = n.absolute_rect()
    a.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=rect.x + 10, y=rect.y + 10))
    a.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=rect.x + 40, y=rect.y + 10))
    a.dispatcher.drain()
    assert g.state.scroll == Offset(0.0, 0.0)


# ------------------------------------------------------------------ edges


def test_an_edge_is_drawn_as_a_segment_between_named_ports() -> None:
    a = app(
        graph(
            node("src", 0.0, 0.0, outputs="out"),
            node("dst", 200.0, 0.0, inputs="in"),
            edges=[{"source": "src.out", "target": "dst.in"}],
        )
    )
    dl = DisplayList()
    a.paint(dl)
    kinds = {int(s["flags"][0]) for s in dl.view}
    assert Kind.SEGMENT in kinds


def test_an_edge_naming_an_unknown_node_is_skipped_not_an_error() -> None:
    a = app(
        graph(
            node("src", 0.0, 0.0, outputs="out"),
            edges=[{"source": "src.out", "target": "missing.in"}],
        )
    )
    dl = DisplayList()
    a.paint(dl)  # must not raise


# ---------------------------------------------------------------- focus


def test_node_is_focusable() -> None:
    assert "Node" in FOCUSABLE_KINDS
