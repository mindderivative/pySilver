"""Dock's runtime half: dragging a tab out of one `DockGroup` and dropping
it as a new tab in another, or onto an edge to split that area and create
a new pane. `dock.py`'s own module docstring used to call this "a separate,
substantially larger feature... deliberately not part of this pass" --
this module is that pass, kept separate from `dock.py` because the drag
controller needs cross-element knowledge (source, target, zone classifier,
tree splicer, overlay ghost) that is a distinct concern from either
element's own static rendering, the same way `tree/reconcile.py` is a
free-function module operating on elements rather than a method on one.

**Gesture.** `DockGroupElement.on_pointer_down` (inside its own tab strip)
stashes the pressed tab's name; `on_pointer_move` compares distance moved
against `DRAG_THRESHOLD` before calling this module's `begin_drag`. Past
that point every move calls `update_drag` (recompute the live drop target
via `element.dispatcher.hit_path` -- independent of pointer capture, the
only way to know what is under the cursor while capture routes every event
to the drag's own source element and nowhere else -- and move the ghost),
and `on_pointer_up` calls `end_drag` (perform the drop, or do nothing if
there was no valid target).

**Tree mutation never disposes a moved subtree.** `remove_child`/
`insert_child` (`layout/node.py`) never call `dispose()` -- a `DockPanel`
holding a live `Terminal` (a running shell process) survives a move
untouched, which is why this is written directly against those two
primitives rather than through `tree/reconcile.py`'s spec-diffing (which
has no cross-parent matching at all, and would tear down and rebuild
anything that moved between parents).

**Scope, stated the same way `dock.py`'s own docstring discloses deferred
work**: only mouse drag (no keyboard-driven rearrange), only cross-group
moves and edge-splits (no reordering tabs within one group, no
multi-panel drag), no floating/undocked windows, and no layout
serialization across reloads -- a runtime rearrangement is pure in-memory
tree state and is lost the moment a view file is hot-reloaded and
`reconcile()` rebuilds from the parsed spec. `on_rearrange` exists so an
application *can* persist a rearrangement if it wants to, not because
pySilver does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, Literal

from ..runtime.events import ChangeEvent, EventType
from ..spec import SizeSpec, StyleSpec, WidgetKind, WidgetSpec

if TYPE_CHECKING:
    from .dock import DockGroupElement, DockPanelElement

__all__ = ["DRAG_THRESHOLD", "begin_drag", "cancel_drag", "end_drag", "update_drag"]

#: Not sourced -- no drag-threshold precedent exists anywhere else in this
#: codebase -- chosen to distinguish an intentional drag from click jitter.
DRAG_THRESHOLD: Final = 8.0

Zone = Literal["tab", "left", "right", "bottom"]

#: Fraction of a target's content-area height, measured from the bottom,
#: that means "split vertically" regardless of horizontal position -- phil's
#: own spec: "If I am on the lower 1/3 of the area I want it split
#: vertically, if I am on the left or right in between the tab strip and
#: the lower drop zone it splits horizontally." No "top" zone at all --
#: deliberately not a symmetric four-way design.
BOTTOM_BAND: Final = 1.0 / 3.0

#: The ghost's own fixed size -- a label-sized rectangle, not a live
#: re-render of the dragged panel's content (which could be a Terminal or
#: anything else expensive/stateful to duplicate mid-drag).
_GHOST_SIZE: Final = (140.0, 32.0)


def _classify(local_x: float, local_y: float, width: float, height: float) -> Zone:
    """Which split zone of a `width` x `height` rect a point falls in.

    Found live, twice: the original design centered a "tab" zone here too
    (a 25%-75% band on both axes), which put the real content area mostly
    into thin, hard-to-hit split margins that did not match the highlight;
    replacing that with a symmetric four-way diagonal cross was still not
    right -- phil: "Adding drop space below the tabs visual area makes it
    confusing" about a reachable "top" zone that doubled up with the tab
    strip's own "insert as a tab" meaning. Tab insertion is handled
    entirely by the caller's own tab-strip check before this ever runs
    (`find_drop_target`), so every point here is a split, and there is no
    "top" case at all: the bottom `BOTTOM_BAND` fraction always means
    "split vertically"; everything above that, left or right of center,
    means "split horizontally" on that side.
    """
    fy = local_y / height if height > 0 else 0.5
    if fy >= 1.0 - BOTTOM_BAND:
        return "bottom"
    fx = local_x / width if width > 0 else 0.5
    return "left" if fx < 0.5 else "right"


def find_drop_target(source: Any, x: float, y: float) -> tuple[Any, Zone] | None:
    """The nearest `DockGroup`/`DockSplit` under `(x, y)`, and which zone of
    it, or `None` if nothing dock-shaped is there. `source` (the dragging
    element) is excluded so dragging back over your own tab strip is never
    a valid target.
    """
    from .dock import DockGroupElement, DockSplitElement

    dispatcher = source.dispatcher
    if dispatcher is None:
        return None
    # `hit_path`/`hit_test` returns deepest-first, root-last (`element.py`'s
    # own `hit_test`: `return [*found, self]`, the recursive call's result
    # ahead of the current, shallower element). Found live: this used to
    # iterate `reversed(path)`, walking root-to-leaf instead -- which, for
    # any layout with a nested DockSplit, picked an ANCESTOR split instead
    # of the specific group actually under the cursor, and that split
    # sometimes already had two children by the time `_drop_as_tab` called
    # `insert_child` on it, crashing (`ValueError: DockSplit takes exactly
    # two children`) after the dragged panel had already been removed from
    # its source -- silently orphaning it, since `rendercanvas` logs a
    # per-frame draw exception rather than propagating it.
    path = dispatcher.hit_path(x, y)
    target = None
    for element in path:
        if element is source:
            continue
        if isinstance(element, DockGroupElement | DockSplitElement):
            target = element
            break
    if target is None:
        return None
    # A DockSplit's own two children fill it entirely except the divider --
    # recurse one more hit_path step to classify against whichever child is
    # actually under the cursor, not the split's own (usually much larger)
    # bounds.
    if isinstance(target, DockSplitElement):
        for element in path:
            if element is target or element is source:
                continue
            is_dock = isinstance(element, DockGroupElement | DockSplitElement)
            if is_dock and element in target.children:
                target = element
                break
        else:
            return None
    rect = target.absolute_rect()
    local_y = y - rect.y
    # Found live: dropping directly onto another group's own tab strip --
    # the intuitive, standard way to add a tab next to existing ones in
    # every real docking IDE -- fell into the generic center/edge fraction
    # test below, which treats the whole rect uniformly and puts most of a
    # (usually short, TAB_HEIGHT-tall) tab strip inside the "top edge"
    # split zone rather than "tab" insert. The tab strip always means
    # "insert as a tab" regardless of horizontal position within it.
    if isinstance(target, DockGroupElement) and 0.0 <= local_y <= target.TAB_HEIGHT:
        return target, "tab"
    zone = _classify(x - rect.x, local_y, rect.width, rect.height)
    return target, zone


def _build_ghost(label: str) -> Any:
    from .registry import build_element

    width, height = _GHOST_SIZE
    spec = WidgetSpec(
        widget=WidgetKind.CONTAINER,
        style=StyleSpec(
            placement="pointer",
            background="primary",
            corner_radius=(6.0, 6.0, 6.0, 6.0),
            width=SizeSpec("fixed", width),
            height=SizeSpec("fixed", height),
        ),
    )
    return build_element(spec)


#: The single element currently showing a drop-zone indicator, tracked
#: globally rather than per-source-group -- see `_set_highlight`. There is
#: only ever one drag in flight at a time in a real app, so a module-level
#: reference is the simplest thing that is also correct.
_highlighted: Any | None = None


def _set_highlight(element: Any, zone: Zone) -> None:
    """Highlight `element`, first clearing whatever else was previously
    highlighted -- guarantees exactly one element is ever highlighted
    app-wide.

    Found live: clearing scoped to "whatever `source.state.data
    ['drag_target']` was last time", one attribute per drag-initiating
    group, could leave a highlight stuck on an element if that
    bookkeeping ever fell even slightly out of step with the highlight it
    was meant to track -- phil: seeing a highlight "mostly on the tab
    strip" while hovering somewhere else entirely. A single, global
    "whatever is highlighted right now" reference cannot drift out of
    sync with itself the way two separate pieces of per-source state can.
    """
    global _highlighted
    if _highlighted is not None and _highlighted is not element:
        _highlighted.state.data.pop("drag_highlight", None)
        _highlighted.mark_needs_paint()
    element.state.data["drag_highlight"] = zone
    element.mark_needs_paint()
    _highlighted = element


def _clear_highlight() -> None:
    global _highlighted
    if _highlighted is not None:
        _highlighted.state.data.pop("drag_highlight", None)
        _highlighted.mark_needs_paint()
        _highlighted = None


def begin_drag(source: DockGroupElement, panel_name: str, x: float, y: float) -> None:
    """Start dragging `panel_name` out of `source`. Pushes a floating ghost
    into the overlay layer, positioned by the same `"pointer"` placement
    every other overlay uses."""
    source.state.data["drag_panel"] = panel_name
    source.state.data["drag_target"] = None
    source.state.data["drag_zone"] = None
    _clear_highlight()  # a stray highlight from any earlier drag must not survive into this one
    if source.dispatcher is not None:
        ghost = _build_ghost(panel_name)
        entry = source.dispatcher.overlays.push_transient(ghost)
        source.state.data["drag_ghost_entry"] = entry
    update_drag(source, x, y)


def update_drag(source: DockGroupElement, x: float, y: float) -> None:
    """Recompute the live drop target and move the ghost. Called on every
    pointer move once a drag has started."""
    found = find_drop_target(source, x, y)
    if found is not None:
        target, zone = found
        _set_highlight(target, zone)
        source.state.data["drag_target"] = target
        source.state.data["drag_zone"] = zone
    else:
        _clear_highlight()
        source.state.data["drag_target"] = None
        source.state.data["drag_zone"] = None
    entry = source.state.data.get("drag_ghost_entry")
    if entry is not None:
        entry.element.drag_offset = _pointer_offset(x, y)


def _pointer_offset(x: float, y: float) -> Any:
    """Where the ghost sits relative to the cursor.

    `OverlayHost._place`'s own `"pointer"` placement adds this to a base
    position from `pointer_anchor` -- which is only ever updated on a
    right-click/context-menu request (`events.py`, the `POINTER_DOWN` +
    secondary-button branch), never on an ordinary drag's moves. It stays
    `OFFSET_ZERO` throughout a whole drag, so this offset alone carries the
    real cursor position (`_at_pointer`'s own contribution clamps to a
    small, near-zero margin from that stale zero).

    Found live: offsetting down-right of the cursor (this used to be
    `Offset(x + 12, y + 12)`) put the ghost directly on top of the
    `"bottom"` zone's own indicator line whenever the cursor was actually
    in the bottom zone -- reaching that zone means the cursor is already
    near the target's bottom edge, so pushing the ghost further down
    pushed it onto the very line meant to be visible there. Above the
    cursor, centered, stays clear of all four zone indicators in the
    ordinary case instead.
    """
    from ..layout import Offset

    width, height = _GHOST_SIZE
    return Offset(x - width / 2.0, y - height - 16.0)


def end_drag(source: DockGroupElement) -> None:
    """Finish the drag: perform the drop if there is a valid target, then
    clear all drag state regardless."""
    from .dock import DockGroupElement as _Group
    from .dock import DockSplitElement as _Split

    panel_name = source.state.data.get("drag_panel")
    target = source.state.data.get("drag_target")
    zone = source.state.data.get("drag_zone")
    if panel_name is not None and target is not None and zone is not None:
        panel = next((c for c in source.children if c.name == panel_name), None)
        # Defense in depth against `find_drop_target` ever again resolving
        # to the wrong element (it did, live, before the hit_path ordering
        # fix above): only ever remove `panel` from `source` once the drop
        # path is confirmed valid for the zone it claims, so a bad target
        # is a silent no-op rather than orphaning the dragged panel.
        if panel is not None:
            if zone == "tab" and isinstance(target, _Group):
                _drop_as_tab(source, panel, target)
            elif zone != "tab" and isinstance(target, _Group | _Split):
                _drop_as_split(source, panel, target, zone)
    _clear_highlight()
    # Set *before* cancel_drag clears "dragging" -- kept as its own
    # one-shot flag, separate from "dragging" itself, because
    # DockGroupElement.on_click needs to see "a drag just ended" AFTER
    # on_pointer_up has already run cancel_drag (dispatch order:
    # POINTER_UP is handled, then, only if press and release shared the
    # same element, a synthesized CLICK follows -- events.py:422-430).
    # "dragging" itself is gone by then; this flag is what on_click
    # actually reads.
    source.state.data["just_dragged"] = True
    cancel_drag(source)


def cancel_drag(source: DockGroupElement) -> None:
    """Clear all drag state without performing a drop -- also the cleanup
    path `end_drag` shares once it has done its own work.

    **Must clear `"dragging"` itself.** Found live: it wasn't, and the
    synthesized CLICK that follows POINTER_UP -- the only *other* place
    that cleared it -- only ever fires when the release lands back on the
    same element as the press (`EventDispatcher._dispatch_pointer`,
    `events.py:422-430`, comparing a fresh `hit_path` at the release point
    against the press's own path). A genuine cross-group drop releases
    over a *different* element, so that CLICK never fires at all for the
    success case this whole feature exists for -- leaving `"dragging"`
    stuck `True` on the source group forever, which made every later
    press-and-move on it skip the threshold check entirely and immediately
    resume "drag update" mode, and left its ghost never cleared the one
    time a real drop's own `cancel_drag` call still ran before this fix.
    """
    entry = source.state.data.pop("drag_ghost_entry", None)
    if entry is not None and source.dispatcher is not None:
        source.dispatcher.overlays.clear_transient()
    source.state.data.pop("drag_panel", None)
    source.state.data.pop("drag_target", None)
    source.state.data.pop("drag_zone", None)
    source.state.data.pop("dragging", None)


def _fire_rearrange(element: Any, kind: str, panel_name: str) -> None:
    handler = element.handlers.get("on_rearrange")
    if handler is not None:
        handler(ChangeEvent(EventType.CHANGE, target=element, value=f"{kind}:{panel_name}"))


def _drop_as_tab(
    source: DockGroupElement, panel: DockPanelElement, target: DockGroupElement
) -> None:
    source.remove_child(panel)
    target.insert_child(len(target.children), panel)
    target._value = panel.name or ""
    _wire_new_subtree(target, panel)
    collapse_if_empty(source)
    _fire_rearrange(target, "tab", panel.name or "")


def _drop_as_split(
    source: DockGroupElement, panel: DockPanelElement, target: Any, zone: Zone
) -> None:
    from .dock import DockGroupElement as _Group
    from .registry import build_element

    parent = target.parent
    if parent is None:
        return
    index = parent.children.index(target)
    horizontal = zone in ("left", "right")
    new_split_spec = WidgetSpec(
        widget=WidgetKind.DOCK_SPLIT,
        style=StyleSpec(axis="horizontal" if horizontal else "vertical"),
    )
    new_group_spec = WidgetSpec(widget=WidgetKind.DOCK_GROUP)
    new_split = build_element(new_split_spec)
    new_group = build_element(new_group_spec)
    assert isinstance(new_group, _Group)

    parent.remove_child(target)
    source.remove_child(panel)
    new_group.insert_child(0, panel)
    new_group._value = panel.name or ""

    # "left": new pane first (left); "right"/"bottom": existing content
    # first, new pane second (right/below). "top" was removed as a
    # reachable zone entirely (see _classify) -- this used to still
    # mention it here as dead code in the condition, correct by accident
    # only because "right" and "bottom" both want the same (target, new)
    # order the old catch-all `else` happened to produce.
    first, second = (new_group, target) if zone == "left" else (target, new_group)
    new_split.insert_child(0, first)
    new_split.insert_child(1, second)
    parent.insert_child(index, new_split)

    _wire_new_subtree(source, new_split)
    collapse_if_empty(source)
    _fire_rearrange(new_split, "split", panel.name or "")


def _wire_new_subtree(reference: Any, subtree: Any) -> None:
    """Wire a subtree built after initial mount the same way `PageHost`
    already wires a page it constructs later (`widgets/pagehost.py`) --
    ticker/text_engine/image_atlas/dispatcher propagated from an already-live
    sibling, then `mounter()` to resolve `{{ }}` bindings and `handlers:`
    the same way `App.mount()` would have for anything present at mount
    time. `subtree` may be a pre-existing moved element (already wired --
    these calls are idempotent, just re-propagating the same values) or a
    genuinely new wrapper -- either way this is correct and cheap.
    """
    subtree.set_ticker(reference.ticker)
    subtree.set_text_engine(reference.text_engine)
    subtree.set_image_atlas(reference.image_atlas)
    if reference.dispatcher is not None:
        subtree.set_dispatcher(reference.dispatcher)
    reference.mounter(subtree)


#: Not sourced -- there is no M3 page for this. A full-fill translucent
#: tint (this file's original design) did not read clearly against the
#: zone it was over -- phil: "Instead of full fill highlight, I want a
#: thick clear line... The colors of the line should all be the same as
#: the accent color." One line, one token (`primary`, this codebase's own
#: accent role), at every zone -- never a per-zone color. Started at 4px;
#: phil asked for 2px once the paint-order/tab-strip-bleed bugs were fixed
#: and the line was actually visible in full.
LINE_THICKNESS: Final = 2.0


def paint_drop_zone(
    ctx: Any,
    x: float,
    y: float,
    width: float,
    height: float,
    zone: Zone,
    *,
    tab_height: float = 0.0,
) -> None:
    """Paint the current drop-zone indicator -- called from both
    `DockGroupElement.paint_self` (passing its own `TAB_HEIGHT`) and
    `DockSplitElement.paint_self` (which never sees zone `"tab"` at all, so
    its default `tab_height=0.0` is never read), reading
    `self.state.data["drag_highlight"]`. A single `LINE_THICKNESS`-wide
    border in the `primary` token, always at an actual edge of the target
    -- never a filled region, an internal zone-boundary line, or a
    per-zone color. phil's own exact spec: "make the bottom border of the
    panel the accent color and 4px [zone 4]... make the left border [zone
    2]... make the right border [zone 3]... the tab strip bottom border
    [zone 1]." Found live: `"bottom"` used to draw at the `BOTTOM_BAND`
    zone *threshold* (2/3 down) rather than the panel's actual bottom
    edge, the one case that was not a true border -- inconsistent with the
    other three, and part of why it was hard to see.

    `"left"`/`"right"` span only the *content* area, from `tab_height`
    down -- not the full `(x, y, width, height)` passed in, which is the
    whole `DockGroup` including its tab strip. Found live: phil noticed
    the tab strip itself lighting up while hovering zones 2/3 -- because
    the group's own tab strip sits inside that same rect, at its very
    top, a left/right line spanning the full height necessarily runs
    along the tab strip's own left/right edge too, reading as "the tab
    strip is highlighted" even though it was really one continuous line
    that happened to pass behind it.
    """
    dpr = ctx.pixel_ratio
    t = LINE_THICKNESS
    content_y = y + tab_height
    content_h = height - tab_height
    match zone:
        case "tab":
            lx, ly, lw, lh = x, y + tab_height - t, width, t
        case "left":
            lx, ly, lw, lh = x, content_y, t, content_h
        case "right":
            lx, ly, lw, lh = x + width - t, content_y, t, content_h
        case "bottom":
            lx, ly, lw, lh = x, y + height - t, width, t
    ctx.display_list.add_box(
        lx * dpr,
        ly * dpr,
        lw * dpr,
        lh * dpr,
        token=ctx.palette.index("primary"),
        color=(1.0, 1.0, 1.0, 1.0),
        clip=ctx.clip,
        clip_radii=ctx.clip_radii,
    )


def collapse_if_empty(group: DockGroupElement) -> None:
    """If `group` lost its last panel, it is no longer valid on its own.

    Its parent is either a `DockSplit` (the common case, by construction --
    collapse it, promoting the surviving sibling into the split's own old
    slot), the tree root (leave it empty, already tolerated --
    `_active_name()` already returns `None` for zero children), or some
    other container a view file legally wrapped it in (leave it empty too
    -- an accepted edge-case limit, not a crash).
    """
    from .dock import DockSplitElement

    if group.children:
        return
    parent = group.parent
    if parent is None or not isinstance(parent, DockSplitElement):
        return
    siblings = [c for c in parent.children if c is not group]
    if len(siblings) != 1:
        return
    survivor = siblings[0]
    grandparent = parent.parent
    if grandparent is None:
        return
    index = grandparent.children.index(parent)
    grandparent.remove_child(parent)
    parent.remove_child(survivor)
    grandparent.insert_child(index, survivor)
