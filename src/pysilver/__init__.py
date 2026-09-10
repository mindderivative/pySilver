"""pySilver -- a GPU-accelerated declarative desktop GUI framework.

Everything re-exported here is the public API and is covered by semantic
versioning. Anything else is private and may change without a major bump.

The surface is deliberately small. An application needs `App`, a `Theme`, some
`Signal`s and its handlers; everything else here supports those. The event
classes are exported so a handler can be type-annotated without reaching into
a private module -- which is the test of whether a surface is actually usable.

`tests/test_public_api.py` pins this list. Adding to it is a minor release;
removing from it or changing a signature in it is a major one.
"""

from __future__ import annotations

from .app import App, run
from .config import Settings
from .motion import DURATION, EASING, Animation, Ticker
from .runtime import Engine
from .runtime.accessibility import AccessibleNode
from .runtime.events import Event, EventType, KeyEvent, PointerEvent, WheelEvent
from .runtime.signals import Computed, Effect, Signal, batch, untrack
from .runtime.viewmodel import ViewModel, ViewModelError
from .spec import SpecError, ViewSpec, WidgetKind, WidgetSpec, load_view
from .theme import TOKEN_ORDER, Palette, Theme, is_token

__version__ = "1.7.0"

__all__ = [
    "DURATION",
    "EASING",
    "TOKEN_ORDER",
    "AccessibleNode",
    "Animation",
    "App",
    "Computed",
    "Effect",
    "Engine",
    "Event",
    "EventType",
    "KeyEvent",
    "Palette",
    "PointerEvent",
    "Settings",
    "Signal",
    "SpecError",
    "Theme",
    "Ticker",
    "ViewModel",
    "ViewModelError",
    "ViewSpec",
    "WheelEvent",
    "WidgetKind",
    "WidgetSpec",
    "__version__",
    "batch",
    "is_token",
    "load_view",
    "run",
    "untrack",
]
