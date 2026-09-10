"""Hit rects that differ from paint rects.

The framework drew and hit-tested the same rectangle until now, which is why
M3's "at least 48x48dp" target could be quoted but not expressed: making a
control hittable at 48dp meant painting it at 48dp. These cover the split --
that the enlarged area really takes events, that it changes nothing about
layout or paint, and that the three ways it can go wrong (escaping a clip,
overlapping a sibling, hiding behind an ancestor's own rect) go the right way.
"""

from __future__ import annotations

import pytest

from pysilver.layout import Constraints, Size
from pysilver.paint import DisplayList
from pysilver.runtime.events import EventDispatcher, EventType, PointerEvent
from pysilver.spec import parse_view
from pysilver.theme import Palette, Theme
from pysilver.tree.element import PaintContext
from pysilver.widgets import build_element


def tree(spec: dict, width: float = 200.0, height: float = 100.0):
    root = build_element(parse_view(spec).root)
    root.layout(Constraints.tight(Size(width, height)))
    return root


def row(*children: dict, spacing: float = 16.0) -> dict:
    return {
        "name": "root",
        "widget": "Horizontal",
        "style": {
            "width": "expand",
            "height": "expand",
            "spacing": spacing,
            "cross_alignment": "center",
        },
        "children": list(children),
    }


def names(path) -> list[str]:
    return [element.name for element in path]


# ------------------------------------------------------------------ defaults


def test_without_either_property_the_two_rects_are_the_same() -> None:
    """The split must cost nothing to a view that does not ask for it."""
    root = tree(row({"name": "cb", "widget": "Checkbox"}))
    box = root.find("cb")
    assert box.absolute_hit_rect() == box.absolute_rect()
    assert root._hit_overflow == 0.0


# -------------------------------------------------------------- min_hit_size


def test_a_minimum_grows_a_small_control_around_its_centre() -> None:
    """M3 states the rule as a minimum size, so this is the property that
    quotes it directly. An 18dp checkbox becomes a 48dp target, and the box
    stays where it was drawn."""
    root = tree(row({"name": "cb", "widget": "Checkbox", "style": {"min_hit_size": 48}}))
    paint = root.find("cb").absolute_rect()
    hit = root.find("cb").absolute_hit_rect()
    assert (paint.width, paint.height) == (18.0, 18.0)
    assert (hit.width, hit.height) == (48.0, 48.0)
    assert paint.x - hit.x == pytest.approx(15.0)
    assert paint.y - hit.y == pytest.approx(15.0)


def test_a_minimum_never_shrinks_a_control_that_already_exceeds_it() -> None:
    """Sized explicitly here because the assertion is about the hit rect
    matching the paint rect, and pinning both to a stated number says that
    more plainly than deriving one from the label."""
    root = tree(
        row(
            {
                "name": "b",
                "widget": "Button",
                "text": "Go",
                "style": {"width": 64, "height": 40, "min_hit_size": 20},
            }
        )
    )
    assert root.find("b").size == Size(64.0, 40.0)
    assert root.find("b").absolute_hit_rect() == root.find("b").absolute_rect()


def test_a_minimum_grows_only_the_axis_that_is_short() -> None:
    """A 200x18 control is wide enough already; only its height is lacking."""
    root = tree(
        {
            "name": "root",
            "widget": "Vertical",
            "style": {"width": "expand", "height": "expand"},
            "children": [
                {
                    "name": "bar",
                    "widget": "Container",
                    "style": {"width": "expand", "height": 18, "min_hit_size": 48},
                }
            ],
        }
    )
    hit = root.find("bar").absolute_hit_rect()
    assert (hit.width, hit.height) == (200.0, 48.0)


# --------------------------------------------------------------- hit_padding


def test_padding_grows_each_edge_independently() -> None:
    """The asymmetric case a minimum cannot state -- a control that should be
    forgiving on one side only."""
    root = tree(
        {
            "name": "root",
            "widget": "Vertical",
            "style": {"width": "expand", "height": "expand"},
            "children": [
                {
                    "name": "b",
                    "widget": "Button",
                    "text": "Go",
                    "style": {"width": 60, "height": 20, "hit_padding": [0, 30, 0, 0]},
                }
            ],
        }
    )
    hit = root.find("b").absolute_hit_rect()
    assert (hit.x, hit.y, hit.width, hit.height) == (0.0, -30.0, 60.0, 50.0)


