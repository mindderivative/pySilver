"""Search Bar demo's logic: one bound query, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class SearchBarDemo(ViewModel):
    """State and commands for `SearchBar_View.yaml`."""

    def __init__(self) -> None:
        self.query = Signal("", name="query")

        self.view_source = (Path(__file__).parent / "SearchBar_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def change_query(self, event: Any) -> None:
        self.query.set(event.value)
