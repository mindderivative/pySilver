"""The gallery's logic: its state, and what its controls do.

This is where the application's behaviour lives. `app.py` next door is the
entry point -- it builds the window and says which ViewModel drives which view,
and nothing else. Moving one function into `app.py` would be the first step
back towards a single global namespace, which is what a ViewModel exists to
avoid.

One view file, one ViewModel: this pairs with `gallery_View.yaml`, and the
fragments it includes may have their own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, Theme, ViewModel

#: The gallery's M3 source colour. The theme is rebuilt from it on a switch.
SEED = "#6750A4"

#: `Image.path:` resolves like any path a running process resolves -- not
#: relative to the view file -- so the view reads it from the ViewModel
#: instead of hardcoding a location that would break if the example were run
#: from a different working directory.
_ASSET_DIR = Path(__file__).parent / "assets"


class Gallery(ViewModel):
    """State and commands for `gallery_View.yaml`.

    Public attributes are the names its `{{ }}` expressions can read; public
    methods are the handlers its `handlers:` can name. Nothing has to be
    registered twice.
    """

    def __init__(self) -> None:
        self.clicks = Signal(0, name="clicks")
        self.dark = Signal(True, name="dark")
        self.confirming = Signal(False, name="confirming")
        self.locking = Signal(False, name="locking")

        # --- the navigation shell: which page PageHost shows, and whether
        # the rail is expanded into a full drawer. ---
        self.current_page = Signal("home", name="current_page")
        self.nav_expanded = Signal(False, name="nav_expanded")

        # --- selection-container state: `value:` only *reads* a signal, so
        # every Tabs/SegmentedButton/NavigationRail/TreeView needs a click
        # handler that writes the clicked child's name back into one. ---
        self.tab = Signal("t0", name="tab")
        self.segment = Signal("s0", name="segment")
        self.rail = Signal("r0", name="rail")
        self.tree_selection = Signal("main", name="tree_selection")
        self.tree_src_expanded = Signal(True, name="tree_src_expanded")
        self.accordion_open = Signal(True, name="accordion_open")

        # --- SpinBox / Pagination hand their new value to on_change instead,
        # since a click can mean "+1", "-1", or "jump to page 7". ---
        self.spin_value = Signal("3", name="spin_value")
        self.page = Signal("1", name="page")

        # --- overlays this view opens itself (the two Dialogs live in parts/
        # with their own ViewModel -- see app.py). Each needs its own
        # `on_dismiss` handler: a bound `open:` means the runtime closing the
        # overlay locally is not enough to make it re-openable. ---
        self.popover_open = Signal(False, name="popover_open")
        self.menu_open = Signal(False, name="menu_open")
        self.tooltip_open = Signal(False, name="tooltip_open")
        self.snackbar_open = Signal(False, name="snackbar_open")
        self.bottom_sheet_open = Signal(False, name="bottom_sheet_open")
        self.side_sheet_open = Signal(False, name="side_sheet_open")

        # --- text input demo ---
        self.email = Signal("ada@example.com", name="email")

        # --- Image: a plain attribute, not a Signal -- the path never
        # changes at runtime, so there is nothing here for reactivity to do. ---
        self.image_path = str(_ASSET_DIR / "sample.png")

    # ------------------------------------------------------------- commands

    def confirm(self, event: Any) -> None:
        self.clicks.update(lambda n: n + 1)

    def reset(self, event: Any) -> None:
        self.clicks.set(0)

    def ask(self, event: Any) -> None:
        """Opens the dialog in parts/confirm_dialog_View.yaml."""
        self.confirming.set(True)

    def lock(self, event: Any) -> None:
        """Opens the locked dialog, which a click outside will not close."""
        self.locking.set(True)

    def toggle_theme(self, event: Any) -> None:
        """A theme switch is a single palette-buffer upload -- no relayout.

        One of the few things that is the *application's* rather than the
        view's, which is why it reaches for `self.app`.
        """
        self.dark.update(lambda on: not on)
        self.app.set_theme(Theme(seed=SEED, dark=self.dark.peek()))

    # -------------------------------------------------------- navigation

    def select_nav(self, event: Any) -> None:
        """One handler for the rail's destinations -- a single
        `NavigationRail` now, collapsed or expanded, rather than a paired
        rail+drawer with duplicate `r_`/`d_`-prefixed items. Each item is
        still `nav_`-prefixed (PageHost's own pages beneath already use
        these bare names, and names must be unique across the view), so one
        prefix still needs stripping -- just one instead of two."""
        self.current_page.set(event.target.name.removeprefix("nav_"))

    def toggle_nav(self, event: Any) -> None:
        self.nav_expanded.update(lambda on: not on)

    # ------------------------------------------------ selection containers

    def select_tab(self, event: Any) -> None:
        self.tab.set(event.target.name)

    def select_segment(self, event: Any) -> None:
        self.segment.set(event.target.name)

    def select_rail(self, event: Any) -> None:
        self.rail.set(event.target.name)

    def select_tree(self, event: Any) -> None:
        self.tree_selection.set(event.target.name)

    def toggle_tree_src(self, event: Any) -> None:
        self.tree_selection.set(event.target.name)
        self.tree_src_expanded.update(lambda expanded: not expanded)

    def toggle_accordion(self, event: Any) -> None:
        self.accordion_open.update(lambda on: not on)

    def change_spin(self, event: Any) -> None:
        self.spin_value.set(event.value)

    def change_page(self, event: Any) -> None:
        self.page.set(event.value)

    def change_email(self, event: Any) -> None:
        self.email.set(event.value)

    # ------------------------------------------------------------ overlays

    def open_popover(self, event: Any) -> None:
        self.popover_open.set(True)

    def close_popover(self, event: Any) -> None:
        self.popover_open.set(False)

    def open_menu(self, event: Any) -> None:
        self.menu_open.set(True)

    def close_menu(self, event: Any) -> None:
        self.menu_open.set(False)

    def open_tooltip(self, event: Any) -> None:
        self.tooltip_open.set(True)

    def close_tooltip(self, event: Any) -> None:
        self.tooltip_open.set(False)

    def open_snackbar(self, event: Any) -> None:
        self.snackbar_open.set(True)

    def close_snackbar(self, event: Any) -> None:
        self.snackbar_open.set(False)

    def open_bottom_sheet(self, event: Any) -> None:
        self.bottom_sheet_open.set(True)

    def close_bottom_sheet(self, event: Any) -> None:
        self.bottom_sheet_open.set(False)

    def open_side_sheet(self, event: Any) -> None:
        self.side_sheet_open.set(True)

    def close_side_sheet(self, event: Any) -> None:
        self.side_sheet_open.set(False)

    # -------------------------------------------------------------- canvas

    def draw_canvas(self, canvas: Any) -> None:
        """`on_paint` is called with one argument, a `CanvasContext` -- no
        `Event` wraps it, since there is nothing an application handler could
        do with one. This sweeps through the primitive vocabulary once:
        a bordered rounded rect, a line, a circle, an arc, a polygon, text.
        """
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
