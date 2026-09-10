"""Pagination demo's logic: one bound page, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class PaginationDemo(ViewModel):
    """State and commands for `Pagination_View.yaml`."""

    def __init__(self) -> None:
        self.page = Signal("1", name="page")

        self.view_source = (Path(__file__).parent / "Pagination_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def change_page(self, event: Any) -> None:
        self.page.set(event.value)
