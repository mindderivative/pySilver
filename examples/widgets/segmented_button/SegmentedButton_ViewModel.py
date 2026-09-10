"""Segmented Button demo's logic: single- and multi-select state, and the
two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class SegmentedButtonDemo(ViewModel):
    """State and commands for `SegmentedButton_View.yaml`."""

    def __init__(self) -> None:
        self.view = Signal("week", name="view")
        self.days = Signal("tue,thu", name="days")

        self.view_source = (Path(__file__).parent / "SegmentedButton_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def select_view(self, event: Any) -> None:
        self.view.set(event.target.name)

    def toggle_day(self, event: Any) -> None:
        name = event.target.name
        current = {d for d in self.days.peek().split(",") if d}
        current.symmetric_difference_update({name})
        self.days.set(",".join(sorted(current)))
