"""Popover demo's logic: open/close state, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class PopoverDemo(ViewModel):
    """State and commands for `Popover_View.yaml`."""

    def __init__(self) -> None:
        self.pop_open = Signal(False, name="pop_open")

        self.view_source = (Path(__file__).parent / "Popover_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def open_popover(self, event: Any) -> None:
        self.pop_open.set(True)

    def close_popover(self, event: Any) -> None:
        self.pop_open.set(False)
