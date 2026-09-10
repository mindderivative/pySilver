"""Terminal: a real shell, spawned and parsed internally.

M3 has no terminal component -- checked directly, not assumed absent, the
same way every other ungrounded widget this session was.

Most tests here never spawn a real process: `TerminalElement` only starts
its PTY session from `set_ticker()` (called by `App`, never by a bare
`build_element(...).layout(...)`), so rendering and key-forwarding logic is
exercised by attaching a `bittty` board directly (`_attach_board`) or by
injecting a fake session (`_FakeSession`) -- the same seam the widget's own
`_feed()` method exists for. A handful of tests at the bottom spawn a real
`/bin/sh` to prove the actual pipeline works end to end, skipped if
`bittty`/`pexpect` are not installed.
"""

from __future__ import annotations

import sys
import time

import pytest

from pysilver.layout import INF, Constraints, Size
from pysilver.motion.animation import Ticker
from pysilver.runtime.events import (
    FOCUSABLE_KINDS,
    EventDispatcher,
    EventType,
    KeyEvent,
    WheelEvent,
)
from pysilver.spec import WidgetKind, parse_view
from pysilver.widgets import build_element
from pysilver.widgets.registry import _REGISTRY
from pysilver.widgets.terminal import (
    _BITTTY_AVAILABLE,
    _PTY_AVAILABLE,
    TerminalElement,
    _cell_color,
)

try:
    from bittty.devices.board import Board
    from bittty.style import Color
except ImportError:
    Board = None  # type: ignore[assignment,misc]
    Color = None  # type: ignore[assignment,misc]

CTRL = frozenset({"Control"})
SHIFT = frozenset({"Shift"})

REAL_PTY = _BITTTY_AVAILABLE and _PTY_AVAILABLE and sys.platform != "win32"


def terminal(width: float = 400.0, height: float = 200.0, **spec) -> TerminalElement:
    node = {"name": "t", "widget": "Terminal", **spec}
    element = build_element(parse_view(node).root)
    element.layout(Constraints(0.0, width, 0.0, height))
    return element


def _attach_board(element: TerminalElement, cols: int = 20, rows: int = 5) -> None:
    """Give the element a real `bittty` board with no real PTY behind it."""
    element._cols, element._rows = cols, rows
    element._board = Board(command="/bin/sh", width=cols, height=rows)


def _cell_text(board, x: int, y: int) -> str:
    return board.blitter.current_page.get_cell(x, y)[1]


class _FakeSession:
    def __init__(self, alive: bool = True) -> None:
        self.alive = alive
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)


def driver(element, *, focus: bool = True) -> EventDispatcher:
    dispatcher = EventDispatcher()
    dispatcher.root = element
    if focus:
        dispatcher.focus(element)
    return dispatcher


def press(dispatcher, key: str, modifiers=frozenset()) -> None:
    dispatcher.post(KeyEvent(EventType.KEY_DOWN, key=key, modifiers=modifiers))
    dispatcher.drain()


# --------------------------------------------------------------- registered


def test_kind_builds() -> None:
    assert terminal() is not None


def test_every_kind_is_registered() -> None:
    assert set(_REGISTRY) == set(WidgetKind)


def test_is_focusable() -> None:
    assert "Terminal" in FOCUSABLE_KINDS


def test_never_started_shows_the_unavailable_message_not_a_crash() -> None:
    """No `set_ticker` call means no PTY session -- `build_element(...)
    .layout(...)` alone must never spawn a process."""
    element = terminal()
    assert element._session is None
    assert element._board is None


def test_set_ticker_alone_does_not_spawn_either() -> None:
    """Not just a bare `layout()` -- `set_ticker()` alone, before any real
    `perform_layout` call, must not spawn a process either. Spawning only
    happens once BOTH a ticker exists AND the real target grid is known --
    see `perform_layout`'s own docstring on why the shell must never be
    spawned at a placeholder size."""
    element = build_element(parse_view({"name": "t", "widget": "Terminal"}).root)
    element.set_ticker(Ticker())
    assert element._session is None
    assert element._board is None


