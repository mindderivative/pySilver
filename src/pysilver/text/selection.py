"""Mapping between points and character offsets in a laid-out paragraph.

Selection needs two questions answered, and they are inverses:

* which character is under this point (placing a caret),
* which rectangles cover this character range (drawing the highlight).

Both are derived from `Paragraph` as it already exists. A `ShapedRun` carries
cluster indices into **its own** text rather than into the paragraph, and no
offset back to it -- `TextLine.run_starts` (parallel to `runs`, in the SAME
visual order) is what recovers the paragraph offset, recorded once at layout
time rather than reconstructed here by accumulating run lengths, which only
works when visual order matches logical order (pure LTR text).

A logical offset can be genuinely AMBIGUOUS on screen: within one run, an
LTR run's glyphs advance in the same direction its source text reads, but an
RTL run's glyphs paint left-to-right while its source offsets *descend* --
the visually-leftmost glyph is the run's own last character. `caret_at` and
`index_at` account for this per run (`run.direction`); a caller walking a run's
glyphs left-to-right and comparing against an ascending offset, the way pure
LTR code can, silently gets the wrong answer for RTL content.

Advances come from `ShapedRun.advances_px`, the same call the paint pass uses,
so a caret cannot land somewhere the glyphs are not -- letter spacing in
particular has to be in both or neither.

Offsets are snapped to **grapheme cluster** boundaries (`segment.py`, UAX #29),
so a selection edge never lands inside a flag emoji or between a base character
and its combining mark.
"""

from __future__ import annotations

from dataclasses import dataclass

from .editing import Affinity
from .itemize import Direction
from .layout import Paragraph, TextLine
from .segment import cluster_boundaries
from .shaping import ShapedRun

__all__ = [
    "SelectionRect",
    "caret_at",
    "index_at",
    "line_end",
    "line_index_at",
    "rects_for",
    "word_at",
]

#: Hard terminators, as `layout.HARD_BREAK_CHARS` spells them.
_BREAKS = "\n\r\v\f\u2028\u2029\u0085"


@dataclass(frozen=True, slots=True)
class SelectionRect:
    """One highlight rectangle, in the paragraph's own coordinate space."""

    x: float
    y: float
    width: float
    height: float


def line_index_at(para: Paragraph, y: float) -> int:
    """Index of the line containing `y`, clamped to the paragraph."""
    if not para.lines:
        return 0
    top = 0.0
    for index, line in enumerate(para.lines):
        if y < top + line.height:
            return index
        top += line.height
    return len(para.lines) - 1


def line_end(para: Paragraph, line: TextLine) -> int:
    """Where a caret goes at the end of *line*.

    Not `line.end`, which is where the *next* line starts and therefore sits
    after a newline. Pressing End on the first of two lines has to leave the
    caret before the break, or it lands at the start of the line below and
    typing appears on the wrong one.
    """
    end = line.end
    while end > line.start and para.text[end - 1] in _BREAKS:
        end -= 1
    return end


def _snap(text: str, offset: int) -> int:
    """Move an offset to the nearest grapheme boundary."""
    if not text:
        return 0
    bounds = cluster_boundaries(text)
    return min(bounds, key=lambda b: (abs(b - offset), b))


