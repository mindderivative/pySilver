"""Switch demo's logic: one toggle, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class SwitchDemo(ViewModel):
    """State and commands for `Switch_View.yaml`."""

    def __init__(self) -> None:
        self.on = Signal(False, name="on")

        self.view_source = (Path(__file__).parent / "Switch_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def toggle(self, event: Any) -> None:
        self.on.update(lambda v: not v)
