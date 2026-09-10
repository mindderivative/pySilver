"""The overlay layer: placement, modality, scrim, dismissal, hit testing."""

from __future__ import annotations

import pytest

from pysilver import App, Signal, Theme
from pysilver.paint import DisplayList
from pysilver.runtime.events import EventType, KeyEvent, PointerEvent
from pysilver.runtime.overlay import SCRIM_OPACITY
from pysilver.theme import Palette

PAL = Palette(Theme(dark=True))


def make(overlays, root_children=None, **signals):
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 20, "spacing": 10},
            "children": root_children
            if root_children is not None
            else [
                {
                    "name": "btn",
                    "widget": "Button",
                    "text": "Open",
                    "style": {"width": 150, "height": 40},
                }
            ],
        },
        "overlays": overlays,
    }
    app = App(view, theme=Theme(dark=True))
    app.expose(**signals)
    app.mount()
    app.update()
    return app


def dialog(**style):
    base = {"width": 200, "height": 120, "placement": "center"}
    base.update(style)
    return {"name": "dlg", "widget": "Card", "open": "{{ show.get() }}", "style": base}


def paint(app) -> DisplayList:
    dl = DisplayList()
    app.paint(dl)
    return dl


# ------------------------------------------------------------- declaration


def test_overlays_are_not_part_of_the_root_tree() -> None:
    """A dialog must not be laid out or clipped by whatever opened it."""
    app = make([dialog()], show=Signal(True))
    assert "dlg" not in [e.name for e in app.root.walk_elements()]
    assert app.overlays.find("dlg") is not None


def test_hidden_by_default() -> None:
    app = make([dialog()], show=Signal(False))
    assert app.overlays.visible() == []


def test_open_binding_shows_it() -> None:
    show = Signal(False)
    app = make([dialog()], show=show)
    show.set(True)
    app.update()
    assert [e.element.name for e in app.overlays.visible()] == ["dlg"]


def test_overlay_contributes_nothing_to_root_layout() -> None:
    closed = make([dialog()], show=Signal(False))
    opened = make([dialog()], show=Signal(True))
    assert closed.root.size == opened.root.size
    assert closed.root.find("btn").offset == opened.root.find("btn").offset


# ---------------------------------------------------------------- placement


def test_centred_placement() -> None:
    app = make([dialog()], show=Signal(True))
    entry = app.overlays.visible()[0]
    window = app.logical_size()
    rect = entry.rect()
    assert rect.x == pytest.approx((window.width - rect.width) / 2)
    assert rect.y == pytest.approx((window.height - rect.height) / 2)


@pytest.mark.parametrize("edge", ["top", "bottom", "left", "right"])
def test_edge_placements_stay_inside_the_window(edge: str) -> None:
    app = make([dialog(placement=edge)], show=Signal(True))
    rect = app.overlays.visible()[0].rect()
    window = app.logical_size()
    assert rect.x >= 0 and rect.y >= 0
    assert rect.right <= window.width and rect.bottom <= window.height


def test_anchored_overlay_sits_below_its_anchor() -> None:
    app = make([dialog(placement="anchor", anchor="btn", height=60)], show=Signal(True))
    rect = app.overlays.visible()[0].rect()
    anchor = app.root.find("btn").absolute_rect()
    assert rect.y >= anchor.bottom


def test_anchored_overlay_flips_above_when_it_would_overflow() -> None:
    """A menu that runs off the bottom is useless, so anchoring flips it.

    The anchor sits near the bottom of the window (pushed there by an
    expanding `Spacer`, as `test_a_submenu_flips_to_the_left_when_it_would_
    overflow` does on the other axis), and the overlay is sized to fit in the
    room above it but not the room below -- the only way to tell "flipped
    above" apart from "clamped to the top because it fits nowhere", which is
    what an anchor near the *top* of the window (as below) always produces
    regardless of whether the flip itself works.
    """
    app = make(
        [dialog(placement="anchor", anchor="btn", height=300)],
        root_children=[
            {"widget": "Spacer", "style": {"height": "expand"}},
            {
                "name": "btn",
                "widget": "Button",
                "text": "Open",
                "style": {"width": 150, "height": 40},
            },
        ],
        show=Signal(True),
    )
    rect = app.overlays.visible()[0].rect()
    anchor = app.root.find("btn").absolute_rect()
    assert rect.bottom <= anchor.y
    assert rect.y >= 0


