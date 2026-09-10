"""The stylesheet: selectors, cascade, and where it is resolved.

`classes` was reserved as a selector target when node identity was split; this
is its consumer. Resolution happens once at load, so the tests assert on the
parsed spec rather than on rendered output -- if the spec is right, everything
downstream reads `style` exactly as it always has.
"""

from __future__ import annotations

import pytest

from pysilver import App, Settings, Theme
from pysilver.paint import DisplayList
from pysilver.spec import SpecError, parse_view
from pysilver.spec.models import StyleRule, StyleSpec, WidgetKind


def view(styles, children, **root):
    return parse_view(
        {
            "styles": styles,
            "root": {"name": "root", "widget": "Vertical", "children": children, **root},
        }
    )


def styled(styles, node) -> StyleSpec:
    return view(styles, [node]).root.children[0].style


# --------------------------------------------------------------- selectors


def test_a_widget_selector_matches_by_kind() -> None:
    node = {"name": "b", "widget": "Button"}
    assert styled([{"widget": "Button", "style": {"height": 40}}], node).height.value == 40
    assert styled([{"widget": "Card", "style": {"height": 40}}], node).height.kind == "auto"


def test_a_class_selector_matches_a_carried_class() -> None:
    rules = [{"classes": "action", "style": {"height": 44}}]
    assert styled(rules, {"name": "a", "widget": "Button", "classes": "action"}).height.value == 44
    assert styled(rules, {"name": "a", "widget": "Button"}).height.kind == "auto"


def test_a_multi_class_selector_requires_all_of_them() -> None:
    rules = [{"classes": "action primary", "style": {"height": 44}}]
    both = {"name": "a", "widget": "Button", "classes": "action primary"}
    one = {"name": "a", "widget": "Button", "classes": "action"}
    assert styled(rules, both).height.value == 44
    assert styled(rules, one).height.kind == "auto", "matched on a partial class list"


def test_a_name_selector_matches_one_node() -> None:
    rules = [{"name": "save", "style": {"width": 200}}]
    assert styled(rules, {"name": "save", "widget": "Button"}).width.value == 200
    assert styled(rules, {"name": "other", "widget": "Button"}).width.kind == "auto"


def test_selectors_combine_within_one_rule() -> None:
    rules = [{"widget": "Button", "classes": "action", "style": {"height": 44}}]
    assert styled(rules, {"name": "a", "widget": "Button", "classes": "action"}).height.value == 44
    assert styled(rules, {"name": "a", "widget": "Card", "classes": "action"}).height.kind == "auto"


def test_a_rule_with_no_selector_is_a_baseline() -> None:
    rules = [{"style": {"corner_radius": 4}}]
    for kind in ("Button", "Card", "Container"):
        assert styled(rules, {"name": "n", "widget": kind}).corner_radius[0] == 4


# ----------------------------------------------------------------- cascade


def test_a_class_beats_a_widget_kind() -> None:
    rules = [
        {"widget": "Button", "style": {"height": 40}},
        {"classes": "action", "style": {"height": 44}},
    ]
    node = {"name": "a", "widget": "Button", "classes": "action"}
    assert styled(rules, node).height.value == 44


def test_a_name_beats_any_number_of_classes() -> None:
    rules = [
        {"classes": "a b c", "style": {"height": 44}},
        {"name": "save", "style": {"height": 60}},
    ]
    node = {"name": "save", "widget": "Button", "classes": "a b c"}
    assert styled(rules, node).height.value == 60


def test_more_classes_beat_fewer() -> None:
    rules = [
        {"classes": "action", "style": {"background": "secondary_container"}},
        {"classes": "action primary", "style": {"background": "primary"}},
    ]
    node = {"name": "a", "widget": "Button", "classes": "action primary"}
    assert styled(rules, node).background == "primary"


def test_document_order_breaks_a_tie() -> None:
    """Equal specificity: the later rule wins, as in CSS."""
    rules = [
        {"widget": "Button", "style": {"height": 40}},
        {"widget": "Button", "style": {"height": 50}},
    ]
    assert styled(rules, {"name": "a", "widget": "Button"}).height.value == 50


def test_an_inline_style_beats_every_rule() -> None:
    """A view file is more specific than any sheet."""
    rules = [{"name": "a", "style": {"height": 44}}]
    node = {"name": "a", "widget": "Button", "style": {"height": 99}}
    assert styled(rules, node).height.value == 99


def test_rules_merge_rather_than_replace() -> None:
    """Each rule contributes only the fields it sets, so two rules compose."""
    rules = [
        {"widget": "Button", "style": {"height": 40}},
        {"classes": "wide", "style": {"width": 200}},
    ]
    style = styled(rules, {"name": "a", "widget": "Button", "classes": "wide"})
    assert style.height.value == 40
    assert style.width.value == 200


