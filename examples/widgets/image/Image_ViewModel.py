"""Image demo's logic: nothing to toggle, just the two source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path

from pysilver import ViewModel

#: `Image.path:` resolves like any path a running process resolves -- not
#: relative to the view file -- so it comes from the ViewModel instead of
#: hardcoding a location that would break if the demo ran from elsewhere.
_ASSET = Path(__file__).parent.parent.parent / "gallery" / "assets" / "sample.png"


class ImageDemo(ViewModel):
    """State for `Image_View.yaml`. No commands -- the path never changes."""

    def __init__(self) -> None:
        self.image_path = str(_ASSET)

        self.view_source = (Path(__file__).parent / "Image_View.yaml").read_text(encoding="utf-8")
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")
