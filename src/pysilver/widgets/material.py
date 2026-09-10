"""Material Design 3 components.

Each class translates one M3 spec into pySilver's element model. Dimensions are
M3's own dp figures used directly, since layout runs in logical units and dp
maps 1:1 (ARCHITECTURE.md 7). Colours are palette **tokens**, never literals,
so a theme switch stays a single buffer upload.

Where pySilver cannot express part of a spec, the class says so rather than
quietly approximating.

**pySilver is a desktop framework and does not target touch.** M3's 48x48dp
minimum touch target is a finger-precision requirement; a mouse pointer is
precise to the pixel, so hit rects match the painted control by default. A view
that wants the M3 figure asks for it with `min_hit_size: 48`, which widens the
hit rect and leaves layout and paint alone. Desktop affordances M3 treats as
secondary -- hover, focus rings, keyboard traversal, right-click -- matter
correspondingly more.
"""

from __future__ import annotations

import math
from typing import Any, Final, override

from ..layout import INF, Constraints, EdgeInsets, Offset, Padding, Size
from ..runtime.events import ChangeEvent, EventType
from ..spec import StyleSpec, WidgetSpec
from ..text.icons import DEFAULT_ICON_SIZE
from ..tree.element import PaintContext
from .base import _StyledMixin, content_token, measure_text, paint_text

__all__ = [
    "AccordionElement",
    "BadgeElement",
    "CardElement",
    "CheckboxElement",
    "ChipElement",
    "DividerElement",
    "FabElement",
    "IconButtonElement",
    "PaginationElement",
    "RadioElement",
    "SpinBoxElement",
    "SwitchElement",
]

#: M3 state-layer opacities (M3_COMPONENT_SPECS.md §0).
HOVER: Final = 0.08
FOCUS: Final = 0.10
PRESS: Final = 0.10


#: "Selection controls have a short duration of 200ms with Standard easing"
#: -- M3 states this outright, and it covers the whole family: checkbox, radio,
#: switch, and the filter chip's checkmark.
SELECTION_MOTION: Final = "short4"
SELECTION_CURVE: Final = "standard"

#: State layers cross-fade rather than snapping. **Not sourced** -- M3 gives no
#: duration for a state layer, and the "begin and end on screen" pair (Standard,
#: 300ms) is about elements arriving, not an in-place emphasis change. 100ms is
#: chosen because a hover response slower than that reads as lag.
STATE_LAYER_MOTION: Final = "short2"
STATE_LAYER_CURVE: Final = "standard"


def _state_alpha(element: Any) -> float:
    """State-layer opacity for the element's current interaction state.

    Animated, so a hover fades in and out instead of blinking. Every component
    that emits a state layer gets this from one place -- which is the whole
    reason `_emit_state_layer` is shared.
    """
    if element.state.pressed:
        target = PRESS
    elif element.state.focus_visible:
        target = FOCUS
    elif element.state.hovered:
        target = HOVER
    else:
        target = 0.0
    alpha: float = element.animated(
        "state_layer", target, duration=STATE_LAYER_MOTION, curve=STATE_LAYER_CURVE
    )
    return alpha


def _emit_state_layer(
    ctx: PaintContext,
    element: Any,
    absolute: Any,
    token: int,
    radii: tuple[float, float, float, float],
) -> None:
    """M3 state layer: a tinted overlay above the container, below the content."""
    alpha = _state_alpha(element)
    if alpha <= 0.001:
        # Below this the layer is invisible; emitting it would cost an instance
        # a frame for nothing, and the fade-out has effectively landed.
        return
    dpr = ctx.pixel_ratio
    ctx.display_list.add_box(
        absolute.x * dpr,
        absolute.y * dpr,
        element.size.width * dpr,
        element.size.height * dpr,
        token=token,
        color=(1.0, 1.0, 1.0, alpha),
        radii=tuple(r * dpr for r in radii),  # type: ignore[arg-type]
        clip=ctx.clip,
        clip_radii=ctx.clip_radii,
    )


def _box(
    ctx: PaintContext,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    token: int,
    radius: float,
    alpha: float = 1.0,
    border_width: float = 0.0,
    border_token: int | None = None,
    border_alpha: float = 1.0,
) -> None:
    """Emit one token-coloured rounded box in logical coordinates."""
    from ..paint import NO_TOKEN

    dpr = ctx.pixel_ratio
    ctx.display_list.add_box(
        x * dpr,
        y * dpr,
        w * dpr,
        h * dpr,
        token=token,
        color=(1.0, 1.0, 1.0, alpha),
        radii=(radius * dpr,) * 4,
        border_width=border_width * dpr,
        border_token=NO_TOKEN if border_token is None else border_token,
        border_color=(1.0, 1.0, 1.0, border_alpha),
        clip=ctx.clip,
        clip_radii=ctx.clip_radii,
    )


def _arc(
    ctx: PaintContext,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    token: int,
    thickness: float,
    start: float,
    sweep: float,
    alpha: float = 1.0,
) -> None:
    """Emit one token-coloured stroked arc in logical coordinates.

    Angles are radians clockwise from 12 o'clock, which is the direction M3
    specifies for circular progress.
    """
    dpr = ctx.pixel_ratio
    ctx.display_list.add_arc(
        x * dpr,
        y * dpr,
        w * dpr,
        h * dpr,
        thickness=thickness * dpr,
        start=start,
        sweep=sweep,
        token=token,
        color=(1.0, 1.0, 1.0, alpha),
        clip=ctx.clip,
        clip_radii=ctx.clip_radii,
    )


#: M3's six elevation levels and their dp heights, quoted from
#: `styles/M3-Styles-Elevation-Tokens.md`. Levels 0-3 are resting states;
#: "+4 and +5 are reserved for user-interacted states such as hover and
#: dragged".
ELEVATION_DP: Final = {0: 0.0, 1: 1.0, 2: 3.0, 3: 6.0, 4: 8.0, 5: 12.0}

#: Turning a dp height into a shadow. **Not sourced** -- the spec describes the
#: relationship ("larger, softer shadows express more distance") and shows it in
#: images, without giving blur or offset figures. The constants are anchored on
#: the value the Card already used for level 1, so the family scales out from a
#: shape that was already reviewed rather than from an invention.
SHADOW_BASE_BLUR: Final = 4.0
SHADOW_BLUR_PER_DP: Final = 2.0
SHADOW_OPACITY: Final = 0.30


def elevation_shadow(
    ctx: PaintContext,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    level: int,
    radii: tuple[float, float, float, float],
) -> None:
    """Emit the shadow for an M3 elevation level. Level 0 draws nothing.

    Shared rather than hand-tuned per widget: three components had their own
    blur values, so a dialog and a FAB at the same M3 level did not look like
    they were at the same height.
    """
    dp = ELEVATION_DP.get(level, 0.0)
    if dp <= 0.0:
        return
    dpr = ctx.pixel_ratio
    ctx.display_list.add_shadow(
        x * dpr,
        y * dpr,
        w * dpr,
        h * dpr,
        blur=(SHADOW_BASE_BLUR + dp * SHADOW_BLUR_PER_DP) * dpr,
        offset=(0.0, dp * dpr),
        color=(0.0, 0.0, 0.0, SHADOW_OPACITY),
        radii=tuple(r * dpr for r in radii),  # type: ignore[arg-type]
        clip=ctx.clip,
        clip_radii=ctx.clip_radii,
    )


