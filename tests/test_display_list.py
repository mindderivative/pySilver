"""Display list: instance layout, growth, emitters, and subtree caching."""

from __future__ import annotations

import numpy as np
import pytest

from pysilver.paint import INSTANCE_DTYPE, INSTANCE_SIZE, NO_TOKEN, DisplayList, Kind

# ------------------------------------------------------------------- layout


def test_instance_is_144_bytes() -> None:
    assert INSTANCE_SIZE == 144


def test_every_field_is_vec4_aligned() -> None:
    """WGSL alignment traps are sidestepped by construction -- no vec3 anywhere."""
    for name in INSTANCE_DTYPE.names:
        offset = INSTANCE_DTYPE.fields[name][1]
        assert offset % 16 == 0, f"{name} at {offset} is not 16-byte aligned"


def test_field_order_matches_shader() -> None:
    assert INSTANCE_DTYPE.names == (
        "rect",
        "radii",
        "clip",
        "clip_radii",
        "fill",
        "border",
        "uv",
        "params",
        "flags",
    )


def test_flags_are_unsigned_ints() -> None:
    assert INSTANCE_DTYPE["flags"].base == np.uint32


# ------------------------------------------------------------------ growth


def test_starts_empty() -> None:
    assert len(DisplayList()) == 0
    assert DisplayList().view.shape == (0,)


def test_grows_by_doubling() -> None:
    dl = DisplayList(capacity=2)
    for _ in range(5):
        dl.add_box(0, 0, 1, 1)
    assert len(dl) == 5
    assert dl.capacity == 8


def test_growth_preserves_existing_instances() -> None:
    dl = DisplayList(capacity=1)
    dl.add_box(11, 22, 33, 44)
    for _ in range(10):
        dl.add_box(0, 0, 1, 1)
    assert tuple(dl.view[0]["rect"]) == (11, 22, 33, 44)


def test_clear_keeps_capacity() -> None:
    """Steady state must perform zero allocations per frame."""
    dl = DisplayList(capacity=4)
    for _ in range(20):
        dl.add_box(0, 0, 1, 1)
    capacity = dl.capacity
    dl.clear()
    assert len(dl) == 0
    assert dl.capacity == capacity


def test_view_is_contiguous_for_upload() -> None:
    dl = DisplayList()
    dl.add_box(0, 0, 1, 1)
    assert dl.view.flags["C_CONTIGUOUS"]


def test_reserve_is_a_noop_when_capacity_suffices() -> None:
    dl = DisplayList(capacity=100)
    dl.reserve(10)
    assert dl.capacity == 100


# ---------------------------------------------------------------- emitters


def test_add_box_writes_geometry_and_kind() -> None:
    dl = DisplayList()
    dl.add_box(10, 20, 30, 40, color=(1, 0, 0, 1), radii=(1, 2, 3, 4))
    s = dl.view[0]
    assert tuple(s["rect"]) == (10, 20, 30, 40)
    assert tuple(s["radii"]) == (1, 2, 3, 4)
    assert tuple(s["fill"]) == (1, 0, 0, 1)
    assert s["flags"][0] == Kind.BOX


def test_add_box_returns_its_index() -> None:
    dl = DisplayList()
    assert dl.add_box(0, 0, 1, 1) == 0
    assert dl.add_box(0, 0, 1, 1) == 1


def test_literal_colour_uses_the_no_token_sentinel() -> None:
    dl = DisplayList()
    dl.add_box(0, 0, 1, 1, color=(1, 0, 0, 1))
    assert dl.view[0]["flags"][2] == NO_TOKEN


def test_token_is_written_to_flags() -> None:
    dl = DisplayList()
    dl.add_box(0, 0, 1, 1, token=7)
    assert dl.view[0]["flags"][2] == 7


def test_opacity_multiplies_fill_alpha() -> None:
    dl = DisplayList()
    dl.add_box(0, 0, 1, 1, color=(1, 1, 1, 0.5), opacity=0.5)
    assert dl.view[0]["fill"][3] == pytest.approx(0.25)


