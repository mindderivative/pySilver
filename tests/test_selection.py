"""Mouse text selection.

Two layers: the geometry in `text/selection.py`, which maps points to
character offsets and back, and the `Text` widget that drives it.
"""

from __future__ import annotations

import pytest

from pysilver import App, Settings, Theme
from pysilver.paint import DisplayList
from pysilver.runtime.clipboard import Clipboard, clipboard
from pysilver.runtime.events import EventType, KeyEvent, PointerEvent
from pysilver.text import TextEngine
from pysilver.text.editing import Affinity
from pysilver.text.selection import caret_at, index_at, rects_for, word_at

ENGINE = TextEngine()


def para(text: str, px: float = 20.0, max_width: float | None = None):
    return ENGINE.layout(text, px=px, max_width=max_width)


# ---------------------------------------------------------------- geometry


def test_a_point_maps_to_a_character_offset() -> None:
    p = para("Hello world")
    assert index_at(p, 0.0, 5.0) == 0
    assert index_at(p, 10_000.0, 5.0) == len(p.text)


def test_the_offset_increases_across_the_line() -> None:
    p = para("Hello world")
    offsets = [index_at(p, x, 5.0) for x in range(0, 120, 10)]
    assert offsets == sorted(offsets)


def test_the_nearest_edge_wins_not_the_containing_glyph() -> None:
    """Clicking the left half of a character puts the caret before it. Anything
    else makes click-and-drag feel like it lags a character behind."""
    p = para("Hello")
    rects = rects_for(p, 0, 1)
    first = rects[0]
    assert index_at(p, first.width * 0.1, 5.0) == 0
    assert index_at(p, first.width * 0.9, 5.0) == 1


def test_an_offset_never_lands_inside_a_grapheme_cluster() -> None:
    """A base character and its combining accent are one unit; a caret between
    them would render as a stray mark."""
    text = "ábc"  # 'a' + combining acute
    p = para(text)
    reachable = {index_at(p, x, 5.0) for x in range(0, 80, 2)}
    assert 1 not in reachable, "the caret split a combining sequence"
    assert reachable <= {0, 2, 3, 4}


def test_an_empty_range_produces_no_rectangle() -> None:
    """A caret is not a selection; a zero-width rect is a stray sliver."""
    assert rects_for(para("Hello"), 3, 3) == []


def test_a_reversed_range_is_normalised() -> None:
    """Dragging right-to-left must highlight the same thing."""
    p = para("Hello world")
    assert rects_for(p, 7, 2) == rects_for(p, 2, 7)


def test_a_wrapped_selection_gives_one_rectangle_per_line() -> None:
    p = para("the quick brown fox jumps over the lazy dog", px=16, max_width=120)
    assert len(p.lines) > 1
    rects = rects_for(p, 0, len(p.text))
    assert len(rects) == len(p.lines)
    assert [r.y for r in rects] == sorted(r.y for r in rects)


def test_a_point_below_the_text_clamps_to_the_last_line() -> None:
    p = para("one\ntwo", max_width=200)
    assert index_at(p, 0.0, 10_000.0) >= p.lines[-1].start


def test_empty_text_maps_to_zero() -> None:
    assert index_at(para(""), 50.0, 50.0) == 0
    assert rects_for(para(""), 0, 5) == []


@pytest.mark.parametrize(
    ("offset", "expected"),
    [(0, "Hello"), (3, "Hello"), (7, "world"), (11, "world")],
)
def test_word_at_finds_the_surrounding_word(offset: int, expected: str) -> None:
    text = "Hello world"
    start, end = word_at(text, offset)
    assert text[start:end] == expected


def test_word_at_on_empty_text_is_safe() -> None:
    assert word_at("", 0) == (0, 0)


# --------------------------------------------------------------------- bidi