def test_an_overlay_too_tall_for_either_side_still_starts_on_screen() -> None:
    """Too tall to fit below the anchor *or* above it: clamped rather than
    left with a negative origin. The anchor sits near the top here, so there
    is no room above it either -- this is the one placement an anchored
    overlay can never actually flip into."""
    app = make(
        [dialog(placement="anchor", anchor="btn", height=2000)],
        show=Signal(True),
    )
    rect = app.overlays.visible()[0].rect()
    assert rect.y >= 0


def test_missing_anchor_falls_back_rather_than_crashing() -> None:
    app = make([dialog(placement="anchor", anchor="nonexistent")], show=Signal(True))
    assert app.overlays.visible()[0].rect().y >= 0


# -------------------------------------------------------------- submenus


def _menu_with_submenu(*, sub_open: str = "true", sub_style: dict | None = None) -> list:
    """A main Menu with one plain item and one submenu trigger, plus the
    submenu itself -- declared second, anchored to the trigger's name."""
    return [
        {
            "name": "main",
            "widget": "Menu",
            "open": "true",
            "style": {"anchor": "btn"},
            "children": [
                {"name": "cut", "widget": "MenuItem", "text": "Cut"},
                {
                    "name": "recent",
                    "widget": "MenuItem",
                    "text": "Open Recent",
                    "style": {"has_submenu": True},
                },
            ],
        },
        {
            "name": "sub",
            "widget": "Menu",
            "open": sub_open,
            "style": {"anchor": "recent", **(sub_style or {})},
            "children": [{"widget": "MenuItem", "text": "report.docx"}],
        },
    ]


def test_a_submenu_anchors_to_an_item_inside_its_parent_overlay() -> None:
    """`recent` lives inside the `main` Menu's own overlay tree, not the main
    tree -- resolving it at all is the point (see `OverlayHost._anchored`)."""
    app = make(_menu_with_submenu())
    sub = next(e for e in app.overlays.visible() if e.element.name == "sub")
    assert sub.rect().width > 0.0


def test_a_submenu_opens_beside_its_trigger_not_below_the_whole_menu() -> None:
    app = make(_menu_with_submenu())
    trigger = app.overlays.find("recent")
    sub = next(e for e in app.overlays.visible() if e.element.name == "sub")
    trigger_rect = trigger.absolute_rect()
    assert sub.rect().x >= trigger_rect.right
    assert sub.rect().y == pytest.approx(trigger_rect.y)


def test_a_submenu_flips_to_the_left_when_it_would_overflow() -> None:
    """The trigger sits near the window's right edge, so a submenu with real
    (but not window-exceeding) width has room to its left and not its right.
    """
    app = make(
        _menu_with_submenu(sub_style={"width": 300}),
        root_children=[
            {
                "widget": "Horizontal",
                "style": {"width": "expand"},
                "children": [
                    {"widget": "Spacer", "style": {"width": "expand"}},
                    {"name": "btn", "widget": "Button", "text": "Open", "style": {"height": 40}},
                ],
            }
        ],
    )
    trigger = app.overlays.find("recent")
    sub = next(e for e in app.overlays.visible() if e.element.name == "sub")
    assert sub.rect().x < trigger.absolute_rect().x
    assert sub.rect().x >= 0.0


def test_a_submenu_positions_correctly_on_the_very_first_paint() -> None:
    """A submenu open on the same frame its parent first appears used to
    anchor against the parent's stale (zero) offset for exactly one frame,
    since only `paint` set it -- not `layout`, which runs first and is where
    a submenu's own anchor is resolved. Fixed in `OverlayHost.layout`."""
    app = make(_menu_with_submenu())
    first = paint(app)
    first_origin = next(e for e in app.overlays.entries if e.element.name == "sub").origin
    second = paint(app)
    second_origin = next(e for e in app.overlays.entries if e.element.name == "sub").origin
    assert first_origin == second_origin
    assert len(first) == len(second)


