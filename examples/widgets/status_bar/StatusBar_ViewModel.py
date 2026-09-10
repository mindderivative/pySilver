"""Status Bar demo's logic: nothing to toggle, just the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path

from pysilver import ViewModel


class StatusBarDemo(ViewModel):
    """State for `StatusBar_View.yaml`. No commands -- this demo has no interaction."""

    def __init__(self) -> None:
        self.view_source = (Path(__file__).parent / "StatusBar_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")
