"""The accessibility tree.

What is tested here is the *semantic* tree -- roles, names, states, structure.
There is no platform bridge, so nothing here proves a screen reader can read a
pySilver application; it proves the tree a bridge would be handed is correct.
That distinction is why the module says so in its first paragraph.
"""

from __future__ import annotations

import pytest

from pysilver import App, Theme
from pysilver.layout import Constraints, Size
from pysilver.runtime.accessibility import ROLES, SILENT, accessibility_tree, role_for
from pysilver.spec import parse_view
from pysilver.spec.models import WidgetKind
from pysilver.widgets import build_element


def tree_of(spec: dict, width: float = 400.0, height: float = 300.0):
    root = build_element(parse_view(spec).root)
    root.layout(Constraints.tight(Size(width, height)))
    return accessibility_tree(root)


# ------------------------------------------------------------------- roles


def test_every_widget_kind_has_a_decided_role() -> None:
    """A kind that is neither mapped nor silenced falls through to "group",
    which is the answer that says nothing. Each should be a decision."""
    undecided = [
        str(kind) for kind in WidgetKind if str(kind) not in ROLES and str(kind) not in SILENT
    ]
    assert undecided == [], f"no role decided for {undecided}"


def test_the_sourced_roles_are_what_m3_says() -> None:
    """Quoted, not chosen: "The role is 'textbox'", "role of 'progressbar'",
    and a navigation item's "The role is 'tab'"."""
    assert role_for("TextField") == "textbox"
    assert role_for("LinearProgress") == "progressbar"
    assert role_for("CircularProgress") == "progressbar"
    assert role_for("NavItem") == "tab"
    assert role_for("Tab") == "tab"


def test_a_navigation_container_is_not_announced() -> None:
    """M3: "the role is not announced". Its items carry the meaning, and a
    reader stopping on the container first would only add noise."""
    assert role_for("NavigationRail") is None


def test_decoration_is_not_announced() -> None:
    assert role_for("Spacer") is None
    assert role_for("Icon") is None, "an icon's meaning is its label, not itself"
    assert role_for("Shape") is None, "a shape has no label and nothing to do"


def test_a_filter_chip_reads_as_a_checkbox_and_the_others_as_buttons() -> None:
    """A filter chip toggles; the rest act on a press. Announcing all four
    variants alike would lose exactly what a user needs to know."""
    view = {
        "name": "root",
        "widget": "Horizontal",
        "children": [
            {"name": "f", "widget": "Chip", "text": "Filter", "style": {"variant": "filter"}},
            {"name": "a", "widget": "Chip", "text": "Assist", "style": {"variant": "assist"}},
        ],
    }
    tree = tree_of(view)
    assert tree.find(name="Filter").role == "checkbox"
    assert tree.find(name="Filter").checked is False
    assert tree.find(name="Assist").role == "button"
    assert tree.find(name="Assist").checked is None, "a button is not unchecked"


# -------------------------------------------------------------------- names


def test_a_node_is_named_by_its_visible_label() -> None:
    tree = tree_of({"name": "go", "widget": "Button", "text": "Confirm"})
    assert tree.find(role="button").name == "Confirm"


def test_the_view_files_name_is_never_announced() -> None:
    """`name:` is a developer handle. Reading out "sw_primary" would be worse
    than silence, so it is carried as `key` for tests and nothing else."""
    tree = tree_of({"name": "sw_primary", "widget": "Button", "text": "Pick"})
    node = tree.find(role="button")
    assert node.name == "Pick"
    assert node.key == "sw_primary"


def test_a_text_fields_supporting_text_is_a_description_not_its_name() -> None:
    """M3: "text field supporting text should have its own accessibility
    label" -- announced separately rather than glued onto the label."""
    tree = tree_of(
        {
            "name": "email",
            "widget": "TextField",
            "text": "Email",
            "value": "ada@example.com",
            "supporting_text": "We never share it",
            "style": {"width": 300},
        }
    )
    field = tree.find(role="textbox")
    assert field.name == "Email"
    assert field.description == "We never share it"
    assert field.value == "ada@example.com"


# ------------------------------------------------------------------- states


def test_checkable_and_uncheckable_are_distinguishable() -> None:
    view = {
        "name": "root",
        "widget": "Horizontal",
        "children": [
            {"name": "c", "widget": "Checkbox", "value": "true"},
            {"name": "b", "widget": "Button", "text": "Go"},
        ],
    }
    tree = tree_of(view)
    assert tree.find(role="checkbox").checked is True
    assert tree.find(role="button").checked is None


def test_selected_and_unselected_are_distinguishable() -> None:
    view = {
        "name": "root",
        "widget": "Horizontal",
        "children": [
            {
                "name": "rail",
                "widget": "NavigationRail",
                "value": "home",
                "children": [
                    {
                        "name": "home",
                        "widget": "NavItem",
                        "icon": "home",
                        "label": "Home",
                    },
                    {
                        "name": "settings",
                        "widget": "NavItem",
                        "icon": "settings",
                        "label": "Settings",
                    },
                ],
            },
            {"name": "go", "widget": "Button", "text": "Go"},
        ],
    }
    tree = tree_of(view)
    assert tree.find(name="Home").selected is True
    assert tree.find(name="Settings").selected is False
    assert tree.find(role="button", name="Go").selected is None, "a button is not unselected"