# ------------------------------------------------------------------- cards


class CardElement(_StyledMixin, Padding):
    """M3 Card: 12dp radius, 16dp padding, three variants.

    Elevated is level 1, filled uses `surface_container_highest`, outlined uses
    `surface` with a 1dp `outline_variant` border. Elevation is approximated by
    shadow alone -- the tonal surface shift M3 also specifies is not modelled.
    """

    RADIUS: Final = 12.0
    PADDING: Final = 16.0
    #: M3 resting levels: "Card (elevated)" is level 1; filled and outlined
    #: cards are level 0. The level therefore depends on the variant.
    ELEVATED_LEVEL: Final = 1

    @override
    @property
    def resting_elevation(self) -> int:
        return self.ELEVATED_LEVEL if self.style.variant == "elevated" else 0

    CONTAINERS: Final = {
        "elevated": "surface_container_low",
        "filled": "surface_container_highest",
        "outlined": "surface",
    }

    @override
    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        radii = self.style.corner_radius
        return radii if any(radii) else (self.RADIUS,) * 4

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, self._insets(spec.style))
        self.init_element(spec)

    @staticmethod
    def _insets(style: StyleSpec) -> EdgeInsets:
        pad = style.padding
        return pad if pad != EdgeInsets() else EdgeInsets.all(CardElement.PADDING)

    @override
    def configure(self) -> None:
        self._padding = self._insets(self.style)

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        inner = super().perform_layout(outer.loosen() if not outer.is_tight else outer)
        return outer.constrain(inner)

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        from ..paint import NO_TOKEN

        style = self.style
        variant = style.variant if style.variant in self.CONTAINERS else "filled"
        radii = self.effective_radii
        container = ctx.palette.index(style.background or self.CONTAINERS[variant])

        if variant == "elevated":
            elevation_shadow(
                ctx,
                absolute.x,
                absolute.y,
                self.size.width,
                self.size.height,
                # Not `or ELEVATED_LEVEL`: an explicit `elevation: 0` is an
                # override, and `or` cannot tell zero from unset.
                level=self.elevation,
                radii=radii,
            )
        # Not `_box`, which only takes one radius for all four corners: a
        # view is free to set `corner_radius: [tl, tr, br, bl]` (docs' Style
        # properties table), and `effective_radii` already carries that
        # through -- so the fill has to be emitted per-corner too, the same
        # way `ButtonElement.paint_self` does it.
        outlined = variant == "outlined"
        dpr = ctx.pixel_ratio
        ctx.display_list.add_box(
            absolute.x * dpr,
            absolute.y * dpr,
            self.size.width * dpr,
            self.size.height * dpr,
            token=container,
            radii=tuple(r * dpr for r in radii),  # type: ignore[arg-type]
            border_width=1.0 * dpr if outlined else 0.0,
            border_token=ctx.palette.index("outline_variant") if outlined else NO_TOKEN,
            border_color=(1.0, 1.0, 1.0, 1.0),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )


# --------------------------------------------------------------- accordion


class AccordionElement(_StyledMixin, Padding):
    """M3 has no Accordion component. What it has is Lists' documented
    disclosure behaviour: "List items containing other list items can expand
    and collapse in a folder-like manner, to reveal or hide content"
    (`COMPONENT_LISTS.md`). Note the SAME section's worked example --
    "Tapping a list item expands it vertically across the entire screen using
    a container transform transition pattern" -- describes something else: a
    full-screen master-detail transition, not the in-place disclosure this
    widget is. This is the more universal pattern, common to nearly every UI
    toolkit; M3 states the behaviour without naming or specifying a widget
    for it, which is why the anatomy below borrows from elsewhere rather than
    quoting a Popover-style measurement table that does not exist.

    **Anatomy is `ListItem`'s** (56dp one-line / 72dp two-line header,
    `on_surface`/`on_surface_variant` text) since M3 gives this component
    none of its own to cite, plus a trailing `expand_more`/`expand_less`
    chevron. **Expand state follows the `value:` convention** `Chip`'s filter
    variant already uses -- `self.checked` reads it, and clicking fires
    `on_click:` for the application to flip its own bound signal, the same
    division of responsibility as every other selectable control.

    **Expansion is a height animation, clipped exactly like `ScrollView`
    clips its viewport** (`animated(..., invalidates="layout")`, the same
    trade `Chip`'s filter checkmark and `Carousel` already make): the body is
    laid out at its full natural height every frame, and the container's own
    height -- which the clip uses -- is that height scaled by the animated
    progress. There is no scroll offset, only a container that grows.

    **The chevron swaps rather than rotates.** A glyph instance carries no
    rotation parameter -- `Shape`'s polygon SDF does, an icon glyph does not
    -- so continuously rotating `expand_more` into `expand_less` is not
    something the current pipeline can express. It swaps on the *logical*
    state (`checked`) rather than partway through the animated progress; a
    mid-transition swap would read as a glitch, not a rotation.
    """

    HEADER_ONE_LINE: Final = 56.0
    HEADER_TWO_LINE: Final = 72.0
    PAD_X: Final = 16.0
    HEADLINE: Final = 16.0
    SUPPORTING: Final = 14.0
    CHEVRON: Final = 24.0
    CURSOR = "pointer"
    CLIPS_CHILDREN = True

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def _header_height(self) -> float:
        return self.HEADER_TWO_LINE if self._supporting.strip() else self.HEADER_ONE_LINE

    def _progress(self) -> float:
        """0 (collapsed) to 1 (fully expanded). Drives both the height and the
        clip that reveals the body -- see the class docstring."""
        return self.animated(
            "expanded",
            1.0 if self.checked else 0.0,
            duration=SELECTION_MOTION,
            curve=SELECTION_CURVE,
            invalidates="layout",
        )

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else 320.0
        header_h = self._header_height()

        body_h = 0.0
        child = self.child
        if child is not None:
            # Unbounded height: the body's NATURAL size, independent of how
            # small the accordion's own current (animated) height is.
            body_constraints = Constraints(
                min_width=width, max_width=width, min_height=0.0, max_height=INF
            )
            child.layout(body_constraints)
            body_h = child.size.height
            child.offset = Offset(0.0, header_h)

        revealed = body_h * self._progress()
        return outer.constrain(Size(width, header_h + revealed))

    @override
    def child_paint_context(self, ctx: PaintContext, absolute: Any) -> PaintContext:
        """Clip to the accordion's own (animated) size -- see `ScrollView`,
        which this mirrors exactly except that nothing scrolls."""
        dpr = ctx.pixel_ratio
        return PaintContext(
            display_list=ctx.display_list,
            palette=ctx.palette,
            text=ctx.text,
            images=ctx.images,
            pixel_ratio=dpr,
            clip=(
                absolute.x * dpr,
                absolute.y * dpr,
                self.size.width * dpr,
                self.size.height * dpr,
            ),
            clip_radii=ctx.clip_radii,
        )

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        header_h = self._header_height()
        headline_tok = content_token(ctx, style, "on_surface")
        supporting_tok = ctx.palette.index("on_surface_variant")

        # A state layer scoped to the header row alone -- `_emit_state_layer`
        # sizes itself from `element.size`, which is the WHOLE (animated)
        # accordion; reusing it as-is would tint the revealed body too.
        alpha = _state_alpha(self)
        if alpha > 0.001:
            dpr = ctx.pixel_ratio
            ctx.display_list.add_box(
                absolute.x * dpr,
                absolute.y * dpr,
                self.size.width * dpr,
                header_h * dpr,
                token=headline_tok,
                color=(1.0, 1.0, 1.0, alpha),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )

        second = self._supporting.strip()
        x = absolute.x + self.PAD_X
        if second:
            top = measure_text(self._text, self.HEADLINE, engine=self.text_engine)
            bottom = measure_text(second, self.SUPPORTING, engine=self.text_engine)
            block = top.height + bottom.height
            y = absolute.y + (header_h - block) / 2
            paint_text(ctx, x, y, self._text, self.HEADLINE, headline_tok)
            paint_text(ctx, x, y + top.height, second, self.SUPPORTING, supporting_tok)
        elif self._text.strip():
            label = measure_text(self._text, self.HEADLINE, engine=self.text_engine)
            y = absolute.y + (header_h - label.height) / 2
            paint_text(ctx, x, y, self._text, self.HEADLINE, headline_tok)

        icon = "expand_less" if self.checked else "expand_more"
        ctx.text.emit_icon(
            ctx.display_list,
            icon,
            x=absolute.x + self.size.width - self.PAD_X - self.CHEVRON,
            y=absolute.y + (header_h - self.CHEVRON) / 2,
            size=self.CHEVRON,
            pixel_ratio=ctx.pixel_ratio,
            token=supporting_tok,
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )


