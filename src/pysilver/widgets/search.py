"""M3 Search: the search bar. Built new, on the same underlying editing model
`TextField` and `CodeEditor` share (`text/editing.py`'s `Editor`/`EditState`,
`text/selection.py`'s point/offset helpers) rather than by subclassing
`TextField` -- the identical reasoning `CodeEditor`'s own docstring gives:
`TextField`'s layout and paint are saturated with its own M3 chrome (a
floating label, an indicator stroke that thickens on focus, filled/outlined
containers) a search bar has none of. It is always a 56dp pill with a fixed
leading icon, never floats a label, and is always single-line -- different
enough anatomy that subclassing would mean overriding nearly every method.

**Search Bar only -- the expanded "Search View" (a results list shown below
it) is deliberately not a second widget kind.** It is exactly the same shape
`Menu`/`MenuItem` already solve: a list of items anchored to a trigger,
opened and closed by the application's own state. A real app composes it
from the existing `Menu` overlay, anchored to this widget's `name`, the same
way a `MenuItem` with `style.has_submenu` anchors its own submenu -- no new
framework capability was needed for it.

**Anatomy (`COMPONENT_SEARCH.md`'s own measurements, docked-style table):**
56dp height, 16dp leading/trailing padding, a full-pill 28dp radius (M3's own
before/after comparison: "M2 open search bars were square and elevated";
M3's own docked table gives one padding figure rather than the
floating-bar's separate unfocused/focused values, used here for both states
rather than animating between them -- a deliberate simplification, not an
oversight). Icon size (24dp) and container colour (`surface_container_high`)
follow the same M3 defaults `IconButton`/`TextField` already use; the exact
token is not in the scraped tokens table (an interactive image, the same gap
`CircularProgress`'s own default diameter has).

`value:` is the typed query, the same convention `TextField` uses;
`supporting_text:` is a placeholder shown only while empty (M3's own
anatomy names this "Supporting text"), not a caption below the field the
way `TextField`'s is. `icon:` names an optional trailing icon (M3: "A
search bar should have one or two trailing icons") -- unset means no
trailing icon at all, matching M3's own "can contain a non-functional
search icon" baseline of a leading icon alone. `on_change` fires on every
edit, identically to `TextField`.
"""

from __future__ import annotations

from typing import Any, Final

from ..layout import Constraints, EdgeInsets, Padding, Size
from ..runtime.clipboard import clipboard
from ..runtime.events import ChangeEvent, EventType, is_accelerator, modifiers_of
from ..spec import WidgetSpec
from ..spec.typescale import TYPE_SCALE
from ..text.editing import Editor, delete_backward, delete_forward, insert, move, word_bounds
from ..text.selection import caret_at, index_at, rects_for
from ..tree.element import PaintContext
from .base import _StyledMixin, content_token, paint_text
from .material import _box, _state_alpha

__all__ = ["SearchBarElement"]

_MOTIONS: Final = {
    "arrowleft": "left",
    "left": "left",
    "arrowright": "right",
    "right": "right",
}


