"""Layout algorithms: padding, alignment, flex distribution, stacking."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pysilver.layout import (
    ALIGN_BOTTOM_RIGHT,
    ALIGN_CENTER,
    Align,
    Alignment,
    Center,
    ConstrainedBox,
    Constraints,
    CrossAxisAlignment,
    EdgeInsets,
    Flexible,
    Horizontal,
    LayoutNode,
    LeafNode,
    MainAxisAlignment,
    MainAxisSize,
    Offset,
    Padding,
    Size,
    SizedBox,
    Spacer,
    Stack,
    Vertical,
)

LOOSE_500 = Constraints.loose(Size(500, 500))


# ----------------------------------------------------------------- padding


def test_padding_inflates_child_size() -> None:
    p = Padding(LeafNode(100, 50), EdgeInsets.all(10))
    assert p.layout(LOOSE_500) == Size(120, 70)


def test_padding_offsets_child_by_top_left() -> None:
    child = LeafNode(100, 50)
    Padding(child, EdgeInsets(left=10, top=20, right=5, bottom=1)).layout(LOOSE_500)
    assert child.offset == Offset(10, 20)


def test_padding_deflates_child_constraints() -> None:
    child = LeafNode(500, 500)
    Padding(child, EdgeInsets.all(10)).layout(Constraints.tight(Size(100, 100)))
    assert child.size == Size(80, 80)


def test_empty_padding_still_occupies_space() -> None:
    assert Padding(None, EdgeInsets.all(10)).layout(LOOSE_500) == Size(20, 20)


def test_single_child_node_rejects_a_second_child() -> None:
    """Extra children would paint unpositioned on top of each other with no
    error anywhere -- this must fail loudly instead."""
    p = Padding(LeafNode(10, 10), EdgeInsets.all(5))
    with pytest.raises(ValueError, match="single child"):
        p.add_child(LeafNode(10, 10))


# --------------------------------------------------------------- alignment


def test_align_fills_bounded_constraints() -> None:
    assert Align(LeafNode(50, 50)).layout(Constraints.loose(Size(200, 100))) == Size(200, 100)


def test_center_positions_child() -> None:
    child = LeafNode(50, 50)
    Center(child).layout(Constraints.tight(Size(200, 100)))
    assert child.offset == Offset(75, 25)


def test_align_bottom_right() -> None:
    child = LeafNode(50, 50)
    Align(child, ALIGN_BOTTOM_RIGHT).layout(Constraints.tight(Size(200, 100)))
    assert child.offset == Offset(150, 50)


def test_align_shrinks_when_unbounded() -> None:
    a = Align(LeafNode(50, 40))
    assert a.layout(Constraints.unbounded()) == Size(50, 40)


def test_align_size_factor_multiplies_child() -> None:
    a = Align(LeafNode(50, 40), ALIGN_CENTER, width_factor=2.0, height_factor=3.0)
    assert a.layout(LOOSE_500) == Size(100, 120)


def test_align_loosens_constraints_for_child() -> None:
    """A child inside Align may be smaller than the tight parent."""
    child = LeafNode(30, 30)
    Align(child).layout(Constraints.tight(Size(200, 200)))
    assert child.size == Size(30, 30)


# ---------------------------------------------------------------- sizedbox


def test_sizedbox_forces_child_size() -> None:
    child = LeafNode(999, 999)
    box = SizedBox(child, width=80, height=40)
    assert box.layout(LOOSE_500) == Size(80, 40)
    assert child.size == Size(80, 40)


def test_sizedbox_single_axis_leaves_other_free() -> None:
    child = LeafNode(30, 70)
    SizedBox(child, width=80).layout(LOOSE_500)
    assert child.size == Size(80, 70)


def test_sizedbox_is_clamped_by_parent() -> None:
    assert SizedBox(None, width=999, height=999).layout(LOOSE_500) == Size(500, 500)


def test_constrained_box_enforces_within_parent() -> None:
    cb = ConstrainedBox(LeafNode(10, 10), extra=Constraints(min_width=60, min_height=60))
    assert cb.layout(LOOSE_500) == Size(60, 60)


# --------------------------------------------------------------------- row


def test_horizontal_places_children_left_to_right() -> None:
    a, b, c = LeafNode(30, 10), LeafNode(50, 20), LeafNode(20, 5)
    Horizontal([a, b, c]).layout(Constraints.tight(Size(200, 100)))
    assert a.offset == Offset(0, 0)
    assert b.offset == Offset(30, 0)
    assert c.offset == Offset(80, 0)


def test_horizontal_cross_size_is_tallest_child() -> None:
    row = Horizontal([LeafNode(10, 10), LeafNode(10, 45), LeafNode(10, 20)])
    assert row.layout(Constraints.loose(Size(500, 500))).height == 45


def test_horizontal_main_size_max_fills_available() -> None:
    row = Horizontal([LeafNode(10, 10)], main_size=MainAxisSize.MAX)
    assert row.layout(Constraints.loose(Size(300, 100))).width == 300


def test_horizontal_main_size_min_shrinks_to_content() -> None:
    row = Horizontal([LeafNode(10, 10), LeafNode(20, 10)], main_size=MainAxisSize.MIN)
    assert row.layout(Constraints.loose(Size(300, 100))).width == 30


def test_horizontal_spacing_between_children() -> None:
    a, b = LeafNode(10, 10), LeafNode(10, 10)
    Horizontal([a, b], spacing=8).layout(LOOSE_500)
    assert b.offset.x == 18


# -------------------------------------------------------------------- flex


def test_expanded_child_fills_free_space() -> None:
    fixed, flex = LeafNode(100, 10), Flexible(LeafNode(0, 10))
    Horizontal([fixed, flex]).layout(Constraints.tight(Size(300, 50)))
    assert flex.size.width == 200


def test_flex_weights_divide_proportionally() -> None:
    a = Flexible(LeafNode(0, 10), flex=1)
    b = Flexible(LeafNode(0, 10), flex=3)
    Horizontal([a, b]).layout(Constraints.tight(Size(400, 50)))
    assert (a.size.width, b.size.width) == (100, 300)


def test_flex_distribution_loses_no_space() -> None:
    """Running-total distribution: shares must sum exactly, no dropped pixels."""
    kids = [Flexible(LeafNode(0, 10), flex=1) for _ in range(3)]
    Horizontal(kids).layout(Constraints.tight(Size(100, 50)))
    assert sum(k.size.width for k in kids) == pytest.approx(100.0)


@given(
    total=st.floats(min_value=1, max_value=10000),
    weights=st.lists(st.integers(min_value=1, max_value=20), min_size=1, max_size=8),
)
def test_flex_always_fills_exactly(total: float, weights: list[int]) -> None:
    kids = [Flexible(LeafNode(0, 10), flex=w) for w in weights]
    Horizontal(kids).layout(Constraints.tight(Size(total, 50)))
    assert sum(k.size.width for k in kids) == pytest.approx(total, abs=1e-6)


def test_loose_fit_allows_smaller_child() -> None:
    from pysilver.layout import FlexFit

    flex = Flexible(LeafNode(20, 10), flex=1, fit=FlexFit.LOOSE)
    Horizontal([flex]).layout(Constraints.tight(Size(300, 50)))
    assert flex.size.width == 20


def test_spacer_consumes_free_space() -> None:
    a, b = LeafNode(50, 10), LeafNode(50, 10)
    Horizontal([a, Spacer(), b]).layout(Constraints.tight(Size(300, 50)))
    assert b.offset.x == 250


def test_flex_in_unbounded_space_is_an_error() -> None:
    row = Horizontal([Flexible(LeafNode(10, 10))])
    with pytest.raises(ValueError, match="unbounded"):
        row.layout(Constraints.unbounded())


def test_negative_flex_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Flexible(LeafNode(10, 10), flex=-1)


def test_inflexible_children_measured_before_flexible() -> None:
    fixed = LeafNode(120, 10)
    flex = Flexible(LeafNode(0, 10))
    Horizontal([fixed, flex]).layout(Constraints.tight(Size(200, 50)))
    assert fixed.size.width == 120
    assert flex.size.width == 80


# ------------------------------------------------------- main-axis alignment


@pytest.mark.parametrize(
    ("alignment", "first_x"),
    [
        (MainAxisAlignment.START, 0.0),
        (MainAxisAlignment.CENTER, 50.0),
        (MainAxisAlignment.END, 100.0),
        (MainAxisAlignment.SPACE_EVENLY, 33.333333),
        (MainAxisAlignment.SPACE_AROUND, 25.0),
        (MainAxisAlignment.SPACE_BETWEEN, 0.0),
    ],
)
def test_main_axis_alignment(alignment: MainAxisAlignment, first_x: float) -> None:
    a, b = LeafNode(50, 10), LeafNode(50, 10)
    Horizontal([a, b], main_alignment=alignment).layout(Constraints.tight(Size(200, 50)))
    assert a.offset.x == pytest.approx(first_x, abs=1e-4)


def test_space_between_pushes_to_edges() -> None:
    a, b = LeafNode(50, 10), LeafNode(50, 10)
    Horizontal([a, b], main_alignment=MainAxisAlignment.SPACE_BETWEEN).layout(
        Constraints.tight(Size(200, 50))
    )
    assert a.offset.x == 0
    assert b.offset.x == 150


# ------------------------------------------------------ cross-axis alignment


@pytest.mark.parametrize(
    ("alignment", "y"),
    [
        (CrossAxisAlignment.START, 0.0),
        (CrossAxisAlignment.CENTER, 20.0),
        (CrossAxisAlignment.END, 40.0),
    ],
)
def test_cross_axis_alignment(alignment: CrossAxisAlignment, y: float) -> None:
    child = LeafNode(10, 10)
    Horizontal([child], cross_alignment=alignment).layout(Constraints.tight(Size(200, 50)))
    assert child.offset.y == pytest.approx(y)


def test_cross_axis_stretch_forces_full_height() -> None:
    child = LeafNode(10, 10)
    Horizontal([child], cross_alignment=CrossAxisAlignment.STRETCH).layout(
        Constraints.tight(Size(200, 50))
    )
    assert child.size.height == 50


# ------------------------------------------------------------------ column


def test_vertical_stacks_vertically() -> None:
    a, b = LeafNode(10, 30), LeafNode(10, 20)
    Vertical([a, b]).layout(Constraints.tight(Size(100, 200)))
    assert a.offset == Offset(0, 0)
    assert b.offset == Offset(0, 30)


def test_vertical_flex_divides_height() -> None:
    a = Flexible(LeafNode(10, 0), flex=1)
    b = Flexible(LeafNode(10, 0), flex=2)
    Vertical([a, b]).layout(Constraints.tight(Size(100, 300)))
    assert (a.size.height, b.size.height) == (100, 200)


# ------------------------------------------------------------------- stack


def test_stack_sizes_to_largest_child() -> None:
    s = Stack([LeafNode(50, 20), LeafNode(30, 90)])
    assert s.layout(LOOSE_500) == Size(50, 90)


def test_stack_overlays_at_same_origin() -> None:
    a, b = LeafNode(50, 50), LeafNode(50, 50)
    Stack([a, b]).layout(LOOSE_500)
    assert a.offset == b.offset == Offset(0, 0)


def test_stack_alignment_centres_children() -> None:
    small = LeafNode(20, 20)
    Stack([LeafNode(100, 100), small], alignment=Alignment(0.5, 0.5)).layout(LOOSE_500)
    assert small.offset == Offset(40, 40)


def test_stack_expand_fills_constraints() -> None:
    s = Stack([LeafNode(10, 10)], expand=True)
    assert s.layout(Constraints.tight(Size(300, 200))) == Size(300, 200)


# --------------------------------------------------------- the invariant


def leaves(n: LayoutNode) -> list[LayoutNode]:
    return [x for x in n.walk() if not x.children]


@st.composite
def random_tree(draw: st.DrawFn, depth: int = 0) -> LayoutNode:
    # Terminate at 20% per level rather than 50%, so generated trees are deep
    # enough to actually exercise constraint propagation.
    if depth >= 5 or draw(st.integers(0, 4)) == 0:
        return LeafNode(draw(st.floats(0, 200)), draw(st.floats(0, 200)))
    kind = draw(st.sampled_from(["horizontal", "vertical", "padding", "align", "stack", "sized"]))
    if kind in ("horizontal", "vertical"):
        kids = draw(st.lists(random_tree(depth + 1), min_size=1, max_size=4))
        cls = Horizontal if kind == "horizontal" else Vertical
        return cls(kids)
    child = draw(random_tree(depth + 1))
    match kind:
        case "padding":
            return Padding(child, EdgeInsets.all(draw(st.floats(0, 20))))
        case "align":
            return Align(child)
        case "stack":
            return Stack([child])
        case _:
            return SizedBox(child, width=draw(st.floats(1, 200)))


@given(
    random_tree(), st.floats(min_value=1, max_value=1000), st.floats(min_value=1, max_value=1000)
)
def test_layout_result_always_satisfies_constraints(tree: LayoutNode, w: float, h: float) -> None:
    c = Constraints.loose(Size(w, h))
    assert c.is_satisfied_by(tree.layout(c))


@given(random_tree(), st.floats(min_value=1, max_value=1000))
def test_size_is_independent_of_position(tree: LayoutNode, w: float) -> None:
    """The invariant: a node's size depends only on its constraints and children.

    Moving nodes must not change any size. If this ever fails, relayout
    boundaries are unsound and subtree-local layout is invalid.
    """
    c = Constraints.loose(Size(w, w))
    tree.layout(c)
    before = [n.size for n in tree.walk()]

    for i, node in enumerate(tree.walk()):
        node.offset = Offset(i * 13.0, i * 7.0)
    for node in tree.walk():
        node.mark_needs_layout()
    tree.layout(c)

    assert [n.size for n in tree.walk()] == before


@given(random_tree(), st.floats(min_value=1, max_value=1000))
def test_layout_is_deterministic(tree: LayoutNode, w: float) -> None:
    c = Constraints.loose(Size(w, w))
    tree.layout(c)
    first = [(n.size, n.offset) for n in tree.walk()]
    for node in tree.walk():
        node.mark_needs_layout()
    tree.layout(c)
    assert [(n.size, n.offset) for n in tree.walk()] == first


@given(random_tree())
def test_children_stay_within_finite_parents(tree: LayoutNode) -> None:
    tree.layout(Constraints.tight(Size(400, 400)))
    for node in tree.walk():
        assert node.size.is_finite
        assert node.size.width >= 0 and node.size.height >= 0
