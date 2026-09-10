"""The `Shape` widget: a regular polygon as an analytic distance field.

M3 has no shape *component*, but it has a shape *system* -- "the Material shape
library contains many types of shapes that can all morph seamlessly into each
other", with shape morph on the expressive motion scheme. The shapes here are
pySilver's own; the system is what is borrowed.

The point these tests protect is the reason it is a shader branch rather than a
compiled glyph: `sides`, `rotation` and `corner_radius` are instance floats, so
animating them is paint-only and never touches the glyph atlas. A shape drawn
through the text pipeline would thrash an atlas that has no per-entry eviction
-- the same trap that quantised the icon FILL axis.
"""

from __future__ import annotations

import math

import pytest

from pysilver.layout import Constraints, Offset, Size
from pysilver.paint import DisplayList
from pysilver.paint.display_list import Kind
from pysilver.spec import parse_view
from pysilver.theme import Palette, Theme
from pysilver.tree.element import PaintContext
from pysilver.widgets import build_element


def painted(node: dict, width: float = 200.0, height: float = 200.0):
    root = build_element(parse_view({"root": node}).root)
    root.layout(Constraints.tight(Size(width, height)))
    dl = DisplayList()
    ctx = PaintContext(
        display_list=dl,
        palette=Palette(Theme(dark=True)),
        text=root.text_engine,
        pixel_ratio=1.0,
    )
    root.paint(ctx, Offset(0.0, 0.0))
    return dl.view


def shape_instance(node: dict, **kw):
    view = painted(node, **kw)
    polys = [i for i in view if i["flags"][0] == Kind.POLYGON]
    assert polys, "no polygon was emitted"
    return polys[0]


# ------------------------------------------------------------------ emission


def test_a_shape_emits_one_polygon_instance() -> None:
    view = painted({"name": "s", "widget": "Shape"})
    assert sum(1 for i in view if i["flags"][0] == Kind.POLYGON) == 1


def test_the_parameters_reach_the_instance() -> None:
    """params is (border_width, sides, rotation, corner_radius) -- the same
    slot order as a box's border width, so the two branches agree."""
    inst = shape_instance(
        {
            "name": "s",
            "widget": "Shape",
            "style": {"sides": 5, "rotation": 90, "corner_radius": 4},
        }
    )
    _, sides, rotation, radius = inst["params"]
    assert sides == pytest.approx(5.0)
    assert rotation == pytest.approx(math.radians(90)), "authored in degrees, emitted in radians"
    assert radius == pytest.approx(4.0)


def test_a_border_reaches_the_instance() -> None:
    """`params[0]` is the border width the docstring above names but the
    previous test leaves as `_` -- this is what actually exercises it."""
    inst = shape_instance(
        {"name": "s", "widget": "Shape", "style": {"border": {"width": 3, "color": "outline"}}}
    )
    border_width = inst["params"][0]
    assert border_width == pytest.approx(3.0)


def test_a_shape_is_token_coloured_rather_than_a_literal() -> None:
    """A literal colour would opt the shape out of theming entirely."""
    inst = shape_instance({"name": "s", "widget": "Shape", "style": {"background": "tertiary"}})
    assert inst["flags"][2] != 0xFFFFFFFF, "no palette token; a theme switch would not reach it"


def test_sides_may_be_fractional() -> None:
    """The whole reason `sides` is a float. A morph that snapped between whole
    numbers would defeat the point of making shapes animatable."""
    inst = shape_instance({"name": "s", "widget": "Shape", "style": {"sides": 5.5}})
    assert inst["params"][1] == pytest.approx(5.5)


def test_fewer_than_three_sides_is_rejected_at_load() -> None:
    """There is no 2-gon. Failing at load gives a path and a line number;
    failing in the shader gives a blank rectangle."""
    from pysilver.spec import SpecError

    with pytest.raises(SpecError):
        parse_view({"root": {"name": "s", "widget": "Shape", "style": {"sides": 2}}})


# -------------------------------------------------------------------- layout


def test_a_shape_has_an_intrinsic_size() -> None:
    root = build_element(parse_view({"root": {"name": "s", "widget": "Shape"}}).root)
    assert root.layout(Constraints(0.0, 400.0, 0.0, 300.0)) == Size(48.0, 48.0)


def test_an_explicit_size_wins() -> None:
    """Nested, because a root element is stretched to the window by the tight
    constraints it is given."""
    inst = shape_instance(
        {
            "name": "row",
            "widget": "Horizontal",
            "children": [{"name": "s", "widget": "Shape", "style": {"width": 120, "height": 80}}],
        }
    )
    assert inst["rect"][2] == pytest.approx(120.0)
    assert inst["rect"][3] == pytest.approx(80.0)


# ------------------------------------------------------------- invalidation


@pytest.mark.parametrize("prop,value", [("sides", 12), ("rotation", 45), ("corner_radius", 20)])
def test_a_shape_parameter_is_not_a_layout_input(prop: str, value: float) -> None:
    """The claim the whole design rests on.

    `sides`, `rotation` and `corner_radius` change what is drawn and never what
    is measured, so a widget animating them dirties paint alone. If any of them
    reached `perform_layout`, a morphing shape would relayout every frame and
    the cheapness would be a fiction -- and it would be invisible, because the
    picture would still be right.
    """
    plain = build_element(parse_view({"root": {"name": "s", "widget": "Shape"}}).root)
    morphed = build_element(
        parse_view({"root": {"name": "s", "widget": "Shape", "style": {prop: value}}}).root
    )
    free = Constraints(0.0, 400.0, 0.0, 300.0)
    assert plain.layout(free) == morphed.layout(free)


def test_a_morph_changes_the_instance_without_changing_the_size() -> None:
    """The same statement from the other side: the pixels must actually differ,
    or the test above would pass on a shape that ignored its parameters."""
    triangle = shape_instance({"name": "s", "widget": "Shape", "style": {"sides": 3}})
    dodecagon = shape_instance({"name": "s", "widget": "Shape", "style": {"sides": 12}})
    assert triangle["params"][1] != dodecagon["params"][1]
    assert tuple(triangle["rect"]) == tuple(dodecagon["rect"])
