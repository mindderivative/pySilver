"""The text pipeline: faces, segmentation, itemisation, shaping, layout."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from pysilver.assets import DEFAULT_FONT, MEDIUM_FONT
from pysilver.spec.typescale import TYPE_SCALE
from pysilver.text import (
    Direction,
    Face,
    FontDB,
    FontRequest,
    ShapeCache,
    TextEngine,
    itemize,
    layout_text,
    shape_run,
)
from pysilver.text.itemize import script_runs
from pysilver.text.layout import Alignment
from pysilver.text.segment import (
    break_opportunities,
    cluster_boundaries,
    clusters,
    next_boundary,
    previous_boundary,
)


@pytest.fixture(scope="module")
def db() -> FontDB:
    return FontDB()


@pytest.fixture(scope="module")
def face(db: FontDB) -> Face:
    return db.face_for(FontRequest())


# ------------------------------------------------------------------- faces


def test_face_reports_family_and_weight(face: Face) -> None:
    assert face.family == "Roboto"
    assert face.weight == 400


def test_metrics_scale_with_size(face: Face) -> None:
    small, large = face.metrics(10.0), face.metrics(20.0)
    assert large.line_height > small.line_height
    assert large.ascent > small.ascent


def test_line_height_is_ascent_descent_and_gap(face: Face) -> None:
    m = face.metrics(16.0)
    assert m.line_height == pytest.approx(m.ascent + m.descent + m.line_gap)


def test_rasterises_a_glyph(face: Face) -> None:
    bitmap = face.rasterize(face.glyph_for(ord("A")), 32.0)
    assert bitmap.width > 0 and bitmap.height > 0
    assert bitmap.coverage.dtype == np.uint8
    assert bitmap.coverage.max() > 0


def test_whitespace_rasterises_blank(face: Face) -> None:
    """Blank glyphs must not consume atlas space."""
    assert face.rasterize(face.glyph_for(ord(" ")), 32.0).is_blank


def test_unsupported_codepoint_is_notdef(face: Face) -> None:
    assert face.glyph_for(0x4F60) == 0
    assert not face.covers(0x4F60)


def test_coverage_spans_latin_greek_cyrillic(face: Face) -> None:
    assert face.covers(ord("A"))
    assert face.covers(0x03B1), "greek alpha"
    assert face.covers(0x0416), "cyrillic zhe"


# ------------------------------------------------------------------ fontdb


def test_loads_the_bundled_stack(db: FontDB) -> None:
    families = {f.family for f in db.faces}
    assert families == {"Roboto", "Noto Sans", "Noto Sans Arabic", "Noto Sans Hebrew"}


def test_selects_by_weight(db: FontDB) -> None:
    assert db.face_for(FontRequest("Roboto", 500)).path == MEDIUM_FONT
    assert db.face_for(FontRequest("Roboto", 400)).path == DEFAULT_FONT


def test_falls_back_to_nearest_weight(db: FontDB) -> None:
    assert db.face_for(FontRequest("Roboto", 900)).weight == 500


def test_fallback_chain_order(db: FontDB) -> None:
    """M3's chain is Roboto then Noto Sans; Arabic/Hebrew are appended after,
    narrow single-script members with no ordering constraint between them."""
    assert [f.family for f in db.fallback_chain] == [
        "Roboto",
        "Noto Sans",
        "Noto Sans Arabic",
        "Noto Sans Hebrew",
    ]


def test_fallback_resolves_a_codepoint_roboto_lacks(db: FontDB) -> None:
    """The fallback tier must actually be reachable, not decorative."""
    only_noto = sorted(set(db.fallback_chain[1].coverage) - set(db.fallback_chain[0].coverage))
    assert only_noto, "Noto adds nothing over Roboto"
    char = chr(only_noto[0])
    assert db.resolve(char, FontRequest()).family == "Noto Sans"


def test_unresolvable_text_falls_back_to_primary(db: FontDB) -> None:
    """Missing glyphs render .notdef -- visible, not a silent gap."""
    assert db.resolve("你", FontRequest()).family == "Roboto"
    assert list(db.missing("A你")) == ["你"]


# ------------------------------------------------------------ segmentation


def test_line_breaks_keep_apostrophes_intact() -> None:
    text = "The quick can't dog-house."
    cuts = [0, *[o.offset for o in break_opportunities(text)]]
    segments = [text[a:b] for a, b in pairwise(cuts)]
    assert "can't " in segments


def test_line_breaks_allow_a_break_after_a_hyphen() -> None:
    assert any(o.trailing_space == 0 for o in break_opportunities("dog-house"))


def test_only_hard_terminators_are_mandatory() -> None:
    assert [o.mandatory for o in break_opportunities("a\nb c")] == [True, False, False]


def test_grapheme_clusters_hold_zwj_sequences_together() -> None:
    text = "áé \U0001f469‍\U0001f469‍\U0001f467"
    assert len(clusters(text)) == 4
    assert clusters(text)[-1] == "\U0001f469‍\U0001f469‍\U0001f467"


def test_caret_moves_by_cluster_not_codepoint() -> None:
    """A caret must jump the whole emoji, never land inside it."""
    text = "a\U0001f469‍\U0001f467b"
    bounds = cluster_boundaries(text)
    assert next_boundary(text, 1) == bounds[2]
    assert previous_boundary(text, bounds[2]) == 1


# ------------------------------------------------------------- itemisation


def test_neutral_punctuation_does_not_split_a_run(db: FontDB) -> None:
    assert len(itemize("Hello, world!", db)) == 1


def test_scripts_split_into_separate_runs(db: FontDB) -> None:
    runs = itemize("Hello مرحبا", db)
    assert [r.script for r in runs] == ["Latn", "Arab"]


def test_direction_follows_script(db: FontDB) -> None:
    runs = itemize("Hello مرحبا", db)
    assert runs[0].direction == Direction.LTR
    assert runs[1].direction == Direction.RTL
    assert runs[1].is_rtl
    # `.level` (text/bidi.py's UAX #9 resolution) is the source of truth
    # `.direction`/`.is_rtl` are derived from -- base is LTR (first strong
    # char 'H'), so the embedded Arabic is bumped exactly one level up
    # (rule I1: even base + AL type -> +1), not reset to some fixed "RTL"
    # constant.
    assert runs[0].level == 0
    assert runs[1].level == 1


def test_rtl_paragraph_reverses_run_order(db: FontDB) -> None:
    ltr = itemize("Hello مرحبا", db)
    rtl = itemize("مرحبا Hello", db)
    assert ltr[0].script == "Latn"
    assert rtl[0].script == "Latn", "RTL paragraph should place runs in visual order"


def test_a_level_boundary_splits_a_run_even_when_script_alone_would_not(db: FontDB) -> None:
    """A digit span inside Arabic is script-neutral ('Zyyy'), which
    `script_runs` alone would glue onto the preceding Arabic run -- but it
    sits at its own, higher bidi level (rule I2), so `itemize` must still
    split it into its own `ItemRun`. Confirmed first that `script_runs`
    really would merge the whole string into one span before asserting
    `itemize` doesn't."""
    text = "مرحبا 123 يا"
    assert script_runs(text) == [(0, len(text), "Arab")], (
        "script alone should merge this whole string -- the real test is that level "
        "splitting still separates it"
    )
    runs = itemize(text, db, visual_order=False)
    digit_runs = [r for r in runs if r.text == "123"]
    assert len(digit_runs) == 1
    assert digit_runs[0].level == 2
    # And its neighbours on both sides stay at the surrounding Arabic level.
    assert all(r.level == 1 for r in runs if r is not digit_runs[0])