def test_disabled_is_reported() -> None:
    tree = tree_of({"name": "b", "widget": "Button", "text": "Go", "disabled": "true"})
    assert tree.find(role="button").disabled is True


def test_focus_is_reported() -> None:
    root = build_element(parse_view({"name": "b", "widget": "Button", "text": "Go"}).root)
    root.layout(Constraints.tight(Size(400.0, 300.0)))
    root.state.focused = True
    assert accessibility_tree(root).find(role="button").focused is True


def test_a_progress_indicator_reports_its_value() -> None:
    tree = tree_of({"name": "p", "widget": "LinearProgress", "value": "0.25"})
    assert tree.find(role="progressbar").value == "0.25"


# ---------------------------------------------------------------- structure


def test_silent_nodes_do_not_bury_their_children() -> None:
    """A Spacer disappears; a rail's items are lifted to where the rail was.
    Keeping an unannounced parent as a level would make a reader walk through
    nothing to reach something."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {"name": "gap", "widget": "Spacer", "style": {"height": 8}},
            {
                "name": "rail",
                "widget": "NavigationRail",
                "children": [
                    {"name": "home", "widget": "NavItem", "icon": "home", "label": "Home"}
                ],
            },
        ],
    }
    tree = tree_of(view)
    assert "tab" in [node.role for node in tree.walk()], "the nav item survived"
    assert tree.find(name="Home") in tree.children, "and was lifted to the rail's place"


def test_an_icon_name_is_never_announced_as_a_label() -> None:
    """For icon-bearing controls `icon:` is a Material Symbols glyph name,
    separate from `label:`. A nav item said "home" rather than "Home" until
    this distinction existed, which is a bug nobody sees until they listen
    to it."""
    view = {
        "name": "root",
        "widget": "Horizontal",
        "children": [
            {"name": "n", "widget": "NavItem", "icon": "home", "label": "Home"},
            {"name": "i", "widget": "IconButton", "icon": "chevron_right"},
        ],
    }
    tree = tree_of(view)
    assert tree.find(role="tab").name == "Home"
    assert tree.find(key="i").name == "", (
        "an icon-only control with no label: has no name to give, and "
        "reporting none is better than reading 'chevron_right' at somebody"
    )


def test_find_locates_a_node_by_role_and_name() -> None:
    """The everyday use: ask for the button called Confirm instead of for a
    rectangle at some coordinate."""
    view = {
        "name": "root",
        "widget": "Horizontal",
        "children": [
            {"name": "a", "widget": "Button", "text": "Cancel"},
            {"name": "b", "widget": "Button", "text": "Confirm"},
        ],
    }
    tree = tree_of(view)
    assert tree.find(role="button", name="Confirm").key == "b"
    assert tree.find(role="button", name="Nope") is None


def test_bounds_come_from_the_laid_out_element() -> None:
    """A bridge has to tell a magnifier where a thing is, so the rect must be
    the real one rather than a placeholder. Nested, because a root element is
    stretched to the window by its tight constraints."""
    tree = tree_of(
        {
            "name": "root",
            "widget": "Horizontal",
            "children": [{"name": "b", "widget": "Button", "text": "Go", "style": {"width": 120}}],
        }
    )
    assert tree.find(role="button").bounds.width == 120.0


# ----------------------------------------------------------------- overlays


def test_a_visible_overlay_is_appended_to_the_root() -> None:
    """A dialog is not a child of what it covers. It goes last, where a reader
    reaches it, and its modal flag is what says to stay there."""
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "children": [{"name": "b", "widget": "Button", "text": "Open"}],
        },
        "overlays": [
            {
                "name": "d",
                "widget": "Dialog",
                "text": "Delete this?",
                "open": "true",
                "style": {"modal": True},
                "children": [{"name": "ok", "widget": "Button", "text": "OK"}],
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    app.mount()
    app.update()
    dialog = app.accessibility_tree().find(role="dialog")
    assert dialog is not None
    assert dialog.name == "Delete this?"
    assert dialog.modal is True
    assert dialog.find(role="button", name="OK") is not None


def test_a_closed_overlay_is_absent_entirely() -> None:
    """Not "present but hidden": a reader must not reach a dialog that is
    not up."""
    view = {
        "root": {"name": "root", "widget": "Vertical", "children": []},
        "overlays": [{"name": "d", "widget": "Dialog", "text": "Nope", "open": "false"}],
    }
    app = App(view, theme=Theme(dark=True))
    app.mount()
    app.update()
    assert app.accessibility_tree().find(role="dialog") is None


# ------------------------------------------------------------------- limits


def test_there_is_no_platform_bridge_and_the_seam_says_so() -> None:
    """Pinned deliberately. If a bridge ever lands this should fail and be
    rewritten -- until then nothing may imply one exists."""
    from pysilver.runtime.accessibility import AccessibleNode, Bridge

    with pytest.raises(NotImplementedError):
        Bridge().update(AccessibleNode(role="group"))
