"""Dock Split demo's logic: one bound split ratio, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class DockSplitDemo(ViewModel):
    """State and commands for `DockSplit_View.yaml`."""

    def __init__(self) -> None:
        self.ratio = Signal("0.5", name="ratio")

        self.view_source = (Path(__file__).parent / "DockSplit_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def change_ratio(self, event: Any) -> None:
        self.ratio.set(event.value)
