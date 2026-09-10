"""Reactivity: dependency tracking, invalidation precision, batching."""

from __future__ import annotations

import threading

import pytest

from pysilver.runtime import signals
from pysilver.runtime.signals import (
    Computed,
    Effect,
    Signal,
    ThreadAffinityError,
    batch,
    bind_thread,
    untrack,
)


@pytest.fixture(autouse=True)
def _reset_thread_binding():
    yield
    signals._OWNER_THREAD = None


def test_get_and_set() -> None:
    s = Signal(1)
    assert s.get() == 1
    s.set(2)
    assert s.get() == 2


def test_effect_runs_immediately() -> None:
    log: list[int] = []
    s = Signal(1)
    Effect(lambda: log.append(s.get()))
    assert log == [1]


def test_effect_reruns_on_change() -> None:
    log: list[int] = []
    s = Signal(1)
    Effect(lambda: log.append(s.get()))
    s.set(2)
    s.set(3)
    assert log == [1, 2, 3]


def test_equal_write_does_not_notify() -> None:
    """Precision matters: a no-op write must not cost a rebuild."""
    log: list[int] = []
    s = Signal(1)
    Effect(lambda: log.append(s.get()))
    s.set(1)
    assert log == [1]


def test_only_actual_readers_are_notified() -> None:
    a, b = Signal(1), Signal(1)
    log: list[str] = []
    Effect(lambda: (a.get(), log.append("a"))[1])
    Effect(lambda: (b.get(), log.append("b"))[1])
    log.clear()
    a.set(2)
    assert log == ["a"], "an unrelated signal triggered work"


def test_peek_does_not_subscribe() -> None:
    s = Signal(1)
    log: list[int] = []
    Effect(lambda: log.append(s.peek()))
    s.set(2)
    assert log == [1]
    assert s.subscriber_count == 0


def test_untrack_suppresses_dependencies() -> None:
    s = Signal(1)
    log: list[int] = []

    def run() -> None:
        with untrack():
            log.append(s.get())

    Effect(run)
    s.set(2)
    assert log == [1]


def test_dependencies_are_recomputed_each_run() -> None:
    """A branch no longer taken must stop causing reruns."""
    flag, a, b = Signal(True), Signal("a"), Signal("b")
    log: list[str] = []
    Effect(lambda: log.append(a.get() if flag.get() else b.get()))
    flag.set(False)
    log.clear()
    a.set("a2")
    assert log == [], "stale dependency on the untaken branch"
    b.set("b2")
    assert log == ["b2"]


# ---------------------------------------------------------------- computed


def test_computed_derives_and_memoises() -> None:
    calls = []
    a, b = Signal(1), Signal(2)
    total = Computed(lambda: (calls.append(1), a.get() + b.get())[1])
    assert total.get() == 3
    assert total.get() == 3
    assert len(calls) == 1, "computed recomputed without a change"


def test_computed_invalidates_transitively() -> None:
    a = Signal(1)
    doubled = Computed(lambda: a.get() * 2)
    quadrupled = Computed(lambda: doubled.get() * 2)
    log: list[int] = []
    Effect(lambda: log.append(quadrupled.get()))
    a.set(5)
    assert log == [4, 20]


def test_computed_is_lazy_until_read() -> None:
    calls: list[int] = []
    a = Signal(1)
    c = Computed(lambda: (calls.append(1), a.get())[1])
    assert calls == []
    c.get()
    assert calls == [1]


def test_computed_peek_does_not_subscribe() -> None:
    a = Signal(1)
    c = Computed(lambda: a.get() * 2)
    log: list[int] = []
    Effect(lambda: log.append(c.peek()))
    a.set(2)
    assert log == [2], "reading a computed via peek() must not create a dependency"


# ----------------------------------------------------------------- batching


def test_batch_collapses_multiple_writes() -> None:
    a, b = Signal(1), Signal(2)
    log: list[int] = []
    Effect(lambda: log.append(a.get() + b.get()))
    with batch():
        a.set(10)
        b.set(20)
    assert log == [3, 30], "effect ran per write instead of once"


def test_batch_never_exposes_half_applied_state() -> None:
    a, b = Signal(1), Signal(1)
    seen: list[tuple[int, int]] = []
    Effect(lambda: seen.append((a.get(), b.get())))
    with batch():
        a.set(2)
        b.set(2)
    assert (2, 1) not in seen and (1, 2) not in seen


def test_nested_batches_flush_once_at_the_outermost() -> None:
    s = Signal(0)
    log: list[int] = []
    Effect(lambda: log.append(s.get()))
    with batch():
        s.set(1)
        with batch():
            s.set(2)
        assert log == [0], "inner batch flushed early"
    assert log == [0, 2]


# ------------------------------------------------------------------ dispose


def test_dispose_stops_reruns_and_unsubscribes() -> None:
    s = Signal(1)
    log: list[int] = []
    effect = Effect(lambda: log.append(s.get()))
    effect.dispose()
    s.set(2)
    assert log == [1]
    assert s.subscriber_count == 0
    assert effect.disposed


# ------------------------------------------------------------ thread safety


def test_write_from_another_thread_is_rejected() -> None:
    bind_thread()
    s = Signal(1)
    error: list[Exception] = []

    def worker() -> None:
        try:
            s.set(2)
        except Exception as exc:
            error.append(exc)

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert error and isinstance(error[0], ThreadAffinityError)
    assert s.peek() == 1


def test_write_from_the_engine_thread_is_allowed() -> None:
    bind_thread()
    s = Signal(1)
    s.set(2)
    assert s.peek() == 2


def test_reads_from_other_threads_are_permitted() -> None:
    """Only writes are restricted; a background task may read freely."""
    bind_thread()
    s = Signal(7)
    out: list[int] = []
    t = threading.Thread(target=lambda: out.append(s.peek()))
    t.start()
    t.join()
    assert out == [7]


def test_runaway_effect_cycle_is_reported() -> None:
    """An effect that writes a signal it reads must fail loudly, not recurse
    until the stack dies."""
    a = Signal(0)
    with pytest.raises(RuntimeError, match="did not converge"):
        Effect(lambda: a.set(a.get() + 1))


def test_effect_may_write_a_signal_it_does_not_read() -> None:
    """The common, legitimate case: an effect maintaining derived state."""
    source, mirror = Signal(1), Signal(0)
    Effect(lambda: mirror.set(source.get() * 10))
    assert mirror.peek() == 10
    source.set(5)
    assert mirror.peek() == 50
