"""Concrete layout algorithms.

Every node here obeys the invariant in :mod:`pysilver.layout.node`: its size is a
function of its constraints and its children only. Each passes
``parent_uses_size=False`` wherever it genuinely ignores a child's size, since
that promotes the child to a relayout boundary and stops dirt propagating.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from .constraints import (
    ALIGN_CENTER,
    ALIGN_TOP_LEFT,
    EDGE_ZERO,
    INF,
    Alignment,
    Constraints,
    EdgeInsets,
    Offset,
    Size,
)
from .node import LayoutNode

__all__ = [
    "Align",
    "Axis",
    "Center",
    "ConstrainedBox",
    "CrossAxisAlignment",
    "Flex",
    "FlexFit",
    "Flexible",
    "Horizontal",
    "MainAxisAlignment",
    "MainAxisSize",
    "Padding",
    "SingleChildNode",
    "SizedBox",
    "Spacer",
    "Stack",
    "Vertical",
]


class Axis(Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class MainAxisAlignment(Enum):
    START = "start"
    END = "end"
    CENTER = "center"
    SPACE_BETWEEN = "space_between"
    SPACE_AROUND = "space_around"
    SPACE_EVENLY = "space_evenly"


class CrossAxisAlignment(Enum):
    START = "start"
    END = "end"
    CENTER = "center"
    STRETCH = "stretch"


class MainAxisSize(Enum):
    MAX = "max"
    MIN = "min"


class FlexFit(Enum):
    TIGHT = "tight"
    LOOSE = "loose"


# ------------------------------------------------------------ single child


class SingleChildNode(LayoutNode):
    """Base for nodes wrapping exactly one child."""

    __slots__ = ()

    def __init__(self, child: LayoutNode | None = None) -> None:
        super().__init__([child] if child is not None else [])

    def insert_child(self, index: int, child: LayoutNode) -> None:
        """Reject a second child rather than silently dropping it.

        A single-child node lays out only ``children[0]`` but paint walks all
        of them, so extra children would render unpositioned on top of each
        other -- visible as overlapping content with no error anywhere.
        """
        if self._children:
            raise ValueError(
                f"{type(self).__name__} takes a single child; "
                "wrap several in a Horizontal or Vertical"
            )
        super().insert_child(index, child)

    @property
    def child(self) -> LayoutNode | None:
        return self._children[0] if self._children else None

    def set_child(self, child: LayoutNode | None) -> None:
        self.clear_children()
        if child is not None:
            self.add_child(child)


class Padding(SingleChildNode):
    """Insets a child. Size is the child's size inflated by the padding."""

    __slots__ = ("_padding",)

    def __init__(self, child: LayoutNode | None = None, padding: EdgeInsets = EDGE_ZERO) -> None:
        super().__init__(child)
        self._padding = padding

    @property
    def padding(self) -> EdgeInsets:
        return self._padding

    @padding.setter
    def padding(self, value: EdgeInsets) -> None:
        if value != self._padding:
            self._padding = value
            self.mark_needs_layout()

    def perform_layout(self, constraints: Constraints) -> Size:
        child = self.child
        if child is None:
            return constraints.constrain(Size(self._padding.horizontal, self._padding.vertical))
        inner = child.layout(constraints.deflate(self._padding))
        child.offset = self._padding.top_left
        return constraints.constrain(inner.inflate(self._padding))


