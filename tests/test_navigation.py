"""Wave 2: navigation, app bar, tabs, segmented buttons, lists, progress."""

from __future__ import annotations

import pytest

from pysilver import App, Signal, Theme
from pysilver.layout import Constraints, Size
from pysilver.paint import NO_TOKEN, DisplayList, Kind
from pysilver.spec import WidgetKind, parse_view
from pysilver.theme import Palette
from pysilver.widgets import build_element
from pysilver.widgets.base import measure_text
from pysilver.widgets.material import BadgeElement
from pysilver.widgets.navigation import ICON, TAB_LABEL_ROLE, TabElement

PAL = Palette(Theme(dark=True))


def laid_out(spec, width=600.0, height=400.0):
    e = build_element(parse_view(spec).root)
    e.layout(Constraints.loose(Size(width, height)))
    return e


def app_with(children, value=None, widget="Tabs", style=None):
    view = {
        "name": "root",
        "widget": "Vertical",
        "style": {"background": "surface", "width": "expand"},
        "children": [
            {
                "name": "c",
                "widget": widget,
                "style": style or {},
                **({"value": value} if value else {}),
                "children": children,
            }
        ],
    }
    a = App(view, theme=Theme(dark=True))
    a.mount()
    a.update()
    return a


def paint(app) -> DisplayList:
    dl = DisplayList()
    app.paint(dl)
    return dl


def tokens(dl) -> set[int]:
    return {int(s["flags"][2]) for s in dl.view} - {NO_TOKEN}


TABS = [
    {"name": f"t{i}", "widget": "Tab", "text": n}
    for i, n in enumerate(("Overview", "Details", "History"))
]
RAIL = [
    {"name": f"r{i}", "widget": "NavItem", "icon": ic, "label": lb}
    for i, (ic, lb) in enumerate([("home", "Home"), ("search", "Search"), ("settings", "Settings")])
]


# --------------------------------------------------------------- registered


@pytest.mark.parametrize(
    "kind",
    [
        "NavigationRail",
        "NavItem",
        "TopAppBar",
        "Tabs",
        "Tab",
        "SegmentedButton",
        "Segment",
        "ListItem",
        "LinearProgress",
        "TreeView",
        "TreeItem",
        "StatusBar",
    ],
)
def test_kind_builds(kind: str) -> None:
    assert laid_out({"name": "w", "widget": kind}) is not None


def test_every_kind_is_registered() -> None:
    from pysilver.widgets.base import _REGISTRY, create_element

    create_element(parse_view({"name": "x", "widget": "Tabs"}).root)
    assert set(_REGISTRY) == set(WidgetKind)


# ------------------------------------------------------ M3 dimensions (dp)


def test_a_collapsed_rail_is_eighty_wide() -> None:
    """M3 4.5. Also M3 Expressive's own point: NavigationRail and
    NavigationDrawer are one component, collapsed and expanded states of
    the same widget -- collapsed no longer means "hidden," it means the
    narrow, icon-only form, and "the collapsed navigation rail should not
    be hidden.\""""
    e = laid_out({"name": "w", "widget": "NavigationRail", "collapsed": "true", "children": RAIL})
    assert e.size.width == 80.0


def test_an_expanded_rail_is_within_the_m3_drawer_range() -> None:
    """M3 4.4: the expanded rail replaces the old drawer's own 240-360dp
    range entirely -- `collapsed: false` is also the default, so an unset
    rail is expanded, not collapsed."""
    e = laid_out({"name": "w", "widget": "NavigationRail", "collapsed": "false", "children": RAIL})
    assert 240.0 <= e.size.width <= 360.0
    default = laid_out({"name": "w", "widget": "NavigationRail", "children": RAIL})
    assert 240.0 <= default.size.width <= 360.0


def test_top_app_bar_is_sixty_four_high() -> None:
    """M3 4.2 small / center-aligned."""
    e = laid_out({"name": "w", "widget": "TopAppBar", "text": "Title"})
    assert e.size.height == 64.0


def test_tabs_are_forty_eight_high() -> None:
    """M3 4.7."""
    e = laid_out({"name": "w", "widget": "Tabs", "children": TABS})
    assert e.size.height == 48.0


def test_a_tab_with_an_icon_grows_the_whole_bar_to_sixty_four() -> None:
    """`COMPONENT_TABS.md`'s own Measurements table: "Container height (icon
    and label text): 64dp" -- and "the container should always... be
    divided into equal sections", so one iconed tab lifts the WHOLE bar,
    even an icon-less sibling next to it."""
    children = [
        {"name": "t0", "widget": "Tab", "text": "Overview", "icon": "home"},
        {"name": "t1", "widget": "Tab", "text": "Details"},
    ]
    e = laid_out({"name": "w", "widget": "Tabs", "children": children})
    assert e.size.height == 64.0
    assert e.find("t1").size.height == 64.0


def test_an_icon_only_tab_still_grows_the_bar_and_paints_one_glyph() -> None:
    app = app_with([{"name": "t0", "widget": "Tab", "icon": "home"}])
    tab = app.root.find("t0")
    assert tab.size.height == TabElement.ICON_HEIGHT == 64.0
    glyphs = [s for s in paint(app).view if s["flags"][0] == Kind.GLYPH]
    assert len(glyphs) == 1


