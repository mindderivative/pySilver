"""A node-based visual editor: draggable nodes wired by declared edges.

M3 has no node-graph component -- checked directly against `M3-References`,
the same way every other ungrounded widget this session was -- so this is
designed from pySilver's own engine and layout primitives instead of a spec.

**Interactive editor, not a thin drawing surface.** `Node` is a real composed
element (its own child content, its own drag handling) rather than something
an application paints itself with `Canvas`, and panning/dragging/hit-testing
all go through the framework's existing mechanisms rather than a bespoke
region system:

* **Panning** reuses `ScrollView`'s own trick exactly: `NodeGraph.child_origin`
  returns `absolute - state.scroll`, so moving the viewport is a paint-time
  translation, not a relayout -- "hit testing threads the same origin, so the
  pointer follows the pixels" holds here unchanged. 1:1 only; there is no
  zoom (below).
* **Dragging a node** moves its own world position, tracked as *runtime
  state* the same way `DockSplit`'s divider ratio is: `StyleSpec.x`/`y` are
  only the starting point, and a reload does not reset a node an author has
  already moved.
* **No special-case region hit-testing.** A `Node`'s title bar is part of its
  own painted area, not a separate child, so a press there is a press on the
  `Node` element itself; a press lower down lands on whatever content widget
  is actually there. `Node.on_pointer_down` only *starts* a drag when the
  point falls inside its own title-bar rect (`DockSplit._on_divider`'s own
  pattern), so a click on the node's content is left alone. A press that
  misses every `Node` reaches `NodeGraph` itself, which is how panning the
  empty background needs no hit-testing of its own either.

**Zoom is deliberately out of scope for this pass.** Scaling would either
distort glyph rasterisation (thrashing the shared glyph atlas -- the same
per-frame-key trap `Icon`'s FILL axis quantisation exists to avoid) or
require re-shaping text at a new pixel size on every step, and would also
need every hit rect scaled to match. That is a real second feature, not a
checkbox on this one; panning and dragging are useful and correct without
it, so v1 stops there.

**Edges are declared, not drawn.** `WidgetSpec.edges` names a static list of
`node.port -> node.port` wires (`EdgeSpec`), resolved to two points and drawn
as segments (`DisplayList.add_segment`, the same primitive `Canvas.line`
already wraps) each frame `NodeGraph` paints. A port's position along its
node's edge is evenly spaced by its index among that side's `inputs`/
`outputs` list -- not sourced from anywhere (there is no spec to source it
from), but the ordinary node-editor convention.
"""

from __future__ import annotations

from typing import Any, Final

from ..layout import INF, Constraints, LayoutNode, Offset, Rect, SingleChildNode, Size
from ..runtime.events import ChangeEvent, EventType
from ..spec import WidgetSpec
from ..spec.typescale import TYPE_SCALE
from ..tree.element import PaintContext
from .base import _StyledMixin, content_token, measure_text, paint_text

__all__ = ["NodeElement", "NodeGraphElement"]

#: A node's title label. Not sourced -- there is no M3 page for this -- reused
#: from `DockGroup`'s own tab-label role rather than inventing a second
#: "small heading" role that means the same thing.
TITLE_LABEL: Final = TYPE_SCALE["title-small"]


def _port_offset(node: NodeElement, side: str, index: int, count: int) -> Offset:
    """A port's position relative to its own node's top-left.

    Evenly spaced down whichever edge that side draws on -- inputs on the
    left, outputs on the right. Not sourced -- there is no spec for this --
    the ordinary node-editor convention.
    """
    x = 0.0 if side == "inputs" else node.size.width
    y = (index + 1) / (count + 1) * node.size.height
    return Offset(x, y)


