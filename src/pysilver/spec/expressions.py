"""Binding expressions: ``{{ count.get() + 1 }}`` in a view file.

View files are DATA, not code. Expressions are parsed with :mod:`ast` (which
does not execute anything) and then walked against a strict node whitelist, so
an untrusted view cannot import, call arbitrary functions, or touch dunders.
``eval`` is never used on view content.
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable, Mapping
from typing import Any, Final

__all__ = ["Expression", "ExpressionError", "has_binding"]

BINDING_RE: Final = re.compile(r"\{\{(.+?)\}\}", re.DOTALL)


class ExpressionError(ValueError):
    """Raised for an expression that is malformed or uses a forbidden construct."""


def has_binding(text: str) -> bool:
    return "{{" in text and "}}" in text


_BINARY: Final[dict[type[ast.operator], Callable[[Any, Any], Any]]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_COMPARE: Final[dict[type[ast.cmpop], Callable[[Any, Any], Any]]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}

#: The only callables a view file may invoke. Deliberately tiny.
SAFE_FUNCTIONS: Final[dict[str, Callable[..., Any]]] = {
    "abs": abs,
    "min": min,
    "max": max,
    "len": len,
    "round": round,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "sum": sum,
    "sorted": sorted,
    "any": any,
    "all": all,
}

#: Zero-argument methods callable on a value, so `{{ count.get() }}` works
#: without opening up arbitrary attribute calls.
SAFE_METHODS: Final[frozenset[str]] = frozenset(
    {"get", "peek", "upper", "lower", "strip", "title", "capitalize"}
)


class Expression:
    """A parsed, validated binding expression."""

    __slots__ = ("_node", "_roots", "source")

    def __init__(self, source: str) -> None:
        self.source = source
        try:
            tree = ast.parse(source.strip(), mode="eval")
        except SyntaxError as exc:
            raise ExpressionError(f"invalid expression {source!r}: {exc.msg}") from exc
        self._node = tree.body
        _validate(self._node, source)
        roots: set[str] = set()
        _collect_roots(self._node, roots)
        self._roots = frozenset(roots)

    @property
    def roots(self) -> frozenset[str]:
        """Top-level names the expression reads. Used to scope invalidation."""
        return self._roots

    def evaluate(self, context: Mapping[str, Any]) -> Any:
        return _eval(self._node, context, self.source)

    def __repr__(self) -> str:
        return f"<Expression {self.source!r}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Expression) and other.source == self.source

    def __hash__(self) -> int:
        return hash(self.source)


class Template:
    """A string with zero or more ``{{ }}`` holes, e.g. ``"Count: {{ n }}"``."""

    __slots__ = ("_parts", "source")

    def __init__(self, source: str) -> None:
        self.source = source
        self._parts: list[str | Expression] = []
        pos = 0
        for match in BINDING_RE.finditer(source):
            if match.start() > pos:
                self._parts.append(source[pos : match.start()])
            self._parts.append(Expression(match.group(1)))
            pos = match.end()
        if pos < len(source):
            self._parts.append(source[pos:])

    @property
    def is_static(self) -> bool:
        return all(isinstance(p, str) for p in self._parts)

    @property
    def roots(self) -> frozenset[str]:
        out: set[str] = set()
        for part in self._parts:
            if isinstance(part, Expression):
                out |= part.roots
        return frozenset(out)

    def render(self, context: Mapping[str, Any]) -> str:
        if len(self._parts) == 1 and isinstance(self._parts[0], Expression):
            return str(self._parts[0].evaluate(context))
        return "".join(p if isinstance(p, str) else str(p.evaluate(context)) for p in self._parts)

    def __repr__(self) -> str:
        return f"<Template {self.source!r}>"


# ------------------------------------------------------------------ walking

_ALLOWED_NODES: Final = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Subscript,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Slice,
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.UAdd,
    *_BINARY,
    *_COMPARE,
)


def _validate(node: ast.AST, source: str) -> None:
    for child in ast.walk(node):
        if not isinstance(child, _ALLOWED_NODES):
            raise ExpressionError(
                f"{type(child).__name__} is not permitted in a view expression ({source!r})"
            )
        if isinstance(child, ast.Attribute) and child.attr.startswith("_"):
            raise ExpressionError(
                f"private attribute {child.attr!r} is not accessible ({source!r})"
            )
        if isinstance(child, ast.Name) and child.id.startswith("_"):
            raise ExpressionError(f"private name {child.id!r} is not accessible")
        if isinstance(child, ast.Call):
            _validate_call(child, source)
        if isinstance(child, ast.Dict) and None in child.keys:
            raise ExpressionError(f"dict unpacking is not supported ({source!r})")


def _validate_call(node: ast.Call, source: str) -> None:
    if node.keywords:
        raise ExpressionError(f"keyword arguments are not supported ({source!r})")
    func = node.func
    if isinstance(func, ast.Name):
        if func.id not in SAFE_FUNCTIONS:
            raise ExpressionError(f"function {func.id!r} is not available ({source!r})")
    elif isinstance(func, ast.Attribute):
        if func.attr not in SAFE_METHODS:
            raise ExpressionError(f"method {func.attr!r} is not callable from a view ({source!r})")
    else:
        raise ExpressionError(f"unsupported call target ({source!r})")


def _collect_roots(node: ast.AST, out: set[str]) -> None:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id not in SAFE_FUNCTIONS:
            out.add(child.id)


def _eval(node: ast.AST, ctx: Mapping[str, Any], source: str) -> Any:
    match node:
        case ast.Constant():
            return node.value
        case ast.Name():
            if node.id in ctx:
                return ctx[node.id]
            if node.id in SAFE_FUNCTIONS:
                return SAFE_FUNCTIONS[node.id]
            raise ExpressionError(f"name {node.id!r} is not defined ({source!r})")
        case ast.Attribute():
            return getattr(_eval(node.value, ctx, source), node.attr)
        case ast.Subscript():
            return _eval(node.value, ctx, source)[_eval(node.slice, ctx, source)]
        case ast.Slice():
            lower = _eval(node.lower, ctx, source) if node.lower is not None else None
            upper = _eval(node.upper, ctx, source) if node.upper is not None else None
            step = _eval(node.step, ctx, source) if node.step is not None else None
            return slice(lower, upper, step)
        case ast.BinOp():
            return _BINARY[type(node.op)](
                _eval(node.left, ctx, source), _eval(node.right, ctx, source)
            )
        case ast.UnaryOp():
            value = _eval(node.operand, ctx, source)
            if isinstance(node.op, ast.Not):
                return not value
            return -value if isinstance(node.op, ast.USub) else +value
        case ast.BoolOp():
            values = [_eval(v, ctx, source) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        case ast.Compare():
            left = _eval(node.left, ctx, source)
            for op, comparator in zip(node.ops, node.comparators, strict=True):
                right = _eval(comparator, ctx, source)
                if not _COMPARE[type(op)](left, right):
                    return False
                left = right
            return True
        case ast.IfExp():
            branch = node.body if _eval(node.test, ctx, source) else node.orelse
            return _eval(branch, ctx, source)
        case ast.Call():
            args = [_eval(a, ctx, source) for a in node.args]
            return _eval(node.func, ctx, source)(*args)
        case ast.List():
            return [_eval(e, ctx, source) for e in node.elts]
        case ast.Tuple():
            return tuple(_eval(e, ctx, source) for e in node.elts)
        case ast.Dict():
            return {
                _eval(k, ctx, source) if k else None: _eval(v, ctx, source)
                for k, v in zip(node.keys, node.values, strict=True)
            }
        case _:  # pragma: no cover - _validate rejects these first
            raise ExpressionError(f"cannot evaluate {type(node).__name__} ({source!r})")
