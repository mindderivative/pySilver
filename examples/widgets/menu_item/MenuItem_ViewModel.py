"""Menu Item demo's logic: a real File/Edit/View/Help menu bar, one submenu,
and a last-clicked readout, plus the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class MenuItemDemo(ViewModel):
    """State and commands for `MenuItem_View.yaml`."""

    def __init__(self) -> None:
        #: Which top-level menu is open: "", "file", "edit", "view", or "help".
        self.open_menu = Signal("", name="open_menu")
        #: The View menu's own submenu (Panels), independent of which top
        #: menu is open so it can be closed without touching the parent.
        self.panels_open = Signal(False, name="panels_open")
        self.last_clicked = Signal("none yet", name="last_clicked")

        self.view_source = (Path(__file__).parent / "MenuItem_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def toggle_menu(self, event: Any) -> None:
        """A menu-bar button: opens its own menu, or closes it if already
        open -- the same click-to-toggle a real menu bar uses."""
        name = event.target.name
        self.open_menu.set("" if self.open_menu.get() == name else name)
        self.panels_open.set(False)

    def close_menu(self, event: Any) -> None:
        """A menu's own `on_dismiss` -- click-outside or Escape."""
        self.open_menu.set("")
        self.panels_open.set(False)

    def open_panels(self, event: Any) -> None:
        self.panels_open.set(True)

    def close_panels(self, event: Any) -> None:
        self.panels_open.set(False)

    def pick(self, event: Any) -> None:
        """Any real action item: Cut, Save, Zoom In, ... -- shows what was
        received, then closes everything, matching a real menu bar."""
        self.last_clicked.set(event.target.text)
        self.open_menu.set("")
        self.panels_open.set(False)
