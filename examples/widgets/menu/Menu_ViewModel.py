"""Menu demo's logic: open/close state and which item was picked, plus the
two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class MenuDemo(ViewModel):
    """State and commands for `Menu_View.yaml`."""

    def __init__(self) -> None:
        self.menu_open = Signal(False, name="menu_open")
        self.last_action = Signal("none yet", name="last_action")

        self.view_source = (Path(__file__).parent / "Menu_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def open_menu(self, event: Any) -> None:
        self.menu_open.set(True)

    def close_menu(self, event: Any) -> None:
        self.menu_open.set(False)

    def pick(self, event: Any) -> None:
        self.last_action.set(event.target.name)
        self.menu_open.set(False)
