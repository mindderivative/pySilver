"""Time Picker demo's logic: one bound time, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class TimePickerDemo(ViewModel):
    """State and commands for `TimePicker_View.yaml`."""

    def __init__(self) -> None:
        self.selected = Signal("09:30", name="selected")

        self.view_source = (Path(__file__).parent / "TimePicker_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def change_time(self, event: Any) -> None:
        self.selected.set(event.value)
