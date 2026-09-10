"""The layout protocol: caching, relayout boundaries, and dirty propagation.

These tests guard the claim that makes the whole engine viable -- that a change
deep in the tree relayouts a handful of nodes rather than thousands.
"""

from __future__ import annotations

import pytest

from pysilver.layout import (
    Align,
    Constraints,
    LayoutNode,
    LayoutOwner,
    LeafNode,
    Padding,
    Size,
    SizedBox,
)
from pysilver.layout.algorithms import EdgeInsets, Vertical


class CountingLeaf(LeafNode):
    """A leaf that records how many times it actually performed layout."""

    __slots__ = ("layouts",)

    def __init__(self, width: float = 10.0, height: float = 10.0) -> None:
        super().__init__(width, height)
        self.layouts = 0

    def perform_layout(self, constraints: Constraints) -> Size:
        self.layouts += 1
        return super().perform_layout(constraints)


class CountingVertical(Vertical):
    __slots__ = ("layouts",)

    def __init__(self, children=()) -> None:  # type: ignore[no-untyped-def]
        super().__init__(children)
        self.layouts = 0

    def perform_layout(self, constraints: Constraints) -> Size:
        self.layouts += 1
        return super().perform_layout(constraints)


# ------------------------------------------------------------------ basics


def test_leaf_clamps_preferred_to_constraints() -> None:
    leaf = LeafNode(200, 200)
    assert leaf.layout(Constraints.loose(Size(100, 50))) == Size(100, 50)


def test_size_starts_zero_before_layout() -> None:
    assert LeafNode(10, 10).size == Size(0, 0)


def test_layout_clears_needs_layout() -> None:
    leaf = LeafNode(10, 10)
    assert leaf.needs_layout
    leaf.layout(Constraints.unbounded())
    assert not leaf.needs_layout


def test_violating_constraints_is_an_error() -> None:
    class Rogue(LayoutNode):
        def perform_layout(self, constraints: Constraints) -> Size:
            return Size(9999, 9999)

    with pytest.raises(AssertionError, match="violates"):
        Rogue().layout(Constraints.tight(Size(10, 10)))


# ----------------------------------------------------------------- caching


def test_identical_constraints_reuse_the_cached_size() -> None:
    leaf = CountingLeaf()
    c = Constraints.loose(Size(100, 100))
    leaf.layout(c)
    leaf.layout(c)
    leaf.layout(c)
    assert leaf.layouts == 1


def test_changed_constraints_force_relayout() -> None:
    leaf = CountingLeaf()
    leaf.layout(Constraints.loose(Size(100, 100)))
    leaf.layout(Constraints.loose(Size(50, 50)))
    assert leaf.layouts == 2


def test_marking_dirty_forces_relayout() -> None:
    leaf = CountingLeaf()
    c = Constraints.loose(Size(100, 100))
    leaf.layout(c)
    leaf.mark_needs_layout()
    leaf.layout(c)
    assert leaf.layouts == 2


# -------------------------------------------------------------- boundaries


def test_root_is_always_a_boundary() -> None:
    leaf = LeafNode(10, 10)
    leaf.layout(Constraints.unbounded())
    assert leaf.is_relayout_boundary


def test_tight_constraints_create_a_boundary() -> None:
    child = LeafNode(10, 10)
    SizedBox(child, width=50, height=50).layout(Constraints.unbounded())
    assert child.is_relayout_boundary


def test_loose_constraints_do_not_create_a_boundary() -> None:
    child = LeafNode(10, 10)
    parent = Padding(child, EdgeInsets.all(5))
    parent.layout(Constraints.unbounded())
    assert not child.is_relayout_boundary
    assert child.relayout_boundary is parent


def test_parent_uses_size_false_creates_a_boundary() -> None:
    """The cheapest outcome: a parent that ignores its child's size."""

    class Ignoring(Padding):
        def perform_layout(self, constraints: Constraints) -> Size:
            child = self.child
            assert child is not None
            child.layout(constraints.loosen(), parent_uses_size=False)
            return constraints.constrain(Size(100, 100))

    child = LeafNode(10, 10)
    Ignoring(child).layout(Constraints.loose(Size(500, 500)))
    assert child.is_relayout_boundary


def test_tight_constraints_propagate_through_padding() -> None:
    """Deflating a tight constraint leaves it tight, so the child is also a
    boundary. Padding inside a fixed-size box is the cheapest arrangement there
    is -- dirt cannot escape the leaf."""
    leaf = LeafNode(10, 10)
    inner = Padding(leaf, EdgeInsets.all(5))
    SizedBox(inner, width=100, height=100).layout(Constraints.unbounded())
    assert inner.is_relayout_boundary
    assert leaf.is_relayout_boundary