class SearchBarElement(_StyledMixin, Padding):
    """M3 Search bar. See the module docstring."""

    HEIGHT: Final = 56.0
    PAD_X: Final = 16.0
    ICON: Final = 24.0
    GAP: Final = 16.0
    RADIUS: Final = HEIGHT / 2
    #: M3: "Container Width: Min: 360dp, max: 720dp". Used directly, the
    #: same "M3's own dp figures, used directly" rule every other widget
    #: follows (ARCHITECTURE.md 5.12).
    MIN_WIDTH: Final = 360.0
    MAX_WIDTH: Final = 720.0
    CARET_WIDTH: Final = 2.0
    BLINK_PERIOD: Final = 1.0
    SELECTION_ALPHA: Final = 0.30
    INPUT_ROLE: Final = TYPE_SCALE["body-large"]
    CURSOR = "text"

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)
        self._editor = Editor(spec.value or "")
        self._external = spec.value or ""
        self._scroll_x = 0.0

    def configure(self) -> None:
        self._adopt_external()

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self.RADIUS,) * 4

    # ---------------------------------------------------------------- state

    def _adopt_external(self) -> None:
        if self._value != self._external:
            self._external = self._value
            self._editor.set_text(self._value)
            self._scroll_x = 0.0

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
        self._scroll_to_caret()
        self.mark_needs_paint()

    # --------------------------------------------------------------- layout

    def _has_trailing_icon(self) -> bool:
        return bool(self._icon.strip())

    def _content_x(self) -> float:
        return self.PAD_X + self.ICON + self.GAP

    def _inner_width(self) -> float:
        trailing = self.ICON + self.GAP if self._has_trailing_icon() else 0.0
        return max(0.0, float(self.size.width) - self._content_x() - self.PAD_X - trailing)

    def _paragraph(self) -> Any:
        return self.text_engine.layout(
            self.content,
            px=self.INPUT_ROLE.size,
            max_width=None,
            tracking=self.INPUT_ROLE.tracking,
            line_height=self.INPUT_ROLE.line_height,
        )

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else self.MIN_WIDTH
        width = max(self.MIN_WIDTH, min(width, self.MAX_WIDTH))
        return outer.constrain(Size(width, self.HEIGHT))

    # ---------------------------------------------------------------- paint

    def _scroll_to_caret(self) -> None:
        para = self._paragraph()
        caret = caret_at(para, self.editor.state.caret)
        inner = self._inner_width()
        if caret.x - self._scroll_x > inner:
            self._scroll_x = caret.x - inner
        if caret.x - self._scroll_x < 0.0:
            self._scroll_x = caret.x
        self._scroll_x = max(0.0, min(self._scroll_x, max(0.0, para.size.width - inner)))

    def _inner_context(self, ctx: PaintContext, absolute: Any) -> PaintContext:
        dpr = ctx.pixel_ratio
        x = absolute.x + self._content_x()
        y = absolute.y
        return PaintContext(
            display_list=ctx.display_list,
            palette=ctx.palette,
            text=ctx.text,
            images=ctx.images,
            pixel_ratio=dpr,
            clip=(x * dpr, y * dpr, self._inner_width() * dpr, self.size.height * dpr),
            clip_radii=(0.0, 0.0, 0.0, 0.0),
        )

    def _caret_visible(self) -> bool:
        if self.ticker.reduce_motion:
            return True
        phase = self.animated("caret", 1.0, duration=self.BLINK_PERIOD, curve="linear", repeat=True)
        return phase < 0.5

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        dpr = ctx.pixel_ratio
        container = ctx.palette.index(style.background or "surface_container_high")
        content = content_token(ctx, style, "on_surface")
        icon_token = ctx.palette.index("on_surface_variant")

        ctx.display_list.add_box(
            absolute.x * dpr,
            absolute.y * dpr,
            self.size.width * dpr,
            self.size.height * dpr,
            token=container,
            radii=(self.RADIUS * dpr,) * 4,
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        alpha = _state_alpha(self)
        if alpha > 0.001:
            ctx.display_list.add_box(
                absolute.x * dpr,
                absolute.y * dpr,
                self.size.width * dpr,
                self.size.height * dpr,
                token=content,
                color=(1.0, 1.0, 1.0, alpha),
                radii=(self.RADIUS * dpr,) * 4,
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )

        ctx.text.emit_icon(
            ctx.display_list,
            "search",
            x=absolute.x + self.PAD_X,
            y=absolute.y + (self.size.height - self.ICON) / 2,
            size=self.ICON,
            pixel_ratio=dpr,
            token=icon_token,
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        if self._has_trailing_icon():
            ctx.text.emit_icon(
                ctx.display_list,
                self._icon.strip(),
                x=absolute.x + self.size.width - self.PAD_X - self.ICON,
                y=absolute.y + (self.size.height - self.ICON) / 2,
                size=self.ICON,
                pixel_ratio=dpr,
                token=icon_token,
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )

        self._paint_content(ctx, absolute, content)

    def _paint_content(self, ctx: PaintContext, absolute: Any, content: int) -> None:
        inner = self._inner_context(ctx, absolute)
        x = absolute.x + self._content_x() - self._scroll_x
        y = absolute.y + (self.size.height - self.INPUT_ROLE.line_height) / 2
        state = self.editor.state
        para = self._paragraph()
        placeholder = self._supporting.strip()

        if state.has_selection:
            low, high = state.selection
            for rect in rects_for(para, low, high):
                _box(
                    inner,
                    x + rect.x,
                    y + rect.y,
                    rect.width,
                    rect.height,
                    token=ctx.palette.index("primary"),
                    radius=0.0,
                    alpha=self.SELECTION_ALPHA,
                )

        if self.content:
            paint_text(inner, x, y, self.content, self.INPUT_ROLE, content)
        elif placeholder and not self.state.focused:
            paint_text(
                inner, x, y, placeholder, self.INPUT_ROLE, ctx.palette.index("on_surface_variant")
            )

        if self.state.focused and not self.effective_disabled and self._caret_visible():
            caret = caret_at(para, state.caret)
            _box(
                inner,
                x + caret.x,
                y + caret.y,
                self.CARET_WIDTH,
                caret.height,
                token=ctx.palette.index("primary"),
                radius=0.0,
            )

    # ------------------------------------------------------------- pointer

    def _offset_at(self, x: float) -> int:
        rect = self.absolute_rect()
        local_x = x - rect.x - self._content_x() + self._scroll_x
        return index_at(self._paragraph(), local_x, 0.0)

    def on_pointer_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        offset = self._offset_at(event.x)
        if self.state.data.pop("search_double", False):
            self.editor.select(*word_bounds(self.content, offset))
        else:
            self.editor.set_caret(offset)
        self.state.data["search_anchor"] = self.editor.state.anchor
        event.capture()
        self._commit(False)

    def on_pointer_move(self, event: Any) -> None:
        if self.effective_disabled or "search_anchor" not in self.state.data:
            return
        if event.button or self.state.pressed:
            self.editor.select(int(self.state.data["search_anchor"]), self._offset_at(event.x))
            self._commit(False)

    def on_click(self, event: Any) -> None:
        self.state.data["search_double"] = not self.state.data.get("search_double", False)

    # --------------------------------------------------------------- typing

    def on_text(self, event: Any) -> None:
        if self.effective_disabled:
            return
        text = str(getattr(event, "text", ""))
        if not text or text < " ":
            return
        editor = self.editor
        self._commit(editor.edit(insert(editor.state, text), "type"))
        event.stop_propagation()

    def on_key_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        key = str(getattr(event, "key", "")).lower()
        mods = modifiers_of(event)
        accel = is_accelerator(mods)
        shift = "shift" in mods
        word = "ctrl" in mods or "alt" in mods
        editor = self.editor
        state = editor.state
        handled = True

        if key in _MOTIONS:
            motion = _MOTIONS[key]
            if word and motion in ("left", "right"):
                motion = f"word_{motion}"
            editor.state = move(state, motion, extend=shift)
            self._commit(False)
        elif key in ("home", "end"):
            target = 0 if key == "home" else len(state.text)
            editor.state = (
                state.selecting(state.anchor, target) if shift else state.collapsed(target)
            )
            self._commit(False)
        elif key == "backspace":
            self._commit(editor.edit(delete_backward(state, word=word), "delete"))
        elif key == "delete":
            self._commit(editor.edit(delete_forward(state, word=word), "delete"))
        elif accel and key == "a":
            editor.state = state.select_all()
            self._commit(False)
        elif accel and key in ("c", "x") and state.has_selection:
            clipboard.set_text(state.selected_text)
            if key == "x":
                self._commit(editor.edit(delete_backward(state), "delete"))
        elif accel and key == "v":
            pasted = clipboard.get_text()
            if pasted:
                self._commit(editor.edit(insert(state, pasted), "paste"))
        elif accel and key == "z" and not shift:
            self._commit(editor.undo())
        elif accel and (key == "y" or (key == "z" and shift)):
            self._commit(editor.redo())
        else:
            handled = False

        if handled:
            event.stop_propagation()

    def on_focus(self, event: Any) -> None:
        self.mark_needs_paint()

    def on_blur(self, event: Any) -> None:
        self.mark_needs_paint()
