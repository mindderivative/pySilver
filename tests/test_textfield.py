"""The text field: the widget half of editable text.

`test_editing.py` covers what an edit does. This covers what the widget does
with keys and pixels -- the M3 dimensions, where the label goes, that the caret
stays in view, and that a bound `value:` and a user's typing do not fight.
"""

from __future__ import annotations

import pytest

from pysilver.layout import Constraints, Offset, Size
from pysilver.paint import DisplayList
from pysilver.paint.display_list import Kind
from pysilver.runtime.clipboard import clipboard
from pysilver.runtime.events import EventDispatcher, EventType, KeyEvent, PointerEvent
from pysilver.spec import parse_view
from pysilver.theme import Palette, Theme
from pysilver.tree.element import PaintContext
from pysilver.widgets import build_element
from pysilver.widgets.textfield import TextFieldElement

#: The spellings a real window sends. Tests that used lower-case ones are how
#: Shift+Tab and Ctrl+A came to be dead in a running application while their
#: tests passed, so these deliberately use GLFW's names.
CTRL = frozenset({"Control"})
SHIFT = frozenset({"Shift"})
CTRL_SHIFT = frozenset({"Control", "Shift"})


def field(width: float = 240.0, **spec) -> TextFieldElement:
    node = {"name": "f", "widget": "TextField", **spec}
    element = build_element(parse_view(node).root)
    element.layout(Constraints(0.0, width, 0.0, 400.0))
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


# ---------------------------------------------------------------- geometry


def test_the_container_is_the_m3_height() -> None:
    """M3_COMPONENT_SPECS 5.8: "Height 56dp" for both variants."""
    assert field(text="Name").size == Size(240.0, 56.0)


def test_supporting_text_adds_its_line_below_the_container() -> None:
    """ "Supporting text and character counter top padding: 4dp" -- so the
    element grows by that gap plus one `body-small` line, and the container
    itself stays 56dp."""
    grown = field(text="Name", supporting_text="Required")
    assert grown.size.height == 56.0 + 4.0 + 16.0


def test_an_unbounded_field_falls_back_to_its_own_minimum() -> None:
    """M3 states no minimum width. 120dp is pySilver's, so that a field in an
    unbounded Horizontal is still usable rather than invisible."""
    element = build_element(parse_view({"name": "f", "widget": "TextField"}).root)
    element.layout(Constraints(0.0, float("inf"), 0.0, float("inf")))
    assert element.size.width == TextFieldElement.MIN_WIDTH


def test_the_vertical_layout_tiles_the_container_exactly() -> None:
    """8dp padding, a 16dp floated label line, a 24dp input line, 8dp padding.
    If any of the four changes the input stops being centred in what is left,
    and nothing else here would catch it."""
    spec = TextFieldElement
    assert (
        spec.PAD_Y + spec.FLOAT_ROLE.line_height + spec.INPUT_ROLE.line_height + spec.PAD_Y
        == spec.HEIGHT
    )


# ------------------------------------------------------------------- label


def test_the_label_floats_when_populated_or_focused() -> None:
    """ "Label Behavior: Floats upward to 12sp typography scale when focused or
    populated" -- quoted. Both halves of the "or" are tested."""
    assert not field(text="Name").floated
    assert field(text="Name", value="Ada").floated
    focused = field(text="Name")
    driver(focused)
    assert focused.floated


def test_the_floated_size_is_the_12sp_role() -> None:
    assert TextFieldElement.FLOAT_ROLE.size == 12.0
    assert TextFieldElement.INPUT_ROLE.size == 16.0


# ---------------------------------------------------------------- keyboard


def test_typing_inserts_at_the_caret_and_fires_on_change() -> None:
    element = field(text="Name", value="Ada", handlers={"on_change": "changed"})
    seen: list[str] = []
    dispatcher = driver(element)
    dispatcher.bind_handlers({"changed": lambda event: seen.append(event.value)})
    type_text(dispatcher, "!")
    assert element.content == "Ada!"
    assert seen == ["Ada!"]


