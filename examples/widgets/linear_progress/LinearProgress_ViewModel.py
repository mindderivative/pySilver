"""Linear Progress demo's logic: a stepped determinate value, and the two
source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class LinearProgressDemo(ViewModel):
    """State and commands for `LinearProgress_View.yaml`."""

    def __init__(self) -> None:
        self.progress = Signal(0.3, name="progress")
        self.percent = Signal(30, name="percent")

        self.view_source = (Path(__file__).parent / "LinearProgress_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def _step(self, delta: float) -> None:
        value = max(0.0, min(1.0, self.progress.peek() + delta))
        self.progress.set(value)
        self.percent.set(round(value * 100))

    def increase(self, event: Any) -> None:
        self._step(0.1)

    def decrease(self, event: Any) -> None:
        self._step(-0.1)
