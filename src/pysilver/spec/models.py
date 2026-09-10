"""The Spec tree: validated, immutable, inert data parsed from a view file.

This is the framework's single validation boundary (ARCHITECTURE.md 1.3). A typo
in a YAML key or an unknown MD3 token fails HERE, at load, with a path -- not
later as a cryptic hardware error or a silently ignored style.

Spec nodes are frozen and hashable, so reconciliation can skip untouched
subtrees by identity. They hold no runtime state whatsoever; that lives on the
Element tree (ARCHITECTURE.md 4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from ..layout import EdgeInsets
from ..theme import is_token
from .expressions import Template

__all__ = [
    "BorderSpec",
    "ShadowSpec",
    "SizeSpec",
    "StyleSpec",
    "ViewSpec",
    "WidgetKind",
    "WidgetSpec",
]

SCHEMA_VERSION = 1

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


class WidgetKind(StrEnum):
    """Enum, not a bare string -- an unknown widget fails at load."""

    CONTAINER = "Container"
    HORIZONTAL = "Horizontal"
    VERTICAL = "Vertical"
    STACK = "Stack"
    TEXT = "Text"
    BUTTON = "Button"
    SPACER = "Spacer"
    ICON = "Icon"
    # Material Design 3 components
    CARD = "Card"
    DIVIDER = "Divider"
    CHECKBOX = "Checkbox"
    RADIO = "Radio"
    SWITCH = "Switch"
    CHIP = "Chip"
    ICON_BUTTON = "IconButton"
    FAB = "Fab"
    BADGE = "Badge"
    NAVIGATION_RAIL = "NavigationRail"
    NAV_ITEM = "NavItem"
    TOP_APP_BAR = "TopAppBar"
    TABS = "Tabs"
    TAB = "Tab"
    SEGMENTED_BUTTON = "SegmentedButton"
    SEGMENT = "Segment"
    LIST_ITEM = "ListItem"
    LINEAR_PROGRESS = "LinearProgress"
    CIRCULAR_PROGRESS = "CircularProgress"
    CAROUSEL = "Carousel"
    CAROUSEL_ITEM = "CarouselItem"
    # Overlay components (see runtime/overlay.py and widgets/overlays.py)
    DIALOG = "Dialog"
    MENU = "Menu"
    MENU_ITEM = "MenuItem"
    TOOLTIP = "Tooltip"
    SNACKBAR = "Snackbar"
    BOTTOM_SHEET = "BottomSheet"
    SIDE_SHEET = "SideSheet"
    SCROLL_VIEW = "ScrollView"
    TEXT_FIELD = "TextField"
    SHAPE = "Shape"
    POPOVER = "Popover"
    ACCORDION = "Accordion"
    TREE_VIEW = "TreeView"
    TREE_ITEM = "TreeItem"
    LINK = "Link"
    SPIN_BOX = "SpinBox"
    SLIDER = "Slider"
    PAGINATION = "Pagination"
    STATUS_BAR = "StatusBar"
    DOCK_SPLIT = "DockSplit"
    DOCK_GROUP = "DockGroup"
    DOCK_PANEL = "DockPanel"
    CANVAS = "Canvas"
    IMAGE = "Image"
    VIDEO = "Video"
    NODE_GRAPH = "NodeGraph"
    NODE = "Node"
    CODE_EDITOR = "CodeEditor"
    TERMINAL = "Terminal"
    PAGE_HOST = "PageHost"
    SEARCH_BAR = "SearchBar"
    SPLIT_BUTTON = "SplitButton"
    DATE_PICKER = "DatePicker"
    TIME_PICKER = "TimePicker"
    BUTTON_GROUP = "ButtonGroup"


@dataclass(frozen=True, slots=True)
class SizeSpec:
    """``120`` | ``auto`` | ``expand`` | ``50%`` | ``flex:2``."""

    kind: str
    value: float = 0.0

    @classmethod
    def parse(cls, raw: Any) -> SizeSpec:
        if isinstance(raw, SizeSpec):
            return raw
        if isinstance(raw, bool):
            raise ValueError(f"invalid size {raw!r}")
        if isinstance(raw, int | float):
            if raw < 0:
                raise ValueError(f"size must be non-negative, got {raw}")
            return cls("fixed", float(raw))
        if isinstance(raw, str):
            text = raw.strip().lower()
            if text == "auto":
                return cls("auto")
            if text == "expand":
                return cls("expand")
            if text.endswith("%"):
                pct = float(text[:-1]) / 100.0
                if pct < 0:
                    raise ValueError(f"size must be non-negative, got {raw!r}")
                return cls("percent", pct)
            if text == "flex" or text.startswith("flex:"):
                _, _, weight = text.partition(":")
                return cls("flex", float(weight) if weight else 1.0)
        raise ValueError(
            f"invalid size {raw!r}; expected a number, 'auto', 'expand', 'N%' or 'flex:N'"
        )


AUTO = SizeSpec("auto")


def _parse_edges(raw: Any) -> EdgeInsets:
    """``8`` | ``[h, v]`` | ``[l, t, r, b]`` | mapping."""
    if isinstance(raw, EdgeInsets):
        return raw
    if isinstance(raw, int | float):
        return EdgeInsets.all(float(raw))
    if isinstance(raw, dict):
        unknown = set(raw) - {"left", "top", "right", "bottom"}
        if unknown:
            raise ValueError(
                f"invalid edge insets key(s) {sorted(unknown)!r}; expected left/top/right/bottom"
            )
        return EdgeInsets(
            float(raw.get("left", 0)),
            float(raw.get("top", 0)),
            float(raw.get("right", 0)),
            float(raw.get("bottom", 0)),
        )
    if isinstance(raw, list | tuple):
        vals = [float(v) for v in raw]
        if len(vals) == 2:
            return EdgeInsets.symmetric(horizontal=vals[0], vertical=vals[1])
        if len(vals) == 4:
            return EdgeInsets(*vals)
    raise ValueError(f"invalid edge insets {raw!r}; expected number, [h,v], or [l,t,r,b]")


def _parse_corners(raw: Any) -> tuple[float, float, float, float]:
    """``16`` | ``[tl, tr, br, bl]``."""
    if isinstance(raw, int | float):
        return (float(raw),) * 4
    if isinstance(raw, list | tuple) and len(raw) == 4:
        return tuple(float(v) for v in raw)  # type: ignore[return-value]
    raise ValueError(f"invalid corner radius {raw!r}; expected a number or [tl,tr,br,bl]")


def _validate_token(raw: Any) -> str:
    """Reject unknown MD3 tokens at load, where the error is actionable."""
    if not isinstance(raw, str):
        raise ValueError(f"expected an MD3 token name, got {raw!r}")
    if raw.startswith("#"):
        return raw  # literal hex, validated by parse_hex downstream
    if not is_token(raw):
        raise ValueError(
            f"unknown MD3 token {raw!r}; use a token name (e.g. 'surface_variant') "
            f"or a '#RRGGBB' literal"
        )
    return raw


def _parse_classes(raw: Any) -> tuple[str, ...]:
    """``"a b"`` or ``[a, b]`` -> ``("a", "b")``."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = raw.split()
    elif isinstance(raw, list | tuple):
        parts = [str(v) for v in raw]
    else:
        raise ValueError(f"invalid class list {raw!r}; expected a string or a list")
    for part in parts:
        if not _IDENT_RE.fullmatch(part):
            raise ValueError(f"invalid class name {part!r}; use letters, digits, _ and -")
    return tuple(parts)