# ------------------------------------------------------------------- paint


def test_scrim_is_emitted_at_the_m3_opacity() -> None:
    app = make([dialog(scrim=True, modal=True)], show=Signal(True))
    scrims = [
        s
        for s in paint(app).view
        if int(s["flags"][2]) == PAL.index("scrim")
        and abs(float(s["fill"][3]) - SCRIM_OPACITY) < 1e-4
    ]
    assert len(scrims) == 1


def test_scrim_covers_the_window_exactly() -> None:
    """Not an arbitrarily large quad -- that wastes fill and hurts precision."""
    app = make([dialog(scrim=True, modal=True)], show=Signal(True))
    window = app.logical_size()
    scrim = next(s for s in paint(app).view if int(s["flags"][2]) == PAL.index("scrim"))
    assert float(scrim["rect"][2]) == pytest.approx(window.width)
    assert float(scrim["rect"][3]) == pytest.approx(window.height)


def test_no_scrim_without_the_flag() -> None:
    app = make([dialog(modal=True)], show=Signal(True))
    assert not any(int(s["flags"][2]) == PAL.index("scrim") for s in paint(app).view)


def test_overlay_paints_above_the_tree() -> None:
    app = make([dialog(scrim=True, modal=True)], show=Signal(True))
    dl = paint(app)
    scrim_index = next(i for i, s in enumerate(dl.view) if int(s["flags"][2]) == PAL.index("scrim"))
    # The root background is instance 0; the scrim comes after it.
    assert scrim_index > 0


def test_closed_overlay_paints_nothing() -> None:
    closed = len(paint(make([dialog()], show=Signal(False))))
    opened = len(paint(make([dialog()], show=Signal(True))))
    assert opened > closed


# -------------------------------------------------------------- hit testing


def test_click_inside_an_overlay_hits_it() -> None:
    app = make([dialog(modal=True)], show=Signal(True))
    rect = app.overlays.visible()[0].rect()
    path = app.dispatcher.hit_path(rect.x + 10, rect.y + 10)
    assert path and path[-1].name == "dlg"


def test_modal_blocks_the_tree_beneath() -> None:
    """Otherwise a click on the scrim falls through to the blocked interface."""
    app = make([dialog(modal=True, scrim=True)], show=Signal(True))
    assert app.dispatcher.hit_path(25, 25) == []


def test_non_modal_lets_the_tree_through() -> None:
    app = make([dialog(modal=False)], show=Signal(True))
    assert app.dispatcher.hit_path(25, 25) != []


def test_closed_overlay_does_not_block() -> None:
    app = make([dialog(modal=True)], show=Signal(False))
    assert app.dispatcher.hit_path(25, 25) != []


# --------------------------------------------------------------- dismissal


def test_escape_dismisses_the_top_overlay() -> None:
    app = make([dialog(modal=True)], show=Signal(True))
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Escape"))
    app.dispatcher.drain()
    app.update()
    assert app.overlays.visible() == []


def test_escape_does_not_dismiss_a_non_dismissable_overlay() -> None:
    app = make([dialog(modal=True, dismissable=False)], show=Signal(True))
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Escape"))
    app.dispatcher.drain()
    app.update()
    assert len(app.overlays.visible()) == 1


def test_clicking_outside_a_modal_dismisses_it() -> None:
    app = make([dialog(modal=True, scrim=True)], show=Signal(True))
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=5, y=5))
    app.dispatcher.drain()
    app.update()
    assert app.overlays.visible() == []


def test_clicking_inside_does_not_dismiss() -> None:
    app = make([dialog(modal=True)], show=Signal(True))
    rect = app.overlays.visible()[0].rect()
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=rect.x + 10, y=rect.y + 10))
    app.dispatcher.drain()
    app.update()
    assert len(app.overlays.visible()) == 1


