"""Tooltip demo's logic: open/close state, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class TooltipDemo(ViewModel):
    """State and commands for `Tooltip_View.yaml`."""

    def __init__(self) -> None:
        self.tip_open = Signal(False, name="tip_open")

        self.view_source = (Path(__file__).parent / "Tooltip_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def show(self, event: Any) -> None:
        self.tip_open.set(True)

    def close(self, event: Any) -> None:
        self.tip_open.set(False)
