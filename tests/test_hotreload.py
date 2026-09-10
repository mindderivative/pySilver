"""Hot reload: watching, marshalling to the engine thread, and surviving bad edits."""

from __future__ import annotations

import threading
import time

import pytest
import yaml

from pysilver import App, Theme
from pysilver.runtime.hotreload import HotReloader

BASE = {
    "name": "root",
    "widget": "Vertical",
    "style": {"background": "surface", "padding": 8},
    "children": [
        {
            "name": "card",
            "widget": "Container",
            "style": {"width": 100, "height": 40, "background": "primary"},
        }
    ],
}


@pytest.fixture
def view(tmp_path):
    import copy

    path = tmp_path / "view.yaml"
    path.write_text(yaml.safe_dump(copy.deepcopy(BASE)))
    return path


def wait_for(predicate, timeout: float = 5.0, step: float = 0.05) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(step)
    return False


# ------------------------------------------------------------- the watcher


def test_watcher_starts_and_stops(view) -> None:
    r = HotReloader([view])
    assert not r.running
    r.start()
    assert r.running
    r.stop()
    assert not r.running


def test_missing_file_is_rejected_at_start(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="cannot watch"):
        HotReloader([tmp_path / "nope.yaml"]).start()


def test_watcher_runs_on_a_background_thread(view) -> None:
    """It must never touch the trees itself (ARCHITECTURE.md 5.11).

    Scoped to this reloader rather than the global thread list: another test's
    watcher shutting down concurrently would otherwise make this order-dependent.
    """
    reloader = HotReloader([view])
    with reloader:
        assert reloader.running
        assert "pysilver-hotreload" in [t.name for t in threading.enumerate()]
    assert not reloader.running


def test_detects_a_real_edit(view) -> None:
    with HotReloader([view]) as r:
        time.sleep(0.3)
        view.write_text(view.read_text() + "\n# touched\n")
        assert wait_for(lambda: r.pending > 0), "no change detected"
        events = r.drain()
        assert events and events[0].path == view.resolve()
        assert r.pending == 0, "drain should empty the queue"


def test_post_injects_without_the_filesystem(view) -> None:
    r = HotReloader([view])
    r.post(view)
    assert r.pending == 1
    assert r.drain()[0].change == "modified"


def test_apply_reports_errors_without_raising(view) -> None:
    r = HotReloader([view])
    r.post(view)

    def boom(_path):
        raise ValueError("bad view")

    events = r.apply(boom)
    assert events[0].error == "bad view"


def test_apply_skips_deleted_files(view) -> None:
    r = HotReloader([view])
    r.post(view, change="deleted")

    calls: list[object] = []
    events = r.apply(calls.append)
    assert calls == [], "a deleted file must not be reloaded"
    assert events[0].error is None


def test_drain_is_safe_while_the_watcher_runs(view) -> None:
    with HotReloader([view]) as r:
        for _ in range(20):
            r.drain()
        assert r.pending == 0


# ------------------------------------------------------------ App integration


def test_reload_applies_a_valid_edit(view) -> None:
    import copy

    app = App(view, theme=Theme(dark=True))
    app.mount()
    assert app.root.find("card").style.width.value == 100

    app.watch()
    try:
        time.sleep(0.3)  # let the watcher settle before touching the file
        changed = copy.deepcopy(BASE)
        changed["children"][0]["style"]["width"] = 250
        view.write_text(yaml.safe_dump(changed))
        assert wait_for(lambda: app.poll_reload() > 0), "reload never applied"
    finally:
        app.unwatch()
    assert app.root.find("card").style.width.value == 250


def test_reload_preserves_runtime_state(view) -> None:
    """The whole point: editing a view file must not wipe state."""
    import copy

    app = App(view, theme=Theme(dark=True))
    app.mount()
    card = app.root.find("card")
    card.state.focused = True
    card.state.data["draft"] = "unsent"

    changed = copy.deepcopy(BASE)
    changed["children"][0]["style"]["background"] = "error"
    app.reload(changed)

    survivor = app.root.find("card")
    assert survivor is card
    assert survivor.state.focused
    assert survivor.state.data["draft"] == "unsent"


def test_invalid_view_is_rejected_and_the_app_survives(view) -> None:
    """Editors save partial files constantly; a bad view must not kill the app."""
    app = App(view, theme=Theme(dark=True))
    app.mount()
    card = app.root.find("card")

    app.watch()
    try:
        time.sleep(0.3)  # let the watcher settle before touching the file
        view.write_text("id: root\nwidget: Vertical\nstyle: {background: not_a_token}\n")
        assert wait_for(lambda: (app.poll_reload(), app.reload_errors)[1])
    finally:
        app.unwatch()

    assert app.reload_errors, "invalid view was not reported"
    assert "unknown MD3 token" in app.reload_errors[0]
    assert app.root.find("card") is card, "previous tree was destroyed"


def test_watching_a_dict_view_is_an_error() -> None:
    app = App(BASE, theme=Theme(dark=True))
    with pytest.raises(ValueError, match="not loaded from a file"):
        app.watch()


def test_poll_is_a_noop_without_a_watcher(view) -> None:
    app = App(view, theme=Theme(dark=True))
    app.mount()
    assert app.poll_reload() == 0


def test_view_path_is_exposed(view) -> None:
    assert App(view, theme=Theme(dark=True)).view_path == view
    assert App(BASE, theme=Theme(dark=True)).view_path is None
