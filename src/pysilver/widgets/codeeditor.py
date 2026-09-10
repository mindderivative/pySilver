"""CodeEditor: a syntax-highlighted, line-numbered multi-line text editor.

M3 has no code editor component -- checked directly against `M3-References`,
the same way every other ungrounded widget this session was -- so this is
designed from pySilver's own editing primitives (`text/editing.py`,
`text/selection.py`) rather than a spec, and built ALONGSIDE `TextField`
rather than on top of it. `editing.py`'s own docstring anticipates more than
one widget consumer ("`TextFieldElement` supplies keys and pixels; this
supplies the answers"), and `TextField`'s own layout and paint methods are
saturated with M3-specific chrome this widget has none of -- a floating
label, an indicator stroke that thickens on focus, filled/outlined
containers. Subclassing `TextFieldElement` would mean overriding nearly
every method on it; building on the shared UNDERLYING model instead reuses
everything that actually is shared -- grapheme-aware caret motion, undo/
redo, selection ranges, click-to-offset -- with none of the M3 baggage.

**Never wraps.** A code editor's line numbers only mean something if they
correspond 1:1 with the source's own lines, so `max_width=None` is always
passed to `text_engine.layout()`. `layout_text`'s own contract is that a
hard break (`\\n`) always starts a new `TextLine` regardless of wrapping, so
this is exactly "one `TextLine` per source line," and a long line scrolls
sideways instead of wrapping into a visual line the gutter could not label.
Because of this, unlike `TextField`, this widget needs a genuinely bounded
**height** -- an unbounded one would try to grow to fit the entire buffer
and never scroll, the same reasoning `ScrollView` raises for.

**Syntax highlighting is optional and Pygments (BSD-2), not a hard
dependency** -- asked of the user directly rather than assumed, choosing it
over tree-sitter for a v1: simpler, already commonly present, and its
whole-buffer re-lex per edit is fine at realistic file sizes, at the cost of
no incremental parsing (a real, accepted limitation for very large files
edited live). `pygments` is imported lazily; with it absent, or
`style.language` unset or unrecognised, this widget still works as a plain
editable multi-line control, just uncoloured -- the same "degrade rather
than crash" choice `Image` makes for a bad path. Colours are literal RGBA,
not palette tokens, for the identical reason `CanvasContext`'s own colour
parameter accepts a literal tuple: there are only four true M3 colour roles
(primary/secondary/tertiary/error) against the ~ten categories a real syntax
theme needs, and no semantic role exists to map the rest onto. A stated
departure from "emit tokens, not colours," not an oversight.

**Defaults to a real bundled monospace font (`Hack Nerd Font Mono`).**
`style.font_family` requests a family by name through the same
`FontRequest`/`FontDB` machinery every widget already resolves against, and
wins if set. Left unset, `_font_request()` loads and requests
`assets.MONOSPACE_FONT` -- the same fix and the same default
`Terminal._font_request()` uses, closing this widget's own long-disclosed
gap (it used to default to `"Roboto"`, proportional, which cannot give a
code editor genuine column alignment for indentation or aligned comments).
`Hack Nerd Font Mono` also carries ~9,000 Nerd-Font-patched icon glyphs, so
ligature-style file-type/status icons some syntax themes lean on render as
real glyphs rather than missing-glyph boxes. An application can still
override with any other face via `style.font_family`, loaded itself with
`app.text.db.load(path)` -- already a public method, no new API.

**A new dispatcher capability was needed, not just a new widget.** Tab is
intercepted and treated as focus traversal BEFORE any element's own
`on_key_down` ever runs (`EventDispatcher._dispatch_to_focused`) -- there was
no way for a widget to see the keypress at all, let alone insert indentation
with it. `ElementMixin.CAPTURES_TAB` (default `False`, the same shape as the
existing `CLIPS_CHILDREN` flag) lets a focused element opt in; `CodeEditor`
is the first, and so far only, one that does. `Escape` still defocuses
unconditionally before per-element delivery too, so trapping Tab this way
never traps the keyboard -- Escape, then Tab, always reaches the next
control, the same escape hatch real code editors themselves rely on.

**Deliberately out of scope for this pass**, each for the same reason a
"v1" stops somewhere concrete rather than half-building everything a real
IDE has: auto-closing/matching brackets, multi-cursor editing, code folding,
a minimap, a draggable scrollbar thumb (wheel and keyboard scrolling are
both implemented; only the visible, grabbable indicator is missing),
incremental re-lexing for very large files, and any language server
integration -- the package survey that grounded this widget's design was
explicit that an LSP client is an APPLICATION concern, not something a
widget should hard-depend on.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Final, override

import numpy as np

from ..assets import MONOSPACE_FONT
from ..layout import Constraints, EdgeInsets, Offset, Padding, Size
from ..runtime.clipboard import clipboard
from ..runtime.events import ChangeEvent, EventType, is_accelerator, modifiers_of
from ..spec import WidgetSpec
from ..text.editing import (
    Editor,
    EditState,
    delete_backward,
    delete_forward,
    insert,
    move,
    word_bounds,
)
from ..text.fontdb import FontRequest
from ..text.selection import caret_at, index_at, line_end, line_index_at, rects_for
from ..theme import srgb_to_linear
from ..tree.element import PaintContext
from .base import _StyledMixin, content_token
from .material import _box

__all__ = ["CodeEditorElement"]

try:
    from pygments import lex as _pygments_lex
    from pygments.lexers import get_lexer_by_name
    from pygments.token import Token as _PygmentsToken
    from pygments.util import ClassNotFound as _PygmentsClassNotFound

    _PYGMENTS_AVAILABLE = True
except ImportError:
    _PYGMENTS_AVAILABLE = False


def _srgb(r: float, g: float, b: float, a: float = 1.0) -> tuple[float, float, float, float]:
    """An sRGB-intended colour, converted to the linear RGBA every literal
    `color=` on the display list actually expects.

    Verified empirically, not assumed: the render target is
    `rgba8unorm-srgb` (ARCHITECTURE.md 5.6.1), which encodes linear values
    written to it -- a literal `color=(0.5, 0.5, 0.5, 1.0)` reads back as
    `(188, 188, 188)`, not `(128, 128, 128)`, unless converted first. These
    syntax colours were originally written as plain "looks about right"
    floats, which is exactly the double-encoding bug ARCHITECTURE.md 5.6.1
    already documents for the palette upload path -- the same mistake, once
    removed, on a literal colour instead of a token.
    """
    lr, lg, lb = srgb_to_linear(np.array([r, g, b], dtype=np.float64))
    return (float(lr), float(lg), float(lb), a)


if _PYGMENTS_AVAILABLE:
    #: Not M3-sourced -- see the module docstring. Chosen to read
    #: reasonably against a dark `surface_container_lowest` background,
    #: the way most editor colour schemes assume a dark canvas; there is no
    #: attempt to adapt these to a light theme. Written as the sRGB values
    #: they are meant to look like; `_srgb()` converts each to the linear
    #: form the shader actually wants.
    _SYNTAX_COLORS: Final[dict[Any, tuple[float, float, float, float]]] = {
        _PygmentsToken.Comment: _srgb(0.47, 0.53, 0.60),
        _PygmentsToken.Keyword: _srgb(0.78, 0.52, 0.87),
        _PygmentsToken.Keyword.Constant: _srgb(0.62, 0.71, 0.93),
        _PygmentsToken.Name.Builtin: _srgb(0.62, 0.71, 0.93),
        _PygmentsToken.Name.Function: _srgb(0.53, 0.75, 0.95),
        _PygmentsToken.Name.Class: _srgb(0.90, 0.75, 0.45),
        _PygmentsToken.Name.Decorator: _srgb(0.90, 0.75, 0.45),
        _PygmentsToken.String: _srgb(0.60, 0.80, 0.55),
        _PygmentsToken.Number: _srgb(0.85, 0.62, 0.45),
        _PygmentsToken.Operator: _srgb(0.80, 0.82, 0.87),
        _PygmentsToken.Error: _srgb(0.94, 0.40, 0.40),
    }
    _SYNTAX_DEFAULT: Final = _srgb(0.82, 0.84, 0.88)

    def _syntax_color(tok_type: Any) -> tuple[float, float, float, float]:
        """Walk a Pygments token type up to its nearest mapped ancestor."""
        t = tok_type
        while t is not None:
            color = _SYNTAX_COLORS.get(t)
            if color is not None:
                return color
            t = t.parent
        return _SYNTAX_DEFAULT

    def _highlight_spans(
        text: str, language: str
    ) -> list[tuple[int, int, tuple[float, float, float, float]]] | None:
        """`(start, end, colour)` spans over `text`'s own source offsets.

        `stripnl=False, stripall=False, ensurenl=False`: Pygments strips by
        default, which would desync a running offset count from `text`'s
        real length -- verified empirically that with these three set,
        `"".join(v for _, v in lex(text, lexer)) == text` exactly.
        """
        try:
            lexer = get_lexer_by_name(language, stripnl=False, stripall=False, ensurenl=False)
        except _PygmentsClassNotFound:
            return None
        spans: list[tuple[int, int, tuple[float, float, float, float]]] = []
        offset = 0
        for tok_type, value in _pygments_lex(text, lexer):
            end = offset + len(value)
            if end > offset:
                spans.append((offset, end, _syntax_color(tok_type)))
            offset = end
        return spans


def _dedent_line(line: str, width: int) -> str:
    n = 0
    while n < width and n < len(line) and line[n] == " ":
        n += 1
    return line[n:]


#: Key names as `rendercanvas` reports them, lower-cased on arrival -- the
#: identical table `TextField` uses for the same reason.
_MOTIONS: Final = {
    "arrowleft": "left",
    "left": "left",
    "arrowright": "right",
    "right": "right",
}
_VISUAL: Final = {
    "arrowup": "up",
    "up": "up",
    "arrowdown": "down",
    "down": "down",
    "home": "home",
    "end": "end",
}


class CodeEditorElement(_StyledMixin, Padding):
    """A multi-line, non-wrapping, line-numbered, optionally highlighted
    editable text buffer.

    `value:` is the buffer content, the same convention `TextField` uses.
    `style.language` names a Pygments lexer for syntax colouring;
    `style.line_numbers` (default on) shows the gutter; `style.tab_size`
    sets how many spaces Tab inserts; `style.font_family` requests a face by
    name (see the module docstring for why there is no bundled monospace
    one). `text:` is unused, the same as `Canvas`/`ScrollView`.
    """

    CONTENT_PAD_X: Final = 8.0
    CONTENT_PAD_Y: Final = 8.0
    GUTTER_PAD_X: Final = 8.0
    #: Not sourced -- there is no M3 page for this widget at all -- larger
    #: than `TextField.MIN_WIDTH` (120) since indented code needs more room
    #: to stay legible than a single input line does.
    MIN_WIDTH: Final = 240.0
    #: Matches `NodeElement`'s own choice of a modest default rounding for
    #: a widget M3 gives no shape to cite.
    RADIUS: Final = 8.0
    BORDER_WIDTH: Final = 1.0
    BORDER_WIDTH_FOCUSED: Final = 2.0
    CARET_WIDTH: Final = 2.0
    BLINK_PERIOD: Final = 1.0
    SELECTION_ALPHA: Final = 0.30

    CURSOR = "text"
    CAPTURES_TAB = True

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)
        self._editor = Editor(spec.value or "")
        #: The last value seen from the spec or a binding -- lets `TextField`'s
        #: own controlled/uncontrolled split work here too.
        self._external = spec.value or ""
        self._scroll_x = 0.0
        self._scroll_y = 0.0
        #: `(content, language, spans)` from the last highlight pass. A caret
        #: blink or a hover repaint marks paint without changing either, and
        #: re-lexing the whole buffer for those would waste exactly the cost
        #: the user already accepted only for an actual edit.
        self._highlight_cache: tuple[str, str, Any] | None = None

    @override
    def configure(self) -> None:
        self._adopt_external()

    @override
    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        radii = self.style.corner_radius
        return radii if any(radii) else (self.RADIUS,) * 4

    # ---------------------------------------------------------------- state

    def _adopt_external(self) -> None:
        if self._value != self._external:
            self._external = self._value
            self._editor.set_text(self._value)
            self._scroll_x = self._scroll_y = 0.0

    @property
    def editor(self) -> Editor:
        self._adopt_external()
        return self._editor

    @property
    def content(self) -> str:
        return self.editor.text

    def _commit(self, changed: bool) -> None:
        if changed:
            self._value = self._editor.text
            self._external = self._editor.text
            handler = self.handlers.get("on_change")
            if handler is not None:
                handler(ChangeEvent(EventType.CHANGE, target=self, value=self._editor.text))
        # Unlike TextField's multiline mode, content never changes THIS
        # widget's own size -- there is no wrap to remeasure and no
        # auto-grow -- so an edit only ever needs a repaint.
        self._scroll_to_caret()
        self.mark_needs_paint()

    # --------------------------------------------------------------- layout

    def _font_request(self) -> FontRequest:
        """`style.font_family` wins if set; otherwise this loads (idempotent
        past the first call) and requests the bundled `Hack Nerd Font Mono`
        -- the same default `Terminal._font_request()` uses, and for the
        same reason: a code editor wants column alignment (indentation,
        aligned comments, ASCII diagrams) that a proportional face like
        Roboto cannot give it. See `assets/fonts/README.md`'s "Monospace"
        section.
        """
        family = self.style.font_family
        if not family:
            self.text_engine.db.load(MONOSPACE_FONT)
            family = "Hack Nerd Font Mono"
        return FontRequest(family=family, weight=self.style.font_weight)

    def _paragraph(self) -> Any:
        style = self.style
        return self.text_engine.layout(
            self.content,
            px=style.font_size,
            max_width=None,
            request=self._font_request(),
            tracking=style.letter_spacing,
            line_height=style.line_height,
        )

    def _gutter_width(self, para: Any) -> float:
        if not self.style.line_numbers:
            return 0.0
        digits = len(str(max(1, len(para.lines))))
        # "9" is among the widest digits in most faces -- a safe stand-in
        # for the actual widest line number without measuring all of them.
        metrics = self.text_engine.measure(
            "9" * digits,
            px=self.style.font_size,
            request=self._font_request(),
            tracking=self.style.letter_spacing,
        )
        return metrics.width + 2 * self.GUTTER_PAD_X

    def _visible_size(self, para: Any) -> Size:
        gutter = self._gutter_width(para)
        return Size(
            max(0.0, self.size.width - 2 * self.CONTENT_PAD_X - gutter),
            max(0.0, self.size.height - 2 * self.CONTENT_PAD_Y),
        )

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        if not outer.has_bounded_height:
            raise ValueError(
                "CodeEditor needs a bounded height; it was given unbounded space, "
                "so it would grow to fit the entire buffer and never scroll. Set "
                "style.height or place it inside something that constrains it."
            )
        width = outer.max_width if outer.has_bounded_width else self.MIN_WIDTH
        return outer.constrain(Size(width, outer.max_height))

    # ---------------------------------------------------------------- paint

    def _inner_context(self, ctx: PaintContext, absolute: Offset, gutter: float) -> PaintContext:
        dpr = ctx.pixel_ratio
        para = self._paragraph()
        x = absolute.x + self.CONTENT_PAD_X + gutter
        y = absolute.y + self.CONTENT_PAD_Y
        visible = self._visible_size(para)
        return PaintContext(
            display_list=ctx.display_list,
            palette=ctx.palette,
            text=ctx.text,
            images=ctx.images,
            pixel_ratio=dpr,
            clip=(x * dpr, y * dpr, visible.width * dpr, visible.height * dpr),
            clip_radii=(0.0, 0.0, 0.0, 0.0),
        )

    def _scroll_to_caret(self) -> None:
        para = self._paragraph()
        caret = caret_at(para, self.editor.state.caret)
        visible = self._visible_size(para)

        if caret.y + caret.height - self._scroll_y > visible.height:
            self._scroll_y = caret.y + caret.height - visible.height
        if caret.y - self._scroll_y < 0.0:
            self._scroll_y = caret.y
        self._scroll_y = max(0.0, min(self._scroll_y, max(0.0, para.size.height - visible.height)))

        if caret.x - self._scroll_x > visible.width:
            self._scroll_x = caret.x - visible.width
        if caret.x - self._scroll_x < 0.0:
            self._scroll_x = caret.x
        self._scroll_x = max(0.0, min(self._scroll_x, max(0.0, para.size.width - visible.width)))

    def _syntax_spans(
        self,
    ) -> list[tuple[int, int, tuple[float, float, float, float]]] | None:
        if not _PYGMENTS_AVAILABLE:
            return None
        language = self.style.language
        if not language:
            return None
        content = self.content
        cache = self._highlight_cache
        if cache is not None and cache[0] == content and cache[1] == language:
            return cache[2]  # type: ignore[no-any-return]
        spans = _highlight_spans(content, language)
        self._highlight_cache = (content, language, spans)
        return spans

    @override
    def paint_self(self, ctx: PaintContext, absolute: Offset) -> None:
        if self.size.is_empty:
            return
        style = self.style
        dpr = ctx.pixel_ratio
        radii = self.effective_radii
        focused = self.state.focused
        border = style.border
        border_width = (
            self.BORDER_WIDTH_FOCUSED
            if focused
            else (border.width if border else self.BORDER_WIDTH)
        )
        border_color = "primary" if focused else (border.color if border else "outline_variant")
        ctx.display_list.add_box(
            absolute.x * dpr,
            absolute.y * dpr,
            self.size.width * dpr,
            self.size.height * dpr,
            token=ctx.palette.index(style.background or "surface_container_lowest"),
            radii=tuple(r * dpr for r in radii),  # type: ignore[arg-type]
            border_width=border_width * dpr,
            border_token=ctx.palette.index(border_color),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )

        para = self._paragraph()
        gutter = self._gutter_width(para)
        self._paint_gutter(ctx, absolute, para, gutter)
        self._paint_content(ctx, absolute, para, gutter)

    def _paint_gutter(self, ctx: PaintContext, absolute: Offset, para: Any, gutter: float) -> None:
        if gutter <= 0.0:
            return
        dpr = ctx.pixel_ratio
        h = self.size.height
        ctx.display_list.add_box(
            absolute.x * dpr,
            absolute.y * dpr,
            gutter * dpr,
            h * dpr,
            token=ctx.palette.index("surface_container_low"),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        ctx.display_list.add_box(
            (absolute.x + gutter - 1.0) * dpr,
            absolute.y * dpr,
            1.0 * dpr,
            h * dpr,
            token=ctx.palette.index("outline_variant"),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        token = ctx.palette.index("on_surface_variant")
        request = self._font_request()
        y = absolute.y + self.CONTENT_PAD_Y - self._scroll_y
        for index, line in enumerate(para.lines, start=1):
            # Skip a line whose row is entirely outside the widget's own
            # rect -- cheap, and the only thing standing between a
            # thousand-line file and a thousand `measure`/`emit` calls a
            # frame, since this loop is plain Python, not the vectorised
            # glyph path `TextEngine.emit` itself uses.
            if y + line.height >= absolute.y and y <= absolute.y + h:
                label = str(index)
                metrics = self.text_engine.measure(label, px=self.style.font_size, request=request)
                self.text_engine.emit(
                    ctx.display_list,
                    self.text_engine.layout(label, px=self.style.font_size, request=request),
                    x=absolute.x + gutter - self.GUTTER_PAD_X - metrics.width,
                    y=y,
                    pixel_ratio=dpr,
                    token=token,
                    clip=ctx.clip,
                    clip_radii=ctx.clip_radii,
                )
            y += line.height

    def _visible_lines(self, para: Any, absolute: Offset) -> list[Any]:
        """*para*'s lines whose row actually falls in the widget's own rect.

        `TextEngine.emit()` has no notion of off-screen -- it emits every
        placement it is given -- so without this, a long file paid for every
        one of its glyphs' atlas lookups every single frame regardless of
        how much of it had scrolled out of view: real waste always, and
        under a live resize specifically the dominant cost, since each
        glyph's shifting screen position changes the subpixel bucket its
        atlas lookup keys on, forcing a fresh rasterise+upload for the
        WHOLE buffer rather than only the handful of lines actually drawn.
        `_paint_gutter` already skips an off-screen line NUMBER this way;
        each `TextLine`'s own `.baseline` is absolute within the paragraph
        (baked in once, over every line, during the original layout), so
        handing `TextEngine.emit()` a paragraph with only a slice of
        `.lines` still places the kept ones correctly.
        """
        h = self.size.height
        y = absolute.y + self.CONTENT_PAD_Y - self._scroll_y
        visible = []
        for line in para.lines:
            if y + line.height >= absolute.y and y <= absolute.y + h:
                visible.append(line)
            y += line.height
        return visible

    def _paint_content(self, ctx: PaintContext, absolute: Offset, para: Any, gutter: float) -> None:
        inner = self._inner_context(ctx, absolute, gutter)
        x = absolute.x + self.CONTENT_PAD_X + gutter - self._scroll_x
        y = absolute.y + self.CONTENT_PAD_Y - self._scroll_y
        state = self.editor.state
        on_surface = content_token(inner, self.style, "on_surface")

        if state.has_selection:
            low, high = state.selection
            for rect in rects_for(para, low, high):
                _box(
                    inner,
                    x + rect.x,
                    y + rect.y,
                    rect.width,
                    rect.height,
                    token=inner.palette.index("primary"),
                    radius=0.0,
                    alpha=self.SELECTION_ALPHA,
                )

        if self.content:
            visible = dataclasses.replace(para, lines=self._visible_lines(para, absolute))
            inner.text.emit(
                inner.display_list,
                visible,
                x=x,
                y=y,
                pixel_ratio=inner.pixel_ratio,
                token=on_surface,
                spans=self._syntax_spans(),
                clip=inner.clip,
                clip_radii=inner.clip_radii,
            )

        if self.state.focused and not self.effective_disabled and self._caret_visible():
            caret = caret_at(para, state.caret)
            _box(
                inner,
                x + caret.x,
                y + caret.y,
                self.CARET_WIDTH,
                caret.height,
                token=inner.palette.index("primary"),
                radius=0.0,
            )

    def _caret_visible(self) -> bool:
        if self.ticker.reduce_motion:
            return True
        phase = self.animated("caret", 1.0, duration=self.BLINK_PERIOD, curve="linear", repeat=True)
        return phase < 0.5

    # ------------------------------------------------------------- pointer

    def _line_offset(self, motion: str) -> int:
        """Home/End/Up/Down, always relative to the SOURCE line -- there is
        no wrapping for "visual line" to mean anything else."""
        para = self._paragraph()
        state = self.editor.state
        caret = caret_at(para, state.caret)
        if motion in ("up", "down"):
            step = caret.height * (-1 if motion == "up" else 1)
            return index_at(para, caret.x, caret.y + caret.height / 2 + step)
        if not para.lines:
            return 0
        line = para.lines[line_index_at(para, caret.y)]
        return int(line.start if motion == "home" else line_end(para, line))

    def _offset_at(self, x: float, y: float) -> int:
        rect = self.absolute_rect()
        para = self._paragraph()
        gutter = self._gutter_width(para)
        local_x = x - rect.x - self.CONTENT_PAD_X - gutter + self._scroll_x
        local_y = y - rect.y - self.CONTENT_PAD_Y + self._scroll_y
        return index_at(para, local_x, local_y)

    def on_pointer_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        offset = self._offset_at(event.x, event.y)
        if self.state.data.pop("editor_double", False):
            self.editor.select(*word_bounds(self.content, offset))
        else:
            self.editor.set_caret(offset)
        self.state.data["editor_anchor"] = self.editor.state.anchor
        event.capture()
        self._commit(False)

    def on_pointer_move(self, event: Any) -> None:
        if self.effective_disabled or "editor_anchor" not in self.state.data:
            return
        if event.button or self.state.pressed:
            self.editor.select(
                int(self.state.data["editor_anchor"]), self._offset_at(event.x, event.y)
            )
            self._commit(False)

    def on_click(self, event: Any) -> None:
        self.state.data["editor_double"] = not self.state.data.get("editor_double", False)

    def on_wheel(self, event: Any) -> None:
        para = self._paragraph()
        visible = self._visible_size(para)
        max_y = max(0.0, para.size.height - visible.height)
        max_x = max(0.0, para.size.width - visible.width)
        new_y = max(0.0, min(self._scroll_y + event.dy, max_y))
        new_x = max(0.0, min(self._scroll_x + event.dx, max_x))
        if new_y != self._scroll_y or new_x != self._scroll_x:
            self._scroll_y, self._scroll_x = new_y, new_x
            self.mark_needs_paint()
            event.stop_propagation()

    # --------------------------------------------------------------- typing

    def on_text(self, event: Any) -> None:
        if self.effective_disabled or self.style.read_only:
            return
        text = str(getattr(event, "text", ""))
        if not text or text < " ":
            return
        editor = self.editor
        self._commit(editor.edit(insert(editor.state, text), "type"))
        event.stop_propagation()

    def _indent(self, *, dedent: bool) -> bool:
        """Tab/Shift+Tab as a block operation over every line the selection
        touches (the current line alone, when there is no selection).

        Simplified relative to a real editor: the selection becomes the
        whole edited block afterward rather than preserving the original
        relative offsets within it -- correct and predictable, if not
        identical to every editor's own exact convention.
        """
        editor = self.editor
        state = editor.state
        text = state.text
        low, high = state.selection
        block_start = text.rfind("\n", 0, low) + 1
        block_end = text.find("\n", high)
        if block_end == -1:
            block_end = len(text)
        block = text[block_start:block_end]
        width = self.style.tab_size
        lines = block.split("\n")
        if dedent:
            new_lines = [_dedent_line(line, width) for line in lines]
        else:
            pad = " " * width
            new_lines = [pad + line for line in lines]
        new_block = "\n".join(new_lines)
        if new_block == block:
            return False
        new_text = text[:block_start] + new_block + text[block_end:]
        new_state = EditState(new_text, block_start, block_start + len(new_block))
        return editor.edit(new_state, "indent")

    def on_key_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        key = str(getattr(event, "key", "")).lower()
        mods = modifiers_of(event)
        accel = is_accelerator(mods)
        shift = "shift" in mods
        word = "ctrl" in mods or "alt" in mods
        read_only = self.style.read_only
        editor = self.editor
        state = editor.state
        handled = True

        if key in _MOTIONS:
            motion = _MOTIONS[key]
            if word and motion in ("left", "right"):
                motion = f"word_{motion}"
            editor.state = move(state, motion, extend=shift)
            self._commit(False)
        elif key in _VISUAL:
            raw = _VISUAL[key]
            if raw in ("home", "end") and accel:
                target = 0 if raw == "home" else len(state.text)
            else:
                target = self._line_offset(raw)
            editor.state = (
                state.selecting(state.anchor, target) if shift else state.collapsed(target)
            )
            self._commit(False)
        elif key == "tab" and not read_only and shift:
            self._commit(self._indent(dedent=True))
        elif key == "tab" and not read_only:
            if state.has_selection:
                self._commit(self._indent(dedent=False))
            else:
                self._commit(editor.edit(insert(state, " " * self.style.tab_size), "type"))
        elif key == "enter" and not read_only:
            text = state.text
            caret = state.caret
            line_start = text.rfind("\n", 0, caret) + 1
            line_end = text.find("\n", caret)
            if line_end == -1:
                line_end = len(text)
            full_line = text[line_start:line_end]
            indent = full_line[: len(full_line) - len(full_line.lstrip(" "))]
            self._commit(editor.edit(insert(state, "\n" + indent), "type"))
        elif key == "backspace" and not read_only:
            self._commit(editor.edit(delete_backward(state, word=word), "delete"))
        elif key == "delete" and not read_only:
            self._commit(editor.edit(delete_forward(state, word=word), "delete"))
        elif accel and key == "a":
            editor.state = state.select_all()
            self._commit(False)
        elif accel and key in ("c", "x") and state.has_selection:
            clipboard.set_text(state.selected_text)
            if key == "x" and not read_only:
                self._commit(editor.edit(delete_backward(state), "delete"))
        elif accel and key == "v" and not read_only:
            pasted = clipboard.get_text()
            if pasted:
                self._commit(editor.edit(insert(state, pasted), "paste"))
        elif accel and key == "z" and not shift and not read_only:
            self._commit(editor.undo())
        elif accel and (key == "y" or (key == "z" and shift)) and not read_only:
            self._commit(editor.redo())
        else:
            handled = False

        if handled:
            event.stop_propagation()

    def on_focus(self, event: Any) -> None:
        self.mark_needs_paint()

    def on_blur(self, event: Any) -> None:
        self.mark_needs_paint()