# ---------------------------------------------------------------- dividers


class DividerElement(_StyledMixin, Padding):
    """M3 Divider: 1dp of `outline_variant`, full-bleed or inset."""

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else 0.0
        return outer.constrain(Size(width, self.style.thickness))

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        inset = style.inset if style.variant == "inset" else 0.0
        _box(
            ctx,
            absolute.x + inset,
            absolute.y,
            max(0.0, self.size.width - inset),
            style.thickness,
            token=ctx.palette.index(style.background or "outline_variant"),
            radius=0.0,
        )


class ShapeElement(_StyledMixin, Padding):
    """A regular polygon, drawn as an analytic distance field.

    **M3 has no shape component**, but it does have a shape *system*: "the
    Material shape library contains many types of shapes that can all morph
    seamlessly into each other", and shape morph "uses the expressive motion
    scheme by default" (Styles > Shape > Shape Morph). The library itself is a
    Figma kit and a per-platform API rather than a table of figures, so the
    shapes here are pySilver's own -- the *system* is what is borrowed.

    **Why this is a shader branch and not a rasterised path.** The obvious
    alternative is to compile shapes into glyph outlines and reuse the text
    atlas. That works, and it is exactly what to do for static SVG artwork --
    but a glyph is cached by `(glyph, size, axes)`, and the atlas has no
    per-entry eviction. A shape that morphs, spins or scales changes that key
    every frame and thrashes the whole atlas. That is the same trap that
    quantised the icon FILL axis to six steps and that ruled out compensating
    the pixel ratio during a resize; this is the third time it has decided a
    design, so shapes stay parametric.

    The payoff: `sides`, `rotation` and `corner_radius` are instance floats.
    Animating them costs *nothing* -- no rasterisation, no cache key, no atlas
    -- so morphing is a paint-only change, and a `Shape` is as cheap to animate
    as it is to draw. It sits in the same single draw call as everything else.

    Two ways to reach a circle, which is worth knowing when choosing a morph:
    raise `sides` (the polygon grows into its circumcircle), or raise
    `corner_radius` to its maximum (it collapses to its *inscribed* circle).
    """

    #: Nothing in M3 sets a size for a shape that has no catalogue entry, so
    #: this is pySilver's own and stated as such: large enough to read as a
    #: shape rather than a dot, small enough not to dominate a row.
    DEFAULT_SIZE: Final = 48.0
    #: One full spin, or one full out-and-back morph -- same cycle
    #: `CircularProgress`'s own indeterminate spinner uses, so a spinning
    #: Shape and a loading spinner read as the same "ongoing" speed.
    CYCLE: Final = "extra_long4"
    #: How many sides `morph:` adds at the peak of its oscillation, on top
    #: of `sides:`'s own declared value. Not sourced -- there is no spec for
    #: this widget at all -- chosen to read clearly as a shape changing
    #: rather than jittering.
    MORPH_RANGE: Final = 5.0

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        return outer.constrain(Size(self.DEFAULT_SIZE, self.DEFAULT_SIZE))

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        from ..paint import NO_TOKEN

        style = self.style
        dpr = ctx.pixel_ratio
        border = style.border
        border_token = NO_TOKEN if border is None else ctx.palette.index(border.color)

        # Authored in degrees, because a view file is written by hand.
        rotation = math.radians(style.rotation)
        if style.spin:
            phase = self.animated("spin", 1.0, duration=self.CYCLE, curve="linear", repeat=True)
            rotation += phase * 2.0 * math.pi

        sides = style.sides
        if style.morph:
            # 0 at phase 0 and 1, peaking at phase 0.5 -- an out-and-back
            # oscillation through the shader's own smooth non-regular
            # intermediates, not a jump between two fixed polygons.
            phase = self.animated("morph", 1.0, duration=self.CYCLE, curve="linear", repeat=True)
            sides += self.MORPH_RANGE * (0.5 - 0.5 * math.cos(phase * 2.0 * math.pi))

        ctx.display_list.add_polygon(
            absolute.x * dpr,
            absolute.y * dpr,
            self.size.width * dpr,
            self.size.height * dpr,
            sides=sides,
            rotation=rotation,
            # `corner_radius` is per-corner for a box; a regular polygon has one
            # radius for every vertex, so the first entry is the one that means
            # anything here. Taking the max instead would make a stray per-corner
            # value silently change the shape.
            corner_radius=style.corner_radius[0] * dpr,
            token=ctx.palette.index(style.background or "primary"),
            color=(1.0, 1.0, 1.0, style.opacity),
            border_width=0.0 if border is None else border.width * dpr,
            border_token=border_token,
            border_color=(1.0, 1.0, 1.0, 1.0),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )


# -------------------------------------------------------- selection controls


