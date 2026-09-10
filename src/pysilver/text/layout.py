"""Paragraph layout: shaped runs become positioned lines.

Stages 4 and 5 of the pipeline interleave (ARCHITECTURE.md 5.7.1). Line
breaking needs measured advances, which only shaping produces, but shaping
context can cross a break. A break that lands inside a ligature is resolved on
*source clusters*, never on glyph indices.

The block is shaped **once**, and candidate breaks are measured by looking up
cumulative advances rather than by re-shaping the growing prefix. Only the
lines actually emitted are shaped again, which they must be regardless -- a
line needs its own runs to paint, and shaping context legitimately differs
either side of a break. That makes the cost linear in break opportunities
instead of quadratic in the number *per line*.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

import numpy as np

from ..layout import SIZE_ZERO, Size
from .bidi import resolve_levels
from .font import Face
from .fontdb import FontDB, FontRequest
from .itemize import Direction, itemize
from .segment import break_opportunities
from .shaping import ShapeCache, ShapedRun

__all__ = ["Alignment", "GlyphPlacement", "Paragraph", "TextLine", "layout_text"]

#: Slack allowed when asking whether a line fits.
#:
#: Not a fudge factor -- it is there because a `Text` shrink-wraps to its own
#: ink width and the paint pass then re-wraps it at exactly that width, so the
#: fit test is evaluated at precise equality every single time. `np.sum` adds
#: pairwise and `np.cumsum` adds sequentially, and for `"title-small"` at
#: `title-small` the two orders differ by 7e-15 px -- enough, at exact
#: equality, to wrap a word onto a second line and make the widget paint taller
#: than it measured. A line that overflows by a femtopixel has not overflowed.
#: Chosen far below a subpixel and far above float64 noise at any width a
#: window can have.
FIT_EPSILON: Final = 1e-6

#: Hard line terminators, written as escapes -- the literal characters are
#: invisible in source and trip ambiguous-character lints.
HARD_BREAK_CHARS: Final = "\n\r\v\f\u2028\u2029\u0085"


class Alignment:
    START = "start"
    CENTER = "center"
    END = "end"


@dataclass(frozen=True, slots=True)
class GlyphPlacement:
    """One glyph, positioned in paragraph-local pixels."""

    face: Face
    gid: int
    x: float
    y: float  # baseline y
    #: Index into the run's own text. Kept because it is what shaping produces.
    cluster: int
    #: Index into the **paragraph's** text -- what a caller reasons in. A
    #: syntax highlighter or an ANSI parser produces spans over the source, so
    #: without this every consumer would have to re-derive the mapping through
    #: line and run offsets, and each would get ligatures wrong differently.
    #: Correct for RTL/mixed-direction text too, via `TextLine.run_starts`
    #: (each run's own true logical start, recorded once at layout time
    #: rather than reconstructed later by walking already-reordered runs).
    offset: int = 0


@dataclass(slots=True)
class TextLine:
    """One laid-out line."""

    runs: list[ShapedRun] = field(default_factory=list)
    #: Each run's own logical (paragraph-text) start offset, parallel to
    #: `runs` and in the SAME (visual) order. Recorded once, here, at the
    #: one point `ItemRun.start` is still trustworthy -- `layout_text`'s own
    #: `shape_segment` populates it directly from `itemize()`'s output,
    #: rather than something reconstructing it later by walking already
    #: visually-reordered runs (which only works for pure LTR text, the
    #: bug this field exists to fix at its root).
    run_starts: list[int] = field(default_factory=list)
    start: int = 0
    end: int = 0
    width: float = 0.0
    baseline: float = 0.0
    height: float = 0.0
    x: float = 0.0

    @property
    def top(self) -> float:
        return self.baseline - self.height


@dataclass(slots=True)
class Paragraph:
    """A fully laid-out block of text."""

    text: str
    lines: list[TextLine] = field(default_factory=list)
    size: Size = SIZE_ZERO
    #: Width the text was wrapped and aligned to. `size.width` is the INK
    #: extent -- the widest line -- so a Text widget shrink-wraps instead of
    #: claiming its whole wrap box and starving its siblings in a Horizontal.
    box_width: float = 0.0
    px: float = 14.0
    #: Letter spacing in logical px, added after every grapheme cluster --
    #: including the last on a line, as CSS `letter-spacing` does. That leaves
    #: centred text off-centre by half a tracking value (a quarter-pixel at
    #: M3's largest), which is the price of every consumer deriving its
    #: positions from one advance array instead of special-casing line ends.
    tracking: float = 0.0
    #: Fixed line height in logical px, or None for the font's own. The extra
    #: space is split evenly above and below the glyphs -- CSS half-leading --
    #: so raising a line's height does not move centred text.
    line_height: float | None = None
    base_direction: str = Direction.LTR

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def placements(self) -> list[GlyphPlacement]:
        """Every glyph with its final position. Consumed by the paint pass."""
        out: list[GlyphPlacement] = []
        for line in self.lines:
            pen = line.x
            # `run_starts` is parallel to `runs`, in the SAME (visual) order
            # -- each run's own true logical start, recorded once at layout
            # time (see `TextLine.run_starts`), not reconstructed here by
            # accumulating run lengths (which only works for pure LTR text).
            for run, run_start in zip(line.runs, line.run_starts, strict=True):
                scale = run.face.scale_for(self.px)
                advances = run.advances_px(self.px, self.tracking)
                for i in range(len(run)):
                    ox, oy = run.offsets[i]
                    cluster = int(run.clusters[i])
                    out.append(
                        GlyphPlacement(
                            face=run.face,
                            gid=int(run.glyphs[i]),
                            x=pen + float(ox) * scale,
                            y=line.baseline - float(oy) * scale,
                            cluster=cluster,
                            offset=run_start + cluster,
                        )
                    )
                    pen += float(advances[i])
        return out


def _line_metrics(runs: list[ShapedRun], px: float, fallback: Face) -> tuple[float, float]:
    """``(ascent, height)`` for a line, taken from the tallest face it uses."""
    faces = [r.face for r in runs] or [fallback]
    return (
        max(f.metrics(px).ascent for f in faces),
        max(f.metrics(px).line_height for f in faces),
    )


def layout_text(
    text: str,
    db: FontDB,
    *,
    px: float = 14.0,
    max_width: float | None = None,
    request: FontRequest | None = None,
    alignment: str = Alignment.START,
    tracking: float = 0.0,
    line_height: float | None = None,
    cache: ShapeCache | None = None,
) -> Paragraph:
    """Shape, break, and position *text*.

    ``max_width`` of None lays the text out as a single unwrapped line.
    ``tracking`` is letter spacing in logical px -- an absolute figure, the way
    M3's type-scale tokens state it, not a multiple of the font size. So is
    ``line_height``, which replaces the font's own; None keeps it.
    """
    req = request or FontRequest()
    # NOT `cache or ShapeCache()`: an empty ShapeCache is falsy (__len__ == 0),
    # so that form silently discards the caller's cache on first use.
    shaper = ShapeCache() if cache is None else cache
    primary = db.face_for(req)
    para = Paragraph(text=text, px=px, tracking=tracking, line_height=line_height)

    if not text:
        para.size = Size(0.0, line_height or primary.metrics(px).line_height)
        para.box_width = max_width or 0.0
        return para

    # A cheap, whole-paragraph-once call: only the base LEVEL is needed
    # here, not a full itemize() (script/font splitting the paragraph is
    # wasted work when the only thing this line ever consumed was
    # `items[0].direction`). Every segment shaped below inherits this same
    # `base` explicitly (`base_direction=base`), rather than each
    # independently re-detecting its own from whatever character happens
    # to start it -- a wrapped line's own first character is not
    # necessarily a reliable signal of the paragraph's real base direction.
    base_level = resolve_levels(text).base_level
    base = Direction.RTL if base_level % 2 else Direction.LTR
    para.base_direction = base

    def shape_segment(
        segment: str, segment_offset: int
    ) -> tuple[list[ShapedRun], list[int], float]:
        runs: list[ShapedRun] = []
        run_starts: list[int] = []
        width = 0.0
        for item in itemize(segment, db, req, base_direction=base):
            run = shaper.get(item.text, item.face, direction=item.direction, script=item.script)
            runs.append(run)
            run_starts.append(segment_offset + item.start)
            width += run.width(px, tracking)
        return runs, run_starts, width

    def prefix_widths(segment: str) -> np.ndarray | None:
        """Pen x at every source offset in *segment*: ``table[o]`` is the width
        of ``segment[:o]``, so any span costs one subtraction.

        This is what replaces re-shaping each candidate prefix. It shapes the
        segment once and attributes each glyph's advance to the source offset
        of the cluster it belongs to, which is why a ligature -- one glyph for
        several characters -- lands wholly on its first character rather than
        being smeared across them.

        Two approximations, both deliberate and both corrected downstream by
        the exact re-shape of the line that is actually emitted:

        * shaping context crosses a break, so kerning either side of a cut is
          not what the cut-down line will really have;
        * a break falling *inside* a ligature measures as though the whole
          ligature followed it.

        Returns None for a segment containing any RTL item, where logical and
        visual order differ and a left-to-right prefix sum has no meaning.
        Callers fall back to re-shaping, which is correct if slower -- and the
        bundled fonts carry no RTL glyphs, so this path is untested by
        anything but its own bail-out (R9).
        """
        per_char = np.zeros(len(segment), dtype=np.float64)
        for item in itemize(segment, db, req, base_direction=base):
            if item.is_rtl:
                return None
            run = shaper.get(item.text, item.face, direction=item.direction, script=item.script)
            if not len(run):
                continue
            # `clusters` index into the item's own text; shift to the segment.
            at = np.asarray(run.clusters, dtype=np.intp) + item.start
            # `add.at` rather than `per_char[at] += ...`: several glyphs can
            # share one cluster (a base and its combining marks) and fancy
            # indexing would keep only the last of them.
            np.add.at(per_char, at, run.advances_px(px, tracking))
        table = np.zeros(len(segment) + 1, dtype=np.float64)
        np.cumsum(per_char, out=table[1:])
        return table

    # Hard breaks split the paragraph first; wrapping happens inside each block.
    blocks: list[tuple[int, str]] = []
    start = 0
    for op in break_opportunities(text):
        if op.mandatory:
            blocks.append((start, text[start : op.offset]))
            start = op.offset
    if start < len(text):
        blocks.append((start, text[start:]))

    lines: list[TextLine] = []
    for offset, block in blocks:
        lines.extend(_wrap_block(block, offset, max_width, shape_segment, prefix_widths))

    # Stack the lines, then apply horizontal alignment.
    y = 0.0
    widest = 0.0
    for line in lines:
        ascent, natural = _line_metrics(line.runs, px, primary)
        height = natural if line_height is None else line_height
        # Half-leading, as CSS distributes it: the glyphs keep their own
        # ascent and descent and sit in the middle of the taller line box.
        # That is what makes a raised line height leave centred text where it
        # was -- a button's label does not move, its box just measures taller.
        line.height = height
        line.baseline = y + (height - natural) / 2.0 + ascent
        y += height
        widest = max(widest, line.width)

    box_width = widest if max_width is None else max_width
    for line in lines:
        slack = max(0.0, box_width - line.width)
        if alignment == Alignment.CENTER:
            line.x = slack / 2
        elif alignment == Alignment.END:
            line.x = slack

    para.lines = lines
    para.box_width = box_width
    para.size = Size(widest, y)
    return para


def _wrap_block(
    block: str,
    offset: int,
    max_width: float | None,
    shape_segment: Callable[[str, int], tuple[list[ShapedRun], list[int], float]],
    prefix_widths: Callable[[str], np.ndarray | None],
) -> list[TextLine]:
    """Greedy wrap of one hard-break-delimited block."""
    stripped = block.rstrip(HARD_BREAK_CHARS)
    if not stripped.strip():
        return [TextLine([], [], offset, offset + len(block), 0.0)]

    if max_width is None:
        runs, run_starts, width = shape_segment(stripped, offset)
        return [TextLine(runs, run_starts, offset, offset + len(block), width)]

    table = prefix_widths(stripped)

    def measure(start: int, end: int) -> float:
        """Width of ``stripped[start:end]``, trailing whitespace excluded.

        Trailing spaces hang past the wrap box rather than pushing a word onto
        the next line, which is what every text engine does and what makes a
        space-separated line break where the eye expects.
        """
        while end > start and stripped[end - 1].isspace():
            end -= 1
        if table is not None:
            return float(table[end] - table[start])
        return shape_segment(stripped[start:end], offset + start)[2] if end > start else 0.0

    lines: list[TextLine] = []
    line_start = 0
    last_fit = 0
    ops = [o.offset for o in break_opportunities(stripped)]
    i = 0
    while i < len(ops):
        op = ops[i]
        if measure(line_start, op) <= max_width + FIT_EPSILON:
            last_fit = op
            i += 1
            continue
        # Overflowed. Emit up to the last opportunity that fitted; if none did,
        # this one unbreakable unit overflows on its own line rather than
        # vanishing. Only advance past `op` when it was consumed as that
        # unbreakable unit -- cutting back to an earlier `last_fit` leaves `op`
        # untested against the new line, and re-trying it (rather than moving
        # on) is what stops the break right after a cut from being lost.
        cut = last_fit if last_fit > line_start else op
        lines.append(_emit(stripped, offset, line_start, cut, shape_segment))
        line_start = cut
        last_fit = cut
        if cut == op:
            i += 1

    if line_start < len(stripped):
        # No `.rstrip()` here, unlike `_emit`'s real mid-paragraph wrap
        # points: this is whatever's left after the loop, which is the
        # WHOLE block when nothing wrapped at all. A trailing space at the
        # true end of the text (not at a break the wrap consumed) is
        # meaningful content -- it is what lets a sentence built from
        # several sibling widgets (a `Text`, a `Link`, another `Text`) keep
        # the gaps between them, and stripping it collapsed "Read the " and
        # a following `Link` together with no space at all.
        runs, run_starts, w = shape_segment(stripped[line_start:], offset + line_start)
        lines.append(TextLine(runs, run_starts, offset + line_start, offset + len(block), w))

    return lines or [TextLine([], [], offset, offset + len(block), 0.0)]


def _emit(
    stripped: str,
    offset: int,
    start: int,
    cut: int,
    shape_segment: Callable[[str, int], tuple[list[ShapedRun], list[int], float]],
) -> TextLine:
    """One finished line, shaped for real.

    The break was chosen from the cumulative-advance table, which is an
    approximation across ligatures and kerning. This is where the line gets its
    true width -- and it is not extra work, because a line needs its own runs
    to paint whatever decided where it ended.
    """
    runs, run_starts, width = shape_segment(stripped[start:cut].rstrip(), offset + start)
    return TextLine(runs, run_starts, offset + start, offset + cut, width)
