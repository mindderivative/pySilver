"""Fab demo's logic: a click counter, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class FabDemo(ViewModel):
    """State and commands for `Fab_View.yaml`."""

    def __init__(self) -> None:
        self.clicks = Signal(0, name="clicks")

        self.view_source = (Path(__file__).parent / "Fab_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def press(self, event: Any) -> None:
        self.clicks.update(lambda n: n + 1)