class CheckboxElement(_StyledMixin, Padding):
    """M3 Checkbox: 18dp box, 2dp radius, checkmark when selected.

    Hit-tested at its 18dp visual size, because M3's 48dp touch target is a
    finger-precision rule and a pointer is pixel-precise. An application that
    wants the M3 figure anyway writes `min_hit_size: 48` on the node; the box
    is still drawn at 18dp.

    `indeterminate:` is M3's third state -- a dash instead of a checkmark,
    for a parent checkbox whose children are only partly checked
    (`COMPONENT_CHECKBOX.md`: "If some, but not all, child checkboxes are
    checked, the parent checkbox becomes an indeterminate checkbox"). It
    takes over which glyph paints but is otherwise inert here -- deciding
    what "some but not all" means for a given tree of children, and setting
    `indeterminate:` from that, is application logic this widget has no way
    to know on its own.
    """

    BOX: Final = 18.0
    RADIUS: Final = 2.0
    CURSOR = "pointer"

    @override
    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self.RADIUS,) * 4

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        return self.sized(constraints, self.style).constrain(Size(self.BOX, self.BOX))

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        selected = self.checked or self.indeterminate
        outline = ctx.palette.index("on_surface_variant")
        primary = ctx.palette.index(self.style.background or "primary")
        on_primary = content_token(ctx, self.style, "on_primary")

        t = self.animated(
            "selected",
            1.0 if selected else 0.0,
            duration=SELECTION_MOTION,
            curve=SELECTION_CURVE,
        )
        # Empty outline fading out, filled container fading in. Two instances
        # only while in flight -- at either end one of them is skipped.
        if t < 1.0:
            _box(
                ctx,
                absolute.x,
                absolute.y,
                self.BOX,
                self.BOX,
                token=outline,
                radius=self.RADIUS,
                alpha=0.0,
                border_width=2.0,
                border_token=outline,
                border_alpha=1.0 - t,
            )
        if t > 0.0:
            _box(
                ctx,
                absolute.x,
                absolute.y,
                self.BOX,
                self.BOX,
                token=primary,
                radius=self.RADIUS,
                alpha=t,
            )
        # After the fill, not before: at t=1 the fill is fully opaque and
        # would otherwise hide the state layer entirely, leaving a checked
        # checkbox with no visible hover/focus/press feedback.
        _emit_state_layer(ctx, self, absolute, primary, (self.RADIUS,) * 4)
        if t > 0.0:
            # M3 draws the checkmark on; a glyph cannot be drawn progressively,
            # so it fades -- an approximation, and the honest one available.
            ctx.text.emit_icon(
                ctx.display_list,
                "remove" if self.indeterminate else "check",
                x=absolute.x,
                y=absolute.y,
                size=self.BOX,
                weight=500,
                pixel_ratio=ctx.pixel_ratio,
                token=on_primary,
                color=(1.0, 1.0, 1.0, t),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )


class RadioElement(_StyledMixin, Padding):
    """M3 Radio: 20dp outer circle, 10dp inner dot when selected."""

    OUTER: Final = 20.0
    INNER: Final = 10.0
    CURSOR = "pointer"

    @override
    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self.OUTER / 2,) * 4

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        return self.sized(constraints, self.style).constrain(Size(self.OUTER, self.OUTER))

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        selected = self.checked
        active = ctx.palette.index(self.style.background or "primary")
        inactive = ctx.palette.index("on_surface_variant")
        ring = active if selected else inactive
        _emit_state_layer(ctx, self, absolute, ring, (self.OUTER / 2,) * 4)

        t = self.animated(
            "selected",
            1.0 if selected else 0.0,
            duration=SELECTION_MOTION,
            curve=SELECTION_CURVE,
        )
        # A circle is a rounded box with radius = half the side. Tokens cannot
        # be interpolated -- the palette is resolved in the shader -- so the
        # ring colour is cross-faded by drawing both rings instead.
        for token, weight in ((inactive, 1.0 - t), (active, t)):
            if weight > 0.0:
                _box(
                    ctx,
                    absolute.x,
                    absolute.y,
                    self.OUTER,
                    self.OUTER,
                    token=token,
                    radius=self.OUTER / 2,
                    alpha=0.0,
                    border_width=2.0,
                    border_token=token,
                    border_alpha=weight,
                )
        # The dot grows out of the centre rather than appearing whole.
        inner = self.INNER * t
        if inner > 0.5:
            pad = (self.OUTER - inner) / 2
            _box(
                ctx,
                absolute.x + pad,
                absolute.y + pad,
                inner,
                inner,
                token=active,
                radius=inner / 2,
            )


class SwitchElement(_StyledMixin, Padding):
    """M3 Switch: 52x32dp track; thumb 16dp unselected, 24dp selected.

    The thumb slides and grows rather than jumping. M3 states the timing for
    this directly -- "Selection controls have a short duration of 200ms with
    Standard easing" -- so it is `short4` and `standard`, not a guess.

    Position and size animate on separate curves-in-name-only (both are the
    same token) but as separate values, because they travel different
    distances and interrupting one must not disturb the other.

    **Tap already worked; drag did not.** M3's own interaction table names
    both explicitly ("Touch: Tap, Drag"; `COMPONENT_SWITCH.md`). Tap needed
    no change: `EventDispatcher._dispatch_pointer`'s own generic rule ("a
    click is press and release over the same element") already synthesises
    `on_click` for any widget a view gives one to, whether or not the widget
    class defines its own pointer methods -- confirmed directly, not assumed,
    since it is easy to mistake "this class defines no `on_click`" for "this
    widget cannot be clicked" (checked here specifically because that
    mistake would have led to reimplementing, and then double-firing, a tap
    that already worked). What was genuinely missing was recognising a real
    drag as a *distinct* gesture: `on_pointer_down`/`_up` add exactly that,
    without touching the tap path at all. A release still inside the track
    is left alone -- the dispatcher's own click rule already covers it, and
    firing again here would toggle it twice, right back to where it started
    (this was tried and caught by testing, not spotted by inspection). Only
    a release that lands *outside* the track -- a real drag past the far
    edge, the same distance a physical toggle's thumb would have to travel
    -- is decided here, from which side of the press point it ended up on,
    and only invokes `on_click:` when that actually disagrees with the
    current value (dragging further toward the side already showing fires
    nothing, since the view's own `on_click:` is a blind toggle with no way
    to say "set to left" versus "set to right"). No visual live-follow
    during the drag is attempted -- the thumb only moves once the value
    actually changes, the same interaction-recognition-without-full-motion
    line `Carousel`'s snap-only physics already draws.
    """

    TRACK_W: Final = 52.0
    TRACK_H: Final = 32.0
    CURSOR = "pointer"
    THUMB_OFF: Final = 16.0
    THUMB_ON: Final = 24.0
    MOTION: Final = SELECTION_MOTION
    CURVE: Final = SELECTION_CURVE

    @override
    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self.TRACK_H / 2,) * 4

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        return self.sized(constraints, self.style).constrain(Size(self.TRACK_W, self.TRACK_H))

    # ------------------------------------------------------------- pointer

    def on_pointer_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        self.state.data["switch_press_x"] = event.x
        # Capture is what lets `on_pointer_up` see a release past the far
        # edge of the track at all -- without it, a release outside this
        # element's own bounds would hit-test to whatever is under the
        # pointer instead, the same reason a drag anywhere else in this
        # codebase (`BottomSheet`, `SideSheet`) claims capture on press.
        event.capture()

    def on_pointer_up(self, event: Any) -> None:
        if self.effective_disabled:
            return
        start_x = self.state.data.pop("switch_press_x", None)
        if start_x is None:
            return
        rect = self.absolute_rect()
        if rect.x <= event.x <= rect.x + rect.width:
            # Still over the track: `_dispatch_pointer`'s own generic click
            # rule already fires `on_click` for this release (press and
            # release over the same element), so this is a tap or a small
            # in-track drag either way -- nothing further to do here.
            return
        # A real drag past the track's edge: which side of the press point
        # the release ended up on decides the target, and only invoking
        # `on_click:` when that disagrees with the current value is what
        # keeps a blind-toggle handler correct for a drag as well as a tap.
        target = event.x > start_x
        if target != self.checked:
            handler = self.handlers.get("on_click")
            if handler is not None:
                handler(event)

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        on = self.checked
        track = ctx.palette.index(
            (self.style.background or "primary") if on else "surface_container_highest"
        )
        thumb = ctx.palette.index("on_primary" if on else "outline")
        radius = self.TRACK_H / 2

        _box(
            ctx,
            absolute.x,
            absolute.y,
            self.TRACK_W,
            self.TRACK_H,
            token=track,
            radius=radius,
            border_width=0.0 if on else 2.0,
            border_token=ctx.palette.index("outline"),
        )
        _emit_state_layer(ctx, self, absolute, track, (radius,) * 4)

        size = self.animated(
            "thumb_size",
            self.THUMB_ON if on else self.THUMB_OFF,
            duration=self.MOTION,
            curve=self.CURVE,
        )
        # Travel is expressed as 0..1 and mapped to pixels afterwards, so the
        # thumb keeps ending flush with the track however its size animates.
        travel = self.animated(
            "thumb_pos", 1.0 if on else 0.0, duration=self.MOTION, curve=self.CURVE
        )
        margin = (self.TRACK_H - size) / 2
        x = absolute.x + margin + (self.TRACK_W - size - margin * 2) * travel
        _box(ctx, x, absolute.y + margin, size, size, token=thumb, radius=size / 2)


