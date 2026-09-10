# Bundled fonts

pySilver ships a default font so that it renders text out of the box and so
that golden-image tests are deterministic (ARCHITECTURE.md §5.7.2, §11). Text
tests must never resolve a font through the OS: shaping output and rasterised
coverage vary between font versions, so a system-resolved face produces
different bytes on every machine and every CI image.

## What is here, and why

Material Design 3 names **Roboto** as the default typeface of its type scale,
and **Noto Sans** as the fallback collection, with the chain
`Roboto Flex -> Roboto -> Noto Sans`
(`M3-References/styles/M3-Styles-Typography-Fonts.md`). Roboto Flex is excluded
deliberately: the same page states it "isn't yet part of the M3 typescale".

| File | Size | Weight | Codepoints | Role |
|---|---|---|---|---|
| `Roboto-Regular.ttf` | 154 KB | 400 | 927 | Default face |
| `Roboto-Medium.ttf` | 154 KB | 500 | 927 | `label-large` and other medium-weight type-scale roles |
| `NotoSans-Regular.ttf` | 612 KB | 400 | 3094 | Fallback tier -- Latin/Greek/Cyrillic |
| `NotoSansArabic-Regular.ttf` | 190 KB | 400 | 1561 | Fallback tier -- Arabic |
| `NotoSansHebrew-Regular.ttf` | 47 KB | 400 | 464 | Fallback tier -- Hebrew |
| `HackNerdFontMono-Regular.ttf` | 2.65 MB | 400 | 12,415 | `MONOSPACE_FONT` -- Terminal's and CodeEditor's default face |

| `MaterialSymbolsOutlined-Subset.ttf` | 102 KB | variable | 218 icons | Material Symbols |

Total ≈ 3.8 MB.

## Monospace

M3 names no monospace typeface -- it has no such role. `HackNerdFontMono-Regular.ttf`
is bundled anyway, specifically for `Terminal` (`widgets/terminal.py`) and
`CodeEditor` (`widgets/codeeditor.py`): a terminal's cell/cursor grid is
positioned by `column * cell_width` regardless of what glyphs a run actually
shapes to, which only lines up when every glyph shares one advance width, and
a code editor's own column alignment (indentation, aligned comments, ASCII
diagrams) needs the identical property. Found live, 2026-09-08: with the
previous default (Roboto, proportional), five lowercase letters like `hello`
measured ~2.5 cell-widths narrower than the grid assumed, so the cursor
visibly detached from typed text by several columns after only a few
keystrokes -- confirmed by direct measurement (`TextEngine.measure`), and
confirmed fixed the same way against `HackNerdFontMono-Regular.ttf`: `M`,
`i`, and `hello` all measure an identical 9.633px per glyph at 16px, zero
drift -- including a Nerd Font icon glyph (Powerline separator U+E0B0),
checked directly against the font's own `hmtx` table since it is not
ordinary Latin content `TextEngine.measure` would exercise incidentally.
Not part of `FALLBACK_CHAIN` -- an ordinary `Text` widget has no reason to
fall back to a monospace face carrying ~9,000 icon glyphs -- exported
separately as `assets.MONOSPACE_FONT` instead. (`NotoSansMono-Regular.ttf`
served this role from 2026-09-08 until it was superseded below.)

## Icons

Material Symbols is a **variable icon font**, so icons render through the same
glyph pipeline as text (ARCHITECTURE.md §5.7.8). The full outlined font is
10.6 MB for ~4,275 icons; this is a `fontTools` subset of a curated 218-icon
core set covering the M3 component catalogue, with `GRAD` and `opsz` pinned and
`FILL` (0–1) and `wght` (100–700) kept live — 102 KB, a 102× reduction.

Source:

```
https://github.com/google/material-design-icons/raw/master/variablefont/MaterialSymbolsOutlined[FILL,GRAD,opsz,wght].ttf
```

It is licensed **Apache-2.0**, not OFL, and embeds no licence name record — its
terms come from that repository's `LICENSE`, vendored here as
`LICENSE-MaterialSymbols.txt`. `material_symbols.json` maps icon names to
codepoints.

Noto Sans adds 2,187 codepoints beyond Roboto — 841 extended Latin, 289 Greek,
533 combining marks and modifiers, 129 Devanagari, 115 Cyrillic. It is the
**Latin/Greek/Cyrillic** Noto family, so it widens coverage *within* those
scripts. `NotoSansArabic-Regular.ttf` (1561 codepoints) and
`NotoSansHebrew-Regular.ttf` (464 codepoints) add real Arabic and Hebrew
coverage on top of that — narrow, single-script Noto members, not the
omnibus multi-script build M3's own full fallback collection would need
(119 MB, plus 299 MB for CJK, still cannot be shipped in a Python package,
so CJK and emoji stay deferred to system font discovery past v1). These two
are what make real UAX #9 bidirectional text (`text/bidi.py`) actually
demonstrable rather than structurally-present-but-untestable: the bundled
stack had zero Arabic/Hebrew coverage before this, confirmed empirically
(every codepoint fell through to `.notdef`).

