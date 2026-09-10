"""Dialog demo's logic: open/close state, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class DialogDemo(ViewModel):
    """State and commands for `Dialog_View.yaml`."""

    def __init__(self) -> None:
        self.dialog_open = Signal(False, name="dialog_open")
        self.deleted = Signal(0, name="deleted")

        self.view_source = (Path(__file__).parent / "Dialog_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def open_dialog(self, event: Any) -> None:
        self.dialog_open.set(True)

    def close_dialog(self, event: Any) -> None:
        """Cancel, click-outside, or Escape -- backing out with nothing done."""
        self.dialog_open.set(False)

    def confirm_delete(self, event: Any) -> None:
        """The actual action the dialog exists to confirm."""
        self.dialog_open.set(False)
        self.deleted.update(lambda n: n + 1)
