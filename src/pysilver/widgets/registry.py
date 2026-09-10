"""The widget factory: maps a `WidgetKind` to its Element class and builds
element (sub)trees from a Spec tree.

Separated from `base.py` on purpose. `base.py` is meant to hold primitive
widget definitions -- as central and as small a surface as `layout/`'s own
(ARCHITECTURE.md 5.3, 5.4) -- but the registry has to reference every leaf
widget module to build itself, which is a different job with a different,
much wider set of dependencies. Kept apart, `base.py` stays reasoned-about
in isolation; only this module needs to know the whole widget catalogue
exists.
"""

from __future__ import annotations

from typing import Any

from ..spec import WidgetKind, WidgetSpec
from .base import (
    ButtonElement,
    ContainerElement,
    HorizontalElement,
    IconElement,
    LinkElement,
    SpacerElement,
    StackElement,
    TextElement,
    VerticalElement,
)

__all__ = ["build_element", "create_element"]


def _material_registry() -> dict[WidgetKind, type]:
    """Imported lazily: most of these modules import helpers from base.py,
    and this keeps that a one-directional dependency at module-load time."""
    from . import buttongroup as bg
    from . import canvas as cv
    from . import carousel as ca
    from . import codeeditor as ce
    from . import datepicker as dp
    from . import dock as dk
    from . import image as im
    from . import material as m
    from . import navigation as n
    from . import nodegraph as ng
    from . import overlays as o
    from . import pagehost as ph
    from . import scroll as sc
    from . import search as se
    from . import slider as sl
    from . import splitbutton as sb
    from . import terminal as tm
    from . import textfield as tf
    from . import timepicker as tp
    from . import video as vd

    return {
        WidgetKind.CARD: m.CardElement,
        WidgetKind.DIVIDER: m.DividerElement,
        WidgetKind.SHAPE: m.ShapeElement,
        WidgetKind.CHECKBOX: m.CheckboxElement,
        WidgetKind.RADIO: m.RadioElement,
        WidgetKind.SWITCH: m.SwitchElement,
        WidgetKind.CHIP: m.ChipElement,
        WidgetKind.ICON_BUTTON: m.IconButtonElement,
        WidgetKind.FAB: m.FabElement,
        WidgetKind.BADGE: m.BadgeElement,
        WidgetKind.SPIN_BOX: m.SpinBoxElement,
        WidgetKind.SLIDER: sl.SliderElement,
        WidgetKind.PAGINATION: m.PaginationElement,
        WidgetKind.ACCORDION: m.AccordionElement,
        WidgetKind.NAVIGATION_RAIL: n.NavigationRailElement,
        WidgetKind.NAV_ITEM: n.NavItemElement,
        WidgetKind.TOP_APP_BAR: n.TopAppBarElement,
        WidgetKind.STATUS_BAR: n.StatusBarElement,
        WidgetKind.DOCK_SPLIT: dk.DockSplitElement,
        WidgetKind.DOCK_GROUP: dk.DockGroupElement,
        WidgetKind.DOCK_PANEL: dk.DockPanelElement,
        WidgetKind.TABS: n.TabsElement,
        WidgetKind.TAB: n.TabElement,
        WidgetKind.SEGMENTED_BUTTON: n.SegmentedButtonElement,
        WidgetKind.SEGMENT: n.SegmentElement,
        WidgetKind.LIST_ITEM: n.ListItemElement,
        WidgetKind.TREE_VIEW: n.TreeViewElement,
        WidgetKind.TREE_ITEM: n.TreeItemElement,
        WidgetKind.LINEAR_PROGRESS: n.LinearProgressElement,
        WidgetKind.CIRCULAR_PROGRESS: n.CircularProgressElement,
        WidgetKind.DIALOG: o.DialogElement,
        WidgetKind.POPOVER: o.PopoverElement,
        WidgetKind.MENU: o.MenuElement,
        WidgetKind.MENU_ITEM: o.MenuItemElement,
        WidgetKind.TOOLTIP: o.TooltipElement,
        WidgetKind.SNACKBAR: o.SnackbarElement,
        WidgetKind.BOTTOM_SHEET: o.BottomSheetElement,
        WidgetKind.SIDE_SHEET: o.SideSheetElement,
        WidgetKind.SCROLL_VIEW: sc.ScrollViewElement,
        WidgetKind.CAROUSEL: ca.CarouselElement,
        WidgetKind.CAROUSEL_ITEM: ca.CarouselItemElement,
        WidgetKind.TEXT_FIELD: tf.TextFieldElement,
        WidgetKind.CANVAS: cv.CanvasElement,
        WidgetKind.IMAGE: im.ImageElement,
        WidgetKind.VIDEO: vd.VideoElement,
        WidgetKind.NODE_GRAPH: ng.NodeGraphElement,
        WidgetKind.NODE: ng.NodeElement,
        WidgetKind.CODE_EDITOR: ce.CodeEditorElement,
        WidgetKind.TERMINAL: tm.TerminalElement,
        WidgetKind.PAGE_HOST: ph.PageHostElement,
        WidgetKind.SEARCH_BAR: se.SearchBarElement,
        WidgetKind.SPLIT_BUTTON: sb.SplitButtonElement,
        WidgetKind.DATE_PICKER: dp.DatePickerElement,
        WidgetKind.TIME_PICKER: tp.TimePickerElement,
        WidgetKind.BUTTON_GROUP: bg.ButtonGroupElement,
    }


_REGISTRY: dict[WidgetKind, type] = {
    WidgetKind.CONTAINER: ContainerElement,
    WidgetKind.HORIZONTAL: HorizontalElement,
    WidgetKind.VERTICAL: VerticalElement,
    WidgetKind.STACK: StackElement,
    WidgetKind.BUTTON: ButtonElement,
    WidgetKind.LINK: LinkElement,
    WidgetKind.TEXT: TextElement,
    WidgetKind.SPACER: SpacerElement,
    WidgetKind.ICON: IconElement,
}

_REGISTRY_COMPLETE = False


def create_element(spec: WidgetSpec) -> Any:
    """Construct the element for one spec node (no children)."""
    global _REGISTRY_COMPLETE
    if not _REGISTRY_COMPLETE:
        _REGISTRY.update(_material_registry())
        _REGISTRY_COMPLETE = True
    return _REGISTRY[spec.widget](spec)


def build_element(spec: WidgetSpec) -> Any:
    """Construct a whole element subtree from a spec subtree."""
    element = create_element(spec)
    for child_spec in spec.children:
        element.add_child(build_element(child_spec))
    return element
