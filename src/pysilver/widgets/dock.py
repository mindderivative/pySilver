"""A dockable panel layout: resizable splits and tabbed groups.

M3 has nothing for this -- checked directly, the same way every other
ungrounded widget this session was. Three widgets, composed the way a real
IDE's layout is:

* `DockPanel` -- one pane. `text:` is its tab label, its single child is its
  content.
* `DockGroup` -- a tabbed stack of `DockPanel`s. Exactly one is visible at a
  time; `value:` names it by `name`, clicking a tab switches it and fires
  `on_change` the same way every other value-bearing widget in this codebase
  does the switch itself and tells the application afterward.
* `DockSplit` -- exactly two children (either can itself be a `DockGroup` or
  a further `DockSplit`, which is how a layout nests) separated by a
  draggable divider. `value:` is the first child's share of the space,
  0..1; dragging the divider updates it and fires `on_change`.

**Runtime drag-and-drop** -- dragging a tab out of one `DockGroup` and
dropping it as a new tab in another, or onto an edge to split that area
and create a new pane -- is implemented in `dock_drag.py`, kept separate
from this file's own static layout/paint/tab-switch/divider-drag code;
see that module's own docstring for the design. A layout is still arranged
once in the view file the way a `Horizontal`/`Vertical`/`Stack` tree is,
but it is no longer fixed for the widget's lifetime.
"""

from __future__ import annotations

from typing import Any, Final

from ..layout import Constraints, EdgeInsets, LayoutNode, Offset, Padding, Size
from ..runtime.events import ChangeEvent, EventType
from ..spec import WidgetSpec
from ..spec.typescale import TYPE_SCALE
from ..tree.element import PaintContext
from . import dock_drag
from .base import _StyledMixin, content_token, measure_text, paint_text
from .material import HOVER, STATE_LAYER_CURVE, STATE_LAYER_MOTION, _box, _state_alpha
from .navigation import INDICATOR_CURVE, INDICATOR_MOTION

__all__ = ["DockGroupElement", "DockPanelElement", "DockSplitElement"]

#: A dock tab's label role. Not sourced -- there is no M3 page for this --
#: reused from `Tabs`' own established anatomy rather than invented fresh,
#: since a dock group's tab strip is functionally the same idea.
TAB_LABEL: Final = TYPE_SCALE["title-small"]


class DockPanelElement(_StyledMixin, Padding):
    """One pane inside a `DockGroup`. `text:` is its tab label.

    A transparent single-child wrapper -- the enclosing `DockGroup` decides
    how much space it gets each frame (its full share when it is the active
    tab, zero otherwise) and marks it `selected` accordingly.

    **Zero size alone does not hide content.** Painting always emits full
    geometry regardless of the parent's clip -- the same fact `Accordion`
    and `TreeItem` already establish -- so an inactive panel's own children
    can still paint at whatever size *they* naturally want, positioned right
    on top of the active panel's content. This was caught by actually
    rendering a group with real content in both tabs and seeing the inactive
    one bleed through, not by reasoning about the layout numbers alone.

    The fix needed a second look even after the clip rect itself was right:
    the shader only *applies* a clip when both its width and height are
    strictly greater than zero (`ui.wgsl`, "a zero-size clip rect means
    unclipped") -- so a literal zero-height rect, which reads as correct
    from the Python side, is silently treated as *no clip at all* by the
    thing that actually draws pixels. Confirmed by rendering a real frame
    and finding the "hidden" content still on screen despite the display
    list carrying what looked like the right clip. The working version uses
    `HIDDEN_EXTENT` -- a real but sub-pixel size -- instead of exactly zero,
    which satisfies the shader's own `> 0.0` test while leaving nothing
    large enough for any fragment to land inside.
    """

    CLIPS_CHILDREN = True

    #: Real, but far below one physical pixel -- passes the shader's own
    #: `clip.z/w > 0.0` gate (`ui.wgsl`) without leaving any rasterisable
    #: area, unlike an exact zero, which that same gate reads as "no clip".
    HIDDEN_EXTENT: Final = 0.01

    def __init__(self, spec: WidgetSpec) -> None:
        Padding.__init__(self, None, EdgeInsets())
        self.init_element(spec)

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        child = self.child
        if child is None:
            return outer.constrain(constraints.smallest)
        size = child.layout(outer)
        child.offset = Offset(0.0, 0.0)
        return outer.constrain(size)

    def child_paint_context(self, ctx: PaintContext, absolute: Any) -> PaintContext:
        if self.selected:
            return ctx
        dpr = ctx.pixel_ratio
        return PaintContext(
            display_list=ctx.display_list,
            palette=ctx.palette,
            text=ctx.text,
            images=ctx.images,
            pixel_ratio=dpr,
            clip=(absolute.x * dpr, absolute.y * dpr, self.HIDDEN_EXTENT, self.HIDDEN_EXTENT),
            clip_radii=ctx.clip_radii,
        )


