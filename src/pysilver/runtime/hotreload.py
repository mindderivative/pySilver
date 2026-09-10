"""Hot reload: watch view files, reload without losing runtime state.

The watcher runs on a background thread and **never touches the trees**
(ARCHITECTURE.md 5.11). It only enqueues paths; the engine thread drains the
queue and performs the reload, which keeps the single-threaded ownership rule
in ARCHITECTURE.md 8 intact.

A validation failure must not kill the application. Editors save partial files
constantly, so a malformed view is logged and the previous tree keeps running.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from watchfiles import Change, watch

__all__ = ["HotReloader", "ReloadEvent"]

log: Final = logging.getLogger("pysilver.hotreload")

#: Group rapid successive writes. Editors frequently save via write-then-rename,
#: producing several events for one logical edit. watchfiles' own default of
#: 1600 ms is far too slow to feel like hot reload.
DEBOUNCE_MS: Final = 100

#: How often the watch loop checks the stop event, so stop() returns promptly.
POLL_MS: Final = 200


@dataclass(slots=True)
class ReloadEvent:
    """A file change awaiting the engine thread."""

    path: Path
    change: str
    error: str | None = field(default=None)


class HotReloader:
    """Watches files and hands changes to the engine thread.

    Not started automatically -- an application opts in, because a file watcher
    is unwanted overhead in a shipped app.
    """

    __slots__ = (
        "_lock",
        "_pending",
        "_seen",
        "_stop",
        "_thread",
        "paths",
    )

    def __init__(self, paths: Iterable[str | Path]) -> None:
        self.paths = [Path(p).resolve() for p in paths]
        self._pending: list[ReloadEvent] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen = 0

    # ------------------------------------------------------------ lifecycle

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def events_seen(self) -> int:
        """Total changes observed, including ones already drained."""
        return self._seen

    def start(self) -> None:
        if self.running:
            return
        missing = [p for p in self.paths if not p.exists()]
        if missing:
            raise FileNotFoundError(f"cannot watch missing files: {missing}")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pysilver-hotreload", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def __enter__(self) -> HotReloader:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # ------------------------------------------------------- watcher thread

    def _run(self) -> None:
        try:
            for batch in watch(
                *self.paths,
                stop_event=self._stop,
                debounce=DEBOUNCE_MS,
                step=10,
                rust_timeout=POLL_MS,
                yield_on_timeout=True,
                raise_interrupt=False,
            ):
                if not batch:
                    continue  # timeout tick; lets the stop event be checked
                self._enqueue(batch)
        except Exception:  # pragma: no cover - watcher must never crash the app
            log.exception("hot reload watcher stopped unexpectedly")

    def _enqueue(self, batch: set[tuple[Change, str]]) -> None:
        # Collapse a batch to one event per path: several writes to the same
        # file are one logical edit, and reloading twice would be wasted work.
        latest: dict[Path, str] = {}
        for change, raw in batch:
            latest[Path(raw).resolve()] = str(change.name)
        with self._lock:
            for path, kind in latest.items():
                self._pending.append(ReloadEvent(path, kind))
                self._seen += 1

    # -------------------------------------------------------- engine thread

    def drain(self) -> list[ReloadEvent]:
        """Take pending events. Called from the engine thread only."""
        with self._lock:
            events, self._pending = self._pending, []
        return events

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    def post(self, path: str | Path, change: str = "modified") -> None:
        """Inject an event manually. Used by tests and by a manual reload key."""
        with self._lock:
            self._pending.append(ReloadEvent(Path(path).resolve(), change))
            self._seen += 1

    def apply(self, reload: Callable[[Path], object]) -> list[ReloadEvent]:
        """Drain and apply *reload* to each changed path.

        A failing reload is recorded on the event and logged, never raised: a
        view file saved mid-edit is routinely invalid, and killing the running
        application over it would make the feature unusable.
        """
        events = self.drain()
        for event in events:
            if event.change == "deleted":
                log.warning("watched view file disappeared: %s", event.path)
                continue
            try:
                reload(event.path)
            except Exception as exc:
                event.error = str(exc)
                log.warning("hot reload rejected %s:\n%s", event.path, exc)
        return events
