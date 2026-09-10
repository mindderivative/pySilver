"""Spec: the validated, immutable document parsed from a view file."""

from .expressions import Expression, ExpressionError, Template
from .include import IncludeError, resolve_includes
from .loader import SpecError, load_view, parse_view
from .models import (
    TEMPLATED_FIELDS,
    BorderSpec,
    ShadowSpec,
    SizeSpec,
    StyleRule,
    StyleSpec,
    ViewSpec,
    WidgetKind,
    WidgetSpec,
)

__all__ = [
    "TEMPLATED_FIELDS",
    "BorderSpec",
    "Expression",
    "ExpressionError",
    "IncludeError",
    "ShadowSpec",
    "SizeSpec",
    "SpecError",
    "StyleRule",
    "StyleSpec",
    "Template",
    "ViewSpec",
    "WidgetKind",
    "WidgetSpec",
    "load_view",
    "parse_view",
    "resolve_includes",
]
