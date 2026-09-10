"""Segment/capsule rendering: the SDF primitive behind `add_segment`.

No widget consumes this yet -- it is an engine prerequisite for Canvas and
node-graph edges (`pySilver Widget Backlog` in the memory graph), both still
unbuilt. These tests protect the primitive itself, the way M2's
`tests/golden/test_primitives.py` protected boxes and shadows before any
widget existed to draw them.
"""

from __future__ import annotations

import pytest

from pysilver.paint import NO_TOKEN, DisplayList, Kind


def params(instance) -> tuple[float, float, float, float]:
    return tuple(float(v) for v in instance["params"])  # type: ignore[return-value]


def radii(instance) -> tuple[float, float, float, float]:
    return tuple(float(v) for v in instance["radii"])  # type: ignore[return-value]


def rect(instance) -> tuple[float, float, float, float]:
    return tuple(float(v) for v in instance["rect"])  # type: ignore[return-value]


# ------------------------------------------------------------- the primitive


def test_add_segment_sets_the_kind() -> None:
    dl = DisplayList()
    i = dl.add_segment(0, 0, 10, 10, thickness=2.0)
    assert int(dl.view[i]["flags"][0]) == int(Kind.SEGMENT)


def test_the_bounding_box_covers_both_endpoints_plus_the_radius() -> None:
    """`rect` is the tight bbox the shader pads for antialiasing, not a
    caller-chosen box the way a box or polygon's is -- add_segment computes it
    from the two endpoints."""
    dl = DisplayList()
    i = dl.add_segment(10, 20, 50, 60, thickness=8.0)
    x, y, w, h = rect(dl.view[i])
    assert (x, y) == pytest.approx((10 - 4, 20 - 4))
    assert (w, h) == pytest.approx((40 + 8, 40 + 8))


def test_endpoints_are_stored_relative_to_the_rects_centre() -> None:
    """`radii` carries (ax, ay, bx, by) in the same centre-relative frame the
    shader's `p` is in -- unused by a stroke otherwise, since it has no
    corners to need per-corner radii for."""
    dl = DisplayList()
    i = dl.add_segment(0, 0, 40, 0, thickness=4.0)
    x, y, w, h = rect(dl.view[i])
    cx, cy = x + w / 2, y + h / 2
    ax, ay, bx, by = radii(dl.view[i])
    assert (ax, ay) == pytest.approx((0 - cx, 0 - cy))
    assert (bx, by) == pytest.approx((40 - cx, 0 - cy))


def test_thickness_lands_in_params() -> None:
    dl = DisplayList()
    i = dl.add_segment(0, 0, 10, 0, thickness=6.0)
    assert params(dl.view[i])[0] == pytest.approx(6.0)


def test_a_vertical_segment_gets_a_tall_thin_bbox() -> None:
    dl = DisplayList()
    i = dl.add_segment(5, 0, 5, 100, thickness=2.0)
    _, _, w, h = rect(dl.view[i])
    assert w == pytest.approx(2.0)
    assert h == pytest.approx(102.0)


def test_a_degenerate_zero_length_segment_gives_a_square_bbox() -> None:
    """`a == b` divides by zero in the shader's sd_segment without a guard;
    the Python side must not itself choke on the same input."""
    dl = DisplayList()
    i = dl.add_segment(10, 10, 10, 10, thickness=4.0)
    _, _, w, h = rect(dl.view[i])
    assert (w, h) == pytest.approx((4.0, 4.0))


def test_add_segment_carries_the_clip_like_every_other_primitive() -> None:
    """A segment inside a ScrollView or a clipped canvas must be clippable."""
    dl = DisplayList()
    i = dl.add_segment(0, 0, 10, 10, thickness=2, clip=(1.0, 2.0, 30.0, 40.0))
    assert tuple(float(v) for v in dl.view[i]["clip"]) == (1.0, 2.0, 30.0, 40.0)


def test_no_border_slot_is_used_a_segment_has_no_border() -> None:
    """Unlike box/polygon, a segment's own width IS its stroke -- there is no
    separate border, the same as `add_arc`."""
    dl = DisplayList()
    i = dl.add_segment(0, 0, 10, 0, thickness=4.0)
    assert tuple(float(v) for v in dl.view[i]["border"]) == (0.0, 0.0, 0.0, 0.0)
    assert int(dl.view[i]["flags"][3]) == NO_TOKEN


def test_token_colours_the_segment() -> None:
    dl = DisplayList()
    i = dl.add_segment(0, 0, 10, 0, thickness=2.0, token=7)
    assert int(dl.view[i]["flags"][2]) == 7


def test_opacity_multiplies_fill_alpha() -> None:
    dl = DisplayList()
    i = dl.add_segment(0, 0, 10, 0, thickness=2.0, color=(1.0, 0.0, 0.0, 0.5), opacity=0.5)
    assert float(dl.view[i]["fill"][3]) == pytest.approx(0.25)
