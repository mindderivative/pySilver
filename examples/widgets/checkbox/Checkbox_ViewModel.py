"""Checkbox demo's logic: one toggle, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class CheckboxDemo(ViewModel):
    """State and commands for `Checkbox_View.yaml`."""

    def __init__(self) -> None:
        self.checked = Signal(False, name="checked")

        self.view_source = (Path(__file__).parent / "Checkbox_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def toggle(self, event: Any) -> None:
        self.checked.update(lambda v: not v)