def test_an_unset_field_in_a_rule_imposes_nothing() -> None:
    """The whole cascade depends on this: a rule that mentions only `height`
    must not also apply every StyleSpec default and erase the rules before it."""
    rules = [
        {"widget": "Button", "style": {"background": "primary"}},
        {"widget": "Button", "style": {"height": 40}},
    ]
    style = styled(rules, {"name": "a", "widget": "Button"})
    assert style.background == "primary", "the later rule wiped an earlier field"
    assert style.height.value == 40


# ------------------------------------------------------------------- reach


def test_the_sheet_reaches_nested_nodes() -> None:
    parsed = view(
        [{"classes": "tag", "style": {"height": 20}}],
        [
            {
                "name": "outer",
                "widget": "Vertical",
                "children": [{"name": "deep", "widget": "Text", "classes": "tag"}],
            }
        ],
    )
    assert parsed.root.children[0].children[0].style.height.value == 20


def test_the_sheet_reaches_overlays() -> None:
    parsed = parse_view(
        {
            "styles": [{"widget": "Dialog", "style": {"corner_radius": 16}}],
            "root": {"name": "root", "widget": "Vertical"},
            "overlays": [{"name": "d", "widget": "Dialog", "open": "true"}],
        }
    )
    assert parsed.overlays[0].style.corner_radius[0] == 16


def test_no_rules_leaves_the_tree_untouched() -> None:
    """The common case must not even copy the tree."""
    parsed = parse_view({"root": {"name": "root", "widget": "Vertical"}})
    from pysilver.spec.stylesheet import apply_stylesheet

    assert apply_stylesheet(parsed) is parsed


# ------------------------------------------------------------- composition


def test_a_sheet_value_counts_as_explicit_for_component_defaults() -> None:
    """Several widgets distinguish "the view set this" from "this is the field
    default" via `model_fields_set`. A stylesheet is authorial intent, so it
    has to land on the explicit side of that line."""
    parsed = parse_view(
        {
            "styles": [{"widget": "BottomSheet", "style": {"placement": "center"}}],
            "root": {"name": "root", "widget": "Vertical"},
            "overlays": [{"name": "s", "widget": "BottomSheet", "open": "true"}],
        }
    )
    assert "placement" in parsed.overlays[0].style.model_fields_set

    app = App(
        {
            "styles": [{"widget": "BottomSheet", "style": {"placement": "center"}}],
            "root": {"name": "root", "widget": "Vertical", "style": {"background": "surface"}},
            "overlays": [{"name": "s", "widget": "BottomSheet", "open": "true"}],
        },
        theme=Theme(dark=True),
        settings=Settings(width=400, height=300),
    )
    app.mount()
    app.update()
    assert app.overlays.visible()[0].placement == "center", "the component default won"


def test_a_sheet_can_override_a_component_default() -> None:
    app = App(
        {
            "styles": [{"widget": "CircularProgress", "style": {"thickness": 10}}],
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [{"name": "p", "widget": "CircularProgress", "value": "0.5"}],
            },
        },
        theme=Theme(dark=True),
        settings=Settings(width=200, height=200),
    )
    app.mount()
    app.paint(DisplayList())
    assert app.root.find("p").thickness == 10.0


# ---------------------------------------------------------------- validation


def test_an_unknown_style_property_in_a_rule_fails_at_load() -> None:
    with pytest.raises(SpecError):
        parse_view(
            {
                "styles": [{"widget": "Button", "style": {"nonsense": 1}}],
                "root": {"name": "root", "widget": "Vertical"},
            }
        )


def test_an_unknown_widget_kind_in_a_selector_fails_at_load() -> None:
    with pytest.raises(SpecError):
        parse_view(
            {
                "styles": [{"widget": "Nonexistent", "style": {"height": 1}}],
                "root": {"name": "root", "widget": "Vertical"},
            }
        )


def test_an_unknown_token_in_a_rule_fails_at_load() -> None:
    with pytest.raises(SpecError):
        parse_view(
            {
                "styles": [{"widget": "Button", "style": {"background": "chartreuse"}}],
                "root": {"name": "root", "widget": "Vertical"},
            }
        )


def test_specificity_ordering_is_what_the_cascade_uses() -> None:
    assert StyleRule(name="a").specificity > StyleRule(classes=("x", "y", "z")).specificity
    assert StyleRule(classes=("x",)).specificity > StyleRule(widget=WidgetKind.BUTTON).specificity
    assert StyleRule(widget=WidgetKind.BUTTON).specificity > StyleRule().specificity