def index_at(para: Paragraph, x: float, y: float) -> int:
    """Character offset nearest the point, snapped to a grapheme boundary.

    The *nearest* edge, not the containing glyph: clicking the left half of a
    character puts the caret before it and the right half after it, which is
    what every text control does and what makes click-and-drag feel right.

    Localizes to a run, then a glyph, by BOX CONTAINMENT (`x` inside
    `[pen, pen + advance)`) before deciding which half -- a single global
    threshold comparison (the natural approach for LTR, where a glyph's own
    pen position and its source offset both increase together) does not
    localize correctly for RTL, where pen increases but source offset
    *decreases* along the same walk: a naive mirrored condition
    (`x >= midpoint`) stays true for every `x` past the FIRST glyph's own
    midpoint, including `x` values that actually belong to a much later
    glyph, and returns the wrong (too-early) answer. Verified against a
    hand-traced three-glyph RTL example, box by box, before writing it
    this way.

    Once localized: an LTR glyph's LEFT half is `before` it (this glyph's
    own cluster) and the RIGHT half is `after` (the next cluster along, or
    the line's own end for the very last glyph) -- unchanged from before
    this module supported RTL. An RTL glyph is the mirror image on both
    axes: its RIGHT half is `before` (this glyph's own cluster, since the
    visually-rightmost content is read FIRST in RTL) and its LEFT half is
    `after` (the PREVIOUS glyph walked, i.e. `clusters[i - 1]` -- earlier
    in visual/array order but LATER in reading order for RTL -- or the
    run's own end, for the first glyph walked).
    """
    if not para.lines or not para.text:
        return 0
    line = para.lines[line_index_at(para, y)]
    pen = line.x
    for run, run_start in zip(line.runs, line.run_starts, strict=True):
        advances = run.advances_px(para.px, para.tracking)
        run_width = float(run.width(para.px, para.tracking))
        is_last_run = run is line.runs[-1]
        if x < pen + run_width or is_last_run:
            local_pen = pen
            for i in range(len(run)):
                advance = float(advances[i])
                is_last_glyph = i == len(run) - 1
                if x < local_pen + advance or is_last_glyph:
                    cluster = run_start + int(run.clusters[i])
                    midpoint = local_pen + advance / 2.0
                    if run.direction == Direction.RTL:
                        if x >= midpoint:
                            return _snap(para.text, cluster)
                        if i == 0:
                            return _snap(para.text, run_start + len(run.text))
                        return _snap(para.text, run_start + int(run.clusters[i - 1]))
                    if x < midpoint:
                        return _snap(para.text, cluster)
                    if not is_last_glyph:
                        return _snap(para.text, run_start + int(run.clusters[i + 1]))
                    break  # last glyph, right half -- fall through to the next run
                local_pen += advance
        pen += run_width
    return _snap(para.text, line_end(para, line))


def _spans_x(line: TextLine, para: Paragraph, start: int, end: int) -> list[tuple[float, float]]:
    """Horizontal extents of `[start, end)` within one line -- one span per
    contiguous VISUAL run of matching glyphs, not one span overall.

    A logically-contiguous range can render as more than one span the
    moment it crosses a direction boundary: selecting "lo مرحبا" (an LTR
    prefix into an embedded RTL word) highlights two disjoint rectangles,
    not one that spans the visual gap between them. Walking visually and
    testing logical-range membership per glyph produces this naturally --
    no direction-specific branching needed here, unlike `caret_at`, since
    this never stops early on a single glyph's own condition.
    """
    pen = line.x
    open_left: float | None = None
    spans: list[tuple[float, float]] = []
    for run, run_start in zip(line.runs, line.run_starts, strict=True):
        advances = run.advances_px(para.px, para.tracking)
        for i in range(len(run)):
            advance = float(advances[i])
            in_range = start <= run_start + int(run.clusters[i]) < end
            if in_range and open_left is None:
                open_left = pen
            elif not in_range and open_left is not None:
                spans.append((open_left, pen))
                open_left = None
            pen += advance
    if open_left is not None:
        spans.append((open_left, pen))
    return spans