def test_a_tabs_icon_paints_above_its_label() -> None:
    """The M3 diagram (`m3.material.io`, fetched live) shows the icon
    stacked above the label, the pair centred as one block -- not side by
    side. The icon is the sole glyph well above the label's own cluster."""
    app = app_with([{"name": "t0", "widget": "Tab", "text": "Home", "icon": "home"}], value="t0")
    glyph_ys = sorted(float(s["rect"][1]) for s in paint(app).view if s["flags"][0] == Kind.GLYPH)
    assert glyph_ys[0] < glyph_ys[1] - 10.0


def test_default_icon_position_is_stacked() -> None:
    e = laid_out({"name": "w", "widget": "Tab", "text": "Home", "icon": "home"})
    assert e.style.icon_position == "stacked"


def test_a_leading_icon_paints_left_of_its_label_on_the_same_row() -> None:
    """`style.icon_position: leading` -- opt-in, phil: "make icons opt-in
    for left and right of label on the tab too." Inline, not stacked: the
    icon and every label glyph share roughly one row (unlike the stacked
    case above, which separates them vertically)."""
    children = [
        {
            "name": "t0",
            "widget": "Tab",
            "text": "Home",
            "icon": "home",
            "style": {"icon_position": "leading"},
        }
    ]
    app = app_with(children, value="t0")
    glyphs = [s for s in paint(app).view if s["flags"][0] == Kind.GLYPH]
    xs = sorted(float(s["rect"][0]) for s in glyphs)
    assert xs[0] < xs[1] - 10.0, "the icon is the sole glyph well left of the label's own cluster"
    ys = [float(s["rect"][1]) for s in glyphs]
    assert max(ys) - min(ys) < 10.0, "inline, not stacked -- everything shares one row"


def test_a_trailing_icon_paints_right_of_its_label_on_the_same_row() -> None:
    children = [
        {
            "name": "t0",
            "widget": "Tab",
            "text": "Home",
            "icon": "home",
            "style": {"icon_position": "trailing"},
        }
    ]
    app = app_with(children, value="t0")
    glyphs = [s for s in paint(app).view if s["flags"][0] == Kind.GLYPH]
    xs = sorted(float(s["rect"][0]) for s in glyphs)
    assert xs[-1] > xs[-2] + 10.0, "the icon is the sole glyph well right of the label's cluster"
    ys = [float(s["rect"][1]) for s in glyphs]
    assert max(ys) - min(ys) < 10.0, "inline, not stacked -- everything shares one row"


def test_an_inline_icon_still_grows_the_bar_to_sixty_four() -> None:
    """The M3 table gives one height for "icon and label text", not one
    per arrangement -- leading/trailing grow the bar exactly like stacked."""
    children = [
        {
            "name": "t0",
            "widget": "Tab",
            "text": "Home",
            "icon": "home",
            "style": {"icon_position": "leading"},
        }
    ]
    e = laid_out({"name": "w", "widget": "Tabs", "children": children})
    assert e.size.height == TabElement.ICON_HEIGHT == 64.0


def test_a_text_only_tab_is_unaffected_by_the_icon_anatomy() -> None:
    """No `icon:` at all -- the overwhelming majority of existing tabs --
    must see zero change from this feature."""
    e = laid_out({"name": "w", "widget": "Tab", "text": "Overview"})
    assert e.size.height == TabElement.HEIGHT == 48.0


# --------------------------------------------------------------- tab badges


def _badge_boxes(dl):
    """The badge's own painted box -- a fully-round BOX at exactly the dot
    or numbered-badge height, which nothing else a Tab paints matches (a
    hover/focus state layer is neither that size nor that shape)."""
    heights = {BadgeElement.DOT, BadgeElement.HEIGHT}
    return [
        s
        for s in dl.view
        if s["flags"][0] == Kind.BOX
        and any(abs(float(s["rect"][3]) - h) < 0.01 for h in heights)
        and abs(float(s["radii"][0]) - float(s["rect"][3]) / 2) < 0.01
    ]


def test_a_tab_with_no_badge_is_unaffected() -> None:
    """No `badge:` at all -- the overwhelming majority of existing tabs --
    must see zero change from this feature."""
    e = laid_out({"name": "w", "widget": "Tab", "text": "Overview"})
    label = measure_text("Overview", TAB_LABEL_ROLE, engine=e.text_engine)
    assert e.size.width == pytest.approx(label.width + 2 * TabElement.PAD_X)

    app = app_with([{"name": "t0", "widget": "Tab", "text": "Overview"}])
    assert _badge_boxes(paint(app)) == []


def test_a_numbered_badge_widens_a_label_only_tab_and_paints_after_it() -> None:
    """`COMPONENT_TABS.md`'s own Measurements table: "padding between
    inline text and badge: 4dp" -- and the tab's own measured width must
    grow to fit it, or it would collide with the tab's own edge."""
    without = laid_out({"name": "w", "widget": "Tab", "text": "Overview"})
    with_badge = laid_out({"name": "w", "widget": "Tab", "text": "Overview", "badge": "3"})
    assert with_badge.size.width > without.size.width + TabElement.TEXT_BADGE_GAP

    app = app_with([{"name": "t0", "widget": "Tab", "text": "Overview", "badge": "3"}])
    dl = paint(app)
    boxes = _badge_boxes(dl)
    assert len(boxes) == 1
    glyphs = [s for s in dl.view if s["flags"][0] == Kind.GLYPH]
    label_right = max(float(s["rect"][0]) + float(s["rect"][2]) for s in glyphs)
    assert float(boxes[0]["rect"][0]) < label_right, "the badge's own digit sits among the glyphs"
    assert len(glyphs) == len("Overview") + 1, "the label's own glyphs, plus the badge's digit"