Size = Annotated[SizeSpec, BeforeValidator(SizeSpec.parse)]
Edges = Annotated[EdgeInsets, BeforeValidator(_parse_edges)]
Corners = Annotated[tuple[float, float, float, float], BeforeValidator(_parse_corners)]
TokenRef = Annotated[str, BeforeValidator(_validate_token)]

#: A dot separates include scopes: a fragment pulled in as `delete_confirm`
#: has its inner `heading` become `delete_confirm.heading`, so the same
#: fragment can be included twice without its names colliding.
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*)*$")]
Classes = Annotated[tuple[str, ...], BeforeValidator(_parse_classes)]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class BorderSpec(_Frozen):
    width: float = Field(default=1.0, ge=0)
    color: TokenRef = "outline"


class ShadowSpec(_Frozen):
    blur: float = Field(default=8.0, ge=0)
    offset_x: float = 0.0
    offset_y: float = 2.0
    color: TokenRef = "shadow"
    opacity: float = Field(default=0.35, ge=0, le=1)


#: Every variant name any component accepts. A widget validates that the one it
#: was given is meaningful for it; declaring them centrally catches typos at
#: load, where the error names the path.
Variant = Literal[
    # buttons and cards
    "filled",
    "filled_tonal",
    "outlined",
    "elevated",
    "text",
    # sizes (FAB, icon button); "standard" is shared with button groups
    "standard",
    "small",
    "medium",
    "large",
    "extended",
    # button groups
    "connected",
    # chips
    "assist",
    "filter",
    "input",
    "suggestion",
    # badges
    "dot",
    "numbered",
    # dividers
    "full_bleed",
    "inset",
    # app bars
    "center_aligned",
    # tabs (primary anchors a rounded indicator; secondary a flat stroke)
    "primary",
    "secondary",
    # carousel layouts
    "uncontained",
    "hero",
    "multi_browse",
    # list items
    "one_line",
    "two_line",
    "three_line",
    # links ("primary" is shared with tabs)
    "tertiary",
]


