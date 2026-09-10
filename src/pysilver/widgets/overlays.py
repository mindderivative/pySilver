"""Material Design 3 overlay components: Dialog, Menu, Tooltip, Snackbar, Sheets.

These are the six components the overlay layer exists for (`runtime/overlay.py`).
That host already owns placement, the scrim, modality and dismissal, so what
these classes add is M3's **anatomy** -- container tokens, shape, and the
padding between the parts -- and no positioning logic of their own. A Dialog
does not know it is centred; it knows it is 28dp-rounded `surface_container_high`
that is at least 280dp and at most 560dp wide.

Every dimension below is cited from `M3-References`. Where the scraped spec has
no table -- Snackbar's corner radius is the one case -- the value is taken from
the shape scale and marked as inferred rather than quietly invented.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

from ..layout import (
    OFFSET_ZERO,
    Axis,
    Constraints,
    EdgeInsets,
    Flex,
    MainAxisSize,
    Offset,
    Padding,
    Size,
)
from ..motion import Animation
from ..runtime.events import PointerEvent
from ..spec import StyleSpec, WidgetSpec
from ..tree.element import PaintContext
from .base import _StyledMixin, content_token, measure_text, paint_text
from .material import _box, _emit_state_layer

#: Settling a released drag back to rest. The same pair the overlay host uses
#: for an overlay entering the screen ("Emphasized decelerate | 400ms"), since
#: returning to rest is the same motion as arriving there.
SNAP_DURATION: Final = "medium4"
SNAP_CURVE: Final = "emphasized_decelerate"

__all__ = [
    "BottomSheetElement",
    "DialogElement",
    "MenuElement",
    "MenuItemElement",
    "PopoverElement",
    "SideSheetElement",
    "SnackbarElement",
    "TooltipElement",
]


def _surface(
    ctx: PaintContext,
    absolute: Any,
    size: Size,
    *,
    token: int,
    radii: tuple[float, float, float, float],
    alpha: float = 1.0,
) -> None:
    """`_box` with per-corner radii, which the sheets need.

    A bottom sheet rounds only its top corners and a side sheet only its
    leading edge, so the single-radius helper in `material.py` cannot express
    them.
    """
    dpr = ctx.pixel_ratio
    ctx.display_list.add_box(
        absolute.x * dpr,
        absolute.y * dpr,
        size.width * dpr,
        size.height * dpr,
        token=token,
        color=(1.0, 1.0, 1.0, alpha),
        radii=tuple(r * dpr for r in radii),  # type: ignore[arg-type]
        clip=ctx.clip,
        clip_radii=ctx.clip_radii,
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _clamped_width(
    constraints: Constraints,
    style: StyleSpec,
    *,
    minimum: float,
    maximum: float,
    unbounded: float,
) -> float:
    """M3's min/max width, reconciled with the constraints actually given.

    Three rules, in order:

    1. An explicit `width:` in the view always wins.
    2. Otherwise the component **fills the width it is offered**, capped at the
       M3 maximum. pySilver has no intrinsic-sizing pass -- layout is one
       downward pass of constraints (ARCHITECTURE.md 5.4) -- so a menu cannot
       ask "how wide is my widest item?". Filling the offer is the honest
       fallback, and a designer who wants content width sets `width:`.
    3. With **unbounded** width there is nothing to fill, so the component
       takes *unbounded* -- its M3 minimum for a menu or dialog, its maximum
       for a sheet, which is meant to span the window.

    The final `constrain_width` is not optional: a layout node must return a
    size its constraints permit (`layout/node.py` asserts this). M3's minimum
    is therefore an aspiration that yields to a narrower parent -- without it a
    Menu offered 50dp raised outright rather than shrinking.
    """
    if style.width.kind == "fixed":
        return constraints.constrain_width(float(style.width.value))
    available = constraints.max_width if constraints.has_bounded_width else unbounded
    return constraints.constrain_width(_clamp(available, minimum, maximum))


class _PaddedFlex(_StyledMixin, Flex):
    """A Flex that reserves padding around its children.

    `Flex` has no padding of its own, so it is applied by deflating the
    constraints, laying out normally, then translating each child by the
    top-left inset. Child offsets are assigned during `Flex.perform_layout`
    and are safe to adjust immediately afterwards.
    """

    axis: Axis = Axis.VERTICAL
    #: Subclass hook: the M3 padding for this component.
    INSETS: ClassVar[EdgeInsets] = EdgeInsets()

    def __init__(self, spec: WidgetSpec) -> None:
        Flex.__init__(self, axis=self.axis, spacing=spec.style.spacing)
        self.init_element(spec)

    def configure(self) -> None:
        self._spacing = self.style.spacing

    def insets(self) -> EdgeInsets:
        pad = self.style.padding
        return pad if pad != EdgeInsets() else self.INSETS

    def perform_layout(self, constraints: Constraints) -> Size:
        pad = self.insets()
        self._main_size = MainAxisSize.MIN
        inner = super().perform_layout(constraints.deflate(pad))
        for child in self.children:
            child.offset = child.offset + pad.top_left
        return constraints.constrain(inner.inflate(pad))


# ------------------------------------------------------------------- dialog


class DialogElement(_StyledMixin, Padding):
    """M3 basic dialog.

    Anatomy, from `COMPONENT_DIALOGS.md`: an optional 24dp icon, a headline
    (`text:`), supporting text (`supporting_text:`), and an actions area --
    supplied as the single child, normally a Horizontal of buttons. `icon:`
    needed no schema change -- already a generic `TEMPLATED_FIELDS` entry
    (`spec/models.py`) from the earlier Icon/IconButton/Fab/NavItem/
    SearchBar migration.

    **The icon changes more than just adding a glyph.** The Measurements
    table states it outright: "Alignment with icon: Center-aligned" /
    "Alignment without icon: Start-aligned" -- confirmed against the actual
    annotated example (`m3.material.io`, fetched live, not recalled): with
    an icon, the icon AND the headline are both horizontally centred as a
    column; the supporting text stays start-aligned regardless -- the
    diagram's own body paragraph is clearly left-flush even directly under
    a centred title. Icon colour is `secondary` -- the one colour role in
    this page's own list ("Surface container high, Secondary, On surface,
    On surface variant, Primary, Scrim") not already claimed by the
    container, headline, supporting text, buttons, or scrim.

    The dialog **shrink-wraps its height** ("Container height: Dynamic") and
    clamps its width to 280-560dp. That is the point of having the widget: the
    view file no longer guesses a fixed height that breaks the moment the body
    text rewraps.
    """

    RADIUS: Final = 28.0
    PADDING: Final = 24.0
    MIN_WIDTH: Final = 280.0
    #: "Dialogs (modal)" sit at level 3.
    RESTING_ELEVATION = 3
    MAX_WIDTH: Final = 560.0
    HEADLINE: Final = 24.0
    BODY: Final = 14.0
    #: "Padding between title and body: 16dp"
    GAP_TITLE_BODY: Final = 16.0
    #: "Padding between body and actions: 24dp"
    GAP_BODY_ACTIONS: Final = 24.0
    #: "Icon size: 24dp".
    ICON: Final = 24.0
    #: "Padding between icon and title: 16dp".
    GAP_ICON_TITLE: Final = 16.0

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
        return pad if pad != EdgeInsets() else EdgeInsets.all(DialogElement.PADDING)

    def configure(self) -> None:
        self._padding = self._insets(self.style)

    @property
    def _has_icon(self) -> bool:
        return bool(self._icon.strip())

    def _width(self, constraints: Constraints) -> float:
        return _clamped_width(
            constraints,
            self.style,
            minimum=self.MIN_WIDTH,
            maximum=self.MAX_WIDTH,
            unbounded=self.MIN_WIDTH,
        )

    def _blocks(self, inner_width: float) -> tuple[float, float]:
        """Measured heights of the (icon +) headline and supporting text."""
        engine = self.text_engine
        head = self._text.strip()
        body = self._supporting.strip()
        head_h = (
            measure_text(head, self.HEADLINE, engine=engine, max_width=inner_width).height
            if head
            else 0.0
        )
        if self._has_icon:
            head_h += self.ICON + self.GAP_ICON_TITLE
        body_h = (
            measure_text(body, self.BODY, engine=engine, max_width=inner_width).height
            if body
            else 0.0
        )
        if head_h and body_h:
            body_h += self.GAP_TITLE_BODY
        return head_h, body_h

    def perform_layout(self, constraints: Constraints) -> Size:
        pad = self._padding
        width = self._width(constraints)
        inner_width = max(0.0, width - pad.horizontal)
        head_h, body_h = self._blocks(inner_width)
        text_h = head_h + body_h

        actions_h = 0.0
        child = self.child
        if child is not None:
            # Tight, not `min_width=0.0`: the actions child (normally a
            # `Horizontal` of buttons) must fill the dialog's own content
            # width, or its own `main_alignment` has no free space to push
            # anything into. Found live (phil: "cancel and delete buttons
            # are aligned to the left, the delete button needs to be
            # aligned to the right") -- with `min_width=0.0`, a Horizontal
            # shrink-wraps to its buttons' own content width regardless of
            # `main_alignment: end`, so the whole row sat flush against
            # `pad.left` no matter what the view asked for. M3's own basic-
            # dialog diagrams (fetched live earlier this session) always
            # show the actions clustered together at the dialog's trailing
            # edge, matching what `main_alignment: end` was already
            # correctly asking for in the demo -- the row just never had
            # room to honour it.
            child.layout(
                Constraints(
                    min_width=inner_width,
                    max_width=inner_width,
                    min_height=0.0,
                    max_height=constraints.max_height,
                )
            )
            actions_h = child.size.height
            gap = self.GAP_BODY_ACTIONS if text_h else 0.0
            child.offset = Offset(pad.left, pad.top + text_h + gap)
            actions_h += gap

        height = pad.vertical + text_h + actions_h
        if self.style.height.kind == "fixed":
            height = float(self.style.height.value)
        return constraints.constrain(Size(width, height))

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        radii = self.effective_radii
        _surface(
            ctx,
            absolute,
            self.size,
            token=ctx.palette.index(style.background or "surface_container_high"),
            radii=radii,
        )

        pad = self._padding
        inner_width = max(0.0, self.size.width - pad.horizontal)
        x = absolute.x + pad.left
        y = absolute.y + pad.top
        has_icon = self._has_icon
        head = self._text.strip()
        body = self._supporting.strip()

        if has_icon:
            ctx.text.emit_icon(
                ctx.display_list,
                self._icon.strip(),
                x=absolute.x + (self.size.width - self.ICON) / 2,
                y=y,
                size=self.ICON,
                pixel_ratio=ctx.pixel_ratio,
                token=ctx.palette.index("secondary"),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )
            y += self.ICON + self.GAP_ICON_TITLE

        if head:
            head_size = measure_text(
                head, self.HEADLINE, engine=self.text_engine, max_width=inner_width
            )
            # Centred as a column with the icon when one is present; the
            # ordinary start-aligned headline otherwise -- COMPONENT_DIALOGS.
            # md's own "Alignment with/without icon" row, made concrete.
            head_x = absolute.x + (self.size.width - head_size.width) / 2 if has_icon else x
            paint_text(
                ctx,
                head_x,
                y,
                head,
                self.HEADLINE,
                content_token(ctx, style, "on_surface"),
                max_width=inner_width,
            )
            y += head_size.height
        if body:
            if head:
                y += self.GAP_TITLE_BODY
            paint_text(
                ctx,
                x,
                y,
                body,
                self.BODY,
                ctx.palette.index("on_surface_variant"),
                max_width=inner_width,
            )


# ------------------------------------------------------------------ popover


class PopoverElement(_StyledMixin, Padding):
    """M3 has no Popover component -- what it has is the **persistent rich
    tooltip**, which is a popover in every behavioural sense and differs from
    the transient kind only in trigger: "Persistent rich tooltips appear when
    ... the parent element is clicked" and "remain active even when leaving
    the target region. They only disappear once a person interacts with
    another UI element. Hovering doesn't trigger the tooltip." (`COMPONENT_
    TOOLTIPS.md`). That maps onto pySilver's existing overlay primitives with
    nothing new to build there: `placement: anchor` (already what `Menu`
    uses) plus the default `dismissable: true` gives click-outside-to-close
    for free, and this widget adds only the anatomy -- container, shape, and
    the gap between subhead, body, and an optional action row -- exactly the
    division of labour `Dialog` and `Menu` already follow.

    Anatomy and colours are the rich tooltip's: subhead (`text:`) and
    supporting text (`supporting_text:`) both `on_surface_variant`, container
    `surface_container_high`, `12dp` corners (`shape.corner.medium`), and
    elevation level 2 -- the same level `Menu` sits at.

    **Width is shrink-to-fit, not fill-to-minimum, and that is a real
    difference from `Dialog` and `Menu` rather than an oversight.** Both of
    those have an M3-stated *minimum* width and so take the width they are
    offered, capped at their maximum (`_clamped_width`). The rich tooltip's
    condensed spec states only a maximum -- `320dp` -- and nothing else,
    which matches its tooltip heritage: a popover with one short line of text
    should be exactly that wide, not stretched to look like a dialog.
    """

    RADIUS: Final = 12.0
    MAX_WIDTH: Final = 320.0
    RESTING_ELEVATION = 2
    SUBHEAD: Final = 14.0
    BODY: Final = 14.0
    #: "Top padding: 12dp / Bottom padding: 8dp / Left and right padding: 16dp"
    PAD_TOP: Final = 12.0
    PAD_BOTTOM: Final = 8.0
    PAD_X: Final = 16.0
    #: Not separately stated for the rich tooltip; reused from Dialog's own
    #: title-to-body and body-to-actions gaps rather than invented afresh,
    #: since both separate a headline block from what follows it.
    GAP_SUBHEAD_BODY: Final = 16.0
    GAP_BODY_ACTIONS: Final = 24.0

    DEFAULT_PLACEMENT = "anchor"

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
        if pad != EdgeInsets():
            return pad
        return EdgeInsets(
            PopoverElement.PAD_X,
            PopoverElement.PAD_TOP,
            PopoverElement.PAD_X,
            PopoverElement.PAD_BOTTOM,
        )

    def configure(self) -> None:
        self._padding = self._insets(self.style)

    def _content_width(self, constraints: Constraints, inner_max: float) -> float:
        """Shrink-to-fit: as wide as the widest line actually needs, never
        wider than *inner_max*. A single short word must not claim the whole
        320dp budget the way `Dialog`'s stated minimum would force it to."""
        if self.style.width.kind == "fixed":
            return max(0.0, float(self.style.width.value) - self._padding.horizontal)
        engine = self.text_engine
        head = self._text.strip()
        body = self._supporting.strip()
        natural = 0.0
        if head:
            natural = max(natural, measure_text(head, self.SUBHEAD, engine=engine).width)
        if body:
            natural = max(natural, measure_text(body, self.BODY, engine=engine).width)
        return min(inner_max, natural) if natural else 0.0

    def perform_layout(self, constraints: Constraints) -> Size:
        pad = self._padding
        outer_max = (
            min(self.MAX_WIDTH, constraints.max_width)
            if constraints.has_bounded_width
            else self.MAX_WIDTH
        )
        inner_max = max(0.0, outer_max - pad.horizontal)
        inner_width = self._content_width(constraints, inner_max)

        engine = self.text_engine
        head = self._text.strip()
        body = self._supporting.strip()
        head_h = (
            measure_text(head, self.SUBHEAD, engine=engine, max_width=inner_width).height
            if head
            else 0.0
        )
        body_h = (
            measure_text(body, self.BODY, engine=engine, max_width=inner_width).height
            if body
            else 0.0
        )
        if head_h and body_h:
            body_h += self.GAP_SUBHEAD_BODY
        text_h = head_h + body_h

        actions_h = 0.0
        child = self.child
        if child is not None:
            child.layout(
                Constraints(
                    min_width=0.0,
                    max_width=inner_max,
                    min_height=0.0,
                    max_height=constraints.max_height,
                )
            )
            inner_width = max(inner_width, child.size.width)
            gap = self.GAP_BODY_ACTIONS if text_h else 0.0
            child.offset = Offset(pad.left, pad.top + text_h + gap)
            actions_h += gap + child.size.height

        width = inner_width + pad.horizontal
        height = pad.vertical + text_h + actions_h
        return constraints.constrain(Size(width, height))

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        _surface(
            ctx,
            absolute,
            self.size,
            token=ctx.palette.index(style.background or "surface_container_high"),
            radii=self.effective_radii,
        )

        pad = self._padding
        inner_width = max(0.0, self.size.width - pad.horizontal)
        x = absolute.x + pad.left
        y = absolute.y + pad.top
        head = self._text.strip()
        body = self._supporting.strip()

        if head:
            paint_text(
                ctx,
                x,
                y,
                head,
                self.SUBHEAD,
                ctx.palette.index("on_surface_variant"),
                max_width=inner_width,
            )
            y += measure_text(
                head, self.SUBHEAD, engine=self.text_engine, max_width=inner_width
            ).height
        if body:
            if head:
                y += self.GAP_SUBHEAD_BODY
            paint_text(
                ctx,
                x,
                y,
                body,
                self.BODY,
                ctx.palette.index("on_surface_variant"),
                max_width=inner_width,
            )


# --------------------------------------------------------------------- menu


class MenuElement(_PaddedFlex):
    """M3 baseline menu: 4dp corners, 112-280dp wide, 8dp vertical padding.

    Values from `COMPONENT_MENUS.md` ("Baseline menu padding and size
    measurements"). The vertical-menu variant M3 now leads with adds shape
    morphing and vibrant colour, both of which need motion and a theme engine
    pySilver does not have yet -- so the baseline is what is implemented, and
    that is a deliberate choice rather than an oversight.

    **Shrink-wraps to its widest row by default**, unlike most overlays: an
    explicit `width:` still wins, but otherwise this measures every
    `MenuItem` child's own `natural_width()` (padding, label, shortcut or
    chevron -- content only) and takes the largest, clamped to the 112-280dp
    range above. A menu that always filled the space it was offered read as
    an accident of `OverlayHost`'s window-sized constraints, not a real
    design -- a two-item menu has no reason to be as wide as a ten-item one.
    """

    RADIUS: Final = 4.0
    #: "Menu" sits at level 2.
    RESTING_ELEVATION = 2
    MIN_WIDTH: Final = 112.0
    MAX_WIDTH: Final = 280.0
    PAD_Y: Final = 8.0
    INSETS: ClassVar[EdgeInsets] = EdgeInsets.symmetric(vertical=PAD_Y)
    axis = Axis.VERTICAL

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        radii = self.style.corner_radius
        return radii if any(radii) else (self.RADIUS,) * 4

    def _shrink_wrapped_width(self, constraints: Constraints) -> float:
        """The widest child's own content width, clamped to the M3 range.

        A throwaway measuring pass: each child is laid out once here under
        unbounded width to learn what it actually needs
        (`parent_uses_size=False`, since this result is discarded), then
        laid out again for real once `perform_layout` below knows the
        menu's resolved width -- the standard shrink-to-content technique
        for a single-pass, constraints-down layout engine that otherwise
        has no way to ask a child its natural size.
        """
        probe = Constraints.unbounded()
        natural = max(
            (child.layout(probe, parent_uses_size=False).width for child in self._children),
            default=self.MIN_WIDTH,
        )
        return constraints.constrain_width(_clamp(natural, self.MIN_WIDTH, self.MAX_WIDTH))

    def perform_layout(self, constraints: Constraints) -> Size:
        width = (
            constraints.constrain_width(float(self.style.width.value))
            if self.style.width.kind == "fixed"
            else self._shrink_wrapped_width(constraints)
        )
        inner = constraints.copy_with(min_width=width, max_width=width)
        return super().perform_layout(inner)

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        _surface(
            ctx,
            absolute,
            self.size,
            token=ctx.palette.index(self.style.background or "surface_container"),
            radii=self.effective_radii,
        )


class MenuItemElement(_StyledMixin, Padding):
    """One row of a Menu: 48dp tall, 12dp side padding.

    Distinct from `ListItem`, whose M3 heights are 56/72/88dp -- a menu row is
    denser. `supporting_text:` is the trailing text (a keyboard shortcut, in
    practice), drawn `on_surface_variant` at the far edge.

    `icon:` is an optional 24dp leading icon (`COMPONENT_MENUS.md`'s own
    anatomy: "List item leading icon"), needing no schema change -- already a
    generic `TEMPLATED_FIELDS` entry (`spec/models.py`) from the earlier
    Icon/IconButton/Fab/NavItem/SearchBar migration. Painted `on_surface_
    variant` (the same role the trailing shortcut/chevron already use, and
    the measurements table's own "left/right padding with-icon: 12dp" --
    unchanged from the no-icon case, so only the label shifts, not the
    row's own edges). Mirrors `NavItemElement`'s own expanded-row pattern
    (icon, then `ICON + GAP` of space, then the label) rather than
    inventing a new one.

    `style.has_submenu` swaps the trailing slot for a 24dp `chevron_right`
    instead -- M3's anatomy lists a generic "Trailing icon (optional)", and a
    right-facing chevron marking "this opens more choices" is the near-
    universal convention for it (shown in the spec's own submenu screenshot,
    though not stated in words to quote). The two trailing contents are
    mutually exclusive: a row that opens a submenu does not also carry its
    own keyboard shortcut.

    The submenu itself is a plain `Menu` overlay declared separately and
    anchored to this item's `name` -- this widget only draws the affordance.
    See `OverlayHost._anchored` for how that anchor resolves (the trigger
    lives inside another overlay, not the main tree) and positions beside the
    item rather than below it.
    """

    HEIGHT: Final = 48.0
    PAD_X: Final = 12.0
    LABEL: Final = 14.0
    CHEVRON: Final = 24.0
    #: "Leading/trailing icon size: 24dp" (`COMPONENT_MENUS.md`'s own
    #: baseline-menu measurement table) -- the same figure as `CHEVRON`
    #: above, kept as its own name since the two are conceptually distinct
    #: slots (leading icon vs. trailing chevron), not the same one reused.
    ICON: Final = 24.0
    #: "Padding between elements within a list item" (`COMPONENT_MENUS.md`'s
    #: own baseline-menu measurement table) -- the gap between the label and
    #: whichever trailing content this row has, and, now, between a leading
    #: icon and the label.
    GAP: Final = 12.0
    CURSOR = "pointer"

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @property
    def _has_icon(self) -> bool:
        return bool(self._icon.strip())

    def natural_width(self) -> float:
        """This row's own content width: side padding, an optional leading
        icon, the label, and whichever trailing content it has (a shortcut
        or the submenu chevron) -- nothing else. `MenuElement` measures
        every row against this to shrink-wrap the whole menu to its widest
        one, rather than each row filling whatever width it happens to be
        offered."""
        width = self.PAD_X * 2
        if self._has_icon:
            width += self.ICON + self.GAP
        label = self._text.strip()
        if label:
            width += measure_text(label, self.LABEL, engine=self.text_engine).width
        if self.style.has_submenu:
            width += self.GAP + self.CHEVRON
        else:
            trailing = self._supporting.strip()
            if trailing:
                width += (
                    self.GAP + measure_text(trailing, self.LABEL, engine=self.text_engine).width
                )
        return width

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else self.natural_width()
        height = (
            float(self.style.height.value) if self.style.height.kind == "fixed" else self.HEIGHT
        )
        return outer.constrain(Size(width, height))

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        label_token = content_token(ctx, style, "on_surface")
        if style.background:
            _surface(
                ctx,
                absolute,
                self.size,
                token=ctx.palette.index(style.background),
                radii=(0.0,) * 4,
            )
        _emit_state_layer(ctx, self, absolute, label_token, (0.0,) * 4)

        x = absolute.x + self.PAD_X
        if self._has_icon:
            ctx.text.emit_icon(
                ctx.display_list,
                self._icon.strip(),
                x=x,
                y=absolute.y + (self.size.height - self.ICON) / 2,
                size=self.ICON,
                pixel_ratio=ctx.pixel_ratio,
                token=ctx.palette.index("on_surface_variant"),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )
            x += self.ICON + self.GAP

        label = self._text.strip()
        if label:
            metrics = measure_text(label, self.LABEL, engine=self.text_engine)
            paint_text(
                ctx,
                x,
                absolute.y + (self.size.height - metrics.height) / 2,
                label,
                self.LABEL,
                label_token,
            )
        if style.has_submenu:
            ctx.text.emit_icon(
                ctx.display_list,
                "chevron_right",
                x=absolute.x + self.size.width - self.PAD_X - self.CHEVRON,
                y=absolute.y + (self.size.height - self.CHEVRON) / 2,
                size=self.CHEVRON,
                pixel_ratio=ctx.pixel_ratio,
                token=ctx.palette.index("on_surface_variant"),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )
            return

        trailing = self._supporting.strip()
        if trailing:
            metrics = measure_text(trailing, self.LABEL, engine=self.text_engine)
            paint_text(
                ctx,
                absolute.x + self.size.width - self.PAD_X - metrics.width,
                absolute.y + (self.size.height - metrics.height) / 2,
                trailing,
                self.LABEL,
                ctx.palette.index("on_surface_variant"),
            )


# ------------------------------------------------------------------ tooltip


class TooltipElement(_StyledMixin, Padding):
    """M3 plain tooltip: 24dp minimum height, 8dp padding.

    From `COMPONENT_TOOLTIPS.md`: container `inverse_surface`, label
    `inverse_on_surface`, 24dp/8dp anatomy. Never modal and never scrimmed --
    a tooltip explains what is underneath it, so covering that would defeat it.

    **Deliberate departure from that spec**: the default colours here are
    `surface_container_high`/`on_surface_variant` -- the same tokens
    `Menu`/`Popover` use -- not the inverse pair M3 states. Overridden on
    request: a plain tooltip inverting relative to every other overlay in the
    same window read as visually inconsistent rather than as the intentional
    M3 distinction it is. `style.background`/`style.color` still override
    per instance, including back to the spec's own inverse pair.
    """

    RADIUS: Final = 4.0
    MIN_HEIGHT: Final = 24.0
    #: The spec table gives a single "Padding: 8dp". It has to mean the
    #: horizontal inset: 8dp above and below a body-small label would exceed
    #: the 24dp container height the same table specifies. So 8dp on the sides,
    #: and the vertical inset is whatever centres the label in 24dp.
    PAD_X: Final = 8.0
    PAD_Y: Final = 4.0
    LABEL: Final = 12.0

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        radii = self.style.corner_radius
        return radii if any(radii) else (self.RADIUS,) * 4

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        label = self._text.strip()
        metrics = measure_text(label, self.LABEL, engine=self.text_engine) if label else Size(0, 0)
        return outer.constrain(
            Size(
                metrics.width + self.PAD_X * 2,
                max(self.MIN_HEIGHT, metrics.height + self.PAD_Y * 2),
            )
        )

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        _surface(
            ctx,
            absolute,
            self.size,
            token=ctx.palette.index(style.background or "surface_container_high"),
            radii=self.effective_radii,
        )
        label = self._text.strip()
        if not label:
            return
        metrics = measure_text(label, self.LABEL, engine=self.text_engine)
        paint_text(
            ctx,
            absolute.x + self.PAD_X,
            absolute.y + (self.size.height - metrics.height) / 2,
            label,
            self.LABEL,
            content_token(ctx, style, "on_surface_variant"),
        )


# ----------------------------------------------------------------- snackbar


class SnackbarElement(_StyledMixin, Padding):
    """M3 snackbar: `inverse_surface`, 48dp single line growing to 64dp.

    Colours and the 48-64dp growth are from `COMPONENT_SNACKBAR.md`. That page
    carries no measurement table, so two values here are **inferred, not
    quoted**: the 4dp corner radius comes from the extra-small step of the
    shape scale (`styles/M3-Styles-Shape-CornerRadiusScale.md`), and the 600dp
    width cap is a desktop-reasonable choice, since the spec constrains a
    snackbar only by "a fixed distance from the leading, trailing, and bottom
    edges". Both are flagged because every other number in this module is
    sourced.

    `supporting_text:` is the optional action label, drawn `inverse_primary` at
    the trailing edge. It is a real control -- `handlers: {on_action: ...}`
    fires when it is clicked, found and fixed during the widget-by-widget
    review: `paint_self` drew it but nothing ever hit-tested it, so a view
    reaching for the natural-looking `children: [{widget: Button, ...}]`
    shape instead (every OTHER overlay's action area works that way) got a
    child this class never lays out or paints at all -- an orphaned element
    floating at whatever stale offset it last had. `supporting_text:` +
    `on_action:` is the only shape this widget actually supports.

    `style.auto_dismiss` (seconds, opt-in, `None` by default) is the other
    half of `COMPONENT_SNACKBAR.md`'s own behaviour section: an actionless
    snackbar may auto-dismiss after 4-10 seconds; one with an action
    shouldn't, so users can act on it "at their own pace." `_maybe_arm_auto_dismiss`
    enforces that second half itself -- it ignores the field outright whenever
    `supporting_text:` is set, rather than leaving the gate to the caller.
    """

    RADIUS: Final = 4.0
    MIN_HEIGHT: Final = 48.0
    MAX_HEIGHT: Final = 64.0
    PAD_X: Final = 16.0
    LABEL: Final = 14.0
    MAX_WIDTH: Final = 600.0
    DEFAULT_PLACEMENT = "bottom"

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        radii = self.style.corner_radius
        return radii if any(radii) else (self.RADIUS,) * 4

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def _action_width(self) -> float:
        action = self._supporting.strip()
        if not action:
            return 0.0
        return measure_text(action, self.LABEL, engine=self.text_engine).width + self.PAD_X

    def _on_action(self, x: float) -> bool:
        action_w = self._action_width()
        if action_w <= 0.0:
            return False
        local = x - self.absolute_rect().x
        return bool(local >= self.size.width - action_w)

    def cursor_at(self, x: float, y: float) -> str | None:
        if self._on_action(x):
            return "pointer"
        return super().cursor_at(x, y)

    def on_click(self, event: Any) -> None:
        if self.effective_disabled or not self._on_action(event.x):
            return
        handler = self.handlers.get("on_action")
        if handler is not None:
            handler(event)

    def _maybe_arm_auto_dismiss(self) -> None:
        """Start (once) M3's auto-dismiss timer for an actionless snackbar.

        Called from `paint_self`, which -- unlike layout's constraint-keyed
        cache -- keeps running through the entrance and exit fades, since
        `OverlayHost.paint` re-reads `entry.opacity` every frame either is
        animating; that is what lets this see the open and the closed edge
        of a toggle without a dedicated hook. `state.data["auto_dismiss_timer"]`
        marks "already armed for this open" and is cleared the moment
        `is_open` goes false, so a later reopen starts a fresh countdown --
        the same flag-on-`state.data` shape `BottomSheetElement`'s own
        `dismiss_requested`/`snap_back` already use, reused rather than
        inventing a second mechanism.

        One disclosed edge: `OverlayHost.paint` also skips a fully
        transparent entry outright (`if opacity <= 0.0: continue`), so on
        the very first frame of an open -- exactly zero motion time
        elapsed, opacity still exactly 0.0 -- this can't run at all. A real
        window self-corrects within one more frame (the entrance fade keeps
        the ticker active, so another frame is always requested right
        away); the one sequence this doesn't cover is closing and reopening
        with *no* real frame rendered in between at all, which does not
        happen from actual clicks (each dispatches its own frame).
        """
        if not self.is_open:
            self.state.data.pop("auto_dismiss_timer", None)
            return
        duration = self.style.auto_dismiss
        if duration is None or self._supporting.strip() or "auto_dismiss_timer" in self.state.data:
            return

        def _check_done() -> None:
            if timer.done:
                self.state.data["dismiss_requested"] = True

        # `curve="linear"` is deliberate, not the default "standard" easing:
        # an eased curve's derivative flattens toward its endpoint, so two
        # ticks close to completion can round to the identical float once
        # passed through it -- `advance()` only calls `on_change` when
        # `.value` actually differs from the previous tick, so that flat
        # tail silently ate the one call this needed, on the exact frame
        # `.done` became true. A linear ramp has no flattening tail, so the
        # completing tick always produces a new value and this fires. Found
        # by tracing a real run where the countdown finished but never
        # dismissed -- not a hypothetical.
        timer = Animation(0.0, 1.0, duration=duration, curve="linear", on_change=_check_done)
        self.state.data["auto_dismiss_timer"] = self.ticker.add(timer)

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = _clamped_width(
            outer, self.style, minimum=0.0, maximum=self.MAX_WIDTH, unbounded=self.MAX_WIDTH
        )

        text_width = max(0.0, width - self.PAD_X * 2 - self._action_width())
        label = self._text.strip()
        metrics = (
            measure_text(label, self.LABEL, engine=self.text_engine, max_width=text_width)
            if label
            else Size(0, 0)
        )
        return outer.constrain(Size(width, self._height_for(metrics.height)))

    def _height_for(self, text_height: float) -> float:
        """M3 gives two heights, not a formula: 48dp for one line, 64dp for two.

        So this counts lines rather than padding the measured height -- an
        arithmetic version landed on 62dp for two lines, which is not a number
        the spec contains.
        """
        one_line = measure_text("Ag", self.LABEL, engine=self.text_engine).height
        return self.MIN_HEIGHT if text_height <= one_line + 1.0 else self.MAX_HEIGHT

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        self._maybe_arm_auto_dismiss()
        style = self.style
        _surface(
            ctx,
            absolute,
            self.size,
            token=ctx.palette.index(style.background or "inverse_surface"),
            radii=self.effective_radii,
        )
        label_token = content_token(ctx, style, "inverse_on_surface")
        action = self._supporting.strip()
        action_w = self._action_width()

        label = self._text.strip()
        if label:
            text_width = max(0.0, self.size.width - self.PAD_X * 2 - action_w)
            metrics = measure_text(label, self.LABEL, engine=self.text_engine, max_width=text_width)
            paint_text(
                ctx,
                absolute.x + self.PAD_X,
                absolute.y + (self.size.height - metrics.height) / 2,
                label,
                self.LABEL,
                label_token,
                max_width=text_width,
            )
        if action:
            metrics = measure_text(action, self.LABEL, engine=self.text_engine)
            paint_text(
                ctx,
                absolute.x + self.size.width - self.PAD_X - metrics.width,
                absolute.y + (self.size.height - metrics.height) / 2,
                action,
                self.LABEL,
                ctx.palette.index("inverse_primary"),
            )


# ------------------------------------------------------------------- sheets


class BottomSheetElement(_PaddedFlex):
    """M3 bottom sheet: full width to a 640dp max, 28dp top corners.

    From `COMPONENT_BOTTOM_SHEETS.md`: `surface_container_low`, an optional
    32x4dp drag handle centred with 22dp padding above and below, and a 640dp
    max width. Only the top corners round, because the sheet is flush with the
    bottom edge of the window.

    **The handle is draggable.** M3: "the drag handle can be dragged or
    selected to change the bottom sheet height", and a sheet is dismissed by
    swiping it down. Dragging moves the sheet; releasing past a threshold
    dismisses it, and releasing short of one snaps it back.

    **Clicking the handle closes the sheet.** M3 requires a single-pointer
    alternative to dragging -- "selecting the drag handle should toggle through
    preset heights or close the sheet". Preset heights are not implemented, so
    a click closes, which is the other half of that sentence.

    `handle:` remains off by default: a sheet without one cannot be dragged,
    and drawing an affordance is what promises the gesture.
    """

    RADIUS: Final = 28.0
    #: "Bottom sheet (modal)" sits at level 1.
    RESTING_ELEVATION = 1
    MAX_WIDTH: Final = 640.0
    HANDLE_WIDTH: Final = 32.0
    HANDLE_HEIGHT: Final = 4.0
    HANDLE_PAD: Final = 22.0
    #: "an optional drag handle with an accessible 48dp hit target". Quoted,
    #: and justified here on pointer grounds rather than M3's finger rule: the
    #: handle is 4dp tall, which no mouse can reliably hit.
    HANDLE_TARGET: Final = 48.0
    #: Fraction of its own height a sheet must be dragged down to dismiss on
    #: release. **Not sourced** -- M3 describes the gesture, not a threshold.
    DISMISS_FRACTION: Final = 0.35
    #: Movement below this is a click, not a drag.
    CLICK_SLOP: Final = 4.0
    DEFAULT_PLACEMENT = "bottom"
    DOCKED = True
    axis = Axis.VERTICAL

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        radii = self.style.corner_radius
        return radii if any(radii) else (self.RADIUS, self.RADIUS, 0.0, 0.0)

    def _handle_band(self) -> float:
        """Vertical space the drag handle occupies, including its padding."""
        if not self.style.handle:
            return 0.0
        return self.HANDLE_HEIGHT + self.HANDLE_PAD * 2

    def insets(self) -> EdgeInsets:
        pad = super().insets()
        band = self._handle_band()
        return EdgeInsets(pad.left, pad.top + band, pad.right, pad.bottom) if band else pad

    def perform_layout(self, constraints: Constraints) -> Size:
        width = _clamped_width(
            constraints,
            self.style,
            minimum=0.0,
            maximum=self.MAX_WIDTH,
            unbounded=self.MAX_WIDTH,
        )
        inner = constraints.copy_with(min_width=width, max_width=width)
        return super().perform_layout(inner)

    # ------------------------------------------------------------ dragging

    @property
    def drag_offset(self) -> Offset:
        """How far the sheet is displaced from its resting place.

        Read by the overlay host when it places the sheet, so dragging moves
        the whole thing -- container, handle and content together -- without
        any of them knowing they are being dragged.

        While a finger is down this is the raw pointer delta: a drag must track
        the pointer exactly, and easing it would make the sheet lag behind the
        thing moving it. Only the release is animated.
        """
        if "drag_start" in self.state.data:
            return Offset(0.0, float(self.state.data.get("drag_dy", 0.0)))
        snap = self.state.data.get("snap_back")
        if snap is not None:
            if snap.done:
                del self.state.data["snap_back"]
                return OFFSET_ZERO
            return Offset(0.0, float(snap.value))
        return OFFSET_ZERO

    def cursor_at(self, x: float, y: float) -> str | None:
        if self.grabs_handle(x, y):
            return "ns-resize"
        return super().cursor_at(x, y)

    def grabs_handle(self, x: float, y: float) -> bool:
        if not self.style.handle:
            return False
        rect = self.absolute_rect()
        band = self.HANDLE_TARGET
        return (rect.x <= x <= rect.right) and (rect.y <= y <= rect.y + band)

    def on_pointer_down(self, event: PointerEvent) -> None:
        if not self.grabs_handle(event.x, event.y):
            return
        self.state.data["drag_start"] = event.y
        self.state.data["drag_dy"] = 0.0
        event.capture()
        event.stop_propagation()

    def on_pointer_move(self, event: PointerEvent) -> None:
        if "drag_start" not in self.state.data:
            return
        # Downwards only: a sheet is docked to the bottom edge, so dragging it
        # up would lift it off the edge its square corners sit against.
        self.state.data["drag_dy"] = max(0.0, event.y - self.state.data["drag_start"])
        self.mark_needs_paint()

    def on_pointer_up(self, event: PointerEvent) -> None:
        if "drag_start" not in self.state.data:
            return
        travelled = self.state.data.pop("drag_dy", 0.0)
        self.state.data.pop("drag_start", None)
        if travelled <= self.CLICK_SLOP:
            # A select, not a drag. M3 requires this alternative to exist.
            self.state.data["dismiss_requested"] = True
        elif travelled >= self.size.height * self.DISMISS_FRACTION:
            self.state.data["dismiss_requested"] = True
        elif travelled > 0.0:
            # Short of the threshold: settle back rather than jump. Emphasized
            # decelerate is M3's "enter the screen" pair, and returning to rest
            # is the same motion as arriving.
            self.state.data["snap_back"] = self.ticker.add(
                Animation(
                    travelled,
                    0.0,
                    duration=SNAP_DURATION,
                    curve=SNAP_CURVE,
                    on_change=self.mark_needs_paint,
                )
            )
        self.mark_needs_paint()

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        _surface(
            ctx,
            absolute,
            self.size,
            token=ctx.palette.index(self.style.background or "surface_container_low"),
            radii=self.effective_radii,
        )
        if not self.style.handle:
            return
        _box(
            ctx,
            absolute.x + (self.size.width - self.HANDLE_WIDTH) / 2,
            absolute.y + self.HANDLE_PAD,
            self.HANDLE_WIDTH,
            self.HANDLE_HEIGHT,
            token=ctx.palette.index("on_surface_variant"),
            radius=self.HANDLE_HEIGHT / 2,
            alpha=0.4,
        )


class SideSheetElement(_PaddedFlex):
    """M3 side sheet: 400dp max width, full height, 16dp leading corners.

    From `COMPONENT_SIDE_SHEETS.md`: `surface_container_low`, 24dp start/end
    padding, 400dp max width, 16dp corner radius. Which corners round depends
    on the edge it is docked to, taken from `placement:` -- a right-hand sheet
    rounds its left corners and vice versa.
    """

    RADIUS: Final = 16.0
    #: "Side sheet (modal)" sits at level 1.
    RESTING_ELEVATION = 1
    MAX_WIDTH: Final = 400.0
    PADDING: Final = 24.0
    INSETS: ClassVar[EdgeInsets] = EdgeInsets.all(PADDING)
    DEFAULT_PLACEMENT = "right"
    DOCKED = True
    axis = Axis.VERTICAL

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        radii = self.style.corner_radius
        if any(radii):
            return radii
        r = self.RADIUS
        # Round only the edge that faces into the window.
        if self.resolved_placement == "left":
            return (0.0, r, r, 0.0)
        return (r, 0.0, 0.0, r)

    def perform_layout(self, constraints: Constraints) -> Size:
        style = self.style
        width = _clamped_width(
            constraints, style, minimum=0.0, maximum=self.MAX_WIDTH, unbounded=self.MAX_WIDTH
        )
        height = (
            float(style.height.value)
            if style.height.kind == "fixed"
            else (constraints.max_height if constraints.has_bounded_height else 0.0)
        )
        inner = constraints.copy_with(min_width=width, max_width=width)
        if height:
            inner = inner.copy_with(min_height=height, max_height=height)
        return super().perform_layout(inner)

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        _surface(
            ctx,
            absolute,
            self.size,
            token=ctx.palette.index(self.style.background or "surface_container_low"),
            radii=self.effective_radii,
        )
