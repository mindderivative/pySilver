"""Terminal: a real shell, spawned and parsed internally.

M3 has no terminal component -- checked directly against `M3-References`,
the same way every other ungrounded widget this session was. Asked of the
user directly, the same way `Video`'s frame-sink-vs-bundled-decoder fork
was: should this widget only render a cell grid an application feeds it
(`Video`'s own shape), or own the whole pipeline -- spawning the shell and
parsing its output -- internally? The answer was the latter: a view says
`widget: Terminal, style: {shell: "/bin/bash"}` and it works, with no
per-application PTY or VT-parsing boilerplate.

**Three layers, two of them someone else's problem.** Spawning a real
pseudo-terminal is OS-specific process management; interpreting its byte
stream is the VT/ANSI state machine every real terminal emulator implements
identically. Neither is this widget's own concern to reinvent -- `pexpect`
(ISC) gives POSIX PTY spawning, `bittty` (WTFPL) gives the state machine,
and what is actually left for pySilver to build is the third layer:
rendering whatever cell grid `bittty.Board`'s video memory says is currently
true, and turning keystrokes into the bytes a shell expects. Both are
optional extras (`pysilver[terminal]`), never hard dependencies.

**`bittty` replaced `pyte` here (2026-09-08), found live.** A single real
keystroke, under zsh with zsh-syntax-highlighting active, could corrupt the
whole input line ("echo hi" rendering as "echoo o hi"). Confirmed a real
`pyte` (0.8.2, the latest release; the project has seen no meaningful update
in years) parsing defect, not a pySilver bug: reproduced with zero pySilver
code involved (bare `pexpect` + `pyte` fed the exact same bytes), independent
of typing speed, independent of how the byte stream was chunked, and gone
entirely once the shell plugin responsible for the redraw sequences was
disabled. `bittty` renders the identical byte stream correctly. pySilver
still owns PTY spawning/reading/writing via `pexpect`/`_PtySession`
unchanged -- only the VT/ANSI state machine consuming those bytes changed,
via `bittty.devices.board.Board` used purely as a parser (`start_process()`,
`bittty`'s own PTY spawning, is never called -- its rendering/chrome layer
has no notion of pySilver's own GPU display-list pipeline, so pySilver still
has to translate cells into display-list primitives regardless of which
`bittty` class is used; `Board` alone is the right amount of integration).

**Known regression from this swap: no scrollback.** `bittty` keeps no
scrollback buffer (a documented limitation, not an oversight -- confirmed
against its own README), unlike `pyte.HistoryScreen`. Mouse-wheel scrollback
is dropped for now; re-implementing it against `bittty` is tracked as a
separate follow-up, not part of this fix.

**A second, real corruption bug -- pySilver's own, found live right after
the `bittty` swap.** Switching VT libraries did not fix a garbled, doubled
prompt with a spurious "%" line at startup, because that was never a VT
parsing defect: this widget always spawned the shell at `DEFAULT_COLS`/
`DEFAULT_ROWS` (80x24) from `set_ticker()`, then corrected it to the real
size once `perform_layout` ran. By the time that correction landed, the
shell had typically already drawn a full prompt at the wrong (80-column)
width -- and many shells, zsh-syntax-highlighting among them, redraw badly
when resized *after* they have already drawn a prompt, leaving stray
wrapped remnants of the old-width draw plus zsh's own "incomplete line"
marker (`%`). Reproduced with pySilver's own code not even involved (bare
`pexpect` + `bittty`): spawning directly at any target width from 30 to 80
columns, with no resize at all, was clean every time; spawning at 80 and
resizing to the real width milliseconds later -- before the shell could
draw anything -- was also clean; spawning at 80, letting the shell fully
draw its prompt, *then* resizing was corrupted every time, identically to
what the real widget showed live. Fixed by deferring the actual spawn
(`_ensure_started`) out of `set_ticker()` and into the first real
`perform_layout` call, once `self._cols`/`self._rows` already hold the
widget's true target grid -- see `perform_layout`'s own docstring.

**Only POSIX is implemented and verified in this pass.** `pexpect.spawn`
was exercised directly (spawn a shell, read its output through
`read_nonblocking`, feed it to `bittty`, read the resulting cell grid back)
before being relied on. Windows needs a different backend entirely --
`pywinpty` wrapping ConPTY; `pexpect.spawn` is POSIX-only -- architected for
(the platform check is a real branch) but not built, since nothing here
could verify it rather than guess. `sys.platform == "win32"` leaves the
widget simply unstarted rather than guessing at an unverified API, the
honest choice `AccessKit`'s own "untested on Windows and macOS" precedent
already sets.

**No PTY mutation happens off the engine thread.** The background reader
thread's only job is to append raw bytes to a lock-guarded buffer --
ARCHITECTURE.md 8's "the engine thread owns everything mutable" applies to
the `bittty.Board` exactly as it does to a `Signal`, so feeding the byte
stream and repainting both happen later, back on the engine thread, in
`_drain_pty()`. When a real `asyncio` loop can be captured, the reader
thread also calls `loop.call_soon_threadsafe(...)` to wake an idle app
promptly -- the identical pattern `VideoElement.push_frame`'s own docstring
already prescribes for "a worker thread has news". Whether or not that wake
succeeds, `paint_self` unconditionally drains pending bytes on every call it
gets for any reason -- and while a session is alive this widget keeps a
`repeat=True` animation running purely to guarantee a repaint (regardless of
focus, so a terminal nobody is looking at still updates), roughly twice a
second either way. The wake is an optimisation for instant updates, not a
correctness requirement -- output is never permanently stuck even if loop
capture fails.

**Defaults to a real bundled monospace font (`Hack Nerd Font Mono`), found
live 2026-09-08 -- it did not before.** Cell backgrounds and the cursor are
positioned on an analytic `column * cell_width` grid regardless of the
resolved font's own metrics, so they always line up; the *glyphs drawn
inside* a run of same-styled cells are laid out with the text engine's
ordinary shaping, which only lands exactly on that grid when the requested
font is genuinely monospace. Defaulting to `"Roboto"` (proportional, the
same gap `CodeEditor` used to have) left `"hello"` shaping ~2.5 cell-widths
narrower than the grid assumed -- confirmed by direct `TextEngine.measure`
comparison, not just visual impression -- so the cursor visibly detached
from typed text by several columns after only a few keystrokes. Fixed by
bundling `assets.MONOSPACE_FONT` and defaulting `_font_request()` to it
whenever `style.font_family` is unset -- confirmed zero drift by the same
measurement (`M`, `i`, and `hello` all land exactly on the grid). An
application can still override with any other face via `style.font_family`,
same as before; see `assets/fonts/README.md`'s "Monospace" section for the
measurement and provenance.

**Nerd Font icon coverage closes a separately-diagnosed gap.** The original
`NotoSansMono` fix above left a related but distinct problem: the bundled
Roboto/Noto Sans set has no Arrows, Dingbats, or Private-Use-Area coverage,
so icon-heavy shell prompt themes (starship, fish-pure, `eza --icons`) drew
their own glyphs -- e.g. U+21E1 (upwards dashed arrow) and U+276F (heavy
right-pointing angle quotation mark) -- as visible missing-glyph boxes,
confirmed live and reproduced through the real VT parser (see the
`pySilver Terminal Symbol Glyph Coverage Gap` history). `MONOSPACE_FONT` was
later swapped from `NotoSansMono-Regular.ttf` to `HackNerdFontMono-Regular.ttf`
specifically to close this: same genuinely-uniform monospace advance width
(confirmed directly via the font's own `hmtx` table, icon glyphs included,
not just Latin letters), plus ~9,000 Nerd-Font-patched icon glyphs covering
the prompt-theme content that used to render as tofu. `HackNerdFontMono`'s
own embedded license metadata is MIT + Bitstream Vera, not the OFL the
`nerd-fonts` project's top-level `LICENSE` claims for patched fonts --
verified directly against the shipped font file, not assumed from the
project's README; see `assets/fonts/README.md`.

**The spawned shell now gets a real `TERM`, found live 2026-09-08.**
`_PtySession.start` used to call `pexpect.spawn` with no `env=`, inheriting
`os.environ` verbatim -- fine for a CLI tool always itself launched from
inside a real terminal, wrong for a GUI widget launched from anywhere (a
desktop icon, an IDE run button, a bare subprocess with no controlling
terminal). With `TERM` genuinely unset, `/bin/sh` falls back to its own
internal default of `TERM=dumb`, and zsh under zsh-syntax-highlighting,
seeing `dumb`, emits its per-keystroke recolour redraw WITHOUT the
cursor-backspace bytes it uses for a real terminal -- reproduced directly by
capturing the raw pty bytes both ways -- so typed characters visibly
duplicated and reordered on screen (typing "hello" then Backspace x3 showed
"hhheellllol l e" instead of "he"). Fixed by defaulting `TERM` (and, as a
companion, `COLUMNS`/`LINES`) in the child's environment, matching the exact
convention a comparable project (`termqt`, a Qt PTY-backed terminal widget)
uses -- `env.get(..., default)` rather than an unconditional overwrite, so
an application's own explicit `TERM` still wins. Not a `bittty` parsing
defect and not a pySilver threading/chunking race: confirmed by feeding
`bittty.Board.feed_host_data` the exact captured byte sequence directly
(zero pySilver code involved) and getting the identical garbled result,
then again with a corrected `TERM` and getting the correct one.

**Deliberately out of scope for this pass**: mouse text selection and
copy (Ctrl+C is always the interrupt byte here, never a copy shortcut,
since there is nothing to copy without a selection), underline and
strikethrough rendering, function keys beyond F1-F4, true-colour-aware
theme adaptation (the ANSI palette is fixed, not part of the M3 theme),
scrollback (see above), and Windows support.
"""

