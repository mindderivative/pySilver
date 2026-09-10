"""Text: shaping, segmentation, fallback, and glyph rasterisation.

`TextEngine` is the facade the rest of the framework uses. It owns the three
caches that make text affordable per frame (ARCHITECTURE.md 5.7.4): shaped
runs, paragraph layouts, and rasterised glyphs in the atlas.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Sequence
from typing import Any, Final

import numpy as np

from ..layout import Size
from ..paint import NO_TOKEN, DisplayList
from ..render.atlas import GlyphAtlas
from .font import SUBPIXEL_BUCKETS, Face, FontMetrics, GlyphBitmap
from .fontdb import FontDB, FontRequest
from .icons import DEFAULT_ICON_SIZE, IconSet
from .itemize import Direction, ItemRun, itemize
from .layout import Alignment, GlyphPlacement, Paragraph, TextLine, layout_text
from .segment import break_opportunities, cluster_boundaries, clusters
from .shaping import ShapeCache, ShapedRun, shape_run
from .svgicons import compile_svg_font, load_svg_icons

__all__ = [
    "DEFAULT_ICON_SIZE",
    "SUBPIXEL_BUCKETS",
    "Alignment",
    "Direction",
    "Face",
    "FontDB",
    "FontMetrics",
    "FontRequest",
    "GlyphBitmap",
    "GlyphPlacement",
    "IconSet",
    "ItemRun",
    "Paragraph",
    "ShapeCache",
    "ShapedRun",
    "TextEngine",
    "TextLine",
    "break_opportunities",
    "cluster_boundaries",
    "clusters",
    "compile_svg_font",
    "itemize",
    "layout_text",
    "load_svg_icons",
    "shape_run",
]

_NO_CLIP = (0.0, 0.0, 0.0, 0.0)

# Bounds `TextEngine._layouts`. Every entry holds a fully shaped `Paragraph`,
# and the key embeds the whole text string, so a widget whose content
# changes on every keystroke (TextField, CodeEditor) would otherwise grow
# this cache without limit for the life of the process (ARCHITECTURE.md
# 5.25). Static UI text -- the common case this cache exists for -- rarely
# has more than a few hundred distinct (text, style) combinations on screen
# at once, so this ceiling doesn't touch that case in practice.
_DEFAULT_LAYOUT_CACHE_SIZE = 512

# Rounds a bounded `max_width` up to the nearest multiple before it is used as
# part of the layout cache key (and as the width actually handed to the
# shaper). A widget whose wrap width tracks a live window size -- any `Text`
# under a `cross_alignment: stretch` column, say -- gets a fresh `max_width`
# on nearly every pixel of a resize drag, and the cache key embeds that width
# verbatim, so a continuous drag was a guaranteed miss on almost every frame:
# measured at 10-40ms per re-shape for a real paragraph of prose, which is
# well past the resize-repaint throttle's 1/120s budget and, once individual
# paints run longer than that, reproduces the very glfw.poll_events() backlog
# `_coalesce_resize_paints` (runtime/engine.py) exists to prevent -- a window
# that visibly freezes mid-drag and then snaps to wherever the cursor ended
# up. Rounding UP (never down) guarantees the bucketed width is never
# *smaller* than what was asked for, which is what keeps
# `test_text_laid_out_at_its_own_ink_width_stays_on_one_line` (test_text.py)
# holding: a widget laid out again at exactly its own measured ink width must
# never wrap, and it can't if it is never given less room than it measured.
# 16px is small enough that the extra slack is imperceptible in prose (well
# under one average glyph) while cutting the number of distinct cache keys a
# smooth per-pixel drag produces by roughly the same factor.
_WRAP_WIDTH_BUCKET_PX: Final = 16.0


def _span_arrays(
    spans: Sequence[tuple[int, int, int | tuple[float, float, float, float]]] | None,
    offsets: list[int],
    color: tuple[float, float, float, float],
    token: int,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Map source-offset spans onto per-glyph colour and token columns.

    Returns ``(None, None)`` when there is nothing to map, so the ordinary
    monochrome path writes a broadcast scalar exactly as it did before -- this
    must not make unhighlighted text more expensive.

    The mapping is a `searchsorted` over the span starts rather than a lookup
    per glyph: §12's rule is that per-glyph Python misses the frame budget, and
    a syntax-highlighted editor is precisely where that would bite.
    """
    if not spans or not offsets:
        return None, None

    ordered = sorted(spans, key=lambda s: s[0])
    starts = np.fromiter((s[0] for s in ordered), dtype=np.int64, count=len(ordered))
    ends = np.fromiter((s[1] for s in ordered), dtype=np.int64, count=len(ordered))

    # Per span: a token index, or NO_TOKEN plus a literal colour. A token span
    # keeps the caller's colour because the shader multiplies the resolved
    # token by `literal.a` -- that is how opacity survives theming.
    span_tokens = np.full(len(ordered), token, dtype=np.uint32)
    span_colors = np.tile(np.asarray(color, dtype=np.float32), (len(ordered), 1))
    for i, (_, _, value) in enumerate(ordered):
        if isinstance(value, int):
            span_tokens[i] = value
        else:
            span_tokens[i] = NO_TOKEN
            span_colors[i] = value

    offs = np.asarray(offsets, dtype=np.int64)
    # The last span starting at or before each glyph...
    idx = np.searchsorted(starts, offs, side="right") - 1
    # ...which only applies if the glyph is also before that span's end. Spans
    # are half-open and need not cover the text; anything uncovered keeps the
    # caller's own colour.
    safe = np.clip(idx, 0, None)
    inside = (idx >= 0) & (offs < ends[safe])

    colors = np.tile(np.asarray(color, dtype=np.float32), (len(offs), 1))
    tokens = np.full(len(offs), token, dtype=np.uint32)
    colors[inside] = span_colors[safe[inside]]
    tokens[inside] = span_tokens[safe[inside]]
    return colors, tokens


