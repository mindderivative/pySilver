"""The universal SDF pipeline: boxes, corners, antialiasing, borders, clipping.

These are the M2 acceptance tests. They assert the properties the architecture
claims are *free* consequences of using a real distance field -- analytic AA and
rounded clipping -- rather than merely that something got drawn.
"""

from __future__ import annotations

import numpy as np
import pytest

from pysilver import Theme
from pysilver.paint import DisplayList
from pysilver.theme import Palette

pytestmark = pytest.mark.gpu

RED = (1.0, 0.0, 0.0, 1.0)
GREEN = (0.0, 1.0, 0.0, 1.0)
BLUE = (0.0, 0.0, 1.0, 1.0)


def linear_to_srgb8(c: float) -> float:
    s = c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return s * 255.0


# ------------------------------------------------------------------ basics


def test_solid_box_fills_its_rect(render_scene) -> None:
    frame, _ = render_scene(lambda dl: dl.add_box(20, 20, 60, 60, color=RED))
    assert tuple(frame[50, 50, :3]) == (255, 0, 0)


def test_outside_the_box_is_untouched(render_scene) -> None:
    frame, _ = render_scene(lambda dl: dl.add_box(20, 20, 60, 60, color=RED))
    assert frame[5, 5, 0] < 50, "box leaked outside its rect"


def test_box_edges_land_where_specified(render_scene) -> None:
    frame, _ = render_scene(lambda dl: dl.add_box(20, 20, 60, 60, color=RED))
    assert frame[50, 21, 0] > 200, "left edge missing"
    assert frame[50, 78, 0] > 200, "right edge missing"
    assert frame[50, 15, 0] < 50, "leaked left"
    assert frame[50, 85, 0] < 50, "leaked right"


def test_empty_display_list_draws_nothing(render_scene) -> None:
    frame, engine = render_scene(lambda dl: None)
    assert engine.instance_count == 0
    assert np.all(frame[:, :, :3] == frame[0, 0, :3])


# ---------------------------------------------------- rounded corners + AA


