"""Spin Box demo's logic: one bound quantity, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class SpinBoxDemo(ViewModel):
    """State and commands for `SpinBox_View.yaml`."""

    def __init__(self) -> None:
        self.qty = Signal("3", name="qty")

        self.view_source = (Path(__file__).parent / "SpinBox_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def change_qty(self, event: Any) -> None:
        self.qty.set(event.value)