def test_a_minimum_measures_from_the_padded_rect() -> None:
    """Otherwise the two would fight: padding would push past the minimum on
    one axis while the minimum re-derived the other from the bare size."""
    root = tree(
        row({"name": "cb", "widget": "Checkbox", "style": {"hit_padding": 4, "min_hit_size": 48}})
    )
    hit = root.find("cb").absolute_hit_rect()
    assert (hit.width, hit.height) == (48.0, 48.0)


# ------------------------------------------------------------- what it hits


def test_the_enlarged_area_takes_the_hit() -> None:
    root = tree(row({"name": "cb", "widget": "Checkbox", "style": {"min_hit_size": 48}}))
    paint = root.find("cb").absolute_rect()
    assert names(root.hit_test(paint.x + 9.0, paint.y + 9.0)) == ["cb", "root"]
    # 10dp below the drawn box, still inside the 48dp target.
    assert names(root.hit_test(paint.x + 9.0, paint.bottom + 10.0)) == ["cb", "root"]
    # ...and 20dp below it, outside.
    assert names(root.hit_test(paint.x + 9.0, paint.bottom + 20.0)) == ["root"]


def test_a_hit_rect_may_reach_outside_its_ancestors() -> None:
    """The part that is not a one-line change. Hit testing stopped at any
    element that did not contain the point, which is correct only while a hit
    rect cannot leave its parent -- so a target wider than the row holding it
    would have been unreachable at the very edges it was widened to cover.
    """
    root = tree(row({"name": "cb", "widget": "Checkbox", "style": {"min_hit_size": 48}}))
    assert root.find("cb").absolute_rect().x == 0.0
    assert names(root.hit_test(-10.0, 50.0)) == ["cb", "root"], "left of the row entirely"
    assert names(root.hit_test(-16.0, 50.0)) == [], "and past even the widened target"


def test_an_ancestor_reports_a_miss_for_its_own_widened_region() -> None:
    """The row descends into a region wider than itself so a child can be
    found there. It must not then claim that region for itself."""
    root = tree(row({"name": "cb", "widget": "Checkbox", "style": {"min_hit_size": 48}}))
    assert names(root.hit_test(-10.0, 50.0)) == ["cb", "root"]
    assert names(root.hit_test(-10.0, 95.0)) == [], "beside the target, outside the row"


def test_two_overlapping_targets_go_to_the_one_on_top() -> None:
    """Enlarged targets can overlap where the drawn controls do not -- M3 asks
    for 8dp between targets and nothing here can enforce it. The tie is broken
    the same way overlapping paint is: the later sibling wins.
    """
    root = tree(
        row(
            {"name": "a", "widget": "Checkbox", "style": {"min_hit_size": 48}},
            {"name": "b", "widget": "Checkbox", "style": {"min_hit_size": 48}},
            spacing=4.0,
        )
    )
    a, b = root.find("a").absolute_hit_rect(), root.find("b").absolute_hit_rect()
    assert a.right > b.x, "the targets overlap, which is the case under test"
    assert names(root.hit_test(b.x + 1.0, 50.0)) == ["b", "root"]
    assert names(root.hit_test(a.x + 1.0, 50.0)) == ["a", "root"]


def test_a_grandchild_target_is_reachable_through_two_ancestors() -> None:
    """The cached overflow has to climb, not just cover one level."""
    root = tree(
        {
            "name": "root",
            "widget": "Vertical",
            "style": {"width": "expand", "height": "expand"},
            "children": [
                {
                    "name": "mid",
                    "widget": "Horizontal",
                    "style": {"width": 18, "height": 18},
                    "children": [
                        {"name": "cb", "widget": "Checkbox", "style": {"min_hit_size": 48}}
                    ],
                }
            ],
        }
    )
    assert root._hit_overflow == 15.0, "the row's overflow reached the column"
    assert names(root.hit_test(2.0, 12.0)) == ["cb", "mid", "root"]