#: M3's type-scale roles: five sizes at three steps each, "from Display Large
#: to Label Small". The **vocabulary** is sourced; the figures behind it are
#: not -- see `TYPE_SCALE_NOTE` and `spec/typescale.py`.
TYPE_ROLES: Final = tuple(
    f"{group}-{step}"
    for group in ("display", "headline", "title", "body", "label")
    for step in ("large", "medium", "small")
)

TypeRole = Literal[
    "display-large",
    "display-medium",
    "display-small",
    "headline-large",
    "headline-medium",
    "headline-small",
    "title-large",
    "title-medium",
    "title-small",
    "body-large",
    "body-medium",
    "body-small",
    "label-large",
    "label-medium",
    "label-small",
]


class StyleSpec(_Frozen):
    """Visual and geometric properties. Note that `children` is NOT here --
    children are structure, and belong on the widget."""

    width: Size = AUTO
    height: Size = AUTO
    padding: Edges = EdgeInsets()
    margin: Edges = EdgeInsets()

    #: Extra area around the paint rect that still counts as a hit. Affects
    #: neither layout nor paint -- a control keeps its size and its drawing,
    #: and merely becomes easier to hit.
    hit_padding: Edges = EdgeInsets()
    #: Smallest hit rect this element accepts, in logical px, centred on the
    #: paint rect. This is how M3's "at least 48x48dp" target is written:
    #: `min_hit_size: 48` on an 18dp checkbox, rather than 15dp of padding
    #: worked out by hand and wrong the moment the box changes size.
    min_hit_size: float | None = Field(default=None, gt=0.0, le=1000.0)

    background: TokenRef | None = None
    #: None means "use this widget's own M3 default for its variant". An
    #: explicit token always wins.
    color: TokenRef | None = None
    corner_radius: Corners = (0.0, 0.0, 0.0, 0.0)
    border: BorderSpec | None = None
    shadow: ShadowSpec | None = None
    opacity: float = Field(default=1.0, ge=0, le=1)

    # flex / stack
    spacing: float = Field(default=0.0, ge=0)
    main_alignment: Literal[
        "start", "end", "center", "space_between", "space_around", "space_evenly"
    ] = "start"
    cross_alignment: Literal["start", "end", "center", "stretch"] = "start"
    align_x: float = Field(default=0.0, ge=0, le=1)
    align_y: float = Field(default=0.0, ge=0, le=1)

    # overlays (see runtime/overlay.py)
    #: Where an overlay sits. `anchor` positions it against another element.
    placement: Literal["center", "anchor", "pointer", "top", "bottom", "left", "right"] = "center"
    #: `name` of the element an anchored overlay attaches to.
    anchor: str | None = None
    #: A modal overlay blocks input to everything beneath it.
    modal: bool = False
    #: Draw M3's 32% scrim behind this overlay.
    scrim: bool = False
    #: Dismiss on a click outside, or on Escape.
    dismissable: bool = True
    #: Gap between an anchored overlay and its anchor, in logical px.
    offset: float = Field(default=4.0, ge=0)
    #: A `MenuItem` that opens a submenu. Purely the visual affordance (a
    #: trailing `chevron_right`, replacing `supporting_text`) -- the submenu
    #: itself is a separate `Menu` overlay entry anchored to this item by
    #: `name`, the same way any anchored overlay is declared.
    has_submenu: bool = False
    #: `SegmentedButton`'s single- vs multi-select mode (M3 names both).
    #: Off by default, preserving the one-`value:`-names-one-child model
    #: every `_SelectionContainer` already uses. On, `value:` is instead a
    #: comma-separated set of selected names, and more than one child can be
    #: marked selected at once. Meaningless on `Tabs`/`NavigationRail` -- M3
    #: does not describe a multi-select form of either -- though nothing
    #: stops a view from setting it there too.
    multi_select: bool = False
    #: `name` of the ScrollView a TopAppBar collapses with. Without it a
    #: medium or large bar simply stays expanded.
    collapses_with: str | None = None
    #: Which way a ScrollView scrolls. Horizontal/Vertical encode their axis
    #: in the widget kind, but a viewport's axis is independent of its content's.
    axis: Literal["vertical", "horizontal"] = "vertical"
    #: Draw a ScrollView's scrollbar when its content overflows.
    scrollbar: bool = True
    #: Draw a bottom sheet's drag handle. Off by default -- opt-in, the way a
    #: view chooses to show any other affordance, not because the gesture
    #: behind it is unwired (`BottomSheetElement.on_pointer_down/_move/_up`
    #: already drag-and-dismiss with or without the handle drawn).
    handle: bool = False
    #: A SpinBox's or Slider's bounds. For `SpinBox`, None on either end means
    #: unbounded in that direction, not "clamp to zero" -- a generic
    #: increment control has no reason to assume a lower bound of zero unless
    #: told one. `Slider` reads the same two fields but falls back to 0.0/1.0
    #: when unset instead of leaving that end unbounded, since a slider with
    #: no upper or lower bound has no track to draw a handle on.
    min: float | None = None
    max: float | None = None
    #: How much one click or arrow-key press changes a SpinBox's or Slider's
    #: value by.
    step: float = Field(default=1.0, gt=0)
    #: A Slider's handle shape. `"line"` is current M3 -- a narrow vertical
    #: bar that narrows further when pressed (`COMPONENT_SLIDERS.md`: "a
    #: vertical handle", explicitly replacing M2's circular one in the same
    #: revision). `"circle"` is an opt-in back to that M2 shape for an
    #: application that wants it; not a scraped M3 figure, since the current
    #: spec no longer documents the M2 handle's own dimensions. `"square"`
    #: and `"hexagon"` are pySilver's own, not M3 at all -- phil asked
    #: directly for a genuinely pluggable handle shape, "not just pySilver's
    #: shipped line/circle pair"; both reuse `Shape`'s own regular-polygon
    #: primitive (`DisplayList.add_polygon`, `sides=4`/`6`), so they cost no
    #: new engine work. A true star (alternating inner/outer points) is NOT
    #: one of the choices -- `add_polygon` only draws regular polygons and
    #: cannot express that shape at all; dropped from this pass rather than
    #: shipped as a misleading approximation, see `SliderElement`'s own
    #: module docstring for the real gap this leaves.
    handle_shape: Literal["line", "circle", "square", "hexagon"] = "line"
    #: An image as a Slider's handle instead of any shape above -- wins over
    #: `handle_shape` when set. Same resolution convention as `Image.path`
    #: (absolute as given, relative to the working directory otherwise), and
    #: the same raster-only reach: decoded through Pillow via the shared
    #: `ImageAtlas` `Image` already uses, so SVG is not supported (Pillow has
    #: no SVG decoder, and pySilver has no other one yet). `None` (default)
    #: means no image handle -- every existing slider is unaffected.
    handle_image: str | None = None
    #: Gap between a Slider's handle and each track segment, in logical px.
    #: Real M3 leaves the background showing on both sides of the handle
    #: rather than running the active colour flush against it -- confirmed
    #: visually, not a number the scraped spec text gives.
    cradle_gap: float = Field(default=6.0, ge=0)
    #: Corner radius on each of a Slider's track segments' handle-facing
    #: end. Visibly more square than `track_radius`, its outer end -- also
    #: not a scraped figure.
    cradle_radius: float = Field(default=2.0, ge=0)
    #: Corner radius on each of a Slider's track segments' outer end.
    #: `COMPONENT_SLIDERS.md`'s own XS-size measurement table: 8dp. The
    #: size-appropriate default for whichever `size:` is set (below) unless
    #: a view file sets this explicitly -- see `SliderElement._track_radius`.
    track_radius: float = Field(default=8.0, gt=0)
    #: A component's step on M3's named size scale, where one applies
    #: (currently only `Slider`; `pySilver ButtonGroup Design Backlog`
    #: expects to want the identical ladder once ButtonGroup's own sizes
    #: are built, so this is deliberately not Slider-specific in name or
    #: place). `COMPONENT_SLIDERS.md`'s own token naming convention
    #: ("md.comp.slider.xsmall") is the source for these spellings. Not
    #: folded into `Variant` above -- that alias is reused *by name* across
    #: many widgets' own distinct M3 vocabularies; a generic size scale is
    #: a different, orthogonal axis, not one more entry in that list.
    size: Literal["extra_small", "small", "medium", "large", "extra_large"] = "extra_small"
    #: A Pagination's total number of pages.
    count: int = Field(default=1, ge=1)
    #: Seconds after which an actionless Snackbar dismisses itself. `None`
    #: (default) never auto-dismisses -- opt-in, so no existing Snackbar's
    #: behaviour changes just from this field existing. `COMPONENT_SNACKBAR.md`:
    #: "Snackbars without actions can auto-dismiss after 4-10 seconds... common
    #: acceptable durations are 4-10 seconds" but "Snackbars with actions
    #: shouldn't auto-dismiss" -- `SnackbarElement` enforces that second half
    #: itself, ignoring this field outright whenever `supporting_text:` (its
    #: action) is set, rather than trusting every caller to remember the gate.
    auto_dismiss: float | None = Field(default=None, gt=0.0)

    # text
    font_size: float = Field(default=14.0, gt=0)
    #: Font weight. Roboto ships 400 and 500; the font database resolves to
    #: the nearest available within the family rather than synthesising one,
    #: so 700 renders as Medium rather than as smeared Regular.
    font_weight: int = Field(default=400, ge=1, le=1000)
    #: Letter spacing in logical px, added after every grapheme cluster. An
    #: absolute figure, the way M3 states tracking -- it does not scale with
    #: `font_size`, so a role's tracking stays correct only at that role's size.
    letter_spacing: float = Field(default=0.0, ge=-100.0, le=100.0)
    #: Fixed line height in logical px. None keeps the font's own, which is
    #: what most text wants; a type-scale role sets it. The extra space is
    #: split evenly above and below the glyphs, so raising it does not move
    #: centred text -- the box measures taller and the label stays put.
    line_height: float | None = Field(default=None, gt=0.0, le=1000.0)
    #: An M3 type-scale role, resolved to `font_size` at load against the
    #: view's `type_scale:`. Naming a role with no scale defined is an error,
    #: not a silent fallback -- pySilver ships no figures for these (see
    #: `docs/view-reference.md`), so a quiet default would be an invented
    #: number wearing a Material label.
    text_style: TypeRole | None = None

    #: Which M3 variant of the component to render.
    variant: Variant = "filled"
    #: Whether a `Text` widget's content can be selected with the mouse.
    #: Whether a `TextField` accepts more than one line.
    #:
    #: M3 names two forms and this covers both, because the difference between
    #: them is exactly whether the author fixed a height. "Multi-line text
    #: fields grow to accommodate multiple lines"; they "initially appear as
    #: single-line fields" and expand as text wraps -- that is `multiline: true`
    #: alone. "Text areas are fixed-height fields" that "scroll vertically when
    #: the cursor reaches the bottom" -- that is `multiline: true` with a
    #: `height:`. Both quoted from COMPONENT_TEXT_FIELDS.
    multiline: bool = False
    #: Off by default: a selectable label shows a text cursor and swallows
    #: drags, which is wrong for the labels most text in an interface is.
    selectable: bool = False
    #: Pointer shape over this element. `None` means "this widget's default".
    #: Names are the backend's own (CSS-style); an unknown one fails at load
    #: rather than raising from inside a frame.
    cursor: (
        Literal[
            "default",
            "text",
            "crosshair",
            "pointer",
            "ew-resize",
            "ns-resize",
            "nesw-resize",
            "nwse-resize",
            "not-allowed",
            "none",
        ]
        | None
    ) = None
    #: M3 elevation level, 0-5. `None` means "this component's resting level".
    #: A level is a *relationship*, not a shadow: it says where a surface sits
    #: relative to others. The dp height it maps to is what produces a shadow.
    elevation: int | None = Field(default=None, ge=0, le=5)
    #: Divider thickness and inset, in logical px.
    thickness: float = Field(default=1.0, gt=0)
    inset: float = Field(default=0.0, ge=0)

    # icons. `icon:` carries the icon name, so a binding expression can switch
    # icons at runtime -- e.g. icon: "{{ 'star' if saved.get() else 'star_border' }}"
    icon_size: float = Field(default=24.0, gt=0)
    #: 0 = outlined, 1 = filled. M3 uses this for selected/unselected states.
    icon_fill: float = Field(default=0.0, ge=0, le=1)
    icon_weight: float = Field(default=400.0, ge=100, le=700)
    #: `Tab`'s icon+label arrangement. `"stacked"` (default) is the one
    #: `COMPONENT_TABS.md`'s own diagram actually shows -- icon above the
    #: label, the pair centred as one block. `"leading"`/`"trailing"` are
    #: opt-in: the icon sits beside the label instead, on whichever side is
    #: named -- the table's own "padding between inline icon and text: 8dp"
    #: row, which names a real, sourced gap but no diagram example of the
    #: arrangement itself, so left/right was a judgment call, not scraped.
    icon_position: Literal["stacked", "leading", "trailing"] = "stacked"
    #: `Tab`'s `badge:` shape -- `"numbered"` (default) shows `badge:`'s own
    #: content in a pill; `"dot"` shows a bare notification dot and ignores
    #: `badge:`'s content entirely, the same `variant` name/values `Badge`
    #: itself already uses for the identical distinction.
    badge_variant: Literal["numbered", "dot"] = "numbered"

    # shapes. A regular polygon is an analytic SDF like the rounded box, not a
    # rasterised path, which is what makes these free to animate: `sides` and
    # `rotation` are instance floats, so changing them per frame costs nothing
    # and never touches the glyph atlas.
    #:
    #: Number of sides. **A float on purpose** -- the shader folds a sample
    #: point into one sector, so 5.5 is a real shape rather than a rounding
    #: error, and a square morphs continuously into a hexagon. Below 3 there is
    #: no polygon, and `corner_radius` at its maximum gives a circle.
    sides: float = Field(default=6.0, ge=3)
    #: Rotation in **degrees**, clockwise -- the direction arcs measure. Degrees
    #: rather than radians because a view file is authored by hand, and 30 is
    #: easier to reason about than 0.5236.
    rotation: float = 0.0
    #: When true, a `Shape` spins continuously on top of `rotation:`'s own
    #: static value -- the same `repeat=True` mechanism `CircularProgress`'s
    #: indeterminate spinner already uses, applied here because animating a
    #: Shape's rotation costs nothing (see `ShapeElement`'s own docstring).
    spin: bool = False
    #: When true, a `Shape`'s `sides` oscillates continuously between its own
    #: declared value and a wider polygon, passing through the smooth
    #: non-regular intermediates the shader's own comment describes -- a
    #: live morph, not a discrete jump between shapes.
    morph: bool = False

    # images
    #: How an `Image` fills a box whose aspect ratio differs from its own,
    #: CSS's `object-fit` vocabulary since M3 states none. `contain` (the
    #: default) never crops and never distorts -- the least surprising choice
    #: for a widget with no M3 anatomy to say otherwise. `cover` crops to
    #: fill; `fill` stretches to the box exactly, distorting if the ratios
    #: differ; `none` draws at the image's own natural size regardless of
    #: the box, centred within it.
    fit: Literal["contain", "cover", "fill", "none"] = "contain"

    # node graph
    #: A `Node`'s initial position in its `NodeGraph`'s own world space,
    #: logical px. Only the starting point -- dragging moves the node from
    #: here, tracked as runtime state (the same split `value:` and drag-
    #: driven state already have on every other draggable widget), and a
    #: reload does not reset a node an author has already moved.
    x: float = 0.0
    y: float = 0.0

    # code editor
    #: A Pygments lexer name or alias (`"python"`, `"yaml"`, ...) for
    #: `CodeEditor` syntax highlighting. Unset or unrecognised means no
    #: highlighting rather than an error -- Pygments is an optional
    #: capability, not a hard dependency (`pysilver[code]`).
    language: str | None = None
    #: `CodeEditor`'s line-number gutter, shown by default.
    line_numbers: bool = True
    #: How many spaces a `CodeEditor`'s Tab key inserts.
    tab_size: int = Field(default=4, ge=1)
    #: `CodeEditor` only: blocks every mutating key/text path (typing, Tab/
    #: Enter/Backspace/Delete/paste, undo/redo, and the delete half of
    #: Ctrl+X) while leaving caret motion, keyboard and mouse selection,
    #: Ctrl+A, and copy fully working -- `disabled` is the wrong tool for
    #: this, since `effective_disabled` also gates pointer selection.
    read_only: bool = False
    #: A font family to request by name (`FontRequest.family`), resolved
    #: through the same `FontDB` every widget already uses. `CodeEditor` and
    #: `Terminal` read this -- see either one's own docstring for why a
    #: monospace-hungry widget is what finally needed to ask for one.
    font_family: str | None = None

    # terminal
    #: The command line `Terminal` runs, split with `shlex.split` (so
    #: `"bash -l"` works). Unset resolves `$SHELL`, falling back to a plain
    #: POSIX shell if that is not set either.
    shell: str | None = None


