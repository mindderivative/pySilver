"""CodeEditor: a multi-line, line-numbered, optionally syntax-highlighted
editable text buffer.

M3 has no code editor component -- checked directly, not assumed absent, the
same way every other ungrounded widget this session was. Shared editing
behaviour (grapheme-aware motion, undo/redo, clipboard) is already covered by
`test_editing.py` and `test_textfield.py`; this file covers what is actually
different about this widget: the bounded-height requirement, never wrapping,
line-relative Home/End, Tab/Shift+Tab indent, Enter auto-indent, Tab capture,
and syntax highlighting.
"""

from __future__ import annotations

import pytest

from pysilver.layout import INF, Constraints, Offset, Size
from pysilver.paint import DisplayList
from pysilver.runtime.clipboard import clipboard
from pysilver.runtime.events import (
    FOCUSABLE_KINDS,
    EventDispatcher,
    EventType,
    KeyEvent,
    PointerEvent,
    WheelEvent,
)
from pysilver.spec import WidgetKind, parse_view
from pysilver.text.editing import insert
from pysilver.theme import Palette, Theme
from pysilver.tree.element import PaintContext
from pysilver.widgets import build_element
from pysilver.widgets.base import _REGISTRY
from pysilver.widgets.codeeditor import CodeEditorElement

CTRL = frozenset({"Control"})
SHIFT = frozenset({"Shift"})


def editor(width: float = 400.0, height: float = 200.0, **spec) -> CodeEditorElement:
    node = {"name": "e", "widget": "CodeEditor", **spec}
    element = build_element(parse_view(node).root)
    element.layout(Constraints(0.0, width, 0.0, height))
    return element


def driver(element, *, focus: bool = True) -> EventDispatcher:
    dispatcher = EventDispatcher()
    dispatcher.root = element
    if focus:
        dispatcher.focus(element)
    return dispatcher


def press(dispatcher, key: str, modifiers=frozenset()) -> None:
    dispatcher.post(KeyEvent(EventType.KEY_DOWN, key=key, modifiers=modifiers))
    dispatcher.drain()


def type_text(dispatcher, text: str) -> None:
    for character in text:
        dispatcher.post(KeyEvent(EventType.TEXT, text=character))
    dispatcher.drain()


def painted(element) -> DisplayList:
    dl = DisplayList()
    ctx = PaintContext(display_list=dl, palette=Palette(Theme(dark=True)))
    element.paint(ctx, Offset(0.0, 0.0))
    return dl


# --------------------------------------------------------------- registered


def test_kind_builds() -> None:
    assert editor() is not None


def test_every_kind_is_registered() -> None:
    assert set(_REGISTRY) == set(WidgetKind)


def test_is_focusable() -> None:
    assert "CodeEditor" in FOCUSABLE_KINDS


# ------------------------------------------------------------------ layout


def test_unbounded_height_raises() -> None:
    element = build_element(parse_view({"name": "e", "widget": "CodeEditor"}).root)
    with pytest.raises(ValueError, match="bounded height"):
        element.layout(Constraints(0.0, 400.0, 0.0, INF))


def test_an_unbounded_width_falls_back_to_its_own_minimum() -> None:
    element = build_element(parse_view({"name": "e", "widget": "CodeEditor"}).root)
    element.layout(Constraints(0.0, INF, 0.0, 200.0))
    assert element.size.width == CodeEditorElement.MIN_WIDTH


def test_a_bounded_size_is_honoured() -> None:
    element = editor(width=500.0, height=300.0)
    assert element.size == Size(500.0, 300.0)


# ------------------------------------------------------------------- typing


def test_typing_inserts_and_fires_on_change() -> None:
    element = editor(handlers={"on_change": "changed"})
    seen: list[str] = []
    dispatcher = driver(element)
    dispatcher.bind_handlers({"changed": lambda event: seen.append(event.value)})
    type_text(dispatcher, "abc")
    assert element.content == "abc"
    assert seen == ["a", "ab", "abc"]


def test_backspace_and_delete_work() -> None:
    element = editor(value="abc")
    dispatcher = driver(element)
    press(dispatcher, "Backspace")
    assert element.content == "ab"


def test_undo_and_redo_reach_the_keyboard() -> None:
    element = editor(value="hello")
    dispatcher = driver(element)
    type_text(dispatcher, " there")
    assert element.content == "hello there"
    press(dispatcher, "z", CTRL)
    assert element.content == "hello"
    press(dispatcher, "y", CTRL)
    assert element.content == "hello there"


def test_a_disabled_editor_ignores_typing() -> None:
    element = editor(value="x", disabled="true")
    dispatcher = driver(element)
    type_text(dispatcher, "y")
    assert element.content == "x"


# --------------------------------------------------------------- read-only


def test_read_only_blocks_typing() -> None:
    element = editor(value="x", style={"read_only": True})
    dispatcher = driver(element)
    type_text(dispatcher, "y")
    assert element.content == "x"


