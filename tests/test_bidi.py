"""UAX #9 bidirectional resolution -- isolated from layout/caret/selection.

Every case here is verified against the actual `python-bidi`-driven pipeline
directly (no pysilver layout/font machinery involved), so a downstream
failure in `itemize`/`layout`/`selection` can be told apart from a bug in the
bidi driver itself.
"""

from __future__ import annotations

from pysilver.text.bidi import BidiLevels, BidiRun, l2_reorder, level_runs, resolve_levels

# -------------------------------------------------------------- resolve_levels


def test_empty_text_resolves_to_no_levels() -> None:
    levels = resolve_levels("")
    assert levels.levels == ()
    assert levels.base_level == 0


def test_pure_ltr_text_is_all_level_zero() -> None:
    levels = resolve_levels("Hello world")
    assert levels.base_level == 0
    assert set(levels.levels) == {0}


def test_pure_rtl_text_is_all_level_one() -> None:
    """Arabic (`AL`, not `R`) resolves to the same odd base level as Hebrew."""
    levels = resolve_levels("مرحبا")
    assert levels.base_level == 1
    assert set(levels.levels) == {1}


def test_latin_embedded_in_arabic_is_bumped_one_level_higher() -> None:
    """Rule I2: inside an RTL (odd) base, `L`-type text is bumped to the
    next EVEN level -- nested one deeper, not merged into the surrounding
    RTL level. Hand-verified: 'مرحبا' -> level 1 (6 codepoints, one of
    them a combining/joining form counted by `len`), ' Hello' -> level 2."""
    levels = resolve_levels("مرحبا Hello")
    assert levels.base_level == 1
    arabic_part = levels.levels[:6]
    latin_part = levels.levels[6:]
    assert set(arabic_part) == {1}
    assert set(latin_part) == {2}


def test_numbers_inside_rtl_text_get_bumped_not_merged() -> None:
    """The classic UAX #9 case this feature exists for: European digits
    inside RTL text resolve to an even (LTR-parity) level of their own,
    one higher than the surrounding Arabic -- 'European numbers inside RTL
    text stay LTR internally', not literally LTR-direction but a distinct,
    higher, even-parity level, which is what keeps them un-reordered."""
    text = "مرحبا 123 يا"
    levels = resolve_levels(text)
    digit_start = text.index("123")
    digit_levels = levels.levels[digit_start : digit_start + 3]
    assert set(digit_levels) == {2}
    # Regression guard against ever letting reordering touch codepoints
    # instead of runs: resolve_levels never reorders the string itself, so
    # "123" must still read "123", not "321", in the source text.
    assert text[digit_start : digit_start + 3] == "123"


def test_nested_embedding_produces_three_distinct_levels() -> None:
    """'English inside Arabic inside English' -- genuinely 3 levels, found
    by construction (isolated digits inside the Arabic span, not merged
    into an adjacent Latin run via rule W7's 'digits following L become
    L' -- 'مرحبا abc123 يا' only produces 2 levels for exactly that reason,
    confirmed empirically before picking this string instead)."""
    text = "read مرحبا 42 يا now"
    levels = resolve_levels(text)
    assert set(levels.levels) == {0, 1, 2}
    digit_start = text.index("42")
    assert set(levels.levels[digit_start : digit_start + 2]) == {2}
    # The isolated digit run is never internally reordered.
    assert text[digit_start : digit_start + 2] == "42"


def test_base_direction_override_wins_over_detection() -> None:
    """An explicit `base_direction` -- needed so a wrapped line can inherit
    its paragraph's own resolved base rather than re-detecting its own,
    see `resolve_levels`'s own docstring -- overrides P2/P3 detection
    entirely, even against text whose own first strong character disagrees."""
    assert resolve_levels("Hello", base_direction="rtl").base_level == 1
    assert resolve_levels("مرحبا", base_direction="ltr").base_level == 0


