"""SVG icons: compiling arbitrary vector artwork into glyphs.

Route A for SVG support (ARCHITECTURE.md, the widget-backlog design
discussion): artwork becomes a font, so it flows through the existing
FontDB/atlas/rasteriser pipeline unchanged rather than adding a second
rendering path next to the one that already exists.

Pixel-level correctness (orientation, the winding traps below) is checked
directly against `Face.rasterize`'s output, not asserted from reading the
transform math -- an SVG's Y-down space, a font's Y-up space, and a winding
rule are exactly the kind of thing that looks right on paper and renders
upside down or hollow-the-wrong-way in practice.
"""

from __future__ import annotations

import pytest

from pysilver.paint import DisplayList, Kind
from pysilver.text import TextEngine
from pysilver.text.svgicons import compile_svg_font, load_svg_icons

TRIANGLE = (
    '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M4 20 L20 20 L12 4 Z"/></svg>'
)

#: A real ring: two circles, wound OPPOSITE directions (outer sweep=0, inner
#: sweep=1) -- the default `fill-rule="nonzero"`, and what every common SVG
#: export tool produces for a hole.
RING = (
    '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M12 2 A10 10 0 1 0 12.01 2 Z M12 8 A6 6 0 1 1 11.99 8 Z"/></svg>'
)

#: The same ring, but both circles wound the SAME direction -- valid SVG only
#: under `fill-rule="evenodd"`, which glyf cannot express (§ module docstring).
RING_EVENODD = (
    '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<path fill-rule="evenodd" d="M12 2 A10 10 0 1 1 11.99 2 Z '
    'M12 8 A6 6 0 1 1 11.99 8 Z"/></svg>'
)