def test_boundary_is_inherited_through_loose_parents() -> None:
    """Under genuinely loose constraints, descendants share the nearest boundary."""
    leaf = LeafNode(10, 10)
    inner = Padding(leaf, EdgeInsets.all(1))
    outer = Vertical([inner])
    root = Align(outer)
    root.layout(Constraints.loose(Size(500, 500)))

    assert outer.is_relayout_boundary, "Align ignores its child's size when bounded"
    assert not inner.is_relayout_boundary
    assert inner.relayout_boundary is outer
    assert leaf.relayout_boundary is outer


# ------------------------------------------------ dirty propagation + owner


def test_dirt_stops_at_the_nearest_boundary() -> None:
    """The headline claim: a deep change does not reach the root.

    The leaf sits under a Vertical (loose constraints, so no boundary of its own)
    inside a fixed-size box. Dirt climbs to the Vertical and stops there.
    """
    leaf = CountingLeaf()
    inner = Vertical([leaf])
    boundary = SizedBox(inner, width=100, height=100)
    root = CountingVertical([boundary])

    owner = LayoutOwner()
    root.attach(owner)
    root.layout(Constraints.tight(Size(200, 200)))
    assert root.layouts == 1
    assert inner.is_relayout_boundary

    leaf.preferred = Size(20, 20)

    assert leaf.needs_layout
    assert inner.needs_layout
    assert not boundary.needs_layout, "dirt escaped past the boundary"
    assert not root.needs_layout, "dirt reached the root"
    assert owner.dirty_count == 1


def test_flush_relayouts_only_the_dirty_subtree() -> None:
    leaf = CountingLeaf()
    boundary = SizedBox(Vertical([leaf]), width=100, height=100)
    sibling = CountingLeaf()
    root = CountingVertical([boundary, sibling])

    owner = LayoutOwner()
    root.attach(owner)
    root.layout(Constraints.tight(Size(200, 200)))
    before = (root.layouts, sibling.layouts, leaf.layouts)

    leaf.preferred = Size(20, 20)
    performed = owner.flush()

    assert performed == 1
    assert root.layouts == before[0], "root relaid out unnecessarily"
    assert sibling.layouts == before[1], "sibling relaid out unnecessarily"
    assert leaf.layouts == before[2] + 1


def test_boundary_size_is_unchanged_by_subtree_relayout() -> None:
    leaf = CountingLeaf()
    boundary = SizedBox(Vertical([leaf]), width=100, height=100)
    owner = LayoutOwner()
    boundary.attach(owner)
    boundary.layout(Constraints.loose(Size(500, 500)))

    leaf.preferred = Size(80, 80)
    owner.flush()
    assert boundary.size == Size(100, 100)


def test_flush_processes_parents_before_children() -> None:
    outer_leaf = CountingLeaf()
    inner_leaf = CountingLeaf()
    inner = SizedBox(inner_leaf, width=40, height=40)
    outer = SizedBox(Vertical([outer_leaf, inner]), width=100, height=100)
    root = Vertical([outer])

    owner = LayoutOwner()
    root.attach(owner)
    root.layout(Constraints.tight(Size(200, 200)))

    inner_leaf.preferred = Size(5, 5)
    outer_leaf.preferred = Size(5, 5)
    assert owner.flush() >= 1
    assert not root.needs_layout


def test_marking_dirty_twice_schedules_once() -> None:
    leaf = LeafNode(10, 10)
    boundary = SizedBox(leaf, width=50, height=50)
    owner = LayoutOwner()
    boundary.attach(owner)
    boundary.layout(Constraints.unbounded())

    boundary.mark_needs_layout()
    boundary.mark_needs_layout()
    assert owner.dirty_count == 1


# ------------------------------------------------------------ tree surgery


def test_adding_a_child_dirties_the_parent() -> None:
    parent = Vertical([])
    parent.layout(Constraints.unbounded())
    assert not parent.needs_layout
    parent.add_child(LeafNode(10, 10))
    assert parent.needs_layout


def test_removing_a_child_dirties_the_parent_and_detaches_it() -> None:
    leaf = LeafNode(10, 10)
    parent = Vertical([leaf])
    parent.layout(Constraints.unbounded())
    assert not parent.needs_layout

    parent.remove_child(leaf)
    assert parent.needs_layout
    assert leaf.parent is None


def test_depth_tracks_nesting() -> None:
    leaf = LeafNode()
    root = Vertical([Vertical([leaf])])
    assert root.depth == 0
    assert root.children[0].depth == 1
    assert leaf.depth == 2


def test_reparenting_requires_removal_first() -> None:
    leaf = LeafNode()
    Vertical([leaf])
    with pytest.raises(ValueError, match="already has a parent"):
        Vertical([leaf])


def test_walk_is_depth_first_preorder() -> None:
    a, b = LeafNode(), LeafNode()
    root = Vertical([a, b])
    assert list(root.walk()) == [root, a, b]
