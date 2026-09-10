"""Material Design 3 navigation, app bar, tabs, lists, and progress.

Three of these -- NavigationRail, Tabs, SegmentedButton -- share one shape:
a container of items where exactly one is selected. That is modelled once
here:

* the container carries ``value:``, the id of the selected child;
* during layout it calls ``set_selected`` on each child;
* the item renders its own selected appearance and reads the icon FILL axis
  from it, which is precisely what M3 uses FILL for.

**Bottom-anchored navigation is deliberately absent.** M3's Navigation Bar and
Bottom App Bar are mobile patterns; the rail and drawer are their desktop
counterparts (ARCHITECTURE.md 1.2.1).
"""

from __future__ import annotations

import math
from typing import Any, Final

from ..layout import (
    INF,
    Axis,
    Constraints,
    CrossAxisAlignment,
    EdgeInsets,
    Flex,
    LayoutNode,
    MainAxisSize,
    Offset,
    Padding,
    Rect,
    Size,
)
from ..spec import WidgetSpec
from ..spec.typescale import TYPE_SCALE
from ..tree.element import ElementMixin, PaintContext
from .base import _StyledMixin, content_token, measure_text, paint_text
from .material import (
    SELECTION_CURVE,
    SELECTION_MOTION,
    BadgeElement,
    _arc,
    _box,
    _emit_state_layer,
    _state_alpha,
)

__all__ = [
    "CircularProgressElement",
    "LinearProgressElement",
    "ListItemElement",
    "NavItemElement",
    "NavigationRailElement",
    "SegmentElement",
    "SegmentedButtonElement",
    "StatusBarElement",
    "TabElement",
    "TabsElement",
    "TopAppBarElement",
    "TreeItemElement",
    "TreeViewElement",
]

#: The components' own M3 type roles, quoted from M3_COMPONENT_SPECS.md: a
#: navigation bar's "Text Label Typography" is `label-medium` (12sp), an
#: app-bar title is `title-large` (22sp), a tab is `title-small` (14sp).
#:
#: Each is held as the whole role rather than as loose numbers, so its size,
#: weight and tracking reach a widget's measure and its paint together. They
#: cannot be half-applied, which is what a separate SIZE/WEIGHT pair allowed.
#:
#: A Segment reuses the Tab role. Only the Tab's is sourced; a segmented button
#: is its sibling control and looking different from it would be worse than
#: following it. NavigationRail's own *expanded*-state label is not here:
#: section 4.4 (the old drawer spec) states no typography, so it keeps a
#: plain size rather than borrowing a role it was never given.
LABEL_ROLE: Final = TYPE_SCALE["label-medium"]
TITLE_ROLE: Final = TYPE_SCALE["title-large"]
TAB_LABEL_ROLE: Final = TYPE_SCALE["title-small"]
TITLE_SIZE: Final = TITLE_ROLE.size
ICON: Final = 24.0

#: One full turn, for the circular progress sweep.
TAU: Final = 2.0 * math.pi

#: An indicator sliding or growing "begins and ends on screen"; M3's suggested
#: pairs table offers Emphasized/500ms or Standard/300ms for that. The standard
#: row is the right one: these respond to a click and are repeated freely, and
#: half a second of emphasis on every tab change would drag.
INDICATOR_MOTION: Final = "medium2"
INDICATOR_CURVE: Final = "standard"

#: How finely the icon FILL axis is stepped while animating.
#:
#: FILL is a variable-font axis, and the axis coordinates are part of the glyph
#: atlas key (`render/atlas.py`). The atlas has no per-entry eviction -- when it
#: fills it resets wholesale and re-rasterises everything -- so animating FILL
#: continuously would pack a fresh rasterisation every frame and force repeated
#: resets. Six steps still reads as a transition and bounds the entries per
#: icon at six.
ICON_FILL_STEPS: Final = 6


def _stepped_fill(t: float) -> float:
    """Quantise an animated FILL so the atlas sees a bounded set of values."""
    return round(t * ICON_FILL_STEPS) / ICON_FILL_STEPS


class _SelectionContainer(_StyledMixin, Flex):
    """A Flex whose ``value:`` names the selected child by id."""

    axis: Axis = Axis.HORIZONTAL

    def __init__(self, spec: WidgetSpec) -> None:
        Flex.__init__(self, axis=self.axis, spacing=spec.style.spacing)
        self.init_element(spec)

    def configure(self) -> None:
        self._spacing = self.style.spacing

    def apply_selection(self) -> None:
        """Push the selected id(s) down to the children. Called before layout.

        `style.multi_select` (meaningful today only for `SegmentedButton`,
        M3's one component with a named multi-select form) switches `value:`
        from a single name to a comma-separated set -- everything else about
        this method, and every other consumer of it, is unchanged.
        """
        if self.style.multi_select:
            active_set = {name.strip() for name in self._value.split(",") if name.strip()}
            for child in self.children:
                if hasattr(child, "set_selected"):
                    child.set_selected(child.name in active_set)
            return
        active = self._value.strip()
        for child in self.children:
            if hasattr(child, "set_selected"):
                child.set_selected(bool(active) and child.name == active)

    def perform_layout(self, constraints: Constraints) -> Size:
        self.apply_selection()
        return super().perform_layout(constraints)

    def selected_child(self) -> Any | None:
        return next((c for c in self.children if getattr(c, "selected", False)), None)


# --------------------------------------------------------- navigation rail


