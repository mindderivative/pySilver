"""Engine/App shutdown: closing a window from Python code, not just the WM.

`Engine.request_close()`/`App.close()` exist so a Quit button or an Escape
handler can end the application. The one thing they must never do is close
the canvas synchronously from the caller's own stack -- a click handler runs
from inside rendercanvas's own event-dispatch, and destroying the GLFW
window there segfaults the process (confirmed live: exit code 139). These
tests lock in the deferred behaviour instead.
"""

from __future__ import annotations

import pytest

from pysilver import App, Theme

pytestmark = pytest.mark.gpu


def test_request_close_does_not_close_synchronously(offscreen_engine) -> None:
    engine = offscreen_engine()
    engine.request_close()
    assert not engine.canvas.get_closed(), "must defer, not close on the spot"


def test_request_close_closes_on_the_next_draw_frame(offscreen_engine) -> None:
    engine = offscreen_engine()
    engine.request_close()
    engine.draw_frame()
    assert engine.canvas.get_closed()


def test_a_frame_drawn_before_any_close_request_paints_normally(offscreen_engine) -> None:
    """The flag must not misfire for the ordinary, no-close-requested path."""
    engine = offscreen_engine()
    engine.draw_frame()
    assert not engine.canvas.get_closed()


def test_app_close_defers_through_the_engine(app_with_engine: App) -> None:
    app_with_engine.close()
    assert not app_with_engine.engine.canvas.get_closed(), "must defer here too"
    app_with_engine.engine.draw_frame()
    assert app_with_engine.engine.canvas.get_closed()


def test_app_close_is_a_noop_before_an_engine_is_attached() -> None:
    app = App({"name": "root", "widget": "Container"}, theme=Theme())
    app.close()  # must not raise


@pytest.fixture
def app_with_engine(offscreen_engine) -> App:
    app = App({"name": "root", "widget": "Container"}, theme=Theme())
    app.mount()
    engine = offscreen_engine()
    app.attach(engine)
    return app
