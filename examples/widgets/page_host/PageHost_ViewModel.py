"""Page Host demo's logic: which page is active, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class PageHostDemo(ViewModel):
    """State and commands for `PageHost_View.yaml`."""

    def __init__(self) -> None:
        self.page = Signal("home", name="page")

        self.view_source = (Path(__file__).parent / "PageHost_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def go_home(self, event: Any) -> None:
        self.page.set("home")

    def go_profile(self, event: Any) -> None:
        self.page.set("profile")

    def go_settings(self, event: Any) -> None:
        self.page.set("settings")
