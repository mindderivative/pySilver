"""Vertical demo's logic: cycling cross_alignment via self.app.reload(...),
and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pysilver import ViewModel

_ALIGNMENTS = ("start", "end", "center", "stretch")


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


class VerticalDemo(ViewModel):
    """State and commands for `Vertical_View.yaml`.

    `cross_alignment` is a plain `style.*` property, not one of the handful
    of templated fields (`text:`, `value:`, ...), so it cannot be bound to
    a Signal with `{{ }}`. The button instead reloads `Vertical_View.yaml`
    ITSELF -- parsed fresh, never hand-duplicated -- with only the
    `live_demo` node's style patched, via `self.app.reload(...)`, the same
    mechanism hot reload uses. Reconciliation matches by `name:`, so
    everything outside `live_demo` (scroll position included) survives the
    reload untouched.
    """

    def __init__(self) -> None:
        self._alignment_index = 0

        self.view_source = (Path(__file__).parent / "Vertical_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()

    def _view(self) -> dict[str, Any]:
        alignment = _ALIGNMENTS[self._alignment_index]
        doc = yaml.safe_load(self.view_source)
        assert isinstance(doc, dict)
        live_demo = _find(doc, "live_demo")
        assert live_demo is not None
        live_demo["style"]["cross_alignment"] = alignment
        label = _find(doc, "label")
        assert label is not None
        label["text"] = f"cross_alignment: {alignment}"
        return doc

    def cycle_alignment(self, event: Any) -> None:
        self._alignment_index = (self._alignment_index + 1) % len(_ALIGNMENTS)
        self.app.reload(self._view())