def test_backspace_and_delete_work_from_the_caret() -> None:
    element = field(value="abc")
    dispatcher = driver(element)
    press(dispatcher, "Backspace")
    assert element.content == "ab"
    press(dispatcher, "Home")
    press(dispatcher, "Delete")
    assert element.content == "b"


def test_arrows_move_and_shift_arrows_select() -> None:
    element = field(value="hello")
    dispatcher = driver(element)
    press(dispatcher, "ArrowLeft")
    assert element.editor.state.caret == 4
    press(dispatcher, "ArrowLeft", SHIFT)
    assert element.editor.state.selection == (3, 4)


def test_ctrl_arrows_move_by_word() -> None:
    element = field(value="hello world")
    dispatcher = driver(element)
    press(dispatcher, "ArrowLeft", CTRL)
    assert element.editor.state.caret == 6


def test_select_all_then_typing_replaces_everything() -> None:
    element = field(value="hello")
    dispatcher = driver(element)
    press(dispatcher, "a", CTRL)
    assert element.editor.state.selection == (0, 5)
    type_text(dispatcher, "x")
    assert element.content == "x"


def test_undo_and_redo_reach_the_keyboard() -> None:
    element = field(value="hello")
    dispatcher = driver(element)
    type_text(dispatcher, " there")
    assert element.content == "hello there"
    press(dispatcher, "z", CTRL)
    assert element.content == "hello"
    press(dispatcher, "z", CTRL_SHIFT)
    assert element.content == "hello there"


def test_cut_copy_and_paste_go_through_the_clipboard() -> None:
    element = field(value="hello world")
    dispatcher = driver(element)
    press(dispatcher, "a", CTRL)
    press(dispatcher, "x", CTRL)
    assert element.content == ""
    assert clipboard.get_text() == "hello world"
    press(dispatcher, "v", CTRL)
    assert element.content == "hello world"


def test_the_glfw_modifier_spelling_is_what_actually_arrives() -> None:
    """`rendercanvas` reports "Control", not "ctrl". Matching one spelling is
    how Ctrl+A came to be dead in a real window with a passing test, so this
    asserts the spelling a window sends and the one a hand-written event uses
    both work."""
    for spelling in ("Control", "ctrl", "Meta"):
        element = field(value="hello")
        press(driver(element), "a", frozenset({spelling}))
        assert element.editor.state.selection == (0, 5), spelling


def test_a_key_the_field_does_not_use_is_left_alone() -> None:
    """Tab has to keep traversing focus, so the field must not swallow every
    key it is handed."""
    element = field(value="hello")
    dispatcher = driver(element)
    event = KeyEvent(EventType.KEY_DOWN, key="F5")
    dispatcher.post(event)
    dispatcher.drain()
    assert not event.stopped


def test_a_disabled_field_ignores_typing() -> None:
    element = field(value="fixed", disabled="true")
    type_text(driver(element), "x")
    assert element.content == "fixed"


def test_control_characters_are_not_inserted() -> None:
    """A backend that reports Enter as text exists; inserting it would put an
    unprintable glyph in the value."""
    element = field(value="a")
    type_text(driver(element), "\n")
    assert element.content == "a"


# ------------------------------------------------------------------ pointer


def test_clicking_places_the_caret_where_the_glyphs_are() -> None:
    element = field(value="hello world")
    dispatcher = driver(element)
    rect = element.absolute_rect()
    dispatcher.post(
        PointerEvent(EventType.POINTER_DOWN, x=rect.x + TextFieldElement.PAD_X + 0.5, y=rect.y + 30)
    )
    dispatcher.drain()
    assert element.editor.state.caret == 0