# ----------------------------------------------------------------- shaping


def test_ligatures_form(face: Face) -> None:
    """GSUB. freetype alone cannot do this."""
    assert len(shape_run("fi film", face)) < len("fi film")


def test_gpos_kerning_is_applied(face: Face) -> None:
    """Modern fonts kern via GPOS, which freetype does not apply."""
    kerned = shape_run("AVA Wa To", face).width_units
    plain = shape_run("AVA Wa To", face, features={"kern": False}).width_units
    assert kerned < plain


def test_clusters_map_glyphs_back_to_source(face: Face) -> None:
    """The only link from a rendered glyph to the source string."""
    run = shape_run("fi film", face)
    assert run.clusters[0] == 0
    assert int(run.clusters[-1]) == len("fi film") - 1
    assert np.all(np.diff(run.clusters) >= 0)


def test_glyph_ids_agree_with_freetype(face: Face) -> None:
    """The seam the two-library design rests on."""
    run = shape_run("A", face)
    assert int(run.glyphs[0]) == face.glyph_for(ord("A"))


def test_shaping_is_size_independent(face: Face) -> None:
    run = shape_run("Hello", face)
    assert run.width(32.0) == pytest.approx(run.width(16.0) * 2)


def test_empty_text_shapes_to_nothing(face: Face) -> None:
    assert len(shape_run("", face)) == 0


