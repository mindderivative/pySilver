"""Events: queue, hit testing, capture/bubble dispatch, hover, and focus.

Events are queued and drained once per frame (step 1 of ARCHITECTURE.md 6), so
a burst of pointer motion coalesces instead of triggering redundant work.

Hit testing walks the tree in REVERSE paint order and returns the topmost path.
A forward walk that visits every node -- which is what a naive implementation
does -- both ignores z-order and cannot express "the panel above intercepted it".
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Any, Final

from ..layout import OFFSET_ZERO, Offset
from .signals import batch

__all__ = [
    "Event",
    "EventDispatcher",
    "EventType",
    "KeyEvent",
    "Phase",
    "PointerEvent",
    "WheelEvent",
]


#: Mouse buttons as the backend reports them: 1 primary, 2 secondary, 3 middle.
#: One-based, not zero-based -- checked against `rendercanvas/glfw.py` rather
#: than assumed, because guessing this wrong fails silently.
MOUSE_PRIMARY: Final = 1
MOUSE_SECONDARY: Final = 2


class EventType(StrEnum):
    POINTER_DOWN = "pointer_down"
    POINTER_UP = "pointer_up"
    POINTER_MOVE = "pointer_move"
    POINTER_ENTER = "pointer_enter"
    POINTER_LEAVE = "pointer_leave"
    CLICK = "click"
    CONTEXT_MENU = "context_menu"
    WHEEL = "wheel"
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"
    TEXT = "text"
    FOCUS = "focus"
    BLUR = "blur"
    #: A control's value settled on something new. Posted by the widget, not
    #: by the canvas -- a text field is the only source so far.
    CHANGE = "change"
    #: An overlay was closed by the runtime rather than by the application --
    #: Escape, or a press outside a dismissable one.
    DISMISS = "dismiss"


class Phase(Enum):
    CAPTURE = "capture"
    TARGET = "target"
    BUBBLE = "bubble"


@dataclass(slots=True)
class Event:
    type: EventType
    target: Any = None
    #: The element whose handler is running right now, which during capture or
    #: bubble is an *ancestor* of `target`. A handler shared between elements
    #: needs this to tell which one it is running for.
    current: Any = None
    phase: Phase = Phase.TARGET
    _stopped: bool = False

    def stop_propagation(self) -> None:
        self._stopped = True

    @property
    def stopped(self) -> bool:
        return self._stopped


@dataclass(slots=True)
class PointerEvent(Event):
    x: float = 0.0
    y: float = 0.0
    button: int = 0
    modifiers: frozenset[str] = field(default_factory=frozenset)
    _capture: Any = None

    def capture(self) -> None:
        """Claim the drag: every pointer event until release comes here.

        Without this, capture goes to whatever was topmost under the press --
        so a scrollbar thumb drawn over a list could never be dragged, because
        the row beneath it would take the press and keep it. An ancestor
        handling the press on the way up claims it instead.
        """
        self._capture = self.current


@dataclass(slots=True)
class WheelEvent(Event):
    """A scroll wheel or trackpad gesture.

    `dy` is positive when scrolling **down**, matching the direction a scroll
    offset grows. The backend already negates the raw platform value, and one
    wheel notch is about 100 units.
    """

    x: float = 0.0
    y: float = 0.0
    dx: float = 0.0
    dy: float = 0.0
    modifiers: frozenset[str] = field(default_factory=frozenset)


@dataclass(slots=True)
class KeyEvent(Event):
    key: str = ""
    text: str = ""
    modifiers: frozenset[str] = field(default_factory=frozenset)


@dataclass(slots=True)
class ChangeEvent(Event):
    """A control's value settled on something new. Carries the new value, so a
    handler does not have to reach back into the widget to find out what it is."""

    value: str = ""


#: Modifier spellings, folded to one vocabulary. `rendercanvas` reports GLFW's
#: names -- "Control", "Shift", "Alt", "Meta" -- while hand-written events and
#: other backends use their own. Matching a raw string against one spelling is
#: how Shift+Tab and Ctrl+A came to be dead in a real window while their tests
#: passed: the tests posted "shift" and "ctrl", and GLFW never sends either.
_MODIFIER_NAMES = {
    "control": "ctrl",
    "ctrl": "ctrl",
    "meta": "meta",
    "super": "meta",
    "cmd": "meta",
    "command": "meta",
    "os": "meta",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "altgraph": "alt",
}


def modifiers_of(event: Any) -> frozenset[str]:
    """An event's modifiers as lower-case canonical names."""
    raw = getattr(event, "modifiers", ()) or ()
    return frozenset(_MODIFIER_NAMES.get(str(name).lower(), str(name).lower()) for name in raw)


