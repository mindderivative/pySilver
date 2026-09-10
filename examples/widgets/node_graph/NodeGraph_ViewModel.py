"""Node Graph demo's logic: nothing to toggle, just the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path

from pysilver import ViewModel


class NodeGraphDemo(ViewModel):
    """State for `NodeGraph_View.yaml`. No commands -- panning and dragging
    are handled internally."""

    def __init__(self) -> None:
        self.view_source = (Path(__file__).parent / "NodeGraph_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")