class DockGroupElement(_StyledMixin, LayoutNode):
    """A tabbed stack of `DockPanel`s: exactly one visible at a time.

    Reuses `Tabs`' own anatomy for the strip (48dp, 3dp bottom indicator,
    `primary` selected / `on_surface_variant` unselected) since a dock
    group's tabs are the same idea with no M3 page of their own to cite
    instead. Unlike `Tabs` -- which is only ever the strip, with the
    application swapping content elsewhere -- this widget also owns the
    content switch itself, since a dock layout has nowhere else for it to
    live.

    `value:` names the active panel by `name`; an unset or unmatched value
    falls back to the first panel rather than showing nothing. Hover is
    tracked and animated per tab (`state.data["tab_hover"]` plus one
    `animated()` key per panel name) -- safe here, unlike `Pagination`'s
    equivalent choice not to, because a dock group's set of tabs is small
    and fixed for the widget's lifetime, not unbounded.
    """

    TAB_HEIGHT: Final = 48.0
    INDICATOR_H: Final = 3.0
    #: "Primary tab active indicators are inset 2dp on each side"
    #: (`COMPONENT_TABS.md`) -- see `TabsElement.PRIMARY_INSET`.
    PRIMARY_INSET: Final = 2.0
    PAD_X: Final = 16.0

    def __init__(self, spec: WidgetSpec) -> None:
        LayoutNode.__init__(self)
        self.init_element(spec)

    def _active_name(self) -> str | None:
        want = self._value.strip()
        names = [c.name for c in self.children if c.name]
        if want in names:
            return want
        return names[0] if names else None

    def _tab_rects(self) -> list[tuple[str, float, float]]:
        rects: list[tuple[str, float, float]] = []
        x = 0.0
        for child in self.children:
            name = child.name
            if not name:
                continue
            label_text = child.text.strip() or name
            label = measure_text(label_text, TAB_LABEL, engine=self.text_engine)
            width = label.width + 2 * self.PAD_X
            rects.append((name, x, width))
            x += width
        return rects

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else 320.0
        height = outer.max_height if outer.has_bounded_height else self.TAB_HEIGHT
        content_h = max(0.0, height - self.TAB_HEIGHT)
        active = self._active_name()
        for child in self.children:
            is_active = child.name is not None and child.name == active
            child.set_selected(is_active)
            size = Size(width, content_h) if is_active else Size(0.0, 0.0)
            child.layout(Constraints.tight(size))
            child.offset = Offset(0.0, self.TAB_HEIGHT)
        return outer.constrain(Size(width, height))

    # ------------------------------------------------------------- pointer

    def _tab_at(self, x: float) -> str | None:
        local = x - self.absolute_rect().x
        for name, tx, tw in self._tab_rects():
            if tx <= local < tx + tw:
                return name
        return None

    def on_click(self, event: Any) -> None:
        if self.effective_disabled:
            return
        if self.state.data.pop("just_dragged", False):
            # A drag that ended with a drop -- or with no valid target --
            # must not also switch the active tab, which the synthesized
            # CLICK following POINTER_UP would otherwise do when press and
            # release land on the same element (only case a CLICK is even
            # synthesized after a drag). A one-shot flag, deliberately
            # separate from "dragging" itself -- `cancel_drag` (called from
            # `on_pointer_up`, which always runs before this) already
            # clears "dragging" by the time a synthesized CLICK could ever
            # reach here, so checking that instead would never fire. See
            # `dock_drag.end_drag`.
            return
        rect = self.absolute_rect()
        if event.y - rect.y > self.TAB_HEIGHT:
            return
        name = self._tab_at(event.x)
        if name is None or name == self._active_name():
            return
        self._value = name
        handler = self.handlers.get("on_change")
        if handler is not None:
            handler(ChangeEvent(EventType.CHANGE, target=self, value=name))
        self.mark_needs_layout()

    def on_pointer_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        rect = self.absolute_rect()
        if event.y - rect.y > self.TAB_HEIGHT:
            return
        name = self._tab_at(event.x)
        if name is None:
            return
        self.state.data["press_tab"] = name
        self.state.data["press_pos"] = (event.x, event.y)

    def on_pointer_move(self, event: Any) -> None:
        press_tab = self.state.data.get("press_tab")
        if press_tab is not None:
            if self.state.data.get("dragging"):
                dock_drag.update_drag(self, event.x, event.y)
                return
            px, py = self.state.data["press_pos"]
            if ((event.x - px) ** 2 + (event.y - py) ** 2) ** 0.5 >= dock_drag.DRAG_THRESHOLD:
                self.state.data["dragging"] = True
                dock_drag.begin_drag(self, press_tab, event.x, event.y)
            return
        rect = self.absolute_rect()
        name = self._tab_at(event.x) if event.y - rect.y <= self.TAB_HEIGHT else None
        if self.state.data.get("tab_hover") != name:
            self.state.data["tab_hover"] = name
            self.mark_needs_paint()

    def on_pointer_up(self, event: Any) -> None:
        self.state.data.pop("press_tab", None)
        self.state.data.pop("press_pos", None)
        if self.state.data.get("dragging"):
            dock_drag.end_drag(self)

    def on_pointer_leave(self, event: Any) -> None:
        if self.state.data.get("tab_hover") is not None:
            self.state.data["tab_hover"] = None
            self.mark_needs_paint()

    # --------------------------------------------------------------- paint

    def _tab_alpha(self, name: str) -> float:
        target = HOVER if self.state.data.get("tab_hover") == name else 0.0
        return self.animated(
            f"tab_hover_{name}", target, duration=STATE_LAYER_MOTION, curve=STATE_LAYER_CURVE
        )

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        style = self.style
        dpr = ctx.pixel_ratio
        _box(
            ctx,
            absolute.x,
            absolute.y,
            self.size.width,
            self.TAB_HEIGHT,
            token=ctx.palette.index(style.background or "surface_container"),
            radius=0.0,
        )
        active = self._active_name()
        by_name = {c.name: c for c in self.children if c.name}
        active_rect: tuple[float, float] | None = None
        for name, x, width in self._tab_rects():
            alpha = self._tab_alpha(name)
            if alpha > 0.001:
                ctx.display_list.add_box(
                    (absolute.x + x) * dpr,
                    absolute.y * dpr,
                    width * dpr,
                    self.TAB_HEIGHT * dpr,
                    token=ctx.palette.index("on_surface"),
                    color=(1.0, 1.0, 1.0, alpha),
                    clip=ctx.clip,
                    clip_radii=ctx.clip_radii,
                )
            selected = name == active
            token = content_token(ctx, style, "primary" if selected else "on_surface_variant")
            child = by_name.get(name)
            label_text = (child.text.strip() if child is not None else "") or name
            label = measure_text(label_text, TAB_LABEL, engine=self.text_engine)
            paint_text(
                ctx,
                absolute.x + x + self.PAD_X,
                absolute.y + (self.TAB_HEIGHT - label.height) / 2,
                label_text,
                TAB_LABEL,
                token,
            )
            if selected:
                active_rect = (x, width)
        if active_rect is not None:
            # The indicator belongs to the group, not to any one tab, which
            # is what lets it travel between them -- the same pattern (and
            # the same reasoning) `TabsElement.paint_self` already
            # establishes: both edges animate, so it stretches and settles
            # rather than jumping. Found live: this used to be drawn
            # per-tab, instantly, inside the loop above -- a real gap, not a
            # regression (`dock.py` never had this animation; only its
            # static anatomy -- inset, rounding -- was ever "reused" from
            # `Tabs`), but phil expected the same travelling-indicator feel
            # `Tabs` has, since this widget's own docstring already claims
            # to reuse its anatomy.
            tab_x, tab_w = active_rect
            # Primary Tabs anatomy, inset 2dp a side with a fully rounded
            # corner radius -- COMPONENT_TABS.md's own measurements.
            ix = self.animated(
                "indicator_x",
                tab_x + self.PRIMARY_INSET,
                duration=INDICATOR_MOTION,
                curve=INDICATOR_CURVE,
            )
            iw = self.animated(
                "indicator_w",
                tab_w - 2.0 * self.PRIMARY_INSET,
                duration=INDICATOR_MOTION,
                curve=INDICATOR_CURVE,
            )
            _box(
                ctx,
                absolute.x + ix,
                absolute.y + self.TAB_HEIGHT - self.INDICATOR_H,
                iw,
                self.INDICATOR_H,
                token=ctx.palette.index("primary"),
                radius=self.INDICATOR_H,
            )

    def paint_foreground(self, ctx: PaintContext, absolute: Any) -> None:
        # Found live: painting the drop-zone highlight from `paint_self`
        # (as the rest of this class's own chrome does) put it BEHIND the
        # active `DockPanel` child's own content, which paints after and
        # covers the group's full content area -- phil saw the left/right
        # lines as "cutoff a little by the edges" when really only the
        # thin seam right at the tab strip, painted before the panel's
        # content began, was ever surviving underneath it. `paint_foreground`
        # runs after every child, the same hook `ScrollView`'s thumb already
        # uses to stay visible over scrolled-under content.
        zone = self.state.data.get("drag_highlight")
        if zone is not None:
            dock_drag.paint_drop_zone(
                ctx,
                absolute.x,
                absolute.y,
                self.size.width,
                self.size.height,
                zone,
                tab_height=self.TAB_HEIGHT,
            )


