"""Skyline packing into the two atlas textures the pipeline binds.

Keeping every glyph -- or every image -- in one texture is what preserves the
single-draw-call property (ARCHITECTURE.md 5.8): a per-glyph or per-image
texture would force a bind group switch, and therefore a draw call, per one.

:class:`SkylinePacker` is generic and knows nothing about glyphs or pixels; it
places rectangles. :class:`GlyphAtlas` and :class:`ImageAtlas` are thin,
independent owners built on it, each with its own texture, cache and wholesale
eviction. Deliberately not one shared base: a glyph atlas rasterises through
FreeType and keys on shaping parameters, an image atlas accepts pixels a
caller already decoded and keys on whatever identifies the source, and forcing
a common parent over that difference would buy an abstraction for its own
sake rather than for a shared problem.

The packer is deliberately GPU-free and tested without a window; only the two
atlas classes touch wgpu.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import numpy as np

if TYPE_CHECKING:
    # Deferred: `text` imports `GlyphAtlas` from this module, so importing
    # `text.font` back at module load time is a real cycle, not just a slow
    # one -- whichever side loads first finds the other mid-initialization.
    # `Face`/`GlyphBitmap` are used only as parameter annotations here, and
    # `from __future__ import annotations` already makes every annotation a
    # string, so deferring the import to type-checking time costs nothing.
    from ..text.font import Face, GlyphBitmap

__all__ = [
    "AtlasEntry",
    "AtlasFullError",
    "GlyphAtlas",
    "ImageAtlas",
    "ImageEntry",
    "ImageKey",
    "SkylinePacker",
]

#: (font path, quarter-pixel size, glyph id, subpixel bucket, axis coords)
AtlasKey = tuple[Path, int, int, int, tuple[float, ...]]

#: One transparent pixel between glyphs. Without it, linear filtering samples a
#: neighbour's coverage along shared edges and glyphs grow faint halos.
PADDING: Final = 1


class AtlasFullError(RuntimeError):
    """Raised when a glyph cannot be placed in the remaining space."""


@dataclass(frozen=True, slots=True)
class AtlasEntry:
    """Where a rasterised glyph lives, and how to place it when drawing."""

    x: int
    y: int
    width: int
    height: int
    left: float  # bearing from the pen position
    top: float  # bearing above the baseline
    generation: int

    def uv(self, atlas_size: int) -> tuple[float, float, float, float]:
        return _uv_rect(self.x, self.y, self.width, self.height, atlas_size)

    @property
    def is_blank(self) -> bool:
        return self.width == 0 or self.height == 0


def _uv_rect(
    x: int, y: int, width: int, height: int, atlas_size: int
) -> tuple[float, float, float, float]:
    s = float(atlas_size)
    return (x / s, y / s, (x + width) / s, (y + height) / s)


class SkylinePacker:
    """Bottom-left skyline rectangle packer.

    Chosen over a shelf packer because glyph heights vary continuously with font
    size; shelves would waste most of a row whenever one tall glyph opened it.
    """

    __slots__ = ("_skyline", "height", "width")

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        # (x, y, width) spans, left to right, covering the full width.
        self._skyline: list[tuple[int, int, int]] = [(0, 0, width)]

    def reset(self) -> None:
        self._skyline = [(0, 0, self.width)]

    @property
    def occupancy(self) -> float:
        """Fraction of the atlas height consumed by the tallest skyline point."""
        return max((y for _, y, _ in self._skyline), default=0) / self.height

    def _fit(self, index: int, width: int, height: int) -> int | None:
        """Lowest y at which a rect of *width* fits starting at span *index*."""
        x = self._skyline[index][0]
        if x + width > self.width:
            return None
        y = 0
        remaining = width
        i = index
        while remaining > 0:
            if i >= len(self._skyline):
                return None
            span_x, span_y, span_w = self._skyline[i]
            y = max(y, span_y)
            if y + height > self.height:
                return None
            remaining -= span_w - max(0, x - span_x)
            i += 1
        return y

    def allocate(self, width: int, height: int) -> tuple[int, int]:
        """Place a rect and return its top-left. Raises :class:`AtlasFullError`."""
        if width <= 0 or height <= 0:
            return (0, 0)
        best: tuple[int, int, int] | None = None  # (y, x, index)
        for i in range(len(self._skyline)):
            y = self._fit(i, width, height)
            if y is None:
                continue
            x = self._skyline[i][0]
            if best is None or (y, x) < (best[0], best[1]):
                best = (y, x, i)
        if best is None:
            raise AtlasFullError(f"cannot place {width}x{height} in {self.width}x{self.height}")

        y, x, index = best
        self._insert(index, x, y + height, width)
        return (x, y)

    def _insert(self, index: int, x: int, top: int, width: int) -> None:
        skyline = self._skyline
        skyline.insert(index, (x, top, width))
        # Trim spans the new node covers.
        i = index + 1
        while i < len(skyline):
            sx, sy, sw = skyline[i]
            prev_end = skyline[i - 1][0] + skyline[i - 1][2]
            if sx >= prev_end:
                break
            shrink = prev_end - sx
            if sw <= shrink:
                skyline.pop(i)
                continue
            skyline[i] = (sx + shrink, sy, sw - shrink)
            break
        # Merge neighbours at the same height.
        i = 0
        while i < len(skyline) - 1:
            if skyline[i][1] == skyline[i + 1][1]:
                x0, y0, w0 = skyline[i]
                skyline[i] = (x0, y0, w0 + skyline[i + 1][2])
                skyline.pop(i + 1)
            else:
                i += 1


class GlyphAtlas:
    """CPU-side atlas image plus its GPU texture.

    Eviction is **wholesale**: a skyline allocator cannot free individual
    rectangles, so a full atlas is cleared and repopulated on demand. A
    generation counter invalidates entries handed out before the reset, which
    is why callers must not cache an :class:`AtlasEntry` across frames without
    checking it.
    """

    __slots__ = (
        "_cache",
        "_device",
        "_dirty",
        "_generation",
        "_packer",
        "_pixels",
        "_resets",
        "_texture",
        "size",
    )

    def __init__(self, device: Any = None, size: int = 1024) -> None:
        self.size = size
        self._packer = SkylinePacker(size, size)
        self._pixels = np.zeros((size, size), dtype=np.uint8)
        self._cache: dict[AtlasKey, AtlasEntry] = {}
        self._generation = 0
        self._resets = 0
        self._dirty = True
        self._device = device
        self._texture: Any = None
        if device is not None:
            self._create_texture()

    # ------------------------------------------------------------ CPU side

    @property
    def pixels(self) -> np.ndarray:
        return self._pixels

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def resets(self) -> int:
        return self._resets

    @property
    def occupancy(self) -> float:
        return self._packer.occupancy

    def __len__(self) -> int:
        return len(self._cache)

    def reset(self) -> None:
        self._packer.reset()
        self._pixels[:] = 0
        self._cache.clear()
        self._generation += 1
        self._resets += 1
        self._dirty = True

    def add(self, key: AtlasKey, bitmap: GlyphBitmap) -> AtlasEntry:
        if bitmap.is_blank:
            entry = AtlasEntry(0, 0, 0, 0, bitmap.left, bitmap.top, self._generation)
            self._cache[key] = entry
            return entry

        w, h = bitmap.width, bitmap.height
        try:
            x, y = self._packer.allocate(w + PADDING, h + PADDING)
        except AtlasFullError:
            self.reset()
            x, y = self._packer.allocate(w + PADDING, h + PADDING)

        self._pixels[y : y + h, x : x + w] = bitmap.coverage
        # Extrude the glyph's own edge pixels one row/column into its padding
        # border, on all four sides. A UV boundary sample blends toward
        # whatever is just past this glyph's own texels, and left
        # unextruded that is always transparent -- this glyph's own reserved
        # right/bottom padding, or blank atlas space to its left/top -- so
        # bilinear filtering blended the outermost row of real antialiasing
        # coverage toward zero on every glyph's every edge. Reported live as
        # "the antialiasing for 1 pixel row is being cut off on all glyphs",
        # worse the smaller the glyph since one lost row is a bigger
        # fraction of it. Extruding means that boundary blends toward a
        # duplicate of the true edge value instead of toward nothing.
        self._pixels[y : y + h, x + w] = bitmap.coverage[:, -1]
        self._pixels[y + h, x : x + w] = bitmap.coverage[-1, :]
        self._pixels[y + h, x + w] = bitmap.coverage[-1, -1]
        if x > 0:
            self._pixels[y : y + h, x - 1] = bitmap.coverage[:, 0]
            self._pixels[y + h, x - 1] = bitmap.coverage[-1, 0]
        if y > 0:
            self._pixels[y - 1, x : x + w] = bitmap.coverage[0, :]
            self._pixels[y - 1, x + w] = bitmap.coverage[0, -1]
        if x > 0 and y > 0:
            self._pixels[y - 1, x - 1] = bitmap.coverage[0, 0]
        entry = AtlasEntry(x, y, w, h, bitmap.left, bitmap.top, self._generation)
        self._cache[key] = entry
        self._dirty = True
        return entry

    def get(
        self,
        face: Face,
        gid: int,
        px: float,
        subpixel: int = 0,
        coords: tuple[float, ...] = (),
    ) -> AtlasEntry:
        """Entry for a glyph, rasterising and packing it on first use.

        ``coords`` is part of the key: a filled and an unfilled icon are the
        same glyph id at the same size, and would otherwise collide.
        """
        key = (face.path, round(px * 4), int(gid), subpixel, coords)
        entry = self._cache.get(key)
        if entry is not None and entry.generation == self._generation:
            return entry
        return self.add(key, face.rasterize(gid, px, subpixel, coords))

    # ------------------------------------------------------------ GPU side

    @property
    def texture(self) -> Any:
        return self._texture

    def attach_device(self, device: Any) -> None:
        """Give a CPU-only atlas a GPU texture.

        Lets an App own one atlas whether or not it is running on a window --
        headless tests share the same code path as a live application.
        """
        if self._device is device:
            return
        self._device = device
        self._create_texture()
        self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    def _create_texture(self) -> None:
        import wgpu

        self._texture = self._device.create_texture(
            size=(self.size, self.size, 1),
            format=wgpu.TextureFormat.r8unorm,
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )

    def destroy(self) -> None:
        """Release the GPU texture. The CPU image stays, so an atlas can be
        re-attached to a new device without re-rasterising anything."""
        if self._texture is not None:
            self._texture.destroy()
            self._texture = None
        self._device = None

    def upload(self) -> bool:
        """Push the CPU image to the GPU if it changed. Returns whether it did."""
        if self._device is None or not self._dirty:
            return False
        self._device.queue.write_texture(
            {"texture": self._texture},
            np.ascontiguousarray(self._pixels),
            {"bytes_per_row": self.size, "rows_per_image": self.size},
            (self.size, self.size, 1),
        )
        self._dirty = False
        return True


#: Whatever identifies a source image to a caller -- a resolved path, a
#: (path, mtime) pair for a hot-reloadable one, a content hash. The atlas
#: only ever uses it as a dict key and has no opinion about what it means.
ImageKey = Hashable


@dataclass(frozen=True, slots=True)
class ImageEntry:
    """Where a packed image lives, and how to sample it.

    Deliberately not :class:`AtlasEntry`: that carries `left`/`top` glyph
    bearings -- the pen offset a rasteriser reports -- which have no meaning
    for an image placed directly at a widget's rect. Reusing it would mean
    two meaningless zero fields on every entry.
    """

    x: int
    y: int
    width: int
    height: int
    generation: int

    def uv(self, atlas_size: int) -> tuple[float, float, float, float]:
        return _uv_rect(self.x, self.y, self.width, self.height, atlas_size)


class ImageAtlas:
    """CPU-side RGBA atlas image plus its GPU texture.

    The counterpart to :class:`GlyphAtlas` for `Kind.IMAGE`
    (`paint/display_list.py`) -- built on the same :class:`SkylinePacker`,
    with the same wholesale-eviction contract, but decode-agnostic: this class
    never opens a file or touches Pillow. A caller decodes (`Image.open(...).
    convert("RGBA")` and `np.asarray`, already a hard dependency) and hands
    over **straight, non-premultiplied** RGBA -- the fragment shader computes
    `premultiply(texel * fill)` itself, so a premultiplied source would be
    darkened twice at every partially transparent pixel.

    Kept decode-agnostic on purpose: it is what makes this trivially testable
    with synthetic numpy arrays and lets a future Canvas or video widget hand
    over pixels from anywhere -- a decoded file, a generated pattern, a
    rendered frame -- through one path.

    **RGBA is four bytes a pixel against the glyph atlas's one**, so the same
    default size (1024²) costs 4x as much VRAM (4 MiB against 1 MiB). Stated
    rather than left to be discovered by a memory profiler; pass a smaller
    `size` for an application that only ever shows a few small images.

    Wired into `Engine` and `App` the same way `TextEngine`'s `GlyphAtlas`
    is: each owns one, bound with `UIPipeline.bind_image_atlas` the way
    `bind_glyph_atlas` already was. `Image` calls `add`/`get_or_add` (one
    decode, cached); `Video` calls `update` instead, to avoid packing a
    fresh rectangle 30-60 times a second for a stream landing back in the
    same slot every frame.
    """

    __slots__ = (
        "_cache",
        "_device",
        "_dirty",
        "_generation",
        "_packer",
        "_pixels",
        "_resets",
        "_texture",
        "size",
    )

    def __init__(self, device: Any = None, size: int = 1024) -> None:
        self.size = size
        self._packer = SkylinePacker(size, size)
        self._pixels = np.zeros((size, size, 4), dtype=np.uint8)
        self._cache: dict[ImageKey, ImageEntry] = {}
        self._generation = 0
        self._resets = 0
        self._dirty = True
        self._device = device
        self._texture: Any = None
        if device is not None:
            self._create_texture()

    # ------------------------------------------------------------ CPU side

    @property
    def pixels(self) -> np.ndarray:
        return self._pixels

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def resets(self) -> int:
        return self._resets

    @property
    def occupancy(self) -> float:
        return self._packer.occupancy

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: ImageKey) -> bool:
        entry = self._cache.get(key)
        return entry is not None and entry.generation == self._generation

    def reset(self) -> None:
        self._packer.reset()
        self._pixels[:] = 0
        self._cache.clear()
        self._generation += 1
        self._resets += 1
        self._dirty = True

    def add(self, key: ImageKey, rgba: np.ndarray) -> ImageEntry:
        """Pack *rgba* -- (height, width, 4) uint8, straight alpha -- and
        cache it under *key*, replacing any existing entry.

        An image wider or taller than the atlas itself cannot be packed even
        after a reset, and raises :class:`AtlasFullError`. Deciding what to do
        about that -- downscale, refuse, fall back to a dedicated texture -- is
        a widget's policy choice, not this atlas's; it only packs what fits.
        """
        rgba = np.asarray(rgba)
        if rgba.ndim != 3 or rgba.shape[2] != 4:
            raise ValueError(f"expected an (h, w, 4) RGBA array, got shape {rgba.shape}")
        if rgba.dtype != np.uint8:
            raise ValueError(f"expected uint8, got {rgba.dtype}")

        h, w = rgba.shape[:2]
        try:
            x, y = self._packer.allocate(w + PADDING, h + PADDING)
        except AtlasFullError:
            self.reset()
            x, y = self._packer.allocate(w + PADDING, h + PADDING)

        self._pixels[y : y + h, x : x + w] = rgba
        entry = ImageEntry(x, y, w, h, self._generation)
        self._cache[key] = entry
        self._dirty = True
        return entry

    def get_or_add(self, key: ImageKey, loader: Callable[[], np.ndarray]) -> ImageEntry:
        """Return the cached entry for *key*, calling *loader* only on a miss.

        Named apart from a plain `get` because the miss cost here is not a
        cheap rasterise: `loader` may decode a file from disk, and the whole
        point of the cache is to make sure that happens once.
        """
        entry = self._cache.get(key)
        if entry is not None and entry.generation == self._generation:
            return entry
        return self.add(key, loader())

    def update(self, key: ImageKey, rgba: np.ndarray) -> ImageEntry:
        """Overwrite *key*'s pixels in place when its shape hasn't changed;
        pack it fresh via `add` otherwise.

        `add` always allocates a new rectangle, which is right for "this
        source decoded to a different image" but wrong for a live video
        frame arriving 30-60 times a second at the same resolution: going
        through the packer every call would churn allocations (and
        eventually force a wholesale reset) for pixels that were only ever
        going to land in the same slot. A same-shape overwrite is one numpy
        slice write and touches neither the packer nor the cache dict.

        Falls back to `add` on a genuine miss, a stale generation (the atlas
        was reset since this key was packed), or a size change -- a decoder
        renegotiating resolution mid-stream is exactly "a different image."
        """
        rgba = np.asarray(rgba)
        if rgba.ndim != 3 or rgba.shape[2] != 4:
            raise ValueError(f"expected an (h, w, 4) RGBA array, got shape {rgba.shape}")
        if rgba.dtype != np.uint8:
            raise ValueError(f"expected uint8, got {rgba.dtype}")

        entry = self._cache.get(key)
        h, w = rgba.shape[:2]
        same_shape = entry is not None and (entry.width, entry.height) == (w, h)
        if entry is not None and entry.generation == self._generation and same_shape:
            self._pixels[entry.y : entry.y + h, entry.x : entry.x + w] = rgba
            self._dirty = True
            return entry
        return self.add(key, rgba)

    # ------------------------------------------------------------ GPU side

    @property
    def texture(self) -> Any:
        return self._texture

    def attach_device(self, device: Any) -> None:
        """Give a CPU-only atlas a GPU texture. See `GlyphAtlas.attach_device`."""
        if self._device is device:
            return
        self._device = device
        self._create_texture()
        self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    def _create_texture(self) -> None:
        import wgpu

        # `-srgb`, not plain `rgba8unorm` -- and this is not a style choice.
        # An image comes from a decoder as sRGB-encoded bytes, the same as
        # every other colour source in this codebase (ARCHITECTURE.md 5.6.1
        # makes the identical point about `materialyoucolor`'s output). The
        # render target is `rgba8unorm-srgb`, which treats what it is given as
        # LINEAR and re-encodes on write. Sampling a plain `rgba8unorm` texture
        # does no decode at all, so an sRGB byte would be treated as linear,
        # then re-encoded -- the same double-encoding bug 5.6.1 records for
        # the palette, reappearing here for images. Declaring the texture
        # `-srgb` makes `textureSample` decode it back to linear first, which
        # is what makes the round trip correct. Measured: a swatch written as
        # (0, 200, 0) came back as (0, 229, 0) with the plain format and
        # (0, 200, 0) with this one.
        self._texture = self._device.create_texture(
            size=(self.size, self.size, 1),
            format=wgpu.TextureFormat.rgba8unorm_srgb,
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )

    def destroy(self) -> None:
        """Release the GPU texture. The CPU image stays, so an atlas can be
        re-attached to a new device without re-decoding anything."""
        if self._texture is not None:
            self._texture.destroy()
            self._texture = None
        self._device = None

    def upload(self) -> bool:
        """Push the CPU image to the GPU if it changed. Returns whether it did."""
        if self._device is None or not self._dirty:
            return False
        self._device.queue.write_texture(
            {"texture": self._texture},
            np.ascontiguousarray(self._pixels),
            {"bytes_per_row": self.size * 4, "rows_per_image": self.size},
            (self.size, self.size, 1),
        )
        self._dirty = False
        return True
