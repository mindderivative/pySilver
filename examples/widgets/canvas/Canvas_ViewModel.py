"""Canvas demo's logic: the on_paint drawing handler, and the two source
panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import ViewModel


class CanvasDemo(ViewModel):
    """State and commands for `Canvas_View.yaml`."""

    def __init__(self) -> None:
        self.view_source = (Path(__file__).parent / "Canvas_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def draw(self, canvas: Any) -> None:
        """`on_paint` is called with one argument, a `CanvasContext` -- no
        `Event` wraps it, since there is nothing an application handler
        could do with one. This sweeps through the primitive vocabulary
        once: a bordered rounded rect, a line, a circle, an arc, a
        polygon, text."""
        canvas.rect(12, 12, 120, 60, color="primary_container", corner_radius=12)
        canvas.rect(
            12,
            12,
            120,
            60,
            color=(0, 0, 0, 0),
            corner_radius=12,
            border_width=2,
            border_color="primary",
        )
        canvas.line(150, 20, 260, 64, thickness=3, color="secondary")
        canvas.circle(300, 42, 26, color="tertiary")
        canvas.arc(370, 42, 26, thickness=6, start=0.0, sweep=4.5, color="error")
        canvas.polygon(420, 16, 52, 52, sides=6, color="on_surface_variant")
        canvas.text(12, 90, "CanvasContext: rect, line, circle, arc, polygon, text", font_size=13)