class NavItemElement(_StyledMixin, Padding):
    """One destination in a `NavigationRail`, collapsed or expanded.

    `icon:` is the icon name and `label:` the destination's label. The icon's
    FILL axis goes to 1 when selected -- M3's own mechanism for expressing
    selection, rather than swapping to a different icon.
    """

    #: "Navigation drawer (modal)" -- the rail's own expanded anatomy -- is
    #: elevation level 1; collapsed is level 0.
    RAIL_W: Final = 80.0
    RAIL_H: Final = 56.0
    INDICATOR_W: Final = 56.0
    INDICATOR_H: Final = 32.0
    DRAWER_H: Final = 56.0
    DRAWER_RADIUS: Final = 28.0
    DRAWER_PAD: Final = 16.0

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @property
    def _expanded(self) -> bool:
        """Row anatomy (icon+label side by side) once the parent's own
        collapse/expand transform has crossed its halfway point; stacked
        icon-over-label otherwise. Swaps rather than interpolates -- the
        same precedent `AccordionElement`'s chevron already establishes for
        a shape change with no continuous parameter to animate through
        ("a glyph instance carries no rotation parameter... a mid-transition
        swap would read as a glitch, not a rotation"); a `Flex` arrangement
        has no interpolation parameter either.
        """
        parent = self.parent
        return isinstance(parent, NavigationRailElement) and parent.progress() > 0.5

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self.DRAWER_RADIUS,) * 4 if self._expanded else (self.INDICATOR_H / 2,) * 4

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        if self._expanded:
            width = outer.max_width if outer.has_bounded_width else 240.0
            return outer.constrain(Size(width, self.DRAWER_H))
        label = self._label_height()
        return outer.constrain(Size(self.RAIL_W, self.INDICATOR_H + label + 4.0))

    def _label_height(self) -> float:
        if not (self._label).strip():
            return 0.0
        return measure_text(self._label, LABEL_ROLE, engine=self.text_engine).height

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        selected = self.selected
        size = self.size
        active_bg = ctx.palette.index("secondary_container")
        t = self.animated(
            "selected",
            1.0 if selected else 0.0,
            duration=INDICATOR_MOTION,
            curve=INDICATOR_CURVE,
        )
        content = content_token(
            ctx,
            self.style,
            "on_secondary_container" if selected else "on_surface_variant",
        )
        label_text = (self._label).strip()

        if self._expanded:
            if t > 0.0:
                _box(
                    ctx,
                    absolute.x,
                    absolute.y,
                    size.width,
                    size.height,
                    token=active_bg,
                    radius=self.DRAWER_RADIUS,
                    alpha=t,
                )
            _emit_state_layer(ctx, self, absolute, content, self.effective_radii)
            x = absolute.x + self.DRAWER_PAD
            if self._icon.strip():
                ctx.text.emit_icon(
                    ctx.display_list,
                    self._icon.strip(),
                    x=x,
                    y=absolute.y + (size.height - ICON) / 2,
                    size=ICON,
                    fill=_stepped_fill(t),
                    pixel_ratio=ctx.pixel_ratio,
                    token=content,
                    clip=ctx.clip,
                    clip_radii=ctx.clip_radii,
                )
                x += ICON + 12.0
            if label_text:
                label = measure_text(label_text, 14.0, engine=self.text_engine)
                paint_text(
                    ctx, x, absolute.y + (size.height - label.height) / 2, label_text, 14.0, content
                )
            return

        # Rail: a 56x32dp indicator pill behind the icon, label beneath. It
        # grows outward from a circle around the icon rather than appearing at
        # full width, which is how M3 expands it.
        if t > 0.0:
            width = self.INDICATOR_H + (self.INDICATOR_W - self.INDICATOR_H) * t
            _box(
                ctx,
                absolute.x + (size.width - width) / 2,
                absolute.y,
                width,
                self.INDICATOR_H,
                token=active_bg,
                radius=self.INDICATOR_H / 2,
                alpha=t,
            )
        _emit_state_layer(ctx, self, absolute, content, self.effective_radii)
        if self._icon.strip():
            ctx.text.emit_icon(
                ctx.display_list,
                self._icon.strip(),
                x=absolute.x + (size.width - ICON) / 2,
                y=absolute.y + (self.INDICATOR_H - ICON) / 2,
                size=ICON,
                fill=_stepped_fill(t),
                pixel_ratio=ctx.pixel_ratio,
                token=content,
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )
        if label_text:
            label = measure_text(label_text, LABEL_ROLE, engine=self.text_engine)
            paint_text(
                ctx,
                absolute.x + (size.width - label.width) / 2,
                absolute.y + self.INDICATOR_H + 4.0,
                label_text,
                LABEL_ROLE,
                content,
            )


class NavigationRailElement(_SelectionContainer):
    """M3 Navigation Rail: collapsed (80dp, icon-only) or expanded (240-360dp,
    icon+label) -- one component with two states that transform into each
    other, per M3 Expressive's own merger of the old Rail/Drawer split
    (`COMPONENT_NAVIGATION_RAIL.md`: "the expanded nav rail is meant to
    replace the [modal] navigation drawer"; "collapsed and expanded
    navigation rails... can easily transform into each other when the menu
    button is selected"). Never hidden by its own state -- "the collapsed
    navigation rail should not be hidden" -- an application that wants it
    fully gone does so through ordinary view composition, not this widget.
    """

    COLLAPSED_W: Final = 80.0
    EXPANDED_DEFAULT_W: Final = 300.0
    EXPANDED_MAX_W: Final = 360.0
    axis = Axis.VERTICAL

    def progress(self) -> float:
        """0 (collapsed) to 1 (expanded) -- drives the animated width, the
        same `animated(..., invalidates="layout")` pattern `AccordionElement`
        uses for its own expand/collapse. Relayouts every frame of the
        transition (`animated()`'s own documented cost), affordable here
        since M3 itself caps a rail at "3-7 navigation items". `NavItem`
        also reads this (via `self.parent.progress()`) to pick its anatomy.
        """
        return self.animated(
            "expanded",
            0.0 if self.collapsed else 1.0,
            duration=SELECTION_MOTION,
            curve=SELECTION_CURVE,
            invalidates="layout",
        )

    def perform_layout(self, constraints: Constraints) -> Size:
        #: `constrain_width` is not optional here -- a layout node must
        #: return a size its constraints permit (`layout/node.py` asserts
        #: this). `_resolved_width`'s own "no explicit width" fallback
        #: returns the flat M3 default with no regard for how much room was
        #: actually offered, so a `Horizontal` squeezed narrower than the
        #: expanded default would raise instead of shrink. See
        #: `overlays.py`'s sibling `_resolved_width` for the same reasoning
        #: applied to Menu/Dialog/Popover/the sheets.
        expanded_w = min(
            self.EXPANDED_MAX_W,
            _resolved_width(self.style, constraints, self.EXPANDED_DEFAULT_W),
        )
        width = self.COLLAPSED_W + (expanded_w - self.COLLAPSED_W) * self.progress()
        w = constraints.constrain_width(width)
        inner = constraints.copy_with(min_width=w, max_width=w)
        return super().perform_layout(inner)

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        _box(
            ctx,
            absolute.x,
            absolute.y,
            self.size.width,
            self.size.height,
            token=ctx.palette.index(self.style.background or "surface_container"),
            radius=0.0,
        )


def _resolved_width(style: Any, constraints: Constraints, default: float) -> float:
    if style.width.kind == "fixed":
        return float(style.width.value)
    if style.width.kind == "expand" and constraints.has_bounded_width:
        return constraints.max_width
    if style.width.kind == "percent" and constraints.has_bounded_width:
        return constraints.max_width * float(style.width.value)
    return default


# ------------------------------------------------------------- top app bar