def test_a_dot_badge_ignores_its_own_content() -> None:
    """`style.badge_variant: dot` shows a bare dot -- `Badge`'s own
    identical distinction -- and paints no digits at all."""
    app = app_with(
        [
            {
                "name": "t0",
                "widget": "Tab",
                "text": "Overview",
                "badge": "3",
                "style": {"badge_variant": "dot"},
            }
        ]
    )
    dl = paint(app)
    boxes = _badge_boxes(dl)
    assert len(boxes) == 1
    assert round(float(boxes[0]["rect"][2]), 3) == round(float(boxes[0]["rect"][3]), 3) == 6.0
    glyphs = [s for s in dl.view if s["flags"][0] == Kind.GLYPH]
    assert len(glyphs) == len("Overview"), "label glyphs only -- no '3' painted for the dot"


def test_a_badge_on_a_stacked_icon_does_not_widen_the_tab() -> None:
    """A stacked icon's badge OVERLAPS the icon instead of adding width --
    `COMPONENT_TABS.md`'s own "overlap of badge on stacked icon: 6dp" is a
    deliberate overlap, not an addition."""
    without_badge = laid_out({"name": "w", "widget": "Tab", "text": "Home", "icon": "home"})
    with_badge = laid_out(
        {"name": "w", "widget": "Tab", "text": "Home", "icon": "home", "badge": "3"}
    )
    assert with_badge.size.width == without_badge.size.width


def test_a_badge_on_a_stacked_icon_overlaps_its_top_right_corner() -> None:
    """Independently recomputes the icon's own block geometry (the same
    formula `_paint_stacked` uses) rather than trying to pick "the icon
    glyph" out of the display list -- a badge that overlaps the icon's own
    top edge can itself paint glyphs above the icon, so glyph y-order alone
    can't tell them apart once a badge is involved."""
    app = app_with(
        [{"name": "t0", "widget": "Tab", "text": "Home", "icon": "home", "badge": "3"}],
        value="t0",
    )
    tab = app.root.find("t0")
    label = measure_text("Home", TAB_LABEL_ROLE, engine=tab.text_engine)
    block_height = ICON + TabElement.STACK_GAP + label.height
    rect = tab.absolute_rect()
    top = rect.y + (tab.size.height - block_height) / 2
    icon_left = rect.x + (tab.size.width - ICON) / 2

    dl = paint(app)
    boxes = _badge_boxes(dl)
    assert len(boxes) == 1
    badge = boxes[0]
    badge_cx = float(badge["rect"][0]) + float(badge["rect"][2]) / 2
    badge_cy = float(badge["rect"][1]) + float(badge["rect"][3]) / 2
    assert badge_cx == pytest.approx(icon_left + ICON - TabElement.BADGE_OVERLAP, abs=0.5)
    assert badge_cy == pytest.approx(top + TabElement.BADGE_OVERLAP, abs=0.5)


def test_an_inline_icon_with_a_badge_widens_the_tab_and_trails_the_label() -> None:
    without_badge = laid_out(
        {
            "name": "w",
            "widget": "Tab",
            "text": "Home",
            "icon": "home",
            "style": {"icon_position": "leading"},
        }
    )
    with_badge = laid_out(
        {
            "name": "w",
            "widget": "Tab",
            "text": "Home",
            "icon": "home",
            "badge": "3",
            "style": {"icon_position": "leading"},
        }
    )
    assert with_badge.size.width > without_badge.size.width + TabElement.TEXT_BADGE_GAP

    app = app_with(
        [
            {
                "name": "t0",
                "widget": "Tab",
                "text": "Home",
                "icon": "home",
                "badge": "3",
                "style": {"icon_position": "leading"},
            }
        ],
        value="t0",
    )
    dl = paint(app)
    boxes = _badge_boxes(dl)
    assert len(boxes) == 1
    icon_glyph = min(
        (s for s in dl.view if s["flags"][0] == Kind.GLYPH), key=lambda s: float(s["rect"][0])
    )
    icon_x = float(icon_glyph["rect"][0])
    assert float(boxes[0]["rect"][0]) > icon_x + ICON, "badge trails the leading icon and label"


def test_segmented_button_is_forty_high() -> None:
    """M3 1.4."""
    e = laid_out(
        {
            "name": "w",
            "widget": "SegmentedButton",
            "children": [{"name": "s", "widget": "Segment", "text": "A"}],
        }
    )
    assert e.size.height == 40.0