def test_shape_cache_hits_on_repeat(face: Face) -> None:
    """A miss on unchanged text is a performance bug (ARCHITECTURE.md 12)."""
    cache = ShapeCache()
    for _ in range(5):
        cache.get("hello", face)
    assert cache.stats == (4, 1)


def test_shape_cache_is_not_discarded_when_empty(face: Face) -> None:
    """An empty cache is falsy; `cache or ShapeCache()` would silently drop it."""
    cache = ShapeCache()
    db = FontDB()
    layout_text("hello world", db, px=14, cache=cache)
    assert cache.stats[1] > 0, "caller's cache was ignored"


# ------------------------------------------------------------------ layout


def test_single_line_when_unbounded(db: FontDB) -> None:
    para = layout_text("Hello, world!", db, px=16)
    assert para.line_count == 1
    assert para.size.width > 0


def test_wrapping_respects_max_width(db: FontDB) -> None:
    text = "The quick brown fox jumps over the lazy dog and keeps running"
    para = layout_text(text, db, px=14, max_width=180)
    assert para.line_count > 1
    for line in para.lines:
        assert line.width <= 180.0 + 0.5


def test_hard_breaks_split_lines(db: FontDB) -> None:
    assert layout_text("one\ntwo\nthree", db, px=14).line_count == 3


def test_a_trailing_space_on_unwrapped_text_still_has_width(db: FontDB) -> None:
    """Found live via the Link demo: 'Read the ' immediately followed by a
    sibling `Link` widget rendered as 'Read theM3...' with no gap at all.
    `_wrap_block`'s final "flush the remainder" step (`layout.py`) stripped
    trailing whitespace from that segment's width unconditionally -- correct
    for a real mid-paragraph wrap point (`_emit`'s own rstrip, unaffected by
    this fix), wrong when nothing ever wrapped and the "remainder" is the
    whole block. A sentence built from several sibling widgets (a `Text`, a
    `Link`, another `Text`) relies on each one's own trailing/leading space
    for the visible gap between them."""
    with_space = layout_text("Read the ", db, px=14, max_width=500)
    without_space = layout_text("Read the", db, px=14, max_width=500)
    assert with_space.lines[0].width > without_space.lines[0].width


def test_lines_stack_without_overlapping(db: FontDB) -> None:
    para = layout_text("alpha beta gamma delta epsilon zeta", db, px=14, max_width=100)
    baselines = [line.baseline for line in para.lines]
    assert baselines == sorted(baselines)
    assert all(b - a >= 1.0 for a, b in pairwise(baselines))


def test_alignment_offsets_lines(db: FontDB) -> None:
    start = layout_text("hi", db, px=14, max_width=200, alignment=Alignment.START)
    centre = layout_text("hi", db, px=14, max_width=200, alignment=Alignment.CENTER)
    end = layout_text("hi", db, px=14, max_width=200, alignment=Alignment.END)
    assert start.lines[0].x == 0
    assert 0 < centre.lines[0].x < end.lines[0].x


def test_placements_advance_left_to_right(db: FontDB) -> None:
    places = layout_text("Hello", db, px=16).placements()
    xs = [p.x for p in places]
    assert xs == sorted(xs)
    assert len({p.gid for p in places}) > 1


def test_empty_text_still_has_line_height(db: FontDB) -> None:
    para = layout_text("", db, px=16)
    assert para.size.width == 0
    assert para.size.height > 0


def test_unbreakable_word_overflows_rather_than_vanishing(db: FontDB) -> None:
    para = layout_text("Supercalifragilistic", db, px=20, max_width=20)
    assert para.line_count >= 1
    assert sum(len(line.runs) for line in para.lines) > 0


# ------------------------------------------------------------- text engine


def test_engine_memoises_layouts() -> None:
    te = TextEngine()
    first = te.layout("Hello", px=16)
    assert te.layout("Hello", px=16) is first


def test_engine_layout_cache_does_not_grow_unbounded() -> None:
    """A widget whose text changes every keystroke (TextField, CodeEditor)
    must not leak one Paragraph per edit for the life of the process."""
    te = TextEngine(layout_cache_size=64)
    for i in range(1000):
        te.layout(f"distinct string number {i}", px=16)
    assert len(te._layouts) <= 64


def test_engine_layout_cache_keeps_recently_used_entries() -> None:
    te = TextEngine(layout_cache_size=8)
    kept = te.layout("kept", px=16)
    for i in range(20):
        te.layout(f"filler {i}", px=16)
        te.layout("kept", px=16)  # touched every iteration, so never LRU-oldest
    assert te.layout("kept", px=16) is kept


