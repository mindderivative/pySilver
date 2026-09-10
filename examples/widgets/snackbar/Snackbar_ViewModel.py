"""Snackbar demo's logic: open/close state, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class SnackbarDemo(ViewModel):
    """State and commands for `Snackbar_View.yaml`."""

    def __init__(self) -> None:
        self.bar_open = Signal(False, name="bar_open")
        self.message = Signal("", name="message")
        self.action = Signal("", name="action")

        self.view_source = (Path(__file__).parent / "Snackbar_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def archive(self, event: Any) -> None:
        """Actionable -- never auto-dismisses, per M3's own rule."""
        self.message.set("Email archived")
        self.action.set("Undo")
        self.bar_open.set(True)

    def mark_read(self, event: Any) -> None:
        """No action -- auto-dismisses after `style.auto_dismiss` seconds."""
        self.message.set("Email marked as read")
        self.action.set("")
        self.bar_open.set(True)

    def close(self, event: Any) -> None:
        self.bar_open.set(False)

    def undo(self, event: Any) -> None:
        self.bar_open.set(False)
