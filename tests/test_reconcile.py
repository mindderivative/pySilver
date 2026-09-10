"""Reconciliation: hot reload as a diff that preserves runtime state."""

from __future__ import annotations

from pysilver.layout import Constraints, Size
from pysilver.spec import parse_view
from pysilver.tree.reconcile import reconcile
from pysilver.widgets import build_element


def spec(**kw):
    return parse_view({"name": "root", "widget": "Vertical", **kw}).root


def tree(**kw):
    return build_element(spec(**kw))


CHILD_A = {"name": "a", "widget": "Container", "style": {"width": 10, "height": 10}}
CHILD_B = {"name": "b", "widget": "Container", "style": {"width": 20, "height": 20}}


# ------------------------------------------------------------ identity


def test_identical_spec_skips_the_subtree() -> None:
    s = spec(children=[CHILD_A])
    root = build_element(s)
    result, stats = reconcile(root, s, build_element)
    assert result is root
    assert stats.skipped == 1
    assert stats.updated == 0


def test_style_change_updates_in_place() -> None:
    root = tree(children=[CHILD_A])
    child = root.find("a")
    new = spec(children=[{**CHILD_A, "style": {"width": 99, "height": 10}}])
    result, stats = reconcile(root, new, build_element)
    assert result is root
    assert result.find("a") is child, "child was rebuilt instead of updated"
    assert child.style.width.value == 99
    assert stats.updated >= 1


def test_disabled_literal_change_updates_in_place() -> None:
    """Regression: `update_spec` used to read `disabled:` only in
    `init_element`, so a reload that flipped it left the old value in place
    (see the comment in `ElementMixin.update_spec`)."""
    root = tree(children=[{**CHILD_A, "disabled": "true"}])
    child = root.find("a")
    assert child.disabled
    result, stats = reconcile(
        root, spec(children=[{**CHILD_A, "disabled": "false"}]), build_element
    )
    assert result.find("a") is child
    assert not child.disabled
    assert stats.updated >= 1


def test_state_survives_a_style_change() -> None:
    """The headline claim: editing a view file must not wipe runtime state."""
    root = tree(children=[CHILD_A])
    child = root.find("a")
    child.state.focused = True
    child.state.scroll = (12, 34)  # type: ignore[assignment]
    child.state.data["draft"] = "unsent text"

    result, _ = reconcile(
        root,
        spec(children=[{**CHILD_A, "style": {"width": 50, "height": 10, "background": "primary"}}]),
        build_element,
    )

    survivor = result.find("a")
    assert survivor is child
    assert survivor.state.focused
    assert survivor.state.scroll == (12, 34)
    assert survivor.state.data["draft"] == "unsent text"


def test_changed_widget_kind_forces_a_rebuild() -> None:
    root = tree(children=[CHILD_A])
    old = root.find("a")
    result, stats = reconcile(root, spec(children=[{**CHILD_A, "widget": "Button"}]), build_element)
    assert result.find("a") is not old
    assert stats.created >= 1


def test_changed_id_forces_a_rebuild() -> None:
    root = tree(children=[CHILD_A])
    result, stats = reconcile(root, spec(children=[{**CHILD_A, "name": "renamed"}]), build_element)
    assert result.find("a") is None
    assert result.find("renamed") is not None
    assert stats.created >= 1


# ------------------------------------------------------------- structure


def test_added_child_is_created() -> None:
    root = tree(children=[CHILD_A])
    kept = root.find("a")
    result, stats = reconcile(root, spec(children=[CHILD_A, CHILD_B]), build_element)
    assert len(result.children) == 2
    assert result.find("a") is kept
    assert stats.created == 1


def test_removed_child_is_disposed() -> None:
    root = tree(children=[CHILD_A, CHILD_B])
    result, stats = reconcile(root, spec(children=[CHILD_A]), build_element)
    assert len(result.children) == 1
    assert result.find("b") is None
    assert stats.disposed == 1


def test_reordering_preserves_identity_and_state() -> None:
    """A move is an index remap, not a destroy-and-rebuild."""
    root = tree(children=[CHILD_A, CHILD_B])
    a, b = root.find("a"), root.find("b")
    a.state.data["keep"] = 1
    result, stats = reconcile(root, spec(children=[CHILD_B, CHILD_A]), build_element)
    assert [c.name for c in result.children] == ["b", "a"]
    assert result.find("a") is a
    assert result.find("b") is b
    assert result.find("a").state.data["keep"] == 1
    assert stats.created == 0
    assert stats.disposed == 0


def test_nested_subtrees_reconcile() -> None:
    nested = {
        "name": "outer",
        "widget": "Vertical",
        "children": [{"name": "inner", "widget": "Container", "style": {"width": 5, "height": 5}}],
    }
    root = tree(children=[nested])
    inner = root.find("inner")
    inner.state.data["x"] = 1
    changed = {
        **nested,
        "children": [{"name": "inner", "widget": "Container", "style": {"width": 77, "height": 5}}],
    }
    result, _ = reconcile(root, spec(children=[changed]), build_element)
    assert result.find("inner") is inner
    assert result.find("inner").state.data["x"] == 1
    assert result.find("inner").style.width.value == 77


def test_reconciled_tree_lays_out_correctly() -> None:
    root = tree(style={"padding": 8, "spacing": 4}, children=[CHILD_A, CHILD_B])
    root.layout(Constraints.tight(Size(200, 200)))
    result, _ = reconcile(
        root,
        spec(
            style={"padding": 8, "spacing": 4},
            children=[CHILD_A, {**CHILD_B, "style": {"width": 20, "height": 40}}],
        ),
        build_element,
    )
    result.layout(Constraints.tight(Size(200, 200)))
    assert result.find("b").size == Size(20, 40)
    assert result.find("b").offset.y == 8 + 10 + 4


def test_disposal_releases_subscriptions() -> None:
    from pysilver.runtime.signals import Signal

    count = Signal(0)
    root = build_element(
        spec(children=[{"name": "t", "widget": "Text", "text": "n={{ count.get() }}"}])
    )
    ctx = {"count": count}
    for element in root.walk_elements():
        element.bind(ctx)
    assert count.subscriber_count == 1

    result, _ = reconcile(root, spec(children=[]), build_element)
    assert result.find("t") is None
    assert count.subscriber_count == 0, "disposed element still subscribed"
