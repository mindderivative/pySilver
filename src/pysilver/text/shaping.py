"""Shaping: text plus a face becomes positioned glyph ids.

HarfBuzz applies ``GSUB`` (ligatures, contextual forms) and ``GPOS`` (real
kerning, mark attachment). This is the step freetype cannot do -- freetype only
exposes the legacy ``kern`` table, which modern fonts do not use.

Output is numpy from the start so the paint pass can write instances in bulk
(ARCHITECTURE.md 12): a per-glyph Python loop will not meet the frame budget.

Shaping runs at font-unit scale, so a :class:`ShapedRun` is **size-independent**
and one cache entry serves every pixel size the same string is drawn at.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import uharfbuzz as hb

from .font import Face

__all__ = ["ShapeCache", "ShapedRun", "shape_run"]

#: Bounds `ShapeCache`. Each entry holds a `ShapedRun` (four numpy arrays) for
#: one distinct (text, face, direction, script, language, features) run -- a
#: widget whose content changes on every keystroke (TextField, CodeEditor)
#: would otherwise grow this without limit for the life of the process, the
#: same failure mode `text/__init__.py`'s `_layouts` cache is bounded against.
_DEFAULT_SHAPE_CACHE_SIZE = 512


@dataclass(frozen=True, slots=True)
class ShapedRun:
    """Positioned glyphs for one run, in font units."""

    face: Face
    text: str
    direction: str
    glyphs: np.ndarray  # uint32 glyph ids
    advances: np.ndarray  # float32, font units
    offsets: np.ndarray  # float32 (n, 2), mark positioning
    clusters: np.ndarray  # uint32, codepoint index back into `text`

    def __len__(self) -> int:
        return int(self.glyphs.shape[0])

    @property
    def width_units(self) -> float:
        return float(self.advances.sum())

    def cluster_ends(self) -> np.ndarray:
        """Mask of glyphs that *complete* a cluster.

        Tracking is added per cluster, not per glyph: a ligature is one glyph
        for several characters, and a combining mark is several glyphs for one.
        Spacing either of those apart internally would be wrong.
        """
        count = len(self)
        ends = np.ones(count, dtype=bool)
        if count > 1:
            ends[:-1] = self.clusters[1:] != self.clusters[:-1]
        return ends

    def advances_px(self, px: float, tracking: float = 0.0) -> np.ndarray:
        """Per-glyph advance in pixels at *px*, with *tracking* folded in.

        **The one place an advance is computed.** Width, caret placement,
        selection rectangles and the paint pen all read this array, so they
        cannot drift apart the way three separate copies of the arithmetic
        would -- which is exactly how a weight mismatch got in.
        """
        advances = np.asarray(self.advances, dtype=np.float64) * self.face.scale_for(px)
        if tracking:
            advances = advances + self.cluster_ends() * tracking
        return advances

    def width(self, px: float, tracking: float = 0.0) -> float:
        """Advance width in pixels at *px*."""
        return float(self.advances_px(px, tracking).sum())

    def cumulative_width(self, px: float, tracking: float = 0.0) -> np.ndarray:
        """Pen x after each glyph, in pixels. Used for caret placement."""
        return np.cumsum(self.advances_px(px, tracking))

    def slice_to_cluster(self, limit: int) -> ShapedRun:
        """The prefix of this run whose source clusters are below *limit*.

        Line breaking works in source offsets but must cut glyph arrays, and the
        two do not correspond one-to-one once ligatures merge characters --
        which is exactly why `clusters` is carried through shaping.
        """
        keep = self.clusters < limit
        return ShapedRun(
            self.face,
            self.text,
            self.direction,
            self.glyphs[keep],
            self.advances[keep],
            self.offsets[keep],
            self.clusters[keep],
        )


def shape_run(
    text: str,
    face: Face,
    *,
    direction: str = "ltr",
    script: str | None = None,
    language: str | None = None,
    features: dict[str, bool] | None = None,
) -> ShapedRun:
    """Shape *text* with *face*. Coordinates come back in font units."""
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    buf.direction = "rtl" if direction == "rtl" else "ltr"
    if script:
        buf.script = script
    if language:
        buf.language = language

    hb.shape(face.hb_font, buf, features)

    infos = buf.glyph_infos
    positions = buf.glyph_positions
    count = len(infos)
    if count == 0:
        empty_f = np.zeros((0,), dtype=np.float32)
        return ShapedRun(
            face,
            text,
            direction,
            np.zeros((0,), dtype=np.uint32),
            empty_f,
            np.zeros((0, 2), dtype=np.float32),
            np.zeros((0,), dtype=np.uint32),
        )

    glyphs = np.fromiter((i.codepoint for i in infos), dtype=np.uint32, count=count)
    clusters = np.fromiter((i.cluster for i in infos), dtype=np.uint32, count=count)
    advances = np.fromiter((p.x_advance for p in positions), dtype=np.float32, count=count)
    offset_x = np.fromiter((p.x_offset for p in positions), dtype=np.float32, count=count)
    offset_y = np.fromiter((p.y_offset for p in positions), dtype=np.float32, count=count)
    offsets = np.stack((offset_x, offset_y), axis=1)

    return ShapedRun(face, text, direction, glyphs, advances, offsets, clusters)


class ShapeCache:
    """Memoises shaped runs.

    The highest-value cache in the text stack: static labels -- most of any
    interface -- hit it on every frame after the first and cost nothing.
    """

    __slots__ = ("_hits", "_max_size", "_misses", "_store")

    def __init__(self, max_size: int = _DEFAULT_SHAPE_CACHE_SIZE) -> None:
        self._store: OrderedDict[
            tuple[str, Path, str, str | None, str | None, tuple[tuple[str, bool], ...]],
            ShapedRun,
        ] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(
        self,
        text: str,
        face: Face,
        *,
        direction: str = "ltr",
        script: str | None = None,
        language: str | None = None,
        features: dict[str, bool] | None = None,
    ) -> ShapedRun:
        key = (
            text,
            face.path,
            direction,
            script,
            language,
            tuple(sorted(features.items())) if features else (),
        )
        hit = self._store.get(key)
        if hit is not None:
            self._hits += 1
            self._store.move_to_end(key)
            return hit
        self._misses += 1
        run = shape_run(
            text, face, direction=direction, script=script, language=language, features=features
        )
        self._store[key] = run
        if len(self._store) > self._max_size:
            self._store.popitem(last=False)
        return run

    @property
    def stats(self) -> tuple[int, int]:
        """``(hits, misses)`` -- asserted on in tests, since a miss on
        unchanged text is a performance bug, not a detail."""
        return (self._hits, self._misses)

    def clear(self) -> None:
        self._store.clear()
        self._hits = self._misses = 0

    def __len__(self) -> int:
        return len(self._store)
