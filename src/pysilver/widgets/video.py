"""A live-updating video surface: the application decodes, this displays.

No M3 component exists -- checked directly against `M3-References`, the same
way every other ungrounded widget this session was. Unlike `Image`, this is
also not something pySilver could reasonably decode itself: nothing in this
project depends on a codec library (Pillow decodes still images; nothing
decodes `.mp4`/`.webm`), and adding one -- realistically PyAV, which wraps
FFmpeg -- would mean taking on its install size and licensing considerations
for every pySilver application, not just the ones that show video. Confirmed
with the user directly rather than assumed: `Video` is a **frame sink**. The
application decodes however it likes (PyAV, OpenCV, a camera driver, frames
generated on the fly) and calls `push_frame(rgba)`; this widget only owns
displaying whatever the latest one was.

**Why not go through `Image`'s `path:` / `get_or_add` at all.** `add`
(`ImageAtlas`) always allocates a fresh rectangle, which is right for "this
source decoded to a different picture" but wrong for a stream arriving
30-60 times a second at the same resolution -- every call would churn the
packer and eventually force a wholesale eviction for pixels that were only
ever going to land in the same slot. `ImageAtlas.update` exists for exactly
this: overwrite an existing entry's pixels in place when the shape matches,
falling back to `add` only on a genuine change (the first frame, a resolution
renegotiation, or the atlas having been reset since). That is the only
addition this widget needed anywhere below the widget layer -- no new
texture slot, no shader change, no exception to the single-draw-call model:
a video frame is still exactly one `Kind.IMAGE` instance sampling the same
`image_atlas` every other image on screen already does.

**No decode-adjacent state lives here either.** There is no `value:` for
play/pause, no built-in scrub bar, no clock. The application already owns
the decode loop -- it is the thing deciding when a new frame exists -- so it
is also the natural owner of transport state and controls, composed from
existing widgets (`IconButton` for play/pause, `LinearProgress` or a
`Canvas`-drawn scrubber for position) around a `Video` the same way a page
composes any other widget. Bundling a player UI here would be designing it
twice: once for whatever this widget guessed at, and once for real when an
application's needs inevitably differ.
"""

from __future__ import annotations

from typing import Any, override

import numpy as np

from ..layout import Constraints, EdgeInsets, Offset, Padding, Size
from ..render.atlas import ImageEntry
from ..spec import WidgetSpec
from ..tree.element import PaintContext
from .base import _StyledMixin
from .image import _fit_image

__all__ = ["VideoElement"]


class VideoElement(_StyledMixin, Padding):
    """A leaf widget with no content of its own until `push_frame` is called.

    Sizing follows `Image`'s shape once a frame has arrived: an unsized axis
    reports the frame's own pixel dimensions, `outer.constrain(natural)`
    handles the rest. Before the first frame there is nothing to be a size
    of, so it lays out `0x0`, `Image`'s own "no path is no picture" answer to
    the same question.

    **Not thread-safe, by the same rule every other mutation in this
    framework follows** (ARCHITECTURE.md 8): `push_frame` touches element
    state and must run on the engine thread. A decoder running on its own
    thread hands a frame back with `loop.call_soon_threadsafe(element.
    push_frame, rgba)`, the identical pattern `Signal.set` already requires.
    """

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)
        #: A fresh, unique atlas key per element instance -- not the spec's
        #: `id`/`name`, because those identify a *position* in the tree, not
        #: this object; reconciliation reuses the same `VideoElement` (and
        #: therefore the same key) for an in-place update, which is exactly
        #: the case `ImageAtlas.update` exists to make cheap.
        self._atlas_key: Any = object()
        self._entry: ImageEntry | None = None
        self._natural = Size(0.0, 0.0)

    def push_frame(self, rgba: np.ndarray) -> None:
        """Display *rgba* -- an `(h, w, 4)` uint8 array, straight alpha, the
        same convention `ImageAtlas.add` requires -- in place of whatever was
        showing before.

        Marks layout dirty only the first time, or if the frame's own size
        changes -- a fixed-resolution stream repaints every call and never
        relayouts, which is what keeps this affordable at frame rate.
        """
        entry = self.image_atlas.update(self._atlas_key, np.asarray(rgba))
        self._entry = entry
        natural = Size(float(entry.width), float(entry.height))
        if natural != self._natural:
            self._natural = natural
            self.mark_needs_layout()
        else:
            self.mark_needs_paint()

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        return outer.constrain(self._natural)

    @override
    def paint_self(self, ctx: PaintContext, absolute: Offset) -> None:
        super().paint_self(ctx, absolute)
        entry = self._entry
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
