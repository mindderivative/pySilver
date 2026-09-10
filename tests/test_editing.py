"""The editing model, with no widget attached.

Every rule a text field has to get right is here rather than behind a window:
what a backspace removes, where a word ends, when two keystrokes are one undo
step. A test that has to open a canvas to check that Ctrl-Backspace eats a word
is a test nobody runs.
"""

from __future__ import annotations

import pytest

from pysilver.text.editing import (
    Affinity,
    Editor,
    EditState,
    delete_backward,
    delete_forward,
    insert,
    move,
    word_bounds,
)

HELLO = EditState("hello world", 11, 11)
#: "e" plus a combining acute -- two code points, one grapheme cluster.
DECOMPOSED = "cafe\u0301"
#: A regional-indicator pair. Python sees two characters, a reader sees a flag.
FLAG = "a\U0001f1ec\U0001f1e7"


# ---------------------------------------------------------------- selection


def test_a_selection_remembers_which_end_the_caret_is_on() -> None:
    """Anchor and focus, not start and length: shift-arrow has to know which
    end to move, and a backwards selection is a real thing a user makes."""
    backwards = EditState("hello", 4, 1)
    assert backwards.selection == (1, 4)
    assert backwards.caret == 1
    assert backwards.selected_text == "ell"


def test_an_empty_selection_is_not_a_selection() -> None:
    assert not EditState("hello", 2, 2).has_selection
    assert EditState("hello", 2, 3).has_selection


def test_offsets_snap_to_grapheme_boundaries() -> None:
    """The caret cannot land between a letter and its accent, because the next
    keystroke would then split them."""
    assert EditState(DECOMPOSED).collapsed(5).caret == 5
    assert EditState(DECOMPOSED).collapsed(4).caret in (3, 5), "never inside the cluster"


def test_offsets_outside_the_text_are_clamped() -> None:
    assert EditState("abc").collapsed(99).caret == 3
    assert EditState("abc").collapsed(-5).caret == 0


# ------------------------------------------------------------------ motion


def test_arrow_keys_move_one_cluster() -> None:
    assert move(HELLO, "left").caret == 10
    assert move(HELLO.collapsed(0), "right").caret == 1


def test_moving_over_a_combining_mark_takes_the_whole_cluster() -> None:
    state = EditState(DECOMPOSED, 5, 5)
    assert move(state, "left").caret == 3, "e and its accent move together"


def test_moving_over_a_flag_takes_both_halves() -> None:
    state = EditState(FLAG, len(FLAG), len(FLAG))
    assert move(state, "left").caret == 1


def test_home_and_end_go_to_the_ends() -> None:
    assert move(HELLO, "home").caret == 0
    assert move(HELLO.collapsed(0), "end").caret == 11


def test_word_motion_skips_the_space_before_the_word() -> None:
    assert move(HELLO, "word_left").caret == 6
    assert move(EditState("hello world", 6, 6), "word_left").caret == 0
    assert move(EditState("hello world", 0, 0), "word_right").caret == 5


def test_shift_arrow_extends_from_the_anchor() -> None:
    extended = move(move(HELLO, "left", extend=True), "left", extend=True)
    assert extended.selection == (9, 11)
    assert extended.anchor == 11, "the anchor stayed where the selection began"


def test_an_unextended_arrow_collapses_to_the_edge_of_a_selection() -> None:
    """Press Right with three words selected and the caret goes to the end of
    them -- not one character past wherever the caret happened to sit. Every
    editor does this, and it is invisible until it is missing.
    """
    selected = EditState("hello world", 2, 8)
    assert move(selected, "right").caret == 8
    assert move(selected, "left").caret == 2
    assert not move(selected, "left").has_selection


def test_an_unknown_motion_is_an_error() -> None:
    with pytest.raises(ValueError, match="unknown motion"):
        move(HELLO, "sideways")


# ---------------------------------------------------------------- bidi motion


def test_right_moves_backward_through_pure_rtl_text() -> None:
    """Inverted from LTR: inside RTL content, visual Right is logically
    BACKWARD (toward the text's own start) and visual Left is FORWARD --
    the mirror image `test_arrow_keys_move_one_cluster` already asserts
    for plain LTR text."""
    state = EditState("مرحبا", 2, 2)
    assert move(state, "right").focus == 1
    assert move(state, "left").focus == 3


