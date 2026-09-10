"""Text Field demo's logic: one bound value, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class TextFieldDemo(ViewModel):
    """State and commands for `TextField_View.yaml`."""

    def __init__(self) -> None:
        self.name = Signal("Ada Lovelace", name="name")
        self.bidi_text = Signal("Hello مرحبا שלום world", name="bidi_text")

        self.view_source = (Path(__file__).parent / "TextField_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def change_name(self, event: Any) -> None:
        self.name.set(event.value)

    def change_bidi_text(self, event: Any) -> None:
        self.bidi_text.set(event.value)