from __future__ import annotations

import contextlib
import os
import shlex
import sys
import threading
import time
from collections.abc import Callable
from typing import Any, Final, override

import numpy as np

from ..assets import MONOSPACE_FONT
from ..layout import Constraints, EdgeInsets, Offset, Padding, Size
from ..paint import NO_TOKEN
from ..runtime.clipboard import clipboard
from ..runtime.events import is_accelerator, modifiers_of
from ..spec import WidgetSpec
from ..text.fontdb import FontRequest
from ..theme import srgb_to_linear
from ..tree.element import PaintContext
from .base import _StyledMixin

__all__ = ["TerminalElement"]

try:
    from bittty.devices.board import Board

    _BITTTY_AVAILABLE = True
except ImportError:
    _BITTTY_AVAILABLE = False

if sys.platform != "win32":
    try:
        import pexpect

        _PTY_AVAILABLE = True
    except ImportError:
        _PTY_AVAILABLE = False
else:
    _PTY_AVAILABLE = False


def _srgb(r: float, g: float, b: float, a: float = 1.0) -> tuple[float, float, float, float]:
    """An sRGB-intended colour, converted to the linear RGBA every literal
    `color=` on the display list actually expects.

    Verified empirically, not assumed: the render target is
    `rgba8unorm-srgb` (ARCHITECTURE.md 5.6.1), which encodes linear values
    written to it -- a literal `color=(0.5, 0.5, 0.5, 1.0)` reads back as
    `(188, 188, 188)`, not `(128, 128, 128)`, unless converted first. Passing
    unconverted "looks about right" floats is exactly the double-encoding
    bug ARCHITECTURE.md 5.6.1 already documents for the palette upload path;
    this is the same mistake, once removed, on a literal colour instead.
    """
    lr, lg, lb = srgb_to_linear(np.array([r, g, b], dtype=np.float64))
    return (float(lr), float(lg), float(lb), a)


