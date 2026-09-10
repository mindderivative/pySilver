"""Icon demo's logic: nothing to toggle, just the two source panels.

FILL and weight are shown side by side rather than through a click-toggle
-- `icon_fill`/`icon_weight` are plain numeric style properties, not
`value:`-style templated fields, so a view can't bind them to a Signal.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path

from pysilver import ViewModel


class IconDemo(ViewModel):
    """State for `Icon_View.yaml`. No commands -- nothing here is interactive."""

    def __init__(self) -> None:
        self.view_source = (Path(__file__).parent / "Icon_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")