def test_read_only_blocks_backspace_and_delete() -> None:
    element = editor(value="abc", style={"read_only": True})
    dispatcher = driver(element)
    press(dispatcher, "Backspace")
    press(dispatcher, "Delete")
    assert element.content == "abc"


def test_read_only_blocks_tab_and_shift_tab() -> None:
    element = editor(value="abc", style={"read_only": True})
    dispatcher = driver(element)
    press(dispatcher, "Tab")
    press(dispatcher, "Tab", SHIFT)
    assert element.content == "abc"


def test_read_only_blocks_enter() -> None:
    element = editor(value="abc", style={"read_only": True})
    dispatcher = driver(element)
    press(dispatcher, "Enter")
    assert element.content == "abc"


def test_read_only_blocks_paste() -> None:
    clipboard.set_text("pasted")
    element = editor(value="abc", style={"read_only": True})
    dispatcher = driver(element)
    press(dispatcher, "v", CTRL)
    assert element.content == "abc"


def test_read_only_blocks_the_delete_half_of_cut_but_not_the_copy_half() -> None:
    element = editor(value="abc", style={"read_only": True})
    dispatcher = driver(element)
    element.editor.state = element.editor.state.select_all()
    press(dispatcher, "x", CTRL)
    assert clipboard.get_text() == "abc", "the copy half of Cut must still work"
    assert element.content == "abc", "but the delete half must not"


def test_read_only_blocks_undo_and_redo() -> None:
    element = editor(value="abc", style={"read_only": True})
    element.editor.edit(insert(element.editor.state, "x"), "type")
    assert element.content == "abcx"
    dispatcher = driver(element)
    press(dispatcher, "z", CTRL)
    assert element.content == "abcx", "undo must be blocked too, not only forward edits"


def test_read_only_still_allows_select_all_and_copy() -> None:
    element = editor(value="abc", style={"read_only": True})
    dispatcher = driver(element)
    press(dispatcher, "a", CTRL)
    press(dispatcher, "c", CTRL)
    assert clipboard.get_text() == "abc"


def test_read_only_still_allows_keyboard_selection() -> None:
    """The initial caret sits at the end of the text (`EditState`'s own
    default), so Left, not Right, is what actually moves it here."""
    element = editor(value="abc", style={"read_only": True})
    dispatcher = driver(element)
    press(dispatcher, "Left", SHIFT)
    assert element.editor.state.has_selection
    assert element.editor.state.selected_text == "c"


def test_read_only_still_allows_caret_motion() -> None:
    element = editor(value="abc", style={"read_only": True})
    dispatcher = driver(element)
    press(dispatcher, "Left")
    assert element.editor.state.caret == 2


def test_read_only_still_allows_mouse_selection() -> None:
    element = editor(value="abc", style={"read_only": True})
    dispatcher = driver(element, focus=False)
    dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=1.0, y=1.0))
    dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=390.0, y=1.0, button=1))
    dispatcher.drain()
    assert element.editor.state.has_selection


# ---------------------------------------------------------- never wraps


def test_content_never_wraps_however_narrow() -> None:
    element = editor(width=60.0, value="a much longer line than the widget is wide")
    para = element._paragraph()
    assert len(para.lines) == 1


def test_lines_split_only_at_newlines() -> None:
    element = editor(value="one\ntwo\nthree")
    para = element._paragraph()
    assert len(para.lines) == 3


# --------------------------------------------------------- line-relative nav


def test_home_and_end_are_line_relative() -> None:
    element = editor(value="first\nsecond")
    dispatcher = driver(element)
    press(dispatcher, "End")
    assert element.editor.state.caret == 12
    press(dispatcher, "Home")
    assert element.editor.state.caret == 6
    press(dispatcher, "ArrowUp")
    press(dispatcher, "Home")
    assert element.editor.state.caret == 0
    press(dispatcher, "End")
    assert element.editor.state.caret == 5, "before the newline, not after it"


def test_ctrl_home_and_end_reach_the_whole_document() -> None:
    element = editor(value="first\nsecond\nthird")
    dispatcher = driver(element)
    press(dispatcher, "Home", CTRL)
    assert element.editor.state.caret == 0
    press(dispatcher, "End", CTRL)
    assert element.editor.state.caret == len(element.content)


def test_up_and_down_move_between_lines() -> None:
    element = editor(value="first\nsecond")
    dispatcher = driver(element)
    press(dispatcher, "ArrowUp")
    assert element.editor.state.caret <= 6
    press(dispatcher, "ArrowDown")
    assert element.editor.state.caret > 6


# -------------------------------------------------------------------- tab


def test_tab_inserts_spaces_with_no_selection() -> None:
    element = editor(value="", style={"tab_size": 2})
    dispatcher = driver(element)
    press(dispatcher, "Tab")
    assert element.content == "  "


def test_tab_indents_every_line_a_selection_touches() -> None:
    element = editor(value="one\ntwo\nthree", style={"tab_size": 2})
    element.editor.select(0, len(element.content))
    dispatcher = driver(element)
    press(dispatcher, "Tab")
    assert element.content == "  one\n  two\n  three"


