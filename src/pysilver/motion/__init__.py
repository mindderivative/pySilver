"""Motion: M3 easing, duration tokens, and the animation clock."""

from .animation import Animation, Ticker, default_ticker
from .easing import DURATION, EASING, Curve, curve, duration

__all__ = [
    "DURATION",
    "EASING",
    "Animation",
    "Curve",
    "Ticker",
    "curve",
    "default_ticker",
    "duration",
]
