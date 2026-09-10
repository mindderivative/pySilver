"""Geometry primitives for the layout engine.

All values are **logical** units (DIPs), never physical pixels -- the conversion
happens once, in the paint pass (ARCHITECTURE.md 7).

The central type is :class:`Constraints`, a box constraint passed *down* the tree.
A node answers with a :class:`Size` passed *up*. The parent then assigns the
child's :class:`Offset`. See ARCHITECTURE.md 5.4.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

__all__ = [
    "ALIGN_BOTTOM_CENTER",
    "ALIGN_BOTTOM_LEFT",
    "ALIGN_BOTTOM_RIGHT",
    "ALIGN_CENTER",
    "ALIGN_CENTER_LEFT",
    "ALIGN_CENTER_RIGHT",
    "ALIGN_TOP_CENTER",
    "ALIGN_TOP_LEFT",
    "ALIGN_TOP_RIGHT",
    "EDGE_ZERO",
    "INF",
    "OFFSET_ZERO",
    "SIZE_ZERO",
    "UNBOUNDED",
    "Alignment",
    "Constraints",
    "EdgeInsets",
    "Offset",
    "Rect",
    "Size",
]

INF: Final = math.inf


def _finite_nonneg(value: float, name: str) -> None:
    if value < 0 or math.isnan(value):
        raise ValueError(f"{name} must be non-negative and not NaN, got {value!r}")


# --------------------------------------------------------------------- Size


@dataclass(frozen=True, slots=True)
class Size:
    width: float = 0.0
    height: float = 0.0

    def __post_init__(self) -> None:
        if __debug__:
            _finite_nonneg(self.width, "width")
            _finite_nonneg(self.height, "height")

    @property
    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0

    @property
    def is_finite(self) -> bool:
        return math.isfinite(self.width) and math.isfinite(self.height)

    def inflate(self, edges: EdgeInsets) -> Size:
        return Size(self.width + edges.horizontal, self.height + edges.vertical)

    def deflate(self, edges: EdgeInsets) -> Size:
        return Size(max(0.0, self.width - edges.horizontal), max(0.0, self.height - edges.vertical))

    def __iter__(self) -> Iterator[float]:
        yield self.width
        yield self.height


SIZE_ZERO: Final = Size(0.0, 0.0)


# ------------------------------------------------------------------- Offset


@dataclass(frozen=True, slots=True)
class Offset:
    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: Offset) -> Offset:
        return Offset(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Offset) -> Offset:
        return Offset(self.x - other.x, self.y - other.y)

    def __iter__(self) -> Iterator[float]:
        yield self.x
        yield self.y


OFFSET_ZERO: Final = Offset(0.0, 0.0)


# --------------------------------------------------------------------- Rect


@dataclass(frozen=True, slots=True)
class Rect:
    """An absolute, axis-aligned box.

    Used for both of an element's rects: the one it paints, and the one it
    accepts clicks in. Those were the same rectangle until `hit_padding` and
    `min_hit_size` split them.
    """

    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    @classmethod
    def from_offset_size(cls, offset: Offset, size: Size) -> Rect:
        return cls(offset.x, offset.y, size.width, size.height)

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.right and self.y <= y < self.bottom

    def translate(self, offset: Offset) -> Rect:
        return Rect(self.x + offset.x, self.y + offset.y, self.width, self.height)

    def intersect(self, other: Rect) -> Rect:
        x = max(self.x, other.x)
        y = max(self.y, other.y)
        return Rect(
            x,
            y,
            max(0.0, min(self.right, other.right) - x),
            max(0.0, min(self.bottom, other.bottom) - y),
        )


# --------------------------------------------------------------- EdgeInsets


@dataclass(frozen=True, slots=True)
class EdgeInsets:
    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0

    @classmethod
    def all(cls, value: float) -> EdgeInsets:
        return cls(value, value, value, value)

    @classmethod
    def symmetric(cls, *, horizontal: float = 0.0, vertical: float = 0.0) -> EdgeInsets:
        return cls(horizontal, vertical, horizontal, vertical)

    @classmethod
    def zero(cls) -> EdgeInsets:
        return EDGE_ZERO

    @property
    def horizontal(self) -> float:
        return self.left + self.right

    @property
    def vertical(self) -> float:
        return self.top + self.bottom

    @property
    def top_left(self) -> Offset:
        return Offset(self.left, self.top)


EDGE_ZERO: Final = EdgeInsets()


# ---------------------------------------------------------------- Alignment


@dataclass(frozen=True, slots=True)
class Alignment:
    """Fractional alignment: 0.0 = start, 0.5 = centre, 1.0 = end."""

    x: float = 0.5
    y: float = 0.5

    def resolve(self, child: Size, parent: Size) -> Offset:
        """Offset placing *child* within *parent*. Never negative-clamped --
        an oversized child overflows symmetrically, which is debuggable."""
        return Offset(
            (parent.width - child.width) * self.x,
            (parent.height - child.height) * self.y,
        )


#: Canonical alignments. Module-level rather than class attributes so they are
#: usable as default arguments without tripping mutable-default lints.
ALIGN_TOP_LEFT: Final = Alignment(0.0, 0.0)
ALIGN_TOP_CENTER: Final = Alignment(0.5, 0.0)
ALIGN_TOP_RIGHT: Final = Alignment(1.0, 0.0)
ALIGN_CENTER_LEFT: Final = Alignment(0.0, 0.5)
ALIGN_CENTER: Final = Alignment(0.5, 0.5)
ALIGN_CENTER_RIGHT: Final = Alignment(1.0, 0.5)
ALIGN_BOTTOM_LEFT: Final = Alignment(0.0, 1.0)
ALIGN_BOTTOM_CENTER: Final = Alignment(0.5, 1.0)
ALIGN_BOTTOM_RIGHT: Final = Alignment(1.0, 1.0)


# -------------------------------------------------------------- Constraints


@dataclass(frozen=True, slots=True)
class Constraints:
    """An immutable box constraint. ``max_*`` may be ``inf``; ``min_*`` may not."""

    min_width: float = 0.0
    max_width: float = INF
    min_height: float = 0.0
    max_height: float = INF

    def __post_init__(self) -> None:
        if __debug__:
            _finite_nonneg(self.min_width, "min_width")
            _finite_nonneg(self.min_height, "min_height")
            if math.isnan(self.max_width) or math.isnan(self.max_height):
                raise ValueError("max constraints must not be NaN")
            if self.min_width > self.max_width:
                raise ValueError(f"min_width {self.min_width} > max_width {self.max_width}")
            if self.min_height > self.max_height:
                raise ValueError(f"min_height {self.min_height} > max_height {self.max_height}")

    # -------------------------------------------------------- constructors

    @classmethod
    def tight(cls, size: Size) -> Constraints:
        return cls(size.width, size.width, size.height, size.height)

    @classmethod
    def tight_for(cls, *, width: float | None = None, height: float | None = None) -> Constraints:
        return cls(
            width if width is not None else 0.0,
            width if width is not None else INF,
            height if height is not None else 0.0,
            height if height is not None else INF,
        )

    @classmethod
    def loose(cls, size: Size) -> Constraints:
        return cls(0.0, size.width, 0.0, size.height)

    @classmethod
    def unbounded(cls) -> Constraints:
        return UNBOUNDED

    @classmethod
    def expand(cls, *, width: float | None = None, height: float | None = None) -> Constraints:
        w = width if width is not None else INF
        h = height if height is not None else INF
        return cls(w, w, h, h)

    # ------------------------------------------------------------ queries

    @property
    def is_tight(self) -> bool:
        """Tight in *both* axes -- the condition for a relayout boundary."""
        return self.min_width >= self.max_width and self.min_height >= self.max_height

    @property
    def is_tight_width(self) -> bool:
        return self.min_width >= self.max_width

    @property
    def is_tight_height(self) -> bool:
        return self.min_height >= self.max_height

    @property
    def has_bounded_width(self) -> bool:
        return self.max_width < INF

    @property
    def has_bounded_height(self) -> bool:
        return self.max_height < INF

    @property
    def smallest(self) -> Size:
        return Size(self.min_width, self.min_height)

    @property
    def biggest(self) -> Size:
        """Largest permitted size. Only meaningful when both axes are bounded."""
        return Size(self.max_width, self.max_height)

    def is_satisfied_by(self, size: Size) -> bool:
        return (
            self.min_width <= size.width <= self.max_width
            and self.min_height <= size.height <= self.max_height
        )

    # ---------------------------------------------------------- operations

    def constrain_width(self, width: float = INF) -> float:
        return max(self.min_width, min(self.max_width, width))

    def constrain_height(self, height: float = INF) -> float:
        return max(self.min_height, min(self.max_height, height))

    def constrain(self, size: Size) -> Size:
        """Clamp *size* into this box. The only sanctioned way to produce a size."""
        return Size(self.constrain_width(size.width), self.constrain_height(size.height))

    def deflate(self, edges: EdgeInsets) -> Constraints:
        """Shrink by *edges* -- what a padding widget passes to its child."""
        h, v = edges.horizontal, edges.vertical
        max_w = max(0.0, self.max_width - h) if self.has_bounded_width else INF
        max_h = max(0.0, self.max_height - v) if self.has_bounded_height else INF
        return Constraints(
            min(max(0.0, self.min_width - h), max_w),
            max_w,
            min(max(0.0, self.min_height - v), max_h),
            max_h,
        )

    def loosen(self) -> Constraints:
        """Drop the minimums. A child may then be smaller than its parent."""
        return Constraints(0.0, self.max_width, 0.0, self.max_height)

    def tighten(self, *, width: float | None = None, height: float | None = None) -> Constraints:
        w = self.constrain_width(width) if width is not None else None
        h = self.constrain_height(height) if height is not None else None
        return Constraints(
            w if w is not None else self.min_width,
            w if w is not None else self.max_width,
            h if h is not None else self.min_height,
            h if h is not None else self.max_height,
        )

    def enforce(self, other: Constraints) -> Constraints:
        """Clamp this constraint inside *other*."""
        max_w = max(other.min_width, min(other.max_width, self.max_width))
        max_h = max(other.min_height, min(other.max_height, self.max_height))
        return Constraints(
            max(other.min_width, min(other.max_width, self.min_width)),
            max_w,
            max(other.min_height, min(other.max_height, self.min_height)),
            max_h,
        )

    def copy_with(
        self,
        *,
        min_width: float | None = None,
        max_width: float | None = None,
        min_height: float | None = None,
        max_height: float | None = None,
    ) -> Constraints:
        return Constraints(
            self.min_width if min_width is None else min_width,
            self.max_width if max_width is None else max_width,
            self.min_height if min_height is None else min_height,
            self.max_height if max_height is None else max_height,
        )


UNBOUNDED: Final = Constraints(0.0, INF, 0.0, INF)
