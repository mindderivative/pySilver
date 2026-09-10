"""Animations and the clock that drives them.

One property governs the design: **an idle pySilver application renders zero
frames** (ARCHITECTURE.md 5.10). Animation is the one thing that legitimately
needs continuous frames, so it must ask for them precisely while it is running
and stop the moment it is not. `Ticker.active` is that signal, and the App
requests the next frame only while it is true.

Animations are advanced by a **frame delta**, never by wall-clock sampling
inside a widget. A widget that read the clock itself would produce a different
value each time it was asked during one frame, so layout and paint could
disagree about where something is.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from .easing import Curve, curve, duration

__all__ = ["Animation", "Ticker", "default_ticker"]

#: A frame delta larger than this is treated as a stall -- a debugger pause, a
#: dragged window, a machine going to sleep. Advancing by the real delta would
#: teleport every animation to its end; clamping loses time instead, which is
#: the failure nobody notices.
MAX_FRAME_DELTA: Final = 0.1


class Animation:
    """Eases a float from `start` to `end`.

    Interrupting one **retargets** rather than restarts: the new animation
    begins from wherever the value currently is, so a switch toggled twice in
    quick succession glides rather than snapping back to its origin.
    """

    __slots__ = (
        "_curve",
        "_duration",
        "_elapsed",
        "end",
        "on_change",
        "repeat",
        "start",
    )

    def __init__(
        self,
        start: float,
        end: float,
        *,
        duration: str | float = "short4",
        curve: str | Curve = "standard",
        repeat: bool = False,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.start = start
        self.end = end
        self._duration = max(0.0, _resolve_duration(duration))
        self._curve = _resolve_curve(curve)
        self.repeat = repeat
        self.on_change = on_change
        self._elapsed = 0.0

    # ------------------------------------------------------------- reading

    @property
    def progress(self) -> float:
        """Linear progress, before easing."""
        if self._duration <= 0.0:
            return 1.0
        return min(1.0, self._elapsed / self._duration)

    @property
    def value(self) -> float:
        eased = self._curve(self.progress)
        return self.start + (self.end - self.start) * eased

    @property
    def done(self) -> bool:
        return not self.repeat and self.progress >= 1.0

    @property
    def duration(self) -> float:
        return self._duration

    # ------------------------------------------------------------ advancing

    def advance(self, dt: float) -> bool:
        """Move time forward. Returns whether the animation is still running."""
        if self.done:
            return False
        before = self.value
        self._elapsed += max(0.0, dt)
        if self.repeat and self._duration > 0.0:
            self._elapsed %= self._duration
        if self.on_change is not None and self.value != before:
            self.on_change()
        return not self.done

    def retarget(
        self,
        end: float,
        *,
        duration: str | float | None = None,
        curve: str | Curve | None = None,
    ) -> None:
        """Aim at a new end, starting from the value right now.

        Timing may change with direction, because M3's own pairs do: entering
        the screen is Emphasized decelerate over 400ms, leaving it is
        Emphasized accelerate over 200ms. A thing arrives gently and departs
        briskly.
        """
        if end == self.end:
            return
        self.start = self.value
        self.end = end
        self._elapsed = 0.0
        if duration is not None:
            self._duration = max(0.0, _resolve_duration(duration))
        if curve is not None:
            self._curve = _resolve_curve(curve)

    def finish(self) -> None:
        """Jump to the end. Used when motion is disabled."""
        self._elapsed = self._duration


def _resolve_duration(value: str | float) -> float:
    return duration(value)


def _resolve_curve(value: str | Curve) -> Curve:
    return curve(value)


class Ticker:
    """Owns the animations currently running.

    A finished animation is dropped, so `active` is false again the moment the
    last one lands and the application goes back to rendering nothing.
    """

    __slots__ = ("_running", "reduce_motion")

    def __init__(self, *, reduce_motion: bool = False) -> None:
        self._running: list[Animation] = []
        #: Accessibility: honour a user who has asked for less movement. The
        #: animation still runs, it simply arrives immediately -- so widget
        #: code needs no branch and cannot forget to handle the case.
        self.reduce_motion = reduce_motion

    def add(self, animation: Animation) -> Animation:
        if self.reduce_motion:
            animation.finish()
            return animation
        if animation not in self._running:
            self._running.append(animation)
        return animation

    def discard(self, animation: Animation) -> None:
        """Stop advancing `animation`, if it is running. Safe to call twice.

        The counterpart to `add`, and the only way to stop a repeating one: a
        `repeat=True` animation is never `done`, so without this it would
        keep firing `on_change` forever after the element that owns it is
        disposed, and `active` would never go back to False.
        """
        if animation in self._running:
            self._running.remove(animation)

    def tick(self, dt: float) -> int:
        """Advance every running animation. Returns how many are still going."""
        if not self._running:
            return 0
        dt = min(max(0.0, dt), MAX_FRAME_DELTA)
        self._running = [a for a in self._running if a.advance(dt)]
        return len(self._running)

    @property
    def active(self) -> bool:
        """Whether a frame is needed. The App asks this and nothing else."""
        return bool(self._running)

    @property
    def count(self) -> int:
        return len(self._running)

    def clear(self) -> None:
        self._running.clear()


_DEFAULT: Ticker | None = None


def default_ticker() -> Ticker:
    """Process-wide fallback, mirroring `default_text_engine`.

    An App installs its own on the element tree; this exists so an element
    built outside one still behaves rather than raising.
    """
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Ticker()
    return _DEFAULT