def test_linear_progress_is_four_high() -> None:
    """M3 2.2."""
    e = laid_out({"name": "w", "widget": "LinearProgress", "style": {"width": "expand"}})
    assert e.size.height == 4.0


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ({"text": "One"}, 56.0),
        ({"text": "One", "supporting_text": "Two"}, 72.0),
        ({"text": "One", "style": {"variant": "three_line"}}, 88.0),
    ],
)
def test_list_item_heights(spec: dict, expected: float) -> None:
    """M3 3.7: 56 / 72 / 88dp."""
    e = laid_out({"name": "w", "widget": "ListItem", **spec})
    assert e.size.height == expected


def test_an_expanded_rail_shrinks_below_its_m3_minimum_rather_than_raising() -> None:
    """A layout node must return a size its own constraints permit
    (`layout/node.py` asserts this) -- M3's 240dp minimum is an aspiration,
    not something a narrower parent has to honour. Real crash this session:
    squeezing a Horizontal containing this widget below 300dp raised instead of
    shrinking, because the old code built its inner constraints from the
    unclamped M3 width outright."""
    e = laid_out(
        {"name": "w", "widget": "NavigationRail", "collapsed": "false", "children": RAIL},
        width=143.0,
    )
    assert e.size.width == 143.0


def test_rail_shrinks_below_its_fixed_width_rather_than_raising() -> None:
    """The same crash, one widget over: `NavigationRailElement` had the
    identical unclamped-width bug. No `collapsed:` needed -- the collapsed
    target (80dp) is itself clamped down to whatever room is offered."""
    e = laid_out(
        {"name": "w", "widget": "NavigationRail", "collapsed": "true", "children": RAIL},
        width=40.0,
    )
    assert e.size.width == 40.0


# ----------------------------------------------------------------- collapsed


def test_collapsed_is_bindable() -> None:
    """Layout-invalidating `animated()` retargets but does not jump on the
    first `update()` -- same two-step as `TreeItem`'s own
    `test_expand_state_is_bindable`, driven by `app.motion.tick`. `collapsed:`
    now animates a width instead of snapping to zero, so this needs the same
    treatment."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "c",
                "widget": "NavigationRail",
                "collapsed": "{{ hide.get() }}",
                "children": RAIL,
            }
        ],
    }
    a = App(view, theme=Theme(dark=True))
    hide = Signal(False)
    a.expose(hide=hide)
    a.mount()
    a.update()
    expanded = a.root.find("c").size.width
    assert expanded > 80.0

    hide.set(True)
    a.update()
    assert a.root.find("c").size.width == expanded

    # `Animation.tick` clamps dt to MAX_FRAME_DELTA (0.1s) per call, so a
    # 0.2s transition needs more than one tick to fully settle.
    for _ in range(4):
        a.motion.tick(1.0)
        a.update()
    assert a.root.find("c").size.width == 80.0


def test_the_rail_width_interpolates_mid_transition() -> None:
    """Not just eventually-correct: a partial tick should land strictly
    between the two targets, not jump straight to either one."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "c",
                "widget": "NavigationRail",
                "collapsed": "{{ hide.get() }}",
                "children": RAIL,
            }
        ],
    }
    a = App(view, theme=Theme(dark=True))
    hide = Signal(False)
    a.expose(hide=hide)
    a.mount()
    a.update()
    expanded = a.root.find("c").size.width

    hide.set(True)
    a.update()
    a.motion.tick(0.05)
    a.update()
    mid = a.root.find("c").size.width
    assert 80.0 < mid < expanded


def test_a_collapsed_rail_still_paints_its_items() -> None:
    """Unlike the old zero-width collapse, a collapsed rail is still
    visible -- narrower, not absent. M3: "the collapsed navigation rail
    should not be hidden.\""""
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "c",
                "widget": "NavigationRail",
                "value": "r1",
                "collapsed": "true",
                "children": RAIL,
            }
        ],
    }
    a = App(view, theme=Theme(dark=True))
    a.mount()
    a.update()
    assert paint(a).view.shape[0] > 0