class Align(SingleChildNode):
    """Positions a child within itself.

    With no size factor the node fills its constraints, so the child's size does
    not affect its own -- the child becomes a relayout boundary.
    """

    __slots__ = ("_alignment", "_height_factor", "_width_factor")

    def __init__(
        self,
        child: LayoutNode | None = None,
        alignment: Alignment = ALIGN_CENTER,
        *,
        width_factor: float | None = None,
        height_factor: float | None = None,
    ) -> None:
        super().__init__(child)
        self._alignment = alignment
        self._width_factor = width_factor
        self._height_factor = height_factor

    @property
    def alignment(self) -> Alignment:
        return self._alignment

    @alignment.setter
    def alignment(self, value: Alignment) -> None:
        if value != self._alignment:
            self._alignment = value
            self.mark_needs_layout()

    def perform_layout(self, constraints: Constraints) -> Size:
        shrink_w = self._width_factor is not None or not constraints.has_bounded_width
        shrink_h = self._height_factor is not None or not constraints.has_bounded_height

        child = self.child
        if child is None:
            return constraints.constrain(Size(0.0 if shrink_w else INF, 0.0 if shrink_h else INF))

        uses_size = shrink_w or shrink_h
        child_size = child.layout(constraints.loosen(), parent_uses_size=uses_size)

        size = constraints.constrain(
            Size(
                child_size.width * (self._width_factor or 1.0) if shrink_w else INF,
                child_size.height * (self._height_factor or 1.0) if shrink_h else INF,
            )
        )
        child.offset = self._alignment.resolve(child_size, size)
        return size


class Center(Align):
    """:class:`Align` with centre alignment."""

    __slots__ = ()

    def __init__(self, child: LayoutNode | None = None, **kw: float | None) -> None:
        super().__init__(child, ALIGN_CENTER, **kw)


class SizedBox(SingleChildNode):
    """Forces a specific size on its child. ``None`` means "leave that axis alone"."""

    __slots__ = ("_height", "_width")

    def __init__(
        self,
        child: LayoutNode | None = None,
        *,
        width: float | None = None,
        height: float | None = None,
    ) -> None:
        super().__init__(child)
        self._width = width
        self._height = height

    def perform_layout(self, constraints: Constraints) -> Size:
        inner = constraints.tighten(width=self._width, height=self._height)
        child = self.child
        if child is None:
            return inner.constrain(inner.smallest)
        # Tight in both axes means the child's size cannot influence ours.
        child.layout(inner, parent_uses_size=not inner.is_tight)
        return inner.constrain(child.size if not inner.is_tight else inner.smallest)


class ConstrainedBox(SingleChildNode):
    """Applies additional constraints, clamped inside those from the parent."""

    __slots__ = ("_extra",)

    def __init__(self, child: LayoutNode | None = None, *, extra: Constraints) -> None:
        super().__init__(child)
        self._extra = extra

    def perform_layout(self, constraints: Constraints) -> Size:
        inner = self._extra.enforce(constraints)
        child = self.child
        if child is None:
            return inner.constrain(inner.smallest)
        # Tight in both axes means the child's size cannot influence ours.
        size = child.layout(inner, parent_uses_size=not inner.is_tight)
        return constraints.constrain(size if not inner.is_tight else inner.smallest)


# -------------------------------------------------------------------- flex


class Flexible(SingleChildNode):
    """Marks a child as flexible along the main axis of its :class:`Flex` parent.

    ``FlexFit.TIGHT`` forces the child to exactly its share (an "expanded" child);
    ``FlexFit.LOOSE`` lets it be smaller.
    """

    __slots__ = ("_fit", "_flex")

    def __init__(
        self,
        child: LayoutNode | None = None,
        *,
        flex: int = 1,
        fit: FlexFit = FlexFit.TIGHT,
    ) -> None:
        if flex < 0:
            raise ValueError(f"flex must be non-negative, got {flex}")
        super().__init__(child)
        self._flex = flex
        self._fit = fit

    @property
    def flex(self) -> int:
        return self._flex

    @property
    def fit(self) -> FlexFit:
        return self._fit

    def perform_layout(self, constraints: Constraints) -> Size:
        child = self.child
        if child is None:
            return constraints.smallest
        return constraints.constrain(child.layout(constraints))


class Spacer(Flexible):
    """Flexible empty space."""

    __slots__ = ()

    def __init__(self, flex: int = 1) -> None:
        super().__init__(None, flex=flex, fit=FlexFit.TIGHT)


def _flex_of(node: LayoutNode) -> int:
    return node.flex if isinstance(node, Flexible) else 0


def _fit_of(node: LayoutNode) -> FlexFit:
    return node.fit if isinstance(node, Flexible) else FlexFit.TIGHT