def is_accelerator(mods: frozenset[str]) -> bool:
    """Whether the platform's shortcut modifier is held.

    Ctrl or Meta, without distinguishing them: pySilver does not branch on
    platform anywhere else, and a Mac user pressing Cmd+C means the same thing
    a Linux user pressing Ctrl+C does.
    """
    return "ctrl" in mods or "meta" in mods


#: Event type -> the handler key a view file uses.
HANDLER_KEYS = {
    EventType.POINTER_DOWN: "on_pointer_down",
    EventType.POINTER_UP: "on_pointer_up",
    EventType.POINTER_MOVE: "on_pointer_move",
    EventType.POINTER_ENTER: "on_pointer_enter",
    EventType.POINTER_LEAVE: "on_pointer_leave",
    EventType.CLICK: "on_click",
    EventType.CONTEXT_MENU: "on_context_menu",
    EventType.WHEEL: "on_wheel",
    EventType.KEY_DOWN: "on_key_down",
    EventType.TEXT: "on_text",
    EventType.FOCUS: "on_focus",
    EventType.BLUR: "on_blur",
    EventType.CHANGE: "on_change",
    EventType.DISMISS: "on_dismiss",
}


#: Widget kinds that take keyboard focus even without an explicit handler.
#: These are interactive controls: a user must be able to Tab to a checkbox
#: whether or not the view file wired an on_click.
FOCUSABLE_KINDS: frozenset[str] = frozenset(
    {
        "Button",
        "Link",
        "Checkbox",
        "Radio",
        "Switch",
        "Chip",
        "IconButton",
        "Fab",
        "NavItem",
        "Tab",
        "Segment",
        "ListItem",
        "TextField",
        "SpinBox",
        "Slider",
        "Pagination",
        "SearchBar",
        "SplitButton",
        "DatePicker",
        "TimePicker",
        "DockGroup",
        "DockSplit",
        "Node",
        "CodeEditor",
        "Terminal",
    }
)


