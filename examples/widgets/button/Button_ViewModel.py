"""Button demo's logic: a click counter, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class ButtonDemo(ViewModel):
    """State and commands for `Button_View.yaml`."""

    def __init__(self) -> None:
        self.clicks = Signal(0, name="clicks")

        # Read live from disk, not hand-copied, so the two code panels can
        # never drift from what is actually running.
        self.view_source = (Path(__file__).parent / "Button_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def press(self, event: Any) -> None:
        self.clicks.update(lambda n: n + 1)