class TopAppBarElement(_StyledMixin, Flex):
    """M3 Top App Bar: 64dp small/center-aligned, 112dp medium, 152dp large.

    A medium or large bar **collapses into a small one as its page scrolls** --
    "when scrolled, medium and large app bars can transform into small app
    bars; they should remain small until the page is scrolled back to the top".
    Name the scrolling view with `collapses_with:`::

        - {name: bar, widget: TopAppBar, text: Inbox,
           style: {variant: large, collapses_with: body}}
        - {name: body, widget: ScrollView, style: {height: expand}}

    This is **scroll-linked**, not timed: there is no animation clock involved,
    the height is a direct function of the offset. The bar registers as a
    follower of that scroll view, which relayouts it as the view moves -- the
    scrolled content itself is untouched and still travels at paint time.

    Heights and title typography are the condensed spec's own text (not the
    deep-dive page's measurement images, which remain unread): 64dp small/
    center-aligned; medium collapsed 64dp, expanded 112dp; large collapsed
    64dp, expanded 152dp. Title typography is title-large (22sp) collapsed;
    headline-medium (28sp) for the medium variant expanded, headline-large
    (32sp) for the large variant expanded -- two different expanded roles,
    not one size shared by both.
    """

    HEIGHT: Final = 64.0
    PAD: Final = 16.0
    #: variant -> expanded height. Small and centre-aligned do not collapse.
    EXPANDED: Final = {"medium": 112.0, "large": 152.0}
    #: The expanded headline, shrinking to title-large on collapse -- one role
    #: per variant, since M3 states "headline-medium (28sp) for medium
    #: expanded; headline-large (32sp) for large expanded", not one size for
    #: both. Held as a role (not a bare size) so the size and the line height
    #: shrink together -- interpolating one and pinning the other would
    #: tighten the leading as the bar moved.
    EXPANDED_HEADLINE_ROLE: Final = {
        "medium": TYPE_SCALE["headline-medium"],
        "large": TYPE_SCALE["headline-large"],
    }

    def __init__(self, spec: WidgetSpec) -> None:
        Flex.__init__(self, axis=Axis.HORIZONTAL, spacing=spec.style.spacing or 8.0)
        self.init_element(spec)
        self._followed: Any = None

    def configure(self) -> None:
        self._spacing = self.style.spacing or 8.0
        self._followed = None  # the view may have been renamed by a reload

    @property
    def expanded_height(self) -> float:
        return self.EXPANDED.get(str(self.style.variant), self.HEIGHT)

    def _scroll_source(self) -> Any:
        """The ScrollView named by `collapses_with:`, resolved once.

        Looked up from the root rather than a sibling search: an app bar and
        the view it follows need not share a parent, and often will not.
        """
        name = self.style.collapses_with
        if name is None:
            return None
        if self._followed is None:
            node: Any = self
            while node.parent is not None:
                node = node.parent
            found = node.find(name) if hasattr(node, "find") else None
            if found is not None and hasattr(found, "scroll_offset"):
                found.follow(self)
                self._followed = found
        return self._followed

    @property
    def collapse(self) -> float:
        """How far collapsed, 0 (fully expanded) to 1 (a small bar)."""
        expanded = self.expanded_height
        travel = expanded - self.HEIGHT
        if travel <= 0.0:
            return 0.0
        source = self._scroll_source()
        if source is None:
            return 0.0
        return max(0.0, min(1.0, float(source.scroll_offset) / travel))

    @property
    def current_height(self) -> float:
        expanded = self.expanded_height
        return expanded - (expanded - self.HEIGHT) * self.collapse

    def perform_layout(self, constraints: Constraints) -> Size:
        height = self.current_height
        outer = constraints.copy_with(min_height=height, max_height=height)
        size = super().perform_layout(outer)
        for child in self.children:
            child.offset = child.offset + EdgeInsets.all(self.PAD).top_left
        return size

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        t = self.collapse
        containers: tuple[tuple[int, float], ...]
        if style.background:
            containers = ((ctx.palette.index(style.background), 1.0),)
        else:
            # "On scroll, the container changes color to surface container."
            # Tokens resolve in the shader, so this is two boxes, not a lerp.
            containers = (
                (ctx.palette.index("surface"), 1.0),
                (ctx.palette.index("surface_container"), t),
            )
        for token_index, weight in containers:
            if weight <= 0.0:
                continue
            _box(
                ctx,
                absolute.x,
                absolute.y,
                self.size.width,
                self.size.height,
                token=token_index,
                radius=0.0,
                alpha=weight,
            )
        title = self._text.strip()
        if not title:
            return
        token = content_token(ctx, style, "on_surface")
        size = style.font_size if style.font_size != 14.0 else TITLE_SIZE
        leading = TITLE_ROLE.line_height
        if self.expanded_height > self.HEIGHT:
            # The headline shrinks to title-large as the bar becomes a small
            # one, so the two forms agree at the moment of arrival.
            headline_role = self.EXPANDED_HEADLINE_ROLE[str(style.variant)]
            size = headline_role.size + (size - headline_role.size) * t
            leading = headline_role.line_height + (leading - headline_role.line_height) * t
        label = measure_text(
            title,
            size,
            engine=self.text_engine,
            weight=TITLE_ROLE.weight,
            tracking=TITLE_ROLE.tracking,
            line_height=leading,
        )
        x = (
            absolute.x + (self.size.width - label.width) / 2
            if style.variant == "center_aligned"
            else absolute.x + self.PAD
        )
        paint_text(
            ctx,
            x,
            absolute.y + (self.size.height - label.height) / 2,
            title,
            size,
            token,
            weight=TITLE_ROLE.weight,
            tracking=TITLE_ROLE.tracking,
            line_height=leading,
        )


# --------------------------------------------------------------- status bar


class StatusBarElement(_StyledMixin, Flex):
    """A thin, informational bar docked to a window edge -- word count,
    encoding, a git branch, connection state.

    M3 has neither this widget nor the phrase "status bar" anywhere in its
    own vocabulary -- checked directly rather than assumed absent, the same
    way `Pagination`'s grounding was checked. Its cousin from the same
    docked-bar family that DOES exist, the docked toolbar (M3's replacement
    for the deprecated bottom app bar), is a different thing: a row of
    *action* buttons, not an informational strip, so this does not borrow
    its anatomy despite sitting at the same edge of a window.

    Built the way `TopAppBar` is: a plain `Flex` a view populates with
    whatever `Text`/`Icon`/`Divider` children it wants. There is no special
    "leading"/"trailing" slot to learn -- a `Spacer` does that split the same
    way it would in any other `Horizontal`.

    `surface_container` background, no drawn border, follows this
    framework's existing convention for a docked surface (`Card`, `Menu`,
    `TopAppBar`, both sheets all read the same way): a tonal shift says "this
    is a separate surface" without a hard line. The 24dp height and 16dp
    horizontal padding are not sourced -- there is nothing to source them
    from -- chosen to read as clearly thinner than every interactive
    control's own 40dp+ density in this framework, which is the one thing a
    purely informational bar should never be mistaken for.
    """

    HEIGHT: Final = 24.0
    PAD_X: Final = 16.0

    def __init__(self, spec: WidgetSpec) -> None:
        Flex.__init__(self, axis=Axis.HORIZONTAL, spacing=spec.style.spacing or 8.0)
        self.init_element(spec)

    def configure(self) -> None:
        self._spacing = self.style.spacing or 8.0

    def flex_of(self, child: Any) -> int:
        """A child styled `expand` or `flex:n` is flexible, matching Horizontal and
        Vertical's own `_FlexElement.flex_of`.

        This widget extends `Flex` directly rather than `_FlexElement`, so
        without this override a `Spacer` meant to push trailing items to the
        far edge -- the documented way to split this bar into leading and
        trailing groups -- is measured as an ordinary inflexible child. It
        would then be sized against nearly all the remaining width and
        starve whatever comes after it, rather than sharing the space.
        """
        explicit = super().flex_of(child)
        if explicit:
            return explicit
        if not isinstance(child, ElementMixin):
            return 0
        size = child.style.width
        if size.kind == "flex":
            return max(1, int(size.value))
        return 1 if size.kind == "expand" else 0

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = constraints.copy_with(min_height=self.HEIGHT, max_height=self.HEIGHT)
        pad = EdgeInsets.symmetric(horizontal=self.PAD_X)
        inner = super().perform_layout(outer.deflate(pad))
        for child in self.children:
            child.offset = child.offset + pad.top_left
        return outer.constrain(inner.inflate(pad))

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        token = ctx.palette.index(self.style.background or "surface_container")
        _box(
            ctx, absolute.x, absolute.y, self.size.width, self.size.height, token=token, radius=0.0
        )


# ------------------------------------------------------------------- tabs


