"""Accordion demo's logic: an expand toggle, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class AccordionDemo(ViewModel):
    """State and commands for `Accordion_View.yaml`."""

    def __init__(self) -> None:
        self.open = Signal(True, name="open")

        self.view_source = (Path(__file__).parent / "Accordion_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def toggle(self, event: Any) -> None:
        self.open.update(lambda on: not on)
