"""UAX #9 bidirectional text: embedding levels and visual reordering.

Two questions, both needed before a paragraph can be shaped or a caret can be
placed correctly: what **level** does each codepoint resolve to (LTR/RTL,
possibly nested several deep -- a run of digits inside Arabic text stays LTR
internally per rule I2, one level higher than its RTL surroundings), and in
what **visual order** do same-level spans display (rule L2: reverse from the
highest level down to the lowest odd one, contiguous runs at a time).

``python-bidi`` implements the rules but exposes no single function that
returns levels *and* order -- only ``get_display()``, which drives its own
internal pipeline end to end and returns a reordered string. This module
drives that same pipeline by hand, stopping after level resolution (before
``python-bidi``'s own ``reorder_resolved_levels``, a different question --
see ``level_runs``/``l2_reorder`` below) to get at the per-codepoint levels
directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from bidi import algorithm as _alg

__all__ = ["BidiLevels", "BidiRun", "l2_reorder", "level_runs", "resolve_levels"]


@dataclass(frozen=True, slots=True)
class BidiLevels:
    """Per-codepoint embedding levels for one paragraph, in LOGICAL order.

    Even levels are LTR, odd levels are RTL -- ``level % 2`` is the
    direction. Not a visual reordering; see `level_runs`/`l2_reorder` for
    that, a separate question (rule L2 vs. the level-resolution rules).
    """

    levels: tuple[int, ...]
    base_level: int


@dataclass(frozen=True, slots=True)
class BidiRun:
    """A maximal LOGICAL-order span at one embedding level."""

    start: int
    end: int
    level: int


@lru_cache(maxsize=4096)
def resolve_levels(text: str, *, base_direction: str | None = None) -> BidiLevels:
    """Resolve UAX #9 embedding levels for *text*, one per codepoint.

    Memoised for the same reason `segment._clusters` is: `itemize()` asks
    for this on every paragraph it splits, and `editing.move()` will ask
    again on every arrow keypress against a field's current text -- pure and
    expensive, and the same strings recur constantly.

    ``base_direction`` overrides paragraph direction detection (rule P2/P3,
    including isolates -- `python-bidi`'s own `get_base_level`, not the
    first-strong-character-only heuristic `itemize.resolve_base_direction`
    used before this module existed) with `"ltr"`/`"rtl"`, the same two
    spellings `itemize.Direction` uses. Needed so a wrapped segment can
    inherit the whole paragraph's own resolved base rather than
    re-detecting its own -- a segment starting with neutral or embedded
    content has no reliable first strong character of its own.
    """
    if not text:
        return BidiLevels(levels=(), base_level=0)

    storage = _alg.get_empty_storage()
    if base_direction is None:
        base_level = _alg.get_base_level(text)
    else:
        base_level = _alg.PARAGRAPH_LEVELS["R" if base_direction == "rtl" else "L"]
    storage["base_level"] = base_level
    storage["base_dir"] = ("L", "R")[base_level]

    _alg.get_embedding_levels(text, storage)
    # Tag each char dict with its logical position before running the rest
    # of the pipeline -- `explicit_embed_and_overrides`'s X9 step (next)
    # DELETES some entries from `storage["chars"]` (explicit-format
    # controls and BN-class codepoints), so the list's own index no longer
    # matches the paragraph offset afterward. The dicts themselves survive
    # untouched; this is what lets them be found again below.
    for position, char in enumerate(storage["chars"]):
        char["orig_index"] = position
    _alg.explicit_embed_and_overrides(storage)
    _alg.resolve_weak_types(storage)
    _alg.resolve_neutral_types(storage, False)
    _alg.resolve_implicit_levels(storage, False)

    # `storage["chars"]` is still in logical order here (nothing has
    # reordered it yet -- that is `reorder_resolved_levels`, a later,
    # separate step this module never calls; see `l2_reorder`). Walk it
    # once, filling the level array at each surviving char's own logical
    # position, and filling the GAPS left by X9's deletions by carrying
    # forward the nearest preceding surviving codepoint's level -- UAX #9's
    # own convention for BN runs, and correct here since a deleted
    # codepoint is always an invisible formatting character, never a
    # grapheme-cluster boundary a caller could land a caret on.
    levels = [base_level] * len(text)
    position = 0
    current = base_level
    for char in storage["chars"]:
        index = char["orig_index"]
        while position < index:
            levels[position] = current
            position += 1
        current = char["level"]
        levels[position] = current
        position += 1
    while position < len(text):
        levels[position] = current
        position += 1

    return BidiLevels(levels=tuple(levels), base_level=base_level)


def level_runs(levels: BidiLevels) -> list[BidiRun]:
    """Maximal same-level spans of *levels*, in LOGICAL order."""
    runs: list[BidiRun] = []
    if not levels.levels:
        return runs
    start = 0
    current = levels.levels[0]
    for index in range(1, len(levels.levels)):
        if levels.levels[index] != current:
            runs.append(BidiRun(start, index, current))
            start, current = index, levels.levels[index]
    runs.append(BidiRun(start, len(levels.levels), current))
    return runs


def l2_reorder(levels: Sequence[int]) -> list[int]:
    """UAX #9 rule L2: a permutation from visual position to logical index.

    ``result[visual_position]`` is the logical index of whatever belongs
    there. Implemented directly against a flat level array rather than by
    re-driving `python-bidi`'s own `reorder_resolved_levels` (which only
    operates on its internal storage dict, one entry per codepoint) --
    deliberately generic over what *one entry* of `levels` represents, so
    the identical function reorders codepoints (a future caller) and
    `ItemRun`s (`itemize.itemize`'s own visual-order pass) alike: L2's
    "reverse contiguous sequences from the highest level down to the
    lowest odd level" is defined purely in terms of one level per item,
    with no assumption about what the item itself is.
    """
    order = list(range(len(levels)))
    if not order:
        return order
    max_level = max(levels)
    odd_levels = [lv for lv in levels if lv % 2 == 1]
    min_odd = min(odd_levels) if odd_levels else max_level + 1
    for threshold in range(max_level, min_odd - 1, -1):
        index = 0
        count = len(order)
        while index < count:
            if levels[order[index]] >= threshold:
                end = index
                while end < count and levels[order[end]] >= threshold:
                    end += 1
                order[index:end] = reversed(order[index:end])
                index = end
            else:
                index += 1
    return order