class TabElement(_StyledMixin, Padding):
    """One tab. The active indicator is drawn by the parent Tabs container.

    `icon:` is an optional icon; `style.icon_position` picks its
    arrangement against the label. `"stacked"` (default) is the one
    `COMPONENT_TABS.md`'s own diagram actually shows (`m3.material.io`,
    fetched directly, not recalled): icon above the label, the pair
    vertically centred as one block -- "Icon and labels are now vertically
    centered within the container." `"leading"`/`"trailing"` are opt-in:
    the icon sits beside the label instead, on the named side, using the
    table's own "padding between inline icon and text: 8dp" figure -- a
    real, sourced gap, though the diagram gave no example of the
    arrangement itself, so left-vs-right is a judgment call, not scraped.

    `icon:`/`label:` (via `self._icon`) needed no schema change -- both are
    already generic `TEMPLATED_FIELDS` (`spec/models.py`) from the earlier
    Icon/IconButton/Fab/NavItem/SearchBar migration. `text:` stays this
    widget's own label (it never overloaded `text:` to mean an icon glyph
    the way those five did before that migration), so only `icon:` (and
    now `icon_position`) are new here.

    **`badge:` -- optional notification content, the M3 anatomy's own
    "Badge (optional)" element, present on both primary and secondary tabs.**
    Reuses `Badge`'s own sizing constants (`BadgeElement.DOT`/`HEIGHT`/
    `PAD_X`/`LABEL_SIZE`) rather than re-deriving them, and its own
    `error`/`on_error` colour pair -- a badge's notification state is
    independent of whether ITS OWN tab happens to be selected, the same way
    a real notification dot on an app icon doesn't change colour when the
    app is in focus. `style.badge_variant: dot` shows a bare dot and ignores
    `badge:`'s own content entirely, mirroring `Badge`'s identical
    `variant: dot` distinction ("Small and large badges can both be used
    with tabs").

    Placement is genuinely two different rules, both from `COMPONENT_
    TABS.md`'s own Measurements table, and neither changes with `icon_
    position` (`leading`/`trailing` behave like `stacked` here -- only
    whether the block has a STACKED icon at all matters):

    * **A stacked icon present** (icon-only, or icon+label with `icon_
      position: stacked`): the badge OVERLAPS the icon's own top-right
      corner ("overlap of badge on stacked icon: 6dp"), and the tab's
      measured width is untouched -- a deliberate overlap, not an addition.
      The exact corner offset (`BADGE_OVERLAP`, both axes) is a best-effort
      diagram read (`m3.material.io`, fetched live -- the scraped text
      gives the 6dp figure but not the geometry it applies to), flagged as
      approximate the same way `STACK_GAP` already is; a bare notification
      dot may read as slightly more tucked into the icon than an idealised
      rendering, since 6dp is a much larger fraction of a 6dp dot than of a
      16dp numbered pill.
    * **No stacked icon** (label only, or an inline icon+label): the badge
      sits trailing the whole content block with a 4dp gap ("padding
      between inline text and badge: 4dp", confirmed in the same live
      diagram fetch for the inline-icon case too), and the block's own
      measured width grows to include it -- unlike the overlap case, this
      would otherwise visibly collide with the tab's own edge or the next
      tab's divider.
    """

    HEIGHT: Final = 48.0
    #: `COMPONENT_TABS.md`'s own Measurements table: "Container height (icon
    #: and label text): 64dp" -- read from the same table's "Container
    #: height (label text only): 48dp" row above. One height for "icon and
    #: label text" full stop, not one per arrangement, so this applies to
    #: `leading`/`trailing` exactly as it does to `stacked`.
    ICON_HEIGHT: Final = 64.0
    PAD_X: Final = 16.0
    #: Gap between the icon and the label beneath it, `"stacked"` only.
    #: Read directly from the Measurements diagram (fetched live from
    #: `m3.material.io`, the scraped text alone gives no number for this)
    #: -- a best-effort reading of the diagram's own tick marks, not a
    #: scraped text figure quoted verbatim the way the two heights above
    #: are.
    STACK_GAP: Final = 6.0
    #: Gap between the icon and the label beside it, `"leading"`/
    #: `"trailing"` only. `COMPONENT_TABS.md`'s own Measurements table:
    #: "Padding between inline icon and text: 8dp" -- a real scraped
    #: figure, unlike `STACK_GAP` above.
    INLINE_GAP: Final = 8.0
    #: `COMPONENT_TABS.md`'s own Measurements table: "Padding between inline
    #: text and badge: 4dp" -- a real scraped figure, used whenever there is
    #: no stacked icon for the badge to overlap instead (see the class
    #: docstring's own two-rule split).
    TEXT_BADGE_GAP: Final = 4.0
    #: "Overlap of badge on stacked icon: 6dp" -- also a real scraped
    #: figure, but the *geometry* it inset from (which corner, which axes)
    #: is a diagram read, not scraped text; see the class docstring.
    BADGE_OVERLAP: Final = 6.0

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @property
    def _has_icon(self) -> bool:
        return bool(self._icon.strip())

    @property
    def _has_badge(self) -> bool:
        return bool(self._badge.strip()) or self.style.badge_variant == "dot"

    def _badge_size(self) -> Size:
        """The badge's own box, reusing `Badge`'s own sizing formula
        (`BadgeElement.DOT`/`HEIGHT`/`PAD_X`/`LABEL_SIZE`) rather than
        re-deriving it -- one source of truth for "how big is a badge"."""
        if self.style.badge_variant == "dot":
            return Size(BadgeElement.DOT, BadgeElement.DOT)
        content = self._badge.strip()
        label = measure_text(content, BadgeElement.LABEL_SIZE, engine=self.text_engine)
        width = max(BadgeElement.HEIGHT, label.width + BadgeElement.PAD_X * 2)
        return Size(width, BadgeElement.HEIGHT)

    def _paint_badge(self, ctx: PaintContext, x: float, y: float) -> None:
        """Paint the badge box (and its content, unless a bare dot) with its
        top-left at `(x, y)` -- callers work out where that is, since the
        two placement rules (overlap vs. trailing) differ in more than just
        position."""
        size = self._badge_size()
        content_token_ = ctx.palette.index("on_error")
        _box(
            ctx,
            x,
            y,
            size.width,
            size.height,
            token=ctx.palette.index("error"),
            radius=size.height / 2,
        )
        if self.style.badge_variant == "dot":
            return
        content = self._badge.strip()
        label = measure_text(content, BadgeElement.LABEL_SIZE, engine=self.text_engine)
        paint_text(
            ctx,
            x + (size.width - label.width) / 2,
            y + (size.height - label.height) / 2,
            content,
            BadgeElement.LABEL_SIZE,
            content_token_,
        )

    @property
    def _icon_position(self) -> str:
        return self.style.icon_position

    def perform_layout(self, constraints: Constraints) -> Size:
        label_text = self._text.strip()
        label = measure_text(label_text, TAB_LABEL_ROLE, engine=self.text_engine)
        has_icon = self._has_icon
        height = self.ICON_HEIGHT if has_icon else self.HEIGHT
        # A stacked icon (or an icon with no label at all) is where the
        # badge OVERLAPS instead of adding width -- see the class
        # docstring's own two-rule split.
        stacked_icon = has_icon and (not label_text or self._icon_position == "stacked")
        if not has_icon:
            content_width = label.width
        elif stacked_icon:
            content_width = max(label.width, ICON) if label_text else ICON
        else:
            content_width = ICON + self.INLINE_GAP + label.width
        if self._has_badge and not stacked_icon:
            content_width += self.TEXT_BADGE_GAP + self._badge_size().width
        return self.sized(constraints, self.style).constrain(
            Size(content_width + self.PAD_X * 2, height)
        )

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        token = content_token(ctx, self.style, "primary" if self.selected else "on_surface_variant")
        _emit_state_layer(ctx, self, absolute, token, (0.0,) * 4)
        label_text = self._text.strip()
        has_icon = self._has_icon
        if not has_icon and not label_text:
            return
        label = None
        if label_text:
            label = measure_text(label_text, TAB_LABEL_ROLE, engine=self.text_engine)
        if not has_icon:
            assert label is not None  # not has_icon and not label_text already returned above
            self._paint_label_with_badge(ctx, absolute, token, label_text, label)
            return
        if not label_text or self._icon_position == "stacked":
            self._paint_stacked(ctx, absolute, token, label)
        else:
            assert label is not None  # inline with no label falls into the stacked branch above
            leading = self._icon_position == "leading"
            self._paint_inline(ctx, absolute, token, label, leading=leading)

    def _paint_label_with_badge(
        self, ctx: PaintContext, absolute: Any, token: int, label_text: str, label: Any
    ) -> None:
        """No-icon tab: the label alone, or (label + gap + badge) centred as
        one block -- the same "one block" principle `_paint_stacked`/
        `_paint_inline` already establish for icon+label."""
        if not self._has_badge:
            paint_text(
                ctx,
                absolute.x + (self.size.width - label.width) / 2,
                absolute.y + (self.size.height - label.height) / 2,
                label_text,
                TAB_LABEL_ROLE,
                token,
            )
            return
        badge_size = self._badge_size()
        block_width = label.width + self.TEXT_BADGE_GAP + badge_size.width
        block_height = max(label.height, badge_size.height)
        left = absolute.x + (self.size.width - block_width) / 2
        top = absolute.y + (self.size.height - block_height) / 2
        paint_text(
            ctx,
            left,
            top + (block_height - label.height) / 2,
            label_text,
            TAB_LABEL_ROLE,
            token,
        )
        self._paint_badge(
            ctx,
            left + label.width + self.TEXT_BADGE_GAP,
            top + (block_height - badge_size.height) / 2,
        )

    def _paint_stacked(self, ctx: PaintContext, absolute: Any, token: int, label: Any) -> None:
        # Icon above label, the pair vertically centred as one block
        # ("vertically centered within the container" -- not two
        # independently-centred halves, which is why this measures the
        # whole block's height once rather than centring the icon and the
        # label against the container separately). A badge, if present,
        # OVERLAPS the icon's own corner instead of joining this block --
        # it does not change the block's height or centring at all.
        block_height = ICON + (self.STACK_GAP + label.height if label is not None else 0.0)
        top = absolute.y + (self.size.height - block_height) / 2
        icon_x = absolute.x + (self.size.width - ICON) / 2
        ctx.text.emit_icon(
            ctx.display_list,
            self._icon.strip(),
            x=icon_x,
            y=top,
            size=ICON,
            pixel_ratio=ctx.pixel_ratio,
            token=token,
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        if self._has_badge:
            badge_size = self._badge_size()
            badge_cx = icon_x + ICON - self.BADGE_OVERLAP
            badge_cy = top + self.BADGE_OVERLAP
            self._paint_badge(
                ctx, badge_cx - badge_size.width / 2, badge_cy - badge_size.height / 2
            )
        if label is not None:
            paint_text(
                ctx,
                absolute.x + (self.size.width - label.width) / 2,
                top + ICON + self.STACK_GAP,
                self._text.strip(),
                TAB_LABEL_ROLE,
                token,
            )

    def _paint_inline(
        self, ctx: PaintContext, absolute: Any, token: int, label: Any, *, leading: bool
    ) -> None:
        # Icon beside the label, the pair horizontally centred as one
        # block -- the same "one block, not two independently-centred
        # halves" reasoning `_paint_stacked` uses, just along the other
        # axis. Icon and label each centre against the block's own height,
        # which may exceed either one alone (a tall icon, a multi-line
        # label neither of these callers actually has today, but the
        # centring still has to be correct if one does). A badge, if
        # present, joins this block immediately after the label -- before a
        # trailing icon, after a leading one -- since it is the label the
        # spec ties it to ("padding between inline text and badge"), not
        # whichever side the icon happens to be on.
        has_badge = self._has_badge
        badge_size = self._badge_size() if has_badge else Size(0.0, 0.0)
        extra = (self.TEXT_BADGE_GAP + badge_size.width) if has_badge else 0.0
        block_width = ICON + self.INLINE_GAP + label.width + extra
        block_height = max(ICON, label.height, badge_size.height if has_badge else 0.0)
        left = absolute.x + (self.size.width - block_width) / 2
        top = absolute.y + (self.size.height - block_height) / 2
        if leading:
            icon_x = left
            label_x = left + ICON + self.INLINE_GAP
            badge_x = label_x + label.width + self.TEXT_BADGE_GAP
        else:
            label_x = left
            badge_x = label_x + label.width + self.TEXT_BADGE_GAP
            icon_x = (
                badge_x + badge_size.width + self.INLINE_GAP
                if has_badge
                else label_x + label.width + self.INLINE_GAP
            )
        ctx.text.emit_icon(
            ctx.display_list,
            self._icon.strip(),
            x=icon_x,
            y=top + (block_height - ICON) / 2,
            size=ICON,
            pixel_ratio=ctx.pixel_ratio,
            token=token,
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        paint_text(
            ctx,
            label_x,
            top + (block_height - label.height) / 2,
            self._text.strip(),
            TAB_LABEL_ROLE,
            token,
        )
        if has_badge:
            self._paint_badge(ctx, badge_x, top + (block_height - badge_size.height) / 2)


class TabsElement(_SelectionContainer):
    """M3 Tabs: 48dp high, or 64dp if any tab carries an `icon:`.

    "The container should always... be divided into equal sections" --
    every tab in one bar shares the same height, so one iconed tab lifts
    the whole strip to 64dp rather than sizing itself independently.

    Primary tabs anchor a 3dp, fully-rounded active indicator to the bottom
    edge, inset 2dp on each side so it does not touch the tab's own edges;
    secondary tabs use a flat, full-width, 2dp stroke -- two different
    heights, not one shared between them (`COMPONENT_TABS.md`'s own
    measurements table: "Primary active indicator height: 3dp", "Secondary
    active indicator height: 2dp").
    """

    HEIGHT: Final = 48.0
    INDICATOR_H_PRIMARY: Final = 3.0
    INDICATOR_H_SECONDARY: Final = 2.0
    #: "Primary tab active indicators are inset 2dp on each side" -- secondary's
    #: own "full-width thin stroke" phrasing means no inset at all.
    PRIMARY_INSET: Final = 2.0
    axis = Axis.HORIZONTAL

    def __init__(self, spec: WidgetSpec) -> None:
        # `_SelectionContainer.__init__` doesn't stretch its children --
        # fine for Segment/NavItem, which are always uniform, but a mixed
        # bar (one iconed 64dp tab next to a text-only 48dp one) needs
        # every tab to fill the bar's own height, found live via
        # `test_a_tab_with_an_icon_grows_the_whole_bar_to_sixty_four`: the
        # bar itself grew to 64dp (forced via `perform_layout`'s own
        # constraints below), but an icon-less sibling stayed at its own
        # natural 48dp -- `Flex`'s `CrossAxisAlignment.STRETCH` is the
        # existing primitive for exactly this, not a new one.
        Flex.__init__(
            self,
            axis=self.axis,
            spacing=spec.style.spacing,
            cross_alignment=CrossAxisAlignment.STRETCH,
        )
        self.init_element(spec)

    def _bar_height(self) -> float:
        has_icon = any(isinstance(c, TabElement) and c._has_icon for c in self.children)
        return TabElement.ICON_HEIGHT if has_icon else self.HEIGHT

    def perform_layout(self, constraints: Constraints) -> Size:
        height = self._bar_height()
        inner = constraints.copy_with(min_height=height, max_height=height)
        return super().perform_layout(inner)

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        _box(
            ctx,
            absolute.x,
            absolute.y,
            self.size.width,
            self.size.height,
            token=ctx.palette.index(self.style.background or "surface"),
            radius=0.0,
        )
        active = self.selected_child()
        if active is None:
            return
        primary = self.style.variant != "secondary"
        indicator_h = self.INDICATOR_H_PRIMARY if primary else self.INDICATOR_H_SECONDARY
        inset = self.PRIMARY_INSET if primary else 0.0
        y = absolute.y + self.size.height - indicator_h
        # The indicator belongs to the container, not to a tab, which is what
        # lets it travel between them. Both edges animate, so it stretches and
        # settles rather than jumping -- and this costs paint only, since the
        # tabs themselves have not moved.
        x = self.animated(
            "indicator_x",
            active.offset.x + inset,
            duration=INDICATOR_MOTION,
            curve=INDICATOR_CURVE,
        )
        width = self.animated(
            "indicator_w",
            active.size.width - inset * 2.0,
            duration=INDICATOR_MOTION,
            curve=INDICATOR_CURVE,
        )
        _box(
            ctx,
            absolute.x + x,
            y,
            width,
            indicator_h,
            token=ctx.palette.index("primary"),
            radius=indicator_h if primary else 0.0,
        )


# ------------------------------------------------------- segmented buttons


class SegmentElement(_StyledMixin, Padding):
    """One segment. Selected segments show a leading 18dp checkmark."""

    HEIGHT: Final = 40.0
    PAD_X: Final = 12.0
    CHECK: Final = 18.0
    GAP: Final = 6.0

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def _check_progress(self) -> float:
        """How far the leading checkmark has arrived, 0 to 1.

        Changes the segment's width, so it invalidates layout -- the label and
        the neighbouring segments move with it. The same trade as the filter
        Chip, and affordable for the same reason: a segmented button holds two
        or three children.
        """
        value: float = self.animated(
            "selected",
            1.0 if self.selected else 0.0,
            duration=INDICATOR_MOTION,
            curve=INDICATOR_CURVE,
            invalidates="layout",
        )
        return value

    def perform_layout(self, constraints: Constraints) -> Size:
        label = measure_text(self._text, TAB_LABEL_ROLE, engine=self.text_engine)
        width = label.width + self.PAD_X * 2 + (self.CHECK + self.GAP) * self._check_progress()
        return self.sized(constraints, self.style).constrain(Size(width, self.HEIGHT))

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        selected = self.selected
        token = content_token(
            ctx, self.style, "on_secondary_container" if selected else "on_surface"
        )
        t = self._check_progress()
        if t > 0.0:
            _box(
                ctx,
                absolute.x,
                absolute.y,
                self.size.width,
                self.size.height,
                token=ctx.palette.index("secondary_container"),
                radius=0.0,
                alpha=t,
            )
        _emit_state_layer(ctx, self, absolute, token, (0.0,) * 4)

        x = absolute.x + self.PAD_X
        if t > 0.0:
            # Grows into the space being made for it, or it would overlap a
            # label that has only travelled part of the way.
            check = self.CHECK * t
            ctx.text.emit_icon(
                ctx.display_list,
                "check",
                x=x,
                y=absolute.y + (self.size.height - check) / 2,
                size=check,
                pixel_ratio=ctx.pixel_ratio,
                token=token,
                color=(1.0, 1.0, 1.0, t),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )
            x += (self.CHECK + self.GAP) * t
        if self._text.strip():
            label = measure_text(self._text, TAB_LABEL_ROLE, engine=self.text_engine)
            paint_text(
                ctx,
                x,
                absolute.y + (self.size.height - label.height) / 2,
                self._text,
                TAB_LABEL_ROLE,
                token,
            )


class SegmentedButtonElement(_SelectionContainer):
    """M3 Segmented Buttons: 40dp high, 1dp outline, 20dp outer corners.

    Internal segments share flat borders, so the outline is drawn once around
    the whole container plus a divider between each pair -- not per segment,
    which would double every internal edge.

    `style.multi_select: true` (M3's own "Multi-select" variant) is
    `_SelectionContainer.apply_selection`'s own shared switch -- see its
    docstring. `value:` becomes a comma-separated set of selected names
    instead of one, and more than one `Segment` shows its checkmark at
    once. An application toggling one on `on_click:` adds or removes that
    segment's own name from the set rather than replacing it outright.
    """

    HEIGHT: Final = 40.0
    RADIUS: Final = 20.0
    axis = Axis.HORIZONTAL

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self.RADIUS,) * 4

    @property
    def _stretches(self) -> bool:
        """True when the view gave the group a width to fill."""
        return self.style.width.kind in ("fixed", "expand", "percent")

    def flex_of(self, child: Any) -> int:
        """With an explicit width, segments divide it equally -- M3's stretched
        form. Without one the group shrinks to its content, so the outline
        never runs on past the last segment."""
        return 1 if self._stretches else super().flex_of(child)

    def perform_layout(self, constraints: Constraints) -> Size:
        inner = constraints.copy_with(min_height=self.HEIGHT, max_height=self.HEIGHT)
        self._main_size = MainAxisSize.MAX if self._stretches else MainAxisSize.MIN
        return super().perform_layout(inner)

    CLIPS_CHILDREN = True

    def child_paint_context(self, ctx: PaintContext, absolute: Any) -> PaintContext:
        """Clip segments to the rounded container so a selected end segment's
        square fill does not poke past the outline."""
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
            clip_radii=(self.RADIUS * dpr,) * 4,
        )

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        outline = ctx.palette.index("outline")
        _box(
            ctx,
            absolute.x,
            absolute.y,
            self.size.width,
            self.size.height,
            token=outline,
            radius=self.RADIUS,
            alpha=0.0,
            border_width=1.0,
            border_token=outline,
        )
        for child in list(self.children)[1:]:
            _box(
                ctx,
                absolute.x + child.offset.x,
                absolute.y,
                1.0,
                self.size.height,
                token=outline,
                radius=0.0,
            )


