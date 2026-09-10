"""DockSplit, DockGroup, DockPanel: a resizable, tabbed panel layout.

No M3 grounding exists for any of the three -- checked directly, not
assumed absent, the same way every other ungrounded widget this session was.
"""

from __future__ import annotations

import pytest

from pysilver import App, Signal, Theme
from pysilver.layout import Constraints, Size
from pysilver.paint import DisplayList
from pysilver.runtime.events import EventType, KeyEvent, PointerEvent
from pysilver.spec import WidgetKind, parse_view
from pysilver.theme import Palette
from pysilver.widgets import build_element

PAL = Palette(Theme(dark=True))
LOOSE = Constraints.loose(Size(1000.0, 800.0))


def laid_out(spec: dict, constraints: Constraints = LOOSE):
    element = build_element(parse_view(spec).root)
    element.layout(constraints)
    return element


def app(view: dict, **signals) -> App:
    a = App(view, theme=Theme(dark=True))
    a.expose(**signals)
    a.mount()
    a.update()
    return a


def paint(a: App) -> DisplayList:
    dl = DisplayList()
    a.paint(dl)
    return dl


def click(a: App, x: float, y: float) -> None:
    a.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=x, y=y))
    a.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=x, y=y))
    a.dispatcher.drain()


def panel(name: str, text: str) -> dict:
    return {
        "name": name,
        "widget": "DockPanel",
        "text": text,
        "children": [{"widget": "Text", "text": text}],
    }


# --------------------------------------------------------------- registered


@pytest.mark.parametrize("kind", ["DockSplit", "DockGroup", "DockPanel"])
def test_kind_builds(kind: str) -> None:
    assert laid_out({"name": "w", "widget": kind}) is not None


def test_every_kind_is_registered() -> None:
    from pysilver.widgets.base import _REGISTRY, create_element

    create_element(parse_view({"name": "x", "widget": "DockSplit"}).root)
    assert set(_REGISTRY) == set(WidgetKind)


# -------------------------------------------------------------- DockPanel


def test_a_panel_sizes_to_its_content() -> None:
    e = laid_out(
        {
            "name": "w",
            "widget": "DockPanel",
            "children": [{"widget": "Container", "style": {"width": 200, "height": 100}}],
        }
    )
    assert e.size == Size(200, 100)


def test_an_empty_panel_is_a_box_around_nothing() -> None:
    assert laid_out({"name": "w", "widget": "DockPanel"}).size == Size(0, 0)


# -------------------------------------------------------------- DockGroup


def _group(*, value: str | None = None, handlers: dict | None = None) -> dict:
    spec: dict = {
        "name": "g",
        "widget": "DockGroup",
        "children": [panel("a", "Files"), panel("b", "Search")],
    }
    if value is not None:
        spec["value"] = value
    if handlers is not None:
        spec["handlers"] = handlers
    return spec


def test_group_defaults_to_the_first_panel() -> None:
    e = laid_out(_group())
    assert e._active_name() == "a"


def test_an_explicit_value_selects_that_panel() -> None:
    e = laid_out(_group(value="b"))
    assert e._active_name() == "b"


def test_an_unmatched_value_falls_back_to_the_first_panel() -> None:
    e = laid_out(_group(value="nope"))
    assert e._active_name() == "a"


def test_only_the_active_panel_gets_real_size() -> None:
    e = laid_out(_group(value="a"), Constraints.tight(Size(400.0, 300.0)))
    a_panel = e.find("a")
    b_panel = e.find("b")
    assert a_panel.size.height > 0.0
    assert b_panel.size == Size(0.0, 0.0)


def test_the_active_panel_is_marked_selected() -> None:
    e = laid_out(_group(value="b"), Constraints.tight(Size(400.0, 300.0)))
    assert e.find("b").selected
    assert not e.find("a").selected


def test_clicking_a_tab_switches_the_active_panel() -> None:
    view = {"name": "root", "widget": "Vertical", "children": [_group(value="a")]}
    a = app(view)
    g = a.root.find("g")
    _, x, w = g._tab_rects()[1]
    rect = g.absolute_rect()
    click(a, rect.x + x + w / 2, rect.y + 20)
    assert g._active_name() == "b"


