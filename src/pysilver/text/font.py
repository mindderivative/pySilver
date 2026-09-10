"""Font faces: metrics, coverage, and glyph rasterisation.

The division of labour that the whole text stack rests on (ARCHITECTURE.md
2.3.1): **uharfbuzz shapes, freetype rasterises**. Both libraries load the same
file and agree on glyph IDs, which is what lets the two be composed without a
translation layer.

A ``Face`` is size-independent. Sizes are supplied per call, because the same
face is used at many sizes and caching is keyed on the pair.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import freetype
import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTFont

__all__ = ["SUBPIXEL_BUCKETS", "Face", "FontMetrics", "GlyphBitmap"]

#: Horizontal subpixel positions cached per glyph. Three is the usual
#: quality/memory trade: finer spacing than whole pixels, without tripling
#: atlas pressure the way 4+ buckets would.
SUBPIXEL_BUCKETS: Final = 3

_NOTDEF: Final = 0

# Coverage gamma applied after rasterisation, compensating for disabling
# hinting (see `Face.rasterize`): an unhinted outline's flat edges (E/l/v's
# top and bottom bars) can each land at an arbitrary, independent fractional
# pixel offset, so one edge often renders as a faint single-row fade while
# the opposite edge lands almost exactly on a pixel boundary and comes out
# fully solid -- an asymmetry confirmed by dumping row-max coverage values
# for the same glyph at several sizes. Darkening partial coverage (gamma <
# 1) pulls a faint fade most of the way toward the solid edge's weight
# without moving any outline point, so curve shapes (d/g/p's bowls) are
# untouched -- verified by comparing gamma-corrected renders side by side
# with gamma=1.0 at the same size. This mirrors the "stem darkening"
# compensation other unhinted-by-default rendering stacks apply for the
# same reason.
_COVERAGE_GAMMA: Final = 0.6
_GAMMA_LUT: Final = (np.linspace(0.0, 1.0, 256) ** _COVERAGE_GAMMA * 255.0).round().astype(np.uint8)


@dataclass(frozen=True, slots=True)
class FontMetrics:
    """Vertical metrics at a specific pixel size."""

    ascent: float
    descent: float  # positive, measured downward
    line_gap: float
    units_per_em: int

    @property
    def line_height(self) -> float:
        return self.ascent + self.descent + self.line_gap

    @property
    def baseline(self) -> float:
        """Distance from the top of a line box down to the baseline."""
        return self.ascent


@dataclass(frozen=True, slots=True)
class GlyphBitmap:
    """A rasterised glyph: 8-bit coverage plus its placement offsets."""

    coverage: np.ndarray  # (rows, cols) uint8; may be empty for blanks
    left: float  # bearing from the pen position, px
    top: float  # bearing above the baseline, px

    @property
    def width(self) -> int:
        return self.coverage.shape[1] if self.coverage.size else 0

    @property
    def height(self) -> int:
        return self.coverage.shape[0] if self.coverage.size else 0

    @property
    def is_blank(self) -> bool:
        return self.coverage.size == 0


class Face:
    """One font file, loaded once for both shaping and rasterisation."""

    __slots__ = (
        "_coverage",
        "_ft",
        "_hb_face",
        "_hb_font",
        "_size_key",
        "axes",
        "family",
        "path",
        "subfamily",
        "units_per_em",
        "weight",
    )

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"font file not found: {self.path}")

        blob = hb.Blob.from_file_path(str(self.path))
        self._hb_face = hb.Face(blob)
        self._hb_font = hb.Font(self._hb_face)
        self.units_per_em = self._hb_face.upem
        # Shape in font units; converting to pixels is the caller's job, which
        # keeps ShapedRun resolution-independent and cacheable across sizes.
        self._hb_font.scale = (self.units_per_em, self.units_per_em)

        self._ft = freetype.Face(str(self.path))
        self._size_key: tuple[int, int, tuple[float, ...]] | None = None

        #: Variable axes as ``tag -> (min, default, max)``, in fvar order.
        #: Empty for a static face. Material Symbols exposes FILL and wght.
        self.axes: dict[str, tuple[float, float, float]] = {}

        tt = TTFont(self.path, lazy=True)
        if "fvar" in tt:
            self.axes = {
                a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in tt["fvar"].axes
            }
        names = {r.nameID: str(r) for r in tt["name"].names if r.platformID == 3}
        self.family = names.get(16) or names.get(1) or self.path.stem
        self.subfamily = names.get(17) or names.get(2) or "Regular"
        self.weight = int(tt["OS/2"].usWeightClass)
        tt.close()

        # Bulk coverage in one call -- building a fallback index this way avoids
        # opening every candidate font through fontTools.
        self._coverage = frozenset(self._hb_face.unicodes)

    # ------------------------------------------------------------- identity

    @property
    def hb_font(self) -> hb.Font:
        return self._hb_font

    @property
    def coverage(self) -> frozenset[int]:
        return self._coverage

    def covers(self, codepoint: int) -> bool:
        return codepoint in self._coverage

    def covers_all(self, text: str) -> bool:
        return all(ord(c) in self._coverage for c in text)

    def glyph_for(self, codepoint: int) -> int:
        """Glyph id for a codepoint, or 0 (.notdef) when unsupported."""
        return self._hb_font.get_nominal_glyph(codepoint) or _NOTDEF

    # -------------------------------------------------------------- metrics

    def scale_for(self, px: float) -> float:
        """Multiplier converting font units to pixels at *px*."""
        return float(px / self.units_per_em)

    def metrics(self, px: float) -> FontMetrics:
        self._activate(px)
        size = self._ft.size
        ascent = size.ascender / 64.0
        descent = -size.descender / 64.0
        return FontMetrics(
            ascent=ascent,
            descent=descent,
            line_gap=max(0.0, size.height / 64.0 - ascent - descent),
            units_per_em=self.units_per_em,
        )

    # -------------------------------------------------------- rasterisation

    @property
    def is_variable(self) -> bool:
        return bool(self.axes)

    def clamp_coords(self, **values: float) -> tuple[float, ...]:
        """Axis values as a tuple in fvar order, clamped to each axis range.

        Unspecified axes take their default, so ``clamp_coords(FILL=1)`` on
        Material Symbols yields ``(1.0, 400.0)``.
        """
        out = []
        for tag, (lo, default, hi) in self.axes.items():
            value = float(values.get(tag, default))
            out.append(min(hi, max(lo, value)))
        return tuple(out)

    def _activate(self, px: float, subpixel: int = 0, coords: tuple[float, ...] = ()) -> None:
        """Configure freetype for a size, subpixel offset, and axis position."""
        key = (round(px * 64), subpixel % SUBPIXEL_BUCKETS, coords)
        if key == self._size_key:
            return
        self._ft.set_char_size(key[0])
        if self.axes:
            # freetype-py takes PLAIN DESIGN VALUES here, not 16.16 fixed
            # point. Passing scaled values silently clamps every axis to its
            # maximum, which looks like "the axis does nothing".
            # Falling through to the previous coords when none are given
            # would leave a variable face stuck at whatever axis position it
            # last rendered at, since freetype doesn't reset it on its own.
            self._ft.set_var_design_coords(list(coords) if coords else list(self.clamp_coords()))
        offset = round(key[1] * 64 / SUBPIXEL_BUCKETS)
        self._ft.set_transform(freetype.Matrix(0x10000, 0, 0, 0x10000), freetype.Vector(offset, 0))
        self._size_key = key

    def rasterize(
        self,
        gid: int,
        px: float,
        subpixel: int = 0,
        coords: tuple[float, ...] = (),
    ) -> GlyphBitmap:
        """Render *gid* to an 8-bit coverage bitmap.

        Whitespace and other blank glyphs come back empty rather than as a
        zero-filled array -- the atlas must not allocate space for them.
        """
        self._activate(px, subpixel, coords)
        # FT_LOAD_NO_HINTING: default (hinted) rendering grid-fits a glyph's
        # own outline to the pixel grid before rasterising it, which for a
        # curve tangent to the baseline -- `d`/`p`/`g`'s rounded bowl bottom
        # -- snaps away the last, faint row of real antialiasing coverage
        # and visibly flattens the curve itself, worse the smaller the size
        # (confirmed directly: at 14/24/32px, FT_LOAD_NO_HINTING recovers
        # one additional row of genuine, non-noise coverage at every size,
        # and a live side-by-side render of "d" showed the hinted bowl
        # measurably flatter than the unhinted one at the same size).
        # pySilver lays out and positions text in fractional logical units
        # already (ARCHITECTURE.md 7), never snapping to the pixel grid
        # elsewhere, so grid-fitting individual glyphs here fights the rest
        # of the pipeline rather than complementing it.
        self._ft.load_glyph(gid, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        slot = self._ft.glyph
        bitmap = slot.bitmap
        if bitmap.rows == 0 or bitmap.width == 0:
            return GlyphBitmap(np.zeros((0, 0), dtype=np.uint8), 0.0, 0.0)

        buffer = np.frombuffer(bytes(bitmap.buffer), dtype=np.uint8)
        coverage = buffer.reshape(bitmap.rows, bitmap.pitch)[:, : bitmap.width]
        coverage = _GAMMA_LUT[coverage]
        return GlyphBitmap(coverage, float(slot.bitmap_left), float(slot.bitmap_top))

    def __repr__(self) -> str:
        return f"<Face {self.family!r} {self.subfamily!r} w{self.weight} {len(self._coverage)}cp>"