@pytest.mark.skipif(not REAL_PTY, reason="bittty/pexpect not available on this platform")
def test_the_shell_spawns_at_the_real_target_grid_not_the_default() -> None:
    """Found live: this widget used to spawn the shell at `DEFAULT_COLS`/
    `DEFAULT_ROWS` (80x24) from `set_ticker()`, then correct the size once
    `perform_layout` ran -- and by the time that correction landed, the
    shell had typically already drawn a full prompt at the wrong width.
    Many shells (zsh-syntax-highlighting among them) redraw badly when
    resized *after* they have already drawn a prompt, leaving stray
    wrapped remnants and a spurious "%" line -- reproduced with pySilver's
    own code not even involved (see the module docstring). The fix defers
    the actual spawn to the first `perform_layout` call, once
    `self._cols`/`self._rows` already hold the real target -- assert the
    `Board` itself was constructed at that size, not the placeholder
    default."""
    element = terminal(width=300.0, height=150.0)  # narrow: real target != default
    real_target = (element._cols, element._rows)
    assert real_target != (TerminalElement.DEFAULT_COLS, TerminalElement.DEFAULT_ROWS)
    element.set_ticker(Ticker())
    try:
        assert element._board is not None
        assert (element._board.width, element._board.height) == real_target
    finally:
        element.dispose()


# ------------------------------------------------------------------ layout


def test_an_unbounded_size_falls_back_to_the_default_grid() -> None:
    element = build_element(parse_view({"name": "t", "widget": "Terminal"}).root)
    element.layout(Constraints(0.0, INF, 0.0, INF))
    assert element._cols == TerminalElement.DEFAULT_COLS
    assert element._rows == TerminalElement.DEFAULT_ROWS


def test_a_bounded_size_is_honoured() -> None:
    element = terminal(width=500.0, height=300.0)
    assert element.size == Size(500.0, 300.0)


def test_the_grid_follows_the_pixel_size() -> None:
    small = terminal(width=200.0, height=100.0)
    large = terminal(width=800.0, height=400.0)
    assert large._cols > small._cols
    assert large._rows > small._rows


def test_resizing_an_attached_board_is_debounced_then_applied() -> None:
    """`_apply_grid`'s trade, mirroring `Engine._pin_surface`: an already-live
    board does not reflow on every intermediate size during a drag (see the
    2026-09 resize investigation -- a reflow forces the whole grid's text to
    re-shape, since every run's text changes), only once the target has sat
    still for `GRID_SETTLE_SECONDS`."""
    element = terminal(width=300.0, height=150.0)
    _attach_board(element, cols=element._cols, rows=element._rows)
    before = (element._board.width, element._board.height)
    element.layout(Constraints(0.0, 900.0, 0.0, 450.0))
    assert (element._board.width, element._board.height) == before, "not yet, still debounced"
    assert element._pending_grid is not None and element._pending_grid != before

    element._pending_grid_since -= TerminalElement.GRID_SETTLE_SECONDS + 0.01
    element._maybe_apply_pending_grid()

    after = (element._board.width, element._board.height)
    assert after != before
    assert element._board.width == element._cols
    assert element._board.height == element._rows
    assert element._pending_grid is None


def test_a_resize_during_the_settle_window_re_arms_it() -> None:
    """A drag is not one clean jump from old size to new -- a second, still
    different, target mid-window must not let the first one sneak through."""
    element = terminal(width=300.0, height=150.0)
    _attach_board(element, cols=element._cols, rows=element._rows)
    before = (element._cols, element._rows)

    element.layout(Constraints(0.0, 900.0, 0.0, 450.0))
    first_target = element._pending_grid
    element._pending_grid_since -= TerminalElement.GRID_SETTLE_SECONDS - 0.02
    element._maybe_apply_pending_grid()
    assert (element._cols, element._rows) == before, "settle window not elapsed yet"

    element.layout(Constraints(0.0, 700.0, 0.0, 350.0))
    second_target = element._pending_grid
    assert second_target != first_target, "the second target replaced the first"
    element._maybe_apply_pending_grid()
    assert (element._cols, element._rows) == before, "re-armed, not counting down from before"

    element._pending_grid_since -= TerminalElement.GRID_SETTLE_SECONDS + 0.01
    element._maybe_apply_pending_grid()
    assert (element._cols, element._rows) == second_target
    assert element._pending_grid is None


# ------------------------------------------------------------------ command


def test_shell_defaults_to_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/zsh")
    element = terminal()
    assert element._command() == "/bin/zsh"


def test_shell_falls_back_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    element = terminal()
    assert element._command() == "/bin/sh"