def test_on_change_carries_the_new_panel_name() -> None:
    calls = []
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [_group(value="a", handlers={"on_change": "switch"})],
    }
    a = App(view, theme=Theme(dark=True))
    a._handlers["switch"] = lambda e: calls.append(e.value)
    a.mount()
    a.update()
    g = a.root.find("g")
    _, x, w = g._tab_rects()[1]
    rect = g.absolute_rect()
    click(a, rect.x + x + w / 2, rect.y + 20)
    assert calls == ["b"]


def test_value_is_bindable_to_a_signal() -> None:
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [_group(value="{{ tab.get() }}")],
    }
    tab = Signal("a")
    a = app(view, tab=tab)
    assert a.root.find("g")._active_name() == "a"
    tab.set("b")
    a.update()
    assert a.root.find("g")._active_name() == "b"


def test_selected_tab_uses_primary() -> None:
    view = {"name": "root", "widget": "Vertical", "children": [_group(value="a")]}
    a = app(view)
    tokens = {int(s["flags"][2]) for s in paint(a).view}
    assert PAL.index("primary") in tokens


def test_the_selected_tabs_indicator_is_inset_and_rounded() -> None:
    """COMPONENT_TABS.md: primary indicators are inset 2dp a side with a
    fully rounded corner radius -- this widget's own hand-rolled strip
    (it does not literally reuse `TabsElement`, despite the docstring's
    "reuses Tabs' own anatomy") needed the identical fix `TabsElement`'s
    indicator did: full tab width, square corners."""
    view = {"name": "root", "widget": "Vertical", "children": [_group(value="a")]}
    a = app(view)
    group = a.root.find("g")
    _name, tab_x, tab_w = next(r for r in group._tab_rects() if r[0] == "a")
    root_rect = group.absolute_rect()

    bars = [
        s
        for s in paint(a).view
        if abs(float(s["rect"][3]) - group.INDICATOR_H) < 0.01
        and int(s["flags"][2]) == PAL.index("primary")
    ]
    assert len(bars) == 1
    bar = bars[0]
    assert float(bar["rect"][0]) == pytest.approx(root_rect.x + tab_x + group.PRIMARY_INSET)
    assert float(bar["rect"][2]) == pytest.approx(tab_w - 2.0 * group.PRIMARY_INSET)