def test_reopening_after_a_dismissal_works() -> None:
    """A dismissal must not outlive the state change that closed it."""
    show = Signal(True)
    app = make([dialog(modal=True)], show=show)
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Escape"))
    app.dispatcher.drain()
    app.update()
    assert app.overlays.visible() == []

    show.set(False)
    app.update()
    show.set(True)
    app.update()
    assert len(app.overlays.visible()) == 1


def test_escape_dismisses_before_clearing_focus() -> None:
    app = make([dialog(modal=True)], show=Signal(True))
    app.dispatcher.focus(app.root.find("btn"), keyboard=True)
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Escape"))
    app.dispatcher.drain()
    app.update()
    assert app.overlays.visible() == []
    assert app.dispatcher.focused is not None, "focus was cleared as well"


# ------------------------------------------------------------------ z-order


def test_declaration_order_is_z_order() -> None:
    a = {"name": "a", "widget": "Card", "open": "true", "style": {"width": 100, "height": 100}}
    b = {"name": "b", "widget": "Card", "open": "true", "style": {"width": 100, "height": 100}}
    app = make([a, b])
    assert [e.element.name for e in app.overlays.visible()] == ["a", "b"]


def test_topmost_overlay_wins_hit_testing() -> None:
    a = {"name": "a", "widget": "Card", "open": "true", "style": {"width": 200, "height": 200}}
    b = {"name": "b", "widget": "Card", "open": "true", "style": {"width": 200, "height": 200}}
    app = make([a, b])
    rect = app.overlays.visible()[0].rect()
    path = app.dispatcher.hit_path(rect.x + 10, rect.y + 10)
    assert path[-1].name == "b"


# ----------------------------------------------------------------- handlers


def test_handlers_inside_an_overlay_resolve() -> None:
    calls: list[str] = []
    view = {
        "root": {"name": "root", "widget": "Vertical", "children": []},
        "overlays": [
            {
                "name": "dlg",
                "widget": "Card",
                "open": "true",
                "style": {"width": 200, "height": 100},
                "children": [
                    {
                        "name": "ok",
                        "widget": "Button",
                        "text": "OK",
                        "style": {"width": 80, "height": 40},
                        "handlers": {"on_click": "confirm"},
                    }
                ],
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    app.handler(lambda e: calls.append("ok"))  # type: ignore[arg-type]
    app._handlers["confirm"] = lambda e: calls.append("confirm")
    app.mount()
    app.update()
    ok = app.overlays.find("ok")
    # `absolute_rect()` is already fully absolute after `update()` -- the
    # overlay root's own offset is set during `layout()`, not only `paint()`
    # (see `OverlayHost.layout`), so no manual `entry.origin` addition here.
    rect = ok.absolute_rect()
    x = rect.x + 5
    y = rect.y + 5
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=x, y=y))
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=x, y=y))
    app.dispatcher.drain()
    assert "confirm" in calls


# ------------------------------------------------------- single-child guard


def test_single_child_container_rejects_extra_children() -> None:
    """It lays out only the first but paints them all, so extras would overlap."""
    with pytest.raises(ValueError, match="single child"):
        App(
            {
                "name": "r",
                "widget": "Vertical",
                "children": [
                    {
                        "name": "c",
                        "widget": "Card",
                        "children": [
                            {"name": "a", "widget": "Text", "text": "one"},
                            {"name": "b", "widget": "Text", "text": "two"},
                        ],
                    }
                ],
            },
            theme=Theme(dark=True),
        )


def test_vertical_sized_only_on_width_does_not_fill_vertically() -> None:
    """A Vertical's main axis is its HEIGHT; keying fill off `width` made a
    menu stretch to the bottom of the window."""
    app = App(
        {
            "name": "r",
            "widget": "Vertical",
            "style": {"background": "surface"},
            "children": [
                {
                    "name": "c",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": [
                        {
                            "name": "a",
                            "widget": "ListItem",
                            "text": "one",
                            "style": {"width": "expand"},
                        },
                        {
                            "name": "b",
                            "widget": "ListItem",
                            "text": "two",
                            "style": {"width": "expand"},
                        },
                    ],
                }
            ],
        },
        theme=Theme(dark=True),
    )
    app.mount()
    app.update()
    assert app.root.find("c").size.height == pytest.approx(112.0)


