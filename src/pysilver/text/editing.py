"""The editing model: text, a selection, and the operations that change them.

Kept apart from any widget on purpose. Editing is where the fiddly rules live
-- what a backspace removes, where a word ends, when two keystrokes are one
undo step -- and every one of them is testable without a window, a font, or a
GPU. `TextFieldElement` supplies keys and pixels; this supplies the answers.

An :class:`EditState` is immutable, so an operation returns a new one and the
undo stack is a list of states rather than a list of inverse operations. For
the sizes a text field holds that is the cheaper thing as well as the simpler
one: no operation needs an inverse, and no inverse can be subtly wrong.

Offsets are Python string indices, and every one this module produces sits on a
**grapheme cluster** boundary (`segment.py`, UAX #29). Backspacing an accented
character removes the character, not the accent; the caret never lands inside a
flag emoji. Selection made the same promise, and an editor that broke it would
be a different kind of surprise: the text would actually change.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

from .bidi import BidiRun, l2_reorder, level_runs, resolve_levels
from .segment import cluster_boundaries

__all__ = [
    "Affinity",
    "EditState",
    "Editor",
    "delete_backward",
    "delete_forward",
    "insert",
    "move",
    "word_bounds",
]

#: Where a caret may go. `word_*` use the whitespace rule below.
MOTIONS: Final = frozenset({"left", "right", "word_left", "word_right", "home", "end"})


class Affinity:
    """Which side of a direction boundary an ambiguous offset means.

    A logical offset is only ever ambiguous exactly AT a boundary between
    two different bidi embedding levels (`text/bidi.py`) -- everywhere
    else, "the content just before this offset" and "the content just
    after it" sit at the identical on-screen position, so affinity is
    consulted nowhere else. `UPSTREAM` means the content already read
    (ending at this offset); `DOWNSTREAM` (the default -- matching a fresh
    caret placement's own natural reading, e.g. a mouse click, which has
    no "which side did I arrive from" to speak of) means the content about
    to be read (starting at this offset).
    """

    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"


@dataclass(frozen=True, slots=True)
class EditState:
    """Text plus a selection.

    Two offsets, not a start and a length: `anchor` is where the selection was
    begun and `focus` is where the caret is now, so shift-arrow knows which end
    to move and a backwards selection is representable rather than normalised
    away the moment it is made.
    """

    text: str = ""
    anchor: int = 0
    focus: int = 0
    #: See `Affinity`. Meaningless everywhere `focus` is not sitting exactly
    #: at a direction boundary -- carried on `EditState` rather than computed
    #: on demand because `move()` is the one place that legitimately needs to
    #: CHOOSE it (which side a horizontal arrow-key press just arrived from),
    #: not just read it back.
    affinity: str = Affinity.DOWNSTREAM

    @property
    def caret(self) -> int:
        return _clamp(self.text, self.focus)

    @property
    def selection(self) -> tuple[int, int]:
        """The selected range, low end first, clamped into the text.

        Clamped because this is a plain dataclass a caller can build with any
        pair of numbers, and every operation below reads the range through
        here. An out-of-range caret that silently deleted nothing would be the
        worst of the available failures: no error, no effect, no clue.
        """
        low = _clamp(self.text, min(self.anchor, self.focus))
        high = _clamp(self.text, max(self.anchor, self.focus))
        return (low, high)

    @property
    def has_selection(self) -> bool:
        return self.anchor != self.focus

    @property
    def selected_text(self) -> str:
        low, high = self.selection
        return self.text[low:high]

    def collapsed(self, offset: int, *, affinity: str = Affinity.DOWNSTREAM) -> EditState:
        """This state with the caret at *offset* and nothing selected."""
        at = _snap(self.text, offset)
        return replace(self, anchor=at, focus=at, affinity=affinity)

    def selecting(
        self, anchor: int, focus: int, *, affinity: str = Affinity.DOWNSTREAM
    ) -> EditState:
        return replace(
            self,
            anchor=_snap(self.text, anchor),
            focus=_snap(self.text, focus),
            affinity=affinity,
        )

    def select_all(self) -> EditState:
        return replace(self, anchor=0, focus=len(self.text))


def _clamp(text: str, offset: int) -> int:
    return max(0, min(offset, len(text)))


def _snap(text: str, offset: int) -> int:
    """Clamp *offset* into the text and onto a grapheme boundary."""
    if not text:
        return 0
    offset = max(0, min(offset, len(text)))
    bounds = cluster_boundaries(text)
    if offset in bounds:
        return offset
    return min(bounds, key=lambda b: (abs(b - offset), b))


def _previous(text: str, offset: int) -> int:
    """The grapheme boundary before *offset*, or 0."""
    previous = [b for b in cluster_boundaries(text) if b < offset]
    return previous[-1] if previous else 0


def _next(text: str, offset: int) -> int:
    """The grapheme boundary after *offset*, or the end."""
    following = [b for b in cluster_boundaries(text) if b > offset]
    return following[0] if following else len(text)


def _run_index_at(offset: int, affinity: str, runs: list[BidiRun]) -> int:
    """Index into *runs* (LOGICAL order) of whichever level-run governs
    *offset*. Only ambiguous exactly AT a boundary between two runs --
    `affinity` picks `UPSTREAM` (the run ENDING here, content already
    read) or `DOWNSTREAM` (the run STARTING here, content about to be
    read); at the very start or end of the text there is only one side.
    """
    if not runs:
        return 0
    if offset <= runs[0].start:
        return 0
    if offset >= runs[-1].end:
        return len(runs) - 1
    for i, run in enumerate(runs):
        if run.start < offset < run.end:
            return i
        if run.end == offset:
            return i if affinity == Affinity.UPSTREAM else i + 1
    return len(runs) - 1  # unreachable given the bounds checked above


def _visual_key(
    offset: int, affinity: str, runs: list[BidiRun], rank_of: dict[int, int]
) -> tuple[int, int]:
    """Sortable ``(run's visual rank, position within that run)`` for
    *offset* -- the shared formula `_visual_positions` and `move()` both
    need, factored out once rather than kept in sync by hand in two
    places. ``rank_of`` maps a LOGICAL run index to its VISUAL rank (0 =
    leftmost), from `bidi.l2_reorder`. Within-run position ascends for an
    even (LTR-parity) run and descends for an odd (RTL-parity) one -- see
    `_visual_positions`'s own docstring for the reasoning.
    """
    run_index = _run_index_at(offset, affinity, runs)
    run = runs[run_index]
    local = (offset - run.start) if run.level % 2 == 0 else (run.end - offset)
    return (rank_of[run_index], local)


def _rank_of_run(runs: list[BidiRun]) -> dict[int, int]:
    """LOGICAL run index -> VISUAL rank (0 = leftmost)."""
    if not runs:
        return {}
    order = l2_reorder([r.level for r in runs])
    return {logical_index: rank for rank, logical_index in enumerate(order)}


def _visual_positions(text: str) -> list[tuple[tuple[int, int], int, str]]:
    """Every grapheme-boundary caret position in *text*, sorted in VISUAL
    order (left to right), as ``(sort_key, offset, affinity)``.

    The mental model that makes this tractable without any pixel data at
    all: within one level-run, visual left-to-right order matches ASCENDING
    logical offset for an even (LTR-parity) run and DESCENDING offset for
    an odd (RTL-parity) run -- exactly `selection.caret_at`'s own per-run
    walk, just expressed over logical text instead of shaped glyphs. Runs
    themselves are ordered visually by `bidi.l2_reorder`, the identical
    function `itemize()` uses to order `ItemRun`s. A boundary offset gets
    two entries (one per affinity), landing at two genuinely different
    points in the sequence -- everywhere else the two affinities agree and
    collapse to one entry.

    Built once per `move()` call, over the WHOLE text rather than walking
    incrementally from the current position: a first draft tried to derive
    the next position from the current one directly (matching whichever
    level was "active" and stepping logically within it), and it is a
    genuinely harder problem than it looks -- verified live by walking the
    right-arrow key repeatedly through mixed text and watching the caret
    cycle between three offsets forever instead of reaching the end. A
    full, explicit ordering sidesteps that failure mode entirely: there is
    no incremental state to get subtly wrong, only "the next entry in an
    already-correct sequence." Cheap enough for anything a text FIELD
    holds; a large `CodeEditor` buffer would want this scoped to one line
    rather than the whole document, not attempted here.
    """
    levels = resolve_levels(text)
    runs = level_runs(levels)
    if not runs:
        return [((0, 0), 0, Affinity.DOWNSTREAM)]
    rank_of = _rank_of_run(runs)
    seen: set[tuple[int, int]] = set()
    entries: list[tuple[tuple[int, int], int, str]] = []
    for offset in cluster_boundaries(text):
        for affinity in (Affinity.UPSTREAM, Affinity.DOWNSTREAM):
            key = _visual_key(offset, affinity, runs, rank_of)
            if key in seen:
                continue
            seen.add(key)
            entries.append((key, offset, affinity))
    entries.sort(key=lambda entry: entry[0])
    return entries


def word_bounds(text: str, offset: int) -> tuple[int, int]:
    """The whitespace-delimited word around *offset*.

    The same rule `selection.word_at` uses for double-click, deliberately: the
    two must agree, or double-clicking a word and then Ctrl-Backspacing it
    would take different amounts of text. It is not UAX #29 word segmentation,
    and saying so is better than implying a Unicode guarantee that is not here.
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


def _word_left(text: str, offset: int) -> int:
    """Start of the word before the caret, skipping any whitespace first."""
    index = offset
    while index > 0 and text[index - 1].isspace():
        index -= 1
    while index > 0 and not text[index - 1].isspace():
        index -= 1
    return index


def _word_right(text: str, offset: int) -> int:
    """End of the word after the caret, skipping any whitespace first."""
    index = offset
    length = len(text)
    while index < length and text[index].isspace():
        index += 1
    while index < length and not text[index].isspace():
        index += 1
    return index


def move(state: EditState, motion: str, *, extend: bool = False) -> EditState:
    """Move the caret. ``extend`` keeps the anchor, which is shift-arrow.

    Without ``extend``, a horizontal move out of a selection lands on the
    *edge* rather than moving from the caret -- press Right with three words
    selected and the caret goes to the end of them, not one character past
    wherever the caret happened to be. Every editor does this, and it is
    invisible until it is missing.

    ``"left"``/``"right"`` are VISUAL directions, resolved against the full
    visual ordering of caret positions (`_visual_positions`): stepping to
    the immediate visual neighbour, one grapheme cluster at a time, in
    whichever direction the key names. Inside an even (LTR-parity) level
    this walks forward/backward through the text exactly like plain LTR
    content; inside an odd (RTL-parity) level the two invert, matching how
    a real bidi-aware editor's arrow keys behave inside right-to-left
    content -- and the ordering is genuinely global, not derived
    incrementally from the current position, specifically because an
    incremental "which level is active, step within it" approach turned out
    to cycle forever between three offsets near a direction boundary rather
    than making steady progress (see `_visual_positions`'s own docstring).
    Only these two motions are bidi-aware -- ``word_left``/``word_right``/
    ``home``/``end`` stay plain logical-offset moves, matching this
    module's own existing, unextended scope for them (a real limitation,
    not silently missing: word motion across a direction boundary is
    deferred, same as bidi-aware Up/Down across a wrapped line already is
    -- see the module docstring).
    """
    if motion not in MOTIONS:
        raise ValueError(f"unknown motion {motion!r}")
    text = state.text
    low, high = state.selection

    if not extend and state.has_selection and motion in ("left", "right"):
        return state.collapsed(low if motion == "left" else high)

    focus = state.focus
    affinity = Affinity.DOWNSTREAM
    if motion in ("left", "right"):
        positions = _visual_positions(text)
        runs = level_runs(resolve_levels(text))
        rank_of = _rank_of_run(runs)
        current_key = _visual_key(focus, state.affinity, runs, rank_of)
        # `_visual_positions` enumerates every (offset, affinity) pair that
        # exists, so `current_key` -- built from the SAME formula -- is
        # always an exact member; a plain linear search (this list is at
        # most 2x the text's own grapheme-cluster count, cheap for
        # anything a text field holds) is simpler to trust than a `bisect`
        # that assumes it and never checks.
        index = next(i for i, entry in enumerate(positions) if entry[0] == current_key)
        index = max(0, min(len(positions) - 1, index + (1 if motion == "right" else -1)))
        _, target, affinity = positions[index]
    elif motion == "word_left":
        target = _word_left(text, focus)
    elif motion == "word_right":
        target = _word_right(text, focus)
    elif motion == "home":
        target = 0
    else:
        target = len(text)

    if extend:
        return state.selecting(state.anchor, target, affinity=affinity)
    return state.collapsed(target, affinity=affinity)


def insert(state: EditState, text: str) -> EditState:
    """Insert *text*, replacing the selection if there is one."""
    if not text:
        return state
    low, high = state.selection
    body = state.text[:low] + text + state.text[high:]
    at = low + len(text)
    return EditState(body, at, at)


def delete_backward(state: EditState, *, word: bool = False) -> EditState:
    """Backspace. Deletes the selection if there is one, otherwise one cluster."""
    low, high = state.selection
    if low != high:
        return EditState(state.text[:low] + state.text[high:], low, low)
    if low == 0:
        return state
    start = _word_left(state.text, low) if word else _previous(state.text, low)
    return EditState(state.text[:start] + state.text[low:], start, start)


def delete_forward(state: EditState, *, word: bool = False) -> EditState:
    """Delete. Deletes the selection if there is one, otherwise one cluster."""
    low, high = state.selection
    if low != high:
        return EditState(state.text[:low] + state.text[high:], low, low)
    if high >= len(state.text):
        return state
    end = _word_right(state.text, high) if word else _next(state.text, high)
    return EditState(state.text[:low] + state.text[end:], low, low)


class Editor:
    """An :class:`EditState` with undo and redo around it.

    Typing coalesces: a run of single characters entered one after another is
    one undo step, because undoing a sentence letter by letter is nobody's idea
    of undo. The run breaks when the kind of edit changes, when the caret is
    somewhere the run did not leave it, or when a selection is replaced -- the
    same three rules a text editor uses, and the reason the last kind and the
    expected caret are both tracked rather than just the state.

    A pure caret move is not an edit and is not recorded. Undo restores the
    text *and* the selection, which is what makes an undone deletion leave you
    where you were rather than at the end of the field.
    """

    __slots__ = ("_last_caret", "_last_kind", "_redo", "_undo", "limit", "state")

    def __init__(self, text: str = "", *, limit: int = 200) -> None:
        end = len(text)
        self.state = EditState(text, end, end)
        self._undo: list[EditState] = []
        self._redo: list[EditState] = []
        self._last_kind: str | None = None
        self._last_caret: int = -1
        #: A bounded history: a long-lived field would otherwise keep every
        #: state anyone ever typed into it for the life of the process.
        self.limit = limit

    # ------------------------------------------------------------- content

    @property
    def text(self) -> str:
        return self.state.text

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def set_text(self, text: str) -> None:
        """Replace the content from outside -- a bound `value:` changing.

        Clears the history rather than recording a step. The new text did not
        come from the user, so offering to undo back to what they had typed
        would restore something the application has already moved past.
        """
        if text == self.state.text:
            return
        end = len(text)
        self.state = EditState(text, end, end)
        self._undo.clear()
        self._redo.clear()
        self._last_kind = None

    # --------------------------------------------------------------- edits

    def edit(self, new: EditState, kind: str) -> bool:
        """Adopt *new* as an edit of the given kind. Returns whether text changed.

        `kind` is what decides coalescing, so it is the caller's statement of
        intent rather than something inferred from the diff: two states can
        look alike whether the user typed a letter or pasted one.
        """
        if new.text == self.state.text:
            self.state = new
            return False
        coalesce = (
            kind == "type"
            and self._last_kind == "type"
            and self.state.caret == self._last_caret
            and not self.state.has_selection
        )
        if not coalesce:
            self._undo.append(self.state)
            if len(self._undo) > self.limit:
                del self._undo[0]
        self._redo.clear()
        self.state = new
        self._last_kind = kind
        self._last_caret = new.caret
        return True

    def select(self, anchor: int, focus: int) -> None:
        self.state = self.state.selecting(anchor, focus)
        self._last_kind = None

    def set_caret(self, offset: int) -> None:
        self.state = self.state.collapsed(offset)
        self._last_kind = None

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.state)
        self.state = self._undo.pop()
        self._last_kind = None
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.state)
        self.state = self._redo.pop()
        self._last_kind = None
        return True
