"""Tree Item demo's logic: one selection, one node's real expand/collapse
state, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class TreeItemDemo(ViewModel):
    """State and commands for `TreeItem_View.yaml`."""

    def __init__(self) -> None:
        self.selected = Signal("main", name="selected")
        #: `src`'s own expand state -- a real signal, not a static literal,
        #: so clicking it actually demonstrates the collapse/expand this
        #: widget exists for.
        self.src_expanded = Signal(True, name="src_expanded")

        self.view_source = (Path(__file__).parent / "TreeItem_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def select(self, event: Any) -> None:
        self.selected.set(event.target.name)

    def toggle_src(self, event: Any) -> None:
        """`src` is a branch, so its click both selects it and toggles its
        expand state -- the same single-click-does-both convention most
        desktop tree views use for a folder row."""
        self.selected.set(event.target.name)
        self.src_expanded.update(lambda expanded: not expanded)
