"""Spacer demo's logic: cycling the two spacers' flex ratio via
self.app.reload(...), and the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pysilver import ViewModel

_RATIOS = ((1, 1), (3, 1), (1, 3))


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


class SpacerDemo(ViewModel):
    """State and commands for `Spacer_View.yaml`.

    The flex weight is part of `style.width` (`flex:N`), a plain style
    property rather than one of the handful of templated fields (`text:`,
    `value:`, ...), so it cannot be bound to a Signal with `{{ }}`. The
    button instead reloads `Spacer_View.yaml` ITSELF -- parsed fresh, never
    hand-duplicated -- with only the two spacers' style patched, via
    `self.app.reload(...)`, the same mechanism hot reload uses.
    Reconciliation matches by `name:`, so everything outside `live_demo`
    (scroll position included) survives the reload untouched.
    """

    def __init__(self) -> None:
        self._ratio_index = 0

        self.view_source = (Path(__file__).parent / "Spacer_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def _view(self) -> dict[str, Any]:
        weight_a, weight_b = _RATIOS[self._ratio_index]
        doc = yaml.safe_load(self.view_source)
        assert isinstance(doc, dict)
        spacer_a = _find(doc, "spacer_a")
        spacer_b = _find(doc, "spacer_b")
        assert spacer_a is not None and spacer_b is not None
        spacer_a["style"]["width"] = f"flex:{weight_a}"
        spacer_b["style"]["width"] = f"flex:{weight_b}"
        label = _find(doc, "label")
        assert label is not None
        label["text"] = f"spacer ratio: {weight_a} : {weight_b}"
        return doc

    def cycle_ratio(self, event: Any) -> None:
        self._ratio_index = (self._ratio_index + 1) % len(_RATIOS)
        self.app.reload(self._view())
