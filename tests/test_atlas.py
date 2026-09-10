"""Skyline packing and the glyph atlas. GPU-free."""

from __future__ import annotations

import numpy as np
import pytest

from pysilver.render.atlas import PADDING, AtlasFullError, GlyphAtlas, ImageAtlas, SkylinePacker
from pysilver.text import FontDB, FontRequest


@pytest.fixture(scope="module")
def face():
    return FontDB().face_for(FontRequest())


# ----------------------------------------------------------------- packer


def test_first_allocation_is_top_left() -> None:
    assert SkylinePacker(64, 64).allocate(10, 10) == (0, 0)


def test_allocations_do_not_overlap() -> None:
    packer = SkylinePacker(64, 64)
    rects = [(*packer.allocate(w, h), w, h) for w, h in [(20, 10), (20, 10), (30, 20), (8, 8)]]
    for i, (x0, y0, w0, h0) in enumerate(rects):
        for x1, y1, w1, h1 in rects[i + 1 :]:
            separated = x0 + w0 <= x1 or x1 + w1 <= x0 or y0 + h0 <= y1 or y1 + h1 <= y0
            assert separated, f"{rects[i]} overlaps {(x1, y1, w1, h1)}"


def test_allocations_stay_in_bounds() -> None:
    packer = SkylinePacker(32, 32)
    for _ in range(8):
        x, y = packer.allocate(7, 7)
        assert x >= 0 and x + 7 <= 32
        assert y >= 0 and y + 7 <= 32


def test_too_wide_raises() -> None:
    with pytest.raises(AtlasFullError):
        SkylinePacker(32, 32).allocate(64, 8)


def test_exhaustion_raises() -> None:
    packer = SkylinePacker(16, 16)
    with pytest.raises(AtlasFullError):
        for _ in range(100):
            packer.allocate(8, 8)


def test_zero_sized_allocation_is_free() -> None:
    packer = SkylinePacker(16, 16)
    assert packer.allocate(0, 0) == (0, 0)
    assert packer.occupancy == 0


def test_reset_reclaims_everything() -> None:
    packer = SkylinePacker(32, 32)
    packer.allocate(30, 30)
    packer.reset()
    assert packer.allocate(30, 30) == (0, 0)


# ------------------------------------------------------------------ atlas


def test_packs_glyphs_and_writes_pixels(face) -> None:
    atlas = GlyphAtlas(size=256)
    for ch in "Hello":
        atlas.get(face, face.glyph_for(ord(ch)), 24.0)
    assert len(atlas) == 4  # H e l o
    assert atlas.pixels.max() > 0


def test_blank_glyphs_consume_no_space(face) -> None:
    atlas = GlyphAtlas(size=128)
    entry = atlas.get(face, face.glyph_for(ord(" ")), 24.0)
    assert entry.is_blank
    assert atlas.occupancy == 0


def test_repeat_lookups_hit_the_cache(face) -> None:
    atlas = GlyphAtlas(size=128)
    gid = face.glyph_for(ord("A"))
    first = atlas.get(face, gid, 24.0)
    assert atlas.get(face, gid, 24.0) is first
    assert len(atlas) == 1


def test_size_and_subpixel_are_separate_entries(face) -> None:
    atlas = GlyphAtlas(size=256)
    gid = face.glyph_for(ord("A"))
    atlas.get(face, gid, 12.0, 0)
    atlas.get(face, gid, 24.0, 0)
    atlas.get(face, gid, 12.0, 1)
    assert len(atlas) == 3


def test_coords_are_part_of_the_key(face) -> None:
    """A filled and an unfilled icon are the same glyph id at the same size,
    and would collide without `coords` in the key -- see `GlyphAtlas.get`."""
    atlas = GlyphAtlas(size=256)
    gid = face.glyph_for(ord("A"))
    atlas.get(face, gid, 24.0, 0, (0.0,))
    atlas.get(face, gid, 24.0, 0, (1.0,))
    assert len(atlas) == 2


def test_uv_is_normalised_and_ordered(face) -> None:
    atlas = GlyphAtlas(size=256)
    entry = atlas.get(face, face.glyph_for(ord("W")), 32.0)
    u0, v0, u1, v1 = entry.uv(256)
    assert 0.0 <= u0 < u1 <= 1.0
    assert 0.0 <= v0 < v1 <= 1.0


def test_glyphs_are_padded_apart(face) -> None:
    """Without padding, linear filtering bleeds a neighbour's coverage."""
    atlas = GlyphAtlas(size=256)
    a = atlas.get(face, face.glyph_for(ord("M")), 20.0)
    b = atlas.get(face, face.glyph_for(ord("W")), 20.0)
    assert b.x >= a.x + a.width + PADDING or b.y >= a.y + a.height + PADDING


