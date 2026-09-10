"""The frozen public API.

`pysilver.__all__` is a promise covered by semantic versioning, so it is
pinned here rather than left to drift. A failure in this module is not a bug
to be silenced -- it is the question "did you mean to change the public API?",
and the answer decides the next version number:

* a name **added**            -> minor release
* a name **removed or renamed** -> major release
* a signature in the list changed -> major release
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import pysilver

#: Every name pySilver promises. Update deliberately, with a version bump.
PUBLIC_API = frozenset(
    {
        # application
        "AccessibleNode",
        "App",
        "ViewModel",
        "ViewModelError",
        "run",
        "Settings",
        "Engine",
        # reactivity
        "Signal",
        "Computed",
        "Effect",
        "batch",
        "untrack",
        # motion (added in 1.1 -- a new name is a minor release)
        "Animation",
        "Ticker",
        "EASING",
        "DURATION",
        # theming
        "Theme",
        "Palette",
        "TOKEN_ORDER",
        "is_token",
        # view documents
        "load_view",
        "ViewSpec",
        "WidgetSpec",
        "WidgetKind",
        "SpecError",
        # events, so a handler can be annotated without a private import
        "Event",
        "EventType",
        "PointerEvent",
        "KeyEvent",
        "WheelEvent",
        # metadata
        "__version__",
    }
)


def test_the_public_surface_is_exactly_what_was_frozen() -> None:
    assert set(pysilver.__all__) == PUBLIC_API


def test_every_promised_name_actually_imports() -> None:
    """`__all__` listing a name that does not exist breaks `import *`."""
    missing = [name for name in pysilver.__all__ if not hasattr(pysilver, name)]
    assert missing == []


def test_all_has_no_duplicates() -> None:
    """Ordering is ruff's job (RUF022, which sorts uppercase-first); a
    duplicate is what it will not catch."""
    assert len(pysilver.__all__) == len(set(pysilver.__all__))


def test_the_version_is_a_release_version() -> None:
    major, minor, patch = pysilver.__version__.split(".")
    assert (int(major), int(minor), int(patch)) >= (1, 0, 0)


def test_the_declared_version_matches_the_packaging_metadata() -> None:
    """Two copies of a version number drift; this is the only thing stopping
    an installed wheel from disagreeing with `pysilver.__version__`."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert declared == pysilver.__version__


def test_a_handler_can_be_annotated_from_the_public_api_alone() -> None:
    """The practical test of whether the surface is usable: writing a typed
    handler must not require importing from `pysilver.runtime`."""
    from pysilver import App, PointerEvent, Signal, Theme

    clicks = Signal(0)
    app = App(
        {
            "name": "root",
            "widget": "Button",
            "text": "Go",
            "handlers": {"on_click": "bump"},
            "style": {"width": 100, "height": 40},
        },
        theme=Theme(dark=True),
    )

    @app.handler
    def bump(event: PointerEvent) -> None:
        clicks.update(lambda n: n + 1)

    app.expose(clicks=clicks)
    app.mount()
    assert clicks.peek() == 0


@pytest.mark.parametrize(
    "module",
    [m.name for m in pkgutil.walk_packages(pysilver.__path__, "pysilver.")],
)
def test_every_submodule_imports_cleanly(module: str) -> None:
    """A module that only imports under some other module's side effects is a
    packaging bug that surfaces as an ImportError for the first user."""
    importlib.import_module(module)


def test_the_package_ships_type_information() -> None:
    """`py.typed` is what makes the annotations visible to a consumer's mypy."""
    from pathlib import Path

    assert (Path(pysilver.__file__).parent / "py.typed").is_file()
