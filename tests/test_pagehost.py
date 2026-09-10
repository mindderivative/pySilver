"""PageHost: a single-active-child container, switched by name.

No M3 component -- this is a pySilver-only navigation primitive, not a
Material widget. The gap it closes: the view format has no conditional
include (`spec/include.py` deliberately leaves that out), so there was no
way to say "mount exactly one of these children." Real integration is
exercised through a full `App`, not a bare `build_element(...).layout(...)`,
because the behaviour under test -- `set_ticker`/`mounter` reaching only the
active page -- is driven by `App.mount()`/`App.__init__`, the same reason
`test_terminal.py` does the same thing for its own lifecycle tests.
"""

from __future__ import annotations

import sys

import pytest

from pysilver import App, Signal, Theme
from pysilver.spec import WidgetKind, parse_view
from pysilver.widgets.base import _REGISTRY, create_element

try:
    from pysilver.widgets.terminal import _BITTTY_AVAILABLE, _PTY_AVAILABLE
except ImportError:
    _PTY_AVAILABLE = _BITTTY_AVAILABLE = False

REAL_PTY = _BITTTY_AVAILABLE and _PTY_AVAILABLE and sys.platform != "win32"


def _view(value: str = "{{ page.get() }}", default: str | None = None) -> dict:
    node: dict = {
        "name": "host",
        "widget": "PageHost",
        "value": value,
        "children": [
            {
                "name": "home",
                "widget": "Text",
                "text": "Home page, clicks={{ clicks.get() }}",
            },
            {"name": "other", "widget": "Text", "text": "Other page"},
        ],
    }
    if default is not None:
        node["default"] = default
    return {"name": "root", "widget": "Vertical", "children": [node]}


def _app(value: str = "{{ page.get() }}", default: str | None = None, page: str = "home"):
    a = App(_view(value, default), theme=Theme(dark=True))
    page_signal = Signal(page, name="page")
    clicks = Signal(0, name="clicks")
    a.expose(page=page_signal, clicks=clicks)
    a.mount()
    a.update()
    return a, page_signal, clicks


def test_registered() -> None:
    create_element(parse_view({"name": "x", "widget": "PageHost"}).root)
    assert WidgetKind.PAGE_HOST in _REGISTRY


def test_the_named_page_is_active() -> None:
    app, _, _ = _app(page="home")
    host = app.root.find("host")
    assert [c.name for c in host.children] == ["home"]
    assert app.root.find("home") is not None
    assert app.root.find("other") is None, "the inactive page must not be reachable via find()"


def test_switching_pages_disposes_the_old_one_and_activates_the_new_one() -> None:
    app, page, _ = _app(page="home")
    host = app.root.find("host")
    home = host._find_page("home")
    assert home._ticker is not None, "the active page must have been given a ticker"

    page.set("other")
    app.update()

    assert [c.name for c in host.children] == ["other"]
    assert home._effect is None, "disposing the outgoing page must tear down its subscriptions"


def test_an_unmatched_value_falls_back_to_default() -> None:
    app, _, _ = _app(value="{{ page.get() }}", default="home", page="not-a-real-page")
    host = app.root.find("host")
    assert [c.name for c in host.children] == ["home"]


def test_page_reaches_a_dormant_page_that_find_cannot_see() -> None:
    app, _, _ = _app(page="home")
    host = app.root.find("host")
    assert app.root.find("other") is None, "find() must not reach a dormant page"
    other = host.page("other")
    assert other is not None and other.name == "other"


def test_a_dormant_page_has_no_ticker_until_activated() -> None:
    app, page, _ = _app(page="home")
    host = app.root.find("host")
    other = host._find_page("other")
    assert other._ticker is None, "a page that was never activated must never have been ticked"

    page.set("other")
    app.update()
    assert other._ticker is not None


def test_revisiting_a_page_re_binds_its_own_expressions() -> None:
    """The object survives (never rebuilt), but `mounter()` must run again on
    reactivation, or a revisited page's `{{ }}` bindings stay frozen at
    whatever they last resolved to instead of tracking the signal again."""
    app, page, clicks = _app(page="home")

    page.set("other")
    app.update()
    clicks.set(5)  # changes a signal the (now dormant) home page reads
    app.update()

    page.set("home")
    app.update()
    home = app.root.find("home")
    assert home is not None
    assert home._text == "Home page, clicks=5"


def test_switching_pages_disposed_the_dormant_one_already() -> None:
    """Because `_activate` disposes the outgoing page immediately (rather
    than leaving every visited page alive with a dormant subscription), only
    the currently active page ever holds live state at all -- this is what
    actually prevents the leak `PageHostElement.dispose`'s docstring warns
    about, before `dispose()` is even called on the host itself."""
    app, page, _ = _app(page="home")
    host = app.root.find("host")
    home = host._find_page("home")
    assert home._effect is not None, "home's own {{ clicks.get() }} binding must be live"

    page.set("other")
    app.update()

    assert home._effect is None, "already torn down by the switch, not deferred to host.dispose()"


def test_host_dispose_cleans_up_the_currently_active_page() -> None:
    app, _, _ = _app(page="home")
    host = app.root.find("host")
    home = host._find_page("home")
    assert home._effect is not None

    host.dispose()

    assert home._effect is None


@pytest.mark.skipif(not REAL_PTY, reason="bittty/pexpect not installed, or not POSIX")
def test_a_terminal_page_does_not_spawn_until_its_page_is_active() -> None:
    """The actual point of the whole widget, proven end to end: a live shell
    process only exists while its page is the one showing."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "host",
                "widget": "PageHost",
                "value": "{{ page.get() }}",
                "default": "home",
                "children": [
                    {"name": "home", "widget": "Text", "text": "Home"},
                    {"name": "term", "widget": "Terminal"},
                ],
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    page = Signal("home", name="page")
    app.expose(page=page)
    app.mount()
    app.update()

    host = app.root.find("host")
    terminal = host._find_page("term")
    assert terminal._session is None, "must not have started while its page was never active"

    page.set("term")
    app.update()
    assert terminal._session is not None
    terminal._session.stop()
