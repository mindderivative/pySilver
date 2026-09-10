"""Material Design 3 easing curves and duration tokens.

Every value here is quoted from `styles/M3-Styles-Motion-EasingAndDuration-
TokensSpecs.md`. Durations are in **seconds**, because that is what a frame
delta is; the spec states them in milliseconds and the conversion happens once,
here.

The `emphasized` curve is the interesting one. It is not a cubic bezier at all
but a **two-segment path** -- M3 gives it as
`M 0,0 C 0.05,0 0.133333,0.06 0.166666,0.4 C 0.208333,0.82 0.25,1 1,1`, and the
spec's own CSS row says "N/A (Use Standard as a fallback)" because
`cubic-bezier()` cannot express two segments. pySilver is not bound by CSS's
limits, so it implements the real curve rather than the fallback.
"""

from __future__ import annotations

from typing import Final, Protocol

__all__ = ["DURATION", "EASING", "Curve", "curve", "duration"]

#: Newton-Raphson usually converges in 2-4 steps; the cap is a guard, not a
#: budget. Below this error the difference is far under one display pixel.
_EPSILON: Final = 1e-7
_MAX_ITERATIONS: Final = 12


class Curve(Protocol):
    """Maps linear progress 0..1 to eased progress."""

    def __call__(self, t: float) -> float: ...


def _bezier(a: float, b: float, c: float, d: float, t: float) -> float:
    """Cubic Bezier at parameter `t` for one axis."""
    u = 1.0 - t
    return u * u * u * a + 3.0 * u * u * t * b + 3.0 * u * t * t * c + t * t * t * d


def _bezier_slope(a: float, b: float, c: float, d: float, t: float) -> float:
    u = 1.0 - t
    return 3.0 * u * u * (b - a) + 6.0 * u * t * (c - b) + 3.0 * t * t * (d - c)


class Segment:
    """One cubic Bezier segment, solved for y given x.

    The curve is a function of *time*, so the parameter `t` of the Bezier is
    not the input: the input is x, and t must be found first. Newton-Raphson
    does that, falling back to bisection where the slope is flat -- which it is
    at both ends of every M3 curve, so the fallback is not hypothetical.
    """

    __slots__ = ("x0", "x1", "x2", "x3", "y0", "y1", "y2", "y3")

    def __init__(
        self,
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        p3: tuple[float, float],
    ) -> None:
        (self.x0, self.y0) = p0
        (self.x1, self.y1) = p1
        (self.x2, self.y2) = p2
        (self.x3, self.y3) = p3

    def _t_for_x(self, x: float) -> float:
        t = (x - self.x0) / (self.x3 - self.x0) if self.x3 != self.x0 else 0.0
        for _ in range(_MAX_ITERATIONS):
            error = _bezier(self.x0, self.x1, self.x2, self.x3, t) - x
            if abs(error) < _EPSILON:
                return t
            slope = _bezier_slope(self.x0, self.x1, self.x2, self.x3, t)
            if abs(slope) < _EPSILON:
                break
            t -= error / slope
        # Bisection: slower, but cannot diverge the way Newton can on a flat.
        low, high = 0.0, 1.0
        t = max(0.0, min(1.0, t))
        for _ in range(_MAX_ITERATIONS * 2):
            value = _bezier(self.x0, self.x1, self.x2, self.x3, t)
            if abs(value - x) < _EPSILON:
                break
            if value < x:
                low = t
            else:
                high = t
            t = (low + high) / 2.0
        return t

    def __call__(self, x: float) -> float:
        return _bezier(self.y0, self.y1, self.y2, self.y3, self._t_for_x(x))


class Cubic:
    """A CSS-style `cubic-bezier(x1, y1, x2, y2)`, anchored at (0,0)-(1,1)."""

    __slots__ = ("_segment",)

    def __init__(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self._segment = Segment((0.0, 0.0), (x1, y1), (x2, y2), (1.0, 1.0))

    def __call__(self, t: float) -> float:
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        return self._segment(t)


class Path:
    """A curve made of several Bezier segments, for M3's `emphasized`."""

    __slots__ = ("_segments",)

    def __init__(self, *segments: Segment) -> None:
        self._segments = segments

    def __call__(self, t: float) -> float:
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        for segment in self._segments:
            if t <= segment.x3:
                return segment(t)
        return self._segments[-1](t)


def _linear(t: float) -> float:
    return max(0.0, min(1.0, t))


#: M3's named easing sets. Control points quoted from the spec's CSS/Flutter
#: rows, which agree with each other and with the Android path interpolators.
EASING: Final[dict[str, Curve]] = {
    "linear": _linear,
    # Standard set -- everyday transitions.
    "standard": Cubic(0.2, 0.0, 0.0, 1.0),
    "standard_decelerate": Cubic(0.0, 0.0, 0.0, 1.0),
    "standard_accelerate": Cubic(0.3, 0.0, 1.0, 1.0),
    # Emphasized set -- large, expressive transitions.
    "emphasized": Path(
        Segment((0.0, 0.0), (0.05, 0.0), (0.133333, 0.06), (0.166666, 0.4)),
        Segment((0.166666, 0.4), (0.208333, 0.82), (0.25, 1.0), (1.0, 1.0)),
    ),
    "emphasized_decelerate": Cubic(0.05, 0.7, 0.1, 1.0),
    "emphasized_accelerate": Cubic(0.3, 0.0, 0.8, 0.15),
}

#: M3 duration tokens, converted from the spec's milliseconds to seconds.
DURATION: Final[dict[str, float]] = {
    "short1": 0.050,
    "short2": 0.100,
    "short3": 0.150,
    "short4": 0.200,
    "medium1": 0.250,
    "medium2": 0.300,
    "medium3": 0.350,
    "medium4": 0.400,
    "long1": 0.450,
    "long2": 0.500,
    "long3": 0.550,
    "long4": 0.600,
    "extra_long1": 0.700,
    "extra_long2": 0.800,
    "extra_long3": 0.900,
    "extra_long4": 1.000,
}


def curve(name: str | Curve) -> Curve:
    """Resolve an easing name. A callable passes through, so an application can
    supply its own without the framework knowing about it."""
    if callable(name):
        return name
    try:
        return EASING[name]
    except KeyError:
        raise KeyError(f"unknown easing {name!r}; use one of {', '.join(sorted(EASING))}") from None


def duration(value: str | float) -> float:
    """Resolve a duration token to seconds. A number passes through."""
    if isinstance(value, int | float):
        return float(value)
    try:
        return DURATION[value]
    except KeyError:
        raise KeyError(
            f"unknown duration token {value!r}; use one of {', '.join(DURATION)}"
        ) from None