def test_a_second_click_selects_a_word() -> None:
    element = field(value="hello world")
    dispatcher = driver(element)
    rect = element.absolute_rect()
    point = {"x": rect.x + TextFieldElement.PAD_X + 2.0, "y": rect.y + 30}
    for _ in range(2):
        dispatcher.post(PointerEvent(EventType.POINTER_DOWN, **point))
        dispatcher.post(PointerEvent(EventType.POINTER_UP, **point))
    dispatcher.drain()
    assert element.editor.state.selected_text == "hello"


def test_the_cursor_over_a_field_is_a_text_cursor() -> None:
    element = field(value="hello")
    dispatcher = driver(element, focus=False)
    rect = element.absolute_rect()
    dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=rect.x + 30, y=rect.y + 30))
    dispatcher.drain()
    assert dispatcher.cursor == "text"


# ------------------------------------------------------------------- value


def test_a_bound_value_the_application_changes_replaces_the_content() -> None:
    element = field(value="one")
    element._value = "two"
    assert element.content == "two"


def test_an_edit_does_not_get_clobbered_by_its_own_value_update() -> None:
    """The edit writes back to `value:`, so a naive "spec wins" rule would undo
    every keystroke on the next read."""
    element = field(value="a")
    type_text(driver(element), "b")
    assert element.content == "ab"
    assert element.content == "ab", "still, on a second read"


def test_an_external_change_moves_the_caret_to_the_end() -> None:
    element = field(value="one")
    driver(element)
    element._value = "much longer text"
    assert element.editor.state.caret == len("much longer text")


# ------------------------------------------------------------------- paint


def painted(element) -> DisplayList:
    display_list = DisplayList()
    ctx = PaintContext(
        display_list=display_list,
        palette=Palette(Theme()),
        text=element.text_engine,
        pixel_ratio=1.0,
    )
    element.set_text_engine(ctx.text)
    element.paint(ctx, Offset(0.0, 0.0))
    return display_list


def boxes(display_list: DisplayList) -> int:
    return sum(1 for instance in display_list.view if int(instance["flags"][0]) == Kind.BOX)


def test_a_filled_field_draws_a_container_and_an_indicator() -> None:
    assert boxes(painted(field(value="Ada"))) == 2


def test_focusing_draws_the_caret() -> None:
    element = field(value="Ada")
    before = boxes(painted(element))
    driver(element)
    assert boxes(painted(element)) > before, "the caret is a box and it was not there"


def test_the_caret_has_real_height_on_an_empty_field() -> None:
    """`caret_at` used to special-case an empty paragraph to an all-zero
    rect, which produced a genuinely invisible (0-tall) caret on any
    freshly focused, empty field -- found live, since every existing test
    up to this point focused a field that already had a value."""
    element = field()
    driver(element)
    dl = painted(element)
    caret = next(
        s
        for s in dl.view
        if int(s["flags"][0]) == Kind.BOX and float(s["rect"][2]) == element.CARET_WIDTH
    )
    assert float(caret["rect"][3]) > 0.0