# ------------------------------------------------------------------- chips


class ChipElement(_StyledMixin, Padding):
    """M3 Chip: 32dp high, 8dp radius, 1dp outline, optional 18dp leading icon.

    A filter chip shows a leading checkmark when selected, which is what the
    `value:` binding drives.
    """

    HEIGHT: Final = 32.0
    RADIUS: Final = 8.0
    ICON: Final = 18.0
    CURSOR = "pointer"
    GAP: Final = 6.0
    PAD_X: Final = 12.0

    @override
    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self.RADIUS,) * 4

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @property
    def _is_filter(self) -> bool:
        return self.style.variant == "filter"

    def _check_progress(self) -> float:
        """How far the leading checkmark has slid in, 0 to 1.

        This changes the chip's **width**, so it invalidates layout rather than
        paint -- the label and every sibling in the row move with it, which is
        the behaviour M3 describes. A chip row is a handful of elements, so the
        relayout is affordable; see the Carousel (5.16) for the same trade.
        """
        if not self._is_filter:
            return 0.0
        value: float = self.animated(
            "selected",
            1.0 if self.checked else 0.0,
            duration=SELECTION_MOTION,
            curve=SELECTION_CURVE,
            invalidates="layout",
        )
        return value

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        style = self.style
        label = measure_text(self._text, style.font_size, engine=self.text_engine)
        width = self.PAD_X * 2 + label.width + (self.ICON + self.GAP) * self._check_progress()
        return self.sized(constraints, style).constrain(Size(width, self.HEIGHT))

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        selected = self._is_filter and self.checked
        t = self._check_progress()
        content = style.color or ("on_secondary_container" if selected else "on_surface_variant")
        content_tok = ctx.palette.index(content)

        containers: tuple[tuple[int, float], ...]
        if style.background:
            containers = ((ctx.palette.index(style.background), 1.0),)
        else:
            # Cross-fade the container the same way as the Radio's ring: the
            # palette is resolved in the shader, so two boxes, not one lerp.
            containers = (
                (ctx.palette.index("surface"), 1.0 - t),
                (ctx.palette.index("secondary_container"), t),
            )
        for token, weight in containers:
            if weight <= 0.0:
                continue
            # The outline belongs to the unselected chip and fades with it. The
            # width must drop to zero as well, not just the alpha: the shader
            # insets the fill by the border width, so a fully transparent 1dp
            # border would leave a transparent ring where the fill should reach.
            border_alpha = (1.0 - t) * weight
            _box(
                ctx,
                absolute.x,
                absolute.y,
                self.size.width,
                self.size.height,
                token=token,
                radius=self.RADIUS,
                alpha=weight,
                border_width=1.0 if border_alpha > 0.0 else 0.0,
                border_token=ctx.palette.index("outline_variant"),
                border_alpha=border_alpha,
            )
        _emit_state_layer(ctx, self, absolute, content_tok, (self.RADIUS,) * 4)

        x = absolute.x + self.PAD_X
        if t > 0.0:
            # The checkmark grows into the space being made for it. Drawn at
            # full size it would overlap the label, which has only travelled a
            # fraction of the way -- visible as "check-Filter" mid-transition.
            icon = self.ICON * t
            ctx.text.emit_icon(
                ctx.display_list,
                "check",
                x=x,
                y=absolute.y + (self.HEIGHT - icon) / 2,
                size=icon,
                pixel_ratio=ctx.pixel_ratio,
                token=content_tok,
                color=(1.0, 1.0, 1.0, t),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )
            x += (self.ICON + self.GAP) * t
        if self._text.strip():
            label = measure_text(self._text, style.font_size, engine=self.text_engine)
            paint_text(
                ctx,
                x,
                absolute.y + (self.HEIGHT - label.height) / 2,
                self._text,
                style.font_size,
                content_tok,
            )


# ------------------------------------------------------------- icon buttons


class IconButtonElement(_StyledMixin, Padding):
    """M3 Icon Button: 40dp container, 24dp icon, full radius, four variants."""

    SIZE: Final = 40.0

    #: variant -> (container token or None for uncontained, content token)
    VARIANTS: Final = {
        "standard": (None, "on_surface_variant"),
        "filled": ("primary", "on_primary"),
        "filled_tonal": ("secondary_container", "on_secondary_container"),
        "outlined": (None, "on_surface_variant"),
    }

    @override
    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self.size.height / 2,) * 4

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        return self.sized(constraints, self.style).constrain(Size(self.SIZE, self.SIZE))

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        variant = style.variant if style.variant in self.VARIANTS else "standard"
        container, content = self.VARIANTS[variant]
        radius = self.size.height / 2
        content_tok = ctx.palette.index(style.color or content)

        if style.background or container:
            _box(
                ctx,
                absolute.x,
                absolute.y,
                self.size.width,
                self.size.height,
                token=ctx.palette.index(style.background or container or "primary"),
                radius=radius,
            )
        if variant == "outlined":
            _box(
                ctx,
                absolute.x,
                absolute.y,
                self.size.width,
                self.size.height,
                token=ctx.palette.index("outline"),
                radius=radius,
                alpha=0.0,
                border_width=1.0,
                border_token=ctx.palette.index("outline"),
            )

        _emit_state_layer(ctx, self, absolute, content_tok, (radius,) * 4)

        icon = style.icon_size or DEFAULT_ICON_SIZE
        if self._icon.strip():
            ctx.text.emit_icon(
                ctx.display_list,
                self._icon.strip(),
                x=absolute.x + (self.size.width - icon) / 2,
                y=absolute.y + (self.size.height - icon) / 2,
                size=icon,
                fill=style.icon_fill,
                weight=style.icon_weight,
                pixel_ratio=ctx.pixel_ratio,
                token=content_tok,
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )


