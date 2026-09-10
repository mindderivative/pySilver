"""Container demo's logic: cycling padding and corner radius via
self.app.reload(...), and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pysilver import ViewModel

_PADDING_STEPS = (8, 24, 48)
_CORNER_STEPS = (0, 12, 999)


def _find(node: Any, name: str) -> dict[str, Any] | None:
    """The first node named *name* in a parsed view document, depth-first."""
    if isinstance(node, dict):
        if node.get("name") == name:
            return node
        for child in node.get("children", ()):
            found = _find(child, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find(item, name)
            if found is not None:
                return found
    return None


class ContainerDemo(ViewModel):
    """State and commands for `Container_View.yaml`.

    `padding` and `corner_radius` are plain `style.*` properties, not one
    of the handful of templated fields (`text:`, `value:`, ...), so they
    cannot be bound to a Signal with `{{ }}`. Each button instead reloads
    `Container_View.yaml` ITSELF -- parsed fresh, never hand-duplicated --
    with only the `live_demo` node's style patched, via
    `self.app.reload(...)`, the same mechanism hot reload uses.
    Reconciliation matches by `name:`, so everything outside `live_demo`
    (scroll position included) survives the reload untouched.
    """

    def __init__(self) -> None:
        self._padding_index = 0
        self._corner_index = 0

        self.view_source = (Path(__file__).parent / "Container_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def _view(self) -> dict[str, Any]:
        padding = _PADDING_STEPS[self._padding_index]
        corner = _CORNER_STEPS[self._corner_index]
        doc = yaml.safe_load(self.view_source)
        assert isinstance(doc, dict)
        live_demo = _find(doc, "live_demo")
        assert live_demo is not None
        live_demo["style"]["padding"] = padding
        live_demo["style"]["corner_radius"] = corner
        live_demo["children"][0]["text"] = f"padding: {padding}, corner_radius: {corner}"
        return doc

    def cycle_padding(self, event: Any) -> None:
        self._padding_index = (self._padding_index + 1) % len(_PADDING_STEPS)
        self.app.reload(self._view())

    def cycle_corner(self, event: Any) -> None:
        self._corner_index = (self._corner_index + 1) % len(_CORNER_STEPS)
        self.app.reload(self._view())