# ------------------------------------------------------------------ lists


class ListItemElement(_StyledMixin, Padding):
    """M3 List item: 56dp one-line, 72dp two-line, 88dp three-line.

    `text:` is the headline, `supporting_text` the second line, and an icon
    name in `style.background`-adjacent fields is not used -- a leading icon is
    given as a child Icon widget instead.
    """

    HEIGHTS: Final = {"one_line": 56.0, "two_line": 72.0, "three_line": 88.0}
    PAD_X: Final = 16.0
    HEADLINE: Final = 16.0
    SUPPORTING: Final = 14.0
    #: "Leading icon top padding: 8dp; ...when height is 88dp or taller: 12dp"
    #: -- a leading icon is always TOP-aligned (unlike a generic leading
    #: element, e.g. an avatar, which centres below 88dp), so this is the
    #: only vertical adjustment it ever needs.
    ICON_TOP: Final = 8.0
    ICON_TOP_TALL: Final = 12.0
    #: Not itself an M3-quoted figure, but self-consistent with one: 16dp
    #: icon left padding + a 24dp icon + this gap lands the label at x=56,
    #: matching the inset: 56 this demo's own Dividers already use to align
    #: under the label rather than the icon.
    ICON_GAP: Final = 16.0

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def _height(self) -> float:
        variant = self.style.variant
        if variant in self.HEIGHTS:
            return self.HEIGHTS[variant]
        return 72.0 if (self._supporting).strip() else 56.0

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else 320.0
        height = self._height()
        if self.child is not None:
            # `Padding`'s own perform_layout (which would otherwise lay out
            # and offset a single child) is fully overridden here, so the
            # leading icon has to be laid out and positioned explicitly --
            # left unfixed, it never gets a real size or offset at all.
            self.child.layout(Constraints(0.0, INF, 0.0, INF))
            top = self.ICON_TOP_TALL if height >= 88.0 else self.ICON_TOP
            self.child.offset = Offset(self.PAD_X, top)
        return outer.constrain(Size(width, height))

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        headline = content_token(ctx, style, "on_surface")
        supporting = ctx.palette.index("on_surface_variant")
        if style.background:
            _box(
                ctx,
                absolute.x,
                absolute.y,
                self.size.width,
                self.size.height,
                token=ctx.palette.index(style.background),
                radius=0.0,
            )
        _emit_state_layer(ctx, self, absolute, headline, (0.0,) * 4)

        second = (self._supporting).strip()
        x = absolute.x + self.PAD_X
        if self.child is not None:
            x += self.child.size.width + self.ICON_GAP
        if second:
            top = measure_text(self._text, self.HEADLINE, engine=self.text_engine)
            bottom = measure_text(second, self.SUPPORTING, engine=self.text_engine)
            block = top.height + bottom.height
            y = absolute.y + (self.size.height - block) / 2
            paint_text(ctx, x, y, self._text, self.HEADLINE, headline)
            paint_text(ctx, x, y + top.height, second, self.SUPPORTING, supporting)
        elif self._text.strip():
            label = measure_text(self._text, self.HEADLINE, engine=self.text_engine)
            paint_text(
                ctx,
                x,
                absolute.y + (self.size.height - label.height) / 2,
                self._text,
                self.HEADLINE,
                headline,
            )


