"""Split Button demo's logic: the two independent click regions, and the
two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class SplitButtonDemo(ViewModel):
    """State and commands for `SplitButton_View.yaml`."""

    def __init__(self) -> None:
        self.saves = Signal(0, name="saves")
        self.menu_open = Signal(False, name="menu_open")

        self.view_source = (Path(__file__).parent / "SplitButton_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def save(self, event: Any) -> None:
        self.saves.update(lambda n: n + 1)

    def open_menu(self, event: Any) -> None:
        self.menu_open.set(True)

    def close_menu(self, event: Any) -> None:
        self.menu_open.set(False)
