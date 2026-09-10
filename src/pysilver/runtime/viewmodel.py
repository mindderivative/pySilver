"""ViewModels: the logic belonging to one view file.

An application's signals and handlers were a single flat namespace: one
context, one handler registry, shared by every node in the tree however deep
the include graph went. That works for one window and stops working the moment
a fragment wants logic of its own, because there is nowhere to put it that is
not global.

A :class:`ViewModel` is that somewhere. **One view file, one ViewModel** --
including the same fragment five times gives five copies of the *view* and one
ViewModel behind them, which is the right shape for logic that belongs to the
view rather than to an instance. Per-instance state stays where it already
lives, on the widget's own `state`.

    # parts/swatch_ViewModel.py
    from pysilver import Signal, ViewModel

    class Swatch(ViewModel):
        picked = Signal(False)

        def pick(self, event) -> None:
            self.picked.set(True)

    # app.py
    from parts.swatch_ViewModel import Swatch
    app.bind_view_model("parts/swatch_View.yaml", Swatch())

**Binding is explicit, and deliberately not by filename.** A view file naming
its own Python module would make the loader import code chosen by data, and
view files are untrusted input here -- `yaml.safe_load` only, includes confined
to the view directory, no `eval` anywhere. Nothing in a `.yaml` should be able
to decide what gets imported. So the application does the importing and says
what pairs with what.

The **naming convention is enforced** rather than merely suggested: a view with
a ViewModel must be `*_View.yaml` and the ViewModel must live in
`*_ViewModel.py`. That is the familiar MVVM shape, and a wrong name fails at
bind time with a message saying so instead of silently binding nothing. Views
without a ViewModel need no suffix, so this costs nothing until it is used.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

__all__ = ["ViewModel", "ViewModelError"]


class ViewModelError(Exception):
    """A ViewModel that cannot be bound: wrong file name, or a bad pairing."""


class ViewModel:
    """Base class for a view's logic.

    Public attributes become names the view's `{{ }}` expressions can read, and
    public methods become handlers its `handlers:` can name. Both are collected
    once at bind time, so neither costs anything per frame.
    """

    _app: Any = None

    @property
    def app(self) -> Any:
        """The application this ViewModel is bound to.

        For the few things that are genuinely the *application's* rather than
        the view's -- switching the theme is the honest example. Reaching for
        it often is a sign that logic has drifted to the wrong layer.
        """
        if self._app is None:
            raise ViewModelError(
                f"{type(self).__name__} is not bound yet; `app` is available "
                "from `bind_view_model` onwards."
            )
        return self._app

    @classmethod
    def _reserved(cls) -> set[str]:
        """Names belonging to this base class, which a view never sees.

        Both collections exclude them, so `app`, `names` and `handlers` cannot
        be read by an expression or named as an event handler -- a view file
        must not be able to reach the App object through its own ViewModel.
        """
        return {name for name in dir(ViewModel) if not name.startswith("_")}

    def names(self) -> dict[str, Any]:
        """Values this ViewModel publishes to its view's expressions."""
        reserved = self._reserved()
        return {
            name: getattr(self, name)
            for name in dir(self)
            if not name.startswith("_")
            and name not in reserved
            and not callable(getattr(self, name, None))
        }

    def handlers(self) -> dict[str, Any]:
        """Callables this ViewModel publishes to its view's `handlers:`."""
        reserved = self._reserved()
        return {
            name: getattr(self, name)
            for name in dir(self)
            if not name.startswith("_") and name not in reserved and callable(getattr(self, name))
        }


def check_naming(view: str, model: ViewModel) -> None:
    """Enforce the `_View.yaml` / `_ViewModel.py` pairing.

    Checked at bind time rather than by discovery, because binding is explicit
    -- the convention is here for familiarity and for the reader, and a
    violation should say so plainly rather than quietly doing nothing.
    """
    if not view.endswith("_View.yaml"):
        raise ViewModelError(
            f"{view!r} is bound to a ViewModel, so it must be named '*_View.yaml'. "
            "A view with no ViewModel needs no suffix."
        )
    name = Path(inspect.getfile(type(model))).name
    # Case-insensitive on purpose. MVVM's convention is `_ViewModel.py` and
    # PEP 8 says module names are lower case; those genuinely conflict, and
    # ruff's N999 will flag the camel form. The shape is what is enforced, so a
    # project can follow either convention without fighting its linter.
    if not name.lower().endswith("_viewmodel.py"):
        raise ViewModelError(
            f"{type(model).__name__} is defined in {name!r}, but a ViewModel "
            "must live in a '*_ViewModel.py' module (or '*_viewmodel.py')."
        )
