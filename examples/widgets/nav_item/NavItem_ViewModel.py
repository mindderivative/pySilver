"""Nav Item demo's logic: one selection, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class NavItemDemo(ViewModel):
    """State and commands for `NavItem_View.yaml`."""

    def __init__(self) -> None:
        self.selected = Signal("home", name="selected")

        self.view_source = (Path(__file__).parent / "NavItem_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def select(self, event: Any) -> None:
        self.selected.set(event.target.name)
