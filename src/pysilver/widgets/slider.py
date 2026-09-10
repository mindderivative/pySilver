"""M3 Slider: a value picked from a range by dragging, clicking, or the keyboard.

Standard variant, every named M3 size -- `style.size` selects one of
`extra_small` (M3's own stated default), `small`, `medium`, `large`, or
`extra_large`, all sourced directly from `COMPONENT_SLIDERS.md`'s own
Measurements table (confirmed twice: the table itself, and again in its
"Size" guideline section, which agree exactly):

| Size | Track height | Handle height | Track corner radius |
|------|-------------|----------------|----------------------|
| extra_small (default) | 16dp | 44dp | 8dp |
| small | 24dp | 44dp | 8dp |
| medium | 40dp | 52dp | 12dp |
| large | 56dp | 68dp | 16dp |
| extra_large | 96dp | 108dp | 28dp |

Handle **width** stays a constant 4dp across every size -- the table's own
"Handle width: 4dp" row has no per-size variation at all, unlike the other
three dimensions. Discrete (stop indicators) and Range (two handles) are
real M3 variants, deliberately out of scope for this pass -- each is a
materially separate widget shape, not a style tweak on this one; so is the
M3 Sliders page's own "Variant" axis (Standard/Centered/Range), which is
why size lives in its own `style.size` field rather than `style.variant` --
that field already means each widget's own distinct M3 vocabulary
elsewhere, and Range would collide with size on it the moment it exists.

**This is the one gap that mattered most.** `SpinBox` (`material.py`) was
built once already citing this same page ("Icon buttons placed outside the
slider should have the button role"), but the actual slider -- the thing
with a track and a draggable handle -- was never built. Nothing here is
therefore inferred; every behaviour quoted below is the page's own words.

**Colour roles** are not fully specified in the scraped tokens table (an
interactive image, not text -- the same gap `CircularProgress`'s own default
diameter has), so this reuses M3's own established selection-control pairing
directly: `primary` for the active track and the handle, `secondary_container`
for the inactive track -- the identical role `Chip`/`Segment` already use for
"filled and selected". The handle is also taller than the track by design
regardless of size ("A handle changes shape when it's being pressed or
dragged"; M3's visual refresh gave it "a vertical handle that narrows when
pressed", not a circular thumb the way `Switch`'s handle is one).

**Not part of the sourced ladder above, and NOT scaled by size** -- the
spec gives no size-dependent figure for any of these, so each stays exactly
the single fixed value it already was before the ladder existed:
`cradle_gap`, `cradle_radius`, the hover/press/focus halo
(`STATE_LAYER_SIZE`), the circle-handle diameter (`style.handle_shape:
circle`), and this widget's own minimum width. This is a known, disclosed
risk, not an oversight -- a 32dp halo sized for a 44dp XS handle may not
read right around a 108dp XL one; watch for it live rather than guessing
another unsourced number ahead of actually seeing it.

**All three named M3 behaviours are implemented, not just one:**

* **"Select & drag"**: `on_pointer_down` jumps to the press position and
  starts a drag; `on_pointer_move` (while pressed) keeps committing the
  value under the pointer -- "the handle drags smoothly", and per "Changes
  made with sliders must take effect immediately", not only on release.
* **"Select jump"**: the same `on_pointer_down` -- M3 describes this as a
  separate interaction ("Select a value by selecting part of the track") but
  it is the identical first frame of a drag here, not a second code path.
* **"Select & arrow"**: `on_key_down` -- Left/Down decrement, Right/Up
  increment, both by `style.step`; Home/End jump to the bound minimum/
  maximum, exactly the page's own keyboard table.

`value:` is the current number, read through the same generic `number`
property every other value-bearing widget uses (`ElementMixin.number`).
`style.min`/`max` bound it, falling back to 0.0/1.0 when unset (see
`StyleSpec.min`'s own docstring for why that differs from `SpinBox`'s
"unbounded" convention); `style.step` is the same field `SpinBox` already
has, and defaults identically. `on_change` fires with the value already
clamped and snapped to the nearest step -- the same split `SpinBox._step`
and `TextField._commit` already make between updating the display and
telling the application what changed.

**Deliberately out of scope for this pass**, matching M3's own "optional"
anatomy: the value indicator (a label that appears above the handle while
dragging), stop indicators, the inset icon, and vertical orientation.

**Pluggable handle shapes, pySilver's own -- not M3.** phil asked directly
for a genuinely pluggable handle, "not just pySilver's shipped line/circle
pair": `style.handle_shape` now also takes `"square"`/`"hexagon"`, and a new
`style.handle_image:` (a path, same resolution convention as `Image.path:`)
draws a decoded image as the handle instead of any shape, winning over
`handle_shape` when set. Square/hexagon cost no new engine work -- both
reuse `Shape`'s own regular-polygon primitive (`DisplayList.add_polygon`),
the same shader branch `Shape` already exercises for exactly this reason
(parametric, no atlas, animates for free). `handle_image` reuses `Image`'s
own decode/cache path (`ImageAtlas`, Pillow) via `resolve_image` (factored
out of `ImageElement._entry` in `image.py` once this needed the identical
staleness-checked resolve-and-cache dance) -- raster only, since Pillow has
no SVG decoder and pySilver has no other one yet.

**A true star was asked for and dropped, not silently skipped.** M3 gives
no handle-shape guidance at all (this whole feature is pySilver's own), but
`add_polygon`'s shader is strictly a *regular* polygon -- one `sides` count,
no alternating inner/outer radius -- so it cannot draw a star shape at any
value of `sides`. A six-pointed hexagram *could* be approximated with two
overlapping `sides=3` triangles, but a real star (five points, the shape
most people mean) needs a genuinely new primitive. Asked phil directly
(`AskUserQuestion`) rather than shipping a shape that only resembles what
was asked for; he chose to drop it from this pass over the hexagram
workaround or new shader work -- logged as a real, disclosed gap, not
solved here.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Final

from ..layout import Constraints, EdgeInsets, Padding, Size
from ..render.atlas import ImageEntry
from ..runtime.events import ChangeEvent, EventType
from ..spec import WidgetSpec
from ..tree.element import PaintContext
from .base import _StyledMixin
from .image import resolve_image
from .material import _box, _state_alpha

__all__ = ["SliderElement"]

#: `add_polygon`'s own convention: `sides=4` at `rotation=0` is a diamond
#: (confirmed directly against the Shape demo's own labelled example,
#: `examples/widgets/shape/`); `pi/4` turns it axis-aligned -- what "square"
#: actually means here.
_SQUARE_ROTATION: Final = math.pi / 4


class SliderElement(_StyledMixin, Padding):
    """M3 Slider, Standard variant, every named size. See the module docstring."""

    #: `style.size` -> (track_height, handle_height, track_radius), all
    #: three sourced from `COMPONENT_SLIDERS.md`'s own Measurements table
    #: (see the module docstring's own copy of it). Handle *width* is not
    #: here -- unlike these three, it does not vary by size at all -- so it
    #: stays `HANDLE_WIDTH`, a plain constant below.
    SIZES: Final = {
        "extra_small": (16.0, 44.0, 8.0),
        "small": (24.0, 44.0, 8.0),
        "medium": (40.0, 52.0, 12.0),
        "large": (56.0, 68.0, 16.0),
        "extra_large": (96.0, 108.0, 28.0),
    }
    HANDLE_WIDTH: Final = 4.0
    HANDLE_RADIUS: Final = 2.0
    #: The bounding box every non-`"line"` handle draws in -- M2's circular
    #: handle originally (opt-in via `style.handle_shape: circle`), now
    #: shared by `"square"`/`"hexagon"` and `handle_image:` too, so every
    #: alternate handle reads as the same size rather than each shape
    #: picking its own. Not a scraped M3 figure for any of them -- the
    #: circle case is a reasoned approximation of M2's own historical thumb
    #: size, and the rest are pySilver's own feature entirely.
    HANDLE_CIRCLE_DIAMETER: Final = 20.0
    #: The halo a hover/press/focus state layer draws around the handle --
    #: not an M3-quoted figure (the state-layer table gives opacities, not a
    #: size), chosen generously enough to read as a real affordance without
    #: implying a bigger hit area than the handle itself has.
    STATE_LAYER_SIZE: Final = 32.0
    #: No M3 figure for a bare slider's own minimum width either; matches
    #: `TextField.MIN_WIDTH`'s own reasoning -- enough room for the handle to
    #: travel visibly rather than sitting on top of itself.
    MIN_WIDTH: Final = 120.0
    CURSOR = "pointer"

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)
        self._handle_image_key: Path | None = None
        self._handle_image_entry: ImageEntry | None = None

    # ------------------------------------------------------------ geometry

    def _geometry(self) -> tuple[float, float, float]:
        """(track_height, handle_height, track_radius) for `style.size`."""
        return self.SIZES.get(self.style.size, self.SIZES["extra_small"])

    def _track_radius(self) -> float:
        """The size-appropriate `track_radius`, unless a view file set it
        explicitly -- the same `model_fields_set` check `DockSplitElement.
        horizontal` already uses to tell "the view actually wrote this"
        apart from "using the field's own bare default" (`widgets/dock.py`).
        Without it, `track_radius`'s own pre-existing default (8.0, correct
        only for `extra_small`) would silently override every larger size's
        real corner radius on every slider that never mentions the field.
        """
        if "track_radius" in self.style.model_fields_set:
            return self.style.track_radius
        return self._geometry()[2]

    # ------------------------------------------------------------- bounds

    def _bounds(self) -> tuple[float, float]:
        style = self.style
        lo = style.min if style.min is not None else 0.0
        hi = style.max if style.max is not None else 1.0
        return (lo, hi) if hi > lo else (lo, lo + 1.0)

    def _clamped(self, value: float) -> float:
        lo, hi = self._bounds()
        step = self.style.step
        snapped = round((value - lo) / step) * step + lo
        return max(lo, min(hi, snapped))

    def _fraction(self) -> float:
        lo, hi = self._bounds()
        return (max(lo, min(hi, self.number)) - lo) / (hi - lo)

    @staticmethod
    def _format(n: float) -> str:
        return str(int(n)) if n == int(n) else str(n)

    def _commit(self, value: float) -> None:
        formatted = self._format(value)
        if formatted == self._value:
            return
        self._value = formatted
        handler = self.handlers.get("on_change")
        if handler is not None:
            handler(ChangeEvent(EventType.CHANGE, target=self, value=formatted))
        self.mark_needs_paint()

    # -------------------------------------------------------------- layout

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else self.MIN_WIDTH
        _track_height, handle_height, _track_radius = self._geometry()
        return outer.constrain(Size(width, handle_height))

    def _usable_width(self) -> float:
        return float(max(1.0, self.size.width - self.HANDLE_WIDTH))

    def _handle_x(self) -> float:
        return self._fraction() * self._usable_width()

    # ------------------------------------------------------------- pointer

    def _value_at(self, x: float) -> float:
        rect = self.absolute_rect()
        local = x - rect.x - self.HANDLE_WIDTH / 2
        fraction = max(0.0, min(1.0, local / self._usable_width()))
        lo, hi = self._bounds()
        return self._clamped(lo + fraction * (hi - lo))

    def on_pointer_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        self.state.data["slider_dragging"] = True
        event.capture()
        self._commit(self._value_at(event.x))

    def on_pointer_move(self, event: Any) -> None:
        if self.effective_disabled or not self.state.data.get("slider_dragging"):
            return
        self._commit(self._value_at(event.x))

    def on_pointer_up(self, event: Any) -> None:
        self.state.data["slider_dragging"] = False

    # ---------------------------------------------------------------- keys

    def on_key_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        key = str(getattr(event, "key", "")).lower()
        lo, hi = self._bounds()
        step = self.style.step
        if key in ("arrowleft", "left", "arrowdown", "down"):
            self._commit(self._clamped(self.number - step))
        elif key in ("arrowright", "right", "arrowup", "up"):
            self._commit(self._clamped(self.number + step))
        elif key == "home":
            self._commit(lo)
        elif key == "end":
            self._commit(hi)

    # --------------------------------------------------------------- paint

    def _resolve_handle_image(self) -> ImageEntry | None:
        """The decoded `handle_image:`, or `None` if unset/unresolved.

        Resolved (and re-resolved, on a changed path or a stale atlas
        generation) via the shared `resolve_image` -- see that function's own
        docstring for why the staleness check is factored out rather than
        duplicated. Called from both `_handle_half_extent` and `paint_self`
        so a failed resolution (bad path, decode error) falls back to the
        default line handle *consistently* -- the track's own cradle-gap
        clearance and the actually-painted handle never disagree about which
        shape is really showing.
        """
        self._handle_image_key, self._handle_image_entry = resolve_image(
            self.image_atlas,
            self.style.handle_image,
            key=self._handle_image_key,
            entry=self._handle_image_entry,
            label="Slider handle_image",
        )
        return self._handle_image_entry

    def _handle_half_extent(self) -> float:
        """Half the current handle shape's own width.

        `"line"` is the narrow default; every other shape -- circle, square,
        hexagon, or a resolved `handle_image:` -- shares the wider
        `HANDLE_CIRCLE_DIAMETER` bounding box, so the cradle-gap clearance is
        always right for whatever is actually painted (see
        `_resolve_handle_image`'s own docstring for the image fallback case).
        """
        if self._resolve_handle_image() is not None:
            return self.HANDLE_CIRCLE_DIAMETER / 2
        if self.style.handle_shape in ("circle", "square", "hexagon"):
            return self.HANDLE_CIRCLE_DIAMETER / 2
        return self.HANDLE_WIDTH / 2

    def _track_segment(
        self,
        ctx: PaintContext,
        x: float,
        y: float,
        w: float,
        h: float,
        token: int,
        radii: tuple[float, float, float, float],
    ) -> None:
        """Like `_box`, but with independent per-corner radii -- `_box`
        itself only takes one radius applied to all four corners, which
        can't express the cradle/outer asymmetry each track segment needs.
        """
        dpr = ctx.pixel_ratio
        ctx.display_list.add_box(
            x * dpr,
            y * dpr,
            w * dpr,
            h * dpr,
            token=token,
            color=(1.0, 1.0, 1.0, 1.0),
            radii=tuple(r * dpr for r in radii),  # type: ignore[arg-type]
        )

    def _paint_handle_polygon(
        self,
        ctx: PaintContext,
        absolute: Any,
        handle_x: float,
        *,
        sides: float,
        rotation: float,
        token: int,
    ) -> None:
        """`style.handle_shape: square`/`hexagon` -- both regular polygons,
        so both are one `add_polygon` call apart (`Shape`'s own primitive,
        `sides=4`/`6`), sized to the shared `HANDLE_CIRCLE_DIAMETER` box
        every non-`"line"` handle uses.
        """
        diameter = self.HANDLE_CIRCLE_DIAMETER
        dpr = ctx.pixel_ratio
        ctx.display_list.add_polygon(
            (handle_x + self.HANDLE_WIDTH / 2 - diameter / 2) * dpr,
            (absolute.y + (self.size.height - diameter) / 2) * dpr,
            diameter * dpr,
            diameter * dpr,
            sides=sides,
            rotation=rotation,
            corner_radius=self.HANDLE_RADIUS * dpr,
            token=token,
        )

    def _paint_handle_image(
        self, ctx: PaintContext, absolute: Any, handle_x: float, entry: ImageEntry
    ) -> None:
        """`style.handle_image:` -- fit the decoded image into the same
        `HANDLE_CIRCLE_DIAMETER` box every non-`"line"` handle shares,
        preserving its own aspect ratio (letterboxed, never cropped -- a
        handle image is content the caller chose, not a photo to fill a
        frame with) and centred. No tint, no corner rounding: `Image` itself
        makes the identical "show the decoded colours as-is" call for the
        same reason (`ARCHITECTURE.md` 5's "emit tokens, not colours" --
        baking a tint would silently stop re-theming on a live palette
        swap), and a handle glyph the caller supplied is exactly the kind of
        asset that should not be silently reshaped.
        """
        diameter = self.HANDLE_CIRCLE_DIAMETER
        box_x = handle_x + self.HANDLE_WIDTH / 2 - diameter / 2
        box_y = absolute.y + (self.size.height - diameter) / 2
        natural_w, natural_h = float(entry.width), float(entry.height)
        scale = (
            min(diameter / natural_w, diameter / natural_h)
            if natural_w > 0 and natural_h > 0
            else 1.0
        )
        w, h = natural_w * scale, natural_h * scale
        dpr = ctx.pixel_ratio
        ctx.display_list.add_image(
            (box_x + (diameter - w) / 2) * dpr,
            (box_y + (diameter - h) / 2) * dpr,
            w * dpr,
            h * dpr,
            uv=entry.uv(self.image_atlas.size),
            tint=(1.0, 1.0, 1.0, 1.0),
            radii=(0.0, 0.0, 0.0, 0.0),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        active = ctx.palette.index(style.background or "primary")
        inactive = ctx.palette.index("secondary_container")
        track_height, handle_height, _track_radius = self._geometry()
        track_y = absolute.y + (self.size.height - track_height) / 2
        handle_x = absolute.x + self._handle_x()
        handle_center = handle_x + self.HANDLE_WIDTH / 2
        clearance = self._handle_half_extent() + style.cradle_gap

        # Active and inactive are two independently-sized segments, each
        # stopping short of the handle by `clearance` -- not a full-width
        # inactive track with the active colour painted over it, which left
        # the accent colour touching the handle with no gap at all, unlike
        # a real M3 slider.
        cradle = style.cradle_radius
        outer = self._track_radius()

        inactive_start = handle_center + clearance
        inactive_width = absolute.x + self.size.width - inactive_start
        if inactive_width > 0.0:
            # Left corners face the handle (cradle), right corners are the
            # segment's own outer end.
            self._track_segment(
                ctx,
                inactive_start,
                track_y,
                inactive_width,
                track_height,
                inactive,
                (cradle, outer, outer, cradle),
            )
        active_width = handle_center - clearance - absolute.x
        if active_width > 0.0:
            # Left corners are the outer end, right corners face the handle.
            self._track_segment(
                ctx,
                absolute.x,
                track_y,
                active_width,
                track_height,
                active,
                (outer, cradle, cradle, outer),
            )

        alpha = _state_alpha(self)
        if alpha > 0.001:
            halo = self.STATE_LAYER_SIZE
            _box(
                ctx,
                handle_x + self.HANDLE_WIDTH / 2 - halo / 2,
                absolute.y + self.size.height / 2 - halo / 2,
                halo,
                halo,
                token=active,
                radius=halo / 2,
                alpha=alpha,
            )

        image_entry = self._handle_image_entry
        if image_entry is not None:
            self._paint_handle_image(ctx, absolute, handle_x, image_entry)
        elif style.handle_shape == "square":
            self._paint_handle_polygon(
                ctx, absolute, handle_x, sides=4.0, rotation=_SQUARE_ROTATION, token=active
            )
        elif style.handle_shape == "hexagon":
            self._paint_handle_polygon(
                ctx, absolute, handle_x, sides=6.0, rotation=0.0, token=active
            )
        elif style.handle_shape == "circle":
            diameter = self.HANDLE_CIRCLE_DIAMETER
            _box(
                ctx,
                handle_x + self.HANDLE_WIDTH / 2 - diameter / 2,
                absolute.y + (self.size.height - diameter) / 2,
                diameter,
                diameter,
                token=active,
                radius=diameter / 2,
            )
        else:
            _box(
                ctx,
                handle_x,
                absolute.y + (self.size.height - handle_height) / 2,
                self.HANDLE_WIDTH,
                handle_height,
                token=active,
                radius=self.HANDLE_RADIUS,
            )