#: The conventional 16-colour ANSI palette. Not M3-sourced -- there is no M3
#: concept of terminal colour at all -- literal RGBA for the identical reason
#: `CodeEditor`'s syntax colours are: no semantic role exists to map any of
#: this onto. Tuned to read against a dark background; there is no light
#: variant, the same one-scheme choice `CodeEditor` makes. Written as the
#: sRGB values they are meant to look like; `_srgb()` converts each to the
#: linear form the shader actually wants.
_ANSI_COLORS: Final[dict[str, tuple[float, float, float, float]]] = {
    "black": _srgb(0.11, 0.11, 0.13),
    "red": _srgb(0.87, 0.35, 0.35),
    "green": _srgb(0.55, 0.75, 0.40),
    "brown": _srgb(0.85, 0.70, 0.35),  # ANSI yellow
    "blue": _srgb(0.40, 0.60, 0.90),
    "magenta": _srgb(0.75, 0.50, 0.85),
    "cyan": _srgb(0.40, 0.75, 0.80),
    "white": _srgb(0.80, 0.80, 0.82),
    "brightblack": _srgb(0.40, 0.42, 0.46),
    "brightred": _srgb(0.95, 0.45, 0.45),
    "brightgreen": _srgb(0.65, 0.85, 0.50),
    "brightbrown": _srgb(0.95, 0.80, 0.45),
    "brightblue": _srgb(0.55, 0.70, 0.95),
    "brightmagenta": _srgb(0.85, 0.60, 0.95),
    "brightcyan": _srgb(0.55, 0.85, 0.90),
    "brightwhite": _srgb(0.95, 0.95, 0.97),
}
#: `Color(mode="indexed", value=N)` for N in 0-15 names into `_ANSI_COLORS`
#: in standard ANSI order (0-7 normal, 8-15 bright).
_ANSI_INDEX_NAMES: Final[tuple[str, ...]] = (
    "black",
    "red",
    "green",
    "brown",
    "blue",
    "magenta",
    "cyan",
    "white",
    "brightblack",
    "brightred",
    "brightgreen",
    "brightbrown",
    "brightblue",
    "brightmagenta",
    "brightcyan",
    "brightwhite",
)
_DEFAULT_FG: Final = _srgb(0.85, 0.85, 0.88)
_DEFAULT_BG: Final = _srgb(0.10, 0.10, 0.12)


