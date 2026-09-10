"""The layout protocol: constraints down, sizes up, parent positions children.

The invariant everything rests on (ARCHITECTURE.md 5.4):

    A node's size depends only on its constraints and its children --
    never on its position, its siblings, or its parent's size.

That is what makes a *relayout boundary* sound. A node is a boundary when its
parent has already fixed its size (tight constraints) or does not read its size
at all; nothing beneath such a node can change its size, so a dirty flag cannot
propagate past it. Relayout then starts from the boundary rather than the root.

Subclasses override :meth:`LayoutNode.perform_layout`. They must never call it
directly -- :meth:`LayoutNode.layout` owns caching, boundary computation, and
invariant checking.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence

from .constraints import OFFSET_ZERO, SIZE_ZERO, Constraints, Offset, Rect, Size

__all__ = ["LayoutNode", "LayoutOwner", "LeafNode"]


class LayoutOwner:
    """Collects dirty relayout boundaries and flushes them in depth order."""

    __slots__ = ("_dirty",)

    def __init__(self) -> None:
        self._dirty: list[LayoutNode] = []

    @property
    def dirty_count(self) -> int:
        return len(self._dirty)

    def schedule(self, node: LayoutNode) -> None:
        self._dirty.append(node)

    def flush(self) -> int:
        """Relayout every dirty boundary. Returns the number of nodes relaid out.

        Shallow nodes go first, so a parent that dirties a child during its own
        layout does not cause that child to be laid out twice.
        """
        performed = 0
        while self._dirty:
            batch = sorted(self._dirty, key=lambda n: n.depth)
            self._dirty = []
            for node in batch:
                if node._needs_layout and node._owner is self:
                    node._layout_without_resize()
                    performed += 1
        return performed


class LayoutNode(ABC):
    """Base class for anything that participates in layout."""

    __slots__ = (
        "_children",
        "_constraints",
        "_depth",
        "_needs_layout",
        "_offset",
        "_owner",
        "_parent",
        "_relayout_boundary",
        "_size",
    )

    def __init__(self, children: Sequence[LayoutNode] = ()) -> None:
        self._children: list[LayoutNode] = []
        self._parent: LayoutNode | None = None
        self._owner: LayoutOwner | None = None
        self._depth: int = 0

        self._constraints: Constraints | None = None
        self._size: Size = SIZE_ZERO
        self._offset: Offset = OFFSET_ZERO
        self._relayout_boundary: LayoutNode | None = None
        self._needs_layout: bool = True

        for child in children:
            self.add_child(child)

    # ------------------------------------------------------------- geometry

    @property
    def size(self) -> Size:
        """Size from the last layout. Reading this before layout returns zero."""
        return self._size

    @property
    def offset(self) -> Offset:
        """Position relative to the parent. Written by the parent, never by self."""
        return self._offset

    @offset.setter
    def offset(self, value: Offset) -> None:
        self._offset = value

    @property
    def constraints(self) -> Constraints | None:
        return self._constraints

    @property
    def rect(self) -> Rect:
        """Parent-relative rect. Absolute rects are composed during paint."""
        return Rect.from_offset_size(self._offset, self._size)

    # ----------------------------------------------------------------- tree

    @property
    def parent(self) -> LayoutNode | None:
        return self._parent

    @property
    def children(self) -> Sequence[LayoutNode]:
        return self._children

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def owner(self) -> LayoutOwner | None:
        return self._owner

    def add_child(self, child: LayoutNode) -> None:
        self.insert_child(len(self._children), child)

    def insert_child(self, index: int, child: LayoutNode) -> None:
        if child._parent is not None:
            raise ValueError("node already has a parent; remove it first")
        child._parent = self
        child._set_depth(self._depth + 1)
        if self._owner is not None:
            child._attach(self._owner)
        self._children.insert(index, child)
        self.mark_needs_layout()

    def remove_child(self, child: LayoutNode) -> None:
        self._children.remove(child)
        child._parent = None
        child._relayout_boundary = None
        if child._owner is not None:
            child._detach()
        self.mark_needs_layout()

    def clear_children(self) -> None:
        """Detach every child in one pass.

        Not a loop over :meth:`remove_child` -- that does an O(n) list search
        per call, making a naive clear O(n^2) in the child count.
        """
        children, self._children = self._children, []
        for child in children:
            child._parent = None
            child._relayout_boundary = None
            if child._owner is not None:
                child._detach()
        if children:
            self.mark_needs_layout()

    def walk(self) -> Iterator[LayoutNode]:
        """Depth-first pre-order traversal including self."""
        yield self
        for child in self._children:
            yield from child.walk()

    def _set_depth(self, depth: int) -> None:
        if self._depth == depth:
            return
        self._depth = depth
        for child in self._children:
            child._set_depth(depth + 1)

    def _attach(self, owner: LayoutOwner) -> None:
        self._owner = owner
        if self._needs_layout and self._relayout_boundary is self:
            owner.schedule(self)
        for child in self._children:
            child._attach(owner)

    def _detach(self) -> None:
        self._owner = None
        for child in self._children:
            child._detach()

    def attach(self, owner: LayoutOwner) -> None:
        """Attach this subtree to *owner* so dirt can be scheduled."""
        self._attach(owner)

    # ------------------------------------------------------- invalidation

    @property
    def needs_layout(self) -> bool:
        return self._needs_layout

    @property
    def relayout_boundary(self) -> LayoutNode | None:
        return self._relayout_boundary

    @property
    def is_relayout_boundary(self) -> bool:
        return self._relayout_boundary is self

    def mark_needs_layout(self) -> None:
        """Mark dirty, propagating up only as far as the nearest boundary."""
        if self._needs_layout:
            return
        self._needs_layout = True
        if self._relayout_boundary is not self and self._parent is not None:
            self._parent.mark_needs_layout()
        elif self._owner is not None:
            self._owner.schedule(self)

    def _clean_child_relayout_boundary(self) -> None:
        """Force recomputation of stale boundaries in the subtree."""
        for child in self._children:
            if child._relayout_boundary is not child:
                child._relayout_boundary = None
                child._clean_child_relayout_boundary()

    # ------------------------------------------------------------- layout

    def layout(self, constraints: Constraints, *, parent_uses_size: bool = True) -> Size:
        """Lay out under *constraints* and return the resulting size.

        Set ``parent_uses_size=False`` when the caller ignores the returned size.
        That makes the child a relayout boundary, which is the cheapest possible
        outcome -- prefer it wherever the parent's own size does not depend on
        the child's.
        """
        boundary: LayoutNode
        if not parent_uses_size or constraints.is_tight or self._parent is None:
            boundary = self
        else:
            parent_boundary = self._parent._relayout_boundary
            boundary = parent_boundary if parent_boundary is not None else self

        if (
            not self._needs_layout
            and constraints == self._constraints
            and boundary is self._relayout_boundary
        ):
            return self._size

        self._constraints = constraints
        if boundary is not self._relayout_boundary:
            self._relayout_boundary = boundary
            self._clean_child_relayout_boundary()

        self._size = self.perform_layout(constraints)
        self._needs_layout = False

        if __debug__ and not constraints.is_satisfied_by(self._size):
            raise AssertionError(
                f"{type(self).__name__}.perform_layout returned {self._size} "
                f"which violates {constraints}"
            )
        return self._size

    def _layout_without_resize(self) -> None:
        """Relayout a boundary in place. Its size cannot change, so the parent
        needs no notification -- this is what makes subtree relayout valid."""
        assert self._constraints is not None
        assert self._relayout_boundary is self
        self._size = self.perform_layout(self._constraints)
        self._needs_layout = False

        if __debug__ and not self._constraints.is_satisfied_by(self._size):
            raise AssertionError(
                f"{type(self).__name__}.perform_layout returned {self._size} "
                f"which violates {self._constraints}"
            )

    @abstractmethod
    def perform_layout(self, constraints: Constraints) -> Size:
        """Choose a size satisfying *constraints*, laying out and positioning
        children. Must not read :attr:`offset` or the parent's size."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} size={self._size} offset={self._offset}>"


class LeafNode(LayoutNode):
    """A childless node with a preferred size, clamped to its constraints."""

    __slots__ = ("_preferred",)

    def __init__(self, width: float = 0.0, height: float = 0.0) -> None:
        super().__init__()
        self._preferred = Size(width, height)

    @property
    def preferred(self) -> Size:
        return self._preferred

    @preferred.setter
    def preferred(self, value: Size) -> None:
        if value != self._preferred:
            self._preferred = value
            self.mark_needs_layout()

    def perform_layout(self, constraints: Constraints) -> Size:
        return constraints.constrain(self._preferred)