def test_an_explicit_shell_style_wins(monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/zsh")
    element = terminal(style={"shell": "bash -l"})
    assert element._command() == "bash -l"


# --------------------------------------------------------------------- font


def test_the_default_font_is_genuinely_monospace() -> None:
    """Found live, 2026-09-08: defaulting to Roboto (proportional) left the
    cursor visibly detached from typed text by several columns, since the
    cell/cursor grid assumes every glyph shares one advance width. Assert
    the fix directly rather than trusting a visual impression -- "M" and a
    narrow letter like "i" must measure identically, and a short run like
    "hello" must land exactly on `n * cell_width`, not merely close to it."""
    element = terminal()
    request = element._font_request()
    assert request.family == "Hack Nerd Font Mono"
    engine = element.text_engine
    cell = element._cell_size()
    m_width = engine.measure("M", px=element.style.font_size, request=request).width
    i_width = engine.measure("i", px=element.style.font_size, request=request).width
    hello_width = engine.measure("hello", px=element.style.font_size, request=request).width
    assert m_width == i_width == cell.width
    assert hello_width == 5 * cell.width


def test_the_default_font_covers_the_prompt_glyphs_that_used_to_be_tofu() -> None:
    """`pySilver Terminal Symbol Glyph Coverage Gap`: fish-pure/starship-style
    prompts draw U+21E1 (upwards dashed arrow, the git-ahead marker) and
    U+276F (heavy right-pointing angle quotation mark, the prompt symbol)
    -- confirmed live as real, reproducible tofu boxes under the old
    Roboto/Noto Sans-only stack, which has no Arrows/Dingbats coverage.
    Hack Nerd Font Mono's ~9,000 Nerd Font glyphs close this specific gap."""
    element = terminal()
    request = element._font_request()
    db = element.text_engine.db
    for codepoint in (0x21E1, 0x276F):
        char = chr(codepoint)
        face = db.resolve(char, request)
        assert face.covers_all(char), f"U+{codepoint:04X} still falls through to .notdef"
        assert face.family == "Hack Nerd Font Mono"


def test_an_explicit_font_family_overrides_the_monospace_default() -> None:
    element = terminal(style={"font_family": "Roboto"})
    assert element._font_request().family == "Roboto"


# ------------------------------------------------------------------- colour


def test_named_ansi_colours_resolve() -> None:
    assert _cell_color(Color("indexed", 1), (0, 0, 0, 1)) != (0, 0, 0, 1)  # red
    assert _cell_color(Color("indexed", 12), (0, 0, 0, 1)) != (0, 0, 0, 1)  # brightblue


def test_default_falls_back_to_the_given_colour() -> None:
    default = (0.1, 0.2, 0.3, 1.0)
    assert _cell_color(None, default) == default
    assert _cell_color(Color("default"), default) == default


def test_an_rgb_colour_is_converted() -> None:
    """`(255, 128, 0)` is sRGB 100%/50%/0% -- converted to linear, red stays
    at 1.0 (a fixed point of the sRGB curve) but green drops well below its
    sRGB reading, which is exactly the point of the conversion (see
    `_srgb`)."""
    r, g, b, a = _cell_color(Color("rgb", (255, 128, 0)), (0, 0, 0, 1))
    assert round(r, 2) == 1.0
    assert 0.15 < g < 0.30
    assert b == 0.0
    assert a == 1.0


def test_an_extended_indexed_colour_resolves() -> None:
    """Beyond the 16 named ANSI colours, `Color`'s mode is always a known
    literal -- there is no free-form "unrecognised name" case any more, so
    this exercises the 256-colour cube and greyscale-ramp branches instead
    of `_cell_color`'s defensive default fallback."""
    default = (0.1, 0.2, 0.3, 1.0)
    assert _cell_color(Color("indexed", 200), default) != default  # 6x6x6 cube
    assert _cell_color(Color("indexed", 244), default) != default  # greyscale ramp


# -------------------------------------------------------------- rendering


@pytest.mark.skipif(Board is None, reason="bittty not installed")
def test_feeding_bytes_renders_without_crashing() -> None:
    element = terminal()
    _attach_board(element)
    element._feed(b"hello\r\n")
    from pysilver.paint import DisplayList
    from pysilver.theme import Palette, Theme
    from pysilver.tree.element import PaintContext

    ctx = PaintContext(display_list=DisplayList(), palette=Palette(Theme(dark=True)))
    element.paint(ctx, element.offset.__class__(0.0, 0.0))
    assert len(ctx.display_list.view) > 0


@pytest.mark.skipif(Board is None, reason="bittty not installed")
def test_coloured_output_paints_more_than_plain_text() -> None:
    from pysilver.paint import DisplayList
    from pysilver.theme import Palette, Theme
    from pysilver.tree.element import PaintContext

    def render(data: bytes) -> int:
        element = terminal()
        _attach_board(element)
        element._feed(data)
        ctx = PaintContext(display_list=DisplayList(), palette=Palette(Theme(dark=True)))
        element.paint(ctx, element.offset.__class__(0.0, 0.0))
        return len(ctx.display_list.view)

    plain = render(b"plain text\r\n")
    coloured = render(b"\x1b[41mred background\x1b[0m\r\n")
    assert coloured > plain


# --------------------------------------------------------------- scrollback


def test_wheel_does_nothing_without_scrollback() -> None:
    """`bittty` keeps no scrollback buffer (see the module docstring) --
    wheeling over a Terminal, attached board or not, must never raise, and
    must not consume the event (it is left to propagate to a containing
    `ScrollView` instead)."""
    element = terminal()
    element.on_wheel(WheelEvent(EventType.WHEEL, dy=-100.0))  # no board: must not raise

    if Board is not None:
        _attach_board(element, cols=20, rows=5)
        element.on_wheel(WheelEvent(EventType.WHEEL, dy=-100.0))  # must not raise either


# ------------------------------------------------------------------ keyboard


def test_typing_forwards_utf8_bytes() -> None:
    element = terminal()
    element._session = _FakeSession()
    element.on_text(KeyEvent(EventType.TEXT, text="q"))
    assert element._session.written == [b"q"]


def test_control_characters_in_on_text_are_ignored() -> None:
    """`on_key_down` handles named/control keys by name; `on_text` must not
    also forward their raw control-code text, or a key like Enter would be
    sent to the shell twice."""
    element = terminal()
    element._session = _FakeSession()
    element.on_text(KeyEvent(EventType.TEXT, text="\r"))
    assert element._session.written == []


def test_arrow_keys_send_the_expected_escape_sequences() -> None:
    element = terminal()
    element._session = _FakeSession()
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="ArrowUp"))
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="ArrowDown"))
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="ArrowLeft"))
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="ArrowRight"))
    assert element._session.written == [b"\x1b[A", b"\x1b[B", b"\x1b[D", b"\x1b[C"]


