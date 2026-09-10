"""Reconciliation: patch the Element tree to match a new Spec tree.

Hot reload is a DIFF, not a replacement (ARCHITECTURE.md 4). Replacing the tree
would discard focus, scroll position, hover, and text-field contents on every
keystroke in the view file, which makes the feature far less useful than it
looks. Matching by ``(id, widget)`` and updating in place preserves all of it.
"""

from __future__ import annotations

from typing import Any

from ..spec import WidgetSpec
from ..widgets import build_element
from .element import ElementMixin

__all__ = ["ReconcileStats", "reconcile"]


class ReconcileStats:
    """What a reconciliation actually did. Tests assert on these."""

    __slots__ = ("created", "disposed", "reused", "skipped", "updated")

    def __init__(self) -> None:
        self.created = 0
        self.updated = 0
        self.reused = 0
        self.disposed = 0
        self.skipped = 0

    def __repr__(self) -> str:
        return (
            f"<ReconcileStats created={self.created} updated={self.updated} "
            f"reused={self.reused} disposed={self.disposed} skipped={self.skipped}>"
        )


def _identity(spec: WidgetSpec) -> str:
    """A node's reconciliation key.

    A `name` is stable across a reorder, so a named node keeps its state when
    it moves. An unnamed node falls back to its positional id and is rebuilt
    instead -- which is the honest outcome, since nothing distinguished it.
    """
    return spec.name or spec.id


def _compatible(element: Any, spec: WidgetSpec) -> bool:
    """Same identity and same widget kind -- otherwise the node is rebuilt."""
    return bool(_identity(element.spec) == _identity(spec) and element.spec.widget == spec.widget)


def reconcile(element: Any, spec: WidgetSpec, stats: ReconcileStats | None = None) -> Any:
    """Return ``(element, stats)``, reusing *element* and all of its runtime
    state wherever identity and widget kind still agree."""
    stats = stats if stats is not None else ReconcileStats()
    return _reconcile(element, spec, stats), stats


def _reconcile(element: Any, spec: WidgetSpec, stats: ReconcileStats) -> Any:
    if element is None or not _compatible(element, spec):
        if element is not None:
            element.dispose()
            stats.disposed += 1
        stats.created += 1
        return build_element(spec)

    if element.spec == spec:
        # Structurally identical subtree: nothing below can differ either.
        stats.skipped += 1
        return element

    element.update_spec(spec)
    stats.updated += 1
    _reconcile_children(element, spec, stats)
    return element


def _reconcile_children(element: Any, spec: WidgetSpec, stats: ReconcileStats) -> None:
    old_children = [c for c in element.children if isinstance(c, ElementMixin)]
    by_key: dict[tuple[str, str], Any] = {
        (_identity(c.spec), str(c.spec.widget)): c for c in old_children
    }

    matched: list[Any] = []
    for child_spec in spec.children:
        key = (_identity(child_spec), str(child_spec.widget))
        existing = by_key.pop(key, None)
        if existing is not None:
            stats.reused += 1
            matched.append(_reconcile(existing, child_spec, stats))
        else:
            stats.created += 1
            matched.append(build_element(child_spec))

    # Anything left unmatched is gone: release its subscriptions.
    for orphan in by_key.values():
        orphan.dispose()
        stats.disposed += 1

    # Detach then reattach in the new order. Reordering is an index remap, not
    # a destroy-and-rebuild, so state survives a move.
    element.clear_children()
    for child in matched:
        if child.parent is not None:
            child.parent.remove_child(child)
        element.add_child(child)