class NodeElement(_StyledMixin, SingleChildNode):
    """One draggable node: a title bar, named ports, and one child.

    `text:` is the title. `style.x`/`y` is only the *initial* world position
    -- see the module docstring -- and `inputs`/`outputs` name this node's
    ports, drawn evenly spaced down its left/right edge respectively.
    Dragging the title bar moves the node and fires `on_change` with its new
    `"x,y"` position once the drag ends; the arrow keys nudge it the same way
    and fire immediately, there being no separate release event for a key.
    """

    DEFAULT_WIDTH: Final = 160.0
    DEFAULT_HEIGHT: Final = 96.0
    TITLE_HEIGHT: Final = 32.0
    PORT_RADIUS: Final = 4.0
    PAD_X: Final = 12.0
    RADIUS: Final = 8.0
    #: Arrow-key nudge distance. Not sourced -- there is no spec for this
    #: widget at all -- chosen to be a visible step without being a jump.
    STEP: Final = 8.0

    def __init__(self, spec: WidgetSpec) -> None:
        SingleChildNode.__init__(self)
        self.init_element(spec)

    @property
    def effective_radii(self) -> tuple[float, float, float, float]:
        radii = self.style.corner_radius
        return radii if any(radii) else (self.RADIUS,) * 4

    # ------------------------------------------------------------ position

    @property
    def position(self) -> Offset:
        """World position: the spec's `x`/`y`, then whatever dragging set.

        Read from the spec once and stashed in `state.data` -- the same split
        `ScrollView`'s `state.scroll` makes between an author's declared value
        and the runtime's own -- so a later `configure()` (a reload with the
        same `x`/`y` still in the view file) never overwrites a position the
        user has since dragged away from it.
        """
        data = self.state.data
        if "x" not in data:
            data["x"] = self.style.x
            data["y"] = self.style.y
        return Offset(data["x"], data["y"])

    def _set_position(self, value: Offset) -> None:
        self.state.data["x"] = value.x
        self.state.data["y"] = value.y

    def _fire_change(self) -> None:
        handler = self.handlers.get("on_change")
        if handler is None:
            return
        pos = self.position
        handler(ChangeEvent(EventType.CHANGE, target=self, value=f"{pos.x:.1f},{pos.y:.1f}"))

    # --------------------------------------------------------------- layout

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        child = self.child
        if child is None:
            content = Size(0.0, max(0.0, self.DEFAULT_HEIGHT - self.TITLE_HEIGHT))
        else:
            inner = Constraints(
                min_width=0.0,
                max_width=outer.max_width if outer.has_bounded_width else INF,
                min_height=0.0,
                max_height=INF,
            )
            content = child.layout(inner)
            child.offset = Offset(0.0, self.TITLE_HEIGHT)
        width = (
            outer.max_width if outer.has_bounded_width else max(self.DEFAULT_WIDTH, content.width)
        )
        height = (
            outer.max_height if outer.has_bounded_height else self.TITLE_HEIGHT + content.height
        )
        return outer.constrain(Size(width, height))

    # ------------------------------------------------------------- pointer

    def _on_title(self, y: float) -> bool:
        return 0.0 <= y - self.absolute_rect().y <= self.TITLE_HEIGHT

    def cursor_at(self, x: float, y: float) -> str | None:
        if self._on_title(y):
            # "move"/"grab" would be the honest cursor for a draggable title
            # bar, but rendercanvas.CursorShape's vocabulary is small and has
            # neither -- confirmed the same way DockSplit's divider cursor
            # bug was: `engine.canvas.set_cursor("move")` raises `ValueError`
            # (real values: default, text, crosshair, pointer, ew-resize,
            # ns-resize, nesw-resize, nwse-resize, not-allowed, none). Every
            # frame `App._sync_cursor()` calls this while the pointer sits
            # over a title bar, so this was not a cosmetic gap -- it crashed
            # the app on hover. `pointer` is the closest available cursor
            # that still signals "interactive," which is what's meant here.
            return "pointer"
        return super().cursor_at(x, y)

    def on_pointer_down(self, event: Any) -> None:
        if self.effective_disabled or not self._on_title(event.y):
            return
        self.state.data["drag_from"] = Offset(event.x, event.y)
        self.state.data["drag_origin"] = self.position
        event.capture()
        event.stop_propagation()

    def on_pointer_move(self, event: Any) -> None:
        if "drag_from" not in self.state.data:
            return
        start = self.state.data["drag_from"]
        origin = self.state.data["drag_origin"]
        self._set_position(Offset(origin.x + (event.x - start.x), origin.y + (event.y - start.y)))
        if self.parent is not None:
            self.parent.mark_needs_layout()

    def on_pointer_up(self, event: Any) -> None:
        if "drag_from" not in self.state.data:
            return
        self.state.data.pop("drag_from", None)
        self.state.data.pop("drag_origin", None)
        self._fire_change()

    def on_key_down(self, event: Any) -> None:
        if self.effective_disabled:
            return
        key = str(getattr(event, "key", "")).lower()
        dx, dy = {
            "left": (-self.STEP, 0.0),
            "right": (self.STEP, 0.0),
            "up": (0.0, -self.STEP),
            "down": (0.0, self.STEP),
        }.get(key, (0.0, 0.0))
        if dx == 0.0 and dy == 0.0:
            return
        pos = self.position
        self._set_position(Offset(pos.x + dx, pos.y + dy))
        if self.parent is not None:
            self.parent.mark_needs_layout()
        self._fire_change()

    # --------------------------------------------------------------- paint

    def paint_self(self, ctx: PaintContext, absolute: Offset) -> None:
        if self.size.is_empty:
            return
        style = self.style
        dpr = ctx.pixel_ratio
        radii = self.effective_radii
        ctx.display_list.add_box(
            absolute.x * dpr,
            absolute.y * dpr,
            self.size.width * dpr,
            self.size.height * dpr,
            token=ctx.palette.index(style.background or "surface_container_low"),
            radii=tuple(r * dpr for r in radii),  # type: ignore[arg-type]
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        title_h = min(self.TITLE_HEIGHT, self.size.height)
        ctx.display_list.add_box(
            absolute.x * dpr,
            absolute.y * dpr,
            self.size.width * dpr,
            title_h * dpr,
            token=ctx.palette.index("surface_container_high"),
            radii=(radii[0] * dpr, radii[1] * dpr, 0.0, 0.0),
            clip=ctx.clip,
            clip_radii=ctx.clip_radii,
        )
        label = self.text.strip()
        if label:
            token = content_token(ctx, style, "on_surface")
            metrics = measure_text(label, TITLE_LABEL, engine=self.text_engine)
            paint_text(
                ctx,
                absolute.x + self.PAD_X,
                absolute.y + (title_h - metrics.height) / 2,
                label,
                TITLE_LABEL,
                token,
                max_width=max(0.0, self.size.width - 2 * self.PAD_X),
            )
        self._paint_ports(ctx, absolute)

    def _paint_ports(self, ctx: PaintContext, absolute: Offset) -> None:
        dpr = ctx.pixel_ratio
        token = ctx.palette.index("outline")
        for side, names in (("inputs", self.spec.inputs), ("outputs", self.spec.outputs)):
            count = len(names)
            for index in range(count):
                local = _port_offset(self, side, index, count)
                cx, cy = absolute.x + local.x, absolute.y + local.y
                ctx.display_list.add_box(
                    (cx - self.PORT_RADIUS) * dpr,
                    (cy - self.PORT_RADIUS) * dpr,
                    self.PORT_RADIUS * 2 * dpr,
                    self.PORT_RADIUS * 2 * dpr,
                    token=token,
                    radii=(self.PORT_RADIUS * dpr,) * 4,
                    clip=ctx.clip,
                    clip_radii=ctx.clip_radii,
                )


class NodeGraphElement(_StyledMixin, LayoutNode):
    """A pannable surface of draggable `Node`s wired by declared `edges`.

    See the module docstring for how panning, dragging, and edge drawing all
    reuse existing mechanisms rather than inventing new ones.
    """

    #: Bigger than `CanvasElement.DEFAULT_SIZE` (200) -- a node editor with no
    #: explicit size needs enough room to be useful, not just non-empty.
    DEFAULT_WIDTH: Final = 480.0
    DEFAULT_HEIGHT: Final = 320.0
    EDGE_THICKNESS: Final = 2.0
    #: See `CanvasElement.HIDDEN_EXTENT` / ARCHITECTURE.md 5.8.6: a clip with
    #: either dimension at exact zero reads as "no clip" to the shader, not
    #: "hidden", so a genuinely empty intersection floors to this instead.
    HIDDEN_EXTENT: Final = 0.01
    CLIPS_CHILDREN = True

    def __init__(self, spec: WidgetSpec) -> None:
        LayoutNode.__init__(self)
        self.init_element(spec)

    # ---------------------------------------------------------------- layout

    def perform_layout(self, constraints: Constraints) -> Size:
        outer = self.sized(constraints, self.style)
        width = outer.max_width if outer.has_bounded_width else self.DEFAULT_WIDTH
        height = outer.max_height if outer.has_bounded_height else self.DEFAULT_HEIGHT
        loose = Constraints(min_width=0.0, max_width=INF, min_height=0.0, max_height=INF)
        for child in self._children:
            child.layout(loose)
            child.offset = child.position if isinstance(child, NodeElement) else Offset(0.0, 0.0)
        return outer.constrain(Size(width, height))

    # ------------------------------------------------------------------ pan

    def child_origin(self, absolute: Offset) -> Offset:
        """Translate the whole subtree by the pan offset.

        `ScrollView`'s own mechanism, unchanged: paint-time only, so panning
        costs one paint of the viewport rather than a relayout.
        """
        scroll = self.state.scroll
        return Offset(absolute.x - scroll.x, absolute.y - scroll.y)

    def child_paint_context(self, ctx: PaintContext, absolute: Offset) -> PaintContext:
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
            clip_radii=tuple(r * dpr for r in self.effective_radii),  # type: ignore[arg-type]
        )

    # ------------------------------------------------------------- pointer

    @property
    def panning(self) -> bool:
        return "pan_from" in self.state.data

    def on_pointer_down(self, event: Any) -> None:
        """Start a pan -- but only when the press's actual *target* is this
        element itself, not some `Node` (or its content) that happens to
        sit above the background at this point.

        A native handler like this one runs on the way up (`EventDispatcher
        ._invoke` skips it during capture), so without this check a press
        anywhere inside a `Node` -- not just its title bar -- would bubble
        here and start panning underneath whatever the user was actually
        trying to drag or click. Reading `event.target` (the dispatcher's
        own hit-test result) is not a second hit-test of this element's
        own -- it is the one already done, so this stays within "no
        special-case region hit-testing" (see the module docstring).
        """
        if self.effective_disabled or event.target is not self:
            return
        self.state.data["pan_from"] = Offset(event.x, event.y)
        self.state.data["pan_origin"] = self.state.scroll
        event.capture()

    def on_pointer_move(self, event: Any) -> None:
        if not self.panning:
            return
        start = self.state.data["pan_from"]
        origin = self.state.data["pan_origin"]
        self.state.scroll = Offset(origin.x - (event.x - start.x), origin.y - (event.y - start.y))
        self.mark_needs_paint()

    def on_pointer_up(self, event: Any) -> None:
        self.state.data.pop("pan_from", None)
        self.state.data.pop("pan_origin", None)

    # --------------------------------------------------------------- paint

    def paint_self(self, ctx: PaintContext, absolute: Offset) -> None:
        super().paint_self(ctx, absolute)
        if not self.spec.edges:
            return
        origin = self.child_origin(absolute)
        by_name = {c.name: c for c in self._children if isinstance(c, NodeElement) and c.name}
        dpr = ctx.pixel_ratio
        token = ctx.palette.index("outline")
        for edge in self.spec.edges:
            point_a = self._port_point(by_name, origin, edge.source, "outputs")
            point_b = self._port_point(by_name, origin, edge.target, "inputs")
            if point_a is None or point_b is None:
                continue
            ctx.display_list.add_segment(
                point_a.x * dpr,
                point_a.y * dpr,
                point_b.x * dpr,
                point_b.y * dpr,
                thickness=self.EDGE_THICKNESS * dpr,
                token=token,
                clip=ctx.clip,
                clip_radii=ctx.clip_radii,
            )

    @staticmethod
    def _port_point(
        by_name: dict[str, NodeElement], origin: Offset, ref: str, side: str
    ) -> Offset | None:
        node_name, _, port = ref.partition(".")
        node = by_name.get(node_name)
        if node is None:
            return None
        names = node.spec.outputs if side == "outputs" else node.spec.inputs
        index = names.index(port) if port in names else 0
        local = _port_offset(node, side, index, max(1, len(names)))
        return Offset(origin.x + node.offset.x + local.x, origin.y + node.offset.y + local.y)
