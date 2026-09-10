"""Spec validation and the expression sandbox."""

from __future__ import annotations

import pytest

from pysilver.spec import SpecError, WidgetKind, parse_view
from pysilver.spec.expressions import Expression, ExpressionError, Template

MINIMAL = {"name": "root", "widget": "Container"}
#: A second node for nesting tests -- a distinct name, since names are unique.
CHILD = {"name": "child", "widget": "Container"}


def view(**overrides):
    return parse_view({**MINIMAL, **overrides})


# ------------------------------------------------------------- validation


def test_minimal_view_parses() -> None:
    v = view()
    assert v.root.name == "root"
    assert v.root.widget is WidgetKind.CONTAINER


def test_bare_widget_is_accepted_as_the_root() -> None:
    assert parse_view(MINIMAL).root.name == "root"


def test_unknown_style_key_is_rejected() -> None:
    """extra='forbid': a typo is a startup error, not a silently ignored style."""
    with pytest.raises(SpecError, match=r"backgronud|Extra inputs"):
        view(style={"backgronud": "surface"})


def test_unknown_widget_kind_is_rejected() -> None:
    with pytest.raises(SpecError):
        parse_view({"name": "x", "widget": "Blender"})


def test_unknown_md3_token_is_rejected_at_load() -> None:
    with pytest.raises(SpecError, match="unknown MD3 token"):
        view(style={"background": "chartreuse"})


def test_hex_literal_colour_is_allowed() -> None:
    assert view(style={"background": "#FF00FF"}).root.style.background == "#FF00FF"


def test_handler_keys_must_start_with_on() -> None:
    with pytest.raises(SpecError, match="must start with 'on_'"):
        view(handlers={"click": "go"})


def test_invalid_id_is_rejected() -> None:
    with pytest.raises(SpecError):
        parse_view({"name": "3 bad id", "widget": "Container"})


def test_future_schema_version_is_rejected() -> None:
    with pytest.raises(SpecError, match="not supported"):
        parse_view({"version": 99, "root": MINIMAL})


def test_errors_name_the_failing_path() -> None:
    with pytest.raises(SpecError) as exc:
        parse_view(
            {
                "name": "r",
                "widget": "Container",
                "children": [{"name": "c", "widget": "Container", "style": {"background": "nope"}}],
            }
        )
    assert "children.0.style.background" in str(exc.value)


# ------------------------------------------------------------- conversions


@pytest.mark.parametrize(
    ("raw", "kind", "value"),
    [
        (120, "fixed", 120.0),
        ("auto", "auto", 0.0),
        ("expand", "expand", 0.0),
        ("50%", "percent", 0.5),
        ("flex:3", "flex", 3.0),
        ("flex", "flex", 1.0),
    ],
)
def test_size_shorthand(raw, kind, value) -> None:
    size = view(style={"width": raw}).root.style.width
    assert (size.kind, size.value) == (kind, value)


def test_invalid_size_is_rejected() -> None:
    with pytest.raises(SpecError):
        view(style={"width": "wide"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(8, (8, 8, 8, 8)), ([4, 2], (4, 2, 4, 2)), ([1, 2, 3, 4], (1, 2, 3, 4))],
)
def test_edge_shorthand(raw, expected) -> None:
    p = view(style={"padding": raw}).root.style.padding
    assert (p.left, p.top, p.right, p.bottom) == expected


def test_corner_shorthand() -> None:
    assert view(style={"corner_radius": 12}).root.style.corner_radius == (12, 12, 12, 12)


def test_children_are_structure_not_style() -> None:
    """A prior draft nested children under `style:`. They are not styling."""
    with pytest.raises(SpecError):
        view(style={"children": [CHILD]})
    assert len(view(children=[CHILD]).root.children) == 1


def test_spec_is_frozen() -> None:
    from pydantic import ValidationError

    root = view().root
    with pytest.raises(ValidationError):
        root.name = "other"


def test_equal_specs_compare_equal() -> None:
    """Reconciliation relies on structural equality to skip subtrees."""
    assert view(style={"width": 10}).root == view(style={"width": 10}).root
    assert view(style={"width": 10}).root != view(style={"width": 11}).root


# ------------------------------------------------------------- expressions


@pytest.mark.parametrize(
    ("src", "ctx", "expected"),
    [
        ("1 + 2 * 3", {}, 7),
        ("n * 2", {"n": 21}, 42),
        ("'yes' if flag else 'no'", {"flag": True}, "yes"),
        ("len(items)", {"items": [1, 2, 3]}, 3),
        ("a > b and a > 0", {"a": 5, "b": 1}, True),
        ("items[1]", {"items": ["x", "y"]}, "y"),
        ("max(1, n)", {"n": 9}, 9),
    ],
)
def test_expression_evaluation(src, ctx, expected) -> None:
    assert Expression(src).evaluate(ctx) == expected


@pytest.mark.parametrize(
    "src",
    [
        "__import__('os')",
        "open('/etc/passwd')",
        "obj._private",
        "_hidden",
        "[x for x in range(3)]",
        "lambda: 1",
        "obj.__class__",
        "obj.destroy()",
        "eval('1')",
        "max(1, n=2)",
        "{**a}",
    ],
)
def test_dangerous_expressions_are_rejected(src) -> None:
    """View files are data. Nothing here may reach the interpreter."""
    with pytest.raises(ExpressionError):
        Expression(src)


def test_expression_reports_its_roots() -> None:
    assert Expression("a.b + len(c)").roots == frozenset({"a", "c"})


def test_undefined_name_is_an_error_not_a_silent_none() -> None:
    with pytest.raises(ExpressionError, match="not defined"):
        Expression("missing").evaluate({})


def test_template_interpolates() -> None:
    assert Template("Count: {{ n }}!").render({"n": 3}) == "Count: 3!"


def test_template_with_no_binding_is_static() -> None:
    assert Template("plain").is_static


def test_template_preserves_non_string_repr() -> None:
    assert Template("{{ n }}").render({"n": 1.5}) == "1.5"
