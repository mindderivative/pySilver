"""Top App Bar demo's logic: nothing to toggle, just the two source panels.

The collapse itself is scroll-linked (see `TopAppBarElement` in
`widgets/navigation.py`) -- no handler is involved.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path

from pysilver import ViewModel


class TopAppBarDemo(ViewModel):
    """State for `TopAppBar_View.yaml`. No commands -- the bar collapses on its own."""

    def __init__(self) -> None:
        self.view_source = (Path(__file__).parent / "TopAppBar_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()
