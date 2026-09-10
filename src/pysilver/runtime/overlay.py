"""The overlay layer: content that renders above the tree.

Six M3 components -- Dialog, Menu, Tooltip, Snackbar, and both Sheet types --
share one requirement the four-tree model cannot otherwise express: they must
render **above** everything, positioned independently of whatever opened them
and clipped by nothing.

Overlays are therefore declared in a top-level ``overlays:`` list rather than
hoisted out of the widget tree. A dialog is not laid out or clipped by the
button that opened it, so declaring it as that button's child would be a lie
about the geometry -- and would leave the parent's Flex trying to reserve space
for something that floats.

The host owns its own layout and paint pass, run after the main tree's, and is
consulted **first** during hit testing because it is on top.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from ..layout import OFFSET_ZERO, Constraints, Offset, Rect, Size
from ..paint import DisplayList
from ..spec import WidgetSpec
from ..theme import Palette
from .events import Event, EventType

__all__ = ["SCRIM_OPACITY", "OverlayEntry", "OverlayHost"]

#: M3: modal surfaces sit behind a 32% scrim.
SCRIM_OPACITY: Final = 0.32

#: Keep an overlay this far inside the window edge.
MARGIN: Final = 8.0

#: M3's own easing/duration pairs, from the "suggested pairs" table:
#: "Emphasized decelerate | 400ms | Enter the screen" and
#: "Emphasized accelerate | 200ms | Exit the screen". A thing arrives gently
#: and departs briskly, which is why the two are not symmetric.
ENTER_DURATION: Final = "medium4"
ENTER_CURVE: Final = "emphasized_decelerate"
EXIT_DURATION: Final = "short4"
EXIT_CURVE: Final = "emphasized_accelerate"


@dataclass(slots=True)
class OverlayEntry:
    """One declared overlay and its resolved position."""

    element: Any
    origin: Offset = OFFSET_ZERO

    @property
    def spec(self) -> WidgetSpec:
        spec: WidgetSpec = self.element.spec
        return spec

    #: Set when the runtime has closed this overlay -- Escape, or a press
    #: outside. Kept on the entry rather than only in the host's set, so that
    #: `showing` can see it: an overlay the host has stopped hit-testing must
    #: also stop being *painted*, or it sits on screen taking no clicks while
    #: they land on whatever is behind it.
    dismissed: bool = False

    #: A controller-owned entry pushed via `OverlayHost.push_transient`
    #: rather than declared in `ViewSpec.overlays` -- Dock's drag-and-drop
    #: ghost/drop-zone highlight is the first user. Never has an `open:`
    #: binding or a dismiss gesture of its own (its owner adds/removes it
    #: directly), so `showing` and `visible()` special-case it: always
    #: "showing" while present, but excluded from hit-testing/press so it
    #: never steals routing from the gesture that owns it.
    transient: bool = False

    @property
    def showing(self) -> bool:
        """Whether this overlay should be up.

        Both sources have to agree. `open:` is the application's answer and a
        dismissal is the runtime's, and when they disagreed the overlay was
        drawn at full opacity while being excluded from hit testing -- a dialog
        you could see, could not click, and could not close, because the only
        buttons that would clear its signal were underneath it.

        A transient entry has neither source -- its lifetime is owned
        directly by whatever pushed it -- so it is simply "showing" for as
        long as it exists.
        """
        if self.transient:
            return True
        return bool(self.element.is_open) and not self.dismissed

    @property
    def opacity(self) -> float:
        """Fade level, advanced by the element's own animation clock."""
        target = 1.0 if self.showing else 0.0
        entering = target > 0.0
        value: float = self.element.animated(
            "overlay_opacity",
            target,
            duration=ENTER_DURATION if entering else EXIT_DURATION,
            curve=ENTER_CURVE if entering else EXIT_CURVE,
        )
        return value

    @property
    def visible(self) -> bool:
        """Whether the *application* wants this up, ignoring any dismissal.

        `sync_dismissals` reads this to notice that the application has closed
        an overlay itself, which is when a dismissal may be forgotten.
        """
        return bool(self.element.is_open)

    @property
    def modal(self) -> bool:
        return bool(self.element.style.modal)

    @property
    def scrim(self) -> bool:
        return bool(self.element.style.scrim)

    @property
    def dismissable(self) -> bool:
        return bool(self.element.style.dismissable)

    @property
    def placement(self) -> str:
        """Resolved placement -- see `ElementMixin.resolved_placement`."""
        return str(self.element.resolved_placement)

    @property
    def key(self) -> str:
        """Stable handle for dismissal tracking: the name if given, else the
        positional id."""
        key: str = self.element.name or self.element.id
        return key

    def rect(self) -> Rect:
        return Rect.from_offset_size(self.origin, self.element.size)


