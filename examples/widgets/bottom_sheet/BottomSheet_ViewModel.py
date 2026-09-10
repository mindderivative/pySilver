"""Bottom Sheet demo's logic: open/close state, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class BottomSheetDemo(ViewModel):
    """State and commands for `BottomSheet_View.yaml`."""

    def __init__(self) -> None:
        self.sheet_open = Signal(False, name="sheet_open")

        self.view_source = (Path(__file__).parent / "BottomSheet_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def open_sheet(self, event: Any) -> None:
        self.sheet_open.set(True)

    def close_sheet(self, event: Any) -> None:
        self.sheet_open.set(False)
