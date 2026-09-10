"""Itemisation: splitting a paragraph into runs that can each be shaped.

Shaping requires a run uniform in **script, direction, and font** all at once,
so a paragraph is split three times, in this order (ARCHITECTURE.md 5.7.1):

1. **Bidi** (UAX #9, `text/bidi.py`) first, because it operates on the whole
   paragraph and produces the embedding levels every later stage needs --
   including which corner cases actually matter: a run of digits inside RTL
   text resolves to its own, higher-level span (rule I2) regardless of
   script, so level splitting has to be the OUTERMOST split or a digit run
   would get glued onto whichever script run happens to precede it.
2. **Script** (UAX #24) next, using ``fontTools.unicodedata``, scoped to one
   level-run's own span at a time -- never across a level boundary.
3. **Font** last, by coverage, since which face is needed depends on the
   characters that survived the first two splits.
"""

from __future__ import annotations

from dataclasses import dataclass

from fontTools import unicodedata as ftud

from .bidi import l2_reorder, level_runs, resolve_levels
from .font import Face
from .fontdb import FontDB, FontRequest
from .segment import clusters

__all__ = ["Direction", "ItemRun", "itemize", "script_runs"]

#: Script codes that carry no direction of their own and join whichever run
#: they appear in. Splitting on them would fragment ordinary punctuated text.
_NEUTRAL = frozenset({"Zyyy", "Zinh", "Zzzz"})


class Direction:
    LTR = "ltr"
    RTL = "rtl"


@dataclass(frozen=True, slots=True)
class ItemRun:
    """A maximal span uniform in script, embedding level, and face.

    ``level`` (from `text/bidi.py`'s UAX #9 resolution) is the source of
    truth -- ``direction``/``is_rtl`` are derived from its parity, kept as
    the plain string `shape_run` already wants rather than making every
    caller spell out ``"rtl" if level % 2 else "ltr"`` itself.
    """

    start: int
    end: int
    text: str
    script: str
    level: int
    face: Face

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def direction(self) -> str:
        return Direction.RTL if self.level % 2 else Direction.LTR

    @property
    def is_rtl(self) -> bool:
        return bool(self.level % 2)


def script_runs(text: str) -> list[tuple[int, int, str]]:
    """``(start, end, script)`` spans. Neutral characters extend the run
    they follow, so ``"Hello, world!"`` stays a single Latin run."""
    if not text:
        return []
    runs: list[tuple[int, int, str]] = []
    start = 0
    current: str | None = None
    for i, char in enumerate(text):
        script = ftud.script(char)
        if script in _NEUTRAL:
            continue
        if current is None:
            current = script
        elif script != current:
            runs.append((start, i, current))
            start, current = i, script
    runs.append((start, len(text), current or "Zyyy"))
    return runs


def itemize(
    text: str,
    db: FontDB,
    request: FontRequest | None = None,
    base_direction: str | None = None,
    *,
    visual_order: bool = True,
) -> list[ItemRun]:
    """Split *text* into runs ready for shaping.

    ``visual_order`` (default `True`) returns the runs in DISPLAY order --
    run 0 paints leftmost, per UAX #9 rule L2 (`bidi.l2_reorder`). Pass
    `False` for LOGICAL (source) order instead: `layout_text` needs this
    internally, since L1 (trailing whitespace/separators reset to the
    paragraph's base level) has to be re-applied per rendered LINE once
    wrapping is involved, not once for the whole paragraph -- see
    `layout.py`'s own `reorder_line_runs`, which redoes the level-run ->
    script-run -> visual-order pipeline's last step at the line level using
    this logical-order form as its input.
    """
    if not text:
        return []
    req = request or FontRequest()
    levels = resolve_levels(text, base_direction=base_direction)

    out: list[ItemRun] = []
    for level_run in level_runs(levels):
        level_text = text[level_run.start : level_run.end]
        for rel_start, rel_end, script in script_runs(level_text):
            start = level_run.start + rel_start
            end = level_run.start + rel_end
            offset = start
            run_face: Face | None = None
            run_start = start
            # Split again by face. Resolution is per grapheme cluster so a
            # base character and its combining marks always land on the
            # same font.
            for cluster in clusters(text[start:end]):
                face = db.resolve(cluster, req)
                if run_face is None:
                    run_face = face
                elif face is not run_face:
                    out.append(
                        ItemRun(
                            run_start,
                            offset,
                            text[run_start:offset],
                            script,
                            level_run.level,
                            run_face,
                        )
                    )
                    run_start, run_face = offset, face
                offset += len(cluster)
            if run_face is not None and offset > run_start:
                out.append(
                    ItemRun(
                        run_start, offset, text[run_start:offset], script, level_run.level, run_face
                    )
                )

    out.sort(key=lambda r: r.start)
    if visual_order:
        order = l2_reorder([r.level for r in out])
        out = [out[i] for i in order]
    return out
