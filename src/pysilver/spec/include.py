"""View composition: ``source:`` pulls a subtree in from another file.

Resolution happens on the **decoded YAML**, before Pydantic validates anything.
A resolved include is therefore indistinguishable from inline content -- the
spec models, reconciliation, and the renderer never learn a file boundary
existed.

A fragment is a plain widget spec that may declare ``params:``; the call site
supplies them with ``with:``::

    # dialogs/confirm.yaml
    params: [title]
    widget: Card
    children:
      - {name: label, widget: Text, text: "{{ title }}"}

    # call site
    - name: delete_confirm
      source: dialogs/confirm.yaml
      with: {title: "Delete file?"}

Parameters are substituted **textually**, which is what makes them compose with
bindings: passing ``title: "{{ user.get() }}"`` leaves a live template behind,
while passing a plain string leaves static text. No separate reactive path is
needed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import yaml

__all__ = [
    "IncludeError",
    "expand_styles",
    "resolve_includes",
]

#: Keys that control inclusion rather than describing a widget.
SOURCE_KEY: Final = "source"
STYLES_KEY: Final = "styles"
TYPE_SCALE_KEY: Final = "type_scale"
PARAMS_KEY: Final = "params"
WITH_KEY: Final = "with"

#: How deep includes may nest. A guard against pathological graphs; cycles are
#: caught separately and reported precisely.
MAX_DEPTH: Final = 32

#: Key stamped onto every widget node recording the view file it came from.
#: Loader-assigned, never authored -- it is what lets a fragment have its own
#: ViewModel after includes have been flattened into one tree.
VIEW_KEY: Final = "view"

_PARAM_RE: Final = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class IncludeError(ValueError):
    """An include that cannot be resolved, with the chain that led to it."""


def _chain_text(chain: tuple[Path, ...]) -> str:
    return " -> ".join(p.name for p in chain) if chain else "<root>"


def _view_id(path: Path, root: Path) -> str:
    """A view file's stable name: its path relative to the view root.

    Relative rather than absolute so the identifier does not change with the
    checkout directory, and POSIX-separated so it does not change with the
    platform -- an application binds a ViewModel against this string.
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _resolve_path(raw: str, base: Path, root: Path, chain: tuple[Path, ...]) -> Path:
    """Resolve *raw* against the including file, confined under *root*.

    View files are untrusted input, so an include may not escape the view
    directory -- ``source: ../../../etc/passwd`` is refused rather than read.
    """
    candidate = (base / raw).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise IncludeError(
            f"{_chain_text(chain)}: include {raw!r} resolves outside the view "
            f"directory ({root}); includes may not escape it"
        ) from None
    if not candidate.is_file():
        raise IncludeError(f"{_chain_text(chain)}: included file not found: {candidate}")
    return candidate