def _fade(display_list: DisplayList, start: int, opacity: float) -> None:
    """Scale the alpha of everything an overlay just emitted.

    Applied to the display-list slice rather than threaded through the paint
    context, because that keeps subtree opacity in one place instead of
    obliging every emit site to multiply. The display list is a numpy
    structured array, so this is a single vectorised pass over a view -- and it
    catches cached subtrees spliced in at full alpha, which a context flag
    would have missed.
    """
    view = display_list.view[start:]
    if len(view) == 0:
        return
    view["fill"][:, 3] *= opacity
    view["border"][:, 3] *= opacity


class OverlayHost:
    """Owns every overlay: layout, paint, hit testing, and dismissal."""

    __slots__ = ("_dismissed", "entries", "pointer_anchor")

    def __init__(self) -> None:
        self.entries: list[OverlayEntry] = []
        #: Where the last context-menu request happened. `placement: pointer`
        #: positions against this rather than against another element.
        self.pointer_anchor: Offset = OFFSET_ZERO
        #: Ids dismissed by a click-outside or Escape. Cleared when the
        #: application reopens them, so a signal-driven overlay still wins.
        self._dismissed: set[str] = set()

    # ------------------------------------------------------------- lifecycle

    def build(
        self,
        specs: tuple[WidgetSpec, ...],
        *,
        text_engine: Any = None,
        image_atlas: Any = None,
        ticker: Any = None,
    ) -> None:
        from ..widgets import build_element

        self.entries = []
        for spec in specs:
            element = build_element(spec)
            if text_engine is not None:
                element.set_text_engine(text_engine)
            if image_atlas is not None:
                element.set_image_atlas(image_atlas)
            # Without this an overlay animates against the process-wide default
            # ticker, which the App never advances -- so its fade never moved.
            if ticker is not None:
                element.set_ticker(ticker)
            self.entries.append(OverlayEntry(element))
        self._dismissed.clear()
        for entry in self.entries:
            entry.dismissed = False

    def push_transient(self, element: Any) -> OverlayEntry:
        """Add a controller-owned overlay entry outside the declarative
        `ViewSpec.overlays` list -- the escape hatch a gesture that must
        paint unclipped, above everything, needs without being authored in
        a view file. `element` still needs to be a real, already-built
        element (via `build_element`, with `text_engine`/`image_atlas`/
        `ticker` already wired the normal way) -- this only skips `build()`'s
        spec-list construction, not element construction itself. Positioned
        by the same `_place()` logic every other overlay uses (read
        `element.style.placement`, e.g. `"pointer"`, same as any declared
        overlay); painted via `rendered()`'s existing fade-aware fallback,
        never hit-tested (`visible()` excludes it). Removed by
        `clear_transient()`, never by dismissal -- a transient entry has no
        `open:` binding for a dismissal to even coordinate against.
        """
        entry = OverlayEntry(element, transient=True)
        self.entries.append(entry)
        return entry

    def clear_transient(self) -> None:
        """Remove every transient entry -- called once the gesture that
        pushed one ends or cancels."""
        self.entries = [e for e in self.entries if not e.transient]

    def bind(
        self,
        context: dict[str, Any],
        context_for: Callable[[str | None], dict[str, Any]] | None = None,
    ) -> None:
        """Subscribe every overlay element's bindings.

        `context_for` resolves a view file to the names visible inside it, so
        an overlay written in its own file sees its own ViewModel. Overlays are
        commonly whole fragments -- a dialog is the obvious one -- which makes
        this the case the scoping exists for.
        """
        for entry in self.entries:
            for element in entry.element.walk_elements():
                element.bind(context if context_for is None else context_for(element.spec.view))

    def elements(self) -> list[Any]:
        """Every element in every overlay, for handler resolution."""
        return [e for entry in self.entries for e in entry.element.walk_elements()]

    def find(self, name: str) -> Any | None:
        for entry in self.entries:
            if entry.element.name == name:
                return entry.element
            found = entry.element.find(name)
            if found is not None:
                return found
        return None

    # -------------------------------------------------------------- visibility

    def visible(self) -> list[OverlayEntry]:
        """Overlays that are **interactive**, bottom to top.

        Deliberately excludes one that is fading out. A dialog the user has
        just dismissed must stop swallowing clicks the moment it is dismissed,
        not 200ms later -- so hit testing, modality and dismissal all read this
        list, while layout and paint read `rendered()`.

        Also excludes transient entries (`OverlayEntry.transient`) -- a drag
        ghost/drop-zone highlight must never itself absorb the hit-testing or
        press handling meant for the gesture that owns it. `rendered()` still
        includes them for layout/paint, via its own `opacity > 0.0` fallback.
        """
        return [
            e
            for e in self.entries
            if not e.transient and e.showing and e.key not in self._dismissed
        ]

    def rendered(self) -> list[OverlayEntry]:
        """Overlays that must be **drawn**: the interactive ones, plus any
        still fading out. Declaration order is z-order."""
        live = {id(e) for e in self.visible()}
        return [e for e in self.entries if id(e) in live or e.opacity > 0.0]

    @property
    def has_modal(self) -> bool:
        return any(e.modal for e in self.visible())

    def _collect_dismiss_requests(self) -> None:
        """Honour an overlay that has asked to close itself.

        A widget cannot reach the host, and giving it one would let any element
        reach into the runtime. It raises a flag on its own state instead and
        the host reads it here, once a frame.
        """
        for entry in self.entries:
            if entry.element.state.data.pop("dismiss_requested", False):
                self.dismiss(entry)

    def dismiss(self, entry: OverlayEntry) -> None:
        """Close an overlay on the user's behalf, and say so.

        The `on_dismiss` handler is the whole point. When `open:` is bound --
        which is how any overlay an application controls is written -- the
        runtime closing it locally is not enough: the binding still says open,
        so the overlay could never be reopened, and before `showing` accounted
        for dismissals it was left painted and unclickable. Telling the
        application lets it clear its own signal, which is the only thing that
        actually closes a bound overlay.
        """
        if not entry.dismissable or entry.dismissed:
            return
        self._dismissed.add(entry.key)
        entry.dismissed = True
        handler = entry.element.handlers.get("on_dismiss")
        if handler is not None:
            handler(Event(EventType.DISMISS, target=entry.element))
            entry.element.mark_needs_paint()

    def dismiss_top(self) -> bool:
        """Dismiss the topmost dismissable overlay. Returns whether one closed."""
        for entry in reversed(self.visible()):
            if entry.dismissable:
                self.dismiss(entry)
                return True
        return False

    def sync_dismissals(self) -> None:
        """Forget dismissals for overlays the application has closed itself.

        Without this, an overlay closed by clicking outside could never be
        reopened by its signal: the dismissal would outlive the state change.
        """
        self._dismissed &= {e.key for e in self.entries if e.visible}
        for entry in self.entries:
            entry.dismissed = entry.key in self._dismissed

    # ------------------------------------------------------------------ layout

    def layout(self, window: Size, root: Any) -> None:
        """Size and place every visible overlay against the window.

        `entry.element.offset` is set here, immediately after `_place`
        resolves it -- not only in `paint`, which used to be the only place
        that happened. A submenu's `_anchored` call reads `absolute_rect()`
        on a `MenuItem` that lives inside an *earlier* entry's own overlay
        tree, and that walk bottoms out at the earlier entry's root element,
        whose absolute position **is** `element.offset` (a root has no
        parent to compose it from). Left unset until `paint`, that offset
        would still hold last frame's value -- or `OFFSET_ZERO` on an entry's
        first frame -- so a submenu opening on the very same frame as its
        parent would anchor against a stale position for one frame before
        snapping to the right place. Declaration order matters here: a
        submenu must be declared after the parent menu it anchors into, the
        same way it would read naturally in a view file.
        """
        self.sync_dismissals()
        self._collect_dismiss_requests()
        for entry in self.rendered():
            element = entry.element
            element.layout(Constraints.loose(window))
            entry.origin = self._place(entry, window, root)
            element.offset = entry.origin

    def _place(self, entry: OverlayEntry, window: Size, root: Any) -> Offset:
        style = entry.element.style
        size = entry.element.size
        placement = entry.placement
        #: A dragged overlay is displaced from wherever placement puts it.
        drag = getattr(entry.element, "drag_offset", OFFSET_ZERO)
        #: A docked overlay (a sheet) is flush with its edge; a floating one
        #: (snackbar, menu, tooltip) keeps clear of it.
        margin = 0.0 if entry.element.DOCKED else MARGIN

        if placement == "pointer":
            return self._at_pointer(size, window) + drag
        if placement == "anchor" and style.anchor:
            return self._anchored(entry, window, root)
        if placement == "top":
            return Offset((window.width - size.width) / 2, margin) + drag
        if placement == "bottom":
            return (
                Offset((window.width - size.width) / 2, window.height - size.height - margin) + drag
            )
        if placement == "left":
            return Offset(margin, (window.height - size.height) / 2) + drag
        if placement == "right":
            return (
                Offset(window.width - size.width - margin, (window.height - size.height) / 2) + drag
            )
        return Offset((window.width - size.width) / 2, (window.height - size.height) / 2) + drag

    def _at_pointer(self, size: Size, window: Size) -> Offset:
        """Open at the pointer, kept whole inside the window.

        A context menu opens down and to the right of the cursor, which is the
        desktop convention; near an edge it flips rather than being clipped,
        the same rule anchoring already uses. Clamped afterwards so a menu
        taller than the window still starts on screen.
        """
        point = self.pointer_anchor
        x = point.x if point.x + size.width <= window.width - MARGIN else point.x - size.width
        y = point.y if point.y + size.height <= window.height - MARGIN else point.y - size.height
        return Offset(
            min(max(MARGIN, x), max(MARGIN, window.width - size.width - MARGIN)),
            min(max(MARGIN, y), max(MARGIN, window.height - size.height - MARGIN)),
        )

    def _anchored(self, entry: OverlayEntry, window: Size, root: Any) -> Offset:
        """Below the anchor, flipping above it when it would overflow.

        A menu that runs off the bottom of the window is useless, so the flip
        is part of anchoring rather than something the caller must handle.

        The anchor target is looked up in `root` first and, if that misses,
        among the *other* overlays -- a submenu's trigger `MenuItem` lives
        inside its parent `Menu`, which is itself an overlay entry, not part
        of the main tree `root` walks. Anchoring to a `MenuItem` specifically
        then positions beside it rather than below it: M3's stated submenu
        placement ("Submenus should open next to the parent menu item
        without overlapping it").
        """
        style = entry.element.style
        size = entry.element.size
        target = root.find(style.anchor) if root is not None else None
        if target is None:
            target = self.find(style.anchor) if style.anchor else None
        if target is None:
            return Offset((window.width - size.width) / 2, MARGIN)

        rect = target.absolute_rect()
        if str(target.spec.widget) == "MenuItem":
            return self._anchored_beside(rect, size, window, style.offset)

        x = min(max(MARGIN, rect.x), max(MARGIN, window.width - size.width - MARGIN))
        below = rect.bottom + style.offset
        if below + size.height <= window.height - MARGIN:
            return Offset(x, below)
        above = rect.y - style.offset - size.height
        if above >= MARGIN:
            return Offset(x, above)
        return Offset(x, max(MARGIN, window.height - size.height - MARGIN))

    def _anchored_beside(self, rect: Rect, size: Size, window: Size, offset: float) -> Offset:
        """A submenu's placement: to the right of its trigger, flipping to the
        left when it would overflow -- the same flip `_anchored` does, on the
        other axis. Vertically kept level with the trigger's top edge, clamped
        inside the window rather than flipped, since there is no "above"
        equivalent for a menu that opens sideways.
        """
        y = min(max(MARGIN, rect.y), max(MARGIN, window.height - size.height - MARGIN))
        right = rect.right + offset
        if right + size.width <= window.width - MARGIN:
            return Offset(right, y)
        left = rect.x - offset - size.width
        if left >= MARGIN:
            return Offset(left, y)
        return Offset(max(MARGIN, window.width - size.width - MARGIN), y)

    # ------------------------------------------------------------------- paint

    def paint(self, ctx: Any, palette: Palette, window: Size) -> int:
        """Paint scrims and overlays above the main tree. Returns the count."""
        from ..tree.element import PaintContext

        painted = 0
        for entry in self.rendered():
            opacity = entry.opacity
            if opacity <= 0.0:
                continue
            start = len(ctx.display_list)
            if entry.scrim:
                self._paint_scrim(ctx, palette, window)
            child_ctx = PaintContext(
                display_list=ctx.display_list,
                palette=ctx.palette,
                text=ctx.text,
                pixel_ratio=ctx.pixel_ratio,
            )
            entry.element.offset = entry.origin
            entry.element.paint(child_ctx, OFFSET_ZERO)
            if opacity < 1.0:
                _fade(ctx.display_list, start, opacity)
            painted += 1
        return painted

    @staticmethod
    def _paint_scrim(ctx: Any, palette: Palette, window: Size) -> None:
        """M3's 32% backdrop, covering exactly the window.

        Sized to the window rather than an arbitrarily large quad: an oversized
        rect wastes fill rate and pushes the SDF far from the origin, where
        float precision is worse.
        """
        dpr = ctx.pixel_ratio
        display_list: DisplayList = ctx.display_list
        display_list.add_box(
            0.0,
            0.0,
            window.width * dpr,
            window.height * dpr,
            token=palette.index("scrim"),
            color=(1.0, 1.0, 1.0, SCRIM_OPACITY),
        )

    # -------------------------------------------------------------- hit testing

    def hit_path(self, x: float, y: float) -> list[Any]:
        """Topmost overlay path under the point, or empty."""
        for entry in reversed(self.visible()):
            entry.element.offset = entry.origin
            found = entry.element.hit_test(x, y, OFFSET_ZERO)
            if found:
                return list(found)
        return []

    def handle_press(self, x: float, y: float) -> bool:
        """Returns True when the press was consumed by the overlay layer.

        A click inside an overlay belongs to it. A click outside a *modal*
        overlay is swallowed and dismisses it if allowed -- it must never reach
        the blocked tree beneath.
        """
        for entry in reversed(self.visible()):
            if entry.rect().contains(x, y):
                return True
            if entry.modal:
                self.dismiss(entry)
                return True
            if entry.dismissable and entry.placement in ("anchor", "pointer"):
                self.dismiss(entry)
        return self.has_modal
