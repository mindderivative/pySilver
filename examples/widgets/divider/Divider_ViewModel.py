"""Divider demo's logic: nothing to toggle, just the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path

from pysilver import ViewModel


class DividerDemo(ViewModel):
    """State for `Divider_View.yaml`. No commands -- a Divider has no interaction."""

    def __init__(self) -> None:
        self.view_source = (Path(__file__).parent / "Divider_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")