def test_border_width_lands_in_params() -> None:
    dl = DisplayList()
    dl.add_box(0, 0, 1, 1, border_width=3.0, border_color=(0, 1, 0, 1), border_token=5)
    assert dl.view[0]["params"][0] == 3.0
    assert tuple(dl.view[0]["border"]) == (0, 1, 0, 1)
    assert dl.view[0]["flags"][3] == 5


def test_add_shadow_carries_blur_and_offset() -> None:
    dl = DisplayList()
    dl.add_shadow(0, 0, 10, 10, blur=8.0, offset=(2.0, 4.0))
    s = dl.view[0]
    assert s["flags"][0] == Kind.SHADOW
    assert tuple(s["params"]) == (0.0, 8.0, 2.0, 4.0)


def test_add_glyph_sets_uv_and_kind() -> None:
    dl = DisplayList()
    dl.add_glyph(0, 0, 8, 12, uv=(0.1, 0.2, 0.3, 0.4))
    s = dl.view[0]
    assert s["flags"][0] == Kind.GLYPH
    assert tuple(s["uv"]) == pytest.approx((0.1, 0.2, 0.3, 0.4))


def test_add_image_sets_uv_and_kind() -> None:
    dl = DisplayList()
    dl.add_image(0, 0, 8, 8, uv=(0.1, 0.2, 0.3, 0.4), tint=(1, 0, 0, 1))
    s = dl.view[0]
    assert s["flags"][0] == Kind.IMAGE
    assert tuple(s["uv"]) == pytest.approx((0.1, 0.2, 0.3, 0.4))
    assert tuple(s["fill"]) == (1, 0, 0, 1)


def test_clip_defaults_to_unclipped() -> None:
    """A zero-size clip rect is the shader's 'no clipping' signal."""
    dl = DisplayList()
    dl.add_box(0, 0, 1, 1)
    assert tuple(dl.view[0]["clip"]) == (0, 0, 0, 0)


# --------------------------------------------------------- bulk and caching


def test_add_boxes_is_vectorised() -> None:
    dl = DisplayList()
    rects = np.array([[0, 0, 10, 10], [20, 20, 5, 5], [1, 2, 3, 4]], dtype=np.float32)
    start = dl.add_boxes(rects)
    assert start == 0
    assert len(dl) == 3
    assert np.array_equal(dl.view["rect"], rects)
    assert np.all(dl.view["flags"][:, 0] == Kind.BOX)


def test_add_boxes_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError, match=r"\(N, 4\)"):
        DisplayList().add_boxes(np.zeros((3, 2), dtype=np.float32))


def test_snapshot_and_extend_round_trip() -> None:
    """This is the subtree cache path: snapshot once, memcpy back each frame."""
    source = DisplayList()
    source.add_box(1, 2, 3, 4, color=(1, 0, 0, 1))
    source.add_box(5, 6, 7, 8, color=(0, 1, 0, 1))
    cached = source.snapshot(0)

    target = DisplayList()
    target.add_box(0, 0, 1, 1)
    start = target.extend(cached)

    assert start == 1
    assert len(target) == 3
    assert np.array_equal(target.view[1:], cached)


def test_extend_rejects_foreign_dtype() -> None:
    with pytest.raises(TypeError, match="expected"):
        DisplayList().extend(np.zeros(3, dtype=np.float32))


def test_snapshot_is_a_copy_not_a_view() -> None:
    dl = DisplayList()
    dl.add_box(1, 1, 1, 1)
    snap = dl.snapshot(0)
    dl.view[0]["rect"] = (9, 9, 9, 9)
    assert tuple(snap[0]["rect"]) == (1, 1, 1, 1)


def test_index_order_is_paint_order() -> None:
    dl = DisplayList()
    dl.add_box(0, 0, 1, 1, color=(1, 0, 0, 1))
    dl.add_box(0, 0, 1, 1, color=(0, 1, 0, 1))
    assert tuple(dl.view[0]["fill"]) == (1, 0, 0, 1)
    assert tuple(dl.view[1]["fill"]) == (0, 1, 0, 1)
