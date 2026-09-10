"""ViewModels: one view file, one ViewModel.

Handlers and `{{ }}` names used to live in a single flat namespace shared by
every node however deep the include graph went, so a fragment could not own
logic without putting it in the application's namespace. These cover the
scoping that fixes it, and the two ways it could quietly do nothing instead:
binding a name that resolves globally anyway, and enforcing a convention that
is never actually checked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from counter_ViewModel import Counter
from pysilver import App, Signal, Theme, ViewModel, ViewModelError


def write_view(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def gallery_view(tmp_path: Path) -> Path:
    write_view(
        tmp_path,
        "panel_View.yaml",
        "params: [label]\n"
        "name: panel\n"
        "widget: Button\n"
        'text: "{{ label }} {{ count.get() }}"\n'
        "handlers: {on_click: bump}\n",
    )
    return write_view(
        tmp_path,
        "screen_View.yaml",
        "root:\n"
        "  name: root\n"
        "  widget: Vertical\n"
        "  children:\n"
        "    - {name: a, source: panel_View.yaml, with: {label: A}}\n"
        "    - {name: b, source: panel_View.yaml, with: {label: B}}\n",
    )


# ------------------------------------------------------------------ scoping


def test_a_fragment_resolves_against_its_own_view_model(tmp_path: Path) -> None:
    """The point of the whole thing: `panel_View.yaml` names `count` and `bump`
    without the application knowing either exists."""
    app = App(gallery_view(tmp_path), theme=Theme(dark=True))
    counter = app.bind_view_model("panel_View.yaml", Counter(7))
    app.mount()
    app.update()

    button = app.root.find("a")
    assert "7" in button.text
    button.handlers["on_click"](None)
    assert counter.count.peek() == 8


def test_one_view_file_means_one_view_model(tmp_path: Path) -> None:
    """Including a fragment twice gives two copies of the view and *one*
    ViewModel behind them. That is the chosen semantics, so it is pinned:
    per-instance state belongs on the widget, not here."""
    app = App(gallery_view(tmp_path), theme=Theme(dark=True))
    counter = app.bind_view_model("panel_View.yaml", Counter())
    app.mount()
    app.update()

    app.root.find("a").handlers["on_click"](None)
    assert counter.count.peek() == 1
    app.root.find("b").handlers["on_click"](None)
    assert counter.count.peek() == 2, "the two includes shared one ViewModel"


def test_a_view_model_shadows_the_application(tmp_path: Path) -> None:
    """Local wins, so a fragment can name things without checking what the rest
    of the application already calls them."""
    app = App(gallery_view(tmp_path), theme=Theme(dark=True))
    app.expose(count=Signal(99, name="global"))
    app.bind_view_model("panel_View.yaml", Counter(1))
    app.mount()
    app.update()
    assert "1" in app.root.find("a").text


def test_a_view_without_a_view_model_still_sees_the_application(tmp_path: Path) -> None:
    """Fallback matters: an application-wide signal has to reach a nested view
    without being threaded through every include."""
    view = write_view(
        tmp_path,
        "plain.yaml",
        'root: {name: root, widget: Text, text: "{{ shared.get() }}"}\n',
    )
    app = App(view, theme=Theme(dark=True))
    app.expose(shared=Signal("hello", name="shared"))
    app.mount()
    app.update()
    assert app.root.find("root").text == "hello"


def test_every_node_records_the_file_it_was_written_in(tmp_path: Path) -> None:
    """The mechanism underneath. Includes are flattened into one tree, and this
    is what survives that."""
    app = App(gallery_view(tmp_path), theme=Theme(dark=True))
    by_view: dict[str | None, int] = {}
    for node in app.view.root.walk():
        by_view[node.view] = by_view.get(node.view, 0) + 1
    assert by_view == {"screen_View.yaml": 1, "panel_View.yaml": 2}


# --------------------------------------------------------------- convention


def test_the_view_must_carry_the_view_suffix(tmp_path: Path) -> None:
    """Enforced rather than suggested: binding is explicit, so a convention
    nobody checks is a convention nobody follows."""
    view = write_view(tmp_path, "plain.yaml", "root: {name: r, widget: Text}\n")
    app = App(view, theme=Theme(dark=True))
    with pytest.raises(ViewModelError, match=r"_View\.yaml"):
        app.bind_view_model("plain.yaml", Counter())


def test_the_view_model_must_live_in_a_viewmodel_module(tmp_path: Path) -> None:
    """This file is deliberately `test_view_models.py`, not `test_viewmodel.py`
    -- the latter ends with `_viewmodel.py` and would satisfy the very rule
    being tested. It did, on the first attempt."""
    view = write_view(tmp_path, "x_View.yaml", "root: {name: r, widget: Text}\n")
    app = App(view, theme=Theme(dark=True))

    class Local(ViewModel):
        """Defined in this file, which is not a `*_ViewModel.py` module."""

    with pytest.raises(ViewModelError, match=r"_ViewModel\.py"):
        app.bind_view_model("x_View.yaml", Local())


# ------------------------------------------------------------------- limits


def test_a_view_cannot_reach_the_app_through_its_view_model() -> None:
    """`app` is there for the few things that are genuinely the application's,
    and it must not be reachable from a view file -- expressions run on
    untrusted input, and handing them the App object would undo that."""
    counter = Counter()
    assert "app" not in counter.names()
    assert "app" not in counter.handlers()
    assert "names" not in counter.handlers(), "the base class is not a handler surface"


def test_an_unbound_view_model_says_so_rather_than_returning_none() -> None:
    with pytest.raises(ViewModelError, match="not bound"):
        _ = Counter().app


def test_names_and_handlers_split_by_what_they_are() -> None:
    counter = Counter()
    assert set(counter.names()) == {"count"}
    assert set(counter.handlers()) == {"bump"}