def test_an_outlined_label_centres_on_the_border_inside_a_full_height_patch() -> None:
    """Real M3 has the floated label sit centred ON the border line, visibly
    overlapping it -- confirmed against a user-supplied M3 screenshot. A
    first attempt erased only a thin band matching the border's own 2dp
    stroke while the label's own line box is much taller, leaving most of
    each letter directly adjacent to un-erased, colour-matched border ink at
    the patch's left/right edges -- unreadable, not because the label
    overlapped the border, but because the patch didn't fully cover it.
    Fixed by sizing the patch to the label's whole line height instead."""
    element = field(text="Search", style={"variant": "outlined"})
    driver(element)
    dl = painted(element)
    glyphs = [s for s in dl.view if int(s["flags"][0]) == Kind.GLYPH]
    assert glyphs, "the label should have painted glyphs"
    tops = [float(s["rect"][1]) for s in glyphs]
    bottoms = [float(s["rect"][1]) + float(s["rect"][3]) for s in glyphs]
    assert min(tops) < 0.0, "the label should reach above the border line"
    assert max(bottoms) > 0.0, "the label should also overlap below it"

    # The erasure patch must fully contain the label's own vertical extent --
    # not just a thin band matching the border's own stroke -- so no
    # un-erased, colour-matched border ink sits adjacent to any letter.
    surface = Palette(Theme()).index("surface")
    patches = [
        s
        for s in dl.view
        if int(s["flags"][0]) == Kind.BOX
        and int(s["flags"][2]) == surface
        and tuple(float(v) for v in s["radii"]) == (0.0, 0.0, 0.0, 0.0)
    ]  # excludes the outlined container's own (radius'd, alpha=0) surface-token box
    assert patches, "the label should paint an erasure patch behind it"
    patch = patches[0]
    patch_top = float(patch["rect"][1])
    patch_bottom = patch_top + float(patch["rect"][3])
    assert patch_top <= min(tops), "the patch must reach as high as the label does"
    assert patch_bottom >= max(bottoms), "the patch must reach as low as the label does"


def test_a_selection_draws_a_highlight() -> None:
    element = field(value="Ada")
    dispatcher = driver(element)
    plain = boxes(painted(element))
    press(dispatcher, "a", CTRL)
    assert boxes(painted(element)) > plain


# ------------------------------------------------------------ native input


def test_the_canvas_char_payload_inserts_the_typed_character() -> None:
    """Guards the boundary with rendercanvas, the same way
    `test_scroll.py::test_the_canvas_wheel_payload_drives_scrolling` guards
    the wheel payload. `rendercanvas/glfw.py` submits the typed character
    under `data` (with `char_str` as a compat alias due for removal) -- not
    `char`, which every real keystroke silently read as missing, inserting
    an empty string every time. Caught live: typing into a real window's
    TextField visibly did nothing, while every dispatcher-level test kept
    passing because they all post `KeyEvent(EventType.TEXT, ...)` directly,
    bypassing this exact translation layer entirely."""
    from pysilver import App, Settings, Theme

    app = App(
        {"root": {"name": "f", "widget": "TextField"}},
        theme=Theme(dark=True),
        settings=Settings(width=300, height=200),
    )
    app.mount()
    app.update()
    element = app.root
    app.dispatcher.focus(element)

    app._on_canvas_event({"event_type": "char", "data": "z", "char_str": "z", "modifiers": ()})
    app.dispatcher.drain()

    assert element.content == "z"


def test_reduce_motion_gives_a_solid_caret() -> None:
    """Everything else obeys the setting by arriving at once. The equivalent
    for something that never arrives is to stop it moving -- a caret that
    blinked anyway would be the one animation the setting did not reach."""
    from pysilver.motion import Ticker

    element = field(value="Ada")
    element.set_ticker(Ticker(reduce_motion=True))
    driver(element)
    assert element._caret_visible()
    assert element._caret_visible(), "and it stays visible, rather than blinking"


# ------------------------------------------------------------------ scroll


def test_the_caret_stays_in_view_when_the_text_outruns_the_field() -> None:
    element = field(width=140.0, value="")
    dispatcher = driver(element)
    type_text(dispatcher, "a value far longer than this field is wide")
    assert element._scroll_x > 0.0, "the view followed the caret"


def test_the_view_scrolls_back_rather_than_leaving_empty_space() -> None:
    element = field(width=140.0, value="")
    dispatcher = driver(element)
    type_text(dispatcher, "a value far longer than this field is wide")
    for _ in range(60):
        press(dispatcher, "Backspace")
    assert element.content == ""
    assert element._scroll_x == 0.0


def test_short_text_never_scrolls() -> None:
    element = field(width=240.0, value="hi")
    driver(element)
    assert element._scroll_x == 0.0


@pytest.mark.parametrize("variant", ["filled", "outlined"])
def test_both_m3_variants_render(variant: str) -> None:
    element = field(text="Name", value="Ada", style={"variant": variant})
    assert len(painted(element)) > 0


