"""Button Group demo's logic: three independent toggles in the standard
group, one single-select switch in the connected group, and the two
source panels.

See app.py in this directory for the entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pysilver import Signal, ViewModel


class ButtonGroupDemo(ViewModel):
    """State and commands for `ButtonGroup_View.yaml`."""

    def __init__(self) -> None:
        # Standard group -- a formatting toolbar. Each button is an
        # independent toggle (the same value:/on_click: convention Chip's
        # filter variant already uses) since bold/italic/underline
        # legitimately stack.
        self.bold = Signal(False, name="bold")
        self.italic = Signal(False, name="italic")
        self.underline = Signal(False, name="underline")
        # Connected group -- a time-period switcher. One shared Signal
        # names which button is active; each button's own value: compares
        # against it, and clicking always SETS it (not a toggle-flip) --
        # exactly one of the three is ever selected, the same
        # single-select pattern `COMPONENT_BUTTON_GROUPS.md` names as the
        # connected variant's replacement for the deprecated segmented
        # button. phil: "connected buttons should not hold the square
        # state they should switch between them" -- an independent
        # per-button toggle (this demo's first cut) let more than one
        # look selected at once, which doesn't read as a real switch.
        self.period = Signal("day", name="period")

        # Size-ladder demo -- one standard group per size, all three buttons
        # independently toggleable (same convention as bold/italic/
        # underline above -- every button in a standard group can be
        # selected on its own, not just the first), so clicking any of them
        # genuinely grows/shrinks and shifts its siblings at every size.
        self.ladder_xs_save = Signal(True, name="ladder_xs_save")
        self.ladder_xs_share = Signal(False, name="ladder_xs_share")
        self.ladder_xs_delete = Signal(False, name="ladder_xs_delete")
        self.ladder_s_save = Signal(True, name="ladder_s_save")
        self.ladder_s_share = Signal(False, name="ladder_s_share")
        self.ladder_s_delete = Signal(False, name="ladder_s_delete")
        self.ladder_m_save = Signal(True, name="ladder_m_save")
        self.ladder_m_share = Signal(False, name="ladder_m_share")
        self.ladder_m_delete = Signal(False, name="ladder_m_delete")
        self.ladder_l_save = Signal(True, name="ladder_l_save")
        self.ladder_l_share = Signal(False, name="ladder_l_share")
        self.ladder_l_delete = Signal(False, name="ladder_l_delete")
        self.ladder_xl_save = Signal(True, name="ladder_xl_save")
        self.ladder_xl_share = Signal(False, name="ladder_xl_share")
        self.ladder_xl_delete = Signal(False, name="ladder_xl_delete")

        self.view_source = (Path(__file__).parent / "ButtonGroup_View.yaml").read_text(
            encoding="utf-8"
        )
        self.viewmodel_source = Path(__file__).read_text(encoding="utf-8")

    def toggle_bold(self, event: Any) -> None:
        self.bold.update(lambda v: not v)

    def toggle_italic(self, event: Any) -> None:
        self.italic.update(lambda v: not v)

    def toggle_underline(self, event: Any) -> None:
        self.underline.update(lambda v: not v)

    def select_day(self, event: Any) -> None:
        self.period.set("day")

    def select_week(self, event: Any) -> None:
        self.period.set("week")

    def select_month(self, event: Any) -> None:
        self.period.set("month")

    def toggle_ladder_xs_save(self, event: Any) -> None:
        self.ladder_xs_save.update(lambda v: not v)

    def toggle_ladder_xs_share(self, event: Any) -> None:
        self.ladder_xs_share.update(lambda v: not v)

    def toggle_ladder_xs_delete(self, event: Any) -> None:
        self.ladder_xs_delete.update(lambda v: not v)

    def toggle_ladder_s_save(self, event: Any) -> None:
        self.ladder_s_save.update(lambda v: not v)

    def toggle_ladder_s_share(self, event: Any) -> None:
        self.ladder_s_share.update(lambda v: not v)

    def toggle_ladder_s_delete(self, event: Any) -> None:
        self.ladder_s_delete.update(lambda v: not v)

    def toggle_ladder_m_save(self, event: Any) -> None:
        self.ladder_m_save.update(lambda v: not v)

    def toggle_ladder_m_share(self, event: Any) -> None:
        self.ladder_m_share.update(lambda v: not v)

    def toggle_ladder_m_delete(self, event: Any) -> None:
        self.ladder_m_delete.update(lambda v: not v)

    def toggle_ladder_l_save(self, event: Any) -> None:
        self.ladder_l_save.update(lambda v: not v)

    def toggle_ladder_l_share(self, event: Any) -> None:
        self.ladder_l_share.update(lambda v: not v)

    def toggle_ladder_l_delete(self, event: Any) -> None:
        self.ladder_l_delete.update(lambda v: not v)

    def toggle_ladder_xl_save(self, event: Any) -> None:
        self.ladder_xl_save.update(lambda v: not v)

    def toggle_ladder_xl_share(self, event: Any) -> None:
        self.ladder_xl_share.update(lambda v: not v)

    def toggle_ladder_xl_delete(self, event: Any) -> None:
        self.ladder_xl_delete.update(lambda v: not v)