def test_repeated_right_crosses_a_direction_boundary_without_getting_stuck() -> None:
    """The real bug this design was built to avoid: an early draft that
    derived each step incrementally from the current position oscillated
    forever between three offsets near a direction boundary instead of
    reaching the end of the text. Walking Right from the very start must
    visit every offset (the boundary offset twice, since it has two
    genuinely different on-screen positions -- see `_visual_positions`),
    then hold at the VISUALLY rightmost one and stop -- which is offset 3
    (the Arabic word's own reading-START, downstream-affinitized), not
    `len(text)` (offset 8, its reading-end): the RTL word's start renders
    further right than its own end, so "keep pressing Right" legitimately
    terminates there, not at the highest logical offset."""
    text = "lo مرحبا"
    state = EditState(text, 0, 0)
    path = [state.focus]
    for _ in range(12):
        state = move(state, "right")
        path.append(state.focus)
    assert set(path) == set(range(len(text) + 1)), "every offset must be reached at least once"
    boundary = text.index("م")
    assert path[-1] == path[-2] == boundary
    assert state.affinity == Affinity.DOWNSTREAM


def test_repeated_left_from_the_start_of_arabic_reading_holds() -> None:
    """The mirror of the above: walking Left repeatedly from the RTL
    word's own reading-start (offset 3, downstream) must reach every
    offset and then hold at offset 0 -- the visually LEFTMOST position,
    which for this string coincides with the true start of the text."""
    text = "lo مرحبا"
    boundary = text.index("م")
    state = EditState(text, boundary, boundary, affinity=Affinity.DOWNSTREAM)
    path = [state.focus]
    for _ in range(12):
        state = move(state, "left")
        path.append(state.focus)
    assert set(path) == set(range(len(text) + 1))
    assert path[-1] == path[-2] == 0


def test_move_at_a_direction_boundary_uses_the_landing_affinity() -> None:
    """A move that lands exactly on a boundary offset records which side
    it arrived at, not the field's own default -- proven by checking the
    resulting `EditState.affinity`, not just `.focus`, matches whichever
    of the two boundary positions the walk actually reached.

    Both approaches use the key that moves TOWARD the boundary given each
    side's own direction: visual Right from inside the LTR prefix (2 ->
    3), and visual Right from inside the RTL word too -- Right is
    logically BACKWARD inside RTL content (`test_right_moves_backward_
    through_pure_rtl_text`), so it is what walks from offset 4 back down
    to the same boundary offset 3, just arriving from the opposite side.
    """
    text = "lo مرحبا"
    boundary = text.index("م")
    # Arriving at the boundary from the LTR side lands on its LEFT-hand
    # rendering -- the "lo " run's own end.
    from_ltr = move(EditState(text, 2, 2), "right")
    assert from_ltr.focus == boundary
    assert from_ltr.affinity == Affinity.UPSTREAM
    # Arriving at it from the RTL side lands on its RIGHT-hand rendering --
    # the Arabic run's own start.
    from_rtl = move(EditState(text, boundary + 1, boundary + 1), "right")
    assert from_rtl.focus == boundary
    assert from_rtl.affinity == Affinity.DOWNSTREAM


# ------------------------------------------------------------------- edits


def test_insert_puts_text_at_the_caret() -> None:
    assert insert(EditState("hello", 5, 5), "!").text == "hello!"
    assert insert(EditState("hello", 0, 0), ">").caret == 1


def test_insert_replaces_a_selection() -> None:
    assert insert(EditState("hello world", 6, 11), "there").text == "hello there"


def test_backspace_removes_one_cluster_not_one_character() -> None:
    """The whole reason offsets go through the segmenter: backspacing an
    accented character has to remove the character, not leave a bare accent."""
    assert delete_backward(EditState(DECOMPOSED, 5, 5)).text == "caf"
    assert delete_backward(EditState(FLAG, 3, 3)).text == "a"


def test_backspace_removes_a_selection_whole() -> None:
    assert delete_backward(EditState("hello world", 5, 11)).text == "hello"