@pytest.mark.parametrize("variant", ["filled", "outlined"])
def test_an_error_field_paints_the_error_token(variant: str) -> None:
    """`error:` drives the same accent slot focus otherwise would -- the
    indicator for filled, the border for outlined -- even while unfocused."""
    element = field(value="Ada", style={"variant": variant}, error="true")
    dl = painted(element)
    error_token = Palette(Theme()).index("error")
    tokens = {int(s["flags"][2]) for s in dl.view} | {int(s["flags"][3]) for s in dl.view}
    assert error_token in tokens


# ---------------------------------------------------------------- multiline

LONG = "This is a long value that will certainly wrap onto several lines here."


def relayout(element, width: float = 240.0) -> None:
    element.layout(Constraints(0.0, width, 0.0, 600.0))


def test_a_multiline_field_starts_the_height_of_a_single_line_one() -> None:
    """COMPONENT_TEXT_FIELDS: multi-line fields "initially appear as
    single-line fields", which is what makes them usable in a compact layout."""
    assert field(text="Notes", style={"multiline": True}).size.height == 56.0


def test_a_multiline_field_grows_with_its_content() -> None:
    """ "Multi-line text fields grow to accommodate multiple lines of text" --
    quoted. The container is padding, the floated label line, one line per
    wrapped line, and padding."""
    grown = field(text="Notes", value=LONG, style={"multiline": True})
    lines = len(grown._paragraph().lines)
    assert lines > 1, "the value has to actually wrap for this to test anything"
    expected = TextFieldElement.PAD_Y * 2 + TextFieldElement.FLOAT_ROLE.line_height
    expected += lines * TextFieldElement.INPUT_ROLE.line_height
    assert grown.size.height == expected


def test_a_single_line_field_never_wraps_however_long_the_value() -> None:
    plain = field(value=LONG)
    assert plain.size.height == 56.0
    assert len(plain._paragraph().lines) == 1, "it scrolls sideways instead"


def test_a_height_makes_it_a_text_area_that_scrolls() -> None:
    """M3's other form: "text areas are fixed-height fields" that "scroll
    vertically when the cursor reaches the bottom". The difference between the
    two forms is exactly whether the author fixed a height, so no second
    property invents it."""
    area = field(value=LONG * 4, style={"multiline": True, "height": 140})
    assert area.size.height == 140.0
    area.editor.set_caret(len(area.content))
    area._scroll_to_caret()
    assert area._scroll_y > 0.0, "the caret at the end must have scrolled it down"
    assert area._scroll_x == 0.0, "a wrapped field has nowhere to scroll sideways"


def test_enter_inserts_a_newline_only_in_a_multiline_field() -> None:
    """On a single-line field Enter is left to bubble, so a view can handle it
    -- swallowing it to insert an invisible newline would be worse than
    useless."""
    multi = field(style={"multiline": True})
    dispatcher = driver(multi)
    type_text(dispatcher, "one")
    press(dispatcher, "Enter")
    type_text(dispatcher, "two")
    assert multi.content == "one\ntwo"

    single = field()
    single_driver = driver(single)
    type_text(single_driver, "one")
    press(single_driver, "Enter")
    assert single.content == "one"


def test_a_newline_makes_the_field_taller() -> None:
    element = field(style={"multiline": True})
    dispatcher = driver(element)
    before = element.size.height
    type_text(dispatcher, "one")
    press(dispatcher, "Enter")
    type_text(dispatcher, "two")
    relayout(element)
    assert element.size.height == before + TextFieldElement.INPUT_ROLE.line_height


