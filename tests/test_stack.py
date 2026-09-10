"""Stack: an overlay container where each child is positioned by its OWN
`style.align_x`/`align_y`, falling back to the group's own value when a
child does not set one.

No test exercised this at all before the widget-by-widget design review
found it silently broken -- every child was being pinned to whatever the
GROUP's own alignment said, regardless of what it asked for individually.
"""

from __future__ import annotations

from pysilver.layout import Constraints, Size
from pysilver.spec import parse_view
from pysilver.widgets import build_element


def laid_out(spec, width=400.0, height=400.0):
    e = build_element(parse_view(spec).root)
    e.layout(Constraints.loose(Size(width, height)))
    return e


def test_each_child_is_positioned_by_its_own_alignment() -> None:
    """The Stack demo's own live example: a centred back panel and a front
    square that moves to whichever corner it names -- not wherever the
    group's own alignment says."""
    stack = laid_out(
        {
            "name": "s",
            "widget": "Stack",
            "style": {"width": 260, "height": 160},
            "children": [
                {
                    "name": "back",
                    "widget": "Container",
                    "style": {"width": 220, "height": 120, "align_x": 0.5, "align_y": 0.5},
                },
                {
                    "name": "front",
                    "widget": "Container",
                    "style": {"width": 64, "height": 64, "align_x": 0.0, "align_y": 0.0},
                },
            ],
        }
    )
    back, front = stack.children
    assert (back.offset.x, back.offset.y) == (20.0, 20.0)
    assert (front.offset.x, front.offset.y) == (0.0, 0.0)


def test_a_child_with_no_alignment_falls_back_to_the_groups_own() -> None:
    """The gallery's own badge-corner usage: the group carries the alignment
    and an unlabelled child inherits it -- must keep working, not just the
    fully-explicit form."""
    stack = laid_out(
        {
            "name": "s",
            "widget": "Stack",
            "style": {"width": 100, "height": 64, "align_x": 1.0, "align_y": 0.0},
            "children": [
                {"name": "base", "widget": "Container", "style": {"width": 100, "height": 64}},
                {"name": "badge", "widget": "Container", "style": {"width": 28, "height": 28}},
            ],
        }
    )
    _base, badge = stack.children
    assert (badge.offset.x, badge.offset.y) == (72.0, 0.0)


def test_an_unset_child_does_not_inherit_a_sibling_that_did_set_one() -> None:
    """The Badge widget's own demo: an icon with no alignment sits at the
    group's default top-left corner while its sibling badge, which DOES set
    align_x/align_y, moves independently -- one child's explicit value must
    not leak onto another child that never asked for it."""
    stack = laid_out(
        {
            "name": "s",
            "widget": "Stack",
            "style": {"width": 40, "height": 40},
            "children": [
                {"name": "icon", "widget": "Container", "style": {"width": 24, "height": 24}},
                {
                    "name": "dot",
                    "widget": "Container",
                    "style": {"width": 8, "height": 8, "align_x": 1.0, "align_y": 0.0},
                },
            ],
        }
    )
    icon, dot = stack.children
    assert (icon.offset.x, icon.offset.y) == (0.0, 0.0)
    assert (dot.offset.x, dot.offset.y) == (32.0, 0.0)