def test_the_selected_tabs_indicator_slides_to_the_new_tab_not_jumps() -> None:
    """phil: "the tab strips animation on selection change no longer
    animates the bar under the tab title." It never had -- the indicator
    used to be drawn instantly, per-tab, inside the tab-paint loop, with no
    `animated()` call anywhere in this class's history (only per-tab hover
    alpha was ever animated). Rebuilt on `TabsElement.paint_self`'s own
    established pattern instead: one shared "indicator_x"/"indicator_w"
    animated() pair, computed once for whichever tab is active, so it
    travels between tabs -- tested with the same two-step `app.motion.tick`
    drive every other animated() binding in this codebase is tested with
    (e.g. `test_navigation.py::test_expand_state_is_bindable`)."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [_group(value="{{ tab.get() }}")],
    }
    tab = Signal("a")
    a = app(view, tab=tab)
    group = a.root.find("g")

    def bar_x() -> float:
        bar = next(
            s
            for s in paint(a).view
            if abs(float(s["rect"][3]) - group.INDICATOR_H) < 0.01
            and int(s["flags"][2]) == PAL.index("primary")
        )
        return float(bar["rect"][0])

    x_on_a = bar_x()
    tab.set("b")
    a.update()
    # Retargets but does not jump on the very next frame -- no motion time
    # has elapsed yet for it to have travelled anywhere.
    assert bar_x() == pytest.approx(x_on_a)

    # A single huge tick is clamped to MAX_FRAME_DELTA by design
    # (`motion/animation.py`) -- several small ticks, the same pattern
    # `test_motion.py` uses, actually exhaust the transition.
    for _ in range(20):
        a.motion.tick(0.1)
    a.update()
    group2 = a.root.find("g")
    _name, tab_b_x, _tab_b_w = next(r for r in group2._tab_rects() if r[0] == "b")
    expected = group2.absolute_rect().x + tab_b_x + group2.PRIMARY_INSET
    assert bar_x() == pytest.approx(expected)
    assert bar_x() != pytest.approx(x_on_a)


def test_the_drop_zone_highlight_paints_over_the_active_panels_content() -> None:
    """Found live: painted from `paint_self` (the rest of this class's own
    chrome), the highlight sat BEHIND the active `DockPanel`'s own content --
    a child always paints after its parent's `paint_self`, so an ordinary
    opaque, full-rect panel background (`width: expand, height: expand`)
    covered it almost entirely. phil saw this as the left/right/bottom lines
    being "cutoff a little by the edges" -- only the thin seam right at the
    tab strip, painted before the panel's own content began, ever showed.
    Moved to `paint_foreground`, the same hook `ScrollView`'s own thumb uses
    to stay visible over scrolled content -- this asserts draw order (index
    order IS draw order, `paint/display_list.py`), not just that the
    highlight was emitted at all."""
    view = {
        "name": "root",
        "widget": "DockGroup",
        "children": [
            {
                "name": "a",
                "widget": "DockPanel",
                "text": "A",
                "children": [
                    {
                        "widget": "Container",
                        "style": {
                            "width": "expand",
                            "height": "expand",
                            "background": "surface_container_low",
                        },
                    }
                ],
            }
        ],
    }
    from pysilver.widgets.dock_drag import LINE_THICKNESS

    a = app(view)
    group = a.root
    group.state.data["drag_highlight"] = "left"
    group.mark_needs_paint()
    data = paint(a).view

    content_idx = next(
        i for i, s in enumerate(data) if int(s["flags"][2]) == PAL.index("surface_container_low")
    )
    highlight_idx = next(
        i
        for i, s in enumerate(data)
        if int(s["flags"][2]) == PAL.index("primary")
        and float(s["rect"][2]) == pytest.approx(LINE_THICKNESS)
    )
    assert highlight_idx > content_idx, "index order is draw order -- the highlight must paint last"


# -------------------------------------------------------------- DockSplit


def _split(*, value: str | None = None, axis: str | None = None) -> dict:
    style = {}
    if axis is not None:
        style["axis"] = axis
    spec: dict = {
        "name": "s",
        "widget": "DockSplit",
        "style": style,
        "children": [
            {"name": "left", "widget": "DockPanel", "children": [{"widget": "Text", "text": "L"}]},
            {"name": "right", "widget": "DockPanel", "children": [{"widget": "Text", "text": "R"}]},
        ],
    }
    if value is not None:
        spec["value"] = value
    return spec


def test_defaults_to_an_even_split() -> None:
    e = laid_out(_split(), Constraints.tight(Size(1000.0, 500.0)))
    left = e.find("left")
    right = e.find("right")
    assert left.size.width == pytest.approx(right.size.width, abs=1.0)


def test_a_ratio_divides_unevenly() -> None:
    e = laid_out(_split(value="0.25"), Constraints.tight(Size(1000.0, 500.0)))
    left = e.find("left")
    right = e.find("right")
    assert left.size.width < right.size.width
    assert left.size.width == pytest.approx(1000.0 * 0.25 - 2.0, abs=2.0)


def test_defaults_to_horizontal_not_the_shared_field_default() -> None:
    """`axis` defaults to `vertical` for ScrollView; DockSplit must not
    silently inherit that -- side by side is the ordinary reading of
    "split", and this is what a wrong-but-valid layout looks like."""
    e = laid_out(_split(), Constraints.tight(Size(1000.0, 500.0)))
    left = e.find("left")
    assert left.size.height == 500.0
    assert left.size.width < 1000.0


def test_explicit_vertical_axis_stacks_instead() -> None:
    e = laid_out(_split(axis="vertical"), Constraints.tight(Size(1000.0, 500.0)))
    left = e.find("left")
    assert left.size.width == 1000.0
    assert left.size.height < 500.0


def test_a_third_child_is_rejected() -> None:
    with pytest.raises(ValueError):
        laid_out(
            {
                "name": "s",
                "widget": "DockSplit",
                "children": [
                    {"name": "a", "widget": "DockPanel"},
                    {"name": "b", "widget": "DockPanel"},
                    {"name": "c", "widget": "DockPanel"},
                ],
            }
        )


def test_dragging_the_divider_changes_the_ratio() -> None:
    view = {"name": "root", "widget": "Vertical", "children": [_split(value="0.5")]}
    a = app(view)
    s = a.root.find("s")
    rect = s.absolute_rect()
    divider_x = rect.x + s._divider_main + 1
    a.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=divider_x, y=rect.y + 100))
    a.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=divider_x + 150, y=rect.y + 100))
    a.dispatcher.drain()
    assert s._ratio() > 0.5


def test_on_change_carries_the_new_ratio() -> None:
    calls = []
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [{**_split(value="0.5"), "handlers": {"on_change": "resize"}}],
    }
    a = App(view, theme=Theme(dark=True))
    a._handlers["resize"] = lambda e: calls.append(e.value)
    a.mount()
    a.update()
    s = a.root.find("s")
    rect = s.absolute_rect()
    divider_x = rect.x + s._divider_main + 1
    a.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=divider_x, y=rect.y + 100))
    a.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=divider_x + 50, y=rect.y + 100))
    a.dispatcher.drain()
    assert calls and float(calls[-1]) != 0.5


def test_arrow_keys_step_the_ratio() -> None:
    view = {"name": "root", "widget": "Vertical", "children": [_split(value="0.5")]}
    a = app(view)
    s = a.root.find("s")
    a.dispatcher.focus(s)
    a.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Right"))
    a.dispatcher.drain()
    assert s._ratio() == pytest.approx(0.52)
    a.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Left"))
    a.dispatcher.drain()
    assert s._ratio() == pytest.approx(0.50)


def test_arrow_keys_use_the_splits_own_axis_when_vertical() -> None:
    """`Right`/`Left` only make sense for a horizontal split; a vertical one
    must answer to `Down`/`Up` instead, the same axis-aware mapping its own
    layout already uses."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [_split(value="0.5", axis="vertical")],
    }
    a = app(view)
    s = a.root.find("s")
    a.dispatcher.focus(s)
    a.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Down"))
    a.dispatcher.drain()
    assert s._ratio() == pytest.approx(0.52)
    a.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Up"))
    a.dispatcher.drain()
    assert s._ratio() == pytest.approx(0.50)


