"""Bundled assets: the default font stack.

A font is bundled rather than resolved from the OS for two reasons
(ARCHITECTURE.md §5.7.2): a framework that renders nothing until the user
configures a font path is not usable out of the box, and golden-image tests
cannot be deterministic against whatever fonts a CI runner happens to have.

See ``fonts/README.md`` for provenance and licensing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

__all__ = [
    "DEFAULT_FONT",
    "FALLBACK_CHAIN",
    "FONT_DIR",
    "MEDIUM_FONT",
    "MONOSPACE_FONT",
    "font_path",
]

FONT_DIR: Final = Path(__file__).parent / "fonts"

#: Material Design 3's default typeface for its type scale.
DEFAULT_FONT: Final = FONT_DIR / "Roboto-Regular.ttf"

#: Weight 500, for `label-large` and other medium-weight type-scale roles.
MEDIUM_FONT: Final = FONT_DIR / "Roboto-Medium.ttf"

#: Resolution order for FontDB. Mirrors M3's Roboto -> Noto Sans chain;
#: Roboto Flex is excluded because M3 states it is not part of the typescale.
#: Arabic/Hebrew are appended, not inserted -- order between disjoint-script
#: members doesn't matter, but appending after the existing Latin/Greek/
#: Cyrillic member preserves every already-covered codepoint's golden-image
#: bytes. Narrow, per-script Noto members, not the omnibus multi-script
#: build M3's own full fallback collection would require (119 MB + 299 MB
#: CJK, still excluded -- see `fonts/README.md`).
FALLBACK_CHAIN: Final = (
    DEFAULT_FONT,
    FONT_DIR / "NotoSans-Regular.ttf",
    FONT_DIR / "NotoSansArabic-Regular.ttf",
    FONT_DIR / "NotoSansHebrew-Regular.ttf",
)

#: Not part of M3's type scale (M3 has no concept of a monospace role) --
#: bundled specifically for Terminal/CodeEditor, whose cell/cursor grid math
#: assumes every glyph has the same advance width. Deliberately NOT in
#: `FALLBACK_CHAIN`: an ordinary `Text` widget has no reason to ever silently
#: fall back to a monospace face carrying ~9,000 icon glyphs. Hack Nerd Font
#: Mono, not plain Hack -- Nerd Fonts' own glyph patch is what closes the
#: Arrows/Dingbats/Private-Use-Area coverage gap that icon-heavy shell prompt
#: themes (starship, fish-pure, `eza --icons`) otherwise render as tofu
#: boxes. See `fonts/README.md` for provenance and a licensing note: the
#: font's own embedded metadata is MIT + Bitstream Vera, not the OFL the
#: `nerd-fonts` project's top-level `LICENSE` claims for patched fonts.
MONOSPACE_FONT: Final = FONT_DIR / "HackNerdFontMono-Regular.ttf"


def font_path(name: str) -> Path:
    """Absolute path to a bundled font file. Raises if it is not present."""
    path = FONT_DIR / name
    if not path.is_file():
        available = sorted(p.name for p in FONT_DIR.glob("*.ttf"))
        raise FileNotFoundError(f"no bundled font {name!r}; available: {available}")
    return path