def test_rounded_corner_removes_the_square_corner(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_box(20, 20, 60, 60, color=RED, radii=(20, 20, 20, 20))

    frame, _ = render_scene(paint)
    assert frame[22, 22, 0] < 50, "corner was not rounded away"
    assert frame[50, 50, 0] > 200, "centre should still be filled"


def test_each_corner_radius_is_independent(render_scene) -> None:
    """radii is (tl, tr, br, bl) -- only the top-left should be cut."""

    def paint(dl: DisplayList) -> None:
        dl.add_box(20, 20, 60, 60, color=RED, radii=(20, 0, 0, 0))

    frame, _ = render_scene(paint)
    assert frame[23, 23, 0] < 60, "top-left not rounded"
    assert frame[23, 76, 0] > 200, "top-right should be square"
    assert frame[76, 76, 0] > 200, "bottom-right should be square"
    assert frame[76, 23, 0] > 200, "bottom-left should be square"


def test_an_oversized_corner_radius_clamps_to_a_pill_not_nothing(render_scene) -> None:
    """`sd_rounded_box`'s formula assumes radius never exceeds the box's own
    half-extent -- a caller passing a larger one (found live via the
    Container widget demo's corner_radius: 999 stress-test step) made it
    return a large positive ("fully outside") distance even at dead centre,
    so the whole box vanished instead of clamping to a circle/stadium."""

    def paint(dl: DisplayList) -> None:
        dl.add_box(20, 20, 60, 60, color=RED, radii=(999, 999, 999, 999))

    frame, _ = render_scene(paint)
    assert frame[50, 50, 0] > 200, "an oversized radius must not erase the box"


def test_antialiasing_produces_intermediate_coverage(render_scene) -> None:
    """The whole point of an SDF: coverage is analytic, so edges are smooth
    without MSAA. A hard-edged rasteriser would give only 0 and 255 here."""

    def paint(dl: DisplayList) -> None:
        dl.add_box(20, 20, 60, 60, color=RED, radii=(25, 25, 25, 25))

    frame, _ = render_scene(paint)
    diagonal = np.array([frame[20 + i, 20 + i, 0] for i in range(20)], dtype=int)
    intermediate = [v for v in diagonal if 20 < v < 235]
    assert len(intermediate) >= 2, f"no soft edge found: {diagonal.tolist()}"


def test_antialiasing_is_monotonic_across_an_edge(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_box(20.5, 20, 60, 60, color=RED)

    frame, _ = render_scene(paint)
    row = np.array([frame[50, x, 0] for x in range(18, 26)], dtype=int)
    assert row[0] < row[-1], "edge does not ramp from outside to inside"


# ---------------------------------------------------------------- borders


def test_border_ring_and_fill_are_distinct(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_box(20, 20, 88, 88, color=RED, border_width=8.0, border_color=GREEN)

    frame, _ = render_scene(paint)
    assert frame[64, 23, 1] > 200, "border ring should be green"
    assert frame[64, 23, 0] < 60
    assert frame[64, 64, 0] > 200, "interior should be red"
    assert frame[64, 64, 1] < 60


def test_border_does_not_double_composite(render_scene) -> None:
    """Fill and border coverages are disjoint, so a semi-transparent pair must
    not stack into something more opaque than either."""

    def paint(dl: DisplayList) -> None:
        dl.add_box(
            20,
            20,
            88,
            88,
            color=(1.0, 0.0, 0.0, 0.5),
            border_width=10.0,
            border_color=(1.0, 0.0, 0.0, 0.5),
        )

    frame, _ = render_scene(paint)
    ring = int(frame[64, 25, 0])
    interior = int(frame[64, 64, 0])
    assert abs(ring - interior) < 12, f"ring {ring} vs interior {interior}"


# --------------------------------------------------------------- clipping


def test_clip_rect_removes_content_outside_it(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_box(0, 0, 128, 128, color=RED, clip=(40, 40, 40, 40))

    frame, _ = render_scene(paint)
    assert frame[60, 60, 0] > 200, "inside the clip should be drawn"
    assert frame[10, 10, 0] < 50, "outside the clip should be removed"
    assert frame[110, 110, 0] < 50


def test_rounded_clip_cuts_corners(render_scene) -> None:
    """Something a scissor rect cannot express at all."""

    def paint(dl: DisplayList) -> None:
        dl.add_box(
            0,
            0,
            128,
            128,
            color=RED,
            clip=(30, 30, 68, 68),
            clip_radii=(30, 30, 30, 30),
        )

    frame, _ = render_scene(paint)
    assert frame[64, 64, 0] > 200, "clip interior missing"
    assert frame[33, 33, 0] < 60, "clip corner was not rounded"


def test_zero_size_clip_means_unclipped(render_scene) -> None:
    frame, _ = render_scene(lambda dl: dl.add_box(0, 0, 128, 128, color=RED, clip=(0, 0, 0, 0)))
    assert frame[64, 64, 0] > 200
    assert frame[5, 5, 0] > 200


# ------------------------------------------------------------------ theme


def test_palette_token_resolves_to_the_theme_colour(render_scene) -> None:
    """A token index in flags is looked up in the palette storage buffer, which
    is what makes a theme switch a single buffer upload."""
    theme = Theme(seed="#6750A4", dark=True)
    palette = Palette(theme)
    index = palette.index("primary")
    expected = [linear_to_srgb8(c) for c in palette.linear("primary")[:3]]

    frame, _ = render_scene(lambda dl: dl.add_box(20, 20, 88, 88, token=index), theme=theme)
    assert frame[64, 64, :3].astype(float) == pytest.approx(expected, abs=2.0)


# --------------------------------------------------- ordering and batching


def test_later_instances_paint_over_earlier_ones(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_box(20, 20, 80, 80, color=RED)
        dl.add_box(40, 40, 40, 40, color=BLUE)

    frame, _ = render_scene(paint)
    assert tuple(frame[64, 64, :3]) == (0, 0, 255), "paint order not respected"
    assert tuple(frame[25, 25, :3]) == (255, 0, 0)


def test_many_primitives_are_one_draw_call(render_scene) -> None:
    """The central design constraint. 500 mixed primitives, one draw."""

    def paint(dl: DisplayList) -> None:
        for i in range(200):
            dl.add_box(i % 100, i % 100, 10, 10, color=RED, radii=(2, 2, 2, 2))
        for i in range(200):
            dl.add_shadow(i % 100, i % 100, 10, 10, blur=4.0)
        for i in range(100):
            dl.add_glyph(i, i, 4, 6, uv=(0, 0, 1, 1), color=GREEN)

    _, engine = render_scene(paint)
    assert engine.instance_count == 500


def test_alpha_blending_composites_correctly(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_box(0, 0, 128, 128, color=(0.0, 0.0, 0.0, 1.0))
        dl.add_box(0, 0, 128, 128, color=(1.0, 1.0, 1.0, 0.5))

    frame, _ = render_scene(paint)
    grey = int(frame[64, 64, 0])
    assert 100 < grey < 220, f"half-transparent white over black gave {grey}"


# ----------------------------------------------------------------- shadow


def test_shadow_is_soft_at_its_edge(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_shadow(40, 40, 48, 48, blur=10.0, color=(0.0, 0.0, 0.0, 1.0))

    frame, engine = render_scene(paint)
    assert engine.instance_count == 1
    centre = int(frame[64, 64, 0])
    edge = int(frame[64, 92, 0])
    far = int(frame[64, 120, 0])
    assert centre < edge < far, f"no shadow falloff: {centre}, {edge}, {far}"


def test_shadow_offset_shifts_it(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_shadow(40, 40, 48, 48, blur=6.0, offset=(12.0, 0.0), color=(0.0, 0.0, 0.0, 1.0))

    frame, _ = render_scene(paint)
    left = int(frame[64, 36, 0])
    right = int(frame[64, 92, 0])
    assert right < left, "shadow did not shift right"


# ---------------------------------------------------------------- segment
#
# No widget draws these yet -- Canvas and node-graph edges, the two the
# `pySilver Widget Backlog` names, are both still unbuilt. These are the M2-
# style acceptance tests for the primitive itself.


def test_segment_fills_its_capsule(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_segment(30, 64, 98, 64, thickness=20.0, color=RED)

    frame, _ = render_scene(paint)
    assert tuple(frame[64, 64, :3]) == (255, 0, 0), "midpoint should be filled"


def test_outside_the_segment_is_untouched(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_segment(30, 64, 98, 64, thickness=20.0, color=RED)

    frame, _ = render_scene(paint)
    assert frame[10, 64, 0] < 50, "segment leaked far above its line"


def test_thickness_bounds_the_stroke(render_scene) -> None:
    """thickness=20 means a 10px radius either side of the line, at a point
    away from both caps where only the perpendicular distance matters."""

    def paint(dl: DisplayList) -> None:
        dl.add_segment(30, 64, 98, 64, thickness=20.0, color=RED)

    frame, _ = render_scene(paint)
    assert frame[64 + 9, 64, 0] > 200, "9px off-axis should still be inside"
    assert frame[64 + 15, 64, 0] < 50, "15px off-axis should be outside a 10px-radius stroke"


def test_the_cap_is_round_not_square(render_scene) -> None:
    """A butt/flat cap would stop dead at x=98. A capsule's round cap bulges
    past it by up to the radius -- the same distance field property that gives
    `add_arc`'s ends their curve with no extra geometry."""

    def paint(dl: DisplayList) -> None:
        dl.add_segment(30, 64, 98, 64, thickness=20.0, color=RED)

    frame, _ = render_scene(paint)
    # 7px straight past the endpoint, on axis: inside a 10px-radius cap.
    assert frame[64, 105, 0] > 200, "round cap did not bulge past the endpoint"
    # (107, 64+9): outside the 10px-radius circle around the endpoint
    # (distance ~12.7), but inside the square a naive bounding-box-shaped cap
    # would wrongly paint (x within [98, 108], y within [54, 74]).
    assert frame[64 + 9, 107, 0] < 50, "cap reads square rather than round"


def test_past_the_cap_is_untouched(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_segment(30, 64, 98, 64, thickness=20.0, color=RED)

    frame, _ = render_scene(paint)
    assert frame[64, 115, 0] < 50, "17px past the endpoint should be well outside the cap"


def test_a_zero_length_segment_paints_a_disc(render_scene) -> None:
    """The degenerate `a == b` case the shader's `max(dot(ba, ba), 1e-6)`
    guards -- it must not divide by zero and vanish."""

    def paint(dl: DisplayList) -> None:
        dl.add_segment(64, 64, 64, 64, thickness=20.0, color=RED)

    frame, _ = render_scene(paint)
    assert tuple(frame[64, 64, :3]) == (255, 0, 0)
    assert frame[64, 64 + 15, 0] < 50, "disc radius should still be bounded by the thickness"


def test_segment_respects_its_clip(render_scene) -> None:
    def paint(dl: DisplayList) -> None:
        dl.add_segment(0, 64, 128, 64, thickness=20.0, color=RED, clip=(0, 0, 64, 128))

    frame, _ = render_scene(paint)
    assert tuple(frame[64, 30, :3]) == (255, 0, 0), "inside the clip should be drawn"
    assert frame[64, 100, 0] < 50, "outside the clip should be removed"


# ------------------------------------------------------------------- images


def _bound_atlas(engine, rgba: np.ndarray):
    """An ImageAtlas holding one swatch, bound to `engine`'s real pipeline in
    place of the 1x1 placeholder.

    Nothing in the running framework does this yet -- no widget draws
    `Kind.IMAGE` -- so this is the seam `bind_image_atlas` exists for,
    exercised directly the way M2 exercised `Kind.BOX` and `Kind.SHADOW`
    before any widget existed to call them.
    """
    from pysilver.render.atlas import ImageAtlas

    atlas = ImageAtlas(engine.device, size=64)
    entry = atlas.add("swatch", rgba)
    atlas.upload()
    engine.pipeline.bind_image_atlas(atlas.texture)
    return entry, atlas.size


def test_an_opaque_image_paints_its_pixels(offscreen_engine) -> None:
    """The whole path: decode (stood in for by a synthetic array, since the
    atlas is decode-agnostic), pack, upload, bind, sample, blend."""
    engine = offscreen_engine(width=128, height=128)
    swatch = np.full((8, 8, 4), (0, 200, 0, 255), dtype=np.uint8)
    entry, size = _bound_atlas(engine, swatch)

    def paint(dl: DisplayList) -> None:
        dl.add_image(20, 20, 60, 60, uv=entry.uv(size))

    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    frame = np.asarray(engine.canvas.draw())
    assert tuple(frame[50, 50, :3]) == (0, 200, 0)


def test_outside_the_image_is_untouched(offscreen_engine) -> None:
    engine = offscreen_engine(width=128, height=128)
    entry, size = _bound_atlas(engine, np.full((8, 8, 4), (0, 200, 0, 255), dtype=np.uint8))

    def paint(dl: DisplayList) -> None:
        dl.add_image(20, 20, 60, 60, uv=entry.uv(size))

    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    frame = np.asarray(engine.canvas.draw())
    assert frame[5, 5, 1] < 50, "image leaked outside its rect"


def test_a_tint_multiplies_a_white_texel(offscreen_engine) -> None:
    """`color = premultiply(texel * fill)` -- a white swatch tinted blue must
    come out exactly blue. This is what lets one image be recoloured, the way
    an icon's glyph coverage is tinted by its fill."""
    engine = offscreen_engine(width=128, height=128)
    entry, size = _bound_atlas(engine, np.full((8, 8, 4), 255, dtype=np.uint8))

    def paint(dl: DisplayList) -> None:
        dl.add_image(20, 20, 60, 60, uv=entry.uv(size), tint=BLUE)

    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    frame = np.asarray(engine.canvas.draw())
    assert tuple(frame[50, 50, :3]) == (0, 0, 255)


def test_a_fully_transparent_texel_leaves_the_background(offscreen_engine) -> None:
    """Straight, non-premultiplied alpha is the documented contract: a texel
    with alpha 0 must vanish entirely regardless of its RGB, which is only
    true if the atlas was never asked to premultiply on the way in."""
    engine = offscreen_engine(width=128, height=128, theme=Theme(dark=True))
    entry, size = _bound_atlas(engine, np.full((8, 8, 4), (255, 0, 0, 0), dtype=np.uint8))
    surface = tuple(round(linear_to_srgb8(c)) for c in engine.palette.linear("surface")[:3])

    def paint(dl: DisplayList) -> None:
        dl.add_image(20, 20, 60, 60, uv=entry.uv(size))

    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    frame = np.asarray(engine.canvas.draw())
    assert tuple(frame[50, 50, :3]) == pytest.approx(surface, abs=2)


def test_an_image_respects_its_clip(offscreen_engine) -> None:
    engine = offscreen_engine(width=128, height=128)
    entry, size = _bound_atlas(engine, np.full((8, 8, 4), (0, 200, 0, 255), dtype=np.uint8))

    def paint(dl: DisplayList) -> None:
        dl.add_image(0, 0, 128, 128, uv=entry.uv(size), clip=(0, 0, 64, 128))

    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    frame = np.asarray(engine.canvas.draw())
    assert tuple(frame[64, 30, :3]) == (0, 200, 0), "inside the clip should be drawn"
    assert frame[64, 100, 1] < 50, "outside the clip should be removed"


def test_an_image_honours_its_own_corner_radius(offscreen_engine) -> None:
    """`Image`/`Video`'s `style.corner_radius` reached `add_image`'s own
    `radii` field, but the KIND_IMAGE fragment-shader branch never read it --
    every image painted with square corners regardless (found live via the
    Image widget demo's `corner_radius: 12` example, which rendered with
    plainly square corners). Mirrors `test_rounded_corner_removes_the_square_
    corner`'s KIND_BOX assertion shape for KIND_IMAGE instead."""
    engine = offscreen_engine(width=128, height=128)
    entry, size = _bound_atlas(engine, np.full((8, 8, 4), (0, 200, 0, 255), dtype=np.uint8))

    def paint(dl: DisplayList) -> None:
        dl.add_image(20, 20, 60, 60, uv=entry.uv(size), radii=(20, 20, 20, 20))

    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    frame = np.asarray(engine.canvas.draw())
    assert frame[22, 22, 1] < 50, "corner was not rounded away"
    assert tuple(frame[50, 50, :3]) == (0, 200, 0), "centre should still be filled"