def test_caret_at_zero_lands_at_the_right_edge_of_pure_rtl_text() -> None:
    """Inverted from LTR intuition, and the point of this whole feature:
    offset 0 (before the FIRST character) is where reading STARTS, and RTL
    reading starts at the right. Real Arabic glyphs, not a hand-built
    level array -- this exercises the actual bundled font + HarfBuzz RTL
    shaping + `caret_at`'s own per-run direction handling together."""
    p = para("مرحبا")
    zero = caret_at(p, 0)
    end = caret_at(p, len(p.text))
    assert zero.x == pytest.approx(p.size.width)
    assert end.x == pytest.approx(0.0)
    assert zero.x > end.x


def test_caret_at_moves_monotonically_backward_through_rtl_text() -> None:
    """As the logical offset increases (reading further into the RTL word),
    the caret moves right-to-left on screen -- the mirror image of LTR,
    checked as a monotonic sequence rather than individual pixel values so
    this doesn't depend on any one font's specific glyph metrics."""
    p = para("مرحبا")
    xs = [caret_at(p, offset).x for offset in range(len(p.text) + 1)]
    assert xs == sorted(xs, reverse=True)


def test_index_at_is_inverted_for_pure_rtl_text() -> None:
    """Clicking near the visual left edge of RTL text lands near the END of
    the text (offset close to len), and the right edge lands near the
    START (offset close to 0) -- the opposite of `test_the_offset_increases_
    across_the_line`'s own LTR expectation."""
    p = para("مرحبا")
    near_left = index_at(p, 1.0, 5.0)
    near_right = index_at(p, p.size.width - 1.0, 5.0)
    assert near_left > near_right


def test_rects_for_splits_across_a_direction_boundary() -> None:
    """A selection that is logically contiguous but visually crosses an
    LTR/RTL boundary highlights as TWO disjoint rectangles, not one rect
    spanning the visual gap between them -- the real behavioural change
    `rects_for` gained for this feature (`_spans_x`)."""
    p = para("lo مرحبا")
    # "o مر" -- starts in the LTR prefix, ends partway into the RTL word.
    start = p.text.index("o")
    end = p.text.index("مر") + 2
    rects = rects_for(p, start, end)
    assert len(rects) == 2
    first, second = sorted(rects, key=lambda r: r.x)
    assert first.x + first.width <= second.x, "the two rects must not overlap"


def test_rects_for_a_pure_ltr_selection_still_gives_one_rect() -> None:
    """The multi-rect change is a strict generalisation -- text with no
    direction boundary at all must still produce exactly one rect per line,
    matching every existing LTR test in this file."""
    p = para("Hello world")
    assert len(rects_for(p, 0, len(p.text))) == 1


def test_caret_affinity_changes_where_a_boundary_offset_renders() -> None:
    """The load-bearing affinity test: proves `affinity` is actually
    threaded through and changes rendered output, not just accepted and
    ignored. At the boundary between an LTR prefix and an embedded RTL
    word, UPSTREAM (content already read) lands at the end of the LTR
    prefix; DOWNSTREAM (content about to be read, the default) lands at
    the RTL word's own reading-start -- its far visual RIGHT edge, since
    Arabic reads right-to-left. These are genuinely different points, not
    a rounding difference."""
    p = para("lo مرحبا")
    boundary = p.text.index("م")
    upstream = caret_at(p, boundary, affinity=Affinity.UPSTREAM)
    downstream = caret_at(p, boundary, affinity=Affinity.DOWNSTREAM)
    assert upstream.x != downstream.x
    # Sanity-check the actual semantics, not just "they differ": upstream
    # sits at the LTR prefix's own end; downstream sits at the RTL word's
    # own far edge, which is further right (Arabic starts at the right).
    assert upstream.x < downstream.x


def test_caret_at_default_affinity_is_downstream() -> None:
    """Omitting `affinity` must behave identically to passing DOWNSTREAM
    explicitly -- the keyword's own default, not a separate code path."""
    p = para("lo مرحبا")
    boundary = p.text.index("م")
    assert caret_at(p, boundary).x == caret_at(p, boundary, affinity=Affinity.DOWNSTREAM).x


