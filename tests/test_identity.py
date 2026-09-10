"""Node identity: positional `id`, optional `name`, repeatable `classes`.

Three separate concerns that used to be one overloaded field:

* ``id``      -- positional, assigned by the loader, never authored
* ``name``    -- optional, unique, the designer's handle and the reconciliation key
* ``classes`` -- optional, repeatable, categories for the theme engine
"""

from __future__ import annotations

import pytest

from pysilver import App, Theme
from pysilver.spec import SpecError, parse_view
from pysilver.tree.reconcile import reconcile
from pysilver.widgets import build_element


def spec(**kw):
    return parse_view({"widget": "Vertical", **kw}).root


def app_for(view):
    a = App(view, theme=Theme(dark=True))
    a.mount()
    a.update()
    return a


# ------------------------------------------------------------ positional id


def test_ids_are_assigned_automatically() -> None:
    """Authors never write an id."""
    root = spec(children=[{"widget": "Text", "text": "a"}, {"widget": "Text", "text": "b"}])
    assert root.id == "/"
    assert [c.id for c in root.children] == ["/0/", "/1/"]


def test_ids_encode_the_path() -> None:
    root = spec(children=[{"widget": "Vertical", "children": [{"widget": "Text"}]}])
    assert root.children[0].children[0].id == "/0/0/"


def test_ids_cannot_collide_with_a_name() -> None:
    """`/` is not permitted in a name, so the two namespaces never overlap."""
    with pytest.raises(SpecError):
        parse_view({"widget": "Text", "name": "a/b"})


def test_overlay_ids_are_distinct_from_root_ids() -> None:
    view = parse_view(
        {
            "root": {"widget": "Vertical"},
            "overlays": [{"widget": "Card", "style": {"width": 10, "height": 10}}],
        }
    )
    assert view.root.id == "/"
    assert view.overlays[0].id == "@0/"


def test_authoring_an_id_is_rejected() -> None:
    """`id` is machinery; writing one is a mistake worth reporting."""
    with pytest.raises(SpecError, match=r"Extra inputs|id"):
        parse_view({"widget": "Text", "id": "mine", "extra_check": 1})


# -------------------------------------------------------------------- name


def test_name_is_optional() -> None:
    assert spec(children=[{"widget": "Text"}]).children[0].name is None


def test_find_matches_the_name() -> None:
    app = app_for(
        {
            "widget": "Vertical",
            "children": [
                {"widget": "Text", "text": "no"},
                {"name": "target", "widget": "Text", "text": "yes"},
            ],
        }
    )
    assert app.root.find("target").text == "yes"


def test_find_returns_none_for_an_unnamed_node() -> None:
    app = app_for({"widget": "Vertical", "children": [{"widget": "Text", "text": "x"}]})
    assert app.root.find("x") is None


@pytest.mark.parametrize("bad", ["1abc", "has space", "a/b", "has.trailing."])
def test_invalid_names_are_rejected(bad: str) -> None:
    with pytest.raises(SpecError):
        parse_view({"widget": "Text", "name": bad})


def test_dotted_names_are_allowed_for_include_scoping() -> None:
    assert parse_view({"widget": "Text", "name": "dialog.heading"}).root.name


# ----------------------------------------------------------------- classes


def test_classes_accept_a_space_separated_string() -> None:
    assert spec(children=[{"widget": "Text", "classes": "a b"}]).children[0].classes == (
        "a",
        "b",
    )


def test_classes_accept_a_list() -> None:
    assert spec(children=[{"widget": "Text", "classes": ["a", "b"]}]).children[0].classes == (
        "a",
        "b",
    )


def test_classes_default_to_empty() -> None:
    assert spec(children=[{"widget": "Text"}]).children[0].classes == ()


def test_classes_repeat_across_nodes() -> None:
    """Unlike a name, several nodes may share a class -- that is the point."""
    app = app_for(
        {
            "widget": "Vertical",
            "children": [
                {"widget": "Button", "text": "a", "classes": "action"},
                {"widget": "Button", "text": "b", "classes": "action primary"},
                {"widget": "Text", "text": "c"},
            ],
        }
    )
    assert len(app.root.find_all("action")) == 2
    assert len(app.root.find_all("primary")) == 1
    assert app.root.find_all("nonexistent") == []


def test_has_class() -> None:
    app = app_for(
        {
            "widget": "Vertical",
            "children": [{"name": "b", "widget": "Button", "text": "x", "classes": "action"}],
        }
    )
    assert app.root.find("b").has_class("action")
    assert not app.root.find("b").has_class("other")


@pytest.mark.parametrize("bad", ["has space!", "1bad"])
def test_invalid_class_names_are_rejected(bad: str) -> None:
    with pytest.raises(SpecError, match="invalid class name"):
        parse_view({"widget": "Text", "classes": [bad]})


# --------------------------------------------------- reconciliation identity