def center_coverage(icons, name: str, px: float = 64.0) -> int:
    gid = icons.glyph(name)
    bmp = icons.face.rasterize(gid, px)
    return int(bmp.coverage[bmp.height // 2, bmp.width // 2])


# --------------------------------------------------------------- compiling


def test_compiling_assigns_private_use_area_codepoints(tmp_path) -> None:
    """Never a printable character -- a name lookup must not collide with
    something a real string could contain."""
    codepoints = compile_svg_font({"triangle": TRIANGLE}, tmp_path / "icons.ttf")
    assert codepoints == {"triangle": 0xE000}


def test_compiling_several_icons_assigns_distinct_codepoints(tmp_path) -> None:
    codepoints = compile_svg_font({"triangle": TRIANGLE, "ring": RING}, tmp_path / "icons.ttf")
    assert codepoints == {"triangle": 0xE000, "ring": 0xE001}


def test_a_path_source_is_read_a_string_source_is_not(tmp_path) -> None:
    """The two source kinds are never confused: a Path is a file to open, a
    str is markup already in hand. Guessing from content would mean a string
    that happens to look like a path gets silently opened -- exactly the
    ambiguity `spec/include.py` refuses for the same underlying reason."""
    svg_file = tmp_path / "triangle.svg"
    svg_file.write_text(TRIANGLE)
    codepoints = compile_svg_font(
        {"from_file": svg_file, "from_string": TRIANGLE}, tmp_path / "icons.ttf"
    )
    assert set(codepoints) == {"from_file", "from_string"}


def test_no_viewbox_raises_rather_than_guessing_a_size(tmp_path) -> None:
    no_viewbox = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L10 0 L5 10 Z"/></svg>'
    with pytest.raises(ValueError, match="viewBox"):
        compile_svg_font({"x": no_viewbox}, tmp_path / "icons.ttf")


# -------------------------------------------------------------- IconSet


def test_load_svg_icons_returns_a_usable_icon_set(tmp_path) -> None:
    icons = load_svg_icons({"triangle": TRIANGLE}, tmp_path / "icons.ttf")
    assert "triangle" in icons
    assert icons.glyph("triangle") != 0  # not .notdef


def test_the_custom_names_do_not_fall_back_to_material_symbols(tmp_path) -> None:
    """The regression this module actually hit while being built:
    `IconSet(face)` with no `names` silently resolves against the BUNDLED
    218-name table, so every real lookup on a custom set raised "unknown
    icon" despite the font compiling correctly. `load_svg_icons` must pass
    its own names explicitly."""
    icons = load_svg_icons({"triangle": TRIANGLE}, tmp_path / "icons.ttf")
    assert "home" not in icons, "resolved against the bundled Material Symbols table"
    assert icons.names == ["triangle"]


# --------------------------------------------------------- pixel correctness


def test_the_triangle_points_up_not_down(tmp_path) -> None:
    """The orientation check. `M4 20 L20 20 L12 4 Z` puts its apex at SVG
    y=4 (near the top of the viewBox) and its base at y=20 (near the
    bottom). If the Y-flip from SVG space into the font's y-up glyf space
    were wrong, this would rasterise upside down -- plausible-looking, and
    exactly the kind of bug a picture doesn't catch by itself (the polygon
    SDF's own 6-o'clock vertex bug looked like a fine triangle too)."""
    icons = load_svg_icons({"triangle": TRIANGLE}, tmp_path / "icons.ttf")
    bmp = icons.face.rasterize(icons.glyph("triangle"), 64.0)
    cov = bmp.coverage
    top_third = cov[: bmp.height // 3, :]
    bottom_third = cov[-bmp.height // 3 :, :]
    # An upward triangle is narrow (little ink) near its apex at the top and
    # wide (much ink) near its base at the bottom.
    assert top_third.sum() < bottom_third.sum()


def test_a_hole_wound_the_common_way_survives(tmp_path) -> None:
    """`fill-rule="nonzero"` (SVG's default) with the hole wound opposite to
    the shape it cuts from -- what every common export tool produces. This is
    the case Route A has to get right, since it is the overwhelming majority
    of real-world icon SVGs."""
    icons = load_svg_icons({"ring": RING}, tmp_path / "icons.ttf")
    assert center_coverage(icons, "ring") < 20, "the hole was filled in"


def test_a_hole_relying_on_evenodd_is_a_documented_limitation(tmp_path) -> None:
    """The other winding convention -- valid SVG, and not supported. `glyf`
    has no per-contour fill-rule flag; FreeType always fills by nonzero. This
    is not a bug to fix here; it is the reason the module docstring says so
    plainly rather than leaving it to be discovered as a silently wrong icon.
    """
    icons = load_svg_icons({"ring": RING_EVENODD}, tmp_path / "icons.ttf")
    assert center_coverage(icons, "ring") > 200, (
        "if this starts passing, the evenodd limitation in the module "
        "docstring is no longer true and should be corrected"
    )


def test_two_unrelated_icons_do_not_affect_each_others_scale(tmp_path) -> None:
    """Each icon is scaled from its OWN viewBox. A tiny-viewBox icon next to
    a huge-viewBox one must not come out a different visual size."""
    small_vb = (
        '<svg viewBox="0 0 2 2" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M0 0 L2 0 L1 2 Z"/></svg>'
    )
    huge_vb = (
        '<svg viewBox="0 0 2000 2000" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M0 0 L2000 0 L1000 2000 Z"/></svg>'
    )
    icons = load_svg_icons({"small": small_vb, "huge": huge_vb}, tmp_path / "icons.ttf")
    a = icons.face.rasterize(icons.glyph("small"), 64.0)
    b = icons.face.rasterize(icons.glyph("huge"), 64.0)
    assert a.width == pytest.approx(b.width, abs=2)
    assert a.height == pytest.approx(b.height, abs=2)


# --------------------------------------------------------------- integration


def test_emit_icon_draws_a_custom_icon_through_the_real_pipeline(tmp_path) -> None:
    """No change to `TextEngine.emit_icon` was needed -- the whole point of
    compiling to a real glyph. A custom `IconSet` swapped in is indistinguishable
    from Material Symbols to everything downstream of it."""
    icons = load_svg_icons({"triangle": TRIANGLE}, tmp_path / "icons.ttf")
    engine = TextEngine()
    engine._icons = icons
    dl = DisplayList()
    drew = engine.emit_icon(dl, "triangle", x=0.0, y=0.0, size=24.0)
    assert drew is True
    assert len(dl) == 1
    assert int(dl.view[0]["flags"][0]) == Kind.GLYPH


def test_an_unknown_custom_icon_name_raises_with_the_real_count(tmp_path) -> None:
    icons = load_svg_icons({"triangle": TRIANGLE}, tmp_path / "icons.ttf")
    with pytest.raises(KeyError, match="1 icons are bundled"):
        icons.glyph("does_not_exist")