def test_selecting_the_whole_mixed_line_still_gives_one_rect() -> None:
    """Selecting EVERYTHING is trivially contiguous in both logical and
    visual space regardless of internal direction boundaries -- multi-rect
    splitting is specifically for a PARTIAL range that crosses one."""
    p = para("lo مرحبا")
    assert len(rects_for(p, 0, len(p.text))) == 1


# ------------------------------------------------------------------ widget


def hosted(*, selectable: bool = True, text: str = "Hello selectable world"):
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface", "padding": 10},
                "children": [
                    {
                        "name": "t",
                        "widget": "Text",
                        "text": text,
                        "style": {
                            "font_size": 20,
                            "selectable": selectable,
                            "width": 300,
                            "height": 40,
                        },
                    },
                    {"name": "plain", "widget": "Text", "text": "label", "style": {"height": 30}},
                ],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=340, height=140),
    )
    app.mount()
    app.paint(DisplayList())
    return app, app.root.find("t")


def drag(app: App, widget, x0: float, x1: float, y: float = 14.0) -> None:
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=x0, y=y))
    app.dispatcher.drain()
    widget.state.pressed = True
    app.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=x1, y=y))
    app.dispatcher.drain()
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=x1, y=y))
    app.dispatcher.drain()
    app.paint(DisplayList())


def test_dragging_selects_text() -> None:
    app, text = hosted()
    drag(app, text, 12, 70)
    assert text.selected_text
    assert text.selected_text in "Hello selectable world"


def test_a_plain_label_selects_nothing() -> None:
    """Selectable is off by default: a label that shows a text cursor and
    swallows drags is wrong for most of the text in an interface."""
    app, text = hosted(selectable=False)
    drag(app, text, 12, 70)
    assert text.selected_text == ""


def test_selectable_text_takes_focus_so_it_can_be_copied() -> None:
    """Key events go to the focused element, so without this Ctrl+C reaches
    nothing at all."""
    app, text = hosted()
    drag(app, text, 12, 70)
    assert app.dispatcher.focused is text


def test_a_plain_label_is_not_focusable() -> None:
    app, _text = hosted()
    assert not app.dispatcher._focusable(app.root.find("plain"))


def test_ctrl_c_copies_the_selection() -> None:
    app, text = hosted()
    drag(app, text, 12, 70)
    expected = text.selected_text
    clipboard.install(None)
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="c", modifiers=frozenset({"ctrl"})))
    app.dispatcher.drain()
    assert clipboard.get_text() == expected


def test_ctrl_a_selects_everything() -> None:
    app, text = hosted()
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=12, y=14))
    app.dispatcher.drain()
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="a", modifiers=frozenset({"ctrl"})))
    app.dispatcher.drain()
    assert text.selected_text == "Hello selectable world"


def test_a_bare_key_does_nothing() -> None:
    app, text = hosted()
    text.select_all()
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="c"))
    app.dispatcher.drain()
    assert text.selected_text == "Hello selectable world", "an unmodified key changed it"


def test_selectable_text_shows_a_text_cursor() -> None:
    app, _text = hosted()
    app.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=50, y=14))
    app.dispatcher.drain()
    assert app.dispatcher.cursor == "text"


def test_an_explicit_cursor_still_wins() -> None:
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [
                    {
                        "name": "t",
                        "widget": "Text",
                        "text": "hi",
                        "style": {
                            "selectable": True,
                            "cursor": "crosshair",
                            "width": 200,
                            "height": 40,
                        },
                    }
                ],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=240, height=100),
    )
    app.mount()
    app.paint(DisplayList())
    app.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=20, y=10))
    app.dispatcher.drain()
    assert app.dispatcher.cursor == "crosshair"


