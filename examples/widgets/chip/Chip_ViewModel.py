"""Chip demo's logic: the filter chip's toggle, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class ChipDemo(ViewModel):
    """State and commands for `Chip_View.yaml`."""

    def __init__(self) -> None:
        self.filter_on = Signal(False, name="filter_on")

        self.view_source = (Path(__file__).parent / "Chip_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def toggle_filter(self, event: Any) -> None:
        self.filter_on.update(lambda v: not v)
