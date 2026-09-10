"""Window example's logic: a created window with a ScrollView panel.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path

from pysilver import Signal, ViewModel


class WindowDemo(ViewModel):
    """State and commands for `Accordion_View.yaml`."""

    def __init__(self) -> None:
        self.open = Signal(True, name="open")

        self.view_source = (Path(__file__).parent / "Window_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")
