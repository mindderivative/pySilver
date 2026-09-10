"""Dock Group demo's logic: one active panel, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class DockGroupDemo(ViewModel):
    """State and commands for `DockGroup_View.yaml`."""

    def __init__(self) -> None:
        self.active = Signal("files", name="active")

        self.view_source = (Path(__file__).parent / "DockGroup_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def select_panel(self, event: Any) -> None:
        self.active.set(event.value)