def test_a_pane_never_shrinks_below_the_minimum() -> None:
    from pysilver.widgets.dock import DockSplitElement

    e = laid_out(_split(value="0.0"), Constraints.tight(Size(1000.0, 500.0)))
    left = e.find("left")
    assert left.size.width == pytest.approx(DockSplitElement.MIN_PANE)


def test_nesting_a_split_inside_a_split() -> None:
    view = {
        "name": "root",
        "widget": "DockSplit",
        "children": [
            {"name": "left", "widget": "DockPanel", "children": [{"widget": "Text", "text": "L"}]},
            {
                "name": "nested",
                "widget": "DockSplit",
                "style": {"axis": "vertical"},
                "children": [
                    {
                        "name": "top",
                        "widget": "DockPanel",
                        "children": [{"widget": "Text", "text": "T"}],
                    },
                    {
                        "name": "bottom",
                        "widget": "DockPanel",
                        "children": [{"widget": "Text", "text": "B"}],
                    },
                ],
            },
        ],
    }
    e = build_element(parse_view(view).root)
    e.layout(Constraints.tight(Size(1000.0, 500.0)))
    top = e.find("top")
    bottom = e.find("bottom")
    assert top.size.height > 0.0
    assert bottom.size.height > 0.0
    assert top.size.width == bottom.size.width < 1000.0


def test_divider_uses_outline_variant() -> None:
    view = {"name": "root", "widget": "Vertical", "children": [_split()]}
    a = app(view)
    tokens = {int(s["flags"][2]) for s in paint(a).view}
    assert PAL.index("outline_variant") in tokens