class FabElement(_StyledMixin, Padding):
    """M3 FAB: standard 56dp/16dp radius, small 40/12, large 96/28 with a 36dp icon.

    Defaults to `primary_container` on `on_primary_container`, M3's default
    colour mapping. M3 puts a FAB at resting **level 3**, alongside modal
    dialogs -- the highest resting level any component uses.

    `variant: extended` is the fifth M3 size, and the odd one out: 56dp tall
    like `standard` and the same 16dp radius, but a **dynamic width** (80dp
    minimum) driven by its content rather than a fixed square -- icon (`icon:`)
    plus a text label (`label:`), 16dp padding on every side, an 8dp gap
    between them (`COMPONENT_EXTENDED_FABS.md`'s own measurements: "Container
    height 56dp, Container width Dynamic, 80dp min, Padding 16dp"). An
    extended FAB with no label just measures as an icon-only pill at the
    80dp floor, which is a legitimate fallback rather than a special case to
    guard against.
    """

    RESTING_ELEVATION = 3

    #: variant -> (container size, corner radius, icon size). `extended`'s
    #: first element is unused (its width is computed, not fixed) but kept
    #: so `_geometry()` returns a uniform 3-tuple for every variant.
    SIZES: Final = {
        "small": (40.0, 12.0, 24.0),
        "standard": (56.0, 16.0, 24.0),
        "medium": (80.0, 20.0, 28.0),
        "large": (96.0, 28.0, 36.0),
        "extended": (56.0, 16.0, 24.0),
    }
    EXTENDED_MIN_WIDTH: Final = 80.0
    EXTENDED_PAD_X: Final = 16.0
    EXTENDED_GAP: Final = 8.0

    @override
    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self._geometry()[1],) * 4

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def _geometry(self) -> tuple[float, float, float]:
        variant = self.style.variant
        return self.SIZES.get(variant, self.SIZES["standard"])

    def _label_width(self) -> float:
        label = self._label.strip()
        if not label:
            return 0.0
        return measure_text(label, self.style.font_size, engine=self.text_engine).width

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        height, _, icon = self._geometry()
        if self.style.variant == "extended":
            has_icon = bool(self._icon.strip())
            label_width = self._label_width()
            content = (icon if has_icon else 0.0) + (
                self.EXTENDED_GAP + label_width if has_icon and label_width else label_width
            )
            width = max(self.EXTENDED_MIN_WIDTH, content + 2 * self.EXTENDED_PAD_X)
            return self.sized(constraints, self.style).constrain(Size(width, height))
        return self.sized(constraints, self.style).constrain(Size(height, height))

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        _, radius, icon = self._geometry()
        container = ctx.palette.index(style.background or "primary_container")
        content = content_token(ctx, style, "on_primary_container")

        # Elevation level 3, shadow only -- the tonal half is not modelled.
        elevation_shadow(
            ctx,
            absolute.x,
            absolute.y,
            self.size.width,
            self.size.height,
            level=self.elevation,
            radii=(radius,) * 4,
        )
        _box(
            ctx,
            absolute.x,
            absolute.y,
            self.size.width,
            self.size.height,
            token=container,
            radius=radius,
        )
        _emit_state_layer(ctx, self, absolute, content, (radius,) * 4)

        if style.variant == "extended":
            self._paint_extended(ctx, absolute, icon, content)
        elif self._icon.strip():
            ctx.text.emit_icon(
                ctx.display_list,
                self._icon.strip(),
                x=absolute.x + (self.size.width - icon) / 2,
                y=absolute.y + (self.size.height - icon) / 2,
                size=icon,
                fill=style.icon_fill,
                weight=style.icon_weight,
                pixel_ratio=ctx.pixel_ratio,
                token=content,
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )

    def _paint_extended(self, ctx: PaintContext, absolute: Any, icon: float, content: int) -> None:
        style = self.style
        label = self._label.strip()
        has_icon = bool(self._icon.strip())
        label_width = self._label_width()
        total = (icon if has_icon else 0.0) + (
            self.EXTENDED_GAP + label_width if has_icon and label else label_width
        )
        x = absolute.x + (self.size.width - total) / 2
        y_center = absolute.y + self.size.height / 2

        if has_icon:
            ctx.text.emit_icon(
                ctx.display_list,
                self._icon.strip(),
                x=x,
                y=y_center - icon / 2,
                size=icon,
                fill=style.icon_fill,
                weight=style.icon_weight,
                pixel_ratio=ctx.pixel_ratio,
                token=content,
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )
            x += icon + self.EXTENDED_GAP

        if label:
            metrics = measure_text(label, style.font_size, engine=self.text_engine)
            paint_text(ctx, x, y_center - metrics.height / 2, label, style.font_size, content)


# ----------------------------------------------------------------- spin box


