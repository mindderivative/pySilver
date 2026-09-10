"""The screen-reader bridge: pySilver's semantic tree, pushed to the platform.

`accessibility.py` builds what an interface *means*. This hands it to
AccessKit, which owns the per-platform half -- AT-SPI over D-Bus on Linux, UIA
on Windows, NSAccessibility on macOS -- so pySilver does not.

**Optional, and imported lazily.** `accesskit` is a native wheel most
applications will not want, so it is an extra (`pip install 'pysilver[a11y]'`)
and its absence is a clear sentence rather than an ImportError from somewhere
deep. Nothing in pySilver imports this module unless an application does.

**Linux only for now, and that is the wheel's doing rather than a choice.**
AccessKit ships its Windows and macOS adapters in their own platform wheels;
the Linux wheel exposes `accesskit.unix` alone. `available()` says what this
build can serve, and `AccessKitBridge` refuses rather than pretending.

Two things are not obvious and are worth stating.

**No window handle is needed.** AT-SPI is a D-Bus protocol, so the adapter
registers itself and is never told which native window it belongs to. That is
why this is possible at all without reaching into rendercanvas's private state,
which is the wall the clipboard nearly hit.

**Actions arrive on the wrong thread.** A screen reader activating a button
calls back from AccessKit's own D-Bus task, and pySilver's signals are thread
affine -- touching one there raises `ThreadAffinityError`, which is the
guardrail working rather than failing. So requests are queued and drained on
the engine thread. A bridge that could only *read* would be half a feature:
announcing a button nobody can press is not access.
"""

from __future__ import annotations

import sys
from collections import deque
from typing import Any, override

from .accessibility import AccessibleNode, Bridge

__all__ = ["AccessKitBridge", "available"]

#: pySilver role -> AccessKit role name. AccessKit has 186 roles under its own
#: names; these are the ones our vocabulary maps onto. Anything unmapped falls
#: back to GENERIC_CONTAINER rather than guessing at a closer fit.
_ROLES: dict[str, str] = {
    "button": "BUTTON",
    "checkbox": "CHECK_BOX",
    "radio": "RADIO_BUTTON",
    "radiogroup": "RADIO_GROUP",
    "switch": "SWITCH",
    "textbox": "TEXT_INPUT",
    "text": "LABEL",
    "group": "GROUP",
    "dialog": "DIALOG",
    "menu": "MENU",
    "menuitem": "MENU_ITEM",
    "tooltip": "TOOLTIP",
    "tab": "TAB",
    "tablist": "TAB_LIST",
    "option": "LIST_BOX_OPTION",
    "progressbar": "PROGRESS_INDICATOR",
    # AccessKit has no separator role; a splitter is the nearest thing that
    # exists and reads as a divider. Stated rather than left as a silent pick.
    "separator": "SPLITTER",
    "status": "STATUS",
    "banner": "BANNER",
    "terminal": "TERMINAL",
}

#: Roles a pointer can activate, and which therefore must offer the click
#: action -- otherwise the tree describes an interface nobody can operate.
_CLICKABLE = frozenset({"button", "checkbox", "radio", "switch", "tab", "option", "menuitem"})


def available() -> str | None:
    """Why the bridge cannot run here, or None when it can.

    A sentence rather than a bool: "not available" with no reason is the least
    useful thing an accessibility feature can say.
    """
    try:
        import accesskit
    except ImportError:
        return (
            "accesskit is not installed. It is an optional native dependency: "
            "pip install 'pysilver[a11y]'"
        )
    if not hasattr(accesskit, "unix"):
        return (
            f"this accesskit build has no adapter for {sys.platform!r}. The "
            "Windows and macOS adapters ship in their own platform wheels."
        )
    return None