def test_engine_layout_coalesces_close_widths_into_one_cache_entry() -> None:
    """A resize drag changes `max_width` by roughly one pixel per frame; this
    is the fix for the pointer-trailing regression a live drag-resize caused
    on the widget-demo apps -- see `_WRAP_WIDTH_BUCKET_PX`'s own docstring."""
    te = TextEngine()
    text = "The quick brown fox jumps over the lazy dog and keeps running"
    # 289..304 all round up to the same 16px bucket (304 = 19 * 16).
    first = te.layout(text, px=14, max_width=289.0)
    for w in range(290, 305):
        assert te.layout(text, px=14, max_width=float(w)) is first


def test_engine_layout_never_gives_less_room_than_requested() -> None:
    """Bucketing rounds up, never down: a request for exactly its own ink
    width must still fit on one line, or the knife-edge single-line
    invariant (`test_text_laid_out_at_its_own_ink_width_stays_on_one_line`)
    would break for any widget whose ink width isn't already a bucket
    multiple."""
    te = TextEngine()
    unwrapped = te.layout("title-small", px=14)
    rewrapped = te.layout("title-small", px=14, max_width=unwrapped.size.width)
    assert rewrapped.line_count == 1


def test_engine_measure_matches_layout() -> None:
    te = TextEngine()
    assert te.measure("Hello", px=16) == te.layout("Hello", px=16).size


def test_engine_emits_glyph_instances() -> None:
    from pysilver.paint import DisplayList, Kind

    te = TextEngine()
    dl = DisplayList()
    n = te.emit(dl, te.layout("Hi", px=16), x=0, y=0)
    assert n == len(dl) == 2
    assert all(i["flags"][0] == Kind.GLYPH for i in dl.view)


def test_engine_skips_blank_glyphs() -> None:
    from pysilver.paint import DisplayList

    te = TextEngine()
    dl = DisplayList()
    te.emit(dl, te.layout("a b", px=16), x=0, y=0)
    assert len(dl) == 2, "the space should not be emitted"


def test_higher_dpi_rasterises_larger() -> None:
    from pysilver.paint import DisplayList

    te = TextEngine()
    lo, hi = DisplayList(), DisplayList()
    para = te.layout("W", px=16)
    te.emit(lo, para, x=0, y=0, pixel_ratio=1.0)
    te.emit(hi, para, x=0, y=0, pixel_ratio=2.0)
    assert hi.view[0]["rect"][2] > lo.view[0]["rect"][2]


# ------------------------------------------------- wrapping at the ink width


@pytest.mark.parametrize("role", sorted(TYPE_SCALE))
def test_text_laid_out_at_its_own_ink_width_stays_on_one_line(role: str) -> None:
    """The knife-edge every `Text` sits on.

    A Text shrink-wraps to its ink extent and the paint pass then lays it out
    again at exactly that width, so this fit test is evaluated at precise
    equality on every frame that draws unwrapped text. It has to hold with no
    slack at all.

    It broke when candidate widths began coming from a cumulative-advance
    table: `np.sum` adds pairwise and `np.cumsum` sequentially, and at
    `title-small` the two orders differ by 7e-15 px. That was enough to wrap
    "title-small" to "title-" / "small", so the widget measured one line and
    painted two, and the golden showed rows overlapping. The pixels caught it;
    this states the rule directly.
    """
    style = TYPE_SCALE[role]
    request = FontRequest(weight=style.weight)
    kwargs = {"px": style.size, "request": request, "tracking": style.tracking}
    unwrapped = layout_text(role, FontDB(), max_width=None, **kwargs)
    rewrapped = layout_text(role, FontDB(), max_width=unwrapped.size.width, **kwargs)
    assert rewrapped.line_count == 1, (
        f"{role!r} wrapped when laid out at its own {unwrapped.size.width} px width"
    )
    assert rewrapped.size.width == pytest.approx(unwrapped.size.width)


def test_a_line_is_broken_where_it_genuinely_exceeds_the_box() -> None:
    """The other side of the epsilon: it must not let real overflow through.
    A tolerance loose enough to hide a wrap would be worse than the bug."""
    para = layout_text("aaaa bbbb", FontDB(), px=14.0, max_width=None)
    assert (
        layout_text("aaaa bbbb", FontDB(), px=14.0, max_width=para.size.width - 1.0).line_count == 2
    )
