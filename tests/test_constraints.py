"""Geometry primitives and the Constraints algebra."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pysilver.layout import INF, Alignment, Constraints, EdgeInsets, Offset, Rect, Size

finite = st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)


@st.composite
def constraints(draw: st.DrawFn) -> Constraints:
    min_w = draw(finite)
    max_w = draw(st.one_of(st.floats(min_value=min_w, max_value=1e6), st.just(INF)))
    min_h = draw(finite)
    max_h = draw(st.one_of(st.floats(min_value=min_h, max_value=1e6), st.just(INF)))
    return Constraints(min_w, max_w, min_h, max_h)


# --------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_width": 10, "max_width": 5},
        {"min_height": 10, "max_height": 5},
        {"min_width": -1},
        {"min_width": math.nan},
        {"max_width": math.nan},
    ],
)
def test_invalid_constraints_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        Constraints(**kwargs)


def test_negative_size_rejected() -> None:
    with pytest.raises(ValueError):
        Size(-1, 10)


# --------------------------------------------------------------- properties


@given(constraints(), finite, finite)
def test_constrain_always_satisfies(c: Constraints, w: float, h: float) -> None:
    """The central guarantee: constrain() can never produce an invalid size."""
    assert c.is_satisfied_by(c.constrain(Size(w, h)))


@given(constraints())
def test_loosen_preserves_maxima_and_drops_minima(c: Constraints) -> None:
    loose = c.loosen()
    assert loose.min_width == 0 and loose.min_height == 0
    assert loose.max_width == c.max_width and loose.max_height == c.max_height


@given(constraints())
def test_loosen_is_idempotent(c: Constraints) -> None:
    assert c.loosen().loosen() == c.loosen()


@given(constraints(), st.floats(min_value=0, max_value=500))
def test_deflate_never_produces_invalid_constraints(c: Constraints, pad: float) -> None:
    d = c.deflate(EdgeInsets.all(pad))
    assert d.min_width <= d.max_width
    assert d.min_height <= d.max_height


@given(constraints(), constraints())
def test_enforce_result_lies_within_the_outer_constraint(a: Constraints, b: Constraints) -> None:
    e = a.enforce(b)
    assert b.min_width <= e.min_width <= e.max_width <= max(b.max_width, b.min_width)
    assert b.min_height <= e.min_height <= e.max_height <= max(b.max_height, b.min_height)


@given(constraints())
def test_tight_constraints_admit_exactly_one_size(c: Constraints) -> None:
    if c.is_tight:
        assert c.constrain(Size(0, 0)) == c.constrain(Size(1e6, 1e6)) == c.smallest


# ------------------------------------------------------------ constructors


def test_tight() -> None:
    c = Constraints.tight(Size(100, 50))
    assert c.is_tight
    assert c.constrain(Size(999, 999)) == Size(100, 50)


def test_tight_for_single_axis_is_not_fully_tight() -> None:
    c = Constraints.tight_for(width=100)
    assert c.is_tight_width and not c.is_tight_height
    assert not c.is_tight


def test_loose() -> None:
    c = Constraints.loose(Size(100, 50))
    assert c.constrain(Size(999, 999)) == Size(100, 50)
    assert c.constrain(Size(10, 10)) == Size(10, 10)


def test_unbounded() -> None:
    c = Constraints.unbounded()
    assert not c.has_bounded_width and not c.has_bounded_height


def test_expand_locks_unspecified_axes_to_infinity() -> None:
    c = Constraints.expand(width=100)
    assert c.is_tight_width and c.max_width == 100
    assert c.is_tight_height and c.max_height == INF


# -------------------------------------------------------------- operations


def test_deflate_shrinks_both_bounds() -> None:
    c = Constraints(50, 100, 50, 100).deflate(EdgeInsets.all(10))
    assert c == Constraints(30, 80, 30, 80)


def test_deflate_clamps_at_zero() -> None:
    c = Constraints(0, 10, 0, 10).deflate(EdgeInsets.all(50))
    assert c == Constraints(0, 0, 0, 0)


def test_deflate_keeps_unbounded_axis_unbounded() -> None:
    assert not Constraints.unbounded().deflate(EdgeInsets.all(10)).has_bounded_width


def test_tighten_clamps_into_range() -> None:
    assert Constraints(0, 100, 0, 100).tighten(width=500).max_width == 100


def test_tighten_leaves_other_axis_alone() -> None:
    c = Constraints(0, 100, 0, 100).tighten(width=50)
    assert c.is_tight_width and not c.is_tight_height


def test_copy_with_overrides_only_the_given_fields() -> None:
    c = Constraints(10, 20, 30, 40)
    assert c.copy_with(min_width=5) == Constraints(5, 20, 30, 40)
    assert c.copy_with(max_height=50) == Constraints(10, 20, 30, 50)


# ------------------------------------------------------------- other types


def test_edge_insets() -> None:
    e = EdgeInsets.symmetric(horizontal=10, vertical=5)
    assert e.horizontal == 20 and e.vertical == 10
    assert e.top_left == Offset(10, 5)


def test_alignment_resolve() -> None:
    child, parent = Size(50, 50), Size(100, 100)
    assert Alignment(0.0, 0.0).resolve(child, parent) == Offset(0, 0)
    assert Alignment(0.5, 0.5).resolve(child, parent) == Offset(25, 25)
    assert Alignment(1.0, 1.0).resolve(child, parent) == Offset(50, 50)


def test_alignment_overflow_is_symmetric_not_clamped() -> None:
    """An oversized child overflows both sides -- visible and debuggable."""
    assert Alignment(0.5, 0.5).resolve(Size(200, 200), Size(100, 100)) == Offset(-50, -50)


def test_rect_contains_is_half_open() -> None:
    r = Rect(0, 0, 10, 10)
    assert r.contains(0, 0) and r.contains(9.99, 9.99)
    assert not r.contains(10, 5)  # right edge excluded -- adjacent rects never overlap


def test_rect_intersect_disjoint_is_empty() -> None:
    assert Rect(0, 0, 10, 10).intersect(Rect(50, 50, 10, 10)).is_empty