def test_nav_item_swaps_anatomy_once_past_the_halfway_point() -> None:
    """`NavItemElement`'s row-vs-stacked anatomy swaps discretely at the
    parent's progress crossing 0.5, mirroring Accordion's chevron swap --
    not a continuous morph."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "c",
                "widget": "NavigationRail",
                "collapsed": "{{ hide.get() }}",
                "children": RAIL,
            }
        ],
    }
    a = App(view, theme=Theme(dark=True))
    hide = Signal(True)
    a.expose(hide=hide)
    a.mount()
    a.update()
    item = a.root.find("r0")
    collapsed_height = item.size.height

    hide.set(False)
    a.update()
    a.motion.tick(0.001)
    a.update()
    assert item.size.height == collapsed_height, "barely started -- still the collapsed anatomy"

    # `Animation.tick` clamps dt to MAX_FRAME_DELTA (0.1s) per call, so a
    # 0.2s transition needs more than one tick to fully settle.
    for _ in range(4):
        a.motion.tick(1.0)
        a.update()
    assert item.size.height != collapsed_height, "past the midpoint -- now the expanded anatomy"


# ---------------------------------------------------------------- selection


def test_container_marks_only_the_named_child() -> None:
    app = app_with(TABS, value="t1")
    sel = [c.name for c in app.root.find("c").children if c.selected]
    assert sel == ["t1"]


def test_selection_is_bindable() -> None:
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [{"name": "c", "widget": "Tabs", "value": "{{ t.get() }}", "children": TABS}],
    }
    a = App(view, theme=Theme(dark=True))
    t = Signal("t0")
    a.expose(t=t)
    a.mount()
    a.update()
    assert a.root.find("t0").selected
    t.set("t2")
    a.update()
    assert a.root.find("t2").selected
    assert not a.root.find("t0").selected


def test_no_value_selects_nothing() -> None:
    app = app_with(TABS)
    assert not any(c.selected for c in app.root.find("c").children)


def test_unknown_id_selects_nothing() -> None:
    app = app_with(TABS, value="nope")
    assert not any(c.selected for c in app.root.find("c").children)


# ------------------------------------------------------------ multi-select


def _segments(n: int = 3) -> list[dict]:
    return [{"name": f"s{i}", "widget": "Segment", "text": "X"} for i in range(n)]


def test_multi_select_off_by_default() -> None:
    """A comma-separated value in single-select mode still only matches a
    child literally named that whole string -- proving the default really is
    off, not silently permissive."""
    app = app_with(_segments(), value="s0,s2", widget="SegmentedButton")
    assert not any(c.selected for c in app.root.find("c").children)


def test_multi_select_marks_every_named_child() -> None:
    app = app_with(
        _segments(), value="s0,s2", widget="SegmentedButton", style={"multi_select": True}
    )
    sel = {c.name for c in app.root.find("c").children if c.selected}
    assert sel == {"s0", "s2"}


def test_multi_select_with_no_value_selects_nothing() -> None:
    app = app_with(_segments(), widget="SegmentedButton", style={"multi_select": True})
    assert not any(c.selected for c in app.root.find("c").children)


def test_multi_select_is_bindable() -> None:
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "c",
                "widget": "SegmentedButton",
                "value": "{{ picked.get() }}",
                "style": {"multi_select": True},
                "children": _segments(),
            }
        ],
    }
    a = App(view, theme=Theme(dark=True))
    picked = Signal("s0")
    a.expose(picked=picked)
    a.mount()
    a.update()
    assert {c.name for c in a.root.find("c").children if c.selected} == {"s0"}
    picked.set("s0,s1")
    a.update()
    assert {c.name for c in a.root.find("c").children if c.selected} == {"s0", "s1"}


# ---------------------------------------------------------------- rendering


def test_tabs_draw_an_indicator_under_the_active_tab() -> None:
    """M3 4.7/COMPONENT_TABS.md: a 3dp primary indicator, inset 2dp a side."""
    app = app_with(TABS, value="t1")
    active = app.root.find("t1")
    bars = [
        s
        for s in paint(app).view
        if abs(float(s["rect"][3]) - 3.0) < 0.01 and int(s["flags"][2]) == PAL.index("primary")
    ]
    assert len(bars) == 1
    assert float(bars[0]["rect"][2]) == pytest.approx(active.size.width - 4.0)
    assert float(bars[0]["rect"][0]) == pytest.approx(active.offset.x + 2.0)


def test_a_secondary_indicator_is_thinner_and_spans_the_full_tab() -> None:
    """COMPONENT_TABS.md: "Secondary active indicator height: 2dp", no inset."""
    app = app_with(TABS, value="t1", style={"variant": "secondary"})
    active = app.root.find("t1")
    bars = [
        s
        for s in paint(app).view
        if abs(float(s["rect"][3]) - 2.0) < 0.01 and int(s["flags"][2]) == PAL.index("primary")
    ]
    assert len(bars) == 1
    assert float(bars[0]["rect"][2]) == pytest.approx(active.size.width)
    assert float(bars[0]["rect"][0]) == pytest.approx(active.offset.x)


def test_tabs_with_no_selection_draw_no_indicator() -> None:
    app = app_with(TABS)
    bars = [
        s
        for s in paint(app).view
        if abs(float(s["rect"][3]) - 3.0) < 0.01 or abs(float(s["rect"][3]) - 2.0) < 0.01
    ]
    assert bars == []


def test_selected_nav_item_uses_the_active_indicator_colour() -> None:
    """M3 4.5/4.4: secondary_container."""
    app = app_with(RAIL, value="r1", widget="NavigationRail")
    assert PAL.index("secondary_container") in tokens(paint(app))


def test_unselected_rail_has_no_active_indicator() -> None:
    app = app_with(RAIL, widget="NavigationRail")
    assert PAL.index("secondary_container") not in tokens(paint(app))


def test_selected_nav_item_fills_its_icon() -> None:
    """M3 uses the icon FILL axis for selection, not a different icon name."""
    sel = app_with(RAIL, value="r1", widget="NavigationRail")
    unsel = app_with(RAIL, widget="NavigationRail")
    # A filled glyph is a distinct atlas entry, so the two frames differ.
    assert paint(sel).view["uv"].tobytes() != paint(unsel).view["uv"].tobytes()


def test_selected_segment_shows_a_checkmark() -> None:
    """M3 1.4: the active segment includes an 18dp checkmark."""
    segs = [
        {"name": f"s{i}", "widget": "Segment", "text": n} for i, n in enumerate(("Day", "Week"))
    ]
    sel = app_with(segs, value="s0", widget="SegmentedButton")
    unsel = app_with(segs, widget="SegmentedButton")
    glyphs = lambda dl: sum(1 for s in dl.view if s["flags"][0] == Kind.GLYPH)  # noqa: E731
    assert glyphs(paint(sel)) == glyphs(paint(unsel)) + 1


def test_segmented_button_shrinks_to_content_by_default() -> None:
    """Otherwise the outline runs on past the last segment."""
    segs = [{"name": f"s{i}", "widget": "Segment", "text": "X"} for i in range(3)]
    app = app_with(segs, widget="SegmentedButton")
    group = app.root.find("c")
    assert group.size.width == pytest.approx(sum(c.size.width for c in group.children))


def test_segmented_button_divides_an_explicit_width_equally() -> None:
    segs = [{"name": f"s{i}", "widget": "Segment", "text": "X"} for i in range(3)]
    app = app_with(segs, widget="SegmentedButton", style={"width": "expand"})
    widths = [c.size.width for c in app.root.find("c").children]
    assert max(widths) - min(widths) < 1.0


def test_linear_progress_fills_proportionally() -> None:
    def filled(value: str) -> float:
        e = laid_out(
            {"name": "w", "widget": "LinearProgress", "value": value, "style": {"width": "expand"}},
            width=200,
        )
        return e.progress

    assert filled("0") == 0.0
    assert filled("0.5") == 0.5
    assert filled("1") == 1.0


def test_progress_is_clamped() -> None:
    e = laid_out(
        {"name": "w", "widget": "LinearProgress", "value": "5", "style": {"width": "expand"}}
    )
    assert e.progress == 1.0


def test_list_item_renders_both_lines() -> None:
    one = laid_out({"name": "w", "widget": "ListItem", "text": "Only"})
    two = laid_out(
        {"name": "w", "widget": "ListItem", "text": "Head", "supporting_text": "Support"}
    )
    assert two.size.height > one.size.height


def _list_item_with_icon(**spec):
    return laid_out(
        {
            "name": "w",
            "widget": "ListItem",
            "text": "Item",
            "children": [{"widget": "Icon", "text": "inbox", "style": {"icon_size": 24}}],
            **spec,
        }
    )


def test_a_leading_icon_is_actually_laid_out() -> None:
    """`ListItemElement` fully overrides `Padding.perform_layout`, the only
    thing that would otherwise lay out and offset a single child -- a
    leading icon was never laid out at all, staying at its default zero
    size and (0, 0) offset regardless of the row's own height. Found live
    via a real render: the icon painted pinned to the row's exact top-left
    corner in every variant, visibly misaligned with the (correctly
    centred) headline text next to it."""
    e = _list_item_with_icon()
    icon = e.child
    assert icon.size.width == 24.0
    assert icon.size.height == 24.0
    assert icon.offset.x == e.PAD_X


@pytest.mark.parametrize(
    ("spec", "expected_top"),
    [
        ({}, 8.0),
        ({"supporting_text": "Sub"}, 8.0),
        ({"style": {"variant": "three_line"}}, 12.0),
    ],
)
def test_a_leading_icon_is_top_aligned_with_the_right_padding(spec, expected_top) -> None:
    """ "Leading icon top padding: 8dp; ...when height is 88dp or taller:
    12dp" (COMPONENT_LISTS.md) -- a leading icon is always top-aligned,
    unlike a generic leading element (e.g. an avatar), which centres below
    88dp."""
    e = _list_item_with_icon(**spec)
    assert e.child.offset.y == expected_top


def test_the_label_clears_a_leading_icon() -> None:
    """The label used to start at a fixed PAD_X regardless of a leading
    icon's presence, overlapping it (icon spans [PAD_X, PAD_X+24], well past
    where the label started). ICON_GAP lands the label at PAD_X + 24 + 16 =
    56 -- the same inset this widget's own demo already uses for its
    Dividers, chosen to align under the label rather than the icon."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "style": {"background": "surface", "width": "expand"},
        "children": [
            {
                "name": "li",
                "widget": "ListItem",
                "text": "Item",
                "children": [{"widget": "Icon", "text": "inbox", "style": {"icon_size": 24}}],
            }
        ],
    }
    a = App(view, theme=Theme(dark=True))
    a.mount()
    a.update()
    dl = paint(a)
    item = a.root.find("li")
    # Excludes the icon's own glyph(s), which paint somewhere inside its
    # [PAD_X, PAD_X + 24] box -- only the label glyphs are expected past it.
    label_glyphs = [
        s
        for s in dl.view
        if int(s["flags"][0]) == Kind.GLYPH and float(s["rect"][0]) >= item.PAD_X + 24.0
    ]
    assert label_glyphs, "the label should have painted glyphs past the icon"
    assert min(float(s["rect"][0]) for s in label_glyphs) >= item.PAD_X + 24.0 + item.ICON_GAP


