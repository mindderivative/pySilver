"""Slider demo's logic: one bound value per size row, and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class SliderDemo(ViewModel):
    """State and commands for `Slider_View.yaml`."""

    def __init__(self) -> None:
        # One Signal per size row -- the live example shows all five sizes
        # at once, so each needs its own independent bound value.
        self.volume_xs = Signal(40, name="volume_xs")
        self.volume_s = Signal(40, name="volume_s")
        self.volume_m = Signal(40, name="volume_m")
        self.volume_l = Signal(40, name="volume_l")
        self.volume_xl = Signal(40, name="volume_xl")

        # One per handle-shape example, same reasoning.
        self.shape_line = Signal(40, name="shape_line")
        self.shape_circle = Signal(40, name="shape_circle")
        self.shape_square = Signal(40, name="shape_square")
        self.shape_hexagon = Signal(40, name="shape_hexagon")
        self.shape_image = Signal(40, name="shape_image")

        self.view_source = (Path(__file__).parent / "Slider_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def change_volume_xs(self, event: Any) -> None:
        self.volume_xs.set(event.value)

    def change_volume_s(self, event: Any) -> None:
        self.volume_s.set(event.value)

    def change_volume_m(self, event: Any) -> None:
        self.volume_m.set(event.value)

    def change_volume_l(self, event: Any) -> None:
        self.volume_l.set(event.value)

    def change_volume_xl(self, event: Any) -> None:
        self.volume_xl.set(event.value)

    def change_shape_line(self, event: Any) -> None:
        self.shape_line.set(event.value)

    def change_shape_circle(self, event: Any) -> None:
        self.shape_circle.set(event.value)

    def change_shape_square(self, event: Any) -> None:
        self.shape_square.set(event.value)

    def change_shape_hexagon(self, event: Any) -> None:
        self.shape_hexagon.set(event.value)

    def change_shape_image(self, event: Any) -> None:
        self.shape_image.set(event.value)