class EventDispatcher:
    """Owns the event queue, hover/press/focus state, and dispatch."""

    def __init__(self) -> None:
        self.root: Any = None
        #: The overlay layer, consulted before the tree because it is on top.
        self.overlays: Any = None
        self._queue: deque[Event] = deque()
        self._hover_path: list[Any] = []
        #: Last pointer position, so the cursor shape can be resolved for a
        #: widget that wants different shapes in different regions.
        self._pointer: tuple[float, float] = (0.0, 0.0)
        #: Unfiltered hit path, for cursor resolution only.
        self._cursor_path: list[Any] = []
        self._pressed: Any = None
        self._captured: Any = None
        self._focused: Any = None

    # ------------------------------------------------------------- queueing

    def post(self, event: Event) -> None:
        """Queue an event. Consecutive motion events coalesce."""
        if (
            event.type is EventType.POINTER_MOVE
            and self._queue
            and self._queue[-1].type is EventType.POINTER_MOVE
        ):
            self._queue[-1] = event
            return
        self._queue.append(event)

    @property
    def pending(self) -> int:
        return len(self._queue)

    def drain(self) -> int:
        """Dispatch everything queued. Returns how many events were handled.

        The whole drain runs in one signal batch, so a handler writing several
        signals triggers dependent work once, not once per write.
        """
        handled = 0
        with batch():
            while self._queue:
                self.dispatch(self._queue.popleft())
                handled += 1
        return handled

    # ------------------------------------------------------------ hit testing

    @staticmethod
    def _enabled_path(path: list[Any]) -> list[Any]:
        """Drop a disabled target and everything under it.

        Truncated rather than filtered: an enabled ancestor of a disabled
        control must still receive the event, so the path is cut at the
        disabled element and its ancestors are kept.
        """
        for index, element in enumerate(path):
            if getattr(element, "effective_disabled", False):
                return path[index + 1 :]
        return path

    def hit_path(self, x: float, y: float) -> list[Any]:
        """Topmost-first list of elements under the point.

        The overlay layer is checked first because it renders above the tree,
        and a modal overlay swallows everything beneath it -- otherwise a click
        on a scrim would fall through to the blocked interface.
        """
        if self.overlays is not None:
            found: list[Any] = list(self.overlays.hit_path(x, y))
            if found:
                return found
            if self.overlays.has_modal:
                return []
        if self.root is None:
            return []
        return list(self.root.hit_test(x, y, OFFSET_ZERO))

    @property
    def focused(self) -> Any:
        return self._focused

    @property
    def cursor(self) -> str:
        """Pointer shape for whatever is under the pointer right now.

        Topmost element with an opinion wins, so a button inside a card gets
        the button's shape and a plain container defers to whatever encloses
        it. Falls back to the platform default.
        """
        x, y = self._pointer
        for element in self._cursor_path:
            shape = element.cursor_at(x, y)
            if shape is not None:
                return str(shape)
        return "default"

    @property
    def hovered(self) -> Any:
        return self._hover_path[0] if self._hover_path else None

    # -------------------------------------------------------------- dispatch

    def dispatch(self, event: Event) -> None:
        if isinstance(event, WheelEvent):
            self._dispatch_wheel(event)
        elif isinstance(event, PointerEvent):
            self._dispatch_pointer(event)
        elif isinstance(event, KeyEvent):
            self._dispatch_to_focused(event)

    def _dispatch_wheel(self, event: WheelEvent) -> None:
        """Send a wheel event to whatever is under the pointer.

        Position, not focus, decides the target: the wheel scrolls what the
        pointer is over, which is the desktop convention every toolkit follows
        and is why this does not go through `_dispatch_to_focused`.
        """
        self._propagate(self._enabled_path(self.hit_path(event.x, event.y)), event)

    def _dispatch_pointer(self, event: PointerEvent) -> None:
        # A captured pointer keeps receiving events outside its own bounds,
        # which is what makes dragging work.
        raw_path = (
            [self._captured] if self._captured is not None else self.hit_path(event.x, event.y)
        )
        path = self._enabled_path(raw_path)

        # A press outside a modal dismisses it and goes no further.
        if (
            event.type is EventType.POINTER_DOWN
            and self.overlays is not None
            and self._captured is None
            and self.overlays.handle_press(event.x, event.y)
            and not path
        ):
            return

        match event.type:
            case EventType.POINTER_MOVE:
                self._pointer = (event.x, event.y)
                # The cursor is resolved from the *unfiltered* path -- already
                # computed above as `raw_path`, so hit testing does not run
                # twice for the same move. A disabled control is removed from
                # the event path -- correctly, it must receive nothing -- but
                # it still has to say "not-allowed", which is feedback rather
                # than an event.
                self._cursor_path = raw_path
                self._update_hover(path)
            case EventType.POINTER_DOWN:
                # Only the primary button presses, captures, and moves focus.
                # A right-click that left a button stuck in its pressed state
                # would be a visible bug the moment anyone tried a context menu.
                if event.button != MOUSE_SECONDARY:
                    target = path[0] if path else None
                    self._pressed = target
                    self._captured = target
                    if target is not None:
                        target.state.pressed = True
                        target.mark_needs_paint()
                    self.focus(target if target and self._focusable(target) else None)
            case EventType.POINTER_UP:
                pressed = self._pressed
                self._captured = None
                self._pressed = None
                if pressed is not None:
                    pressed.state.pressed = False
                    pressed.mark_needs_paint()

        self._propagate(path, event)

        # A secondary press is a context-menu request. Synthesised like CLICK
        # rather than delivered raw, so a view writes `on_context_menu:` and
        # never has to know which integer the backend calls "right".
        if event.type is EventType.POINTER_DOWN and event.button == MOUSE_SECONDARY:
            if self.overlays is not None:
                self.overlays.pointer_anchor = Offset(event.x, event.y)
            self._propagate(
                path,
                PointerEvent(EventType.CONTEXT_MENU, x=event.x, y=event.y, button=event.button),
            )

        # An element that claimed the drag during the press takes capture from
        # whatever happened to be topmost. Applied after propagation, so a
        # handler on the way up can still claim it.
        if event.type is EventType.POINTER_DOWN and event._capture is not None:
            self._captured = event._capture

        # A click is press and release over the same element. The live path is
        # filtered the same way, or a press that landed on an enabled ancestor
        # of a disabled child would never match and no click would fire.
        # Secondary release is excluded the same way secondary press is above --
        # otherwise a right-click that lands and lifts over a button fires
        # `on_click` right alongside `on_context_menu`.
        if (
            event.type is EventType.POINTER_UP
            and event.button != MOUSE_SECONDARY
            and path
            and path[0] is not None
        ):
            live = self._enabled_path(self.hit_path(event.x, event.y))
            if live and live[0] is path[0]:
                self._propagate(live, PointerEvent(EventType.CLICK, x=event.x, y=event.y))

    def _update_hover(self, path: list[Any]) -> None:
        new_set = set(map(id, path))
        for element in self._hover_path:
            if id(element) not in new_set and element.state.hovered:
                element.state.hovered = False
                element.mark_needs_paint()
                self._propagate([element], Event(EventType.POINTER_LEAVE))
        old_set = set(map(id, self._hover_path))
        for element in path:
            if id(element) not in old_set:
                element.state.hovered = True
                element.mark_needs_paint()
                self._propagate([element], Event(EventType.POINTER_ENTER))
        self._hover_path = path

    def _dispatch_to_focused(self, event: Event) -> None:
        # Tab traversal is handled before delivery: it must work even when
        # nothing is focused yet, which is the state an app starts in.
        if isinstance(event, KeyEvent) and event.type is EventType.KEY_DOWN:
            if event.key in ("Tab", "tab") and not getattr(self._focused, "CAPTURES_TAB", False):
                # getattr, not a direct attribute read: `self._focused` can be
                # None (nothing focused yet), which has no CAPTURES_TAB at all.
                self.focus_next(backwards="shift" in modifiers_of(event))
                return
            if event.key in ("Escape", "escape"):
                # Escape closes the topmost overlay before it clears focus.
                if self.overlays is not None and self.overlays.dismiss_top():
                    return
                if self._focused is not None:
                    self.focus(None)
                    return

        if self._focused is None:
            return
        path: list[Any] = []
        node = self._focused
        while node is not None:
            path.append(node)
            node = getattr(node, "parent", None)
        self._propagate(path, event)

    def _propagate(self, path: list[Any], event: Event) -> None:
        """Capture (root -> target), then target, then bubble (target -> root)."""
        if not path:
            return
        event.target = path[0]

        ancestors = path[1:]
        sequence: list[tuple[Phase, Any]] = [
            *((Phase.CAPTURE, e) for e in reversed(ancestors)),
            (Phase.TARGET, path[0]),
            *((Phase.BUBBLE, e) for e in ancestors),
        ]
        for phase, element in sequence:
            event.phase = phase
            event.current = element
            self._invoke(element, event)
            if event.stopped:
                return

    @staticmethod
    def _invoke(element: Any, event: Event) -> None:
        # Invoked in BOTH the capture and bubble phases, deliberately: the
        # view format registers one handler with no phase, and an ancestor
        # being able to intercept during capture is a tested feature
        # (`test_stop_propagation_during_capture_prevents_the_target`).
        #
        # The consequence is a real sharp edge: a handler on an *ancestor* of
        # the target runs twice for one event unless it checks `event.phase`.
        # Documented in docs/view-reference.md rather than silently changed --
        # it is a frozen 1.x API.
        handler = element.handlers.get(HANDLER_KEYS.get(event.type, ""))
        if handler is not None:
            handler(event)
        if event.stopped:
            return
        # Some widgets respond to an event natively rather than through a
        # view-declared handler -- a scroll view consumes the wheel whether or
        # not anyone wrote `on_wheel:`. The view's handler runs first so it can
        # stop propagation and pre-empt the built-in behaviour.
        # Native behaviour runs once, on the way up only -- a scroll view must
        # not consume one wheel notch twice.
        native = getattr(element, HANDLER_KEYS.get(event.type, ""), None)
        if native is not None and event.phase is not Phase.CAPTURE:
            native(event)

    # ----------------------------------------------------------------- focus

    @staticmethod
    def _focusable(element: Any) -> bool:
        """A disabled control is skipped by Tab as well as by the pointer.

        Leaving it in the focus order would let the keyboard reach something
        the mouse cannot, which is the accessibility failure disabled state
        exists to avoid.
        """
        if getattr(element, "effective_disabled", False):
            return False
        # Selectable text is keyboard-reachable: it has to take focus to
        # receive Ctrl+C at all, and being able to Tab to a block of text and
        # copy it is the accessible behaviour rather than an accident.
        if getattr(element, "selectable", False):
            return True
        return bool(element.handlers) or str(element.spec.widget) in FOCUSABLE_KINDS

    def focus(self, element: Any, *, keyboard: bool = False) -> None:
        """Move focus. ``keyboard=True`` also shows the focus ring.

        Desktop convention: clicking focuses silently, Tab shows the indicator.
        """
        if element is self._focused:
            if element is not None and element.state.focus_visible != keyboard:
                element.state.focus_visible = keyboard
                element.mark_needs_paint()
            return
        if self._focused is not None:
            self._focused.state.focused = False
            self._focused.state.focus_visible = False
            self._focused.mark_needs_paint()
            self._propagate([self._focused], Event(EventType.BLUR))
        self._focused = element
        if element is not None:
            element.state.focused = True
            element.state.focus_visible = keyboard
            element.mark_needs_paint()
            self._propagate([element], Event(EventType.FOCUS))

    def focus_order(self) -> list[Any]:
        """Focusable elements in document order -- the Tab traversal."""
        if self.root is None:
            return []
        return [e for e in self.root.walk_elements() if self._focusable(e)]

    def focus_next(self, backwards: bool = False) -> Any:
        """Move focus along the Tab order. Always shows the ring."""
        order = self.focus_order()
        if not order:
            return None
        if self._focused is None or self._focused not in order:
            self.focus(order[-1] if backwards else order[0], keyboard=True)
            return self._focused
        index = order.index(self._focused)
        self.focus(order[(index + (-1 if backwards else 1)) % len(order)], keyboard=True)
        return self._focused

    def bind_handlers(
        self,
        registry: dict[str, Callable[[Any], None]],
        extra: list[Any] | None = None,
        scoped: dict[str, dict[str, Callable[[Any], None]]] | None = None,
    ) -> list[str]:
        """Resolve handler names from view files against *registry*.

        `scoped` maps a view file to the handlers its own ViewModel publishes.
        A node resolves against its view's ViewModel first and the application
        registry second, so a fragment can name a handler without knowing what
        the rest of the application calls things -- and can deliberately shadow
        one.

        Returns the names that could not be resolved, so the caller can fail at
        load rather than silently ignoring a typo'd handler.
        """
        missing: list[str] = []
        if self.root is None:
            return missing
        by_view = scoped or {}
        targets = list(self.root.walk_elements()) + list(extra or [])
        for element in targets:
            element.handlers = {}
            local = by_view.get(element.spec.view or "", {})
            for event_key, name in element.spec.handlers.items():
                fn = local.get(name) or registry.get(name)
                if fn is None:
                    label = element.spec.name or element.spec.id
                    missing.append(f"{label}.{event_key} -> {name!r}")
                else:
                    element.handlers[event_key] = fn
        return missing
