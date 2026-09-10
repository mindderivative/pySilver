"""Logic for the locked dialog -- the one a click outside will not close.

Note what is absent: any counterpart to `on_dismiss`. With `dismissable: false`
the runtime never closes this overlay, so there is nothing to be told about,
and the only way out is the button below.
"""

from __future__ import annotations

from typing import Any

from pysilver import Signal, ViewModel


class LockedDialog(ViewModel):
    def __init__(self, locking: Signal) -> None:
        #: The same signal the gallery calls `locking`, named for this view.
        #: A fragment's own ViewModel owns whether the fragment is showing.
        self.is_open = locking

    def unlock(self, event: Any) -> None:
        self.is_open.set(False)