class TextEngine:
    """Owns fonts, caches, and the glyph atlas for one application."""

    __slots__ = ("_icons", "_layout_cache_size", "_layouts", "atlas", "db", "shaper")

    def __init__(
        self,
        device: Any = None,
        *,
        atlas_size: int = 1024,
        layout_cache_size: int = _DEFAULT_LAYOUT_CACHE_SIZE,
    ) -> None:
        self.db = FontDB()
        self.shaper = ShapeCache()
        self.atlas = GlyphAtlas(device, size=atlas_size)
        self._layouts: OrderedDict[tuple[Any, ...], Paragraph] = OrderedDict()
        self._layout_cache_size = layout_cache_size
        self._icons: IconSet | None = None

    @property
    def icons(self) -> IconSet:
        """Material Symbols, loaded on first use -- an app with no icons pays
        nothing for the font."""
        if self._icons is None:
            self._icons = IconSet.bundled()
        return self._icons

    def emit_icon(
        self,
        display_list: DisplayList,
        name: str,
        *,
        x: float,
        y: float,
        size: float = DEFAULT_ICON_SIZE,
        fill: float = 0.0,
        weight: float = 400.0,
        pixel_ratio: float = 1.0,
        token: int = NO_TOKEN,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        clip: tuple[float, float, float, float] = _NO_CLIP,
        clip_radii: tuple[float, float, float, float] = _NO_CLIP,
    ) -> bool:
        """Emit one icon at logical ``(x, y)``. Returns whether it drew anything.

        An icon is a glyph, so this reuses the atlas and the same GLYPH
        instance kind -- it costs no extra draw call.
        """
        icons = self.icons
        gid = icons.glyph(name)
        coords = icons.coords(fill=fill, weight=icons.suggested_weight(size, weight))
        entry = self.atlas.get(icons.face, gid, size * pixel_ratio, 0, coords)
        if entry.is_blank:
            return False
        display_list.add_glyph(
            x * pixel_ratio + entry.left,
            (y + size) * pixel_ratio - entry.top,
            float(entry.width),
            float(entry.height),
            uv=entry.uv(self.atlas.size),
            color=color,
            token=token,
            clip=clip,
            clip_radii=clip_radii,
        )
        return True

    def attach_device(self, device: Any) -> None:
        """Promote a CPU-only engine to a GPU-backed one."""
        self.atlas.attach_device(device)

    # ------------------------------------------------------------- layout

    def layout(
        self,
        text: str,
        *,
        px: float = 14.0,
        max_width: float | None = None,
        request: FontRequest | None = None,
        alignment: str = Alignment.START,
        tracking: float = 0.0,
        line_height: float | None = None,
    ) -> Paragraph:
        """Lay out *text*, memoised. Static labels cost nothing after frame one.

        The cache is bounded (LRU, ``layout_cache_size`` entries): a widget
        whose text changes every keystroke -- `TextField`, `CodeEditor` --
        keeps recently-seen paragraphs around for reuse but does not grow
        `_layouts` without limit over a long editing session.
        """
        req = request or FontRequest()
        if max_width is not None and alignment == Alignment.START:
            # Bucketing is only safe for START alignment. `layout_text` sets
            # `box_width = max_width` and centres/ends lines against THAT --
            # not against the line's own ink width -- so a centered or
            # end-aligned paragraph laid out against a rounded-up `max_width`
            # would visibly drift from true centre by up to half a bucket
            # (caught by `tests/golden/test_baselines.py::test_wrapped_text_baseline`,
            # whose "centred" line shifted right when this was tried
            # unconditionally). START alignment has no such box-relative
            # offset, so it is the only case bucketing is free.
            max_width = math.ceil(max_width / _WRAP_WIDTH_BUCKET_PX) * _WRAP_WIDTH_BUCKET_PX
        key = (text, px, max_width, req.key(), alignment, tracking, line_height)
        hit = self._layouts.get(key)
        if hit is not None:
            self._layouts.move_to_end(key)
            return hit
        para = layout_text(
            text,
            self.db,
            px=px,
            max_width=max_width,
            request=req,
            alignment=alignment,
            tracking=tracking,
            line_height=line_height,
            cache=self.shaper,
        )
        self._layouts[key] = para
        if len(self._layouts) > self._layout_cache_size:
            self._layouts.popitem(last=False)
        return para

    def measure(
        self,
        text: str,
        *,
        px: float = 14.0,
        max_width: float | None = None,
        request: FontRequest | None = None,
        tracking: float = 0.0,
        line_height: float | None = None,
    ) -> Size:
        return self.layout(
            text,
            px=px,
            max_width=max_width,
            request=request,
            tracking=tracking,
            line_height=line_height,
        ).size

    def clear_caches(self) -> None:
        self._layouts.clear()
        self.shaper.clear()

    # -------------------------------------------------------------- paint

    def emit(
        self,
        display_list: DisplayList,
        paragraph: Paragraph,
        *,
        x: float,
        y: float,
        pixel_ratio: float = 1.0,
        token: int = NO_TOKEN,
        color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        spans: Sequence[tuple[int, int, int | tuple[float, float, float, float]]] | None = None,
        clip: tuple[float, float, float, float] = _NO_CLIP,
        clip_radii: tuple[float, float, float, float] = _NO_CLIP,
    ) -> int:
        """Emit glyph quads for *paragraph* at logical position ``(x, y)``.

        Rasterisation happens at the **physical** size, so text is sharp at any
        DPI; layout stays in logical units (ARCHITECTURE.md 7).

        `spans` colours parts of the text differently: ``(start, end, value)``
        over **paragraph source offsets**, where *value* is either a palette
        token index or a literal RGBA tuple. Half-open, and they must not
        overlap. This is what syntax highlighting and ANSI need.

        **Source offsets, not glyph indices**, because that is what a lexer
        produces and because the two do not correspond -- a ligature is one
        glyph for several characters. Mapping happens here, once, so every
        consumer gets ligatures right the same way.

        A token themes with the rest of the interface and a literal colour does
        not, which makes the literal correct only where the colour genuinely is
        fixed -- an ANSI escape's is; a syntax theme's should be tokens.

        Spans cost nothing when absent: the scalar path writes one broadcast
        column exactly as before, and the mapping below is vectorised rather
        than a lookup per glyph.
        """
        dpr = pixel_ratio
        px_physical = paragraph.px * dpr
        atlas_size = self.atlas.size

        # The atlas lookup is an unavoidable Python dict hit per glyph, but the
        # instance write is not: collect first, then write whole columns.
        rects: list[tuple[float, float, float, float]] = []
        uvs: list[tuple[float, float, float, float]] = []
        offsets: list[int] = []
        for place in paragraph.placements():
            pen_x = (x + place.x) * dpr
            pen_y = (y + place.y) * dpr
            bucket = int((pen_x % 1.0) * SUBPIXEL_BUCKETS) % SUBPIXEL_BUCKETS
            entry = self.atlas.get(place.face, place.gid, px_physical, bucket)
            if entry.is_blank:
                continue
            # `pen_x`'s fractional part chose `bucket` above, and that same
            # fraction is already baked into `entry`'s own pixels -- FreeType
            # rendered it pre-shifted by exactly that amount (font.py's
            # `_activate`). Placing the quad at the full, un-floored `pen_x`
            # applies the fraction a SECOND time on top of that. Bilinear
            # filtering blurred the resulting double-counted offset into
            # softness; `floor` here (not on `pen_y`, which has no bucket
            # system and needs its own fractional part) is what makes the
            # bucket's pre-shift the only shift that happens.
            rects.append(
                (
                    math.floor(pen_x) + entry.left,
                    pen_y - entry.top,
                    float(entry.width),
                    float(entry.height),
                )
            )
            uvs.append(entry.uv(atlas_size))
            if spans is not None:
                offsets.append(place.offset)

        if not rects:
            return 0
        colors_arr, tokens_arr = _span_arrays(spans, offsets, color, token)
        display_list.add_glyphs(
            np.asarray(rects, dtype=np.float32),
            np.asarray(uvs, dtype=np.float32),
            color=color,
            token=token,
            colors=colors_arr,
            tokens=tokens_arr,
            clip=clip,
            clip_radii=clip_radii,
        )
        return len(rects)
