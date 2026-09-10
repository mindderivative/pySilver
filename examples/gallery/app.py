"""pySilver widget gallery -- the entry point, and nothing else.

    python examples/gallery/app.py

This file builds the window and says which ViewModel drives which view. The
behaviour lives in `gallery_ViewModel.py`, beside the view it belongs to.
Moving one handler back in here would be the first step towards a single
global namespace, which is what a ViewModel exists to avoid.

The gallery exercises every widget kind and doubles as the corpus for the
golden-image suite. Hot reload is on: edit `gallery_View.yaml` while it runs
and the window updates without losing the click count or which button has
focus.
"""

from pathlib import Path

import numpy as np
from gallery_ViewModel import SEED, Gallery
from parts.confirm_dialog_ViewModel import ConfirmDialog
from parts.locked_dialog_ViewModel import LockedDialog

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "gallery_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed=SEED, dark=True),
    settings=Settings(
        title="pySilver gallery",
        width=900,
        height=820,
        hot_reload=True,
        # Ask the compositor for the window frame instead of libdecor. On KDE
        # Plasma that skips libdecor entirely, including the "Failed to load
        # plugin 'libdecor-gtk.so'" warning a missing GTK produces.
        #
        # Note if you run this on GNOME: it offers no server-side decorations
        # for xdg-shell, so this leaves the window with no title bar and no
        # close button. Drop this line there -- the default is "auto".
        wayland_decorations="server",
    ),
)

#: One view file, one ViewModel -- for fragments too. This file is the
#: composition root: it builds each ViewModel and hands the dialogs the gallery
#: signal they act on, because whether a dialog is open is the gallery's state
#: rather than the dialog's. A child view cannot be passed an object through
#: `with:` (parameters are textual substitution into YAML), so sharing between
#: ViewModels happens here, in Python, where it is visible.
gallery = app.bind_view_model("gallery_View.yaml", Gallery())
app.bind_view_model("parts/confirm_dialog_View.yaml", ConfirmDialog(gallery.confirming))
app.bind_view_model("parts/locked_dialog_View.yaml", LockedDialog(gallery.locking))

#: Every page and every shared nav fragment is really the same gallery,
#: split across files for navigation, not a separate feature with its own
#: state -- `stamp_view` gives each included file its own view id
#: (spec/include.py), so a handler declared in gallery_ViewModel.py is only
#: visible to nodes from files THIS ViewModel is bound to. Rebinding the same
#: instance to each one keeps every page reading and writing the identical
#: signals (current_page, clicks, dark, ...) rather than scattering copies.
for _page in (
    "pages/home_View.yaml",
    "pages/foundations_View.yaml",
    "pages/structure_View.yaml",
    "pages/input_View.yaml",
    "pages/media_View.yaml",
    "pages/advanced_View.yaml",
    "pages/settings_View.yaml",
    "parts/nav_item_View.yaml",
):
    app.bind_view_model(_page, gallery)


def _synthetic_video_frame() -> np.ndarray:
    """`Video` has no file to decode -- an application feeds it frames

    directly through `push_frame`. A live camera or stream would call this
    repeatedly; the gallery only needs one frame to prove the widget paints
    what it is given, so it generates a single (h, w, 4) uint8 RGBA array
    with the same gradient technique `assets/sample.png` used for `Image`,
    in a different palette so the two widgets read as distinct sources.
    """
    h, w = 160, 260
    y, x = np.mgrid[0:h, 0:w]
    t = (x / w + y / h) / 2.0
    top = np.array([0x00, 0x69, 0x6B], dtype=np.float32)  # teal
    bottom = np.array([0x6A, 0x1B, 0x9A], dtype=np.float32)  # violet
    rgb = top[None, None, :] + (bottom - top)[None, None, :] * t[:, :, None]
    frame = np.empty((h, w, 4), dtype=np.uint8)
    frame[:, :, :3] = rgb.astype(np.uint8)
    frame[:, :, 3] = 255
    return frame


# `mount()` is idempotent and `run()`/`attach()` call it again -- doing it
# here just makes `app.root.find(...)` available so the composition root can
# push a frame before the window ever opens.
#
# `video_demo` lives on the "media" page, which is not the one PageHost shows
# first (that's "home") -- `find()` only reaches the currently active page,
# so this goes through `content`'s own `page()` instead, which reaches any
# page's built subtree regardless of activation (every page is built eagerly
# at mount time; only *aliveness* -- a ticker, a live PTY -- is gated).
app.mount()
app.root.find("content").page("media").find("video_demo").push_frame(_synthetic_video_frame())

if __name__ == "__main__":
    app.run()