class EdgeSpec(_Frozen):
    """A drawn connection between two `Node` ports in a `NodeGraph`.

    `source`/`target` rather than `from`/`to` -- `from` is a keyword, and this
    keeps the pair symmetric with `Identifier`'s existing dotted shape rather
    than inventing a separate `"node:port"` syntax: each side is
    `"node.port"`, the node's `name` and one of its `inputs`/`outputs` names.
    """

    source: Identifier
    target: Identifier


#: Every field a view file may drive with a `{{ }}` binding, paired with the
#: private attribute `ElementMixin` stores its rendered value under. This is
#: the single place a new bindable field's *mechanism* cost lives --
#: `WidgetSpec.templates()` and `ElementMixin.init_element`/`update_spec`/
#: `bind` all loop over it instead of each needing a hand-written line per
#: field. Declaring the field itself (below, on `WidgetSpec`) plus one entry
#: here is the entire cost of adding a new one.
TEMPLATED_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("text", "_text"),
    ("value", "_value"),
    ("supporting_text", "_supporting"),
    ("open", "_open"),
    ("disabled", "_disabled"),
    ("error", "_error"),
    ("collapsed", "_collapsed"),
    ("indeterminate", "_indeterminate"),
    ("path", "_path"),
    ("icon", "_icon"),
    ("label", "_label"),
    ("badge", "_badge"),
)