class DockSplitElement(_StyledMixin, LayoutNode):
    """Exactly two children, side by side or stacked, separated by a
    draggable divider.

    `style.axis` is `horizontal` (default, side by side) or `vertical`
    (stacked) -- the same field `ScrollView` already uses for its own axis,
    reused rather than adding a second one that means the same thing.
    `value:` is the *first* child's share of the space, 0..1, defaulting to
    0.5 when unset. Dragging the divider updates it live and fires
    `on_change` with the new ratio already computed, matching `SpinBox` and
    `Pagination`'s own split between updating the display and telling the
    application what changed.

    A `DockSplit`'s own two children fill it entirely except for a 4dp
    divider strip that no child covers, so the framework's own hit-testing
    already isolates hover/press to exactly that strip -- unlike `SpinBox`
    or `Pagination`, which each have several regions inside one element, a
    `DockSplit` needs no per-region state of its own, and its `_state_alpha`
    reuse is the ordinary, whole-element one every other component uses.
    """

    DIVIDER: Final = 4.0
    #: Neither pane is allowed to shrink to nothing under a drag or an
    #: extreme ratio. Not sourced -- there is no spec for this widget at
    #: all -- chosen to keep a pane usable rather than a sliver.
    MIN_PANE: Final = 48.0

    def __init__(self, spec: WidgetSpec) -> None:
        LayoutNode.__init__(self)
        self.init_element(spec)
        self._divider_main = 0.0

    def insert_child(self, index: int, child: LayoutNode) -> None:
        if len(self._children) >= 2:
            raise ValueError(
                "DockSplit takes exactly two children; nest another DockSplit for a third pane"
            )
        super().insert_child(index, child)

    @property
    def horizontal(self) -> bool:
        """Side by side unless `axis: vertical` is explicit.

        `axis` is shared with `ScrollView`, whose own sensible default is
        `vertical` -- so its bare field default cannot also mean "horizontal"
        for this widget without checking `model_fields_set` to tell "the
        view actually wrote `vertical`" apart from "nobody set anything".
        """
        if "axis" in self.style.model_fields_set:
            return self.style.axis != "vertical"
        return True

    def _ratio(self) -> float:
        raw = self._value.strip()
        if not raw:
            return 0.5
        try:
            return min(1.0, max(0.0, float(raw)))
        except ValueError:
            return 0.5

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else 0.0
        height = outer.max_height if outer.has_bounded_height else 0.0
        horizontal = self.horizontal
        main = width if horizontal else height
        cross = height if horizontal else width
        available = max(0.0, main - self.DIVIDER)

        first_main = available * self._ratio()
        if available >= 2 * self.MIN_PANE:
            first_main = min(max(self.MIN_PANE, first_main), available - self.MIN_PANE)
        self._divider_main = first_main
        second_main = max(0.0, available - first_main)

        if len(self._children) >= 1:
            size0 = Size(first_main, cross) if horizontal else Size(cross, first_main)
            self._children[0].layout(Constraints.tight(size0))
            self._children[0].offset = Offset(0.0, 0.0)
        if len(self._children) >= 2:
            size1 = Size(second_main, cross) if horizontal else Size(cross, second_main)
            self._children[1].layout(Constraints.tight(size1))
            past_divider = first_main + self.DIVIDER
            self._children[1].offset = (
                Offset(past_divider, 0.0) if horizontal else Offset(0.0, past_divider)
            )
        return outer.constrain(Size(width, height))

    # ------------------------------------------------------------- pointer

    def _on_divider(self, x: float, y: float) -> bool:
        rect = self.absolute_rect()
        local = (x - rect.x) if self.horizontal else (y - rect.y)
        #: A few extra px either side, the same reasoning the scrollbar
        #: thumb's own hit target already uses: a 4dp strip is unusable
        #: with a mouse otherwise.
        pad = 3.0
        return self._divider_main - pad <= local <= self._divider_main + self.DIVIDER + pad

    def cursor_at(self, x: float, y: float) -> str | None:
        if self._on_divider(x, y):
            # `rendercanvas.CursorShape` has no "col-resize"/"row-resize" --
            # those are CSS names, not this backend's. `ew-resize`/`ns-resize`
            # is the same vocabulary `ScrollView`'s own thumb cursor already
            # uses. The wrong name did not just paint a bad cursor: it raised
            # `ValueError` inside `App._sync_cursor()`, called every frame
            # from `update()`, so hovering the divider silently broke the
            # OS cursor updating at all rather than showing the wrong shape.
            return "ew-resize" if self.horizontal else "ns-resize"
        return super().cursor_at(x, y)

    def on_pointer_down(self, event: Any) -> None:
        if self.effective_disabled or not self._on_divider(event.x, event.y):
            return
        self.state.data["drag_start"] = event.x if self.horizontal else event.y
        self.state.data["drag_ratio0"] = self._ratio()
        event.capture()
        event.stop_propagation()

    def on_pointer_move(self, event: Any) -> None:
        if "drag_start" not in self.state.data:
            return
        rect = self.absolute_rect()
        main = rect.width if self.horizontal else rect.height
        available = max(1.0, main - self.DIVIDER)
        pos = event.x if self.horizontal else event.y
        delta = pos - self.state.data["drag_start"]
        new_ratio = min(1.0, max(0.0, self.state.data["drag_ratio0"] + delta / available))
        self._value = f"{new_ratio:.4f}"
        handler = self.handlers.get("on_change")
        if handler is not None:
            handler(ChangeEvent(EventType.CHANGE, target=self, value=self._value))
        self.mark_needs_layout()

    def on_pointer_up(self, event: Any) -> None:
        self.state.data.pop("drag_start", None)
        self.state.data.pop("drag_ratio0", None)

    # ---------------------------------------------------------------- keys

    #: WAI-ARIA's own Window Splitter pattern, which "separator" claims:
    #: the arrow keys along the split's axis move it by a step. Not sourced
    #: from M3 -- there is nothing to source -- but a real ARIA convention
    #: for the exact role this widget already reports.
    STEP: Final = 0.02

    def on_key_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        key = str(getattr(event, "key", "")).lower()
        forward = "right" if self.horizontal else "down"
        backward = "left" if self.horizontal else "up"
        if key == forward:
            delta = self.STEP
        elif key == backward:
            delta = -self.STEP
        else:
            return
        self._value = f"{min(1.0, max(0.0, self._ratio() + delta)):.4f}"
        handler = self.handlers.get("on_change")
        if handler is not None:
            handler(ChangeEvent(EventType.CHANGE, target=self, value=self._value))
        self.mark_needs_layout()

    # --------------------------------------------------------------- paint

    def paint_self(self, ctx: PaintContext, absolute: Any) -> None:
        dpr = ctx.pixel_ratio
        horizontal = self.horizontal
        x = absolute.x + self._divider_main if horizontal else absolute.x
        y = absolute.y if horizontal else absolute.y + self._divider_main
        w = self.DIVIDER if horizontal else self.size.width
        h = self.size.height if horizontal else self.DIVIDER
        _box(
            ctx,
            x,
            y,
            w,
            h,
            token=ctx.palette.index(self.style.background or "outline_variant"),
            radius=0.0,
        )
        alpha = _state_alpha(self)
        if alpha > 0.001:
            ctx.display_list.add_box(
                x * dpr,
                y * dpr,
                w * dpr,
                h * dpr,
                token=ctx.palette.index("on_surface"),
                color=(1.0, 1.0, 1.0, alpha),
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )

    def paint_foreground(self, ctx: PaintContext, absolute: Any) -> None:
        # Same reasoning as `DockGroupElement.paint_foreground`: this
        # split's own two children fill its full rect (bar the divider),
        # so painting the highlight from `paint_self` put it underneath
        # whichever child paints there.
        zone = self.state.data.get("drag_highlight")
        if zone is not None:
            dock_drag.paint_drop_zone(
                ctx, absolute.x, absolute.y, self.size.width, self.size.height, zone
            )
