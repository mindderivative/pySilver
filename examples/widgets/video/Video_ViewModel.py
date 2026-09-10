"""Video demo's logic: nothing to toggle, just the two source panels.

Pushing the one synthetic frame happens in app.py, after `mount()`, the
same way `examples/gallery/app.py` does it for its own Video demo -- not
here, since a ViewModel's `__init__` runs before the element tree exists
and `push_frame` needs a live `VideoElement` to call it on.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path

from pysilver import ViewModel


class VideoDemo(ViewModel):
    """State for `Video_View.yaml`. No commands -- there is nothing to interact with."""

    def __init__(self) -> None:
        self.view_source = (Path(__file__).parent / "Video_View.yaml").read_text()
        self.viewmodel_source = Path(__file__).read_text()
