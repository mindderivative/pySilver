"""A single decoded raster image.

M3 has no `Image` component -- checked directly against `M3-References`,
the same way every other ungrounded widget this session was; images appear
only as content *inside* other components (Carousel, Cards), never with an
anatomy of their own. Designed instead from the two engine prerequisites
built for exactly this and unused until now: `DisplayList.add_image`
(`Kind.IMAGE`, already a shader branch) and `ImageAtlas` (skyline-packed,
decode-agnostic). This is their first consumer.

**Why `path:` and not `source:`.** `source:` is already view-*composition*
syntax -- `spec/include.py` splices in a fragment wherever it sees that key,
on the raw YAML, before Pydantic ever runs. A widget field reusing the name
would be silently swallowed as an include attempt rather than reaching this
model. `path:` is resolved the way a running process resolves any filesystem
path -- absolute as given, relative to the working directory otherwise --
deliberately **not** relative to the view file `source:` includes confine
themselves to; an application wanting that resolves the path itself before
handing it to a binding.

**No tint.** `add_image`'s `Kind.IMAGE` branch has no palette-token slot --
only `Shape`/`Icon`/every text glyph do, because those clear their own atlas
key on every colour-affecting parameter. Baking a literal tint from
`ctx.palette.linear(...)` would silently stop re-theming on a live palette
swap (`ARCHITECTURE.md` 5's "emit tokens, not colours" rule exists precisely
to prevent that), so an `Image` always shows its own decoded colours; an
application wanting a tinted picture composites it before decoding.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from ..layout import Constraints, EdgeInsets, Offset, Padding, Size
from ..render.atlas import ImageAtlas, ImageEntry
from ..spec import WidgetSpec
from ..tree.element import PaintContext
from .base import _StyledMixin

__all__ = ["ImageElement", "resolve_image"]


def _decode(path: Path) -> np.ndarray:
    """Straight (non-premultiplied) RGBA, as `ImageAtlas.add` requires."""
    return np.asarray(PILImage.open(path).convert("RGBA"))


def resolve_image(
    atlas: ImageAtlas,
    path: str | None,
    *,
    key: Path | None,
    entry: ImageEntry | None,
    label: str,
) -> tuple[Path | None, ImageEntry | None]:
    """`(new_key, new_entry)` for `path`, re-resolving on a changed path or a
    stale atlas generation -- `ImageAtlas.reset` (a wholesale eviction forced
    by some other image needing room) invalidates every entry it packed, not
    just one widget's, so a widget whose `path:` never changes still has to
    notice and re-resolve. Factored out of `ImageElement._entry` once
    `Slider`'s own `handle_image:` needed the identical resolve-cache-decode
    dance -- this staleness check is non-trivial enough that a second,
    subtly different copy is a real risk, not a hypothetical one.

    A missing path, or a decode failure, resolves to `(new_key_or_None,
    None)` rather than raising -- the caller draws nothing for that frame,
    the same "blank rather than a crashed paint pass" choice `ImageElement`
    already makes; `label` only changes the stderr line's prefix.
    """
    if not path:
        return None, None
    new_key = Path(path).expanduser().resolve()
    stale = entry is not None and entry.generation != atlas.generation
    if new_key == key and not stale:
        return key, entry
    try:
        return new_key, atlas.get_or_add(new_key, lambda: _decode(new_key))
    except Exception as exc:  # decode, or the atlas rejecting the shape
        print(f"{label}: could not load {new_key}: {exc}", file=sys.stderr)
        return new_key, None


def _fit_image(
    box: Size,
    natural: Size,
    mode: str,
    uv: tuple[float, float, float, float],
) -> tuple[float, float, float, float, tuple[float, float, float, float]]:
    """Where to draw and what to sample, for one `fit` mode.

    Returns `(x, y, width, height, uv)` in the same logical units as `box`
    and `natural`, `x`/`y` relative to the box's own top-left. `contain` and
    `none` can leave part of the box uncovered -- the widget's own
    background, if any, shows through there, painted first by the inherited
    `paint_self`. Only `cover` crops: it scales up until the box is full and
    then narrows the *source* UV rect rather than the destination, so no
    extra geometry is needed for the cropped part to simply not be sampled.
    """
    bw, bh = box.width, box.height
    nw, nh = natural.width, natural.height
    if mode == "fill" or nw <= 0.0 or nh <= 0.0:
        return 0.0, 0.0, bw, bh, uv
    if mode == "none":
        return (bw - nw) / 2.0, (bh - nh) / 2.0, nw, nh, uv
    if mode == "cover":
        scale = max(bw / nw, bh / nh)
        visible_w = bw / (nw * scale)
        visible_h = bh / (nh * scale)
        u0, v0, u1, v1 = uv
        du = (u1 - u0) * (1.0 - visible_w) / 2.0
        dv = (v1 - v0) * (1.0 - visible_h) / 2.0
        return 0.0, 0.0, bw, bh, (u0 + du, v0 + dv, u1 - du, v1 - dv)
    # "contain": scale down/up uniformly so the whole image fits, centred.
    scale = min(bw / nw, bh / nh)
    dw, dh = nw * scale, nh * scale
    return (bw - dw) / 2.0, (bh - dh) / 2.0, dw, dh, uv


class ImageElement(_StyledMixin, Padding):
    """A leaf widget: decode `path:` once, cache it in the shared atlas, draw it.

    Sizing has real intrinsic content to fall back on, unlike `Canvas`: with
    no explicit `width`/`height` it reports the decoded image's own pixel
    dimensions as its logical size (one image px, one logical px), the same
    `outer.constrain(natural)` shape `Shape` and every other widget with an
    intrinsic size already uses -- an axis the view *did* size wins outright,
    since `sized()` made that axis tight before `constrain` ever sees it.

    A missing file or a decode failure is caught once per resolved path,
    logged to stderr, and cached as "nothing to draw" rather than raised --
    raising would crash the whole frame's paint for one bad asset reference,
    which is a worse failure than a blank box. Changing `path:` to something
    that decodes retries on its own; nothing needs telling.
    """

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)
        self._resolved_key: Path | None = None
        self._resolved_entry: ImageEntry | None = None

    def _entry(self) -> ImageEntry | None:
        self._resolved_key, self._resolved_entry = resolve_image(
            self.image_atlas,
            self.path,
            key=self._resolved_key,
            entry=self._resolved_entry,
            label="Image",
        )
        return self._resolved_entry

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        entry = self._entry()
        natural = (
            Size(float(entry.width), float(entry.height)) if entry is not None else Size(0.0, 0.0)
        )
        return outer.constrain(natural)

    def paint_self(self, ctx: PaintContext, absolute: Offset) -> None:
        super().paint_self(ctx, absolute)
        entry = self._entry()
        if entry is None or self.size.is_empty:
            return
        natural = Size(float(entry.width), float(entry.height))
        uv = entry.uv(self.image_atlas.size)
        x, y, w, h, uv = _fit_image(self.size, natural, self.style.fit, uv)
        dpr = ctx.pixel_ratio
        ctx.display_list.add_image(
            (absolute.x + x) * dpr,
            (absolute.y + y) * dpr,
            w * dpr,
            h * dpr,
            uv=uv,
            tint=(1.0, 1.0, 1.0, self.style.opacity),
            radii=tuple(r * dpr for r in self.style.corner_radius),  # type: ignore[arg-type]
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