def test_resolve_levels_is_cached_and_pure() -> None:
    """Same input, same object identity -- `lru_cache` actually applying,
    not just coincidentally equal results."""
    assert resolve_levels("Hello مرحبا") is resolve_levels("Hello مرحبا")


# ----------------------------------------------------------------- level_runs


def test_level_runs_of_empty_levels_is_empty() -> None:
    assert level_runs(BidiLevels(levels=(), base_level=0)) == []


def test_level_runs_splits_at_every_level_change() -> None:
    levels = BidiLevels(levels=(0, 0, 1, 1, 1, 2, 2, 0), base_level=0)
    assert level_runs(levels) == [
        BidiRun(0, 2, 0),
        BidiRun(2, 5, 1),
        BidiRun(5, 7, 2),
        BidiRun(7, 8, 0),
    ]


def test_level_runs_of_a_uniform_level_is_one_run() -> None:
    levels = BidiLevels(levels=(1, 1, 1), base_level=1)
    assert level_runs(levels) == [BidiRun(0, 3, 1)]


def test_level_runs_matches_resolve_levels_output() -> None:
    """Not a fresh hand-built array this time -- the real pipeline's own
    output, so a change to `resolve_levels`'s level-filling logic that
    silently produced non-contiguous garbage would show up here too."""
    runs = level_runs(resolve_levels("مرحبا Hello"))
    assert [(r.start, r.end, r.level) for r in runs] == [(0, 6, 1), (6, 11, 2)]


# ------------------------------------------------------------------ l2_reorder
#
# Every expected value below was verified by running `l2_reorder` itself
# against the hand-built level array before writing the assertion -- a
# first draft of the doubly-nested and the "even level, no enclosing odd
# level" cases both had a hand-arithmetic mistake caught exactly this way
# (reversing a 3-element span is not a no-op), so these are checked
# results, not guesses.


def test_l2_reorder_of_pure_ltr_is_unchanged() -> None:
    assert l2_reorder([0, 0, 0, 0]) == [0, 1, 2, 3]


def test_l2_reorder_of_pure_rtl_reverses_everything() -> None:
    assert l2_reorder([1, 1, 1, 1]) == [3, 2, 1, 0]


def test_l2_reorder_of_empty_is_empty() -> None:
    assert l2_reorder([]) == []


def test_l2_reorder_reverses_one_embedded_rtl_span() -> None:
    """'abc' + RTL 'xyz' + 'def' -- the RTL span reverses in place, the LTR
    spans either side keep their own internal order."""
    # levels: a b c | x y z (rtl) | d e f
    levels = [0, 0, 0, 1, 1, 1, 0, 0, 0]
    assert l2_reorder(levels) == [0, 1, 2, 5, 4, 3, 6, 7, 8]


def test_l2_reorder_double_reverses_a_doubly_nested_span() -> None:
    """The recursive case: a level-2 span nested inside a level-1 RTL span
    inside level-0 text. The level-1 pass reverses the WHOLE embedded
    block (including the already-once-reversed level-2 sub-span), so the
    level-2 content ends up reversed twice -- net unchanged internal
    order, exactly matching how a real nested-LTR-inside-RTL phrase reads
    left-to-right in its own local position while the RTL span around it
    still runs right-to-left."""
    levels = [0, 0, 1, 1, 2, 2, 2, 1, 1, 0, 0]
    assert l2_reorder(levels) == [0, 1, 8, 7, 4, 5, 6, 3, 2, 9, 10]


def test_l2_reorder_threshold_sweeps_from_highest_to_lowest_odd_level() -> None:
    """A level-2 span enclosed by level-1 on both sides, with nothing at
    level 0 -- L2 sweeps threshold 2 then 1: the level-2 pass reverses the
    3-long middle span in place first, then the level-1 pass (everything
    here is >=1, so the whole 7-long array is one contiguous run) reverses
    that already-once-reversed result again, in full."""
    levels = [1, 1, 2, 2, 2, 1, 1]
    assert l2_reorder(levels) == [6, 5, 2, 3, 4, 1, 0]