def caret_at(para: Paragraph, offset: int, *, affinity: str = Affinity.DOWNSTREAM) -> SelectionRect:
    """Where a caret sitting *before* `offset` belongs, as a zero-width rect.

    Finds every RUN whose own `[run_start, run_end]` contains `offset`
    (closed on both ends) and the pen position at each candidate's own
    entry -- normally exactly one, but exactly two when `offset` sits at a
    boundary shared by two adjacent runs, which is genuinely ambiguous
    (two different, both-correct on-screen positions). `affinity` breaks
    the tie deliberately: `UPSTREAM` picks whichever candidate `offset`
    equals the END of (the content already read), `DOWNSTREAM` (the
    default) picks whichever it equals the START of (the content about to
    be read). Collecting candidates first, rather than returning on the
    first run whose range matches, is what makes this a deliberate choice
    instead of an accident of visual iteration order -- which run happens
    to be visited first at a boundary is not consistently "upstream" or
    "downstream" (it depends on the specific paragraph's own L2 reordering,
    verified directly against two paragraphs where the answer came out
    opposite ways), so it cannot be trusted as an implicit default.

    Once localized to one run: an RTL run's glyphs paint left-to-right
    while their source offsets *descend* (the visually-leftmost glyph is
    the run's own LAST character) -- inverted from LTR, where walking left
    to right and stopping at the first glyph whose offset has reached
    `offset` is correct as-is. An RTL run instead has to walk until the
    offset has dropped BELOW `offset`, the exact mirror image -- found the
    hard way: a first draft used a half-open `< run_end` upper bound
    (matching the "skip past, add full width" logic that's correct for
    LTR), which put an RTL run's own END offset (e.g. `caret_at(para,
    len(text))` for a pure-RTL paragraph) at the WRONG edge, since "skip
    this run" silently assumes skipping always means "continue rightward"
    -- true for LTR, backwards for RTL. Caught by computing actual pixel
    values for a real Arabic paragraph and checking them by hand before
    trusting the code, not by reasoning about the algorithm alone.
    """
    if not para.lines:
        # An empty paragraph still records a correct line height (see
        # `layout_text`'s own early-return for `not text`) -- returning it
        # here, not 0, is what keeps a caret on an empty field visible
        # instead of collapsing to a degenerate zero-height rect.
        return SelectionRect(0.0, 0.0, 0.0, para.size.height)
    top = 0.0
    line = para.lines[0]
    for candidate_line in para.lines:
        if candidate_line.start <= offset <= candidate_line.end:
            line = candidate_line
            break
        top += candidate_line.height
    else:
        line = para.lines[-1]
        top -= line.height

    pen = line.x
    candidates: list[tuple[ShapedRun, int, float, bool]] = []
    for run, run_start in zip(line.runs, line.run_starts, strict=True):
        run_end = run_start + len(run.text)
        if run_start <= offset <= run_end:
            candidates.append((run, run_start, pen, offset == run_end))
        pen += float(run.width(para.px, para.tracking))
    if not candidates:
        return SelectionRect(pen, top, 0.0, line.height)

    chosen = candidates[0]
    if len(candidates) > 1:
        wants_end = affinity == Affinity.UPSTREAM
        chosen = next((c for c in candidates if c[3] == wants_end), candidates[0])
    run, run_start, pen, _ = chosen

    advances = run.advances_px(para.px, para.tracking)
    if run.direction == Direction.RTL:
        for i in range(len(run)):
            if run_start + int(run.clusters[i]) < offset:
                return SelectionRect(pen, top, 0.0, line.height)
            pen += float(advances[i])
    else:
        for i in range(len(run)):
            if run_start + int(run.clusters[i]) >= offset:
                return SelectionRect(pen, top, 0.0, line.height)
            pen += float(advances[i])
    return SelectionRect(pen, top, 0.0, line.height)


def rects_for(para: Paragraph, start: int, end: int) -> list[SelectionRect]:
    """Highlight rectangles covering `[start, end)`, possibly several per
    line touched -- see `_spans_x` for why a single logically-contiguous
    range can render as more than one rectangle on one line.

    Empty when the range is empty -- a caret is not a selection, and drawing a
    zero-width rectangle for one would put a stray sliver on screen.
    """
    lo, hi = min(start, end), max(start, end)
    if lo == hi or not para.lines:
        return []

    rects: list[SelectionRect] = []
    top = 0.0
    for line in para.lines:
        if line.end > lo and line.start < hi:
            for left, right in _spans_x(line, para, max(lo, line.start), min(hi, line.end)):
                if right > left:
                    rects.append(SelectionRect(left, top, right - left, line.height))
        top += line.height
    return rects


def word_at(text: str, offset: int) -> tuple[int, int]:
    """The word around an offset, for double-click.

    Whitespace-delimited rather than UAX #29 word segmentation: the boundary
    algorithm is not exposed by the segmentation module, and inventing a
    half-version of it here would be worse than a rule that is simple and
    predictable. Stated plainly rather than presented as Unicode-correct.
    """
    if not text:
        return (0, 0)
    offset = max(0, min(offset, len(text)))
    if offset >= len(text) or text[offset].isspace():
        offset = max(0, offset - 1)
    if offset < len(text) and text[offset].isspace():
        return (offset, offset)

    start = offset
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    end = offset
    while end < len(text) and not text[end].isspace():
        end += 1
    return (start, end)