# --------------------------------------------------------------- tree view


class TreeViewElement(_SelectionContainer):
    """M3 has no Tree component -- the same gap Accordion fills, and the same
    source: Lists' "List items containing other list items can expand and
    collapse in a folder-like manner" (`COMPONENT_LISTS.md`). A tree is that
    statement applied recursively rather than once.

    Reuses `_SelectionContainer`'s shape -- `value:` names the selected item
    -- but a tree's selected item can sit at any depth, not just among direct
    children, so `apply_selection` is overridden to walk the whole subtree
    instead of one level.
    """

    axis = Axis.VERTICAL

    def apply_selection(self) -> None:
        active = self._value.strip()

        def walk(node: Any) -> None:
            for child in node.children:
                if isinstance(child, TreeItemElement):
                    child.set_selected(bool(active) and child.name == active)
                    walk(child)

        walk(self)


class TreeItemElement(_StyledMixin, LayoutNode):
    """One node. `children:` of further `TreeItem`s makes it a branch; none
    makes it a leaf, with no chevron and nothing to expand.

    **Anatomy is `ListItem`'s**, exactly as Accordion's is, for the same
    reason: M3 gives this nothing of its own. **Expand state, the chevron
    swap, and the height-animation-plus-clip reveal are Accordion's
    mechanism reused verbatim** -- see `AccordionElement`'s docstring for why
    each of those is shaped the way it is; a tree node is an accordion that
    can nest.

    **Two things ARE new here, because recursion makes them unavoidable:**

    - **Indentation.** Each level indents by one chevron-width (`INDENT`).
      Not sourced from M3 -- no tree page exists to source it from -- chosen
      to line a child's content up under where its own children's chevrons
      would begin, the common convention across desktop tree views.
    - **The clip intersects its ancestor's, rather than replacing it.**
      Accordion and `ScrollView` both simply overwrite the incoming
      `ctx.clip` with their own rect, which is safe only because neither is
      ever nested inside its own kind in practice. A tree item routinely is:
      collapsing a node must hide every descendant regardless of which of
      them are individually expanded, so a grandchild's effective clip has
      to be its own rect intersected with everything above it, not just its
      immediate parent's.

    Selection is a **separate, orthogonal concern** owned by the enclosing
    `TreeView` (`value:` naming the selected node), not by this class --
    the same split Accordion has none of, because it never had a container.
    """

    HEADER_ONE_LINE: Final = 56.0
    HEADER_TWO_LINE: Final = 72.0
    PAD_X: Final = 16.0
    HEADLINE: Final = 16.0
    SUPPORTING: Final = 14.0
    CHEVRON: Final = 24.0
    #: One chevron-width per nesting level -- see the class docstring.
    INDENT: Final = CHEVRON
    CURSOR = "pointer"
    CLIPS_CHILDREN = True

    def __init__(self, spec: WidgetSpec) -> None:
        LayoutNode.__init__(self)
        self.init_element(spec)

    @property
    def depth(self) -> int:
        """Nesting level, derived from ancestry rather than stored -- the
        same idiom `NavItemElement._expanded` uses for its own context."""
        depth = 0
        node = self.parent
        while node is not None:
            if isinstance(node, TreeItemElement):
                depth += 1
            node = node.parent
        return depth

    def _header_height(self) -> float:
        return self.HEADER_TWO_LINE if self._supporting.strip() else self.HEADER_ONE_LINE

    def _progress(self) -> float:
        """0 (collapsed) to 1 (fully expanded) -- see `AccordionElement._progress`."""
        return self.animated(
            "expanded",
            1.0 if self.checked else 0.0,
            duration=SELECTION_MOTION,
            curve=SELECTION_CURVE,
            invalidates="layout",
        )

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else 320.0
        header_h = self._header_height()

        # Every child is laid out and stacked at its NATURAL height regardless
        # of this node's own current (animated) height -- same reasoning as
        # Accordion's single child, generalised to however many there are.
        cursor = header_h
        if self._children:
            child_constraints = Constraints(
                min_width=width, max_width=width, min_height=0.0, max_height=INF
            )
            for child in self._children:
                size = child.layout(child_constraints)
                child.offset = Offset(0.0, cursor)
                cursor += size.height
        body_h = cursor - header_h

        revealed = body_h * self._progress()
        return outer.constrain(Size(width, header_h + revealed))

    #: Real, but far below one physical pixel -- passes the shader's own
    #: `clip.z/w > 0.0` gate (`ui.wgsl`: "a zero-size clip rect means
    #: unclipped") without leaving any rasterisable area. `Rect.intersect`
    #: clamps a no-overlap result to an exact zero in the degenerate
    #: dimension, which that same shader gate reads as "no clip at all" --
    #: the opposite of what a collapsed ancestor needs. Confirmed by
    #: rendering a real frame: a grandchild's label was still on screen
    #: with the un-floored intersection, despite the clip rect looking
    #: correct from the Python side.
    HIDDEN_EXTENT: Final = 0.01

    def child_paint_context(self, ctx: PaintContext, absolute: Any) -> PaintContext:
        """Clip to this node's own (animated) size, INTERSECTED with whatever
        clip already reached it -- see the class docstring for why this
        cannot simply replace the incoming clip the way Accordion's does."""
        dpr = ctx.pixel_ratio
        own = Rect(
            absolute.x * dpr, absolute.y * dpr, self.size.width * dpr, self.size.height * dpr
        )
        clip = own if ctx.clip[2] == 0.0 and ctx.clip[3] == 0.0 else Rect(*ctx.clip).intersect(own)
        width = clip.width if clip.width > 0.0 else self.HIDDEN_EXTENT
        height = clip.height if clip.height > 0.0 else self.HIDDEN_EXTENT
        return PaintContext(
            display_list=ctx.display_list,
            palette=ctx.palette,
            text=ctx.text,
            images=ctx.images,
            pixel_ratio=dpr,
            clip=(clip.x, clip.y, width, height),
            clip_radii=ctx.clip_radii,
        )

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        header_h = self._header_height()
        headline_tok = content_token(ctx, style, "on_surface")
        supporting_tok = ctx.palette.index("on_surface_variant")

        if self.selected:
            dpr = ctx.pixel_ratio
            ctx.display_list.add_box(
                absolute.x * dpr,
                absolute.y * dpr,
                self.size.width * dpr,
                header_h * dpr,
                token=ctx.palette.index("secondary_container"),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )
            headline_tok = ctx.palette.index("on_secondary_container")

        # Scoped to the header row alone -- see AccordionElement.paint_self
        # for why `_emit_state_layer` (sized from the whole animated element)
        # is the wrong helper here.
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

        indent = self.PAD_X + self.depth * self.INDENT
        x = absolute.x + indent
        if self._children:
            icon = "expand_less" if self.checked else "expand_more"
            ctx.text.emit_icon(
                ctx.display_list,
                icon,
                x=x,
                y=absolute.y + (header_h - self.CHEVRON) / 2,
                size=self.CHEVRON,
                pixel_ratio=ctx.pixel_ratio,
                token=supporting_tok,
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )
        # A leaf's label starts where a branch's would, chevron or not, so
        # sibling labels stay aligned regardless of which ones can expand.
        x += self.CHEVRON + 8.0

        second = self._supporting.strip()
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


