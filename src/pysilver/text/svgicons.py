"""SVG icons: compile vector artwork into glyph outlines, once.

Material Symbols needs no rendering path of its own because it is a font --
an icon is a glyph, and flows through the existing `FontDB`, rasteriser, and
glyph atlas unchanged (`text/icons.py`). This module gives arbitrary SVG
artwork the same property, by *becoming* a font rather than by adding a
second rendering path next to the one that already exists.

**Why compile to a glyph rather than render the path directly.** The atlas,
caching, tinting, and the single draw call all already work for glyphs; a
second code path would have to reinvent every one of them, and -- the
decisive reason, from `ARCHITECTURE.md` 5.8.5 -- animating raw path geometry
per frame is a different problem this module does not solve (see `Shape` for
that: parametric shapes stay off the atlas entirely because a glyph's cache
key includes its rasterised size, and an atlas with no per-entry eviction
punishes anything that changes that key every frame). Static artwork -- an
icon, a logo, a piece of SVG art that does not morph -- has no such problem:
it is rasterised once, like any other glyph, and the cache does the rest.

**The pipeline:** SVG path commands (`svgelements`) -> cubic-to-quadratic
conversion (`fontTools.pens.cu2quPen`, since TrueType `glyf` outlines are
quadratic and SVG's are cubic) -> a real glyph (`fontTools.pens.ttGlyphPen`)
-> a real font file on disk (`fontTools.fontBuilder`) -> `text.font.Face`,
identical to loading Roboto or Material Symbols. `Face` only ever loads from
a path (HarfBuzz, FreeType and fontTools all open the same file), which is
not a limitation to route around -- it is the seam that makes this reuse the
whole existing pipeline with no changes to it at all.

**A real limitation, checked rather than assumed away: `fill-rule="evenodd"`
does not survive.** `glyf` outlines have no per-contour fill-rule flag --
FreeType always fills them by the nonzero winding rule. An SVG using the
default `fill-rule="nonzero"` and encoding a hole the way that rule requires
(the hole's contour wound opposite to the shape it cuts from -- what every
common SVG export tool does) compiles and rasterises correctly, verified
against a real ring shape with a real hole. An SVG that instead sets
`fill-rule="evenodd"` and winds every contour the *same* direction -- valid
SVG, relying on the other rule to punch its holes -- loses the hole: the
centre rasterises solid. Confirmed with the same ring shape, wound the
`evenodd` way. There is no fix inside this module; `evenodd` source has to be
rewound (or exported as `nonzero`, which is the default and the overwhelming
majority of real-world icon SVGs) before it can become a glyph.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING, Final

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

from .font import Face
from .icons import IconSet

if TYPE_CHECKING:
    from fontTools.pens.basePen import AbstractPen
    from svgelements import Matrix

__all__ = ["compile_svg_font", "load_svg_icons"]

#: Unicode Private Use Area. Every real icon font -- Material Symbols
#: included -- assigns its glyphs here rather than to characters that mean
#: something, so a name lookup can never collide with real text.
_PUA_START: Final = 0xE000

#: fontTools' own recommended tolerance for a cubic-to-quadratic refit; the
#: same value the M4 text stack already trusts nowhere near visibly, since
#: this is a one-time compile rather than a per-frame cost.
_MAX_CUBIC_TO_QUAD_ERROR: Final = 1.0

#: A square glyph fills the whole em box, corner to corner -- the convention
#: Material Symbols itself uses (a 24x24dp viewBox at 24dp render size), which
#: is what lets `IconElement` treat every icon the same regardless of source.
_UNITS_PER_EM: Final = 1000


def _draw_into(pen: AbstractPen, svg_source: str, transform: Matrix) -> None:
    """Draw every shape in *svg_source* into *pen*, through *transform*.

    Every SVG segment type maps onto the pen protocol directly except `Arc`,
    which fontTools has no primitive for; `as_cubic_curves()` decomposes it
    first. Everything -- lines, native cubics, decomposed arcs -- goes through
    the same `curveTo`/`lineTo` calls so winding and closure stay consistent
    regardless of which commands the source SVG happened to use.
    """
    import svgelements as se

    doc = se.SVG.parse(io.StringIO(svg_source))
    started = False
    for element in doc.elements():
        if not isinstance(element, se.Shape):
            continue
        for seg in se.Path(element):
            if isinstance(seg, se.Move):
                if started:
                    pen.closePath()
                pen.moveTo(transform.point_in_matrix_space((seg.end.x, seg.end.y)))
                started = True
            elif isinstance(seg, se.Line):
                pen.lineTo(transform.point_in_matrix_space((seg.end.x, seg.end.y)))
            elif isinstance(seg, se.QuadraticBezier):
                pen.qCurveTo(
                    transform.point_in_matrix_space((seg.control.x, seg.control.y)),
                    transform.point_in_matrix_space((seg.end.x, seg.end.y)),
                )
            elif isinstance(seg, se.CubicBezier):
                pen.curveTo(
                    transform.point_in_matrix_space((seg.control1.x, seg.control1.y)),
                    transform.point_in_matrix_space((seg.control2.x, seg.control2.y)),
                    transform.point_in_matrix_space((seg.end.x, seg.end.y)),
                )
            elif isinstance(seg, se.Arc):
                for cubic in seg.as_cubic_curves():
                    pen.curveTo(
                        transform.point_in_matrix_space((cubic.control1.x, cubic.control1.y)),
                        transform.point_in_matrix_space((cubic.control2.x, cubic.control2.y)),
                        transform.point_in_matrix_space((cubic.end.x, cubic.end.y)),
                    )
            elif isinstance(seg, se.Close):
                pen.closePath()
                started = False
    if started:
        pen.closePath()


def _viewbox_transform(svg_source: str) -> Matrix:
    """Map an SVG's own `viewBox` into the font em-square, Y-flipped.

    SVG is y-down with an arbitrary-sized viewBox; `glyf` outlines are y-up
    with the baseline at 0 and the em box `units_per_em` tall. Flattened into
    one `svgelements.Matrix` so every point is transformed once regardless of
    how many segments it took to describe it.
    """
    import svgelements as se

    doc = se.SVG.parse(io.StringIO(svg_source))
    if doc.viewbox is None:
        raise ValueError("SVG has no viewBox -- cannot scale it to a glyph")
    vx, vy, vw, vh = doc.viewbox.x, doc.viewbox.y, doc.viewbox.width, doc.viewbox.height
    if not vw or not vh:
        raise ValueError("SVG has a zero-sized viewBox -- cannot scale it to a glyph")
    scale = _UNITS_PER_EM / max(vw, vh)
    # Translate the viewBox origin to (0, 0), scale to em units, then flip Y --
    # SVG's +Y is down the page, glyf's +Y is up from the baseline.
    return se.Matrix(scale, 0, 0, -scale, -vx * scale, vh * scale + vy * scale)


def compile_svg_font(
    icons: dict[str, str | Path],
    output_path: str | Path,
    *,
    units_per_em: int = _UNITS_PER_EM,
) -> dict[str, int]:
    """Compile named SVG artwork into a real TrueType font file.

    *icons* maps a name to its source: a `Path` is read as a file, a plain
    `str` is SVG markup already in hand. Never guessed from the string's
    contents -- a string that happens to look like a path is never silently
    opened, which matters because view files are untrusted input and a
    caller resolving one into a `Path` is the point at which it must already
    have applied its own containment check (`spec/include.py`'s
    `_resolve_path` is the existing precedent).

    Returns the assigned name -> codepoint mapping (Private Use Area, from
    U+E000, in *icons*' iteration order) -- what `IconSet` needs to resolve
    `text: "my_icon"` the same way it resolves `text: "home"`.

    Every icon is scaled to fill its own em box, corner to corner -- one
    icon's proportions never affect another's, which is what lets a mixed set
    of hand-drawn SVGs sit at a consistent visual size the way Material
    Symbols' own 218 do.
    """
    glyph_order = [".notdef", *list(icons)]
    charstrings: dict[str, object] = {}
    advance_widths: dict[str, tuple[int, int]] = {".notdef": (units_per_em, 0)}
    cmap: dict[int, str] = {}

    empty = TTGlyphPen(None)
    charstrings[".notdef"] = empty.glyph()

    for i, (name, source) in enumerate(icons.items()):
        svg_source = source.read_text(encoding="utf-8") if isinstance(source, Path) else source
        transform = _viewbox_transform(svg_source)
        tt_pen = TTGlyphPen(None)
        pen = Cu2QuPen(tt_pen, max_err=_MAX_CUBIC_TO_QUAD_ERROR, reverse_direction=True)
        _draw_into(pen, svg_source, transform)
        charstrings[name] = tt_pen.glyph()
        advance_widths[name] = (units_per_em, 0)
        cmap[_PUA_START + i] = name

    builder = FontBuilder(units_per_em, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(cmap)
    builder.setupGlyf(charstrings)
    builder.setupHorizontalMetrics(advance_widths)
    builder.setupHorizontalHeader(ascent=units_per_em, descent=0)
    builder.setupNameTable({"familyName": "pySilver Custom Icons", "styleName": "Regular"})
    builder.setupOS2(
        sTypoAscender=units_per_em, sTypoDescender=0, usWinAscent=units_per_em, usWinDescent=0
    )
    builder.setupPost()
    builder.save(str(output_path))

    return {name: _PUA_START + i for i, name in enumerate(icons)}


def load_svg_icons(
    icons: dict[str, str | Path],
    output_path: str | Path,
    *,
    units_per_em: int = _UNITS_PER_EM,
) -> IconSet:
    """Compile *icons* and load the result as an `IconSet`, ready to hand to
    `TextEngine` or to look up icons from directly.

    `output_path` is a real file, not a temporary one chosen for you: a
    compiled icon font is cheap to keep, and an application that calls this
    once at startup and reuses the file across runs pays the compile cost
    once rather than every launch.
    """
    names = compile_svg_font(icons, output_path, units_per_em=units_per_em)
    # `IconSet`'s `names` defaults to the BUNDLED Material Symbols table when
    # omitted -- passing it explicitly is not optional here, or a custom set
    # silently resolves against the wrong 218 names and every lookup for a
    # real custom icon fails with "unknown icon". Caught by testing this
    # against a real triangle before assuming the constructor "just worked".
    return IconSet(Face(output_path), names)
