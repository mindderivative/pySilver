"""The clipboard: the system one where it works, in-process where it does not.

This shipped as an in-process clipboard only, on the stated grounds that "the
only route is the backend's private window handle (`canvas._window`)". **That
was wrong.** GLFW's clipboard functions take the window as a *deprecated*
parameter and accept `None` -- "the window parameter to glfwSetClipboardString
is deprecated" -- so reaching the system clipboard needs no private state at
all, only that GLFW has been initialised. `GlfwClipboard` does exactly that,
and `Engine` installs it when it creates a real window.

**Reading has a constraint worth knowing.** On Wayland a client may only read
the selection while it holds keyboard focus; that is the compositor's security
model and not something a client can work around. In practice this is fine --
a user pressing Ctrl+V is, by definition, focused on the window. But a read
attempted without focus returns nothing, so `Clipboard.get_text` falls back to
whatever this process last copied rather than returning an empty string. The
consequence to know: pasting into a pySilver application always works, and a
system clipboard changed while the window was unfocused is picked up as soon
as focus returns.

Writing needs only a surface and works regardless of focus.

An application can still supply its own backend, which takes precedence over
the built-in one:

    from pysilver.runtime.clipboard import clipboard
    import pyperclip

    class SystemClipboard:
        def set_text(self, text: str) -> bool:
            pyperclip.copy(text)
            return True

        def get_text(self) -> str:
            return pyperclip.paste()

    clipboard.install(SystemClipboard())

Process-global on purpose, unlike the animation ticker: a clipboard genuinely
is one shared thing, so there is nothing for an App to own.
"""

from __future__ import annotations

from typing import Any, Protocol

__all__ = ["Clipboard", "ClipboardBackend", "GlfwClipboard", "clipboard"]


class ClipboardBackend(Protocol):
    """What an application supplies to reach the real system clipboard."""

    def set_text(self, text: str) -> bool: ...
    def get_text(self) -> str: ...


class Clipboard:
    """In-process clipboard, with a seam for a real one."""

    __slots__ = ("_backend", "_text")

    def __init__(self) -> None:
        self._text = ""
        self._backend: Any = None

    def install(self, backend: ClipboardBackend | None) -> None:
        """Route through a real clipboard. `None` returns to in-process only."""
        self._backend = backend

    @property
    def system_backed(self) -> bool:
        return self._backend is not None

    def set_text(self, text: str) -> bool:
        """Copy. Returns whether it reached a system clipboard.

        The in-process copy happens either way, so a failed system write still
        leaves the application able to paste into itself.
        """
        self._text = text
        if self._backend is None:
            return False
        try:
            return bool(self._backend.set_text(text))
        except Exception:  # pragma: no cover - a backend must never break a frame
            return False

    def get_text(self) -> str:
        """Paste. Falls back to this process's own copy.

        An empty result from the backend is treated as a miss rather than as an
        empty clipboard, because on Wayland that is what a read without
        keyboard focus looks like. Preferring the in-process text there keeps
        paste working inside the application; the cost is that genuinely
        clearing the system clipboard elsewhere does not clear this one.
        """
        if self._backend is not None:
            try:
                got = str(self._backend.get_text())
            except Exception:  # pragma: no cover - a backend must never break a frame
                return self._text
            if got:
                return got
        return self._text


class GlfwClipboard:
    """The system clipboard, through GLFW.

    No private state: the window parameter these functions take is deprecated
    and `None` is accepted, so this needs only that GLFW is initialised -- which
    it is from the moment a window exists. Every failure degrades to the
    in-process clipboard rather than raising.
    """

    __slots__ = ()

    @staticmethod
    def _quiet() -> Any:
        """Silence the binding's own warning for a call whose error we read.

        `pyglfw` reports failures by `warnings.warn`, so a clipboard call made
        before a window exists prints a GLFWError traceback fragment at the
        user. The error code is checked directly below, so the warning is pure
        noise -- and only this call is silenced, not the process.
        """
        import warnings

        import glfw

        return warnings.catch_warnings(action="ignore", category=glfw.GLFWError)

    def set_text(self, text: str) -> bool:
        try:
            import glfw

            # The stubs type the window as a pointer, but GLFW deprecated the
            # parameter and accepts NULL -- passing a window raises a
            # DeprecationWarning. Ignored rather than fed a private handle.
            with self._quiet():
                # Clear first. `get_error` reports the *last* error and clears
                # it, so without this a stale one -- an earlier unfocused read,
                # typically -- makes a perfectly good write report failure.
                # That happened, and a wrong answer either way is worse than
                # no answer.
                glfw.get_error()
                glfw.set_clipboard_string(None, text)  # type: ignore[arg-type]
                # The binding *warns* on failure rather than raising, so a
                # try/except reports success for a write that did nothing at
                # all -- before a window exists, say. Ask GLFW directly.
                code, _ = glfw.get_error()
        except Exception:
            return False
        return code == glfw.NO_ERROR

    def get_text(self) -> str:
        try:
            import glfw

            with self._quiet():
                glfw.get_error()
                got: Any = glfw.get_clipboard_string(None)  # type: ignore[arg-type]
                glfw.get_error()  # Clear it, so a miss cannot fail a later set.
        except Exception:
            return ""
        # The stubs promise `str`; the runtime returns None when there is no
        # readable selection -- which on Wayland is what a read without
        # keyboard focus looks like -- and bytes on some builds. Typed as Any
        # above so this stays checkable rather than being declared unreachable.
        if got is None:
            return ""
        return got.decode() if isinstance(got, bytes) else str(got)


#: The process-wide clipboard.
clipboard = Clipboard()