# --------------------------------------------------------------- progress


#: Indeterminate cycle length. **Not sourced** -- M3 describes the behaviour
#: ("move along a fixed track, growing and shrinking in size") but the scrape
#: carries no cycle duration, so this is the longest M3 duration token.
INDETERMINATE_CYCLE: Final = "extra_long4"


class LinearProgressElement(_StyledMixin, Padding):
    """M3 Linear Progress: 4dp high with rounded ends.

    Omitting `value:` selects the **indeterminate** form, which M3 describes as
    moving "along a fixed track, growing and shrinking in size". Supplying a
    value makes it determinate -- and M3 notes an indicator should change from
    indeterminate to determinate as information arrives, which here is just
    binding `value:` to a signal that starts empty.

    Colour roles are shared with `CircularProgress`: active `primary`, track
    `secondary_container`. This widget originally used `surface_variant` for
    the track, which the spec does not say -- corrected when the circular
    variant was built and the two had to agree.
    """

    HEIGHT: Final = 4.0

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        return (self.HEIGHT / 2,) * 4

    @property
    def indeterminate(self) -> bool:
        """No resolved value at all means the wait time is unknown.

        Read from the live `_value` rather than the static `spec.value` --
        `value:` is templated like `text:`, so a signal bound through it that
        starts empty must be able to flip this determinate on its own once it
        reports one, per docs/view-reference.md's "changes from indeterminate
        to determinate ... as information arrives". `spec.value` is only ever
        the unrendered template source, which is never None once `value:` is
        written at all.
        """
        return not self._value.strip()

    @property
    def progress(self) -> float:
        return max(0.0, min(1.0, self.number))

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else 0.0
        return outer.constrain(Size(width, self.HEIGHT))

    def _indeterminate_span(self) -> tuple[float, float]:
        """Leading edge and length of the travelling bar, as fractions.

        One repeating value drives both, so the bar grows out of the leading
        edge, crosses, and shrinks into the trailing one -- "growing and
        shrinking in size" without a second animation to keep in step.
        """
        # Linear, not eased: a looping animation on an ease curve decelerates
        # into the wrap and jumps back to full speed, which reads as a stutter
        # once a second. Eased curves are for transitions that end.
        t = self.animated(
            "indeterminate", 1.0, duration=INDETERMINATE_CYCLE, curve="linear", repeat=True
        )
        head = min(1.0, t * 2.0)
        tail = max(0.0, t * 2.0 - 1.0)
        return tail, head - tail

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        radius = self.HEIGHT / 2
        _box(
            ctx,
            absolute.x,
            absolute.y,
            self.size.width,
            self.size.height,
            token=ctx.palette.index(self.style.background or "secondary_container"),
            radius=radius,
        )
        if self.indeterminate:
            start, length = self._indeterminate_span()
            offset, filled = self.size.width * start, self.size.width * length
        else:
            # A bound `value:` can flip this element determinate without a
            # dispose -- nothing else stops the repeat=True animation already
            # registered with the ticker, so it would keep firing forever.
            running = self.animation("indeterminate")
            if running is not None:
                self.ticker.discard(running)
            offset, filled = 0.0, self.size.width * self.progress
        if filled > 0:
            _box(
                ctx,
                absolute.x + offset,
                absolute.y,
                filled,
                self.size.height,
                token=content_token(ctx, self.style, "primary"),
                radius=radius,
            )