class Flex(LayoutNode):
    """Lays children along an axis, distributing free space to flexible ones.

    Two sub-passes: inflexible children are measured first against the full
    available space, then whatever remains is divided among flexible children by
    weight. This is O(n) -- no solver, no iteration to convergence.
    """

    __slots__ = (
        "_axis",
        "_cross_alignment",
        "_main_alignment",
        "_main_size",
        "_spacing",
    )

    def __init__(
        self,
        children: Sequence[LayoutNode] = (),
        *,
        axis: Axis = Axis.HORIZONTAL,
        main_alignment: MainAxisAlignment = MainAxisAlignment.START,
        cross_alignment: CrossAxisAlignment = CrossAxisAlignment.START,
        main_size: MainAxisSize = MainAxisSize.MAX,
        spacing: float = 0.0,
    ) -> None:
        super().__init__(children)
        self._axis = axis
        self._main_alignment = main_alignment
        self._cross_alignment = cross_alignment
        self._main_size = main_size
        self._spacing = spacing

    # --- axis helpers -------------------------------------------------

    @property
    def axis(self) -> Axis:
        return self._axis

    def _main(self, size: Size) -> float:
        return size.width if self._axis is Axis.HORIZONTAL else size.height

    def _cross(self, size: Size) -> float:
        return size.height if self._axis is Axis.HORIZONTAL else size.width

    def _size_for(self, main: float, cross: float) -> Size:
        return Size(main, cross) if self._axis is Axis.HORIZONTAL else Size(cross, main)

    def _offset_for(self, main: float, cross: float) -> Offset:
        return Offset(main, cross) if self._axis is Axis.HORIZONTAL else Offset(cross, main)

    def _max_main(self, c: Constraints) -> float:
        return c.max_width if self._axis is Axis.HORIZONTAL else c.max_height

    def _max_cross(self, c: Constraints) -> float:
        return c.max_height if self._axis is Axis.HORIZONTAL else c.max_width

    def _min_cross(self, c: Constraints) -> float:
        return c.min_height if self._axis is Axis.HORIZONTAL else c.min_width

    def _child_constraints(
        self, min_main: float, max_main: float, constraints: Constraints
    ) -> Constraints:
        stretch = self._cross_alignment is CrossAxisAlignment.STRETCH
        max_cross = self._max_cross(constraints)
        min_cross = max_cross if stretch else 0.0
        if stretch and max_cross == INF:
            min_cross = 0.0
        if self._axis is Axis.HORIZONTAL:
            return Constraints(min_main, max_main, min_cross, max_cross)
        return Constraints(min_cross, max_cross, min_main, max_main)

    # --- flex participation -------------------------------------------

    def flex_of(self, child: LayoutNode) -> int:
        """Flex weight of *child*. Overridden by widgets to read their spec."""
        return _flex_of(child)

    def fit_of(self, child: LayoutNode) -> FlexFit:
        return _fit_of(child)

    # --- layout -------------------------------------------------------

    def perform_layout(self, constraints: Constraints) -> Size:
        max_main = self._max_main(constraints)
        # `flex_of` is a widget-overridable hook (a StyleSpec attribute read,
        # not a cheap field access), so it's computed once per child here
        # rather than up to three times across the two passes below.
        child_flex = [(c, self.flex_of(c)) for c in self._children]
        total_flex = sum(flex for _, flex in child_flex)
        gaps = self._spacing * max(0, len(self._children) - 1)

        if total_flex > 0 and max_main == INF:
            raise ValueError(
                f"{type(self).__name__} has flexible children but unbounded "
                f"{self._axis.value} space; give it a bounded size or remove the flex"
            )

        # Pass 1 -- inflexible children against all available space.
        allocated = 0.0
        max_cross_seen = 0.0
        for child, flex in child_flex:
            if flex > 0:
                continue
            size = child.layout(
                self._child_constraints(
                    0.0,
                    INF if max_main == INF else max(0.0, max_main - allocated - gaps),
                    constraints,
                )
            )
            allocated += self._main(size)
            max_cross_seen = max(max_cross_seen, self._cross(size))

        # Pass 2 -- divide the remainder among flexible children by weight.
        free = max(0.0, max_main - allocated - gaps) if max_main != INF else 0.0
        remaining = free
        flex_seen = 0
        for child, flex in child_flex:
            if flex == 0:
                continue
            flex_seen += flex
            # Distribute by running total so rounding never loses a pixel.
            share = (free * flex_seen / total_flex) - (free - remaining)
            remaining -= share
            tight = self.fit_of(child) is FlexFit.TIGHT
            size = child.layout(
                self._child_constraints(share if tight else 0.0, share, constraints)
            )
            allocated += self._main(size)
            max_cross_seen = max(max_cross_seen, self._cross(size))

        # Own size.
        content_main = allocated + gaps
        main = max_main if self._main_size is MainAxisSize.MAX and max_main != INF else content_main
        cross = max(max_cross_seen, self._min_cross(constraints))
        size = constraints.constrain(self._size_for(main, cross))

        self._position_children(size, content_main)
        return size

    def _position_children(self, size: Size, content_main: float) -> None:
        main_extent = self._main(size)
        cross_extent = self._cross(size)
        slack = max(0.0, main_extent - content_main)
        n = len(self._children)

        lead, between = 0.0, self._spacing
        match self._main_alignment:
            case MainAxisAlignment.START:
                pass
            case MainAxisAlignment.END:
                lead = slack
            case MainAxisAlignment.CENTER:
                lead = slack / 2
            case MainAxisAlignment.SPACE_BETWEEN:
                between += slack / (n - 1) if n > 1 else 0.0
            case MainAxisAlignment.SPACE_AROUND:
                unit = slack / n if n else 0.0
                lead = unit / 2
                between += unit
            case MainAxisAlignment.SPACE_EVENLY:
                unit = slack / (n + 1) if n else 0.0
                lead = unit
                between += unit

        cursor = lead
        for i, child in enumerate(self._children):
            child_main = self._main(child.size)
            child_cross = self._cross(child.size)
            match self._cross_alignment:
                case CrossAxisAlignment.START | CrossAxisAlignment.STRETCH:
                    cross_pos = 0.0
                case CrossAxisAlignment.END:
                    cross_pos = cross_extent - child_cross
                case CrossAxisAlignment.CENTER:
                    cross_pos = (cross_extent - child_cross) / 2
            child.offset = self._offset_for(cursor, cross_pos)
            cursor += child_main
            if i < n - 1:
                cursor += between