# ------------------------------------------------------------------ focus


@pytest.mark.parametrize("kind", ["DockGroup", "DockSplit"])
def test_are_focusable(kind: str) -> None:
    from pysilver.runtime.events import FOCUSABLE_KINDS

    assert kind in FOCUSABLE_KINDS


# ---------------------------------------------------------- runtime drag/drop


def _two_groups(*, second_two_panels: bool = False) -> dict:
    """`left` (one panel) beside `right` (one or two panels), matching the
    shape most of these tests drag between."""
    right_children = [panel("terminal", "Terminal")]
    if second_two_panels:
        right_children.append(panel("output", "Output"))
    return {
        "name": "root",
        "widget": "DockSplit",
        "style": {"width": 800, "height": 400},
        "children": [
            {"name": "left", "widget": "DockGroup", "children": [panel("editor", "Editor")]},
            {"name": "right", "widget": "DockGroup", "children": right_children},
        ],
    }


def drag(a: App, start: tuple[float, float], *moves: tuple[float, float]) -> None:
    """A press, past-threshold move(s), then release at the last point --
    the minimum shape `dock_drag`'s gesture state machine needs to
    register a drag rather than a click."""
    sx, sy = start
    a.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=sx, y=sy))
    a.dispatcher.drain()
    for mx, my in moves:
        a.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=mx, y=my))
        a.dispatcher.drain()
    lx, ly = moves[-1]
    a.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=lx, y=ly))
    a.dispatcher.drain()


def test_a_plain_click_still_switches_tabs_not_a_drag() -> None:
    """Below `DRAG_THRESHOLD`, this is an ordinary tab click -- must not be
    swallowed by the new press/move/up handlers."""
    view = _two_groups(second_two_panels=True)
    a = app(view)
    right = a.root.find("right")
    rect = right.absolute_rect()
    click(a, rect.x + 20, rect.y + 20)
    assert right._active_name() == "terminal"


def test_a_drag_that_releases_back_on_its_own_group_does_not_switch_tabs() -> None:
    """Found live: a real cross-group drag left `state.data["dragging"]`
    stuck `True` forever, because the synthesized CLICK that used to clear
    it only fires when release lands back on the *same* element as the
    press (`EventDispatcher._dispatch_pointer`) -- true for THIS case
    (wobble within one group, past threshold, release still over it), but
    never true for a genuine cross-group drop. `end_drag`'s own
    `just_dragged` one-shot flag is what actually has to suppress the
    tab-switch here; assert that mechanism works for the one case where a
    CLICK really does follow."""
    view = _two_groups(second_two_panels=True)
    a = app(view)
    right = a.root.find("right")
    rect = right.absolute_rect()
    start = (rect.x + 20, rect.y + 20)  # "terminal" tab
    # Wobble past DRAG_THRESHOLD but land back over the same group, on a
    # different tab ("output") -- a real drag, released on itself.
    end = (rect.x + 20, rect.y + 20 + 20)
    drag(a, start, (start[0] + 20, start[1] + 5), end)
    assert right._active_name() == "terminal", "the drag's own drop decided this, not a stray click"
    # And a plain, later click still works normally -- the guard is a
    # one-shot flag, not stuck permanently suppressing clicks.
    right2 = a.root.find("right")
    output_x = right2.absolute_rect().x + right2._tab_rects()[1][1] + 10
    click(a, output_x, right2.absolute_rect().y + 20)
    assert right2._active_name() == "output"


def test_dragging_a_tab_onto_another_groups_strip_inserts_it_as_a_tab() -> None:
    a = app(_two_groups())
    left = a.root.find("left")
    right = a.root.find("right")
    start = (left.absolute_rect().x + 20, left.absolute_rect().y + 20)
    target_rect = right.absolute_rect()
    # Within right's own tab strip (TAB_HEIGHT) -- the only zone that means
    # "insert as a tab" now; the content area is always a split.
    drop = (target_rect.x + target_rect.width / 2, target_rect.y + 20.0)
    drag(a, start, (start[0] + 20, start[1] + 5), drop)

    right2 = a.root.find("right")
    assert [c.name for c in right2.children] == ["terminal", "editor"]
    assert a.root.find("editor") is not None, "moved, not disposed"


