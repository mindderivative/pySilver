"""Per-glyph colour: colouring parts of a paragraph differently.

The feature two widgets on the backlog cannot exist without -- a code editor
needs syntax highlighting and a terminal needs ANSI colour, and both are the
same requirement. Everything before this coloured a paragraph with exactly one
token.

Spans are expressed in **source offsets**, not glyph indices, because that is
what a lexer or an escape-sequence parser produces, and because the two do not
correspond: a ligature is one glyph for several characters. The mapping happens
in one place so that every consumer gets ligatures right identically.
"""

from __future__ import annotations

import numpy as np
import pytest

from pysilver.paint import NO_TOKEN, DisplayList
from pysilver.paint.display_list import Kind
from pysilver.text import FontDB, TextEngine, layout_text

RED = (1.0, 0.0, 0.0, 1.0)
BLUE = (0.0, 0.0, 1.0, 1.0)


@pytest.fixture(scope="module")
def engine():
    return TextEngine()


def emitted(engine, text: str, spans=None, token: int = NO_TOKEN, **kw):
    para = layout_text(text, engine.db if hasattr(engine, "db") else FontDB(), px=16.0, **kw)
    dl = DisplayList()
    engine.emit(dl, para, x=0.0, y=0.0, token=token, spans=spans)
    return [i for i in dl.view if i["flags"][0] == Kind.GLYPH]


def tokens_of(instances):
    return [int(i["flags"][2]) for i in instances]


def colors_of(instances):
    return [tuple(round(float(c), 3) for c in i["fill"]) for i in instances]


# ------------------------------------------------------------------ mapping


def test_a_span_colours_only_the_glyphs_it_covers(engine) -> None:
    """`def foo` -- the keyword one colour, the name another.

    Six quads, not seven: a blank glyph is skipped entirely, so glyph count
    does not track character count. That is exactly why spans are addressed in
    source offsets, and it would be an off-by-one in every consumer if they
    were not.
    """
    glyphs = emitted(engine, "def foo", spans=[(0, 3, 7)], token=3)
    assert tokens_of(glyphs) == [7, 7, 7, 3, 3, 3], "the span ends at 3, exclusive"


def test_text_outside_every_span_keeps_the_callers_own_colour(engine) -> None:
    """Spans need not cover the text. Anything uncovered is ordinary text, not
    a hole."""
    glyphs = emitted(engine, "abcdef", spans=[(2, 4, 9)], token=1)
    assert tokens_of(glyphs) == [1, 1, 9, 9, 1, 1]


def test_spans_may_be_given_in_any_order(engine) -> None:
    """A lexer emits them in order; an ANSI parser reconstructing a screen may
    not. Sorting here costs nothing and removes a sharp edge."""
    forwards = tokens_of(emitted(engine, "abcdef", spans=[(0, 2, 5), (4, 6, 8)], token=1))
    backwards = tokens_of(emitted(engine, "abcdef", spans=[(4, 6, 8), (0, 2, 5)], token=1))
    assert forwards == backwards == [5, 5, 1, 1, 8, 8]


def test_a_literal_colour_span_sets_the_fill_and_clears_the_token(engine) -> None:
    """ANSI's 24-bit colours are not palette roles, so they cannot be tokens.
    The token must be cleared or the shader would resolve it and ignore the
    literal entirely."""
    glyphs = emitted(engine, "ab", spans=[(0, 1, RED)], token=4)
    assert tokens_of(glyphs) == [NO_TOKEN, 4]
    assert colors_of(glyphs)[0] == RED


def test_token_and_literal_spans_coexist(engine) -> None:
    glyphs = emitted(engine, "abcd", spans=[(0, 2, 6), (2, 4, BLUE)], token=1)
    assert tokens_of(glyphs) == [6, 6, NO_TOKEN, NO_TOKEN]
    assert colors_of(glyphs)[2] == BLUE


def test_spans_survive_wrapping(engine) -> None:
    """Offsets are paragraph-absolute, so a span that straddles a line break
    must still land on the right glyphs -- the case where a per-line mapping
    would quietly go wrong."""
    text = "alpha beta gamma"
    glyphs = emitted(engine, text, spans=[(6, 10, 7)], max_width=70.0)
    assert tokens_of(glyphs).count(7) == 4, "'beta' is four glyphs, on whichever line"


# ------------------------------------------------------------------- limits


def test_no_spans_writes_a_broadcast_scalar(engine) -> None:
    """The performance claim. Unhighlighted text must not pay for a feature it
    does not use, so the arrays are not built at all."""
    from pysilver.text import _span_arrays

    assert _span_arrays(None, [1, 2, 3], (1.0, 1.0, 1.0, 1.0), 5) == (None, None)
    assert _span_arrays([], [1, 2, 3], (1.0, 1.0, 1.0, 1.0), 5) == (None, None)


def test_the_mapping_is_vectorised_not_a_lookup_per_glyph() -> None:
    """§12's rule: per-glyph Python misses the frame budget, and a syntax
    highlighted editor is exactly where that would bite. Asserted on the output
    type, since that is what proves whole columns were written."""
    from pysilver.text import _span_arrays

    colors, tokens = _span_arrays([(0, 2, 5)], [0, 1, 2, 3], (1.0, 1.0, 1.0, 1.0), 1)
    assert isinstance(colors, np.ndarray) and colors.shape == (4, 4)
    assert isinstance(tokens, np.ndarray) and tokens.shape == (4,)
    assert tokens.tolist() == [5, 5, 1, 1]