def test_up_and_down_move_by_a_line_as_drawn() -> None:
    """Which character sits a line above is a question about wrapping, not
    about the string, so it is resolved against the laid-out paragraph."""
    element = field(style={"multiline": True})
    dispatcher = driver(element)
    type_text(dispatcher, "first")
    press(dispatcher, "Enter")
    type_text(dispatcher, "second")
    relayout(element)
    press(dispatcher, "ArrowUp")
    assert element.editor.state.caret <= 5, "it landed on the first line"
    press(dispatcher, "ArrowDown")
    assert element.editor.state.caret > 5, "and back down to the second"


def test_the_column_is_preserved_across_lines() -> None:
    """Down from the end of a short line lands at the same *x* on the next one,
    not at its start -- which is what makes arrow navigation feel like a text
    editor rather than like walking the string."""
    element = field(style={"multiline": True})
    dispatcher = driver(element)
    type_text(dispatcher, "abc")
    press(dispatcher, "Enter")
    type_text(dispatcher, "abcdefghij")
    relayout(element)
    press(dispatcher, "Home")
    press(dispatcher, "ArrowUp")
    press(dispatcher, "End")
    assert element.editor.state.caret == 3, "end of the first line"
    press(dispatcher, "ArrowDown")
    assert 4 <= element.editor.state.caret <= 8, "same column on the longer line"


def test_home_and_end_are_line_relative_when_wrapped() -> None:
    """And End stops *before* the newline. `TextLine.end` is where the next
    line starts, so using it directly puts the caret on the line below and
    typing appears on the wrong one."""
    element = field(style={"multiline": True})
    dispatcher = driver(element)
    type_text(dispatcher, "first")
    press(dispatcher, "Enter")
    type_text(dispatcher, "second")
    relayout(element)
    press(dispatcher, "ArrowUp")
    press(dispatcher, "Home")
    assert element.editor.state.caret == 0
    press(dispatcher, "End")
    assert element.editor.state.caret == 5, "before the newline at 5, not after it"


def test_shift_with_a_vertical_arrow_selects() -> None:
    element = field(style={"multiline": True})
    dispatcher = driver(element)
    type_text(dispatcher, "first")
    press(dispatcher, "Enter")
    type_text(dispatcher, "second")
    relayout(element)
    press(dispatcher, "ArrowUp", SHIFT)
    assert element.editor.state.has_selection


def test_clicking_a_wrapped_line_uses_the_y_as_well_as_the_x() -> None:
    element = field(value=LONG, style={"multiline": True})
    relayout(element)
    rect = element.absolute_rect()
    first = element._offset_at(rect.x + TextFieldElement.PAD_X + 4.0, rect.y + 30.0)
    second = element._offset_at(
        rect.x + TextFieldElement.PAD_X + 4.0,
        rect.y + 30.0 + TextFieldElement.INPUT_ROLE.line_height,
    )
    assert second > first, "the lower click landed further into the text"


def test_a_multiline_field_paints_at_the_width_it_measured() -> None:
    """The bug this catches shipped for an hour: `_paragraph` wrapped to the
    inner width and `paint_text` was never given one, so layout sized a
    container for two lines and paint drew a single unwrapped one.

    The paragraph cache keys on the wrap width, so measuring and painting at
    different widths leaves two entries. A single-line field legitimately has
    one width -- None -- so this asks the question the same way for both.
    """
    from pysilver.layout import Offset
    from pysilver.text import TextEngine

    for multiline in (True, False):
        engine = TextEngine()
        style = {"width": 240, "multiline": multiline}
        element = build_element(
            parse_view({"name": "f", "widget": "TextField", "value": LONG, "style": style}).root
        )
        element.set_text_engine(engine)
        relayout(element)
        ctx = PaintContext(
            display_list=DisplayList(), palette=Palette(Theme()), text=engine, pixel_ratio=1.0
        )
        element.paint(ctx, Offset(0.0, 0.0))
        widths = {key[2] for key in engine._layouts if key[0] == LONG}
        assert len(widths) == 1, f"multiline={multiline}: measured and painted at {widths}"
        if multiline:
            assert widths != {None}, "a multiline field must wrap to a real width"
