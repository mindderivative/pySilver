"""Unicode segmentation: line-break opportunities and grapheme clusters.

Two different standards, needed for two different jobs:

* **UAX #14** line breaking decides where a paragraph may wrap. It is not
  "split on spaces" -- it keeps ``can't`` whole, allows a break after a hyphen,
  and forbids one before a closing bracket.
* **UAX #29** grapheme clusters define what a *user* considers one character.
  Cursor movement, selection, and font fallback all operate on clusters, not
  codepoints: ``👩‍👩‍👧`` is seven codepoints and one cluster.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from uniseg.graphemecluster import grapheme_clusters
from uniseg.linebreak import line_break_units

#: Hard line terminators (UAX #14 classes BK/CR/LF/NL). Written as escapes:
#: the literal characters are invisible in source and trip ambiguity lints.
_HARD_BREAKS = ("\n", "\r", "\u2028", "\u2029", "\v", "\f", "\u0085")

__all__ = [
    "BreakOpportunity",
    "break_opportunities",
    "cluster_boundaries",
    "clusters",
    "line_break_units_of",
    "next_boundary",
    "previous_boundary",
]


@dataclass(frozen=True, slots=True)
class BreakOpportunity:
    """A position where a line may wrap.

    ``offset`` is where the next line starts. ``trailing_space`` is the width of
    whitespace before it, which hangs past the wrap point rather than counting
    against the line's measured width -- otherwise a line that just fits would
    wrap early because of a space nobody can see.
    """

    offset: int
    trailing_space: int
    mandatory: bool


def line_break_units_of(text: str) -> list[str]:
    """UAX #14 units. Each includes its own trailing whitespace."""
    return list(line_break_units(text))


#: Memoised for the same reason as `_clusters`, and it matters more: wrapping
#: asks for a paragraph's break positions once per candidate line and again on
#: every relayout, and they do not depend on the width being tried. The tuple
#: is returned as a list so callers keep a value they may mutate.
@lru_cache(maxsize=1024)
def _break_opportunities(text: str) -> tuple[BreakOpportunity, ...]:
    out: list[BreakOpportunity] = []
    offset = 0
    for unit in line_break_units(text):
        offset += len(unit)
        stripped = unit.rstrip()
        mandatory = unit.endswith(_HARD_BREAKS)
        out.append(
            BreakOpportunity(
                offset=offset,
                trailing_space=len(unit) - len(stripped),
                mandatory=mandatory,
            )
        )
    return tuple(out)


def break_opportunities(text: str) -> list[BreakOpportunity]:
    """Every legal wrap position in *text*, in order."""
    return list(_break_opportunities(text))


#: Memoised because segmentation is pure and expensive, and the same strings
#: come back constantly: wrapping asks for every candidate prefix of a
#: paragraph at every width it is tried at, and a caret asks for the whole
#: field's boundaries on every keystroke. Profiling a window resize put uniseg
#: at 54% of the frame, all of it recomputing answers it had already given.
#: Bounded, because the keys are arbitrary user text.
@lru_cache(maxsize=4096)
def _clusters(text: str) -> tuple[str, ...]:
    return tuple(grapheme_clusters(text))


@lru_cache(maxsize=4096)
def _boundaries(text: str) -> tuple[int, ...]:
    out = [0]
    offset = 0
    for cluster in _clusters(text):
        offset += len(cluster)
        out.append(offset)
    return tuple(out)


def clusters(text: str) -> list[str]:
    """UAX #29 grapheme clusters -- what a user calls 'characters'."""
    return list(_clusters(text))


def cluster_boundaries(text: str) -> list[int]:
    """Codepoint offsets at which a cluster starts, plus the end offset.

    These are the only positions a caret may legally occupy.
    """
    return list(_boundaries(text))


def previous_boundary(text: str, offset: int) -> int:
    """Nearest cluster boundary strictly before *offset* (for a left arrow)."""
    bounds = cluster_boundaries(text)
    candidates = [b for b in bounds if b < offset]
    return candidates[-1] if candidates else 0


def next_boundary(text: str, offset: int) -> int:
    """Nearest cluster boundary strictly after *offset* (for a right arrow)."""
    bounds = cluster_boundaries(text)
    return next((b for b in bounds if b > offset), len(text))