def _cell_color(
    color: Any, default: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    """A `bittty` cell colour (`None`, or a `Color` in "default"/"indexed"/
    "rgb" mode) resolved to linear RGBA.

    The indexed branch beyond 0-15 is the standard xterm 256-colour table:
    16-231 a 6x6x6 cube (`0, 95, 135, 175, 215, 255` per axis step), 232-255
    a 24-step greyscale ramp (`8` to `238`, step `10`) -- the same formula
    every terminal emulator (and `pyte` itself) uses, not an approximation.
    """
    if color is None or color.mode == "default":
        return default
    if color.mode == "rgb":
        r, g, b = color.value
        return _srgb(r / 255.0, g / 255.0, b / 255.0)
    if color.mode == "indexed":
        index = color.value
        if 0 <= index < 16:
            return _ANSI_COLORS[_ANSI_INDEX_NAMES[index]]
        if 16 <= index < 232:
            cube = index - 16
            r, g, b = cube // 36, (cube // 6) % 6, cube % 6

            def scale(v: int) -> float:
                return 0.0 if v == 0 else (55 + v * 40) / 255.0

            return _srgb(scale(r), scale(g), scale(b))
        if 232 <= index < 256:
            level = (index - 232) * 10 + 8
            v = level / 255.0
            return _srgb(v, v, v)
    return default


#: Named keys translated to the bytes a POSIX terminal sends for them
#: (xterm's own "normal" cursor-key mode, not application mode -- pySilver
#: never negotiates DECCKM). Plain character keys are deliberately absent:
#: those arrive through `on_text` instead, and including them here would
#: send every printable character twice.
_KEY_BYTES: Final[dict[str, bytes]] = {
    "arrowup": b"\x1b[A",
    "up": b"\x1b[A",
    "arrowdown": b"\x1b[B",
    "down": b"\x1b[B",
    "arrowright": b"\x1b[C",
    "right": b"\x1b[C",
    "arrowleft": b"\x1b[D",
    "left": b"\x1b[D",
    "home": b"\x1b[H",
    "end": b"\x1b[F",
    "pageup": b"\x1b[5~",
    "pagedown": b"\x1b[6~",
    "delete": b"\x1b[3~",
    "insert": b"\x1b[2~",
    "f1": b"\x1bOP",
    "f2": b"\x1bOQ",
    "f3": b"\x1bOR",
    "f4": b"\x1bOS",
    "enter": b"\r",
    "return": b"\r",
    "backspace": b"\x7f",
    "escape": b"\x1b",
}


class _PtySession:
    """Owns exactly one background thread: reading a pty is a blocking
    syscall, and the only thing that thread does is append raw bytes to a
    lock-guarded buffer. Feeding them to `bittty` and repainting both happen
    later, back on the engine thread -- see the module docstring.
    """

    def __init__(self, command: str) -> None:
        self._command = command
        self._child: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pending = bytearray()
        self._loop: Any = None
        self._on_output: Callable[[], None] | None = None

    @property
    def alive(self) -> bool:
        return self._child is not None and bool(self._child.isalive())

    def start(self, size: tuple[int, int], on_output: Callable[[], None]) -> None:
        self._on_output = on_output
        try:
            import asyncio

            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop running yet (or ever) -- see the module docstring:
            # the periodic repaint fallback covers this, just less promptly.
            self._loop = None
        cols, rows = size
        parts = shlex.split(self._command) or ["/bin/sh"]
        # `pexpect.spawn` inherits `os.environ` verbatim when `env=` is
        # omitted -- fine for a CLI tool that is always itself launched from
        # inside a real terminal (TERM already set correctly by whatever
        # spawned it), wrong for a GUI widget that can be launched from
        # anywhere (a desktop icon, an IDE run button, a bare subprocess
        # with no controlling terminal at all). With TERM genuinely unset,
        # `/bin/sh` (dash) falls back to its own internal default of
        # `TERM=dumb` -- confirmed directly (`env` shows no TERM reaches the
        # child's real environment at all; the shell supplies "dumb" itself)
        # -- and zsh under zsh-syntax-highlighting, seeing `dumb`, emits its
        # per-keystroke recolour redraw WITHOUT the cursor-backspace bytes it
        # uses for a real terminal, so typing visibly duplicated and
        # reordered characters on screen. `TERM`/`COLUMNS`/`LINES` matches
        # the exact convention a comparable real project (termqt, a Qt
        # PTY-backed terminal widget) uses for the identical reason;
        # `env.get(..., default)` rather than an unconditional overwrite so
        # an application's own explicit TERM (or COLUMNS/LINES) still wins.
        env = dict(os.environ)
        env["TERM"] = env.get("TERM") or "xterm-256color"
        env.setdefault("COLUMNS", str(cols))
        env.setdefault("LINES", str(rows))
        self._child = pexpect.spawn(
            parts[0], parts[1:], dimensions=(rows, cols), encoding=None, timeout=None, env=env
        )
        self._thread = threading.Thread(target=self._run, name="pysilver-terminal", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                chunk = self._child.read_nonblocking(size=4096, timeout=0.2)
            except pexpect.TIMEOUT:
                continue
            except Exception:
                break  # EOF (process exited) or the fd was closed under us
            if not chunk:
                continue
            with self._lock:
                self._pending.extend(chunk)
            if self._loop is not None and self._on_output is not None:
                self._loop.call_soon_threadsafe(self._on_output)

    def drain(self) -> bytes:
        with self._lock:
            data, self._pending = bytes(self._pending), bytearray()
        return data

    def write(self, data: bytes) -> None:
        if self._child is not None and self._child.isalive():
            self._child.send(data)

    def resize(self, cols: int, rows: int) -> None:
        if self._child is not None and self._child.isalive():
            self._child.setwinsize(rows, cols)

    def stop(self) -> None:
        self._stop.set()
        if self._child is not None:
            with contextlib.suppress(Exception):
                self._child.close(force=True)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


class _BitttyConnection:
    """Adapts `_PtySession.write` to `bittty`'s `Connection` protocol
    (`write(str)`), so a `Board`'s own internal auto-replies -- device status
    reports, cursor position reports, and any other query a shell or its
    plugins may issue -- reach the real pty. `_PtySession` still owns PTY
    spawning and reading; this only wires the reply-writing direction, the
    same "screen writes back to the process" seam `pyte`'s own
    `write_process_input` extension point existed for.
    """

    closed = False

    def __init__(self, session: _PtySession) -> None:
        self._session = session

    def write(self, data: str) -> None:
        self._session.write(data.encode("utf-8", "ignore"))

    def resize(self, rows: int, cols: int) -> None:
        """No-op: `TerminalElement._apply_grid` already resizes the real pty
        directly through `_PtySession.resize`; `Board.resize()` calls this
        too, but there is nothing further to do here."""


class TerminalElement(_StyledMixin, Padding):
    """A real shell, rendered as a grid of styled monospace cells.

    `style.shell` names the command line to run (`shlex.split`, so
    `"bash -l"` works); unset resolves `$SHELL`, falling back to `/bin/sh`.
    `style.font_family`/`font_size` pick the face and cell size, the same
    fields `CodeEditor` reads. `text:`/`value:` are unused -- there is no
    buffer to bind, only a live process.
    """

    PAD_X: Final = 4.0
    PAD_Y: Final = 4.0
    #: Not sourced -- there is no M3 page for this widget at all -- the
    #: classic default grid every terminal emulator without an explicit
    #: size falls back to.
    DEFAULT_COLS: Final = 80
    DEFAULT_ROWS: Final = 24
    CURSOR_BLINK_PERIOD: Final = 1.0
    #: How long a candidate (cols, rows) must sit unchanged before an
    #: already-live grid actually reflows to it -- the same trade
    #: `Engine._pin_surface` makes for the swapchain (ARCHITECTURE.md
    #: 5.8.1), applied here instead. Wall-clock, not a frame count:
    #: `perform_layout` only runs when something actually re-lays-out,
    #: which a static (non-resizing) window may never do again after this
    #: fires, so the countdown cannot depend on layout being called again.
    #: See `perform_layout`/`_maybe_apply_pending_grid`.
    GRID_SETTLE_SECONDS: Final = 0.1
    CAPTURES_TAB = True
    CURSOR = "text"

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)
        self._session: _PtySession | None = None
        self._board: Any = None
        self._cols = self.DEFAULT_COLS
        self._rows = self.DEFAULT_ROWS
        #: The debounced target and when it was last (re)armed -- see
        #: `perform_layout`/`_maybe_apply_pending_grid`.
        self._pending_grid: tuple[int, int] | None = None
        self._pending_grid_since = 0.0
        #: Whether this element has ever completed one grid sizing. Also
        #: gates the PTY spawn itself -- see `_ensure_started` and the
        #: module docstring on why the shell must never be spawned at
        #: `DEFAULT_COLS`/`DEFAULT_ROWS` and corrected afterward.
        self._grid_settled_once = False

    # ------------------------------------------------------------- lifecycle

    @override
    def set_ticker(self, ticker: Any) -> None:
        super().set_ticker(ticker)
        self._ensure_started()

    @override
    def dispose(self) -> None:
        if self._session is not None:
            self._session.stop()
            self._session = None
        super().dispose()

    def _command(self) -> str:
        shell = self.style.shell
        if shell:
            return shell
        return os.environ.get("SHELL") or "/bin/sh"

    def _ensure_started(self) -> None:
        """Spawn the shell, but only once BOTH a ticker exists (`App`-managed,
        not a bare `build_element(...).layout(...)`) AND the first real
        `perform_layout` has already set `self._cols`/`self._rows` to the
        widget's actual target grid -- see the module docstring on why
        spawning at a placeholder size and correcting it after the shell has
        already drawn a prompt is a real, confirmed corruption bug, not a
        cosmetic one. Called from both `set_ticker()` and `perform_layout()`,
        harmlessly, since either one may run first.
        """
        if (
            self._session is not None
            or self._ticker is None
            or not self._grid_settled_once
            or not (_BITTTY_AVAILABLE and _PTY_AVAILABLE)
        ):
            return
        board = Board(command=self._command(), width=self._cols, height=self._rows)
        self._board = board
        session = _PtySession(self._command())
        self._session = session
        # Wire reply-writing (DSR etc.) back to the real pty -- see
        # `_BitttyConnection`. This never calls `Board.start_process()`, so
        # `bittty`'s own PTY spawning/reading is never used.
        board.pty = _BitttyConnection(session)
        session.start((self._cols, self._rows), self._on_output)

    def _on_output(self) -> None:
        """The PTY wake callback -- may run via `call_soon_threadsafe` from
        the reader thread, so it must do nothing beyond what `_drain_pty`
        already does safely on the engine thread."""
        self._drain_pty()
        self.mark_needs_paint()

    def _drain_pty(self) -> None:
        if self._session is None or self._board is None:
            return
        data = self._session.drain()
        if data:
            self._board.feed_host_data(data)

    def _feed(self, data: bytes) -> None:
        """Feed bytes directly into the VT parser, bypassing any real PTY.

        The seam a test uses to exercise rendering without a real subprocess
        -- see `tests/test_terminal.py`.
        """
        if self._board is not None:
            self._board.feed_host_data(data)

    # ---------------------------------------------------------------- layout

    def _font_request(self) -> FontRequest:
        """`style.font_family` wins if set; otherwise this loads (idempotent
        past the first call -- `FontDB.load` is a dict lookup once a path has
        been loaded) and requests the bundled `Hack Nerd Font Mono`.

        Found live, 2026-09-08: defaulting to `"Roboto"` (proportional) here
        instead of a real monospace face left every glyph run measured
        against an `"M"`-based cell width it did not actually match --
        `"hello"` shaped ~2.5 cell-widths narrower than the grid assumed, so
        the cursor visibly detached from typed text after a few keystrokes.
        See `assets/fonts/README.md`'s "Monospace" section.
        """
        family = self.style.font_family
        if not family:
            self.text_engine.db.load(MONOSPACE_FONT)
            family = "Hack Nerd Font Mono"
        return FontRequest(family=family, weight=self.style.font_weight)

    def _cell_size(self) -> Size:
        style = self.style
        request = self._font_request()
        one = self.text_engine.measure(
            "M", px=style.font_size, request=request, line_height=style.line_height
        )
        two = self.text_engine.measure("MM", px=style.font_size, request=request)
        # A real monospace face reports every glyph at this same advance;
        # "M" is a conventional reference character for a fallback that is
        # not one. See the module docstring on grid alignment.
        width = two.width - one.width
        return Size(width if width > 0 else one.width, one.height)

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        """Sizing is exact every frame; reflowing an already-live grid is not.

        `board.resize()` reflows `bittty`'s video memory, which changes
        exactly which characters land in which row -- so the very next
        paint's per-run `text_engine.layout()` calls see brand-new text the
        shape cache has never seen, forcing a full re-shape of the whole
        visible grid. Applying that on every (cols, rows) change during a
        live resize drag means doing it roughly once per cell of width
        crossed, which measured 8-22ms per occurrence against this widget's
        ordinary ~2ms paint -- a real, confirmed stutter (see the 2026-09
        resize investigation). `Engine._pin_surface` already accepts the
        identical trade for the swapchain: stay coarse while the drag is in
        flight, catch up once it stops.

        Debouncing only kicks in once a grid has already been sized once --
        the very first sizing applies immediately, since there is no prior
        content to keep stable against and nothing else would ever advance
        a deferred target for a window that never resizes again. That first
        sizing is also the moment the shell actually spawns (`_ensure_started`,
        called below) -- **not** `set_ticker()`, and deliberately not at
        `DEFAULT_COLS`/`DEFAULT_ROWS` either. Found live: spawning at that
        placeholder size and correcting it once the real size is known,
        which is what this widget used to do, reliably corrupted the
        prompt -- many shells (zsh-syntax-highlighting among them) redraw
        badly when resized *after* they have already drawn a full prompt at
        the old width, leaving stray wrapped remnants and a spurious "%"
        line. Reproduced with pySilver's own code not even involved (bare
        `pexpect`+`bittty`: spawn at 80 columns, wait for the prompt to
        finish drawing, resize to the real width -- corrupted every time;
        spawning directly at the real width from the start, or resizing
        before the shell finishes its first draw, was clean every time).
        See `_maybe_apply_pending_grid` for why the *later* debounce
        countdown lives there and not here. The returned `size` is never
        debounced; only the reflow of an already-settled grid is, so
        surrounding layout stays exact.
        """
        outer = self.sized(constraints, self.style)
        cell = self._cell_size()
        width = (
            outer.max_width
            if outer.has_bounded_width
            else self.DEFAULT_COLS * cell.width + 2 * self.PAD_X
        )
        height = (
            outer.max_height
            if outer.has_bounded_height
            else self.DEFAULT_ROWS * cell.height + 2 * self.PAD_Y
        )
        size = outer.constrain(Size(width, height))
        cols = max(1, int((size.width - 2 * self.PAD_X) / cell.width))
        rows = max(1, int((size.height - 2 * self.PAD_Y) / cell.height))
        target = (cols, rows)
        if not self._grid_settled_once:
            self._cols, self._rows = target
            self._grid_settled_once = True
            self._pending_grid = None
            self._ensure_started()
        elif target == (self._cols, self._rows):
            self._pending_grid = None
        elif target != self._pending_grid:
            self._pending_grid = target
            self._pending_grid_since = time.monotonic()
        return size

    def _apply_grid(self, target: tuple[int, int]) -> None:
        cols, rows = target
        self._cols, self._rows = cols, rows
        if self._board is not None:
            self._board.resize(cols, rows)
        if self._session is not None:
            self._session.resize(cols, rows)
        self._pending_grid = None
        self._grid_settled_once = True

    def _maybe_apply_pending_grid(self) -> None:
        """Catch up a deferred reflow once it has sat still long enough.

        Checked from `paint_self`, not `perform_layout`: `perform_layout`
        only runs when something actually re-lays-out, which is not
        guaranteed to happen again once a drag stops. `paint_self` is --
        while a session is alive, the `terminal_poll` animation below
        guarantees a repaint roughly twice a second forever, which is what
        lets a deferred reflow catch up even if the window is never resized
        again after the drag that deferred it.
        """
        if self._pending_grid is None:
            return
        if time.monotonic() - self._pending_grid_since < self.GRID_SETTLE_SECONDS:
            return
        self._apply_grid(self._pending_grid)

    # ----------------------------------------------------------------- paint

    @override
    def paint_self(self, ctx: PaintContext, absolute: Offset) -> None:
        self._maybe_apply_pending_grid()
        self._drain_pty()
        if self.size.is_empty:
            return
        style = self.style
        dpr = ctx.pixel_ratio
        ctx.display_list.add_box(
            absolute.x * dpr,
            absolute.y * dpr,
            self.size.width * dpr,
            self.size.height * dpr,
            token=ctx.palette.index(style.background) if style.background else NO_TOKEN,
            color=(1.0, 1.0, 1.0, 1.0) if style.background else _DEFAULT_BG,
            radii=tuple(r * dpr for r in self.effective_radii),  # type: ignore[arg-type]
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        if self._board is None:
            self._paint_unavailable(ctx, absolute)
            return

        cell = self._cell_size()
        origin = Offset(absolute.x + self.PAD_X, absolute.y + self.PAD_Y)
        self._paint_rows(ctx, origin, cell)
        if self._session is not None and self._session.alive:
            self._paint_cursor(ctx, origin, cell)
            # Keeps a repaint scheduled roughly twice a second for as long as
            # a session is alive, focused or not -- see the module docstring
            # on why output must not depend on an async wake succeeding.
            self.animated(
                "terminal_poll",
                1.0,
                duration=self.CURSOR_BLINK_PERIOD,
                curve="linear",
                repeat=True,
            )
        else:
            poll = self.animation("terminal_poll")
            if poll is not None:
                self.ticker.discard(poll)

    def _paint_unavailable(self, ctx: PaintContext, absolute: Offset) -> None:
        message = (
            "bittty/pexpect not installed (pysilver[terminal])"
            if not (_BITTTY_AVAILABLE and _PTY_AVAILABLE)
            else "Terminal is not implemented on this platform"
        )
        self.text_engine.emit(
            ctx.display_list,
            self.text_engine.layout(message, px=self.style.font_size),
            x=absolute.x + self.PAD_X,
            y=absolute.y + self.PAD_Y,
            pixel_ratio=ctx.pixel_ratio,
            token=ctx.palette.index("error"),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )

    def _paint_rows(self, ctx: PaintContext, origin: Offset, cell: Size) -> None:
        page = self._board.blitter.current_page
        dpr = ctx.pixel_ratio
        request = self._font_request()
        for row in range(self._rows):
            y = origin.y + row * cell.height
            col = 0
            while col < self._cols:
                start = col
                first_style, first_char = page.get_cell(col, row)
                fg_color, bg_color = first_style.fg, first_style.bg
                if first_style.reverse:
                    fg_color, bg_color = bg_color, fg_color
                text_chars: list[str] = []
                col += 1
                if first_char:
                    text_chars.append(first_char)
                while col < self._cols:
                    ch_style, ch_char = page.get_cell(col, row)
                    ch_fg, ch_bg = ch_style.fg, ch_style.bg
                    if ch_style.reverse:
                        ch_fg, ch_bg = ch_bg, ch_fg
                    if ch_fg != fg_color or ch_bg != bg_color:
                        break
                    if ch_char:
                        text_chars.append(ch_char)
                    col += 1
                width_cols = col - start
                bg = _cell_color(bg_color, _DEFAULT_BG)
                if bg != _DEFAULT_BG:
                    ctx.display_list.add_box(
                        (origin.x + start * cell.width) * dpr,
                        y * dpr,
                        width_cols * cell.width * dpr,
                        cell.height * dpr,
                        color=bg,
                        clip=ctx.clip,
                        clip_radii=ctx.clip_radii,
                    )
                text = "".join(text_chars)
                if text.strip():
                    fg = _cell_color(fg_color, _DEFAULT_FG)
                    paragraph = self.text_engine.layout(
                        text, px=self.style.font_size, request=request
                    )
                    self.text_engine.emit(
                        ctx.display_list,
                        paragraph,
                        x=origin.x + start * cell.width,
                        y=y,
                        pixel_ratio=dpr,
                        color=fg,
                        clip=ctx.clip,
                        clip_radii=ctx.clip_radii,
                    )

    def _paint_cursor(self, ctx: PaintContext, origin: Offset, cell: Size) -> None:
        board = self._board
        if not board.modes.cursor_visible:
            return
        if not self.state.focused:
            return
        phase = self.animated(
            "cursor_blink", 1.0, duration=self.CURSOR_BLINK_PERIOD, curve="linear", repeat=True
        )
        if not self.ticker.reduce_motion and phase >= 0.5:
            return
        dpr = ctx.pixel_ratio
        x = origin.x + board.cursor.x * cell.width
        y = origin.y + board.cursor.y * cell.height
        ctx.display_list.add_box(
            x * dpr,
            y * dpr,
            cell.width * dpr,
            cell.height * dpr,
            color=_ANSI_COLORS["brightwhite"],
            opacity=0.5,
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )

    # ------------------------------------------------------------- pointer

    def on_wheel(self, event: Any) -> None:
        """No-op: `bittty` keeps no scrollback buffer to page through (see
        the module docstring) -- the event is left to propagate rather than
        swallowed, so a Terminal sitting inside a `ScrollView` at least lets
        the page scroll instead of doing nothing at all."""
        return

    def on_focus(self, event: Any) -> None:
        self.mark_needs_paint()

    def on_blur(self, event: Any) -> None:
        self.mark_needs_paint()

    # -------------------------------------------------------------- keyboard

    def write_input(self, text: str) -> None:
        """Send *text* to the shell as if it had been typed. Public: an
        application composing a terminal into a larger workflow (running a
        prepared command, say) has no other way to reach the PTY."""
        if self._session is not None:
            self._session.write(text.encode("utf-8", "ignore"))

    def on_text(self, event: Any) -> None:
        if self.effective_disabled or self._session is None:
            return
        text = str(getattr(event, "text", ""))
        if not text or text < " ":
            return
        self.write_input(text)
        event.stop_propagation()

    def on_key_down(self, event: Any) -> None:
        if self.effective_disabled or self._session is None:
            return
        key = str(getattr(event, "key", "")).lower()
        mods = modifiers_of(event)
        if key == "tab":
            self._session.write(b"\x1b[Z" if "shift" in mods else b"\t")
            event.stop_propagation()
            return
        if is_accelerator(mods) and key == "v":
            pasted = clipboard.get_text()
            if pasted:
                self.write_input(pasted)
            event.stop_propagation()
            return
        if "ctrl" in mods and len(key) == 1 and key.isalpha():
            self._session.write(bytes([ord(key.upper()) - 64]))
            event.stop_propagation()
            return
        data = _KEY_BYTES.get(key)
        if data is not None:
            self._session.write(data)
            event.stop_propagation()
