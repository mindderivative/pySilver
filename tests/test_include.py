"""View composition: `source:` pulls a subtree in from another file."""

from __future__ import annotations

import textwrap
import time

import pytest

from pysilver import App, Signal, Theme
from pysilver.spec import SpecError, load_view


@pytest.fixture
def views(tmp_path):
    (tmp_path / "row.yaml").write_text(
        textwrap.dedent("""
        params: [label]
        name: item
        widget: ListItem
        text: "{{ label }}"
        style: {width: expand}
    """)
    )
    (tmp_path / "card.yaml").write_text(
        textwrap.dedent("""
        params: [title]
        name: card
        widget: Card
        style: {width: 200, height: 100}
        children:
          - {name: heading, widget: Text, text: "{{ title }}"}
    """)
    )
    return tmp_path


def write(views, body: str, name: str = "view.yaml"):
    (views / name).write_text(textwrap.dedent(body))
    return views / name


def app_for(views, body: str, **signals):
    a = App(write(views, body), theme=Theme(dark=True))
    a.expose(**signals)
    a.mount()
    a.update()
    return a


# ---------------------------------------------------------------- expansion


def test_include_expands_into_the_tree(views) -> None:
    app = app_for(
        views,
        """
        root:
          name: root
          widget: Vertical
          children:
            - {name: r1, source: row.yaml, with: {label: "Hello"}}
    """,
    )
    assert app.root.find("r1").text == "Hello"


def test_a_resolved_include_is_indistinguishable_from_inline(views) -> None:
    """Resolution happens before validation, so nothing downstream can tell."""
    included = app_for(
        views,
        """
        root: {name: root, widget: Vertical, children: [
          {name: r, source: row.yaml, with: {label: "X"}}]}
    """,
    )
    inline = App(
        {
            "name": "root",
            "widget": "Vertical",
            "children": [
                {"name": "r", "widget": "ListItem", "text": "X", "style": {"width": "expand"}}
            ],
        },
        theme=Theme(dark=True),
    )
    inline.mount()
    inline.update()
    assert included.root.find("r").text == inline.root.find("r").text
    assert included.root.find("r").size == inline.root.find("r").size


def test_overlays_can_be_included(views) -> None:
    app = app_for(
        views,
        """
        root: {name: root, widget: Vertical, children: []}
        overlays:
          - {name: dlg, source: card.yaml, with: {title: "Confirm"}}
    """,
    )
    assert app.overlays.find("dlg") is not None
    assert app.overlays.find("dlg.heading").text == "Confirm"


def test_fragments_nest(views) -> None:
    (views / "outer.yaml").write_text(
        textwrap.dedent("""
        params: [name]
        name: outer
        widget: Vertical
        children:
          - {name: inner, source: row.yaml, with: {label: "{{ name }}"}}
    """)
    )
    app = app_for(
        views,
        """
        root: {name: root, widget: Vertical, children: [
          {name: o, source: outer.yaml, with: {name: "nested"}}]}
    """,
    )
    assert app.root.find("o.inner").text == "nested"


# --------------------------------------------------------------- parameters


def test_plain_parameter_becomes_static_text(views) -> None:
    app = app_for(
        views,
        """
        root: {name: root, widget: Vertical, children: [
          {name: r, source: row.yaml, with: {label: "Static"}}]}
    """,
    )
    assert app.root.find("r").text == "Static"


def test_a_binding_passed_as_a_parameter_stays_reactive(views) -> None:
    """Textual substitution is what makes this compose: the fragment ends up
    holding the caller's template, not a snapshot of its value."""
    live = Signal("before")
    app = app_for(
        views,
        """
        root: {name: root, widget: Vertical, children: [
          {name: r, source: row.yaml, with: {label: "{{ live.get() }}"}}]}
    """,
        live=live,
    )
    assert app.root.find("r").text == "before"
    live.set("after")
    assert app.root.find("r").text == "after"


def test_missing_parameter_is_reported(views) -> None:
    with pytest.raises(SpecError, match="missing parameter"):
        app_for(
            views,
            """
            root: {name: root, widget: Vertical, children: [
              {name: r, source: row.yaml}]}
        """,
        )


def test_unknown_parameter_is_reported(views) -> None:
    """Catches a typo'd parameter name rather than ignoring it."""
    with pytest.raises(SpecError, match="unknown parameter"):
        app_for(
            views,
            """
            root: {name: root, widget: Vertical, children: [
              {name: r, source: row.yaml, with: {label: a, labl: b}}]}
        """,
        )


def test_call_site_may_not_carry_other_keys(views) -> None:
    """Parameters are the interface; merging would need murky precedence rules."""
    with pytest.raises(SpecError, match="only `name:` and `with:`"):
        app_for(
            views,
            """
            root: {name: root, widget: Vertical, children: [
              {name: r, source: row.yaml, with: {label: a}, style: {width: 10}}]}
        """,
        )


# ------------------------------------------------------------- id namespacing


def test_the_same_fragment_included_twice_does_not_collide(views) -> None:
    """Reconciliation matches on (id, widget); duplicates would break state."""
    app = app_for(
        views,
        """
        root:
          name: root
          widget: Vertical
          children:
            - {name: a, source: card.yaml, with: {title: "A"}}
            - {name: b, source: card.yaml, with: {title: "B"}}
    """,
    )
    ids = [e.name for e in app.root.walk_elements()]
    assert len(ids) == len(set(ids))
    assert app.root.find("a.heading").text == "A"
    assert app.root.find("b.heading").text == "B"


def test_call_site_name_names_the_fragment_root(views) -> None:
    app = app_for(
        views,
        """
        root: {name: root, widget: Vertical, children: [
          {name: mycard, source: card.yaml, with: {title: "T"}}]}
    """,
    )
    assert app.root.find("mycard") is not None
    assert app.root.find("card") is None, "the fragment's own root id leaked"


