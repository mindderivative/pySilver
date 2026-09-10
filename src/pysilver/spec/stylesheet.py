"""Stylesheet resolution: merging `styles:` rules into each node's style.

**Resolved once, at load.** A rule's properties are folded into the node's own
`StyleSpec` before the element tree is built, so layout and paint read `style`
exactly as they always have and a stylesheet costs nothing per frame. That also
means a stylesheet change is a reload, which is what hot reload already does.

The merge relies on Pydantic's `model_fields_set`: only fields a rule (or a
node) actually wrote are applied. Without that, every rule would impose the
full set of `StyleSpec` defaults and the last one to match would erase all the
others -- and a node's own `style:` could never win, because its unset fields
would look identical to deliberate values.

Precedence, lowest to highest:

1. rules with no selector (a baseline)
2. `widget:` rules
3. `classes:` rules, more classes beating fewer
4. `name:` rules
5. the node's own inline `style:`

Ties within a level go to document order, later winning -- the same rule CSS
uses, and the one people already expect.
"""

from __future__ import annotations

from typing import Any

from .models import StyleRule, StyleSpec, ViewSpec, WidgetSpec

__all__ = ["apply_stylesheet", "resolve_style"]


def resolve_style(node: WidgetSpec, rules: tuple[StyleRule, ...]) -> StyleSpec:
    """The style a node ends up with once the sheet is applied."""
    matched = [rule for rule in rules if rule.matches(node)]
    if not matched:
        return node.style

    merged: dict[str, Any] = {}
    # `sorted` is stable, so equal specificity keeps document order.
    for rule in sorted(matched, key=lambda r: r.specificity):
        for field in rule.style.model_fields_set:
            merged[field] = getattr(rule.style, field)
    # The node's own style wins: a view file is more specific than any sheet.
    for field in node.style.model_fields_set:
        merged[field] = getattr(node.style, field)
    return StyleSpec(**merged)


def _apply(node: WidgetSpec, rules: tuple[StyleRule, ...]) -> WidgetSpec:
    children = tuple(_apply(child, rules) for child in node.children)
    style = resolve_style(node, rules)
    if style is node.style and all(a is b for a, b in zip(children, node.children, strict=True)):
        return node  # nothing matched anywhere in this subtree
    return node.model_copy(update={"style": style, "children": children})


def apply_stylesheet(view: ViewSpec) -> ViewSpec:
    """Fold `view.styles` into every node, returning the resolved view.

    A no-op when there are no rules, so the common case pays nothing -- not
    even a tree copy.
    """
    if not view.styles:
        return view
    return view.model_copy(
        update={
            "root": _apply(view.root, view.styles),
            "overlays": tuple(_apply(o, view.styles) for o in view.overlays),
        }
    )
