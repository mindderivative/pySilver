"""The bundled font stack. Golden-image determinism depends on these existing."""

from __future__ import annotations

import pytest
from fontTools.ttLib import TTFont

from pysilver.assets import DEFAULT_FONT, FALLBACK_CHAIN, FONT_DIR, MEDIUM_FONT, font_path


def test_default_font_is_present() -> None:
    assert DEFAULT_FONT.is_file()


def test_fallback_chain_files_all_exist() -> None:
    for path in FALLBACK_CHAIN:
        assert path.is_file(), path


def test_chain_starts_with_the_default() -> None:
    """M3's chain is Roboto -> Noto Sans; Roboto must be tried first."""
    assert FALLBACK_CHAIN[0] == DEFAULT_FONT


def test_licences_are_shipped_beside_the_fonts() -> None:
    """OFL requires the licence to be redistributed with the font."""
    for name in ("LICENSE-Roboto.txt", "LICENSE-NotoSans.txt"):
        text = (FONT_DIR / name).read_text(encoding="utf-8")
        assert "SIL OPEN FONT LICENSE" in text.upper()


@pytest.mark.parametrize(
    ("path", "family", "weight"),
    [
        (DEFAULT_FONT, "Roboto", 400),
        (MEDIUM_FONT, "Roboto", 500),
        (FONT_DIR / "NotoSans-Regular.ttf", "Noto Sans", 400),
        (FONT_DIR / "NotoSansArabic-Regular.ttf", "Noto Sans Arabic", 400),
        (FONT_DIR / "NotoSansHebrew-Regular.ttf", "Noto Sans Hebrew", 400),
    ],
)
def test_font_metadata(path, family: str, weight: int) -> None:
    tt = TTFont(path, lazy=True)
    names = {r.nameID: str(r) for r in tt["name"].names if r.platformID == 3}
    assert (names.get(16) or names.get(1)) == family
    assert tt["OS/2"].usWeightClass == weight
    tt.close()


#: Each bundled font: the licence it is distributed under, and the string its
#: embedded name record must contain (None when the font declares no licence
#: record, as Material Symbols does -- its terms come from the repo LICENSE).
EXPECTED_LICENCES = {
    "Roboto-Regular.ttf": ("OFL 1.1", "Open Font License"),
    "Roboto-Medium.ttf": ("OFL 1.1", "Open Font License"),
    "NotoSans-Regular.ttf": ("OFL 1.1", "Open Font License"),
    "NotoSansArabic-Regular.ttf": ("OFL 1.1", "Open Font License"),
    "NotoSansHebrew-Regular.ttf": ("OFL 1.1", "Open Font License"),
    # Not OFL, despite the `nerd-fonts` project's own top-level LICENSE
    # claiming patched fonts are -- this font's own embedded nameID-13
    # record says otherwise (checked directly), so that is what is
    # vendored and tested against. See `fonts/README.md`'s Licensing
    # section.
    "HackNerdFontMono-Regular.ttf": ("MIT + Bitstream Vera", "MIT License"),
    "MaterialSymbolsOutlined-Subset.ttf": ("Apache-2.0", None),
}

#: Licence text that must ship for each font, since both OFL and Apache-2.0
#: require redistribution of the licence.
LICENCE_FILES = {
    "Roboto-Regular.ttf": "LICENSE-Roboto.txt",
    "Roboto-Medium.ttf": "LICENSE-Roboto.txt",
    "NotoSans-Regular.ttf": "LICENSE-NotoSans.txt",
    "NotoSansArabic-Regular.ttf": "LICENSE-NotoSansArabic.txt",
    "NotoSansHebrew-Regular.ttf": "LICENSE-NotoSansHebrew.txt",
    "HackNerdFontMono-Regular.ttf": "LICENSE-HackNerdFontMono.txt",
    "MaterialSymbolsOutlined-Subset.ttf": "LICENSE-MaterialSymbols.txt",
}


def test_every_bundled_font_is_accounted_for() -> None:
    """A new font must be added here deliberately, with its licence recorded."""
    shipped = {p.name for p in FONT_DIR.glob("*.ttf")}
    assert shipped == set(EXPECTED_LICENCES)
    assert shipped == set(LICENCE_FILES)


def test_embedded_licence_records_match() -> None:
    for path in FONT_DIR.glob("*.ttf"):
        _, expected = EXPECTED_LICENCES[path.name]
        tt = TTFont(path, lazy=True)
        record = next(
            (str(r) for r in tt["name"].names if r.nameID == 13 and r.platformID == 3),
            None,
        )
        tt.close()
        if expected is None:
            continue  # declares none; covered by the licence-file test below
        assert record and expected in record, f"{path.name}: {str(record)[:60]!r}"


def test_licence_texts_ship_alongside_the_fonts() -> None:
    """Both OFL and Apache-2.0 require the licence to be redistributed.

    This is the only licence guarantee for Material Symbols, which embeds no
    licence record of its own.
    """
    for font, licence in LICENCE_FILES.items():
        path = FONT_DIR / licence
        assert path.is_file(), f"{font} ships no licence text ({licence})"
        assert path.read_text(encoding="utf-8").strip(), f"{licence} is empty"


def test_fallback_widens_coverage() -> None:
    """Each fallback tier must actually add codepoints, or it is dead weight."""

    def cps(p):
        tt = TTFont(p, lazy=True)
        out = set(tt.getBestCmap())
        tt.close()
        return out

    default = cps(DEFAULT_FONT)
    assert len(cps(FALLBACK_CHAIN[1]) - default) > 1000
    # Arabic/Hebrew: smaller, narrowly-scoped members (~1500/~460 codepoints
    # total), so the bar is real coverage, not the four-figure threshold the
    # much broader Latin/Greek/Cyrillic member clears.
    assert len(cps(FALLBACK_CHAIN[2]) - default) > 500
    assert len(cps(FALLBACK_CHAIN[3]) - default) > 100


def test_arabic_and_hebrew_text_no_longer_falls_through_to_notdef() -> None:
    """The real gap this bundling closes: RTL text used to render as tofu."""
    from pysilver.text.fontdb import FontDB, FontRequest

    db = FontDB()
    request = FontRequest()
    # A word each, not a lone codepoint -- `resolve()` snaps to grapheme
    # clusters, and a single test that only ever asked for one codepoint
    # wouldn't catch a face that covers isolated forms but not the
    # contextual shaping cmap entries real words need.
    for word, family in (("مرحبا", "Noto Sans Arabic"), ("שלום", "Noto Sans Hebrew")):
        for char in word:
            face = db.resolve(char, request)
            assert face.covers_all(char), f"{char!r} in {word!r} falls through to .notdef"
            assert face.family == family


def test_font_path_rejects_unknown_names() -> None:
    with pytest.raises(FileNotFoundError, match="no bundled font"):
        font_path("Comic Sans.ttf")