def test_supporting_text_is_bindable() -> None:
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {"name": "li", "widget": "ListItem", "text": "H", "supporting_text": "{{ s.get() }}"}
        ],
    }
    a = App(view, theme=Theme(dark=True))
    s = Signal("first")
    a.expose(s=s)
    a.mount()
    assert a.root.find("li").supporting == "first"
    s.set("second")
    assert a.root.find("li").supporting == "second"


def test_centered_app_bar_title_differs_from_left_aligned() -> None:
    def first_glyph_x(variant: str) -> float:
        view = {
            "name": "root",
            "widget": "Vertical",
            "style": {"width": "expand", "background": "surface"},
            "children": [
                {
                    "name": "b",
                    "widget": "TopAppBar",
                    "text": "Title",
                    "style": {"variant": variant, "width": "expand"},
                }
            ],
        }
        a = App(view, theme=Theme(dark=True))
        a.mount()
        dl = paint(a)
        return min(float(s["rect"][0]) for s in dl.view if s["flags"][0] == Kind.GLYPH)

    assert first_glyph_x("center_aligned") > first_glyph_x("filled")


# ------------------------------------------------------------------- focus


@pytest.mark.parametrize("kind", ["NavItem", "Tab", "Segment", "ListItem"])
def test_items_are_focusable(kind: str) -> None:
    from pysilver.runtime.events import FOCUSABLE_KINDS

    assert kind in FOCUSABLE_KINDS