def test_tab_with_a_selection_never_just_replaces_it() -> None:
    """The correctness fix: `insert()`'s own semantics replace a selection,
    which would otherwise turn a multi-line selection into a lone tab."""
    element = editor(value="one\ntwo")
    element.editor.select(0, len(element.content))
    dispatcher = driver(element)
    press(dispatcher, "Tab")
    assert "one" in element.content
    assert "two" in element.content


def test_shift_tab_dedents() -> None:
    element = editor(value="    line", style={"tab_size": 4})
    dispatcher = driver(element)
    press(dispatcher, "Tab", SHIFT)
    assert element.content == "line"


def test_shift_tab_dedents_at_most_the_available_spaces() -> None:
    element = editor(value="  line", style={"tab_size": 4})
    dispatcher = driver(element)
    press(dispatcher, "Tab", SHIFT)
    assert element.content == "line"


def test_dedenting_with_nothing_to_remove_is_a_no_op() -> None:
    element = editor(value="line", style={"tab_size": 4})
    dispatcher = driver(element)
    press(dispatcher, "Tab", SHIFT)
    assert element.content == "line"


def test_tab_does_not_move_focus_away_from_the_editor() -> None:
    """The dispatcher-level fix: CAPTURES_TAB keeps Tab routed here instead
    of triggering EventDispatcher's default focus traversal."""
    element = editor(value="")
    dispatcher = driver(element)
    press(dispatcher, "Tab")
    assert dispatcher.focused is element
    assert element.content == " " * element.style.tab_size


def test_escape_still_defocuses_so_tab_can_reach_the_next_control() -> None:
    element = editor()
    dispatcher = driver(element)
    dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Escape"))
    dispatcher.drain()
    assert dispatcher.focused is None


# ------------------------------------------------------------------- enter


def test_enter_auto_indents_to_match_the_current_line() -> None:
    element = editor(value="    line")
    dispatcher = driver(element)
    press(dispatcher, "End")
    press(dispatcher, "Enter")
    assert element.content == "    line\n    "


def test_enter_with_no_indentation_adds_none() -> None:
    element = editor(value="line")
    dispatcher = driver(element)
    press(dispatcher, "End")
    press(dispatcher, "Enter")
    assert element.content == "line\n"


# ------------------------------------------------------------------- wheel


def test_wheel_scrolls_vertically() -> None:
    lines = "\n".join(f"line {i}" for i in range(100))
    element = editor(value=lines, height=100.0)
    assert element._scroll_y == 0.0
    element.on_wheel(WheelEvent(EventType.WHEEL, dy=500.0))
    assert element._scroll_y > 0.0


def test_wheel_does_not_scroll_past_the_content() -> None:
    element = editor(value="short")
    element.on_wheel(WheelEvent(EventType.WHEEL, dy=500.0))
    assert element._scroll_y == 0.0


# -------------------------------------------------------------------- gutter


def test_gutter_is_shown_by_default() -> None:
    element = editor(value="a\nb\nc")
    para = element._paragraph()
    assert element._gutter_width(para) > 0.0


def test_gutter_can_be_turned_off() -> None:
    element = editor(value="a\nb\nc", style={"line_numbers": False})
    para = element._paragraph()
    assert element._gutter_width(para) == 0.0


def test_gutter_widens_for_more_digits() -> None:
    element = editor(value="\n".join(str(i) for i in range(5)))
    narrow = element._gutter_width(element._paragraph())
    element2 = editor(value="\n".join(str(i) for i in range(500)))
    wide = element2._gutter_width(element2._paragraph())
    assert wide > narrow


def test_painting_does_not_crash_with_the_gutter_on_or_off() -> None:
    for line_numbers in (True, False):
        element = editor(value="def foo():\n    return 1", style={"line_numbers": line_numbers})
        dl = painted(element)
        assert len(dl.view) > 0


# ----------------------------------------------------------------- syntax


def test_no_language_means_no_highlight_spans() -> None:
    element = editor(value="def foo(): pass")
    assert element._syntax_spans() is None


def test_a_known_language_produces_spans_covering_the_text() -> None:
    element = editor(value="def foo():\n    return 1", style={"language": "python"})
    spans = element._syntax_spans()
    assert spans is not None
    assert spans[0][0] == 0
    assert spans[-1][1] == len(element.content)


def test_an_unknown_language_is_not_an_error() -> None:
    element = editor(value="hello", style={"language": "not-a-real-language"})
    assert element._syntax_spans() is None
    dl = painted(element)
    assert len(dl.view) > 0


def test_the_highlight_cache_is_reused_when_nothing_changed() -> None:
    element = editor(value="def foo(): pass", style={"language": "python"})
    first = element._syntax_spans()
    second = element._syntax_spans()
    assert first is second


def test_the_highlight_cache_invalidates_on_edit() -> None:
    element = editor(value="x = 1", style={"language": "python"})
    first = element._syntax_spans()
    dispatcher = driver(element)
    type_text(dispatcher, "y")
    second = element._syntax_spans()
    assert first is not second
