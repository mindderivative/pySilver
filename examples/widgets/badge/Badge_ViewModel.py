"""Badge demo's logic: an unread counter, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class BadgeDemo(ViewModel):
    """State and commands for `Badge_View.yaml`."""

    def __init__(self) -> None:
        self.unread = Signal(3, name="unread")

        self.view_source = (Path(__file__).parent / "Badge_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def increment(self, event: Any) -> None:
        self.unread.update(lambda n: n + 1)
