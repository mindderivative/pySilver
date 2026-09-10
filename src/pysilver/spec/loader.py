"""Loading view files.

``yaml.safe_load`` only -- view files are treated as untrusted input, so no
object construction, no arbitrary tags.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .include import IncludeError, resolve_includes, stamp_view
from .models import ViewSpec, WidgetSpec
from .stylesheet import apply_stylesheet
from .typescale import TypeScaleError, apply_type_scale

__all__ = ["SpecError", "assign_ids", "load_view", "parse_view"]


class SpecError(ValueError):
    """A view file that is malformed or fails validation, with its location."""


def _format(exc: ValidationError, origin: str) -> str:
    lines = [f"{origin}: {exc.error_count()} validation error(s)"]
    for err in exc.errors():
        path = ".".join(str(p) for p in err["loc"]) or "<root>"
        lines.append(f"  {path}: {err['msg']}")
    return "\n".join(lines)


def assign_ids(node: Any, path: str = "/") -> None:
    """Give every node a positional id, derived from its path in the tree.

    Authors never write ids. This exists so every node has *some* identity for
    reconciliation; because it encodes position, it changes when a node moves
    among its siblings -- which is exactly the semantics we want for an unnamed
    node. ``/`` cannot appear in a `name`, so a positional id can never collide
    with an authored one.
    """
    if isinstance(node, dict):
        node["id"] = path
        children = node.get("children")
        if isinstance(children, list):
            for index, child in enumerate(children):
                assign_ids(child, f"{path}{index}/")


def _check_unique_names(view: ViewSpec, origin: str) -> None:
    """Reject duplicate ``name``s.

    A name is a lookup key -- ``find()``, ``anchor:``, and the reconciliation
    key all resolve through it -- so a duplicate does not fail loudly, it
    silently resolves to whichever node was visited first. Caught at load time
    with both positional ids, that is a one-line fix; caught at runtime it
    looks like a widget mysteriously ignoring its handler.
    """
    seen: dict[str, str] = {}
    stack: list[WidgetSpec] = [view.root, *view.overlays]
    while stack:
        node = stack.pop()
        if node.name is not None:
            first = seen.get(node.name)
            if first is not None:
                raise SpecError(
                    f"{origin}: duplicate name {node.name!r} "
                    f"(used at {first} and {node.id}); names must be unique"
                )
            seen[node.name] = node.id
        stack.extend(node.children)


def parse_view(data: Any, *, origin: str = "<string>") -> ViewSpec:
    """Validate an already-decoded mapping into a :class:`ViewSpec`."""
    if not isinstance(data, dict):
        raise SpecError(f"{origin}: expected a mapping at the top level, got {type(data).__name__}")
    # A bare widget (no `version:`/`root:`) is accepted as the root, so trivial
    # view files stay trivial.
    payload = data if "root" in data else {"root": data}
    if isinstance(payload.get("root"), dict):
        assign_ids(payload["root"], "/")
    for index, overlay in enumerate(payload.get("overlays") or []):
        assign_ids(overlay, f"@{index}/")
    try:
        view = ViewSpec.model_validate(payload)
    except ValidationError as exc:
        raise SpecError(_format(exc, origin)) from exc
    _check_unique_names(view, origin)
    try:
        return apply_type_scale(apply_stylesheet(view))
    except TypeScaleError as exc:
        raise SpecError(f"{origin}: {exc}") from exc


def load_view(path: str | Path, *, sources: set[Path] | None = None) -> ViewSpec:
    """Read and validate a YAML view file, expanding any ``source:`` includes.

    Every file touched is added to *sources* when given, which is how hot
    reload watches the whole include graph rather than only the entry file.
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"cannot read view file {p}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SpecError(f"{p}: invalid YAML: {exc}") from exc
    if data is None:
        raise SpecError(f"{p}: file is empty")

    touched = sources if sources is not None else set()
    touched.add(p.resolve())
    try:
        data = resolve_includes(data, base=p.parent, root=p.parent, sources=touched)
        # Whatever the includes did not claim belongs to this file.
        data = stamp_view(data, p.name)
    except IncludeError as exc:
        raise SpecError(f"{p}: {exc}") from exc
    return parse_view(data, origin=str(p))


def find_by_id(root: WidgetSpec, widget_id: str) -> WidgetSpec | None:
    return next((n for n in root.walk() if n.name == widget_id), None)
