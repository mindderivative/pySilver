"""Stack demo's logic: cycling the front child's align_x/align_y via
self.app.reload(...), and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pysilver import ViewModel

_CORNERS = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.5, 0.5))


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


class StackDemo(ViewModel):
    """State and commands for `Stack_View.yaml`.

    `align_x`/`align_y` are plain `style.*` properties, not one of the
    handful of templated fields (`text:`, `value:`, ...), so they cannot be
    bound to a Signal with `{{ }}`. The button instead reloads
    `Stack_View.yaml` ITSELF -- parsed fresh, never hand-duplicated -- with
    only the front square's style patched, via `self.app.reload(...)`, the
    same mechanism hot reload uses. Reconciliation matches by `name:`, so
    everything outside `live_demo` (scroll position included) survives the
    reload untouched.
    """

    def __init__(self) -> None:
        self._corner_index = 0

        self.view_source = (Path(__file__).parent / "Stack_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def _view(self) -> dict[str, Any]:
        align_x, align_y = _CORNERS[self._corner_index]
        doc = yaml.safe_load(self.view_source)
        assert isinstance(doc, dict)
        live_demo = _find(doc, "live_demo")
        assert live_demo is not None
        # The front square is `live_demo`'s second child in the YAML's own
        # declared order -- the first is the fixed back panel.
        front = live_demo["children"][1]
        front["style"]["align_x"] = align_x
        front["style"]["align_y"] = align_y
        label = _find(doc, "label")
        assert label is not None
        label["text"] = f"front square: align_x={align_x}, align_y={align_y}"
        return doc

    def cycle_alignment(self, event: Any) -> None:
        self._corner_index = (self._corner_index + 1) % len(_CORNERS)
        self.app.reload(self._view())