class CircularProgressElement(_StyledMixin, Padding):
    """M3 Circular Progress: a 4dp ring, filled clockwise from 12 o'clock.

    Omitting `value:` selects the **indeterminate** form: a fixed-length arc
    that rotates continuously, since a circular track has no leading or
    trailing edge for a bar to grow out of.

    Sourced from `COMPONENT_PROGRESS_INDICATORS.md`: "Track thickness: Fixed
    (4dp)", the shared colour roles (active `primary`, track
    `secondary_container`), and "circular indicators animate from the top of
    the track, clockwise by default" -- which is why angles here are measured
    clockwise from 12 o'clock rather than from the +X axis.

    The **48dp default diameter is not sourced**: that page's size table is an
    image, so the scrape carries no text for it. Set `width:` to override.
    """

    DIAMETER: Final = 48.0
    THICKNESS: Final = 4.0

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    #: How much of the ring the spinning arc covers.
    INDETERMINATE_SWEEP: Final = 0.75

    @property
    def indeterminate(self) -> bool:
        """Same rule as `LinearProgress.indeterminate` -- see its docstring."""
        return not self._value.strip()

    @property
    def progress(self) -> float:
        return max(0.0, min(1.0, self.number))

    @property
    def thickness(self) -> float:
        """`style.thickness` defaults to 1dp for Divider's sake, so an explicit
        value is distinguished from the field default rather than compared to
        it."""
        if "thickness" in self.style.model_fields_set:
            return float(self.style.thickness)
        return self.THICKNESS

    def _diameter(self, constraints: Constraints) -> float:
        style = self.style
        if style.width.kind == "fixed":
            return float(style.width.value)
        if style.height.kind == "fixed":
            return float(style.height.value)
        return self.DIAMETER

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        d = self._diameter(constraints)
        # Square by default. A view that sets *both* width and height gets the
        # box it asked for -- constraints are not negotiable -- and the circle
        # is then inscribed in the shorter side and centred by paint_self,
        # rather than stretched into an ellipse.
        return outer.constrain(Size(d, d))

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        thickness = self.thickness
        side = min(self.size.width, self.size.height)
        x = absolute.x + (self.size.width - side) / 2
        y = absolute.y + (self.size.height - side) / 2

        _arc(
            ctx,
            x,
            y,
            side,
            side,
            token=ctx.palette.index(style.background or "secondary_container"),
            thickness=thickness,
            start=0.0,
            sweep=TAU,
        )
        if self.indeterminate:
            turn = self.animated(
                "spin", 1.0, duration=INDETERMINATE_CYCLE, curve="linear", repeat=True
            )
            start, sweep = TAU * turn, TAU * self.INDETERMINATE_SWEEP
        else:
            # Same repeat=True leak as LinearProgress -- see its paint_self.
            running = self.animation("spin")
            if running is not None:
                self.ticker.discard(running)
            start, sweep = 0.0, TAU * self.progress
        if sweep > 0.0:
            _arc(
                ctx,
                x,
                y,
                side,
                side,
                token=content_token(ctx, style, "primary"),
                thickness=thickness,
                start=start,
                sweep=sweep,
            )