class SpinBoxElement(_StyledMixin, Padding):
    """A numeric value with increment/decrement buttons.

    M3 has no dedicated component for this. Deliberately named `SpinBox`
    rather than the more common "Stepper" to avoid a real collision: M3's
    own (M2-inherited) vocabulary uses "Stepper" for a multi-step flow
    indicator, a completely different widget this is not.

    The nearest M3 grounding is the Sliders page's convention for the same
    underlying need -- "Icon buttons placed outside the slider should have
    the button role" -- applied here as two 40dp icon-button regions
    (`IconButton`'s own anatomy: no container, `on_surface_variant`
    content) flanking a numeric display, rather than only at a slider's
    ends.

    `value:` is the current number, read through the same generic
    `number` property every other value-bearing widget uses. Clicking
    either side computes the new value itself (clamped to `style.min`/
    `style.max`, stepped by `style.step`), updates its own display
    immediately, and fires `on_change` with the result -- the same split
    `TextField._commit` already makes between updating its own display and
    telling the application what changed. Arrow keys do the same, borrowing
    Sliders' own quoted keyboard convention ("Arrows: Increase and decrease
    the value") since no closer M3 analogue exists.

    A side at its bound dims to M3's disabled-content opacity (38%) --
    reused by analogy, not because this component is actually disabled --
    and stops responding, but keeps a plain pointer cursor rather than
    "not-allowed"; only the whole element's `cursor_at` is a place to hang a
    cursor override, not one half of it. Hover feedback is per side; press
    and focus are not, since neither is tracked per-region anywhere else in
    the framework and adding it here would be new machinery for one widget.

    **Deliberately out of scope: typing a value directly.** That needs
    `TextField`'s whole editing machinery (caret, selection, IME) for what
    would otherwise be a half-built text field wearing a SpinBox's paint.
    Only the two buttons and the keyboard are wired.
    """

    SIZE: Final = 40.0
    ICON: Final = 24.0
    VALUE_MIN_WIDTH: Final = 32.0
    VALUE_PAD_X: Final = 8.0
    #: Reuses M3's disabled-content opacity for a bound that can't move
    #: further -- the same visual language, not the same mechanism as
    #: `effective_disabled` (which recolours the whole element automatically).
    AT_BOUND_OPACITY: Final = 0.38
    CURSOR = "pointer"

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @staticmethod
    def _format(n: float) -> str:
        return str(int(n)) if n == int(n) else str(n)

    def _clamped(self, value: float) -> float:
        style = self.style
        if style.min is not None:
            value = max(style.min, value)
        if style.max is not None:
            value = min(style.max, value)
        return value

    def _step(self, direction: float) -> None:
        if self.effective_disabled:
            return
        new = self._clamped(self.number + direction * self.style.step)
        if new == self.number:
            return
        self._value = self._format(new)
        handler = self.handlers.get("on_change")
        if handler is not None:
            handler(ChangeEvent(EventType.CHANGE, target=self, value=self._value))
        self.mark_needs_layout()

    def _value_width(self) -> float:
        label = measure_text(
            self._format(self.number), self.style.font_size, engine=self.text_engine
        )
        return max(self.VALUE_MIN_WIDTH, label.width + 2 * self.VALUE_PAD_X)

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = 2 * self.SIZE + self._value_width()
        return outer.constrain(Size(width, self.SIZE))

    # ------------------------------------------------------------- pointer

    def _side_at(self, x: float) -> str | None:
        local = x - self.absolute_rect().x
        if local < self.SIZE:
            return "dec"
        if local > self.size.width - self.SIZE:
            return "inc"
        return None

    def on_click(self, event: Any) -> None:
        side = self._side_at(event.x)
        if side == "dec":
            self._step(-1.0)
        elif side == "inc":
            self._step(1.0)

    def on_pointer_move(self, event: Any) -> None:
        side = self._side_at(event.x)
        if self.state.data.get("spin_hover") != side:
            self.state.data["spin_hover"] = side
            self.mark_needs_paint()

    def on_pointer_leave(self, event: Any) -> None:
        if self.state.data.get("spin_hover") is not None:
            self.state.data["spin_hover"] = None
            self.mark_needs_paint()

    # ---------------------------------------------------------------- keys

    def on_key_down(self, event: Any) -> None:
        key = str(getattr(event, "key", "")).lower()
        if key in ("up", "right"):
            self._step(1.0)
        elif key in ("down", "left"):
            self._step(-1.0)

    # --------------------------------------------------------------- paint

    def _side_alpha(self, side: str) -> float:
        target = HOVER if self.state.data.get("spin_hover") == side else 0.0
        return self.animated(
            f"spin_{side}", target, duration=STATE_LAYER_MOTION, curve=STATE_LAYER_CURVE
        )

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        content = content_token(ctx, style, "on_surface_variant")
        dpr = ctx.pixel_ratio
        at_min = style.min is not None and self.number <= style.min
        at_max = style.max is not None and self.number >= style.max

        for side, icon, center_x, at_bound in (
            ("dec", "remove", absolute.x + self.SIZE / 2, at_min),
            ("inc", "add", absolute.x + self.size.width - self.SIZE / 2, at_max),
        ):
            if not at_bound:
                alpha = self._side_alpha(side)
                if alpha > 0.001:
                    ctx.display_list.add_box(
                        (center_x - self.SIZE / 2) * dpr,
                        absolute.y * dpr,
                        self.SIZE * dpr,
                        self.SIZE * dpr,
                        token=content,
                        color=(1.0, 1.0, 1.0, alpha),
                        radii=(self.SIZE / 2 * dpr,) * 4,
                        clip=ctx.clip,
                        clip_radii=ctx.clip_radii,
                    )
            ctx.text.emit_icon(
                ctx.display_list,
                icon,
                x=center_x - self.ICON / 2,
                y=absolute.y + (self.SIZE - self.ICON) / 2,
                size=self.ICON,
                pixel_ratio=dpr,
                token=content,
                color=(1.0, 1.0, 1.0, self.AT_BOUND_OPACITY if at_bound else 1.0),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )

        value_text = self._format(self.number)
        label = measure_text(value_text, style.font_size, engine=self.text_engine)
        value_token = content_token(ctx, style, "on_surface")
        paint_text(
            ctx,
            absolute.x + self.SIZE + (self._value_width() - label.width) / 2,
            absolute.y + (self.SIZE - label.height) / 2,
            value_text,
            style.font_size,
            value_token,
        )


# -------------------------------------------------------------- pagination


