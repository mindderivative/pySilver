"""Date Picker demo's logic: one bound date, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class DatePickerDemo(ViewModel):
    """State and commands for `DatePicker_View.yaml`."""

    def __init__(self) -> None:
        self.selected = Signal("2026-09-04", name="selected")

        self.view_source = (Path(__file__).parent / "DatePicker_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def change_date(self, event: Any) -> None:
        self.selected.set(event.value)