`HackNerdFontMono-Regular.ttf`'s ~9,000 Nerd Font icon glyphs are a separate,
unrelated icon system from Material Symbols above — they live in Arrows,
Dingbats, and Private-Use-Area codepoints (Powerline separators, devicons,
Octicons, Font Awesome, and others the Nerd Fonts patcher aggregates), the
exact ranges icon-heavy shell prompt themes (starship, fish-pure,
`eza --icons`) draw from and that the previous Roboto/Noto Sans-only stack
rendered as tofu (found live, `pySilver Terminal Symbol Glyph Coverage Gap`).
They are reachable only through `MONOSPACE_FONT`, not `FALLBACK_CHAIN` — an
ordinary `Text` widget never requests them.

## Provenance

Roboto, Noto Sans, Noto Sans Arabic, and Noto Sans Hebrew were taken from the
canonical `google/fonts` repository, which publishes them only as variable
fonts. The static faces here were produced with `fontTools.varLib.instancer`,
pinning `wght` (400 / 500) and `wdth` (100):

```
https://github.com/google/fonts/raw/main/ofl/roboto/Roboto[wdth,wght].ttf
https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans[wdth,wght].ttf
https://github.com/google/fonts/raw/main/ofl/notosansarabic/NotoSansArabic[wdth,wght].ttf
https://github.com/google/fonts/raw/main/ofl/notosanshebrew/NotoSansHebrew[wdth,wght].ttf
```

Instancing rather than shipping the variable fonts saves several MB and keeps
the font loader simple: no variation axes to configure at load time. Noto
Sans Hebrew's own default instance is weight 100 (Thin), unlike the other
three families' own default of 400 — pinning `wght=400` explicitly is what
makes this one Regular rather than Thin; checked directly (`fvar` axes),
not assumed to match the others.

`HackNerdFontMono-Regular.ttf` is taken as-is (already a static TTF, no
`fvar` table, nothing to instance) from the `nerd-fonts` project's `v3.5.1`
release:

```
https://github.com/ryanoasis/nerd-fonts/releases/download/v3.5.1/Hack.zip
```
(`HackNerdFontMono-Regular.ttf` inside the zip; the release also ships Bold/
Italic/BoldItalic and non-Mono/Windows-compatible variants, none bundled
here — only Regular is needed, matching every other bundled family's
single-weight-per-role convention.)

## Licensing

Roboto, Noto Sans, Noto Sans Arabic, and Noto Sans Hebrew are all under the
**SIL Open Font License 1.1** — see `LICENSE-Roboto.txt`, `LICENSE-NotoSans.txt`,
`LICENSE-NotoSansArabic.txt`, and `LICENSE-NotoSansHebrew.txt`, which must be
redistributed with them. OFL is compatible with pySilver's MIT licence; the
fonts remain under OFL and are not relicensed. The Arabic/Hebrew copyright
lines differ from Noto Sans's own (`github.com/notofonts/arabic` and
`.../hebrew`, vs. `.../latin-greek-cyrillic`) — checked directly, not assumed
identical — but the OFL boilerplate itself is byte-identical.

Note that Roboto was **relicensed**: copies predating the move to `ofl/` in
`google/fonts` (for example the v2.137 build from 2017 still shipped by some
distributions) carry Apache-2.0 instead. The files here are OFL.

**`HackNerdFontMono-Regular.ttf` is MIT + Bitstream Vera, not OFL** — a real
correction, not an assumption. The `nerd-fonts` project's own top-level
`LICENSE` file claims "Nerd Fonts source fonts, patched fonts... are
licensed under SIL OPEN FONT LICENSE Version 1.1," but the font's own
embedded name-table record (checked directly with `fontTools`, nameID 13)
says nothing of the kind: it states the Hack project is MIT (Source Foundry,
2018), DejaVu is public domain, and Bitstream Vera Sans Mono carries the
Bitstream Vera License — the same text as the release's own `LICENSE.md`,
word-for-word. The patcher apparently never updated this font's embedded
metadata to match the project-level OFL claim. Since the embedded,
checkable declaration is the actual authoritative source for what ships,
`LICENSE-HackNerdFontMono.txt` vendors that text (MIT + Bitstream Vera), and
`tests/test_assets.py` checks against it, not the aspirational README claim.