def test_glyph_edges_are_extruded_into_padding(face) -> None:
    """Bilinear sampling at a UV boundary blends with whatever is just past
    this glyph's own texels. Left as transparent padding, that blends the
    outermost row of real antialiasing coverage toward zero on every edge --
    reported live as antialiasing looking cut off, worst on small glyphs.
    Extruding the edge into the padding fixes what the blend lands on
    without changing the glyph's own declared rect."""
    atlas = GlyphAtlas(size=256)
    gid = face.glyph_for(ord("g"))
    bitmap = face.rasterize(gid, 14.0)
    entry = atlas.get(face, gid, 14.0)
    x, y, w, h = entry.x, entry.y, entry.width, entry.height
    assert np.array_equal(atlas.pixels[y : y + h, x + w], bitmap.coverage[:, -1])
    assert np.array_equal(atlas.pixels[y + h, x : x + w], bitmap.coverage[-1, :])
    if x > 0:
        assert np.array_equal(atlas.pixels[y : y + h, x - 1], bitmap.coverage[:, 0])
    if y > 0:
        assert np.array_equal(atlas.pixels[y - 1, x : x + w], bitmap.coverage[0, :])


def test_overflow_resets_and_keeps_working(face) -> None:
    """Eviction is wholesale: the skyline cannot free individual rectangles."""
    atlas = GlyphAtlas(size=64)
    entries = [atlas.get(face, face.glyph_for(ord(c)), 28.0) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    assert atlas.resets >= 1
    assert atlas.generation >= 1
    assert entries[-1].generation == atlas.generation


def test_stale_entries_are_refreshed_after_a_reset(face) -> None:
    atlas = GlyphAtlas(size=128)
    gid = face.glyph_for(ord("A"))
    stale = atlas.get(face, gid, 20.0)
    atlas.reset()
    fresh = atlas.get(face, gid, 20.0)
    assert fresh.generation > stale.generation


def test_reset_clears_the_image(face) -> None:
    atlas = GlyphAtlas(size=128)
    atlas.get(face, face.glyph_for(ord("A")), 24.0)
    atlas.reset()
    assert np.all(atlas.pixels == 0)
    assert len(atlas) == 0


def test_upload_is_a_noop_without_a_device() -> None:
    assert GlyphAtlas(size=64).upload() is False


# ------------------------------------------------------------ image atlas


def rgba(w: int, h: int, colour: tuple[int, int, int, int] = (255, 0, 0, 255)) -> np.ndarray:
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[:, :] = colour
    return out


def test_packing_an_image_writes_its_pixels() -> None:
    atlas = ImageAtlas(size=256)
    entry = atlas.add("swatch", rgba(20, 10))
    assert entry.width == 20 and entry.height == 10
    assert tuple(atlas.pixels[entry.y, entry.x]) == (255, 0, 0, 255)


def test_get_or_add_repeat_lookups_hit_the_cache() -> None:
    """get_or_add must not call the loader again once cached -- the whole
    point, since a loader may be an expensive disk read."""
    atlas = ImageAtlas(size=256)
    calls = []

    def loader() -> np.ndarray:
        calls.append(1)
        return rgba(8, 8)

    first = atlas.get_or_add("a", loader)
    second = atlas.get_or_add("a", loader)
    assert first == second
    assert len(calls) == 1


def test_different_keys_are_different_entries() -> None:
    atlas = ImageAtlas(size=256)
    a = atlas.add("a", rgba(8, 8))
    b = atlas.add("b", rgba(8, 8))
    assert (a.x, a.y) != (b.x, b.y)


def test_re_adding_a_key_replaces_it() -> None:
    atlas = ImageAtlas(size=256)
    atlas.add("k", rgba(8, 8, (255, 0, 0, 255)))
    atlas.add("k", rgba(8, 8, (0, 255, 0, 255)))
    entry = atlas.get_or_add("k", lambda: rgba(8, 8, (0, 0, 255, 255)))
    assert tuple(atlas.pixels[entry.y, entry.x]) == (0, 255, 0, 255)


def test_images_are_padded_apart() -> None:
    atlas = ImageAtlas(size=256)
    a = atlas.add("a", rgba(20, 20))
    b = atlas.add("b", rgba(20, 20))
    assert b.x >= a.x + a.width + PADDING or b.y >= a.y + a.height + PADDING


def test_image_uv_is_normalised_and_ordered() -> None:
    atlas = ImageAtlas(size=256)
    entry = atlas.add("a", rgba(30, 40))
    u0, v0, u1, v1 = entry.uv(256)
    assert 0.0 <= u0 < u1 <= 1.0
    assert 0.0 <= v0 < v1 <= 1.0


def test_image_overflow_resets_and_keeps_working() -> None:
    """Eviction is wholesale, exactly as for glyphs -- the skyline cannot
    free individual rectangles."""
    atlas = ImageAtlas(size=64)
    entries = [atlas.add(i, rgba(20, 20)) for i in range(20)]
    assert atlas.resets >= 1
    assert atlas.generation >= 1
    assert entries[-1].generation == atlas.generation


def test_an_image_larger_than_the_atlas_raises() -> None:
    from pysilver.render.atlas import AtlasFullError

    with pytest.raises(AtlasFullError):
        ImageAtlas(size=64).add("too-big", rgba(200, 200))


def test_image_reset_clears_the_atlas() -> None:
    atlas = ImageAtlas(size=64)
    atlas.add("a", rgba(8, 8))
    atlas.reset()
    assert np.all(atlas.pixels == 0)
    assert len(atlas) == 0


def test_contains_reflects_generation_not_just_presence() -> None:
    atlas = ImageAtlas(size=64)
    atlas.add("a", rgba(8, 8))
    assert "a" in atlas
    atlas.reset()
    assert "a" not in atlas, "the key is still in the dict but its generation is stale"


def test_image_upload_is_a_noop_without_a_device() -> None:
    assert ImageAtlas(size=64).upload() is False


def test_a_non_rgba_array_is_rejected() -> None:
    atlas = ImageAtlas(size=64)
    with pytest.raises(ValueError, match="RGBA"):
        atlas.add("bad", np.zeros((8, 8, 3), dtype=np.uint8))


def test_a_non_uint8_array_is_rejected() -> None:
    atlas = ImageAtlas(size=64)
    with pytest.raises(ValueError, match="uint8"):
        atlas.add("bad", np.zeros((8, 8, 4), dtype=np.float32))


# ------------------------------------------------------- image atlas: update


def test_update_on_a_miss_packs_fresh() -> None:
    atlas = ImageAtlas(size=256)
    entry = atlas.update("frame", rgba(80, 40))
    assert entry.width == 80 and entry.height == 40


def test_update_with_the_same_shape_overwrites_in_place() -> None:
    atlas = ImageAtlas(size=256)
    first = atlas.update("frame", rgba(80, 40, (255, 0, 0, 255)))
    second = atlas.update("frame", rgba(80, 40, (0, 255, 0, 255)))
    assert (second.x, second.y) == (first.x, first.y), "same shape must not reallocate"
    assert tuple(atlas.pixels[second.y, second.x]) == (0, 255, 0, 255)


def test_update_does_not_touch_the_packer_on_a_hit() -> None:
    """The whole point: a same-shape update is a pixel write, not an
    allocation -- repeating it must not grow occupancy or generation."""
    atlas = ImageAtlas(size=256)
    atlas.update("frame", rgba(80, 40))
    occupancy_after_first = atlas._packer.occupancy
    for _ in range(50):
        atlas.update("frame", rgba(80, 40))
    assert atlas._packer.occupancy == occupancy_after_first
    assert atlas.generation == 0


def test_update_with_a_different_shape_reallocates() -> None:
    atlas = ImageAtlas(size=256)
    first = atlas.update("frame", rgba(80, 40))
    second = atlas.update("frame", rgba(40, 20))
    assert (second.width, second.height) == (40, 20)
    assert (second.x, second.y) != (first.x, first.y)


def test_update_after_a_reset_repacks_rather_than_reusing_stale_coordinates() -> None:
    atlas = ImageAtlas(size=64)
    atlas.update("frame", rgba(20, 20))
    atlas.reset()
    repacked = atlas.update("frame", rgba(20, 20, (0, 0, 255, 255)))
    assert repacked.generation == atlas.generation
    assert tuple(atlas.pixels[repacked.y, repacked.x]) == (0, 0, 255, 255)


def test_update_rejects_the_same_shapes_add_does() -> None:
    atlas = ImageAtlas(size=64)
    with pytest.raises(ValueError, match="RGBA"):
        atlas.update("bad", np.zeros((8, 8, 3), dtype=np.uint8))
    with pytest.raises(ValueError, match="uint8"):
        atlas.update("bad", np.zeros((8, 8, 4), dtype=np.float32))
