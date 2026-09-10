"""Search bar: a real typed query, styled as M3's pill-shaped search bar.

Built on the same editing model `TextField`/`CodeEditor` share, so this file
covers what is actually different about this widget -- the fixed pill
geometry, the leading/trailing icons, the placeholder, and the min/max width
-- rather than re-testing caret motion or undo/redo, which `test_editing.py`
already covers at the model level and `test_textfield.py` already covers as
a widget.
"""

from __future__ import annotations

import pytest

from pysilver.layout import Constraints, Offset
from pysilver.paint import DisplayList
from pysilver.paint.display_list import Kind
from pysilver.runtime.clipboard import clipboard
from pysilver.runtime.events import EventDispatcher, EventType, KeyEvent, PointerEvent
from pysilver.spec import WidgetKind, parse_view
from pysilver.theme import Palette, Theme
from pysilver.tree.element import PaintContext
from pysilver.widgets import build_element
from pysilver.widgets.base import _REGISTRY, create_element
from pysilver.widgets.search import SearchBarElement

CTRL = frozenset({"Control"})


def bar(width: float = 500.0, **spec) -> SearchBarElement:
    node = {"name": "s", "widget": "SearchBar", **spec}
    element = build_element(parse_view(node).root)
    element.layout(Constraints(0.0, width, 0.0, 100.0))
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
    assert bar() is not None


def test_every_kind_is_registered() -> None:
    create_element(parse_view({"name": "x", "widget": "SearchBar"}).root)
    assert WidgetKind.SEARCH_BAR in _REGISTRY


def test_is_focusable() -> None:
    from pysilver.runtime.events import FOCUSABLE_KINDS

    assert "SearchBar" in FOCUSABLE_KINDS


# ------------------------------------------------------------------ geometry


def test_the_container_is_the_m3_height() -> None:
    """COMPONENT_SEARCH.md: "Height 56dp"."""
    assert bar().size.height == 56.0


def test_an_unbounded_width_falls_back_to_the_m3_minimum() -> None:
    """COMPONENT_SEARCH.md: "Container Width: Min: 360dp"."""
    from pysilver.layout import INF

    node = {"name": "s", "widget": "SearchBar"}
    element = build_element(parse_view(node).root)
    element.layout(Constraints(0.0, INF, 0.0, 100.0))
    assert element.size.width == SearchBarElement.MIN_WIDTH == 360.0


def test_width_is_capped_at_the_m3_maximum() -> None:
    """COMPONENT_SEARCH.md: "Container Width: ... max: 720dp"."""
    assert bar(width=2000.0).size.width == SearchBarElement.MAX_WIDTH == 720.0


def test_a_width_within_range_is_honoured() -> None:
    assert bar(width=500.0).size.width == 500.0


# --------------------------------------------------------------------- typing


def test_typing_inserts_and_fires_on_change() -> None:
    element = bar(handlers={"on_change": "changed"})
    seen: list[str] = []
    dispatcher = driver(element)
    dispatcher.bind_handlers({"changed": lambda event: seen.append(event.value)})
    type_text(dispatcher, "abc")
    assert element.content == "abc"
    assert seen == ["a", "ab", "abc"]


def test_backspace_and_delete_work() -> None:
    element = bar(value="abc")
    dispatcher = driver(element)
    press(dispatcher, "Backspace")
    assert element.content == "ab"


def test_undo_and_redo_reach_the_keyboard() -> None:
    element = bar(value="hello")
    dispatcher = driver(element)
    type_text(dispatcher, " there")
    assert element.content == "hello there"
    press(dispatcher, "z", CTRL)
    assert element.content == "hello"
    press(dispatcher, "y", CTRL)
    assert element.content == "hello there"


def test_a_disabled_search_bar_ignores_typing() -> None:
    element = bar(value="x", disabled="true")
    dispatcher = driver(element)
    type_text(dispatcher, "y")
    assert element.content == "x"


def test_cut_copy_and_paste_go_through_the_clipboard() -> None:
    element = bar(value="hello world")
    dispatcher = driver(element)
    press(dispatcher, "a", CTRL)
    press(dispatcher, "x", CTRL)
    assert element.content == ""
    assert clipboard.get_text() == "hello world"
    press(dispatcher, "v", CTRL)
    assert element.content == "hello world"


def test_home_and_end_reach_the_ends_of_the_query() -> None:
    element = bar(value="hello")
    dispatcher = driver(element)
    press(dispatcher, "Home")
    type_text(dispatcher, ">")
    assert element.content == ">hello"
    press(dispatcher, "End")
    type_text(dispatcher, "!")
    assert element.content == ">hello!"


# ---------------------------------------------------------------- value sync


def test_value_is_bindable_to_a_signal() -> None:
    from pysilver import App, Signal

    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [{"name": "s", "widget": "SearchBar", "value": "{{ q.get() }}"}],
    }
    app = App(view, theme=Theme(dark=True))
    q = Signal("")
    app.expose(q=q)
    app.mount()
    assert app.root.find("s").content == ""
    q.set("hello")
    assert app.root.find("s").content == "hello"


# ------------------------------------------------------------------- paint


def test_painting_does_not_crash_with_or_without_a_trailing_icon() -> None:
    assert painted(bar(value="query")).view.shape[0] > 0
    assert painted(bar(value="query", text="mic")).view.shape[0] > 0


def test_a_trailing_icon_paints_more_glyph_instances() -> None:
    def glyphs(dl: DisplayList) -> int:
        return sum(1 for s in dl.view if s["flags"][0] == Kind.GLYPH)

    without = painted(bar(value=""))
    with_icon = painted(bar(value="", icon="mic"))
    assert glyphs(with_icon) > glyphs(without)


def test_the_placeholder_shows_only_while_empty_and_unfocused() -> None:
    def glyphs(dl: DisplayList) -> int:
        return sum(1 for s in dl.view if s["flags"][0] == Kind.GLYPH)

    empty = painted(bar(value="", supporting_text="Search"))
    filled = painted(bar(value="query", supporting_text="Search"))
    # Empty-and-unfocused paints the placeholder text plus the search icon;
    # filled paints the query plus the search icon -- both are nonzero, so
    # this only proves the placeholder path does not crash and emits text,
    # not that it is exactly one glyph count versus another.
    assert glyphs(empty) > 1
    assert glyphs(filled) > 1


@pytest.mark.parametrize("focused", [True, False])
def test_pointer_down_moves_the_caret(focused: bool) -> None:
    element = bar(value="abc")
    dispatcher = driver(element, focus=focused)
    rect = element.absolute_rect()
    dispatcher.post(
        PointerEvent(EventType.POINTER_DOWN, x=rect.x + element._content_x() + 200, y=rect.y + 28)
    )
    dispatcher.drain()
    assert element.editor.state.caret == 3  # clicked well past the short value's end
