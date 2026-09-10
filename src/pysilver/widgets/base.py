"""Concrete widgets: an element mixin combined with a layout algorithm.

Each class is ``ElementMixin`` (empty ``__slots__``, so no layout contribution)
plus exactly one M1 layout node. The subclass declares no ``__slots__`` of its
own, so it gains a ``__dict__`` for the element fields -- which is what lets a
slotted layout base and the mixin coexist without an instance-layout conflict.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from ..layout import (
    Alignment,
    Axis,
    Constraints,
    CrossAxisAlignment,
    EdgeInsets,
    Flex,
    MainAxisAlignment,
    MainAxisSize,
    Padding,
    Size,
    Stack,
)
from ..paint import NO_TOKEN
from ..spec import StyleSpec, WidgetSpec
from ..spec.typescale import TYPE_SCALE, TypeStyle
from ..text import TextEngine
from ..text.fontdb import FontRequest
from ..text.layout import Alignment as TextAlignment
from ..theme import is_token
from ..tree.element import ElementMixin, PaintContext, default_text_engine

__all__ = [
    "ButtonElement",
    "ContainerElement",
    "HorizontalElement",
    "IconElement",
    "LinkElement",
    "SpacerElement",
    "StackElement",
    "TextElement",
    "VerticalElement",
    "content_token",
    "measure_text",
    "paint_text",
    "paired_content_token",
]

_MAIN = {
    "start": MainAxisAlignment.START,
    "end": MainAxisAlignment.END,
    "center": MainAxisAlignment.CENTER,
    "space_between": MainAxisAlignment.SPACE_BETWEEN,
    "space_around": MainAxisAlignment.SPACE_AROUND,
    "space_evenly": MainAxisAlignment.SPACE_EVENLY,
}
_CROSS = {
    "start": CrossAxisAlignment.START,
    "end": CrossAxisAlignment.END,
    "center": CrossAxisAlignment.CENTER,
    "stretch": CrossAxisAlignment.STRETCH,
}


def _resolve_axis(spec_size: Any, available: float) -> float | None:
    """Turn a SizeSpec into a concrete extent, or None to mean 'use content'."""
    match spec_size.kind:
        case "fixed":
            return float(spec_size.value)
        case "expand":
            return available
        case "percent":
            return available * float(spec_size.value)
        case _:
            return None


def content_token(ctx: PaintContext, style: StyleSpec, default: str) -> int:
    """Palette index for a widget's content colour.

    `style.color` of None means "use this widget's M3 default for its variant",
    so each component supplies its own rather than inheriting a global one.
    """
    return ctx.palette.index(style.color or default)


def paired_content_token(ctx: PaintContext, style: StyleSpec, default: str) -> int:
    """Content colour that follows an overridden container.

    M3 pairs a container role with an `on_` role -- `primary_container` with
    `on_primary_container` -- so a widget whose background the view has
    changed should change its content colour with it. Without this, a label
    keeps the default's `on_surface` and turns near-invisible the moment
    someone sets a light container.

    Only used where the whole surface is the widget's own (a carousel item);
    a component whose background is one part of a larger anatomy keeps its
    variant's content token.
    """
    if style.color:
        return ctx.palette.index(style.color)
    if style.background:
        paired = f"on_{style.background}"
        if is_token(paired):
            return ctx.palette.index(paired)
    return ctx.palette.index(default)


class _StyledMixin(ElementMixin):
    """Applies width/height/padding from the spec around a layout algorithm."""

    def sized(self, constraints: Constraints, style: StyleSpec) -> Constraints:
        w = _resolve_axis(style.width, constraints.max_width)
        h = _resolve_axis(style.height, constraints.max_height)
        return constraints.tighten(width=w, height=h)


class ContainerElement(_StyledMixin, Padding):
    """A styled box with padding and at most one child."""

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, spec.style.padding)
        self.init_element(spec)

    def configure(self) -> None:
        self._padding = self.style.padding

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        inner = super().perform_layout(outer.loosen() if not outer.is_tight else outer)
        return outer.constrain(inner)


def _main_size_for(axis: Axis, style: StyleSpec) -> MainAxisSize:
    """Fill the main axis only when the view sized THAT axis.

    The main axis of a Vertical is its HEIGHT. Keying this off `width` made a
    Vertical with `width: expand` greedily fill vertically as well.
    """
    sized = style.width if axis is Axis.HORIZONTAL else style.height
    return MainAxisSize.MAX if sized.kind != "auto" else MainAxisSize.MIN


class _FlexElement(_StyledMixin, Flex):
    axis: Axis = Axis.HORIZONTAL

    def __init__(self, spec: WidgetSpec) -> None:
        style = spec.style
        Flex.__init__(
            self,
            axis=self.axis,
            main_alignment=_MAIN[style.main_alignment],
            cross_alignment=_CROSS[style.cross_alignment],
            main_size=_main_size_for(self.axis, style),
            spacing=style.spacing,
        )
        self._padding = style.padding
        self.init_element(spec)

    def flex_of(self, child: Any) -> int:
        """A child styled `expand` or `flex:n` along the main axis is flexible.

        Without this a Spacer with `width: expand` is treated as inflexible,
        measured against all remaining space, and starves its siblings.
        """
        explicit = super().flex_of(child)
        if explicit:
            return explicit
        if not isinstance(child, ElementMixin):
            return 0
        size = child.style.width if self.axis is Axis.HORIZONTAL else child.style.height
        if size.kind == "flex":
            return max(1, int(size.value))
        return 1 if size.kind == "expand" else 0

    def configure(self) -> None:
        style = self.style
        self._main_alignment = _MAIN[style.main_alignment]
        self._cross_alignment = _CROSS[style.cross_alignment]
        self._spacing = style.spacing
        self._main_size = _main_size_for(self.axis, style)
        self._padding = style.padding

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        pad: EdgeInsets = self._padding
        inner = super().perform_layout(outer.deflate(pad))
        for child in self.children:
            child.offset = child.offset + pad.top_left
        return outer.constrain(inner.inflate(pad))


class HorizontalElement(_FlexElement):
    axis = Axis.HORIZONTAL


class VerticalElement(_FlexElement):
    axis = Axis.VERTICAL


class StackElement(_StyledMixin, Stack):
    """Overlays children, each positioned by its OWN `style.align_x`/`align_y`
    when it sets one, falling back to the group's own `align_x`/`align_y`
    otherwise -- not one alignment forced onto every child regardless of what
    it asked for. The base `Stack` layout node knows nothing about style (the
    four-tree split keeps the layout layer spec-unaware), so it can only
    place every child at one shared `self._alignment`; this class
    re-positions each child itself afterward, reading its own style
    directly. `model_fields_set` is what tells "this child wrote align_x"
    apart from "nobody set anything, so the group's own value applies" --
    the same idiom `DockSplit.axis` already uses for an identical ambiguity.
    """

    def __init__(self, spec: WidgetSpec) -> None:
        Stack.__init__(self)
        self.init_element(spec)

    def perform_layout(self, constraints: Constraints) -> Size:
        size = super().perform_layout(self.sized(constraints, self.style))
        for child in self.children:
            fields = child.style.model_fields_set
            align_x = child.style.align_x if "align_x" in fields else self.style.align_x
            align_y = child.style.align_y if "align_y" in fields else self.style.align_y
            child.offset = Alignment(align_x, align_y).resolve(child.size, size)
        return size


def _face_of(
    font: float | TypeStyle,
    weight: int,
    tracking: float,
    line_height: float | None,
) -> tuple[float, int, float, float | None]:
    """``(size, weight, tracking, line_height)`` from a raw size or a role.

    A role is passed as **one object** on purpose. Four loose numbers that must
    match between a widget's measure and its paint are four chances to
    disagree, and a weight mismatch is exactly the bug that got in when the
    scale's weights were applied. A role cannot half-arrive.
    """
    if isinstance(font, TypeStyle):
        return (font.size, font.weight, font.tracking, font.line_height)
    return (float(font), weight, tracking, line_height)


def measure_text(
    text: str,
    font: float | TypeStyle,
    *,
    engine: TextEngine | None = None,
    max_width: float | None = None,
    weight: int = 400,
    tracking: float = 0.0,
    line_height: float | None = None,
) -> Size:
    """Shaped metrics for *text*. Memoised by the engine.

    `font` is either a raw size in logical px or a `TypeStyle` role, which
    carries its own weight, tracking and line height and overrides the keyword
    arguments.

    Weight selects a real face, tracking adds width per cluster and line height
    sets the box's height, so metrics differ on all three -- which is why layout
    and paint must pass the same values or they will disagree about how large a
    label is.
    """
    size, face_weight, track, leading = _face_of(font, weight, tracking, line_height)
    return (engine or default_text_engine()).measure(
        text,
        px=size,
        max_width=max_width,
        request=FontRequest(weight=face_weight),
        tracking=track,
        line_height=leading,
    )


def paint_text(
    ctx: PaintContext,
    x: float,
    y: float,
    text: str,
    font: float | TypeStyle,
    token: int,
    *,
    max_width: float | None = None,
    alignment: str = TextAlignment.START,
    weight: int = 400,
    tracking: float = 0.0,
    line_height: float | None = None,
    spans: Sequence[tuple[int, int, int | tuple[float, float, float, float]]] | None = None,
) -> int:
    """Emit shaped glyphs at logical position ``(x, y)``.

    ``x``/``y`` are the top-left of the text block; the baseline offset comes
    from the font's own ascent, so lines sit correctly whatever face is used.
    ``font`` takes a raw size or a `TypeStyle` role, as `measure_text` does.
    """
    size, face_weight, track, leading = _face_of(font, weight, tracking, line_height)
    paragraph = ctx.text.layout(
        text,
        px=size,
        max_width=max_width,
        alignment=alignment,
        request=FontRequest(weight=face_weight),
        tracking=track,
        line_height=leading,
    )
    return ctx.text.emit(
        ctx.display_list,
        paragraph,
        x=x,
        y=y,
        pixel_ratio=ctx.pixel_ratio,
        token=token,
        spans=spans,
        clip=ctx.clip,
        clip_radii=ctx.clip_radii,
    )


class ButtonElement(ContainerElement):
    """M3 Common Button: 40dp high, full radius, five variants.

    M3 describes these as one component in five configurations, so they are one
    widget with a `variant`, not five widget kinds. Container and content
    tokens come from the variant unless the view sets them explicitly.

    **Shape morph, sourced from `COMPONENT_BUTTONS.md`'s own "Corner sizes"
    table** (a different file than `ButtonGroup`'s own citations) -- pressed
    always morphs to a size-appropriate corner ("Both round and square
    buttons should have the same pressed shape"), and a toggle button
    (`checked`, the same `value:`-bound convention `Chip`'s filter variant
    and `Accordion` already use -- see `checked` on `ElementMixin`) rests at
    a size-appropriate corner when selected instead of full round. This
    applies to every `Button`, grouped or not -- the source page describes
    it as ordinary Button behaviour, not something `ButtonGroup` adds. An
    un-`checked`, unpressed `Button` (the overwhelming majority in this
    codebase -- anything with no `value:` binding at all) is completely
    unaffected.

    **The real XS-XL size ladder, opt-in via `style.size`.** This widget
    shipped with exactly one size, whose own dimensions (40dp height, 24dp
    horizontal padding) turn out to be neither M3 Expressive's real "Small"
    (40dp height, but 16dp padding) nor its "Medium" (56dp height, 24dp
    padding) -- a pre-Expressive baseline figure that predates the 5-size
    ladder entirely. Rather than silently reinterpreting every existing
    Button in the codebase as one size or the other, that shape stays
    exactly what it was -- `style.size`'s bare default -- and the five real
    Expressive sizes are additive: `size:` only changes anything when a view
    file actually sets it, the same `model_fields_set` override-detection
    `SliderElement._track_radius` and `DockSplitElement.horizontal` already
    use for an identical "explicit beats default" question. `COMPONENT_
    BUTTONS.md`'s own "Padding and size measurements" section carries no
    scraped table (an annotated diagram, not text) -- confirmed live against
    the actual image at `m3.material.io` rather than guessed, and
    cross-checked against `COMPONENT_BUTTON_GROUPS.md`'s own scraped token
    residue for the `extra_small` row (32dp height, matching exactly):

    | Size | Height | Padding | Checked corner | Pressed corner |
    |------|--------|---------|-----------------|------------------|
    | extra_small | 32dp | 12dp | 12dp | 8dp |
    | small | 40dp | 16dp | 12dp | 8dp |
    | medium | 56dp | 24dp | 16dp | 12dp |
    | large | 96dp | 48dp | 28dp | 16dp |
    | extra_large | 136dp | 64dp | 28dp | 16dp |

    The checked/pressed corner columns are the one part with an independent,
    already text-scraped source (`COMPONENT_BUTTONS.md`'s "Corner sizes"
    table) -- confirmed to agree with the diagram at every row. `MIN_WIDTH`
    and `LABEL_ROLE` are NOT scaled by size -- the diagram gives no min-width
    figure at any size, and nothing sources a per-size type-scale role
    either, so both stay their one existing value regardless of `size:`,
    matching `Slider`'s own precedent for a quantity no size-specific figure
    exists for.
    """

    #: "Container Height: 40dp", "Minimum Width: 64dp", "Padding: Horizontal
    #: 24dp ... Vertical 10dp" -- quoted from the same anatomy table. These
    #: were declared and never used: a Button has no child element, so it
    #: inherited a Padding layout that measured its (absent) child and returned
    #: nothing. A button written without an explicit size laid out 0x0 and drew
    #: nothing at all. Every example carried a size or a stylesheet class,
    #: which is why no golden ever caught it. Also this class's own LEGACY
    #: size-ladder row (`_geometry()` below) -- `style.size`'s bare default,
    #: unchanged by the ladder's existence.
    HEIGHT: Final = 40.0
    MIN_WIDTH: Final = 64.0
    PAD_X: Final = 24.0
    CURSOR = "pointer"

    #: "Typography: md.sys.typescale.label-large (14sp / 20dp line height,
    #: medium weight)" -- quoted, and the reason a button label is Medium
    #: rather than Regular. The whole role travels as one object so its size,
    #: weight and tracking cannot arrive at measure and paint separately.
    #: Not scaled by `style.size` -- no source gives a per-size type-scale
    #: role, so every size shares this one.
    LABEL_ROLE: Final = TYPE_SCALE["label-large"]

    #: Set by a `ButtonGroup` parent (`buttongroup.py`) to merge this
    #: button's shape into the group's connected pill -- `None` (the
    #: default, for a button with no such parent) leaves `effective_radii`
    #: reading `style.corner_radius` exactly as before. Not a spec field:
    #: it is computed from the button's position among its siblings, which
    #: a frozen `StyleSpec` cannot express.
    _group_radii: tuple[float, float, float, float] | None = None

    #: `COMPONENT_BUTTONS.md`'s own "Corner sizes" table, this class's LEGACY
    #: row (`style.size` unset) -- happens to equal the real ladder's own
    #: `"medium"` row exactly, unlike `HEIGHT`/`PAD_X` above. Round
    #: (unselected, unpressed) stays `size.height / 2` at every size,
    #: already correct below; `CHECKED_RADIUS` is the toggle-selected
    #: resting shape; `PRESSED_RADIUS` applies to every press regardless of
    #: selection ("Both round and square buttons should have the same
    #: pressed shape").
    CHECKED_RADIUS: Final = 16.0
    PRESSED_RADIUS: Final = 12.0

    #: `style.size` -> (height, pad_x, checked_radius, pressed_radius). See
    #: this class's own docstring for the sourced table and why the LEGACY
    #: row above -- not any one of these five -- is `style.size`'s bare
    #: default.
    SIZES: Final = {
        "extra_small": (32.0, 12.0, 12.0, 8.0),
        "small": (40.0, 16.0, 12.0, 8.0),
        "medium": (56.0, 24.0, 16.0, 12.0),
        "large": (96.0, 48.0, 28.0, 16.0),
        "extra_large": (136.0, 64.0, 28.0, 16.0),
    }

    def _geometry(self) -> tuple[float, float, float, float]:
        """(height, pad_x, checked_radius, pressed_radius) for `style.size`.

        Consults the ladder only when a view file actually wrote `size:` --
        `model_fields_set` is the same "explicit beats bare default" check
        `SliderElement._track_radius`/`DockSplitElement.horizontal` already
        use, needed here because `style.size`'s own bare default
        (`"extra_small"`, correct for `Slider`, the field's first owner) is
        NOT this class's own legacy shape.
        """
        legacy = (self.HEIGHT, self.PAD_X, self.CHECKED_RADIUS, self.PRESSED_RADIUS)
        if "size" not in self.style.model_fields_set:
            return legacy
        return self.SIZES.get(self.style.size, legacy)

    #: Set by a `ButtonGroup` parent, `standard` variant only -- mirrors
    #: `_group_radii`'s own pattern above. `False` (the default: no such
    #: parent, or a `connected` one) leaves this button's width unaffected
    #: by selection/press -- connected groups never grow width,
    #: `COMPONENT_BUTTON_GROUPS.md`'s own "don't add any interaction
    #: between buttons... only affect the shape."
    _group_standard: bool = False

    #: Not sourced -- `COMPONENT_BUTTON_GROUPS.md` never gives a number for
    #: how much a standard group's selected/pressed button grows, only
    #: that it does ("changes the width... of itself and adjacent
    #: buttons"). Extra horizontal padding per side while selected or
    #: pressed inside a standard group.
    GROUP_SELECT_PAD_EXTRA: Final = 8.0

    def _select_progress(self) -> float:
        """0..1 toward the standard-group selected/pressed width growth.

        Reveals extra padding the same way `Chip._check_progress()` reveals
        its checkmark (`material.py`) -- `invalidates="layout"` so the
        whole `ButtonGroup` row reflows, which is what visibly shifts later
        siblings along it. No new cross-element coupling: an ordinary Flex
        row already reflows whenever any child's own size changes.
        """
        target = 1.0 if self._group_standard and (self.checked or self.state.pressed) else 0.0
        return self.animated(
            "group_select",
            target,
            duration=SELECTION_MOTION,
            curve=SELECTION_CURVE,
            invalidates="layout",
        )

    def perform_layout(self, constraints: Constraints) -> Size:
        """Size to the label, floored at M3's minimum.

        A Button paints its label rather than holding it as a child, so there
        is nothing for the inherited container layout to measure. It has to
        measure the text itself -- with the same role its paint pass uses, or
        the box would be sized for one rendering and drawn in another.
        """
        height, pad_x, _checked_radius, _pressed_radius = self._geometry()
        outer = self.sized(constraints, self.style)
        label = (
            measure_text(self._text, self.LABEL_ROLE, engine=self.text_engine)
            if self._text.strip()
            else Size(0.0, 0.0)
        )
        pad = pad_x + self.GROUP_SELECT_PAD_EXTRA * self._select_progress()
        return outer.constrain(Size(max(self.MIN_WIDTH, label.width + 2 * pad), height))

    #: Only the `elevated` variant rests above the surface; M3 puts filled,
    #: tonal and outlined buttons at level 0.
    @property
    def resting_elevation(self) -> int:
        return 1 if self.style.variant == "elevated" else 0

    #: variant -> (container token or None, content token, outlined, elevated)
    VARIANTS: Final = {
        "filled": ("primary", "on_primary", False, False),
        "filled_tonal": ("secondary_container", "on_secondary_container", False, False),
        "outlined": (None, "primary", True, False),
        "elevated": ("surface_container_low", "primary", False, True),
        "text": (None, "primary", False, False),
    }

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        # Pressed always wins -- "both round and square buttons should
        # have the same pressed shape," overriding whatever the resting
        # shape was, connected-group position-square included. Checked
        # (the toggle-selected resting shape) comes next, also ahead of a
        # connected group's own position-based override -- a connected
        # group's own button still morphs on selection independent of its
        # neighbours (`COMPONENT_BUTTON_GROUPS.md`: "only affect the shape
        # of the button being selected").
        _height, _pad_x, checked_radius, pressed_radius = self._geometry()
        if self.state.pressed:
            return (pressed_radius,) * 4
        if self.checked:
            return (checked_radius,) * 4
        if self._group_radii is not None:
            return self._group_radii
        radii = self.style.corner_radius
        return radii if any(radii) else (self.size.height / 2,) * 4

    def _variant(self) -> tuple[str | None, str, bool, bool]:
        return self.VARIANTS.get(self.style.variant, self.VARIANTS["filled"])

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        container, content, outlined, elevated = self._variant()
        size = self.size
        dpr = ctx.pixel_ratio
        radii = self.effective_radii
        token = content_token(ctx, style, content)

        if elevated:
            # "Button (elevated)" is a level-1 resting component. The shadow
            # comes from the level, not from a number chosen here.
            elevation_shadow(
                ctx,
                absolute.x,
                absolute.y,
                size.width,
                size.height,
                level=self.elevation,
                radii=radii,
            )

        fill = style.background or container
        if fill is not None:
            ctx.display_list.add_box(
                absolute.x * dpr,
                absolute.y * dpr,
                size.width * dpr,
                size.height * dpr,
                token=ctx.palette.index(fill),
                color=(1.0, 1.0, 1.0, style.opacity),
                radii=tuple(r * dpr for r in radii),  # type: ignore[arg-type]
                border_width=1.0 * dpr if outlined else 0.0,
                border_token=ctx.palette.index("outline") if outlined else NO_TOKEN,
                border_color=(1.0, 1.0, 1.0, 1.0),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )
        elif outlined:
            ctx.display_list.add_box(
                absolute.x * dpr,
                absolute.y * dpr,
                size.width * dpr,
                size.height * dpr,
                token=ctx.palette.index("outline"),
                color=(1.0, 1.0, 1.0, 0.0),
                radii=tuple(r * dpr for r in radii),  # type: ignore[arg-type]
                border_width=1.0 * dpr,
                border_token=ctx.palette.index("outline"),
                border_color=(1.0, 1.0, 1.0, 1.0),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )

        # MD3 state layer: over the container, under the label. Shared with
        # every other component rather than reimplemented here -- Button had
        # its own copy, which is why it alone did not cross-fade when state
        # layers were animated.
        _emit_state_layer(ctx, self, absolute, token, radii)

        if self._text.strip():
            label = measure_text(self._text, self.LABEL_ROLE, engine=self.text_engine)
            paint_text(
                ctx,
                absolute.x + (size.width - label.width) / 2,
                absolute.y + (size.height - label.height) / 2,
                self._text,
                self.LABEL_ROLE,
                token,
            )


class LinkElement(_StyledMixin, Padding):
    """M3's hyperlinked text -- underlined, `primary` or `tertiary`.

    Not a component with its own page: the source is the typography
    guidance's "Applying type" ("For hyperlinked text appearing on top of a
    surface color, use primary. However, tertiary can be used to make links
    less prominent" and, separately, "Hyperlinked text must also be
    underlined") plus the Buttons page's explicit contrast with a text
    button -- "Don't underline the text button. Use hyperlinked body text
    instead to emphasize links." That contrast is the whole anatomy: a Link
    carries **no container and no state layer**, which is what actually
    tells it apart from a text button at rest, not just the underline.

    Sized with `style.font_size` directly, not a fixed type-scale role the
    way `Button`'s label is -- a link is meant to sit inline with whatever
    body text surrounds it, not own a typography of its own. No hover/press
    feedback is modelled: this is typography guidance, not a component with
    a states table to translate.
    """

    #: 1dp, matching the framework's other hairline (`Divider`). Not
    #: M3-sourced -- no measurement table exists for this "component".
    UNDERLINE_THICKNESS: Final = 1.0
    #: How far below the baseline the underline sits, as a fraction of the
    #: font's descent. Also not sourced; a conventional typographic offset.
    UNDERLINE_DEPTH: Final = 0.3
    CURSOR = "pointer"

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def _color_role(self) -> str:
        return "tertiary" if self.style.variant == "tertiary" else "primary"

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        style = self.style
        label = (
            measure_text(
                self._text, style.font_size, engine=self.text_engine, weight=style.font_weight
            )
            if self._text.strip()
            else Size(0.0, 0.0)
        )
        return outer.constrain(label)

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        if not self._text.strip():
            return
        style = self.style
        token = content_token(ctx, style, self._color_role())
        label = measure_text(
            self._text, style.font_size, engine=self.text_engine, weight=style.font_weight
        )
        paint_text(
            ctx,
            absolute.x,
            absolute.y,
            self._text,
            style.font_size,
            token,
            weight=style.font_weight,
        )

        metrics = self.text_engine.db.face_for(FontRequest(weight=style.font_weight)).metrics(
            style.font_size
        )
        dpr = ctx.pixel_ratio
        underline_y = absolute.y + metrics.baseline + metrics.descent * self.UNDERLINE_DEPTH
        ctx.display_list.add_box(
            absolute.x * dpr,
            underline_y * dpr,
            label.width * dpr,
            self.UNDERLINE_THICKNESS * dpr,
            token=token,
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )


class TextElement(_StyledMixin, Padding):
    """A run of text, shaped and wrapped to the available width.

    With `selectable: true` it can be selected with the mouse: click to place a
    caret, drag to extend, double-click for a word, Ctrl+A for all of it, and
    Ctrl+C to copy. Selection is by **grapheme cluster**, so an edge never
    lands inside a flag emoji or between a base character and its accent.
    """

    #: Highlight opacity. Not sourced -- M3 has no selection colour, and the
    #: state-layer opacities are for interaction, not for a persistent mark.
    SELECTION_ALPHA: Final = 0.30

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, spec.style.padding)
        self.init_element(spec)

    def configure(self) -> None:
        self._padding = self.style.padding

    # -------------------------------------------------------- selection

    @property
    def selectable(self) -> bool:
        return bool(self.style.selectable)

    @property
    def selection(self) -> tuple[int, int]:
        """The selected range, ordered. Empty when nothing is selected."""
        anchor = int(self.state.data.get("sel_anchor", 0))
        focus = int(self.state.data.get("sel_focus", 0))
        return (min(anchor, focus), max(anchor, focus))

    @property
    def selected_text(self) -> str:
        start, end = self.selection
        return self._text[start:end]

    def select(self, anchor: int, focus: int) -> None:
        self.state.data["sel_anchor"] = anchor
        self.state.data["sel_focus"] = focus
        self.mark_needs_paint()

    def select_all(self) -> None:
        self.select(0, len(self._text))

    def clear_selection(self) -> None:
        self.select(0, 0)

    def _paragraph(self) -> Any:
        """The laid-out paragraph, in the shape the paint pass draws.

        Wrapped to the box actually laid out rather than re-deriving it from
        constraints: hit testing has to agree with what is on screen, and a
        second derivation is a second chance to disagree.
        """
        width = self.size.width - self._padding.horizontal
        return self.text_engine.layout(
            self._text,
            px=self.style.font_size,
            max_width=width if width > 0 else None,
            request=FontRequest(weight=self.style.font_weight),
            tracking=self.style.letter_spacing,
            line_height=self.style.line_height,
        )

    def _offset_at(self, x: float, y: float) -> int:
        from ..text.selection import index_at

        rect = self.absolute_rect()
        local_x = x - rect.x - self._padding.left
        local_y = y - rect.y - self._padding.top
        return index_at(self._paragraph(), local_x, local_y)

    def cursor_at(self, x: float, y: float) -> str | None:
        if self.selectable and self.style.cursor is None:
            return "text"
        return super().cursor_at(x, y)

    # ----------------------------------------------------------- events

    def on_pointer_down(self, event: Any) -> None:
        if not self.selectable:
            return
        offset = self._offset_at(event.x, event.y)
        if self.state.data.pop("sel_double", False):
            from ..text.selection import word_at

            self.select(*word_at(self._text, offset))
        else:
            self.select(offset, offset)
        event.capture()

    def on_pointer_move(self, event: Any) -> None:
        if not self.selectable or "sel_anchor" not in self.state.data:
            return
        if event.button or self.state.pressed:
            self.select(int(self.state.data["sel_anchor"]), self._offset_at(event.x, event.y))

    def on_click(self, event: Any) -> None:
        """A second click in quick succession selects a word.

        Tracked by count rather than by clock: pySilver has no wall-clock in
        the event path, and a double-click that depends on real time would make
        every test that exercises it flaky.
        """
        if not self.selectable:
            return
        self.state.data["sel_double"] = not self.state.data.get("sel_double", False)

    def on_key_down(self, event: Any) -> None:
        if not self.selectable:
            return
        from ..runtime.events import is_accelerator, modifiers_of

        key = str(getattr(event, "key", "")).lower()
        if not is_accelerator(modifiers_of(event)):
            return
        if key == "a":
            self.select_all()
            event.stop_propagation()
        elif key == "c" and self.selected_text:
            from ..runtime.clipboard import clipboard

            clipboard.set_text(self.selected_text)
            event.stop_propagation()

    def _wrap_width(self, constraints: Constraints) -> float | None:
        """Width available for text, or None when the box is unbounded."""
        width = _resolve_axis(self.style.width, constraints.max_width)
        if width is None:
            if not constraints.has_bounded_width:
                return None
            width = constraints.max_width
        return max(0.0, width - self._padding.horizontal)

    def measure(self, constraints: Constraints | None = None) -> Size:
        wrap = self._wrap_width(constraints) if constraints is not None else None
        return measure_text(
            self._text,
            self.style.font_size,
            engine=self.text_engine,
            max_width=wrap,
            weight=self.style.font_weight,
            tracking=self.style.letter_spacing,
            line_height=self.style.line_height,
        )

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        return outer.constrain(self.measure(constraints).inflate(self._padding))

    def _paint_selection(self, ctx: PaintContext, absolute: Any) -> None:
        """Highlight behind the glyphs.

        Drawn here rather than in `paint_foreground` on purpose: a highlight
        over the text would tint the letters it is meant to be behind.
        """
        from ..text.selection import rects_for

        start, end = self.selection
        if start == end:
            return
        origin_x = absolute.x + self._padding.left
        origin_y = absolute.y + self._padding.top
        token = ctx.palette.index("primary")
        for rect in rects_for(self._paragraph(), start, end):
            _box(
                ctx,
                origin_x + rect.x,
                origin_y + rect.y,
                rect.width,
                rect.height,
                token=token,
                radius=0.0,
                alpha=self.SELECTION_ALPHA,
            )

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        super().paint_self(ctx, absolute)
        if not self._text.strip():
            return
        if self.selectable:
            self._paint_selection(ctx, absolute)
        paint_text(
            ctx,
            absolute.x + self._padding.left,
            absolute.y + self._padding.top,
            self._text,
            self.style.font_size,
            content_token(ctx, self.style, "on_surface"),
            max_width=max(0.0, self.size.width - self._padding.horizontal) or None,
            weight=self.style.font_weight,
            tracking=self.style.letter_spacing,
            line_height=self.style.line_height,
        )


class IconElement(_StyledMixin, Padding):
    """A Material Symbols icon.

    The icon name comes from `icon:`, so binding expressions work on it -- an
    icon can switch with state exactly the way a label can:
    `icon: "{{ 'star' if saved.get() else 'star_border' }}"`.
    """

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, spec.style.padding)
        self.init_element(spec)

    def configure(self) -> None:
        self._padding = self.style.padding

    def perform_layout(self, constraints: Constraints) -> Size:
        style = self.style
        outer = self.sized(constraints, style)
        natural = Size(style.icon_size, style.icon_size).inflate(self._padding)
        return outer.constrain(natural)

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        super().paint_self(ctx, absolute)
        name = self._icon.strip()
        if not name:
            return
        style = self.style
        size = style.icon_size
        # Centre the glyph box within whatever the element was given, so an
        # icon in a fixed-size button sits correctly rather than at its corner.
        ctx.text.emit_icon(
            ctx.display_list,
            name,
            x=absolute.x + (self.size.width - size) / 2,
            y=absolute.y + (self.size.height - size) / 2,
            size=size,
            fill=style.icon_fill,
            weight=style.icon_weight,
            pixel_ratio=ctx.pixel_ratio,
            token=content_token(ctx, style, "on_surface"),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )


class SpacerElement(_StyledMixin, Padding):
    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        return outer.constrain(outer.smallest)


# Placed here, after every name material.py needs from this module
# (_StyledMixin, content_token, measure_text, paint_text) is already defined,
# rather than at the top of the file -- material.py imports those at its own
# module level, so this import at the TOP of base.py, before they exist,
# would find base.py only half-initialized and fail. This is the one place
# ButtonElement/TextElement's own shared paint helpers come from; previously
# four separate local imports, one per call site, working around the same
# constraint less legibly.
from .material import (  # noqa: E402
    SELECTION_CURVE,
    SELECTION_MOTION,
    _box,
    _emit_state_layer,
    elevation_shadow,
)
