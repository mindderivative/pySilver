"""PageHost: a single-active-child container, switched by name.

The gap this closes: pySilver's view format has no conditional include or
computed path (`spec/include.py`'s own docstring calls that out
deliberately), so there was no way to say "mount exactly one of these
children, chosen by a signal." `PageHost` is that widget -- not a workaround
built from what already exists (a `Stack` with everything alive and hidden
would have kept every inactive page's animations ticking and, worse, kept a
`Terminal` page's real shell process running in the background forever), but
a real, narrow addition: exactly one child is ever "live."

**`value:` follows the exact convention `Tabs`/`NavigationRail`/
`SegmentedButton` already use** (`navigation.py`'s `_SelectionContainer`) --
the name of the active child. `default:` (new, `WidgetSpec.default`, plain
and unTemplated) names a fallback shown whenever `value:` doesn't match any
declared child -- unset, a typo, a signal not yet initialised.

**All children are built eagerly, by the ordinary `build_element` recursion
-- deliberately.** Construction alone has no side effects for any widget in
this catalogue today (checked directly: `TerminalElement`'s PTY spawns from
`set_ticker()`, never `__init__`), so building every page's element tree up
front costs only a little memory, and it means switching back to a
previously-visited page reuses the same object rather than re-parsing YAML.
What is genuinely gated is *aliveness*: only the active child is exposed
through the public `children` property, so every mechanism that already
propagates by walking `self.children` -- `set_ticker`, `set_text_engine`,
`set_image_atlas`, `paint`, `walk_elements` (and therefore `find`),
`dispose` -- automatically reaches only the active page, for free, with no
changes to any of those methods. A hidden page never animates, never
paints, and a hidden `Terminal` page holds no shell process.

**Switching disposes the outgoing page and re-arms the incoming one.**
`dispose()` tears down its `Effect` and any running animations (already true
of every element); calling `set_ticker`/`set_text_engine`/`set_image_atlas`
and `mounter()` (see `ElementMixin.mounter`) on it again afterward correctly
revives it -- confirmed for `TerminalElement` specifically:
`set_ticker` -> `_ensure_started()`'s only guard is `self._session is not
None`, which `dispose()` cleared, so navigating back to a `Terminal` page
spawns a fresh shell rather than reusing a stale one. Everything that is
*not* tied to being alive -- a `SpinBox`'s current number, a `Checkbox`'s
local state -- simply survives, because the object itself is never rebuilt.

**`self.mounter(page)` is what makes a page's own `{{ }}` bindings and
`handlers:` work at all.** `App.mount()`'s one-time walk
(`root.walk_elements()`) only ever reaches elements that already existed
when it ran; by design, a page other than whichever is active at that moment
is invisible to it (`children` filters it out). `mounter` is `App`'s own
per-element mount work, propagated down the tree the same way `ticker`/
`text_engine`/`image_atlas` already are, so activating a page runs the
identical bind-and-resolve-handlers step `App.mount()` did for everything
else, scoped to just that one subtree.
"""

from __future__ import annotations

from typing import Any, override

from ..layout import Constraints, LayoutNode, Offset, Size
from ..spec import WidgetSpec
from ..tree.element import ElementMixin
from .base import _StyledMixin

__all__ = ["PageHostElement"]


class PageHostElement(_StyledMixin, LayoutNode):
    def __init__(self, spec: WidgetSpec) -> None:
        LayoutNode.__init__(self)
        self.init_element(spec)
        self._active: Any | None = None
        #: The name last activated -- `""` before the first layout pass ever
        #: runs, which no real page is ever named, so the first real target
        #: always compares unequal and triggers the initial activation.
        self._active_name: str = ""

    @override
    def configure(self) -> None:
        """Nothing style-derived to capture -- `value:`/`default:` are read
        fresh from `self._value`/`self.spec` on every layout pass instead,
        matching `_SelectionContainer.apply_selection`'s own idiom."""

    # ------------------------------------------------------------- activity

    @override
    @property
    def children(self) -> tuple[Any, ...]:
        """Only the active page -- see the module docstring. `self._children`
        (the private list every declared page was added to, unconditionally,
        by the ordinary `build_element` recursion) is where a dormant page
        actually lives; this is what everything else in the tree sees."""
        return (self._active,) if self._active is not None else ()

    def _find_page(self, name: str) -> Any | None:
        return next((c for c in self._children if getattr(c, "name", None) == name), None)

    def page(self, name: str) -> Any | None:
        """A built page's own root element, by name, whether or not it is
        currently active.

        `find()` cannot reach a dormant page -- `children` filters it out on
        purpose (see the module docstring) -- but every page is still built
        eagerly at mount time, so application code that needs to reach into
        one before it is ever navigated to (pushing an initial `Video` frame,
        for instance) can start its own `find()` from here instead of from
        `app.root`.
        """
        return self._find_page(name)

    def _activate(self, name: str) -> None:
        if self._active is not None:
            self._active.dispose()
            self._active = None
        page = self._find_page(name)
        if page is not None:
            page.set_ticker(self.ticker)
            page.set_text_engine(self.text_engine)
            page.set_image_atlas(self.image_atlas)
            self.mounter(page)
        self._active = page
        self._active_name = name

    def _sync_active(self) -> None:
        target = self._value.strip()
        if not target or self._find_page(target) is None:
            target = (self.spec.default or "").strip()
        if target != self._active_name:
            self._activate(target)

    # -------------------------------------------------------------- layout

    @override
    def perform_layout(self, constraints: Constraints) -> Size:
        self._sync_active()
        outer = self.sized(constraints, self.style)
        size = outer.constrain(
            Size(
                outer.max_width if outer.has_bounded_width else 0.0,
                outer.max_height if outer.has_bounded_height else 0.0,
            )
        )
        if self._active is not None:
            self._active.layout(Constraints.tight(size))
            self._active.offset = Offset(0.0, 0.0)
        return size

    # ------------------------------------------------------------- lifecycle

    @override
    def dispose(self) -> None:
        """Disposes every page this host ever built, not only the active
        one -- `self.children` (the filtered public property) would miss
        every dormant page, leaking its subscriptions."""
        if self._effect is not None:
            self._effect.dispose()
            self._effect = None
        for animation in self._animations.values():
            self.ticker.discard(animation)
        for child in self._children:
            if isinstance(child, ElementMixin):
                child.dispose()