def test_a_clipping_parent_confines_the_target() -> None:
    """A scroll view clips what it paints, so it must clip what it hits: a
    control scrolled just past the edge cannot take a click it has no way to
    show a response to."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "style": {"width": "expand", "height": "expand"},
        "children": [
            {"name": "gap", "widget": "Spacer", "style": {"height": 40}},
            {
                "name": "sv",
                "widget": "ScrollView",
                "style": {"width": "expand", "height": 60},
                "children": [
                    {
                        "name": "col",
                        "widget": "Vertical",
                        "style": {"width": "expand"},
                        "children": [
                            {"name": "cb", "widget": "Checkbox", "style": {"min_hit_size": 48}},
                            {
                                "name": "filler",
                                "widget": "Container",
                                "style": {"width": "expand", "height": 200},
                            },
                        ],
                    }
                ],
            },
        ],
    }
    root = tree(view, 200.0, 200.0)
    assert root.find("cb").absolute_hit_rect().y == 25.0, "the target reaches above the viewport"
    assert names(root.hit_test(9.0, 45.0))[0] == "cb", "inside the viewport it still works"
    assert names(root.hit_test(9.0, 35.0)) == ["root"], "above it, the clip wins"


# ------------------------------------------------- it changes nothing visible


def test_neither_property_affects_layout() -> None:
    """The whole point: a control keeps its size and its neighbours keep their
    positions. A target that pushed its siblings apart would be a padding
    property wearing a different name."""
    plain = tree(row({"name": "cb", "widget": "Checkbox"}, {"name": "x", "widget": "Checkbox"}))
    grown = tree(
        row(
            {"name": "cb", "widget": "Checkbox", "style": {"min_hit_size": 48, "hit_padding": 6}},
            {"name": "x", "widget": "Checkbox"},
        )
    )
    for name in ("root", "cb", "x"):
        assert plain.find(name).size == grown.find(name).size
        assert plain.find(name).absolute_rect() == grown.find(name).absolute_rect()


def test_neither_property_affects_paint() -> None:
    def painted(spec: dict) -> list:
        root = tree(spec)
        ctx = PaintContext(
            display_list=DisplayList(),
            palette=Palette(Theme()),
            text=root.text_engine,
            pixel_ratio=1.0,
        )
        root.paint(ctx, root.offset)
        return [tuple(instance["rect"]) for instance in ctx.display_list.view]

    plain = painted(row({"name": "cb", "widget": "Checkbox"}))
    grown = painted(row({"name": "cb", "widget": "Checkbox", "style": {"min_hit_size": 48}}))
    assert plain == grown


# --------------------------------------------------------------- end to end


def test_a_click_in_the_enlarged_area_reaches_the_handler() -> None:
    """Rects are the mechanism; this is the behaviour anyone actually wants."""
    root = tree(
        row(
            {
                "name": "cb",
                "widget": "Checkbox",
                "style": {"min_hit_size": 48},
                "handlers": {"on_click": "toggle"},
            }
        )
    )
    calls: list[str] = []
    dispatcher = EventDispatcher()
    dispatcher.root = root
    dispatcher.bind_handlers({"toggle": lambda e: calls.append("hit")})
    paint = root.find("cb").absolute_rect()
    point = {"x": paint.x + 9.0, "y": paint.bottom + 10.0}
    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, **point))
    dispatcher.post(PointerEvent(EventType.POINTER_UP, **point))
    dispatcher.drain()
    assert calls == ["hit"]


def test_the_cursor_follows_the_target_not_the_drawing() -> None:
    """Otherwise the enlarged area would take clicks while looking dead."""
    root = tree(row({"name": "cb", "widget": "Checkbox", "style": {"min_hit_size": 48}}))
    dispatcher = EventDispatcher()
    dispatcher.root = root
    paint = root.find("cb").absolute_rect()
    dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=paint.x + 9.0, y=paint.bottom + 10.0))
    dispatcher.drain()
    assert dispatcher.cursor == "pointer"


def test_reconciliation_picks_up_a_changed_target() -> None:
    """A reload that changes only these two properties marks paint, not
    layout -- so refreshing them on the next layout pass would have meant an
    edited view file quietly keeping the old target."""
    root = tree(row({"name": "cb", "widget": "Checkbox"}))
    assert root.find("cb").absolute_hit_rect().width == 18.0

    grown = parse_view(row({"name": "cb", "widget": "Checkbox", "style": {"min_hit_size": 48}}))
    root.find("cb").update_spec(grown.root.children[0])
    hit = root.find("cb").absolute_hit_rect()
    assert (hit.width, hit.height) == (48.0, 48.0)
    paint = root.find("cb").absolute_rect()
    assert names(root.hit_test(paint.x + 9.0, paint.bottom + 10.0)) == ["cb", "root"], (
        "and the wider area takes hits"
    )