def _substitute(node: Any, values: dict[str, str]) -> Any:
    """Replace ``{{ name }}`` with the supplied text, throughout the fragment."""
    if isinstance(node, str):
        return _PARAM_RE.sub(
            lambda m: values[m.group(1)] if m.group(1) in values else m.group(0), node
        )
    if isinstance(node, dict):
        return {k: _substitute(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [_substitute(v, values) for v in node]
    return node


def _namespace_names(node: Any, prefix: str, local: set[str]) -> Any:
    """Qualify every `name` declared inside a fragment with the call-site name.

    Positional ids are inherently scoped by path, so only names need this --
    but they need it badly: including the same fragment twice would otherwise
    give two nodes the same name, and ``find()`` would return the wrong one.
    """
    if isinstance(node, list):
        return [_namespace_names(v, prefix, local) for v in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "name" and isinstance(value, str):
            out[key] = f"{prefix}.{value}"
        elif key == "anchor" and isinstance(value, str) and value in local:
            # An anchor naming a fragment-local id must follow it; one naming
            # an outer element is left alone.
            out[key] = f"{prefix}.{value}"
        else:
            out[key] = _namespace_names(value, prefix, local)
    return out


def _collect_names(node: Any, into: set[str]) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("name"), str):
            into.add(node["name"])
        for value in node.values():
            _collect_names(value, into)
    elif isinstance(node, list):
        for value in node:
            _collect_names(value, into)


def _load_fragment(path: Path, chain: tuple[Path, ...]) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise IncludeError(f"{_chain_text((*chain, path))}: invalid YAML: {exc}") from exc
    except OSError as exc:
        raise IncludeError(f"{_chain_text(chain)}: cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise IncludeError(
            f"{_chain_text((*chain, path))}: a fragment must be a mapping "
            f"(one widget), got {type(raw).__name__}"
        )
    return raw


def _load_rules(path: Path, chain: tuple[Path, ...]) -> list[Any]:
    """Read a stylesheet file: a bare YAML list of rules.

    A sheet is a list, not a mapping, which is what distinguishes it from a
    widget fragment. Checking that here means a file included in the wrong
    place says so, instead of failing later as a confusing validation error on
    a widget that was never a widget.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise IncludeError(f"{_chain_text((*chain, path))}: invalid YAML: {exc}") from exc
    except OSError as exc:
        raise IncludeError(f"{_chain_text(chain)}: cannot read {path}: {exc}") from exc
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise IncludeError(
            f"{_chain_text((*chain, path))}: a stylesheet must be a list of rules, "
            f"got {type(raw).__name__}"
        )
    return raw


def expand_styles(
    entries: Any,
    base: Path,
    root: Path,
    sources: set[Path],
    chain: tuple[Path, ...] = (),
) -> list[Any]:
    """Splice every `- source:` in a `styles:` list into the rules it names.

    Included rules land **in place**, so document order -- and with it the
    tie-breaking half of the cascade -- reads exactly as written: a view that
    pulls in a base theme and then adds its own rules overrides it, because
    its rules come later.
    """
    if not isinstance(entries, list):
        raise IncludeError("`styles:` must be a list of rules")
    if len(chain) >= MAX_DEPTH:
        raise IncludeError(f"{_chain_text(chain)}: stylesheets nested more than {MAX_DEPTH} deep")

    out: list[Any] = []
    for entry in entries:
        if not (isinstance(entry, dict) and SOURCE_KEY in entry):
            out.append(entry)
            continue
        extra = set(entry) - {SOURCE_KEY}
        if extra:
            raise IncludeError(
                f"{_chain_text(chain)}: a stylesheet include takes only `source:`, "
                f"got {', '.join(sorted(extra))}"
            )
        path = _resolve_path(str(entry[SOURCE_KEY]), base, root, chain)
        if path in chain:
            raise IncludeError(f"stylesheet cycle: {_chain_text((*chain, path))}")
        sources.add(path)
        out.extend(
            expand_styles(_load_rules(path, chain), path.parent, root, sources, (*chain, path))
        )
    return out


def expand_type_scale(
    value: Any,
    base: Path,
    root: Path,
    sources: set[Path],
) -> Any:
    """Expand `type_scale: {source: scale.yaml}` into the mapping it names.

    A scale is a mapping of role to size, so the file is a mapping too -- which
    is what distinguishes it from a stylesheet, and lets including one in the
    wrong place say so instead of failing later.
    """
    if not (isinstance(value, dict) and SOURCE_KEY in value):
        return value
    extra = set(value) - {SOURCE_KEY}
    if extra:
        raise IncludeError(
            f"a type-scale include takes only `source:`, got {', '.join(sorted(extra))}"
        )
    path = _resolve_path(str(value[SOURCE_KEY]), base, root, ())
    sources.add(path)
    raw = _load_fragment(path, ())
    if any(not isinstance(v, int | float) for v in raw.values()):
        raise IncludeError(f"{path.name}: a type scale maps each role to a number")
    return raw


def stamp_view(node: Any, view: str) -> Any:
    """Record *view* as the origin of every widget node that has no origin yet.

    Innermost wins: a fragment's own includes are expanded and stamped first,
    so this only fills in the nodes that belong to *this* file. Without it the
    include tree is flattened and there is no way back to which file a node was
    written in -- which is the whole basis of binding a ViewModel per view.
    """
    if isinstance(node, list):
        return [stamp_view(v, view) for v in node]
    if not isinstance(node, dict):
        return node
    out = {
        k: (stamp_view(v, view) if k in ("root", "children", "overlays") else v)
        for k, v in node.items()
    }
    if "widget" in out and VIEW_KEY not in out:
        out[VIEW_KEY] = view
    return out


def _expand(
    node: dict[str, Any],
    base: Path,
    root: Path,
    sources: set[Path],
    chain: tuple[Path, ...],
) -> dict[str, Any]:
    """Replace one ``source:`` node with the fragment it names."""
    if len(chain) >= MAX_DEPTH:
        raise IncludeError(f"{_chain_text(chain)}: includes nested more than {MAX_DEPTH} deep")

    path = _resolve_path(str(node[SOURCE_KEY]), base, root, chain)
    if path in chain:
        raise IncludeError(f"include cycle: {_chain_text((*chain, path))}")
    sources.add(path)

    fragment = _load_fragment(path, chain)
    declared = fragment.pop(PARAMS_KEY, []) or []
    if not isinstance(declared, list):
        raise IncludeError(f"{path.name}: `params:` must be a list of names")

    supplied = node.get(WITH_KEY) or {}
    if not isinstance(supplied, dict):
        raise IncludeError(f"{_chain_text((*chain, path))}: `with:` must be a mapping")

    missing = [p for p in declared if p not in supplied]
    if missing:
        raise IncludeError(
            f"{_chain_text((*chain, path))}: missing parameter(s) {missing}; "
            f"{path.name} declares {declared}"
        )
    unknown = [k for k in supplied if k not in declared]
    if unknown:
        raise IncludeError(
            f"{_chain_text((*chain, path))}: unknown parameter(s) {unknown}; "
            f"{path.name} declares {declared or '[]'}"
        )

    fragment = _substitute(fragment, {k: str(v) for k, v in supplied.items()})

    # Resolve the fragment's own includes relative to ITS directory.
    resolved = _walk(fragment, path.parent, root, sources, (*chain, path))
    fragment = resolved if isinstance(resolved, dict) else fragment
    stamped = stamp_view(fragment, _view_id(path, root))
    fragment = stamped if isinstance(stamped, dict) else fragment

    call_name = node.get("name")
    if isinstance(call_name, str):
        local: set[str] = set()
        _collect_names(fragment, local)
        fragment = _namespace_names(fragment, call_name, local)
        fragment["name"] = call_name

    # Anything else at the call site (open:, style:, ...) is not merged --
    # parameters are the interface.
    for key in (SOURCE_KEY, WITH_KEY, "name"):
        node.pop(key, None)
    if node:
        raise IncludeError(
            f"{_chain_text((*chain, path))}: a `source:` node takes only `name:` "
            f"and `with:`; got {sorted(node)}. Pass configuration as parameters."
        )
    return fragment


#: The only keys whose values can hold widget-tree nodes (and therefore
#: `source:` includes). Recursing into every key indiscriminately means any
#: unrelated field that happens to be a dict with its own `source` entry --
#: `EdgeSpec.source`/`.target` in a `NodeGraph`'s `edges:` list, for one --
#: gets misread as an include and fails to resolve as a file path. Mirrors
#: `stamp_view`'s own restriction to the same three keys, plus `styles:` for
#: stylesheet includes.
_TREE_KEYS: Final = ("root", "children", "overlays", "styles")


def _walk(node: Any, base: Path, root: Path, sources: set[Path], chain: tuple[Path, ...]) -> Any:
    if isinstance(node, list):
        return [_walk(v, base, root, sources, chain) for v in node]
    if not isinstance(node, dict):
        return node
    if SOURCE_KEY in node:
        return _expand(dict(node), base, root, sources, chain)
    return {
        k: (_walk(v, base, root, sources, chain) if k in _TREE_KEYS else v) for k, v in node.items()
    }


def resolve_includes(
    data: Any,
    *,
    base: Path,
    root: Path | None = None,
    sources: set[Path] | None = None,
) -> Any:
    """Expand every ``source:`` in *data*.

    ``base`` is the directory of the file being resolved; ``root`` confines
    includes (defaults to *base*). Every file touched is added to ``sources``,
    which is what lets hot reload watch the whole graph rather than one file.
    """
    confine = root if root is not None else base
    touched = sources if sources is not None else set()
    # `styles:` is a top-level key and holds rules, not widgets, so it is
    # expanded on its own path -- handing a rule list to the widget-fragment
    # expander would report a mapping error about a file that is correct.
    if isinstance(data, dict) and STYLES_KEY in data:
        data = {**data, STYLES_KEY: expand_styles(data[STYLES_KEY], base, confine, touched)}
    if isinstance(data, dict) and TYPE_SCALE_KEY in data:
        data = {
            **data,
            TYPE_SCALE_KEY: expand_type_scale(data[TYPE_SCALE_KEY], base, confine, touched),
        }
    return _walk(data, base, confine, touched, ())