CHILD_A = {"name": "a", "widget": "Container", "style": {"width": 10, "height": 10}}
CHILD_B = {"name": "b", "widget": "Container", "style": {"width": 20, "height": 20}}
ANON_A = {"widget": "Container", "style": {"width": 10, "height": 10}}
ANON_B = {"widget": "Container", "style": {"width": 20, "height": 20}}


def test_a_named_node_survives_a_reorder() -> None:
    """A name is stable across a move, so state follows the node."""
    root = build_element(spec(children=[CHILD_A, CHILD_B]))
    a = root.find("a")
    a.state.data["keep"] = 1
    result, stats = reconcile(root, spec(children=[CHILD_B, CHILD_A]))
    assert [c.name for c in result.children] == ["b", "a"]
    assert result.find("a") is a
    assert result.find("a").state.data["keep"] == 1
    assert stats.created == 0 and stats.disposed == 0


def test_an_unnamed_node_keeps_state_by_position_not_content() -> None:
    """The precise cost of leaving a node unnamed.

    On a reorder the element at index 0 is reused and simply given the other
    node's spec -- so its state stays with the *slot*, not with the content
    that moved. For a Divider that is meaningless; for anything holding focus
    or text it is why you give it a name.
    """
    root = build_element(spec(children=[ANON_A, ANON_B]))
    slot0 = root.children[0]
    slot0.state.data["keep"] = 1

    result, stats = reconcile(root, spec(children=[ANON_B, ANON_A]))

    # Same element object in slot 0 ...
    assert result.children[0] is slot0
    # ... still carrying the state ...
    assert result.children[0].state.data["keep"] == 1
    # ... but now rendering the node that moved into that slot.
    assert result.children[0].style.width.value == 20  # ANON_B's width
    assert stats.created == 0


def test_an_unnamed_node_survives_when_position_is_unchanged() -> None:
    root = build_element(spec(children=[ANON_A]))
    first = root.children[0]
    first.state.data["keep"] = 1
    changed = {"widget": "Container", "style": {"width": 99, "height": 10}}
    result, _ = reconcile(root, spec(children=[changed]))
    assert result.children[0] is first
    assert result.children[0].state.data["keep"] == 1


def test_naming_only_some_children_still_works() -> None:
    root = build_element(spec(children=[ANON_A, CHILD_B]))
    b = root.find("b")
    b.state.data["keep"] = 1
    result, _ = reconcile(root, spec(children=[CHILD_B, ANON_A]))
    assert result.find("b") is b
    assert result.find("b").state.data["keep"] == 1


# ------------------------------------------------------------- integration


def test_anchor_resolves_a_name() -> None:
    app = App(
        {
            "root": {
                "widget": "Vertical",
                "style": {"background": "surface", "padding": 10},
                "children": [
                    {
                        "name": "trigger",
                        "widget": "Button",
                        "text": "x",
                        "style": {"width": 100, "height": 40},
                    }
                ],
            },
            "overlays": [
                {
                    "widget": "Card",
                    "open": "true",
                    "style": {
                        "width": 120,
                        "height": 60,
                        "placement": "anchor",
                        "anchor": "trigger",
                    },
                }
            ],
        },
        theme=Theme(dark=True),
    )
    app.mount()
    app.update()
    anchor = app.root.find("trigger").absolute_rect()
    assert app.overlays.visible()[0].rect().y >= anchor.bottom


def test_selection_container_matches_a_child_name() -> None:
    app = app_for(
        {
            "widget": "Vertical",
            "children": [
                {
                    "widget": "Tabs",
                    "value": "second",
                    "style": {"width": "expand"},
                    "children": [
                        {"name": "first", "widget": "Tab", "text": "One"},
                        {"name": "second", "widget": "Tab", "text": "Two"},
                    ],
                }
            ],
        }
    )
    assert app.root.find("second").selected
    assert not app.root.find("first").selected


def test_duplicate_names_are_rejected_at_load() -> None:
    """A name is a lookup key, so a collision must fail loudly, not silently."""
    with pytest.raises(SpecError, match="duplicate name 'dup'"):
        parse_view(
            {
                "root": {
                    "widget": "Vertical",
                    "children": [
                        {"name": "dup", "widget": "Container"},
                        {"name": "dup", "widget": "Container"},
                    ],
                }
            }
        )


def test_duplicate_name_error_names_both_positions() -> None:
    with pytest.raises(SpecError, match=r"/0/ and /1/|/1/ and /0/"):
        parse_view(
            {
                "root": {
                    "widget": "Vertical",
                    "children": [
                        {"name": "dup", "widget": "Container"},
                        {"name": "dup", "widget": "Container"},
                    ],
                }
            }
        )


def test_a_name_may_repeat_across_separate_views() -> None:
    """Uniqueness is per-view, not global -- two views may both have a 'root'."""
    for _ in range(2):
        assert parse_view({"name": "root", "widget": "Container"}).root.name == "root"