class PaginationElement(_StyledMixin, Padding):
    """Page-number navigation: prev/next arrows around a row of page numbers.

    M3 has no Pagination component -- checked directly, not assumed to be
    missing: "pagination" appears in the whole reference library exactly
    once, and only as a prohibition ("Cards shouldn't contain content that
    can be swiped, such as an image carousel or pagination"). Nothing here
    is therefore quoted from a spec. The anatomy borrows `IconButton`'s own
    (40dp, no container, `on_surface_variant`) for the prev/next arrows and
    unselected page numbers, and the same selected pairing `Chip`/`Segment`
    already use (`secondary_container` / `on_secondary_container`) for the
    current page.

    `value:` is the current page, 1-indexed -- matching how a person reads
    "page 3 of 10", not a 0-indexed offset -- and `style.count` is the
    total. Clicking a page number or an arrow (or the Left/Right keys)
    computes the new page and fires `on_change` with it already settled,
    the same division every other value-bearing control here makes.

    **Windowing**, since nothing sources one either: always show the first
    and last page and the current page's immediate neighbours, collapsing
    any larger gap into a non-interactive "…". Below eight pages nothing is
    ever collapsed -- an ellipsis saves no room when it would replace only
    one or two numbers. A consequence worth stating rather than hiding: the
    control's own width changes slightly as the current page moves between
    the edges (fewer numbers shown) and the middle (an ellipsis on each
    side) -- the same minor variance most page-number widgets have.

    **Hover is intentionally not animated, unlike every other state layer in
    this file.** Those all use a fixed, small set of keys (SpinBox has
    exactly two). A page count is unbounded, and an `animated()` call
    creates a persistent entry in `self._animations` that nothing ever
    evicts -- keying one per page number would leak one entry per page a
    user ever hovered over a long session. Hover here is therefore a single
    tracked slot (`state.data["page_hover"]`, overwritten in place) painted
    at a flat opacity: real feedback, without state that grows without
    bound.
    """

    BUTTON: Final = 40.0
    GAP: Final = 4.0
    ICON: Final = 24.0
    #: Reuses M3's disabled-content opacity for a boundary arrow that can't
    #: move further -- the same visual language `SpinBox` reuses, not the
    #: same mechanism as `effective_disabled`.
    AT_BOUND_OPACITY: Final = 0.38
    CURSOR = "pointer"

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def _current(self) -> int:
        return max(1, min(int(self.number) or 1, max(1, self.style.count)))

    def _pages(self) -> list[int | None]:
        """The page numbers to show, `None` marking a collapsed run."""
        count = max(1, self.style.count)
        if count <= 7:
            return list(range(1, count + 1))
        current = self._current()
        shown = {1, count, current}
        for delta in (-1, 1):
            candidate = current + delta
            if 1 <= candidate <= count:
                shown.add(candidate)
        ordered = sorted(shown)
        result: list[int | None] = []
        previous: int | None = None
        for page in ordered:
            if previous is not None and page - previous > 1:
                result.append(None)
            result.append(page)
            previous = page
        return result

    def _slots(self) -> list[tuple[str, int | None]]:
        slots: list[tuple[str, int | None]] = [("prev", None)]
        for page in self._pages():
            slots.append(("page", page) if page is not None else ("ellipsis", None))
        slots.append(("next", None))
        return slots

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        n = len(self._slots())
        width = n * self.BUTTON + max(0, n - 1) * self.GAP
        return outer.constrain(Size(width, self.BUTTON))

    # ------------------------------------------------------------- pointer

    def _slot_at(self, x: float) -> tuple[str, int | None] | None:
        local = x - self.absolute_rect().x
        cursor = 0.0
        for kind, page in self._slots():
            if cursor <= local < cursor + self.BUTTON:
                return (kind, page)
            cursor += self.BUTTON + self.GAP
        return None

    def _goto(self, page: int) -> None:
        self._value = str(page)
        handler = self.handlers.get("on_change")
        if handler is not None:
            handler(ChangeEvent(EventType.CHANGE, target=self, value=self._value))
        self.mark_needs_layout()

    def on_click(self, event: Any) -> None:
        if self.effective_disabled:
            return
        hit = self._slot_at(event.x)
        if hit is None:
            return
        kind, page = hit
        current = self._current()
        count = max(1, self.style.count)
        if kind == "prev" and current > 1:
            self._goto(current - 1)
        elif kind == "next" and current < count:
            self._goto(current + 1)
        elif kind == "page" and page is not None and page != current:
            self._goto(page)

    def on_pointer_move(self, event: Any) -> None:
        hit = self._slot_at(event.x)
        if self.state.data.get("page_hover") != hit:
            self.state.data["page_hover"] = hit
            self.mark_needs_paint()

    def on_pointer_leave(self, event: Any) -> None:
        if self.state.data.get("page_hover") is not None:
            self.state.data["page_hover"] = None
            self.mark_needs_paint()

    # ---------------------------------------------------------------- keys

    def on_key_down(self, event: Any) -> None:
        key = str(getattr(event, "key", "")).lower()
        current = self._current()
        count = max(1, self.style.count)
        if key == "right" and current < count:
            self._goto(current + 1)
        elif key == "left" and current > 1:
            self._goto(current - 1)

    # --------------------------------------------------------------- paint

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        content = content_token(ctx, style, "on_surface_variant")
        selected_bg = ctx.palette.index("secondary_container")
        selected_content = ctx.palette.index("on_secondary_container")
        dpr = ctx.pixel_ratio
        current = self._current()
        count = max(1, style.count)
        hovered = self.state.data.get("page_hover")

        cursor = 0.0
        for kind, page in self._slots():
            x = absolute.x + cursor
            if kind == "ellipsis":
                label = measure_text("...", style.font_size, engine=self.text_engine)
                paint_text(
                    ctx,
                    x + (self.BUTTON - label.width) / 2,
                    absolute.y + (self.BUTTON - label.height) / 2,
                    "...",
                    style.font_size,
                    content,
                )
                cursor += self.BUTTON + self.GAP
                continue

            at_bound = (kind == "prev" and current <= 1) or (kind == "next" and current >= count)
            selected = kind == "page" and page == current
            if selected:
                ctx.display_list.add_box(
                    x * dpr,
                    absolute.y * dpr,
                    self.BUTTON * dpr,
                    self.BUTTON * dpr,
                    token=selected_bg,
                    radii=(self.BUTTON / 2 * dpr,) * 4,
                    clip=ctx.clip,
                    clip_radii=ctx.clip_radii,
                )
            elif hovered == (kind, page) and not at_bound:
                ctx.display_list.add_box(
                    x * dpr,
                    absolute.y * dpr,
                    self.BUTTON * dpr,
                    self.BUTTON * dpr,
                    token=content,
                    color=(1.0, 1.0, 1.0, HOVER),
                    radii=(self.BUTTON / 2 * dpr,) * 4,
                    clip=ctx.clip,
                    clip_radii=ctx.clip_radii,
                )

            token = selected_content if selected else content
            if kind == "page":
                label = measure_text(str(page), style.font_size, engine=self.text_engine)
                paint_text(
                    ctx,
                    x + (self.BUTTON - label.width) / 2,
                    absolute.y + (self.BUTTON - label.height) / 2,
                    str(page),
                    style.font_size,
                    token,
                )
            else:
                icon = "chevron_left" if kind == "prev" else "chevron_right"
                ctx.text.emit_icon(
                    ctx.display_list,
                    icon,
                    x=x + (self.BUTTON - self.ICON) / 2,
                    y=absolute.y + (self.BUTTON - self.ICON) / 2,
                    size=self.ICON,
                    pixel_ratio=dpr,
                    token=token,
                    color=(1.0, 1.0, 1.0, self.AT_BOUND_OPACITY if at_bound else 1.0),
                    clip=ctx.clip,
                    clip_radii=ctx.clip_radii,
                )
            cursor += self.BUTTON + self.GAP


# ------------------------------------------------------------------ badges


class BadgeElement(_StyledMixin, Padding):
    """M3 Badge: a 6dp dot, or a 16dp-high numbered pill with 4dp padding.

    `value:` carries the count, so it tracks a signal.
    """

    DOT: Final = 6.0
    HEIGHT: Final = 16.0
    PAD_X: Final = 4.0
    LABEL_SIZE: Final = 11.0

    @override
    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self.size.height / 2,) * 4

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @property
    def _displayed(self) -> str:
        """`value:` if set, else `text:`. Not the framework's `label:`
        binding -- Badge has no icon+label anatomy, just one displayed
        string with two possible sources."""
        return self._value.strip() or self._text.strip()

    @property
    def _is_dot(self) -> bool:
        return self.style.variant == "dot" or not self._displayed

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        if self._is_dot:
            return outer.constrain(Size(self.DOT, self.DOT))
        label = measure_text(self._displayed, self.LABEL_SIZE, engine=self.text_engine)
        width = max(self.HEIGHT, label.width + self.PAD_X * 2)
        return outer.constrain(Size(width, self.HEIGHT))

    @override
    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        container = ctx.palette.index(style.background or "error")
        content = content_token(ctx, style, "on_error")
        radius = self.size.height / 2

        _box(
            ctx,
            absolute.x,
            absolute.y,
            self.size.width,
            self.size.height,
            token=container,
            radius=radius,
        )
        if self._is_dot:
            return
        label = measure_text(self._displayed, self.LABEL_SIZE, engine=self.text_engine)
        paint_text(
            ctx,
            absolute.x + (self.size.width - label.width) / 2,
            absolute.y + (self.size.height - label.height) / 2,
            self._displayed,
            self.LABEL_SIZE,
            content,
        )
