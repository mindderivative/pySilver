"""Tabs demo's logic: six independent selections (primary, secondary,
stacked/leading/trailing icon+label, and badges), and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class TabsDemo(ViewModel):
    """State and commands for `Tabs_View.yaml`."""

    def __init__(self) -> None:
        self.tab = Signal("t0", name="tab")
        self.tab2 = Signal("s0", name="tab2")
        self.tab3 = Signal("i0", name="tab3")
        self.tab4 = Signal("l0", name="tab4")
        self.tab5 = Signal("r0", name="tab5")
        self.tab6 = Signal("b0", name="tab6")
        #: `Inbox`'s badge -- templated like any other `badge:`, to show it
        #: tracks a signal the same way `text:`/`icon:` already do.
        self.inbox_count = Signal("3", name="inbox_count")

        self.view_source = (Path(__file__).parent / "Tabs_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def select_tab(self, event: Any) -> None:
        self.tab.set(event.target.name)

    def select_tab2(self, event: Any) -> None:
        self.tab2.set(event.target.name)

    def select_tab3(self, event: Any) -> None:
        self.tab3.set(event.target.name)

    def select_tab4(self, event: Any) -> None:
        self.tab4.set(event.target.name)

    def select_tab5(self, event: Any) -> None:
        self.tab5.set(event.target.name)

    def select_tab6(self, event: Any) -> None:
        self.tab6.set(event.target.name)