class Horizontal(Flex):
    """Horizontal :class:`Flex`."""

    __slots__ = ()

    def __init__(self, children: Sequence[LayoutNode] = (), **kw: object) -> None:
        super().__init__(children, axis=Axis.HORIZONTAL, **kw)  # type: ignore[arg-type]


class Vertical(Flex):
    """Vertical :class:`Flex`."""

    __slots__ = ()

    def __init__(self, children: Sequence[LayoutNode] = (), **kw: object) -> None:
        super().__init__(children, axis=Axis.VERTICAL, **kw)  # type: ignore[arg-type]


# ------------------------------------------------------------------- stack


class Stack(LayoutNode):
    """Overlays children. Paint order is child order; last child is on top."""

    __slots__ = ("_alignment", "_expand")

    def __init__(
        self,
        children: Sequence[LayoutNode] = (),
        *,
        alignment: Alignment = ALIGN_TOP_LEFT,
        expand: bool = False,
    ) -> None:
        super().__init__(children)
        self._alignment = alignment
        self._expand = expand

    def perform_layout(self, constraints: Constraints) -> Size:
        if not self._children:
            return constraints.constrain(
                Size(
                    constraints.max_width if constraints.has_bounded_width else 0.0,
                    constraints.max_height if constraints.has_bounded_height else 0.0,
                )
            )

        inner = constraints if self._expand else constraints.loosen()
        width = height = 0.0
        for child in self._children:
            child_size = child.layout(inner)
            width = max(width, child_size.width)
            height = max(height, child_size.height)

        if self._expand:
            width = constraints.max_width if constraints.has_bounded_width else width
            height = constraints.max_height if constraints.has_bounded_height else height

        size = constraints.constrain(Size(width, height))
        for child in self._children:
            child.offset = self._alignment.resolve(child.size, size)
        return size