class WidgetSpec(_Frozen):
    #: Positional identity, assigned by the loader from the node's path. Never
    #: written by an author -- it exists so every node has *some* identity for
    #: reconciliation, and it changes when the node moves among its siblings.
    id: str = ""
    #: The view file this node was written in, relative to the view root.
    #: **Assigned by the loader.** Never author one. Includes are flattened
    #: into a single tree, and this is what survives that -- it is how a
    #: fragment can have its own ViewModel.
    view: str | None = None
    widget: WidgetKind
    #: The designer's handle: unique, optional, and stable across a reorder.
    #: Referenced by `find()`, `anchor:`, and a selection container's `value:`,
    #: and used as the reconciliation key when present.
    name: Identifier | None = None
    #: Categories, for the theme engine and stylesheet to select on. Repeatable
    #: by design -- unlike `name`, several nodes may share one. Accepts a list
    #: or a space-separated string, and normalises to a tuple.
    classes: Classes = ()
    style: StyleSpec = StyleSpec()
    text: str | None = None
    #: A bound value: selection for Checkbox/Radio/Switch/Chip, count for
    #: Badge, progress for indicators. Templated like `text`, so
    #: `value: "{{ checked.get() }}"` tracks a signal.
    value: str | None = None
    #: A ListItem's second line. Content, not style, and templated like `text`.
    supporting_text: str | None = None
    #: A Material Symbols glyph name. Templated like `text`, so
    #: `icon: "{{ 'star' if saved.get() else 'star_border' }}"` switches the
    #: icon with state. `Icon`, `IconButton`, `Fab`, `NavItem`, and
    #: `SearchBar`'s trailing icon read this -- `text:` used to double as the
    #: glyph name for these widgets, which is why `docs/view-reference.md`
    #: says "an icon name is never announced": `text:` is normally read aloud
    #: as a control's name, so it had to be excluded specifically for them.
    #: With the glyph in its own field, `text:` no longer needs that carve-out
    #: for any of them. Meaningless on a widget with no icon anatomy.
    icon: str | None = None
    #: A widget's own visible/accessible label, distinct from `text:`'s
    #: primary-content role -- `IconButton`'s and `Fab`'s accessible name,
    #: `Fab`'s extended-variant visible text, and `NavItem`'s destination
    #: label. Templated like `text`. Meaningless on a widget with no label
    #: anatomy of its own.
    label: str | None = None
    #: A `Tab`'s optional notification badge content -- a count ("3", "22")
    #: or, per `COMPONENT_TABS.md`'s own "limit badge content to four
    #: characters, including a '+'" guidance, something like "999+". Empty/
    #: unset means no badge at all, the same way `icon:`/`label:` read
    #: "meaningless on a widget with no such anatomy" for everything else.
    #: `style.badge_variant: dot` shows a bare notification dot instead and
    #: ignores this field's content entirely (mirrors `Badge`'s own
    #: `variant: dot` -- "small and large badges can both be used with
    #: tabs"). Templated like `text`.
    badge: str | None = None
    #: `PageHost`'s fallback child name, used whenever `value:` resolves to a
    #: name that doesn't match any declared child (unset, a typo, a Signal
    #: not yet initialised). **Not templated** -- unlike `value:`, this names
    #: a fixed page the author chose at design time, not something a signal
    #: should be able to move around. Meaningless outside `PageHost`.
    default: str | None = None
    #: Whether an overlay is showing. Templated: `open: "{{ show.get() }}"`.
    #: Meaningless outside the `overlays:` list.
    open: str | None = None

    #: Whether this control is inert. Templated like `value:` and `open:`, so
    #: it tracks a signal: `disabled: "{{ not form_valid.get() }}"`. It is
    #: **state, not style** -- it changes what a control *is*, not how a view
    #: chooses to paint it -- which is why it lives here and not on StyleSpec.
    #: Disabling a container disables everything inside it.
    disabled: str | None = None
    #: Whether this control is showing an error. Templated like `disabled:`,
    #: and state for the same reason: M3 gives an errored text field its own
    #: colours and a view should be able to drive it from validation rather
    #: than restyle it. Only `TextField` reads it.
    error: str | None = None
    #: Whether `NavigationRail` shows its narrow, icon-only anatomy (true)
    #: or its wide, labelled one (false, default) -- M3 Expressive's own
    #: "collapsed"/"expanded" states of one component, not two. Templated
    #: like `disabled:`, for the same reason it lives here rather than on
    #: `StyleSpec`: `style.width` is a load-time value (confirmed by
    #: trying it), not something a `{{ }}` binding can drive, and this is
    #: state a signal should flip. Meaningless on anything else.
    collapsed: str | None = None
    #: `Checkbox`'s third M3 state -- a dash instead of a checkmark, for a
    #: parent whose children are only partly checked. Templated like
    #: `disabled:`, since it is state a signal should drive (recomputed from
    #: the children's own checked count), not a fixed design-time choice.
    #: Takes precedence over `value:` for which glyph paints, but does not
    #: itself change `value:` -- checking an indeterminate box is still the
    #: view's own `on_click` to handle, same as any other checkbox click.
    #: Meaningless on anything else.
    indeterminate: str | None = None
    #: An `Image`'s file to decode and display. Templated like `value:`, so
    #: `path: "{{ avatar.get() }}"` swaps the picture when a signal changes.
    #: **Not** `source:` -- that key is already view-*composition* syntax
    #: (`spec/include.py` splices in a fragment wherever it sees one, before
    #: Pydantic ever runs), so a widget field reusing it would be silently
    #: swallowed as an include rather than reaching this model at all.
    #: Resolved exactly as a running process resolves any other path --
    #: absolute as given, relative to the working directory otherwise --
    #: **not** relative to the view file the way `source:` includes are; an
    #: application wanting that computes the path itself, e.g. from
    #: `Path(__file__).parent`.
    path: str | None = None
    handlers: dict[str, str] = Field(default_factory=dict)
    #: A `Node`'s named connection points, drawn on whichever edge a future
    #: pass decides (left for inputs, right for outputs). Meaningless outside
    #: `NodeGraph`. Parsed the same way as `classes:` -- a list or a
    #: space-separated string.
    inputs: Classes = ()
    outputs: Classes = ()
    #: A `NodeGraph`'s statically declared wires between ports, each
    #: `"node.port"` on both ends. Meaningless outside `NodeGraph`.
    edges: tuple[EdgeSpec, ...] = ()
    children: tuple[WidgetSpec, ...] = ()

    @field_validator("handlers")
    @classmethod
    def _check_handler_names(cls, value: dict[str, str]) -> dict[str, str]:
        for event in value:
            if not event.startswith("on_"):
                raise ValueError(f"handler key {event!r} must start with 'on_'")
        return value

    def templates(self) -> dict[str, Template | None]:
        """Compiled template per rendered-value attribute, keyed the same
        way `ElementMixin` stores them -- see `TEMPLATED_FIELDS`.

        Adding a new `{{ }}`-bindable field to this spec is now just that
        field's declaration above plus one entry in `TEMPLATED_FIELDS`:
        `ElementMixin.init_element`/`update_spec`/`bind` all loop over
        this dict rather than each needing a hand-written line per field --
        the previous shape, where a new field meant a matching
        `<field>_template()` method here *and* three more hand-maintained
        spots in `tree/element.py`, was exactly how `disabled:` once went
        missing from `update_spec` (see that method's own comment).
        """
        return {
            attr: Template(value) if (value := getattr(self, field)) is not None else None
            for field, attr in TEMPLATED_FIELDS
        }

    def walk(self) -> Any:
        yield self
        for child in self.children:
            yield from child.walk()


