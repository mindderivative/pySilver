"""The display list: a flat, painter-ordered array of GPU instances.

This is the single hand-off between the CPU-side tree and the GPU. It is a numpy
structured array rather than a list of objects, because ARCHITECTURE.md 12 makes
vectorised assembly a hard requirement -- a per-widget Python loop appending to a
list will not meet the frame budget.

Index order IS draw order. UI compositing is painter's algorithm, and with a
single instanced draw there is no depth buffer to reorder anything.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Final

import numpy as np

__all__ = [
    "INSTANCE_DTYPE",
    "INSTANCE_SIZE",
    "NO_TOKEN",
    "DisplayList",
    "Kind",
]


class Kind(IntEnum):
    """Fragment-shader branch selector, written to ``flags.x``."""

    BOX = 0
    GLYPH = 1
    IMAGE = 2
    SHADOW = 3
    ARC = 4
    POLYGON = 5
    SEGMENT = 6


#: Sentinel in ``flags.z`` / ``flags.w`` meaning "use the literal colour".
NO_TOKEN: Final = 0xFFFFFFFF

#: Must match the ``VertexIn`` instance attributes in ui.wgsl exactly.
#: Every field is vec4-aligned by construction, which sidesteps WGSL's
#: alignment rules entirely -- there is no vec3 anywhere to mis-pad.
INSTANCE_DTYPE: Final = np.dtype(
    [
        ("rect", np.float32, 4),  # x, y, w, h   physical px
        ("radii", np.float32, 4),  # tl, tr, br, bl
        ("clip", np.float32, 4),  # ancestor clip rect; w/h 0 = unclipped
        ("clip_radii", np.float32, 4),
        ("fill", np.float32, 4),  # linear RGBA (alpha = opacity multiplier)
        ("border", np.float32, 4),
        ("uv", np.float32, 4),  # u0, v0, u1, v1
        ("params", np.float32, 4),  # border_w, blur, shadow_dx, shadow_dy
        #                           # ARC: thickness, start, sweep, _
        ("flags", np.uint32, 4),  # kind, atlas, fill_token, border_token
    ]
)

INSTANCE_SIZE: Final = INSTANCE_DTYPE.itemsize  # 144 bytes

_ZERO4: Final = (0.0, 0.0, 0.0, 0.0)
_WHITE: Final = (1.0, 1.0, 1.0, 1.0)


class DisplayList:
    """A growable, reusable instance buffer.

    Capacity only ever grows, and :meth:`clear` keeps the allocation -- steady
    state performs zero allocations per frame.
    """

    __slots__ = ("_capacity", "_count", "_data")

    def __init__(self, capacity: int = 1024) -> None:
        self._capacity = max(1, capacity)
        self._data = np.zeros(self._capacity, dtype=INSTANCE_DTYPE)
        self._count = 0

    # ------------------------------------------------------------ container

    def __len__(self) -> int:
        return self._count

    @property
    def count(self) -> int:
        return self._count

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def view(self) -> np.ndarray:
        """The populated prefix. Contiguous -- upload this directly."""
        return self._data[: self._count]

    def clear(self) -> None:
        """Reset without freeing. Stale bytes past ``count`` are never read."""
        self._count = 0

    def reserve(self, additional: int) -> None:
        needed = self._count + additional
        if needed <= self._capacity:
            return
        new_capacity = self._capacity
        while new_capacity < needed:
            new_capacity *= 2
        grown = np.zeros(new_capacity, dtype=INSTANCE_DTYPE)
        grown[: self._count] = self._data[: self._count]
        self._data = grown
        self._capacity = new_capacity

    def _next(self, n: int = 1) -> np.ndarray:
        self.reserve(n)
        start = self._count
        self._count += n
        return self._data[start : start + n]

    # -------------------------------------------------------------- emitters

    def add_box(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        color: tuple[float, float, float, float] = _WHITE,
        token: int = NO_TOKEN,
        radii: tuple[float, float, float, float] = _ZERO4,
        border_width: float = 0.0,
        border_color: tuple[float, float, float, float] = _ZERO4,
        border_token: int = NO_TOKEN,
        clip: tuple[float, float, float, float] = _ZERO4,
        clip_radii: tuple[float, float, float, float] = _ZERO4,
        opacity: float = 1.0,
    ) -> int:
        """Emit a rounded box with optional border. Returns its index."""
        i = self._count
        s = self._next()[0]
        s["rect"] = (x, y, width, height)
        s["radii"] = radii
        s["clip"] = clip
        s["clip_radii"] = clip_radii
        s["fill"] = (color[0], color[1], color[2], color[3] * opacity)
        s["border"] = border_color
        s["uv"] = _ZERO4
        s["params"] = (border_width, 0.0, 0.0, 0.0)
        s["flags"] = (Kind.BOX, 0, token, border_token)
        return i

    def add_arc(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        thickness: float,
        start: float,
        sweep: float,
        color: tuple[float, float, float, float] = _WHITE,
        token: int = NO_TOKEN,
        clip: tuple[float, float, float, float] = _ZERO4,
        clip_radii: tuple[float, float, float, float] = _ZERO4,
        opacity: float = 1.0,
    ) -> int:
        """Emit a stroked circular arc inscribed in the given box.

        `start` and `sweep` are radians measured **clockwise from 12 o'clock**,
        which is the direction M3 specifies for circular progress. The arc is
        centred in the box and its radius comes from the shorter side, so a
        non-square rect still produces a circle rather than an ellipse.

        Round caps come free from the distance field -- there is no separate
        cap geometry, and a full turn takes a ring branch that avoids the seam
        a degenerate wedge test would leave at the join.
        """
        i = self._count
        s = self._next()[0]
        s["rect"] = (x, y, width, height)
        s["radii"] = _ZERO4
        s["clip"] = clip
        s["clip_radii"] = clip_radii
        s["fill"] = (color[0], color[1], color[2], color[3] * opacity)
        s["border"] = _ZERO4
        s["uv"] = _ZERO4
        s["params"] = (thickness, start, sweep, 0.0)
        s["flags"] = (Kind.ARC, 0, token, NO_TOKEN)
        return i

    def add_polygon(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        sides: float,
        rotation: float = 0.0,
        corner_radius: float = 0.0,
        color: tuple[float, float, float, float] = _WHITE,
        token: int = NO_TOKEN,
        border_width: float = 0.0,
        border_color: tuple[float, float, float, float] = _ZERO4,
        border_token: int = NO_TOKEN,
        clip: tuple[float, float, float, float] = _ZERO4,
        clip_radii: tuple[float, float, float, float] = _ZERO4,
        opacity: float = 1.0,
    ) -> int:
        """Emit a regular polygon inscribed in the given box.

        `sides` is a float rather than an int, and deliberately: the shader
        folds a sample point into one sector, so a value between two whole
        numbers is a real shape rather than a rounding error. That is what lets
        a square morph continuously into a hexagon instead of snapping.

        The polygon is inscribed in the **shorter** side, as an arc is, so a
        non-square rect gives a regular polygon rather than a stretched one.

        `rotation` is radians clockwise, matching the direction arcs measure.
        `corner_radius` rounds the vertices; at its maximum the shape becomes
        the inscribed circle.
        """
        i = self._count
        s = self._next()[0]
        s["rect"] = (x, y, width, height)
        s["radii"] = _ZERO4
        s["clip"] = clip
        s["clip_radii"] = clip_radii
        s["fill"] = (color[0], color[1], color[2], color[3] * opacity)
        s["border"] = border_color
        s["uv"] = _ZERO4
        s["params"] = (border_width, sides, rotation, corner_radius)
        s["flags"] = (Kind.POLYGON, 0, token, border_token)
        return i

    def add_segment(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        thickness: float,
        color: tuple[float, float, float, float] = _WHITE,
        token: int = NO_TOKEN,
        clip: tuple[float, float, float, float] = _ZERO4,
        clip_radii: tuple[float, float, float, float] = _ZERO4,
        opacity: float = 1.0,
    ) -> int:
        """Emit a capsule -- a line segment with round caps -- from one point to another.

        Round caps come free from the distance field, the same way `add_arc`'s
        do: subtracting a radius rounds every point on the segment uniformly,
        so the ends need no extra geometry. `thickness` is the capsule's own
        full width, matching `add_arc`'s convention -- not a border added to
        something else, which is why there is no separate `border_*` here.

        The instance's `rect` is the tight bounding box of the capsule (both
        endpoints, expanded by the radius); the endpoints themselves travel in
        `radii`, relative to that box's centre, since a stroke has no corners
        to need per-corner radii for.
        """
        r = thickness * 0.5
        min_x = min(x1, x2) - r
        min_y = min(y1, y2) - r
        width = max(x1, x2) + r - min_x
        height = max(y1, y2) + r - min_y
        cx = min_x + width * 0.5
        cy = min_y + height * 0.5
        i = self._count
        s = self._next()[0]
        s["rect"] = (min_x, min_y, width, height)
        s["radii"] = (x1 - cx, y1 - cy, x2 - cx, y2 - cy)
        s["clip"] = clip
        s["clip_radii"] = clip_radii
        s["fill"] = (color[0], color[1], color[2], color[3] * opacity)
        s["border"] = _ZERO4
        s["uv"] = _ZERO4
        s["params"] = (thickness, 0.0, 0.0, 0.0)
        s["flags"] = (Kind.SEGMENT, 0, token, NO_TOKEN)
        return i

    def add_shadow(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        blur: float,
        offset: tuple[float, float] = (0.0, 0.0),
        color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.3),
        token: int = NO_TOKEN,
        radii: tuple[float, float, float, float] = _ZERO4,
        clip: tuple[float, float, float, float] = _ZERO4,
        clip_radii: tuple[float, float, float, float] = _ZERO4,
    ) -> int:
        """Emit a shadow. Must be emitted BEFORE the box it sits behind."""
        i = self._count
        s = self._next()[0]
        s["rect"] = (x, y, width, height)
        s["radii"] = radii
        s["clip"] = clip
        s["clip_radii"] = clip_radii
        s["fill"] = color
        s["border"] = _ZERO4
        s["uv"] = _ZERO4
        s["params"] = (0.0, blur, offset[0], offset[1])
        s["flags"] = (Kind.SHADOW, 0, token, NO_TOKEN)
        return i

    def add_glyph(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        uv: tuple[float, float, float, float],
        color: tuple[float, float, float, float] = _WHITE,
        token: int = NO_TOKEN,
        clip: tuple[float, float, float, float] = _ZERO4,
        clip_radii: tuple[float, float, float, float] = _ZERO4,
    ) -> int:
        """Emit a glyph quad sampling the R8 coverage atlas."""
        i = self._count
        s = self._next()[0]
        s["rect"] = (x, y, width, height)
        s["radii"] = _ZERO4
        s["clip"] = clip
        s["clip_radii"] = clip_radii
        s["fill"] = color
        s["border"] = _ZERO4
        s["uv"] = uv
        s["params"] = _ZERO4
        s["flags"] = (Kind.GLYPH, 0, token, NO_TOKEN)
        return i

    def add_image(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        uv: tuple[float, float, float, float],
        tint: tuple[float, float, float, float] = _WHITE,
        radii: tuple[float, float, float, float] = _ZERO4,
        clip: tuple[float, float, float, float] = _ZERO4,
        clip_radii: tuple[float, float, float, float] = _ZERO4,
    ) -> int:
        """Emit an image quad sampling the RGBA atlas. Colour emoji use this."""
        i = self._count
        s = self._next()[0]
        s["rect"] = (x, y, width, height)
        s["radii"] = radii
        s["clip"] = clip
        s["clip_radii"] = clip_radii
        s["fill"] = tint
        s["border"] = _ZERO4
        s["uv"] = uv
        s["params"] = _ZERO4
        s["flags"] = (Kind.IMAGE, 0, NO_TOKEN, NO_TOKEN)
        return i

    # ----------------------------------------------------------- bulk / cache

    def extend(self, instances: np.ndarray) -> int:
        """Splice a prebuilt slice in. This is how cached subtrees are reused --
        no per-widget Python, just a memcpy."""
        if instances.dtype != INSTANCE_DTYPE:
            raise TypeError(f"expected {INSTANCE_DTYPE!r}, got {instances.dtype!r}")
        start = self._count
        self._next(len(instances))[:] = instances
        return start

    def add_boxes(
        self,
        rects: np.ndarray,
        *,
        colors: np.ndarray | None = None,
        tokens: np.ndarray | None = None,
        radii: np.ndarray | None = None,
    ) -> int:
        """Vectorised emission of N boxes from an (N, 4) rect array."""
        rects = np.asarray(rects, dtype=np.float32)
        if rects.ndim != 2 or rects.shape[1] != 4:
            raise ValueError(f"rects must be (N, 4), got {rects.shape}")
        n = len(rects)
        start = self._count
        s = self._next(n)
        s["rect"] = rects
        s["radii"] = 0.0 if radii is None else radii
        s["clip"] = 0.0
        s["clip_radii"] = 0.0
        s["fill"] = _WHITE if colors is None else colors
        s["border"] = 0.0
        s["uv"] = 0.0
        s["params"] = 0.0
        s["flags"][:, 0] = Kind.BOX
        s["flags"][:, 1] = 0
        s["flags"][:, 2] = NO_TOKEN if tokens is None else tokens
        s["flags"][:, 3] = NO_TOKEN
        return start

    def add_glyphs(
        self,
        rects: np.ndarray,
        uvs: np.ndarray,
        *,
        color: tuple[float, float, float, float] = _WHITE,
        token: int = NO_TOKEN,
        colors: np.ndarray | None = None,
        tokens: np.ndarray | None = None,
        clip: tuple[float, float, float, float] = _ZERO4,
        clip_radii: tuple[float, float, float, float] = _ZERO4,
    ) -> int:
        """Vectorised emission of N glyph quads.

        The scalar :meth:`add_glyph` costs roughly 4 microseconds per glyph,
        which exceeds the text budget at around 400 glyphs. Writing whole
        columns at once is the same rule §12 states for boxes.

        Pass `colors` (N, 4) or `tokens` (N,) to colour glyphs individually --
        what syntax highlighting and ANSI need. A palette `token` themes with
        the rest of the interface; a literal colour does not, which is the
        right trade only when the colour is genuinely fixed, as an ANSI
        sequence's is.
        """
        rects = np.asarray(rects, dtype=np.float32)
        uvs = np.asarray(uvs, dtype=np.float32)
        if rects.ndim != 2 or rects.shape[1] != 4:
            raise ValueError(f"rects must be (N, 4), got {rects.shape}")
        if uvs.shape != rects.shape:
            raise ValueError(f"uvs must match rects, got {uvs.shape} vs {rects.shape}")

        n = len(rects)
        start = self._count
        s = self._next(n)
        s["rect"] = rects
        s["uv"] = uvs
        s["radii"] = 0.0
        s["clip"] = clip
        s["clip_radii"] = clip_radii
        # `colors` and `tokens` are per glyph; the scalars are the whole run.
        # Both go through the same column write, so a syntax-highlighted line
        # costs exactly what a monochrome one does.
        s["fill"] = color if colors is None else colors
        s["border"] = 0.0
        s["params"] = 0.0
        s["flags"][:, 0] = Kind.GLYPH
        s["flags"][:, 1] = 0
        s["flags"][:, 2] = token if tokens is None else tokens
        s["flags"][:, 3] = NO_TOKEN
        return start

    def snapshot(self, start: int, end: int | None = None) -> np.ndarray:
        """Copy a range out for subtree caching."""
        return self._data[start : self._count if end is None else end].copy()