def test_a_click_after_a_cancelled_drag_does_not_switch_tabs() -> None:
    """`on_click`'s own drag-guard: the synthesized click after a drag's
    POINTER_UP must not also switch the active tab."""
    view = _two_groups(second_two_panels=True)
    a = app(view)
    right = a.root.find("right")
    start = (right.absolute_rect().x + 20, right.absolute_rect().y + 20)
    # Drag onto genuinely empty space, well outside the 800x400 view (no
    # dock target at all) -- a no-op drop, but still a real drag, past
    # threshold.
    drag(a, start, (start[0] + 50, start[1] + 5), (5000.0, 5000.0))
    assert right._active_name() == "terminal", "the drag's own drop, not a click, decides this"


def test_the_content_area_has_exactly_the_four_zones_phil_specified() -> None:
    """phil's own spec, confirmed with an annotated screenshot: tab strip
    (covered separately, not by `_classify`), the lower third of the
    content area always means "split vertically", and everything above
    that means "split horizontally" on whichever side (left or right of
    center) the point is on. No "top" zone exists at all."""
    from pysilver.widgets.dock_drag import _classify

    w, h = 400.0, 300.0
    assert _classify(50.0, 10.0, w, h) == "left"
    assert _classify(350.0, 10.0, w, h) == "right"
    assert _classify(50.0, h - 10.0, w, h) == "bottom", "bottom band overrides side"
    assert _classify(350.0, h - 10.0, w, h) == "bottom", "bottom band overrides side"
    # Just above vs. just inside the bottom third -- the boundary itself.
    boundary = h * (2.0 / 3.0)
    assert _classify(50.0, boundary - 5.0, w, h) == "left"
    assert _classify(50.0, boundary + 5.0, w, h) == "bottom"


def test_dropping_directly_on_another_groups_tab_strip_always_inserts_a_tab() -> None:
    """Found live: dropping onto another group's own tab strip -- the
    intuitive, standard way to land two tabs next to each other, exactly
    the way `editor`/`readme` start out in this test's own view -- used to
    fall into the generic center/edge fraction test and land in the "top
    edge" split zone instead, since a (short) tab strip sits mostly outside
    the old 25%-75% center band of the whole rect. The tab strip must
    always mean "insert as a tab", regardless of where along it you drop."""
    a = app(_two_groups())
    left = a.root.find("left")
    right = a.root.find("right")
    start = (left.absolute_rect().x + 20, left.absolute_rect().y + 20)
    target_rect = right.absolute_rect()
    # Well within the tab strip band (TAB_HEIGHT=48), but off-center
    # horizontally -- must still classify as "tab", not an edge.
    drop = (target_rect.x + 5.0, target_rect.y + 10.0)
    drag(a, start, (start[0] + 20, start[1] + 5), drop)

    right2 = a.root.find("right")
    assert [c.name for c in right2.children] == ["terminal", "editor"], (
        "landed as a tab in `right`, not a split -- the whole point of this test"
    )


def test_dragging_onto_an_edge_splits_and_creates_a_new_pane() -> None:
    a = app(_two_groups())
    left = a.root.find("left")
    right = a.root.find("right")
    start = (right.absolute_rect().x + 20, right.absolute_rect().y + 20)
    target_rect = left.absolute_rect()
    # Right edge of `left`'s own rect -- classified as zone "right".
    drop = (target_rect.x + target_rect.width * 0.9, target_rect.y + target_rect.height / 2)
    drag(a, start, (start[0] - 20, start[1] + 5), drop)

    left2 = a.root.find("left")
    terminal = a.root.find("terminal")
    assert terminal is not None, "moved, not disposed"
    assert left2 is not None
    new_split = left2.parent
    from pysilver.widgets.dock import DockSplitElement

    assert isinstance(new_split, DockSplitElement)
    # Dropped on the right edge -- the original content stays first.
    assert new_split.children[0] is left2
    assert terminal.parent in new_split.children