def test_enter_and_backspace() -> None:
    element = terminal()
    element._session = _FakeSession()
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="Enter"))
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="Backspace"))
    assert element._session.written == [b"\r", b"\x7f"]


def test_ctrl_c_sends_the_interrupt_byte_not_a_copy() -> None:
    element = terminal()
    element._session = _FakeSession()
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="c", modifiers=CTRL))
    assert element._session.written == [b"\x03"]


def test_ctrl_d_sends_end_of_transmission() -> None:
    element = terminal()
    element._session = _FakeSession()
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="d", modifiers=CTRL))
    assert element._session.written == [b"\x04"]


def test_tab_sends_a_tab_byte_and_shift_tab_sends_back_tab() -> None:
    element = terminal()
    element._session = _FakeSession()
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="Tab", modifiers=SHIFT))
    assert element._session.written == [b"\t", b"\x1b[Z"]


def test_tab_does_not_move_focus_away_from_the_terminal() -> None:
    """The same dispatcher-level fix `CodeEditor` needed: `CAPTURES_TAB`
    keeps Tab routed here instead of the dispatcher's default focus
    traversal."""
    element = terminal()
    element._session = _FakeSession()
    dispatcher = driver(element)
    press(dispatcher, "Tab")
    assert dispatcher.focused is element
    assert element._session.written == [b"\t"]


def test_paste_writes_the_clipboard() -> None:
    from pysilver.runtime.clipboard import clipboard

    clipboard.set_text("pasted text")
    element = terminal()
    element._session = _FakeSession()
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="v", modifiers=CTRL))
    assert element._session.written == [b"pasted text"]