def test_backspace_at_the_start_does_nothing() -> None:
    start = EditState("hello", 0, 0)
    assert delete_backward(start) == start


def test_delete_removes_forwards() -> None:
    assert delete_forward(EditState("hello", 0, 0)).text == "ello"
    assert delete_forward(EditState("hello", 5, 5)).text == "hello", "at the end, nothing"


def test_word_deletion_matches_word_motion() -> None:
    assert delete_backward(HELLO, word=True).text == "hello "
    assert delete_forward(EditState("hello world", 0, 0), word=True).text == " world"


def test_an_out_of_range_caret_still_edits_sanely() -> None:
    """Nothing in the widget produces one, but `EditState` is a plain dataclass
    and a caller can build anything. Silently deleting nothing would be the
    worst of the options."""
    assert delete_backward(EditState("abc", 99, 99)).text == "ab"


# ------------------------------------------------------------------- words


def test_word_bounds_agrees_with_selection_double_click() -> None:
    """They must: double-clicking a word and then Ctrl-Backspacing it should
    take the same text. Both use the whitespace rule, which is not UAX #29 and
    is documented as such rather than implied to be Unicode-correct."""
    from pysilver.text.selection import word_at

    for offset in range(len("hello world")):
        assert word_bounds("hello world", offset) == word_at("hello world", offset)


# -------------------------------------------------------------------- undo


def test_typing_a_run_is_one_undo_step() -> None:
    """Undoing a sentence letter by letter is nobody's idea of undo."""
    editor = Editor("")
    for character in "hello":
        editor.edit(insert(editor.state, character), "type")
    assert editor.text == "hello"
    assert editor.undo()
    assert editor.text == ""


def test_a_caret_move_breaks_the_run() -> None:
    editor = Editor("")
    for character in "ab":
        editor.edit(insert(editor.state, character), "type")
    editor.set_caret(0)
    editor.edit(insert(editor.state, "X"), "type")
    editor.undo()
    assert editor.text == "ab", "the move started a new step"


def test_a_deletion_is_its_own_step() -> None:
    editor = Editor("hello")
    editor.edit(insert(editor.state, "!"), "type")
    editor.edit(delete_backward(editor.state), "delete")
    assert editor.text == "hello"
    editor.undo()
    assert editor.text == "hello!"


def test_undo_restores_the_selection_too() -> None:
    """So an undone deletion leaves you where you were, rather than at the end
    of the field wondering what happened."""
    editor = Editor("hello world")
    editor.select(6, 11)
    editor.edit(delete_backward(editor.state), "delete")
    assert editor.text == "hello "
    editor.undo()
    assert editor.state.selection == (6, 11)


def test_redo_replays_and_a_new_edit_discards_it() -> None:
    editor = Editor("a")
    editor.edit(insert(editor.state, "b"), "type")
    editor.undo()
    assert editor.can_redo
    editor.redo()
    assert editor.text == "ab"
    editor.undo()
    editor.edit(insert(editor.state, "c"), "type")
    assert not editor.can_redo, "the redo branch was abandoned"


def test_undo_on_an_untouched_editor_reports_it_did_nothing() -> None:
    editor = Editor("hello")
    assert not editor.undo()
    assert not editor.redo()
    assert editor.text == "hello"


def test_an_external_value_clears_the_history() -> None:
    """A bound `value:` changing did not come from the user, so offering to
    undo back to what they typed would restore something the application has
    already moved past."""
    editor = Editor("draft")
    editor.edit(insert(editor.state, "!"), "type")
    editor.set_text("from the application")
    assert not editor.can_undo
    assert editor.text == "from the application"


def test_the_history_is_bounded() -> None:
    """A long-lived field would otherwise keep every state anyone ever typed
    into it for the life of the process."""
    editor = Editor("", limit=5)
    for index in range(20):
        # A kind that never coalesces, so every one is its own step.
        editor.edit(insert(editor.state, str(index)), "delete")
    assert len(editor._undo) == 5


def test_an_edit_that_changes_nothing_is_not_a_step() -> None:
    editor = Editor("hello")
    assert not editor.edit(delete_backward(EditState("hello", 0, 0)), "delete")
    assert not editor.can_undo
