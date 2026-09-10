"""The accessibility tree: what an interface *means*, apart from how it looks.

This module is the half that belongs to the toolkit: what the interface means,
with no notion of any platform. `accesskit_bridge` is the half that belongs to
the platform, and is optional -- an application binds it with
`App.bind_accessibility` and pays for a native wheel only if it wants one.
**Without a bridge bound, nothing reaches a screen reader**; the tree is still
worth having, because it is what a bridge is handed and because it lets a test
ask for "the button named Confirm" rather than for a pixel.

Today the bridge covers AT-SPI on Linux. Windows and macOS need their own
AccessKit platform wheels and are untested here, which `available()` says
rather than leaving to be discovered.

**Roles are sourced where M3 states one**, which is not often -- a text field is
"textbox", a progress indicator has the "role of 'progressbar'", a list is a
"List box", a navigation item's role is "tab", and a navigation *container's*
"role is not announced". Everything else follows ARIA convention and is marked
as such, so the difference stays visible instead of being smoothed over.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Final

from ..layout import Rect

__all__ = ["AccessibleNode", "Bridge", "accessibility_tree", "role_for"]

#: Widget kind -> ARIA role. Sourced entries carry the quote; the rest are the
#: conventional ARIA role for the equivalent control and say so.
ROLES: Final[dict[str, str]] = {
    # --- stated by M3
    "TextField": "textbox",  # "The role is 'textbox'"
    # ARIA's own dedicated role for exactly this control, distinct from a
    # plain "textbox" -- COMPONENT_SEARCH.md gives no role of its own, but
    # ARIA's real, standard "searchbox" role is the closest anatomy and is
    # used directly rather than approximated with "textbox".
    "SearchBar": "searchbox",
    # No M3 component -- see CodeEditorElement's own docstring. ARIA's
    # "textbox" (with aria-multiline) is the same role a multi-line HTML
    # <textarea> reports, which is the closest real anatomy this has.
    "CodeEditor": "textbox",
    # No M3 component -- see TerminalElement's own docstring. Unlike most
    # gaps in this module, this one has a precise real answer rather than an
    # approximation: AT-SPI/AccessKit's own role vocabulary has a dedicated
    # "terminal" role, verified against the installed accesskit package
    # (`accesskit.Role.TERMINAL`) rather than assumed.
    "Terminal": "terminal",
    "LinearProgress": "progressbar",  # "role of 'progressbar'"
    "CircularProgress": "progressbar",  # "role of 'progressbar'"
    "NavItem": "tab",  # "The role is 'tab'"
    "Tab": "tab",  # "The role is 'tab'"
    "ListItem": "option",  # a list is a "List box", so its items are options
    # ARIA convention: no single role exists for "a strip of page numbers",
    # since M3 has no Pagination component to name one for either. The
    # individual page buttons are not separately exposed -- this is one
    # opaque control, the same shape as SpinBox's two internal buttons.
    "Pagination": "navigation",
    # --- ARIA convention
    "Button": "button",
    "Chip": "button",  # ...except a filter chip, which toggles -- see `_node_for`
    "IconButton": "button",
    "Fab": "button",
    # No dedicated ARIA role exists for a split button's two independently-
    # clickable regions as one compound control -- treated the same opaque
    # way `Pagination`'s own two internal buttons are, above.
    "SplitButton": "button",
    # ARIA convention for a calendar grid -- no M3-stated role, and no
    # dedicated ARIA "datepicker" role exists either.
    "DatePicker": "grid",
    # No dedicated ARIA "timepicker" role either; a fieldset-like grouping of
    # independent hour/minute/period controls is what "group" is for.
    "TimePicker": "group",
    "Link": "link",
    # ARIA's own name for exactly this control -- no M3 page to quote a role
    # from, since SpinBox has no M3 component at all (see its docstring).
    "SpinBox": "spinbutton",
    # Stated directly, unlike most of this module's approximations:
    # COMPONENT_SLIDERS.md's own accessibility page says "It should have the
    # slider role" -- ARIA's own dedicated role, used verbatim.
    "Slider": "slider",
    # A submenu trigger (`style.has_submenu`) should additionally carry
    # `aria-haspopup`/`aria-expanded`, per ARIA convention -- not modelled:
    # `_node_for` sees one element at a time and has no visibility into
    # whether some *other* overlay happens to be anchored to this one.
    "MenuItem": "menuitem",
    "Checkbox": "checkbox",
    "Radio": "radio",
    "Switch": "switch",
    "Segment": "radio",  # a segmented button is a single-choice set
    "Text": "text",
    "Card": "group",
    "Divider": "separator",
    "Dialog": "dialog",
    # M3 has no Popover component; its persistent rich tooltip is one in
    # every behavioural sense but ARIA's own "tooltip" role forbids
    # interactive content, and a Popover can hold buttons. A non-modal
    # dialog is the ARIA shape that actually fits.
    "Popover": "dialog",
    # M3 has no Accordion component either -- see `AccordionElement`'s
    # docstring. ARIA's disclosure-widget convention is a button that
    # controls an adjacent region, which is exactly its shape here.
    "Accordion": "button",
    # Also no M3 Tree component -- see AccordionElement's docstring for the
    # same gap. ARIA has dedicated tree/treeitem roles, unlike Accordion's
    # borrowed "button", so those are used directly rather than approximated.
    "TreeView": "tree",
    "TreeItem": "treeitem",
    "Menu": "menu",
    "Tooltip": "tooltip",
    "Snackbar": "status",  # "announced ... but don't trap focus"
    "Badge": "status",
    "BottomSheet": "dialog",
    "SideSheet": "dialog",
    "TopAppBar": "banner",
    # The footer counterpart to TopAppBar's "banner" landmark -- a status bar
    # is a persistent informational region, not a transient announcement, so
    # this is "contentinfo" rather than Snackbar/Badge's "status".
    "StatusBar": "contentinfo",
    "Tabs": "tablist",
    # No M3 component for any of the three; see DockSplitElement's own
    # docstring. ARIA has precise roles for both shapes, so no approximation
    # is needed the way Accordion/TreeView had to borrow "button"/"tree".
    "DockGroup": "tablist",
    "DockPanel": "tabpanel",
    "DockSplit": "separator",  # WAI-ARIA's own Window Splitter pattern
    # ARIA/HTML5 convention for a canvas element: opaque raster content with
    # no structure of its own to expose. An application drawing something
    # that DOES carry meaning names its own better role via `aria_label`-
    # style metadata once that exists; not modelled today, same gap every
    # other widget's alt-text story has.
    "Canvas": "img",
    "Image": "img",
    # No dedicated ARIA role exists for video either -- HTML-AAM exposes
    # `<video>` as "video" through platform accessibility APIs, but that is
    # not a role the abstract ARIA taxonomy itself defines. Treated the same
    # opaque-visual-content way `Canvas`/`Image` are rather than asserting a
    # role this session could not verify against the spec directly.
    "Video": "img",
    "SegmentedButton": "radiogroup",  # M3 calls the equivalent a "Radio group"
    "Carousel": "group",
    "CarouselItem": "group",
    "ScrollView": "group",  # ARIA has no scroll-region role
    # No M3 component either -- see NodeGraphElement's own docstring for the
    # same gap. The W3C Graphics-ARIA module defines exactly this shape:
    # "graphics-document" for a diagram's container, "graphics-object" for
    # one figure within it -- used directly rather than approximated.
    "NodeGraph": "graphics-document",
    "Node": "graphics-object",
    "Container": "group",
    "Horizontal": "group",
    "Vertical": "group",
    "Stack": "group",
    # No M3 component -- see PageHostElement's own docstring. Structurally a
    # plain box holding one child at a time, the same shape as Container/
    # Horizontal/Vertical/Stack above, not a navigation container with a stated "not
    # announced" role like NavigationRail below -- so it gets the same
    # generic "group" those get, rather than being silenced.
    "PageHost": "group",
}

#: Kinds a screen reader should never hear about. A navigation *container's*
#: "role is not announced" per M3; the rest are layout or decoration with
#: nothing to say that their children do not say better.
SILENT: Final[frozenset[str]] = frozenset(
    {
        "Spacer",
        "Icon",
        "NavigationRail",
        # "Button groups are invisible containers" (COMPONENT_BUTTON_GROUPS.md)
        # and "the button group container is not a focusable element" -- its
        # buttons carry the meaning, the same reasoning as the nav container
        # kinds above.
        "ButtonGroup",
        # A Shape is decoration. It has no label and nothing to do, so a reader
        # stopping on it would announce "group" and waste the user's time. An
        # application that means a shape to be meaningful should give it a Text
        # or wrap it in a control, exactly as it would for an Icon.
        "Shape",
    }
)

#: Kinds with a dedicated `label:` field, read as the accessible name instead
#: of `text:`. These widgets' `text:` used to double as a Material Symbols
#: glyph name (fixed by giving them their own `icon:` field) -- announcing
#: "home" instead of "Home" was the sort of bug that only shows up when
#: someone actually listens to it. "Icon" itself is not listed: it is in
#: `SILENT`, so `_node_for` never calls `_label_of` on one at all.
ICON_NAMED: Final[frozenset[str]] = frozenset({"IconButton", "Fab", "NavItem"})

#: Kinds whose `checked` is meaningful. Anything else reports None, which is
#: what distinguishes an unchecked checkbox from a button.
CHECKABLE: Final[frozenset[str]] = frozenset({"Checkbox", "Radio", "Switch"})

#: Kinds whose `selected` is meaningful.
SELECTABLE: Final[frozenset[str]] = frozenset(
    {"Tab", "NavItem", "Segment", "ListItem", "MenuItem", "TreeItem", "DockPanel"}
)


def role_for(kind: str) -> str | None:
    """The ARIA role for a widget kind, or None if it should not be announced."""
    if kind in SILENT:
        return None
    return ROLES.get(kind, "group")


@dataclass(slots=True)
class AccessibleNode:
    """One node of the semantic tree.

    A plain snapshot rather than a live view of the element: a bridge pushes
    updates on its own schedule, and a test wants something stable to assert
    against.
    """

    role: str
    name: str = ""
    #: Detail announced after the name -- a text field's supporting text, which
    #: M3 says "should have its own accessibility label".
    description: str = ""
    #: Current content, for anything that has one: a field's text, a progress
    #: indicator's fraction.
    value: str = ""
    bounds: Rect = field(default_factory=Rect)
    focused: bool = False
    disabled: bool = False
    #: Tri-state. None means "not checkable at all", which is how an unchecked
    #: checkbox differs from a button.
    checked: bool | None = None
    selected: bool | None = None
    expanded: bool | None = None
    modal: bool = False
    #: The view file's `name:`, so a test can find a node the way an author
    #: refers to it. Never announced -- it is a developer handle.
    key: str | None = None
    children: list[AccessibleNode] = field(default_factory=list)

    def walk(self) -> Iterator[AccessibleNode]:
        yield self
        for child in self.children:
            yield from child.walk()

    def find(
        self,
        *,
        role: str | None = None,
        name: str | None = None,
        key: str | None = None,
    ) -> AccessibleNode | None:
        """First node matching any combination of role, name and key.

        The everyday use: ask for "the button called Confirm" instead of for a
        rectangle at some coordinate. `key` matches the view file's `name:`,
        which is how a test refers to a control that has no visible label.
        """
        for node in self.walk():
            if (
                (role is None or node.role == role)
                and (name is None or node.name == name)
                and (key is None or node.key == key)
            ):
                return node
        return None


def _label_of(element: Any) -> str:
    """What a reader should call this element.

    Never the view file's `name:` -- that is a developer handle, and announcing
    "sw_primary" would be worse than silence.

    For an icon-bearing control `text:` no longer carries anything at all
    (its glyph name moved to `icon:`), so the label comes from `label:`
    instead. An icon-only control with no `label:` therefore has no
    accessible name at all, and reports one rather than reading
    "chevron_right" at somebody.
    """
    order = ("label",) if str(element.spec.widget) in ICON_NAMED else ("text", "supporting")
    for attr in order:
        value = getattr(element, attr, "") or ""
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _node_for(element: Any) -> AccessibleNode | None:
    """Snapshot one element, or None if it should not be announced."""
    kind = str(element.spec.widget)
    role = role_for(kind)
    if role is None:
        return None

    style = element.spec.style
    #: A filter chip toggles, so it reads as a checkbox rather than a button --
    #: the other chip variants act on a press and do not.
    filter_chip = kind == "Chip" and style.variant == "filter"
    if kind == "Chip":
        role = "checkbox" if filter_chip else "button"

    node = AccessibleNode(
        role=role,
        name=_label_of(element),
        bounds=element.absolute_rect(),
        focused=bool(getattr(element.state, "focused", False)),
        disabled=bool(getattr(element, "effective_disabled", False)),
        checked=bool(element.checked) if (kind in CHECKABLE or filter_chip) else None,
        selected=bool(element.selected) if kind in SELECTABLE else None,
        modal=bool(style.modal),
        key=element.spec.name,
    )

    if kind == "TextField":
        # "Text field supporting text should have its own accessibility label",
        # so it is a description rather than being glued onto the name.
        node.name = (element.spec.text or "").strip()
        node.description = (getattr(element, "supporting", "") or "").strip()
        node.value = getattr(element, "content", "") or ""
    elif kind == "CodeEditor":
        # No supporting-text/label anatomy to read -- see the widget's own
        # docstring: `text:` is unused, the same as `Canvas`/`ScrollView`.
        node.value = getattr(element, "content", "") or ""
    elif role in ("progressbar", "spinbutton") or kind in ("Pagination", "DockSplit"):
        # aria-valuemin/-valuemax have no field on AccessibleNode to carry
        # them -- not modelled, same honesty as the rest of this module.
        node.value = str(element.number)
    elif role in ("dialog", "menu", "tooltip", "status"):
        node.expanded = bool(element.is_open)
    elif kind == "Accordion":
        # Keyed on kind, not on role == "button" -- a plain Button shares that
        # role and has no `is_open`/`checked` disclosure state to read.
        node.expanded = bool(element.checked)
    elif kind == "TreeItem":
        # A leaf reports no expanded state at all, same as an unchecked box
        # differs from a plain button -- there is nothing here to expand.
        node.expanded = bool(element.checked) if element.children else None
    return node


def accessibility_tree(root: Any, overlays: Any = None) -> AccessibleNode:
    """Snapshot the semantic tree for a mounted element tree.

    A silent element is skipped but its children are kept and lifted to its
    parent, so a `Horizontal` wrapping three buttons does not bury them behind a node
    that says only "group" -- and a `Spacer` disappears entirely rather than
    becoming an empty announcement.

    Visible overlays are appended to the root. A dialog is not a child of
    whatever it covers, and a reader should reach it last, which is where the
    modal flag then tells it to stay.
    """

    def build(element: Any) -> list[AccessibleNode]:
        children: list[AccessibleNode] = []
        for child in element.children:
            if hasattr(child, "spec"):
                children.extend(build(child))
        node = _node_for(element)
        if node is None:
            return children
        node.children = children
        return [node]

    built = build(root)
    tree = built[0] if built else AccessibleNode(role="group")
    if overlays is not None:
        for entry in overlays.visible():
            tree.children.extend(build(entry.element))
    return tree


class Bridge:
    """The seam a platform adapter plugs into.

    A bridge is handed the tree when it changes and pushes it to AT-SPI, UIA
    or NSAccessibility. `accesskit_bridge.AccessKitBridge` implements it for
    AT-SPI; it is an optional extra because it brings a native wheel, so an
    application opts in with `App.bind_accessibility` rather than paying for it
    by default.

    This base raises, so a bridge that forgets to implement `update` fails
    loudly rather than silently announcing nothing.
    """

    def update(self, tree: AccessibleNode) -> None:  # pragma: no cover - a seam
        raise NotImplementedError
