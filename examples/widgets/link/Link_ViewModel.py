"""Link demo's logic: nothing to toggle, just the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path

from pysilver import ViewModel


class LinkDemo(ViewModel):
    """State for `Link_View.yaml`. No commands -- this demo has no interaction."""

    def __init__(self) -> None:
        self.view_source = (Path(__file__).parent / "Link_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()