# --------------------------------------------------------------- tree view


def _tree_view(*, root_value: str = "true", leaf_value: str = "false") -> dict:
    return {
        "name": "tv",
        "widget": "TreeView",
        "children": [
            {
                "name": "src",
                "widget": "TreeItem",
                "text": "src",
                "value": root_value,
                "children": [
                    {"name": "main", "widget": "TreeItem", "text": "main.py"},
                    {
                        "name": "utils",
                        "widget": "TreeItem",
                        "text": "utils",
                        "value": leaf_value,
                        "children": [
                            {"name": "helpers", "widget": "TreeItem", "text": "helpers.py"}
                        ],
                    },
                ],
            },
            {"name": "readme", "widget": "TreeItem", "text": "README.md"},
        ],
    }


def test_a_leaf_is_a_header_row_only() -> None:
    e = laid_out({"name": "w", "widget": "TreeItem", "text": "leaf"})
    assert e.size.height == 56.0


def test_two_line_tree_item_is_seventy_two_dp() -> None:
    e = laid_out({"name": "w", "widget": "TreeItem", "text": "leaf", "supporting_text": "detail"})
    assert e.size.height == 72.0


def test_a_collapsed_branch_shows_only_its_header() -> None:
    e = laid_out(
        {
            "name": "w",
            "widget": "TreeItem",
            "text": "src",
            "value": "false",
            "children": [{"name": "c", "widget": "TreeItem", "text": "child"}],
        }
    )
    assert e.size.height == 56.0


def test_an_expanded_branch_sums_its_children() -> None:
    e = laid_out(
        {
            "name": "w",
            "widget": "TreeItem",
            "text": "src",
            "value": "true",
            "children": [
                {"name": "c1", "widget": "TreeItem", "text": "one"},
                {"name": "c2", "widget": "TreeItem", "text": "two"},
            ],
        }
    )
    assert e.size.height == 56.0 + 56.0 + 56.0


def test_depth_is_derived_from_ancestry() -> None:
    e = laid_out(_tree_view())
    assert e.find("src").depth == 0
    assert e.find("utils").depth == 1
    assert e.find("helpers").depth == 2
    assert e.find("readme").depth == 0


def test_only_branches_draw_a_chevron() -> None:
    """A leaf gets no `expand_more`/`expand_less` -- nothing to expand.

    Both variants share one label and an empty-text child, so the only
    possible difference in glyph count is the chevron itself -- a body child
    with real text would add its own glyphs regardless of the parent's own
    collapsed state, since the clip only hides them, it does not cull them
    from the display list (see AccordionElement's own chevron test).
    """

    def render(children: list[dict]) -> DisplayList:
        view = {
            "name": "root",
            "widget": "Vertical",
            "children": [{"name": "w", "widget": "TreeItem", "text": "item", "children": children}],
        }
        app = App(view, theme=Theme(dark=True))
        app.mount()
        dl = DisplayList()
        app.paint(dl)
        return dl

    leaf = render([])
    branch = render([{"name": "c", "widget": "TreeItem", "text": ""}])
    glyphs = lambda dl: sum(1 for s in dl.view if s["flags"][0] == Kind.GLYPH)  # noqa: E731
    assert glyphs(branch) == glyphs(leaf) + 1


def test_tree_selection_is_bindable_at_any_depth() -> None:
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "tv",
                "widget": "TreeView",
                "value": "{{ sel.get() }}",
                "children": [_tree_view()["children"][0]],
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    sel = Signal("helpers")
    app.expose(sel=sel)
    app.mount()
    app.update()
    assert app.root.find("helpers").selected
    assert not app.root.find("src").selected
    sel.set("src")
    app.update()
    assert app.root.find("src").selected
    assert not app.root.find("helpers").selected


