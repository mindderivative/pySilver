"""Tree View demo's logic: one selection at any depth, two branches' real
expand/collapse state, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class TreeViewDemo(ViewModel):
    """State and commands for `TreeView_View.yaml`."""

    def __init__(self) -> None:
        self.selected = Signal("main", name="selected")
        #: Each branch's own expand state -- real signals, not static
        #: literals, so clicking one actually demonstrates collapse/expand
        #: at more than one depth, not just selection.
        self.src_expanded = Signal(True, name="src_expanded")
        self.widgets_expanded = Signal(True, name="widgets_expanded")

        self.view_source = (Path(__file__).parent / "TreeView_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def select(self, event: Any) -> None:
        self.selected.set(event.target.name)

    def toggle_src(self, event: Any) -> None:
        self.selected.set(event.target.name)
        self.src_expanded.update(lambda expanded: not expanded)

    def toggle_widgets(self, event: Any) -> None:
        self.selected.set(event.target.name)
        self.widgets_expanded.update(lambda expanded: not expanded)