class AccessKitBridge(Bridge):
    """Pushes the semantic tree to AT-SPI through AccessKit.

    Construct it once and hand it to `App.bind_accessibility`. It costs almost
    nothing until a screen reader attaches: `update_if_active` does no work
    while nothing is listening, which is what makes it safe to call whenever
    the tree may have changed.
    """

    def __init__(
        self,
        *,
        window_title: str = "",
        toolkit_name: str = "pySilver",
        toolkit_version: str = "",
    ) -> None:
        reason = available()
        if reason is not None:
            raise RuntimeError(reason)
        import accesskit

        self._ak = accesskit
        self._toolkit_name = toolkit_name
        self._toolkit_version = toolkit_version
        #: AccessKit expects the tree's root to be a WINDOW carrying the title.
        #: Handing it our own root -- a Vertical, which converts to GROUP -- made
        #: AT-SPI list the application as "python3.14", the process name,
        #: because there was nothing better to call it. Found by asking the
        #: registry rather than by reading the docs.
        self._window_title = window_title
        #: The latest tree, kept so a reader attaching mid-session is handed
        #: the current state rather than nothing until something next changes.
        self._latest: Any = None
        #: Requests from AccessKit's D-Bus thread, drained on the engine thread.
        self._requests: deque[Any] = deque()
        #: AccessKit node id -> the node it came from, rebuilt each update so an
        #: action lands on what is there now rather than on something replaced.
        self._targets: dict[int, AccessibleNode] = {}
        self._adapter: Any = accesskit.unix.Adapter(
            self._on_activate, self._requests.append, self._on_deactivate
        )

    # -------------------------------------------------------------- adapter

    def _on_activate(self) -> Any:
        """A screen reader attached. Hand it whatever the tree is now."""
        return self._latest

    def _on_deactivate(self) -> None:
        """The last reader detached. Nothing to undo: the next `update` is
        skipped by `update_if_active` on its own."""

    @override
    def update(self, tree: AccessibleNode) -> None:
        if self._adapter is None:
            return
        built = self._build(tree)
        self._latest = built
        self._adapter.update_if_active(lambda: built)

    def close(self) -> None:
        """Shut the adapter down. Idempotent, and not optional.

        AccessKit runs a D-Bus task on its own thread which calls back into
        Python. Left alive at interpreter shutdown it panics --

            The Python interpreter is not initialized ... pyo3/src/gil.rs

        -- because it reaches for an interpreter that has already finalised.
        The same shape as the wgpu surface outliving its window: a native
        background thread has to be stopped while Python is still there to stop
        it. `App.run` closes the bridge in a `finally`, and anything driving an
        App by hand should do the same.
        """
        self._adapter = None
        self._latest = None
        self._targets.clear()
        self._requests.clear()

    def __enter__(self) -> AccessKitBridge:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------- requests

    @property
    def closed(self) -> bool:
        return self._adapter is None

    def drain(self) -> list[Any]:
        """Take the action requests that have arrived since the last call.

        Called from the engine thread. AccessKit delivers on its own D-Bus
        task, and pySilver's signals are thread affine, so a request cannot be
        acted on where it arrives. Popped one at a time rather than snapshot-
        then-clear: that pairing could drop a request the D-Bus thread appends
        in the gap between the two.
        """
        out: list[Any] = []
        while self._requests:
            out.append(self._requests.popleft())
        return out

    def target_of(self, request: Any) -> AccessibleNode | None:
        """The node an action request was aimed at, if it is still there."""
        return self._targets.get(int(request.target))

    # ---------------------------------------------------------------- build

    def _build(self, tree: AccessibleNode) -> Any:
        """Convert one snapshot into an AccessKit `TreeUpdate`.

        Ids are assigned by traversal order. They are stable *within* an
        update, which is what AccessKit needs, and deliberately not across
        updates: a pySilver element has no identity a bridge could borrow, and
        inventing one that survived reconciliation would be a second identity
        system to keep correct.
        """
        ak = self._ak
        nodes: list[tuple[int, Any]] = []
        targets: dict[int, AccessibleNode] = {}
        focus = [0]
        counter = [0]

        def visit(node: AccessibleNode) -> int:
            node_id = counter[0]
            counter[0] += 1
            targets[node_id] = node
            child_ids = [visit(child) for child in node.children]

            out = ak.Node(getattr(ak.Role, _ROLES.get(node.role, "GENERIC_CONTAINER")))
            if node.name:
                out.set_label(node.name)
            if node.description:
                out.set_description(node.description)
            if node.value:
                out.set_value(node.value)
            box = node.bounds
            out.set_bounds(ak.Rect(box.x, box.y, box.x + box.width, box.y + box.height))
            if node.disabled:
                out.set_disabled()
            if node.modal:
                out.set_modal()
            if node.checked is not None:
                out.set_toggled(ak.Toggled.TRUE if node.checked else ak.Toggled.FALSE)
            if node.selected is not None:
                out.set_selected(node.selected)
            if node.expanded is not None:
                out.set_expanded(node.expanded)
            if node.role in _CLICKABLE:
                out.add_action(ak.Action.CLICK)
            if child_ids:
                out.set_children(child_ids)
            nodes.append((node_id, out))
            if node.focused:
                focus[0] = node_id
            return node_id

        content_id = visit(tree)
        # The window wraps whatever the view produced, so the root is always a
        # WINDOW with a title however the interface itself is structured.
        window_id = counter[0]
        window = ak.Node(ak.Role.WINDOW)
        window.set_label(self._window_title or self._toolkit_name)
        window.set_children([content_id])
        nodes.append((window_id, window))
        root_id = window_id
        self._targets = targets

        ak_tree = ak.Tree(root_id)
        ak_tree.toolkit_name = self._toolkit_name
        ak_tree.toolkit_version = self._toolkit_version
        update = ak.TreeUpdate(focus[0])
        update.tree = ak_tree
        update.nodes = nodes
        return update