def test_disabled_terminal_ignores_input() -> None:
    element = terminal(disabled="true")
    element._session = _FakeSession()
    element.on_text(KeyEvent(EventType.TEXT, text="q"))
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="Enter"))
    assert element._session.written == []


def test_no_session_means_no_crash_on_input() -> None:
    element = terminal()
    element.on_text(KeyEvent(EventType.TEXT, text="q"))
    element.on_key_down(KeyEvent(EventType.KEY_DOWN, key="Enter"))  # must not raise


def test_write_input_is_public_and_reaches_the_session() -> None:
    element = terminal()
    element._session = _FakeSession()
    element.write_input("echo hi\n")
    assert element._session.written == [b"echo hi\n"]


# --------------------------------------------------------------- disposal


def test_dispose_stops_the_session() -> None:
    element = terminal()
    stopped = []

    class _Session(_FakeSession):
        def stop(self) -> None:
            stopped.append(True)

    element._session = _Session()
    element.dispose()
    assert stopped == [True]
    assert element._session is None


# -------------------------------------------------------- real end to end


@pytest.mark.skipif(not REAL_PTY, reason="bittty/pexpect not available on this platform")
def test_a_real_shell_produces_visible_output() -> None:
    element = terminal(width=400.0, height=200.0, style={"shell": "/bin/sh -c 'echo hello-pty'"})
    element.set_ticker(Ticker())
    try:
        deadline = time.monotonic() + 5.0
        found = False
        while time.monotonic() < deadline:
            element._drain_pty()
            if element._board is not None and any(
                "hello-pty" in "".join(_cell_text(element._board, c, r) for c in range(20))
                for r in range(5)
            ):
                found = True
                break
            time.sleep(0.05)
        assert found, "the real shell's output never reached the bittty board"
    finally:
        element.dispose()


@pytest.mark.skipif(not REAL_PTY, reason="bittty/pexpect not available on this platform")
def test_a_real_shell_receives_keyboard_input() -> None:
    element = terminal(width=400.0, height=200.0, style={"shell": "/bin/cat"})
    element.set_ticker(Ticker())
    try:
        element.on_text(KeyEvent(EventType.TEXT, text="p"))
        deadline = time.monotonic() + 5.0
        found = False
        while time.monotonic() < deadline:
            element._drain_pty()
            if element._board is not None and "p" in "".join(
                _cell_text(element._board, c, 0) for c in range(10)
            ):
                found = True
                break
            time.sleep(0.05)
        assert found, "typed input never echoed back through the real pty"
    finally:
        element.dispose()


@pytest.mark.skipif(not REAL_PTY, reason="bittty/pexpect not available on this platform")
def test_the_spawned_shell_gets_a_real_term_value() -> None:
    """Found live: `pexpect.spawn` inherits `os.environ` verbatim unless
    told otherwise, which is fine for a CLI tool (always itself launched
    from inside a real terminal) but not for a GUI widget that can be
    launched from anywhere -- a desktop icon, an IDE run button, a bare
    subprocess with no controlling terminal. With TERM unset, `/bin/sh`
    (dash) falls back to its own internal default of `TERM=dumb` --
    confirmed directly (`/usr/bin/env` shows no TERM at all reaches the
    child's real environment; the shell supplies "dumb" itself) -- and
    zsh under zsh-syntax-highlighting, seeing `dumb`, emits its
    per-keystroke recolour redraw WITHOUT the cursor-backspace bytes it
    uses for a real terminal, so typed characters visibly duplicate and
    reorder on screen. `_PtySession.start` now defaults TERM to a real
    value (never overriding an application's own explicit one), the same
    convention a comparable project (termqt) uses."""
    element = terminal(width=400.0, height=200.0, style={"shell": "/bin/sh -c 'echo TERM=$TERM'"})
    element.set_ticker(Ticker())
    try:
        deadline = time.monotonic() + 5.0
        line = ""
        while time.monotonic() < deadline:
            element._drain_pty()
            if element._board is not None:
                line = "".join(_cell_text(element._board, c, 0) for c in range(30))
                if "TERM=" in line:
                    break
            time.sleep(0.05)
        assert "TERM=" in line, "the shell's own $TERM was never observed"
        value = line.split("TERM=", 1)[1].strip()
        assert value not in ("", "dumb"), f"TERM must name a real terminal, got {value!r}"
    finally:
        element.dispose()
