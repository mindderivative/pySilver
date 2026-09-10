"""Logic for the dismissable confirm dialog.

A fragment with its own ViewModel, which is the point of the pattern: this
file's behaviour lives beside this file's view, not in the application's
namespace.

The signal it drives belongs to the *gallery*, though -- whether the dialog is
open is the gallery's state, not the dialog's. So it is handed in at
construction by `app.py`, which is the composition root. A child view cannot
receive an object through `with:`, because parameters are textual substitution
into YAML; sharing state between ViewModels is Python's job and is done in
Python, where you can see it.
"""

from __future__ import annotations

from typing import Any

from pysilver import Signal, ViewModel


class ConfirmDialog(ViewModel):
    def __init__(self, confirming: Signal) -> None:
        #: Published so this view's `open:` can read it. The gallery calls
        #: this signal `confirming`; in here it is simply whether the dialog
        #: is up. One object, two names -- the ViewModel boundary working.
        self.is_open = confirming

    def dismiss(self, event: Any) -> None:
        """Closes the dialog. Both buttons use this, and so does `on_dismiss`.

        The runtime closing a dismissable overlay is only a request -- `open:`
        is bound to this signal, and clearing it is what actually closes it.
        """
        self.is_open.set(False)