def test_an_anchor_naming_a_fragment_local_id_is_namespaced_too(views) -> None:
    """`anchor:` must follow the same namespacing `name:` gets, or two
    included copies would end up pointing at each other's target."""
    (views / "pair.yaml").write_text(
        textwrap.dedent("""
        name: pair
        widget: Vertical
        children:
          - {name: target, widget: Button, text: Open}
          - {name: near, widget: Button, text: Near, style: {anchor: target}}
    """)
    )
    view = load_view(
        write(
            views,
            """
            root:
              name: root
              widget: Vertical
              children:
                - {name: a, source: pair.yaml}
                - {name: b, source: pair.yaml}
        """,
        )
    )
    a_near = next(c for c in view.root.children[0].children if c.name == "a.near")
    b_near = next(c for c in view.root.children[1].children if c.name == "b.near")
    assert a_near.style.anchor == "a.target"
    assert b_near.style.anchor == "b.target"


def test_state_survives_a_reload_of_an_included_tree(views) -> None:
    path = write(
        views,
        """
        root: {name: root, widget: Vertical, children: [
          {name: a, source: card.yaml, with: {title: "A"}}]}
    """,
    )
    app = App(path, theme=Theme(dark=True))
    app.mount()
    app.update()
    card = app.root.find("a")
    card.state.data["keep"] = "yes"
    app.reload(path)
    assert app.root.find("a") is card
    assert app.root.find("a").state.data["keep"] == "yes"


# ----------------------------------------------------------------- failures


def test_cycles_are_reported_with_the_chain(views) -> None:
    (views / "a.yaml").write_text(
        "name: a\nwidget: Vertical\nchildren: [{name: b, source: b.yaml}]"
    )
    (views / "b.yaml").write_text(
        "name: b\nwidget: Vertical\nchildren: [{name: c, source: a.yaml}]"
    )
    with pytest.raises(SpecError, match="include cycle"):
        app_for(
            views,
            """
            root: {name: root, widget: Vertical, children: [{name: x, source: a.yaml}]}
        """,
        )


def test_includes_may_not_escape_the_view_directory(views) -> None:
    """View files are untrusted input."""
    with pytest.raises(SpecError, match="outside the view directory"):
        app_for(
            views,
            """
            root: {name: root, widget: Vertical, children: [
              {name: x, source: ../../../etc/passwd}]}
        """,
        )


def test_missing_file_is_reported(views) -> None:
    with pytest.raises(SpecError, match="not found"):
        app_for(
            views,
            """
            root: {name: root, widget: Vertical, children: [
              {name: x, source: nope.yaml, with: {}}]}
        """,
        )


def test_a_fragment_must_be_a_mapping(views) -> None:
    (views / "list.yaml").write_text("- one\n- two\n")
    with pytest.raises(SpecError, match="must be a mapping"):
        app_for(
            views,
            """
            root: {name: root, widget: Vertical, children: [
              {name: x, source: list.yaml, with: {}}]}
        """,
        )


def test_validation_errors_name_the_entry_file(views) -> None:
    (views / "bad.yaml").write_text("name: b\nwidget: Card\nstyle: {background: not_a_token}\n")
    with pytest.raises(SpecError, match="unknown MD3 token"):
        app_for(
            views,
            """
            root: {name: root, widget: Vertical, children: [
              {name: x, source: bad.yaml, with: {}}]}
        """,
        )


# ---------------------------------------------------------------- hot reload


def test_every_included_file_is_tracked(views) -> None:
    app = app_for(
        views,
        """
        root: {name: root, widget: Vertical, children: [
          {name: r, source: row.yaml, with: {label: "x"}},
          {name: c, source: card.yaml, with: {title: "y"}}]}
    """,
    )
    assert {p.name for p in app.sources} == {"view.yaml", "row.yaml", "card.yaml"}


def test_hot_reload_watches_the_whole_graph(views) -> None:
    """Editing a fragment must reload the view, or `source:` silently breaks
    the framework's best feature."""
    path = write(
        views,
        """
        root: {name: root, widget: Vertical, children: [
          {name: r, source: row.yaml, with: {label: "before"}}]}
    """,
    )
    app = App(path, theme=Theme(dark=True))
    app.mount()
    app.update()
    assert app.root.find("r").text == "before"

    reloader = app.watch()
    try:
        assert {p.name for p in reloader.paths} == {"view.yaml", "row.yaml"}
        time.sleep(0.3)
        # Edit the FRAGMENT, not the entry file.
        (views / "row.yaml").write_text(
            'params: [label]\nid: item\nwidget: ListItem\ntext: "{{ label }}!"\n'
            "style: {width: expand}\n"
        )
        end = time.monotonic() + 5.0
        while time.monotonic() < end:
            if app.poll_reload():
                break
            time.sleep(0.05)
    finally:
        app.unwatch()
    assert app.root.find("r").text == "before!"


def test_dict_views_have_no_sources() -> None:
    app = App({"name": "r", "widget": "Vertical"}, theme=Theme(dark=True))
    assert app.sources == set()


def test_load_view_reports_sources(views) -> None:
    path = write(
        views,
        """
        root: {name: root, widget: Vertical, children: [
          {name: r, source: row.yaml, with: {label: "x"}}]}
    """,
    )
    seen: set = set()
    load_view(path, sources=seen)
    assert {p.name for p in seen} == {"view.yaml", "row.yaml"}


def test_a_view_without_includes_still_works(views) -> None:
    app = app_for(
        views,
        """
        root: {name: root, widget: Vertical, children: [
          {name: t, widget: Text, text: "plain"}]}
    """,
    )
    assert app.root.find("t").text == "plain"