def test_dragging_onto_a_group_nested_two_levels_deep_finds_that_group() -> None:
    """Found live: dropping a tab onto a group nested inside TWO DockSplits
    (a root split whose second child is itself a split) crashed --
    `find_drop_target` iterated `hit_path` backwards (root-to-leaf instead
    of `hit_test`'s own documented deepest-first order), so it resolved to
    an ANCESTOR split instead of the specific group under the cursor. A
    flat, one-level layout accidentally self-corrected through the
    split-recursion step; a real two-level layout, the whole reason this
    feature nests DockSplit inside DockSplit at all, did not."""
    view = {
        "name": "root",
        "widget": "DockSplit",
        "style": {"width": 900, "height": 400},
        "children": [
            {"name": "files", "widget": "DockGroup", "children": [panel("browser", "Browser")]},
            {
                "name": "right_split",
                "widget": "DockSplit",
                "style": {"axis": "vertical"},
                "children": [
                    {
                        "name": "editor_group",
                        "widget": "DockGroup",
                        "children": [panel("editor", "Editor"), panel("readme", "Readme")],
                    },
                    {
                        "name": "terminal_group",
                        "widget": "DockGroup",
                        "children": [panel("terminal", "Terminal")],
                    },
                ],
            },
        ],
    }
    a = app(view)
    editor_group = a.root.find("editor_group")
    terminal_group = a.root.find("terminal_group")
    # "readme" is editor_group's 2nd tab -- start past "editor"'s own width.
    start = (editor_group.absolute_rect().x + 90, editor_group.absolute_rect().y + 20)
    target_rect = terminal_group.absolute_rect()
    # Within terminal_group's own tab strip -- "insert as a tab" zone.
    drop = (target_rect.x + target_rect.width / 2, target_rect.y + 20.0)
    drag(a, start, (start[0] + 10, start[1] + 5), drop)

    assert a.root.find("readme") is not None, "moved, not orphaned by a crash mid-drop"
    terminal_group2 = a.root.find("terminal_group")
    assert terminal_group2 is not None and len(terminal_group2.children) == 2, (
        "the actual target -- not an ancestor split -- received the drop"
    )
    editor_group2 = a.root.find("editor_group")
    assert [c.name for c in editor_group2.children] == ["editor"]


def test_an_emptied_group_collapses_its_parent_split() -> None:
    """The last panel leaving a group must not leave a dangling empty group
    and an invalid single-child split sitting in the tree."""
    view = {
        "name": "root",
        "widget": "DockSplit",
        "style": {"width": 900, "height": 400},
        "children": [
            {"name": "outer", "widget": "DockGroup", "children": [panel("files", "Files")]},
            {
                "name": "inner_split",
                "widget": "DockSplit",
                "children": [
                    {
                        "name": "mid",
                        "widget": "DockGroup",
                        "children": [panel("editor", "Editor")],
                    },
                    {
                        "name": "empties",
                        "widget": "DockGroup",
                        "children": [panel("terminal", "T")],
                    },
                ],
            },
        ],
    }
    a = app(view)
    empties = a.root.find("empties")
    mid = a.root.find("mid")
    start = (empties.absolute_rect().x + 20, empties.absolute_rect().y + 20)
    target_rect = mid.absolute_rect()
    # Dead center of `mid`'s own rect -- classifies as some split zone
    # (exactly which one is not what this test is about); the invariant
    # below must hold regardless of which valid zone a drop lands in.
    drop = (target_rect.x + target_rect.width / 2, target_rect.y + target_rect.height / 2)
    drag(a, start, (start[0] - 20, start[1] + 5), drop)

    from pysilver.widgets.dock import DockSplitElement

    assert a.root.find("empties") is None, "the emptied group is gone"
    assert a.root.find("terminal") is not None, "its panel was moved, not disposed"

    def splits(node) -> list:
        found = [node] if isinstance(node, DockSplitElement) else []
        for child in node.children:
            found.extend(splits(child))
        return found

    for split in splits(a.root):
        assert len(split.children) != 1, "no dangling single-child split anywhere in the tree"
