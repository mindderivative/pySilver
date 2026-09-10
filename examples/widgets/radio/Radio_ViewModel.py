"""Radio demo's logic: a single shared choice, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class RadioDemo(ViewModel):
    """State and commands for `Radio_View.yaml`."""

    def __init__(self) -> None:
        self.choice = Signal("a", name="choice")

        self.view_source = (Path(__file__).parent / "Radio_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def select(self, event: Any) -> None:
        self.choice.set(event.target.name.removeprefix("radio_"))