class StyleRule(_Frozen):
    """One stylesheet rule: what it matches, and what it sets.

    Selectors are structured rather than a CSS-like string. A string grammar
    would need `#name`, which YAML reads as a comment unless quoted -- a
    papercut on every rule -- and this form validates with a path to the
    offending field like every other part of the format.

    A rule with no selector at all matches everything, which is how you set a
    baseline.
    """

    #: Match a widget kind, e.g. `Button`.
    widget: WidgetKind | None = None
    #: Match nodes carrying **all** of these classes.
    classes: Classes = ()
    #: Match one node by name.
    name: Identifier | None = None
    #: What to apply. Only fields set here are applied; the rest are not
    #: defaults being imposed, they are simply absent from the rule.
    style: StyleSpec = StyleSpec()

    @property
    def specificity(self) -> tuple[int, int, int]:
        """CSS's ordering: a name beats any number of classes, which beat a
        kind. Ties are broken by document order, later winning."""
        return (1 if self.name else 0, len(self.classes), 1 if self.widget else 0)

    def matches(self, node: WidgetSpec) -> bool:
        if self.name is not None and node.name != self.name:
            return False
        if self.widget is not None and node.widget != self.widget:
            return False
        return all(c in node.classes for c in self.classes)


class ViewSpec(_Frozen):
    """A whole view file: a schema version plus one root widget."""

    version: int = SCHEMA_VERSION
    root: WidgetSpec
    #: Overlays live OUTSIDE the root tree, not hoisted out of it. A dialog is
    #: not laid out or clipped by whatever opened it, so declaring it as a
    #: child would be a lie about the geometry.
    overlays: tuple[WidgetSpec, ...] = ()
    #: Stylesheet rules, applied to every node before the element tree is
    #: built. Resolution happens once at load, so nothing is paid per frame.
    styles: tuple[StyleRule, ...] = ()
    #: Type-scale role -> size in dp. Supplied by the application, because the
    #: reference library does not carry the figures (see `spec/typescale.py`).
    type_scale: dict[TypeRole, float] = Field(default_factory=dict)

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: int) -> int:
        if value != SCHEMA_VERSION:
            raise ValueError(
                f"view schema version {value} is not supported "
                f"(this build understands version {SCHEMA_VERSION})"
            )
        return value