# ------------------------------------------------- dismissal and the deadlock


def _dialog_app(*, dismissable: bool = True, on_dismiss: bool = True):
    """A modal dialog whose openness is bound, which is how one is written."""
    from pysilver import App, Signal, Theme

    style: dict = {"modal": True, "scrim": True}
    if not dismissable:
        style["dismissable"] = False
    node: dict = {
        "name": "confirm",
        "widget": "Dialog",
        "text": "Delete this?",
        "supporting_text": "Cannot be undone.",
        "open": "{{ confirming.get() }}",
        "style": style,
        "children": [
            {"name": "ok", "widget": "Button", "text": "OK", "style": {"width": 80, "height": 40}}
        ],
    }
    if on_dismiss:
        node["handlers"] = {"on_dismiss": "close"}
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"width": "expand", "height": "expand"},
            "children": [
                {"name": "ask", "widget": "Button", "text": "Delete", "style": {"width": 100}}
            ],
        },
        "overlays": [node],
    }
    confirming = Signal(False, name="confirming")
    app = App(view, theme=Theme(dark=True))
    app.expose(confirming=confirming)

    def close(event: object) -> None:
        confirming.set(False)

    app.handler(close)
    app.mount()
    app.update()
    confirming.set(True)
    app.update()
    return app, confirming


def test_a_dismissed_overlay_is_never_left_painted_but_unclickable() -> None:
    """The bug this fixes, in the state it produced.

    A press outside marked the overlay dismissed, which removed it from hit
    testing and modality -- but `showing` read only the `open:` binding, so it
    kept painting at full opacity. The result was a dialog you could see, could
    not click, and could not close, because the buttons that would clear its
    signal were underneath it. Clicks landed on the tree behind instead.
    """
    app, _ = _dialog_app(on_dismiss=False)
    host = app.overlays
    host.handle_press(2.0, 2.0)
    for _ in range(6):
        app.update()
    painted = [e.element.name for e in host.rendered()]
    clickable = [e.element.name for e in host.visible()]
    assert not (painted and not clickable), f"painted {painted} while hit testing saw {clickable}"


def test_dismissing_a_bound_overlay_tells_the_application() -> None:
    """`open:` is bound, so the runtime closing it is only a request -- the
    binding still says open. Without `on_dismiss` there is nothing that can
    actually close it, and it would come straight back."""
    app, confirming = _dialog_app()
    assert confirming.get() is True
    app.overlays.handle_press(2.0, 2.0)
    for _ in range(4):
        app.update()
    assert confirming.get() is False, "the handler never ran"
    assert app.overlays.visible() == []


def test_a_dismissed_dialog_can_be_reopened() -> None:
    """The other half of the deadlock: a dismissal that outlived the signal
    meant the button that opened it stopped working."""
    app, confirming = _dialog_app()
    app.overlays.handle_press(2.0, 2.0)
    for _ in range(4):
        app.update()
    confirming.set(True)
    for _ in range(3):
        app.update()
    assert [e.element.name for e in app.overlays.visible()] == ["confirm"]


def test_a_locked_dialog_ignores_a_click_outside_and_keeps_focus() -> None:
    """The other behaviour worth having: `dismissable: false` dims the parent,
    blocks it, and closes only through the dialog's own buttons."""
    from pysilver.runtime.events import EventType, PointerEvent

    app, confirming = _dialog_app(dismissable=False, on_dismiss=False)
    inside = app.overlays.entries[0].element.find("ok")
    app.dispatcher.focus(inside)

    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=2.0, y=2.0))
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=2.0, y=2.0))
    app.dispatcher.drain()
    app.update()

    assert app.dispatcher.focused is inside, "focus escaped a locked dialog"
    assert [e.element.name for e in app.overlays.visible()] == ["confirm"]
    assert app.overlays.has_modal
    assert confirming.get() is True


def test_a_modal_swallows_clicks_meant_for_the_tree_beneath() -> None:
    app, _ = _dialog_app(dismissable=False, on_dismiss=False)
    assert app.dispatcher.hit_path(2.0, 2.0) == [], "a click reached the blocked tree"