def test_expand_state_is_bindable() -> None:
    """Layout-invalidating `animated()` retargets but does not jump on the
    first `update()` -- same two-step as AccordionElement's own binding test
    and `test_motion.py`'s switch, driven by `app.motion.tick`."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "src",
                "widget": "TreeItem",
                "text": "src",
                "value": "{{ open.get() }}",
                "children": [{"name": "c", "widget": "TreeItem", "text": "child"}],
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    open_ = Signal(False)
    app.expose(open=open_)
    app.mount()
    app.update()
    collapsed = app.root.find("src").size.height

    open_.set(True)
    app.update()
    assert app.root.find("src").size.height == collapsed

    app.motion.tick(1.0)
    app.update()
    assert app.root.find("src").size.height > collapsed


def test_collapsing_an_ancestor_clips_every_descendant() -> None:
    """A tree item's clip intersects its ancestor's rather than replacing it
    -- unlike Accordion/ScrollView (never nested inside their own kind in
    practice), a tree item routinely is. Collapsing `a` must hide `c` even
    though `b`, in between, is itself expanded.
    """
    view = {
        "name": "root",
        "widget": "Vertical",
        "style": {"background": "surface"},
        "children": [
            {
                "name": "a",
                "widget": "TreeItem",
                "text": "a",
                "value": "false",
                "children": [
                    {
                        "name": "b",
                        "widget": "TreeItem",
                        "text": "b",
                        "value": "true",
                        "children": [{"name": "c", "widget": "TreeItem", "text": "c"}],
                    }
                ],
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    app.mount()
    dl = DisplayList()
    app.paint(dl)

    glyphs = [s for s in dl.view if s["flags"][0] == Kind.GLYPH]
    above_fold = [s for s in glyphs if s["rect"][1] < 56.0]
    below_fold = [s for s in glyphs if s["rect"][1] >= 56.0]
    assert above_fold, "expected a's own header glyph to exist"
    assert below_fold, "expected b/c's glyphs to exist further down the display list"

    def visible(clip, rect) -> bool:
        """Would the shader's per-pixel clip test let any of `rect` through.

        Mirrors `ui.wgsl` exactly: `if (clip.z > 0.0 && clip.w > 0.0)` is the
        real gate -- EITHER dimension being zero (not just both) means "no
        clip at all", which is why a naive `Rect.intersect` result cannot be
        used to hide content directly (see `TreeItemElement.HIDDEN_EXTENT`).

        A clip rect can also have real area and still hide its own content
        -- b's header clip is a's own restrictive (0, 0, w, 56) rect, which
        has plenty of area but sits nowhere near where b is actually
        positioned (b starts at y=56, entirely below it). So this checks
        overlap with the glyph's own rect too, not just whether the clip
        rect itself is degenerate.
        """
        cx, cy, cw, ch = (float(v) for v in clip)
        if cw <= 0.0 or ch <= 0.0:  # ui.wgsl's own "unclipped" gate
            return True
        rx, ry, rw, rh = (float(v) for v in rect)
        return rx < cx + cw and rx + rw > cx and ry < cy + ch and ry + rh > cy

    # a is at the root with no ancestor clip, so its own header is visible.
    assert all(visible(s["clip"], s["rect"]) for s in above_fold)
    # b and c sit below a's collapsed 56px boundary -- both are hidden by
    # a's clip regardless of b's own (expanded) state.
    assert not any(visible(s["clip"], s["rect"]) for s in below_fold)


# --------------------------------------------------------------- status bar


def test_status_bar_is_twenty_four_high() -> None:
    e = laid_out({"name": "w", "widget": "StatusBar"})
    assert e.size.height == 24.0


def test_status_bar_uses_surface_container() -> None:
    app = app_with([{"name": "label", "widget": "Text", "text": "Ready"}], widget="StatusBar")
    assert PAL.index("surface_container") in tokens(paint(app))


def test_a_spacer_splits_leading_and_trailing_groups() -> None:
    """A Spacer styled `width: expand` must actually claim the free space --
    StatusBar extends Flex directly, not _FlexElement, so without its own
    flex_of override a Spacer here would be measured as an ordinary
    inflexible child and swallow the room meant to be shared, starving
    whatever comes after it (the same gap TopAppBar has and does not need
    to close, since it never puts a Spacer among its own children)."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "style": {"background": "surface", "width": "expand"},
        "children": [
            {
                "name": "bar",
                "widget": "StatusBar",
                "children": [
                    {"name": "lead", "widget": "Text", "text": "Ready"},
                    {"name": "gap", "widget": "Spacer", "style": {"width": "expand"}},
                    {"name": "trail", "widget": "Text", "text": "UTF-8"},
                ],
            }
        ],
    }
    a = App(view, theme=Theme(dark=True))
    a.mount()
    a.update()
    bar = a.root.find("bar")
    lead = a.root.find("lead")
    trail = a.root.find("trail")
    assert trail.size.width > 0.0, "the trailing label was starved of space"
    assert trail.offset.x + trail.size.width <= bar.size.width, "it overflowed the bar"
    assert trail.offset.x > lead.offset.x + lead.size.width, "the spacer did nothing"


def test_status_bar_pads_both_edges() -> None:
    """The Flex layout happens against the deflated width, not the full one
    with padding bolted on afterwards -- otherwise the last child's own
    right edge would run PAD_X past the bar's right edge."""
    from pysilver.widgets.navigation import StatusBarElement

    view = {
        "name": "root",
        "widget": "Vertical",
        "style": {"background": "surface", "width": "expand"},
        "children": [
            {
                "name": "bar",
                "widget": "StatusBar",
                "children": [{"name": "label", "widget": "Text", "text": "Ready"}],
            }
        ],
    }
    a = App(view, theme=Theme(dark=True))
    a.mount()
    a.update()
    label = a.root.find("label")
    assert label.offset.x == StatusBarElement.PAD_X
