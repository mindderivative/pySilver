"""Projection maths and instance ring behaviour (the CPU-testable half)."""

from __future__ import annotations

import numpy as np
import pytest

from pysilver.render import ortho_projection


def project(width: float, height: float, x: float, y: float) -> tuple[float, float]:
    """Apply the projection the way WGSL does: column-major mat4x4 times vec4."""
    m = ortho_projection(width, height).reshape(4, 4).T
    out = m @ np.array([x, y, 0.0, 1.0], dtype=np.float32)
    return float(out[0]), float(out[1])


def test_origin_maps_to_top_left_of_ndc() -> None:
    assert project(800, 600, 0, 0) == pytest.approx((-1.0, 1.0))


def test_far_corner_maps_to_bottom_right_of_ndc() -> None:
    assert project(800, 600, 800, 600) == pytest.approx((1.0, -1.0))


def test_centre_maps_to_ndc_origin() -> None:
    assert project(800, 600, 400, 300) == pytest.approx((0.0, 0.0))


def test_y_axis_is_flipped() -> None:
    """UI coordinates grow downward; NDC grows upward. Exactly one flip."""
    _, top = project(100, 100, 50, 10)
    _, bottom = project(100, 100, 50, 90)
    assert top > bottom


def test_projection_is_column_major_16_floats() -> None:
    p = ortho_projection(800, 600)
    assert p.shape == (16,)
    assert p.dtype == np.float32


def test_zero_size_does_not_divide_by_zero() -> None:
    assert np.all(np.isfinite(ortho_projection(0, 0)))