def test_the_highlight_is_painted_behind_the_glyphs() -> None:
    """Over them it would tint the letters it is meant to sit behind."""
    from pysilver.paint import Kind

    app, text = hosted()
    text.select_all()
    dl = DisplayList()
    app.paint(dl)
    kinds = [int(s["flags"][0]) for s in dl.view]
    boxes = [i for i, k in enumerate(kinds) if k == int(Kind.BOX)]
    glyphs = [i for i, k in enumerate(kinds) if k == int(Kind.GLYPH)]
    assert boxes and glyphs
    assert min(boxes) < min(glyphs)


def test_selecting_nothing_paints_no_highlight() -> None:
    app, text = hosted()
    before = len(list(iter_view(app)))
    text.select_all()
    after = len(list(iter_view(app)))
    assert after > before
    text.clear_selection()
    assert len(list(iter_view(app))) == before


def iter_view(app: App):
    dl = DisplayList()
    app.paint(dl)
    return list(dl.view)


# --------------------------------------------------------------- clipboard


def test_a_bare_clipboard_is_in_process() -> None:
    """With no backend, copying still works within the application. `Engine`
    installs the system one when it creates a real window; a `Clipboard` built
    by hand, and every headless use, keeps this behaviour."""
    board = Clipboard()
    assert not board.system_backed
    assert board.set_text("hi") is False
    assert board.get_text() == "hi", "the in-process copy must still work"


def test_an_application_can_install_a_real_one() -> None:
    board = Clipboard()
    seen: list[str] = []

    class Fake:
        def set_text(self, text: str) -> bool:
            seen.append(text)
            return True

        def get_text(self) -> str:
            return "from system"

    board.install(Fake())
    assert board.system_backed
    assert board.set_text("copied") is True
    assert seen == ["copied"]
    assert board.get_text() == "from system"


def test_a_failing_backend_never_breaks_a_frame() -> None:
    board = Clipboard()

    class Broken:
        def set_text(self, text: str) -> bool:
            raise RuntimeError("no clipboard here")

        def get_text(self) -> str:
            raise RuntimeError("no clipboard here")

    board.install(Broken())
    assert board.set_text("x") is False
    assert board.get_text() == "x", "it lost the in-process copy on failure"


def test_an_empty_read_falls_back_to_the_in_process_copy() -> None:
    """On Wayland a client may only read the selection while it holds keyboard
    focus, and an unfocused read comes back empty rather than failing. Treating
    that as "the clipboard is empty" would break pasting inside the
    application, so an empty result is a miss and the local copy wins.
    """
    board = Clipboard()

    class Silent:
        def set_text(self, text: str) -> bool:
            return True

        def get_text(self) -> str:
            return ""

    board.install(Silent())
    board.set_text("copied here")
    assert board.get_text() == "copied here"


def test_installing_none_returns_to_in_process() -> None:
    board = Clipboard()

    class Fake:
        def set_text(self, text: str) -> bool:
            return True

        def get_text(self) -> str:
            return "from system"

    board.install(Fake())
    assert board.get_text() == "from system"
    board.install(None)
    assert not board.system_backed
    board.set_text("local")
    assert board.get_text() == "local"


def test_the_glfw_backend_degrades_when_there_is_no_window() -> None:
    """It reports failure rather than silently succeeding.

    The binding *warns* on failure instead of raising, so a plain try/except
    reports a successful write for one that did nothing -- which is what this
    did at first. It asks GLFW for the error code instead.
    """
    from pysilver.runtime.clipboard import GlfwClipboard

    backend = GlfwClipboard()
    assert backend.set_text("x") is False, "claimed success with no GLFW"
    assert backend.get_text() == ""


def test_a_glfw_failure_still_leaves_a_working_in_process_clipboard() -> None:
    from pysilver.runtime.clipboard import GlfwClipboard

    board = Clipboard()
    board.install(GlfwClipboard())
    assert board.set_text("copied") is False, "no window, so it did not reach the system"
    assert board.get_text() == "copied", "but the application can still paste into itself"
