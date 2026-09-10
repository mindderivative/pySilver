"""Fine-grained reactivity.

A read of a signal inside a tracking scope records a dependency; a write then
notifies exactly the observers that read it. That precision is the whole point:
a global dirty flag would rebuild the frame on every change, and ARCHITECTURE.md
12 shows the frame budget cannot absorb that.

Signals are engine-thread-only (ARCHITECTURE.md 8). Writes from a worker thread
must be marshalled with ``loop.call_soon_threadsafe``; the affinity check turns
a latent race into an immediate, located error.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

__all__ = [
    "Computed",
    "Effect",
    "Signal",
    "ThreadAffinityError",
    "batch",
    "bind_thread",
    "untrack",
]

_STACK: list[_Observer] = []
_BATCH_DEPTH = 0
_PENDING: dict[_Observer, None] = {}  # dict preserves insertion order
_FLUSHING = False
_OWNER_THREAD: int | None = None


class ThreadAffinityError(RuntimeError):
    """Raised when a signal is written from outside the engine thread."""


def bind_thread(ident: int | None = None) -> None:
    """Claim the calling thread (or *ident*) as the engine thread."""
    global _OWNER_THREAD
    _OWNER_THREAD = threading.get_ident() if ident is None else ident


def _check_thread() -> None:
    if _OWNER_THREAD is not None and threading.get_ident() != _OWNER_THREAD:
        raise ThreadAffinityError(
            "signals may only be written from the engine thread; "
            "use loop.call_soon_threadsafe from worker threads"
        )


class _Reactive:
    """Base for every participant in the dependency graph.

    Both edge sets live here rather than on separate Source/Observer bases:
    Computed is both, and two bases each carrying non-empty ``__slots__`` cannot
    be combined -- Python rejects the instance layout.
    """

    __slots__ = ("_deps", "_subs")

    def __init__(self) -> None:
        self._subs: set[_Observer] = set()  # observers depending on me
        self._deps: set[_Source] = set()  # sources I depend on


class _Observer(_Reactive, ABC):
    """Something that reads signals and must react when they change."""

    __slots__ = ()

    def _unlink(self) -> None:
        for dep in self._deps:
            dep._subs.discard(self)
        self._deps.clear()

    @abstractmethod
    def _notify(self) -> None:
        """Called when a dependency changed."""

    @abstractmethod
    def _run(self) -> None:
        """Called during flush to bring this observer up to date."""


class _Source(_Reactive):
    """Something observers can depend on."""

    __slots__ = ()

    def _track(self) -> None:
        if _STACK:
            observer = _STACK[-1]
            self._subs.add(observer)
            observer._deps.add(self)

    def _notify_subscribers(self) -> None:
        for sub in tuple(self._subs):
            sub._notify()


@contextmanager
def _scope(observer: _Observer) -> Iterator[None]:
    observer._unlink()
    _STACK.append(observer)
    try:
        yield
    finally:
        _STACK.pop()


class _NullObserver(_Observer):
    __slots__ = ()

    def _notify(self) -> None:  # pragma: no cover - never subscribed
        pass

    def _run(self) -> None:  # pragma: no cover
        pass

    def _unlink(self) -> None:
        pass


@contextmanager
def untrack() -> Iterator[None]:
    """Read signals without recording dependencies."""
    _STACK.append(_NullObserver())
    try:
        yield
    finally:
        _STACK.pop()


@contextmanager
def batch() -> Iterator[None]:
    """Defer effect execution until the outermost batch exits.

    Without this, a handler writing three signals runs its dependents three
    times. With it, they run once -- and never observe a half-applied state.
    """
    global _BATCH_DEPTH
    _BATCH_DEPTH += 1
    try:
        yield
    finally:
        _BATCH_DEPTH -= 1
        if _BATCH_DEPTH == 0:
            _flush()


def _schedule(observer: _Observer) -> None:
    _PENDING[observer] = None
    if _BATCH_DEPTH == 0 and not _FLUSHING:
        _flush()


def _flush() -> None:
    """Drain pending observers until quiet.

    Re-entrancy matters here: an effect that writes a signal would otherwise
    start a nested flush and recurse until the stack dies. The guard keeps such
    a write inside the existing drain loop, where the convergence counter can
    actually see it.
    """
    global _FLUSHING
    if _FLUSHING:
        return
    _FLUSHING = True
    try:
        guard = 0
        while _PENDING:
            pending = tuple(_PENDING)
            _PENDING.clear()
            for observer in pending:
                observer._run()
            guard += 1
            if guard > 100:
                _PENDING.clear()
                raise RuntimeError(
                    "signal update did not converge after 100 passes "
                    "(an effect probably writes a signal it also reads)"
                )
    finally:
        _FLUSHING = False


def _default_eq(a: Any, b: Any) -> bool:
    if a is b:
        return True
    try:
        return bool(a == b)
    except Exception:  # pragma: no cover - exotic __eq__
        return False


class Signal[T](_Source):
    """A mutable reactive value."""

    __slots__ = ("_eq", "_name", "_value")

    def __init__(
        self,
        value: T,
        *,
        name: str = "",
        eq: Callable[[T, T], bool] | None = None,
    ) -> None:
        super().__init__()
        self._value = value
        self._name = name
        self._eq = eq or _default_eq

    def get(self) -> T:
        self._track()
        return self._value

    def peek(self) -> T:
        """Read without creating a dependency."""
        return self._value

    def set(self, value: T) -> None:
        _check_thread()
        if self._eq(self._value, value):
            return
        self._value = value
        # Wrapped in a batch of its own: `_subs` is an unordered set, so without
        # this an Effect notified before a sibling Computed would flush and read
        # it still marked clean -- a stale value from a single, un-batched write.
        with batch():
            self._notify_subscribers()

    def update(self, fn: Callable[[T], T]) -> None:
        self.set(fn(self._value))

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def __repr__(self) -> str:
        label = f" {self._name!r}" if self._name else ""
        return f"<Signal{label}={self._value!r} subs={len(self._subs)}>"


class Computed[T](_Source, _Observer):
    """A derived value: memoised, lazily recomputed, itself observable."""

    __slots__ = ("_dirty", "_fn", "_value")

    def __init__(self, fn: Callable[[], T]) -> None:
        super().__init__()
        self._fn = fn
        self._value: T | None = None
        self._dirty = True

    def get(self) -> T:
        self._track()
        if self._dirty:
            self._run()
        return self._value  # type: ignore[return-value]

    def peek(self) -> T:
        if self._dirty:
            self._run()
        return self._value  # type: ignore[return-value]

    def _run(self) -> None:
        with _scope(self):
            self._value = self._fn()
        self._dirty = False

    def _notify(self) -> None:
        if self._dirty:
            return
        self._dirty = True
        # Invalidation is transitive: dependents of a computed must hear about
        # it even though the recomputation itself is deferred.
        self._notify_subscribers()

    def __repr__(self) -> str:
        return f"<Computed dirty={self._dirty} value={self._value!r}>"


class Effect(_Observer):
    """A side effect that re-runs when its dependencies change."""

    __slots__ = ("_disposed", "_fn")

    def __init__(self, fn: Callable[[], None], *, immediate: bool = True) -> None:
        super().__init__()
        self._fn = fn
        self._disposed = False
        if immediate:
            self._run()

    def _run(self) -> None:
        if self._disposed:
            return
        with _scope(self):
            self._fn()

    def _notify(self) -> None:
        if not self._disposed:
            _schedule(self)

    def dispose(self) -> None:
        """Unsubscribe permanently. Elements call this when disposed."""
        self._disposed = True
        self._unlink()

    @property
    def disposed(self) -> bool:
        return self._disposed
