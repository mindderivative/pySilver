"""Golden-image baselines: the whole pipeline, compared pixel by pixel.

These catch what property assertions cannot -- a shader regression that still
produces "some antialiased coverage in roughly the right place". Baselines are
committed; see conftest.py for how to regenerate them.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from pysilver import App, Theme
from pysilver.paint import DisplayList

pytestmark = pytest.mark.gpu

SEED = "#6750A4"


def test_primitives_baseline(render_scene, assert_golden) -> None:
    """The box and shadow kinds: plain, bordered, clipped, and a soft shadow.

    Not every SDF kind -- glyph, image, arc, polygon and segment each get
    their own baseline instead (`text`, `image`/`video`, `arc`, `shapes`,
    `canvas`)."""

    def paint(dl: DisplayList) -> None:
        dl.add_shadow(
            24,
            24,
            100,
            60,
            blur=10.0,
            offset=(0.0, 4.0),
            color=(0.0, 0.0, 0.0, 0.5),
            radii=(16,) * 4,
        )
        dl.add_box(24, 24, 100, 60, color=(0.80, 0.75, 0.92, 1.0), radii=(16,) * 4)
        dl.add_box(
            150,
            24,
            100,
            60,
            color=(0.25, 0.22, 0.30, 1.0),
            radii=(28, 4, 28, 4),
            border_width=3.0,
            border_color=(0.80, 0.75, 0.92, 1.0),
        )
        dl.add_box(
            24,
            110,
            226,
            50,
            color=(0.55, 0.45, 0.85, 1.0),
            clip=(60, 110, 150, 50),
            clip_radii=(24,) * 4,
        )

    frame, _ = render_scene(paint, width=280, height=180, theme=Theme(seed=SEED, dark=True))
    assert_golden("primitives", frame)


def test_text_baseline(render_scene, assert_golden) -> None:
    """Shaped text through the atlas: ligatures, kerning, two sizes."""
    _, engine = render_scene(
        lambda dl: None, width=360, height=120, theme=Theme(seed=SEED, dark=True)
    )

    def paint(dl: DisplayList) -> None:
        engine.text.emit(
            dl,
            engine.text.layout("Hamburgefons fi fl", px=26),
            x=16,
            y=14,
            token=engine.palette.index("primary"),
        )
        engine.text.emit(
            dl,
            engine.text.layout("AVATAR To Wa. quick brown fox", px=14),
            x=16,
            y=62,
            token=engine.palette.index("on_surface"),
        )

    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("text", np.asarray(engine.canvas.draw()))


def test_wrapped_text_baseline(render_scene, assert_golden) -> None:
    """Line breaking and alignment."""
    _, engine = render_scene(
        lambda dl: None, width=300, height=160, theme=Theme(seed=SEED, dark=True)
    )
    body = "The quick brown fox jumps over the lazy dog and keeps running"

    def paint(dl: DisplayList) -> None:
        engine.text.emit(
            dl,
            engine.text.layout(body, px=14, max_width=260),
            x=20,
            y=16,
            token=engine.palette.index("on_surface"),
        )
        engine.text.emit(
            dl,
            engine.text.layout("centred", px=14, max_width=260, alignment="center"),
            x=20,
            y=110,
            token=engine.palette.index("primary"),
        )

    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("text_wrapped", np.asarray(engine.canvas.draw()))


def test_widget_tree_baseline(render_scene, assert_golden) -> None:
    """A real App through the full four-tree pipeline."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "style": {
            "background": "surface",
            "padding": 16,
            "spacing": 12,
            "width": "expand",
            "height": "expand",
            "cross_alignment": "stretch",
        },
        "children": [
            {
                "name": "title",
                "widget": "Text",
                "text": "Gallery",
                "style": {"color": "on_surface", "font_size": 20},
            },
            {
                "name": "card",
                "widget": "Container",
                "style": {
                    "height": 70,
                    "background": "surface_container_high",
                    "corner_radius": 16,
                    "padding": 14,
                    "border": {"width": 1, "color": "outline_variant"},
                    "shadow": {"blur": 12, "offset_y": 3},
                },
                "children": [
                    {
                        "name": "body",
                        "widget": "Text",
                        "text": "Elevated card",
                        "style": {"color": "on_surface_variant", "font_size": 14},
                    }
                ],
            },
            {
                "name": "row",
                "widget": "Horizontal",
                "style": {"height": 44, "spacing": 10, "width": "expand"},
                "children": [
                    {
                        "name": "primary",
                        "widget": "Button",
                        "text": "Confirm",
                        "style": {
                            "width": 140,
                            "height": 44,
                            "background": "primary",
                            "color": "on_primary",
                            "corner_radius": 22,
                        },
                    },
                    {
                        "name": "tonal",
                        "widget": "Button",
                        "text": "Cancel",
                        "style": {
                            "width": 120,
                            "height": 44,
                            "background": "secondary_container",
                            "color": "on_secondary_container",
                            "corner_radius": 22,
                        },
                    },
                ],
            },
        ],
    }
    _, engine = render_scene(
        lambda dl: None, width=340, height=220, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("widget_tree", np.asarray(engine.canvas.draw()))


def test_light_theme_baseline(render_scene, assert_golden) -> None:
    """The same tokens in the light scheme -- catches palette regressions."""
    theme = Theme(seed=SEED, dark=False)
    _, engine = render_scene(lambda dl: None, width=260, height=120, theme=theme)

    def paint(dl: DisplayList) -> None:
        for i, token in enumerate(["primary", "secondary", "tertiary", "error"]):
            dl.add_box(16 + i * 58, 16, 48, 48, token=engine.palette.index(token), radii=(12,) * 4)
        engine.text.emit(
            dl,
            engine.text.layout("Light scheme", px=16),
            x=16,
            y=76,
            token=engine.palette.index("on_surface"),
        )

    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("light_theme", np.asarray(engine.canvas.draw()))


def _import_gallery_app() -> Any:
    """Import `examples/gallery/app.py` as a module, restoring `sys.path`."""
    import sys
    from pathlib import Path

    gallery = Path(__file__).resolve().parents[2] / "examples" / "gallery"
    sys.path.insert(0, str(gallery))
    try:
        import app as demo

        return demo
    finally:
        sys.path.remove(str(gallery))


def test_gallery_baseline(render_scene, assert_golden) -> None:
    """The gallery's default shell: Home page active, rail collapsed.

    A `PageHost`-driven shell shows one page at a time by design, so no
    single frame exercises every widget kind the way the old one-scroll
    gallery did -- that breadth now lives in each widget's own unit tests
    and in `test_gallery_advanced_page_baseline` below for the one page
    (Terminal) that needs a real running `App` to render deterministically.
    This is still the corpus test for the shell itself: Container, Horizontal,
    Vertical, Stack, Text, Button, Spacer, PageHost, and the nav rail together,
    so a regression anywhere in the four-tree pipeline shows up here.
    """
    demo = _import_gallery_app()

    _, engine = render_scene(
        lambda dl: None, width=900, height=820, theme=Theme(seed=SEED, dark=True)
    )
    demo.app.attach(engine)

    demo.gallery.clicks.set(3)
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("gallery", np.asarray(engine.canvas.draw()))


def test_gallery_advanced_page_baseline(render_scene, assert_golden) -> None:
    """The Advanced page: NodeGraph, CodeEditor, and a real Terminal.

    Terminal only spawns its shell once its page is actually active
    (`PageHost`'s whole reason for existing -- see `pagehost.py`), so unlike
    the old single-scroll gallery this needs an explicit navigation before
    the swapped-in `bittty` stand-in below has anything to attach to.
    """
    from bittty.devices.board import Board

    demo = _import_gallery_app()
    demo.gallery.current_page.set("advanced")

    _, engine = render_scene(
        lambda dl: None, width=900, height=820, theme=Theme(seed=SEED, dark=True)
    )
    demo.app.attach(engine)
    # `attach()` does not itself lay anything out -- that happens on the next
    # `draw_frame` -- so force one now, or `find("terminal_demo")` below would
    # still see whatever page was active before `current_page` changed.
    demo.app.update()

    # The `update()` above already laid the page out for real, so
    # `terminal_demo` has a genuine live PTY session by now -- stop it and
    # swap in an always-alive stand-in before painting, the same determinism
    # fix `test_terminal_baseline` uses, needed here because `(cols, rows)`
    # isn't known until this page's own flexible layout actually ran.
    term = demo.app.root.find("terminal_demo")
    assert term is not None, "the advanced page must be the one PageHost is showing"
    if term._session is not None:
        term._session.stop()

    class _AlwaysAlive:
        alive = True

        def drain(self) -> bytes:
            return b""

        def resize(self, cols: int, rows: int) -> None:
            pass

    term._session = _AlwaysAlive()
    term._board = Board(command="/bin/sh", width=term._cols, height=term._rows)
    term._feed(b"$ \x1b[32mgit status\x1b[0m\r\n")
    term._feed(b"\x1b[41mon branch main\x1b[0m\r\n")

    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("gallery_advanced", np.asarray(engine.canvas.draw()))


def test_icons_baseline(render_scene, assert_golden) -> None:
    """Material Symbols through the glyph atlas, across both live axes."""
    _, engine = render_scene(
        lambda dl: None, width=420, height=170, theme=Theme(seed=SEED, dark=True)
    )

    def paint(dl: DisplayList) -> None:
        on_surface = engine.palette.index("on_surface")
        primary = engine.palette.index("primary")
        row = [
            "home",
            "search",
            "settings",
            "person",
            "favorite",
            "star",
            "check_circle",
            "delete",
            "share",
            "menu",
        ]
        for i, name in enumerate(row):
            engine.text.emit_icon(dl, name, x=14 + i * 38, y=16, size=24, token=on_surface)
        # FILL 0 -> 1
        for i in range(5):
            engine.text.emit_icon(
                dl, "favorite", x=14 + i * 44, y=62, size=32, fill=i / 4, token=primary
            )
        # weight 200 -> 700
        for i, w in enumerate((200, 300, 400, 500, 700)):
            engine.text.emit_icon(
                dl,
                "bolt",
                x=14 + i * 44,
                y=112,
                size=32,
                weight=w,
                token=engine.palette.index("tertiary"),
            )

    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("icons", np.asarray(engine.canvas.draw()))


def test_focus_ring_baseline(render_scene, assert_golden) -> None:
    """The ring must follow each control's shape -- a rectangle around a circle
    reads as a bug, and only a rendered image catches that."""
    from pysilver.runtime.events import EventType, KeyEvent

    view = {
        "name": "root",
        "widget": "Vertical",
        "style": {"background": "surface", "padding": 16},
        "children": [
            {
                "name": "row",
                "widget": "Horizontal",
                "style": {"height": 56, "spacing": 20, "cross_alignment": "center"},
                "children": [
                    {
                        "name": "btn",
                        "widget": "Button",
                        "text": "Filled",
                        "style": {"width": 110, "height": 40, "variant": "filled"},
                    },
                    {"name": "cb", "widget": "Checkbox", "value": "true"},
                    {"name": "rd", "widget": "Radio", "value": "true"},
                    {"name": "sw", "widget": "Switch", "value": "false"},
                    {
                        "name": "ib",
                        "widget": "IconButton",
                        "icon": "favorite",
                        "style": {"variant": "filled_tonal"},
                    },
                    {"name": "fab", "widget": "Fab", "icon": "add", "style": {"variant": "small"}},
                ],
            }
        ],
    }
    _, engine = render_scene(
        lambda dl: None, width=520, height=88, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.update()
    # Tab three times: focus lands on the radio, whose ring must be circular.
    for _ in range(3):
        app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Tab"))
    app.dispatcher.drain()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("focus_ring", np.asarray(engine.canvas.draw()))


def test_navigation_baseline(render_scene, assert_golden) -> None:
    """Wave 2 in one frame: rail, app bar, tabs, progress, segments, lists."""
    from pysilver import Signal

    view = {
        "name": "root",
        "widget": "Horizontal",
        "style": {"background": "surface", "width": "expand", "height": "expand"},
        "children": [
            {
                "name": "rail",
                "widget": "NavigationRail",
                "value": "{{ dest.get() }}",
                "collapsed": "true",
                "style": {"spacing": 8, "padding": [0, 12]},
                "children": [
                    {
                        "name": "r_home",
                        "widget": "NavItem",
                        "icon": "home",
                        "label": "Home",
                    },
                    {
                        "name": "r_search",
                        "widget": "NavItem",
                        "icon": "search",
                        "label": "Search",
                    },
                    {
                        "name": "r_set",
                        "widget": "NavItem",
                        "icon": "settings",
                        "label": "Settings",
                    },
                ],
            },
            {
                "name": "main",
                "widget": "Vertical",
                "style": {"width": "expand"},
                "children": [
                    {
                        "name": "bar",
                        "widget": "TopAppBar",
                        "text": "Wave 2",
                        "style": {"width": "expand"},
                    },
                    {
                        "name": "tabs",
                        "widget": "Tabs",
                        "value": "{{ tab.get() }}",
                        "style": {"width": "expand"},
                        "children": [
                            {"name": "t1", "widget": "Tab", "text": "Overview"},
                            {"name": "t2", "widget": "Tab", "text": "Details"},
                            {"name": "t3", "widget": "Tab", "text": "History"},
                        ],
                    },
                    {
                        "name": "prog",
                        "widget": "LinearProgress",
                        "value": "0.62",
                        "style": {"width": "expand"},
                    },
                    {
                        "name": "body",
                        "widget": "Vertical",
                        "style": {"padding": 16, "spacing": 14, "width": "expand"},
                        "children": [
                            {
                                "name": "seg",
                                "widget": "SegmentedButton",
                                "value": "{{ seg.get() }}",
                                "children": [
                                    {"name": "s1", "widget": "Segment", "text": "Day"},
                                    {"name": "s2", "widget": "Segment", "text": "Week"},
                                    {"name": "s3", "widget": "Segment", "text": "Month"},
                                ],
                            },
                            {
                                "name": "li1",
                                "widget": "ListItem",
                                "text": "Single line item",
                                "style": {"width": "expand"},
                            },
                            {"name": "dv", "widget": "Divider", "style": {"width": "expand"}},
                            {
                                "name": "li2",
                                "widget": "ListItem",
                                "text": "Two line item",
                                "supporting_text": "With supporting text beneath",
                                "style": {"width": "expand"},
                            },
                        ],
                    },
                ],
            },
        ],
    }
    _, engine = render_scene(
        lambda dl: None, width=680, height=400, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.expose(dest=Signal("r_search"), tab=Signal("t2"), seg=Signal("s2"))
    app.attach(engine)
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("navigation", np.asarray(engine.canvas.draw()))


def test_overlay_baseline(render_scene, assert_golden) -> None:
    """A modal dialog over a 32% scrim, and an anchored menu beside it."""
    from pysilver import Signal

    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 20, "spacing": 12},
            "children": [
                {
                    "name": "open_btn",
                    "widget": "Button",
                    "text": "Open dialog",
                    "style": {"width": 170, "height": 40},
                },
                {
                    "name": "menu_btn",
                    "widget": "Button",
                    "text": "Menu",
                    "style": {"width": 120, "height": 40, "variant": "outlined"},
                },
                {
                    "name": "li",
                    "widget": "ListItem",
                    "text": "Background content",
                    "supporting_text": "Dimmed by the scrim",
                    "style": {"width": "expand"},
                },
            ],
        },
        "overlays": [
            {
                "name": "menu",
                "widget": "Card",
                "open": "true",
                "style": {
                    "width": 190,
                    "placement": "anchor",
                    "anchor": "menu_btn",
                    "variant": "filled",
                    "corner_radius": 4,
                    "padding": 0,
                },
                "children": [
                    {
                        "name": "mcol",
                        "widget": "Vertical",
                        "style": {"width": "expand"},
                        "children": [
                            {
                                "name": "m1",
                                "widget": "ListItem",
                                "text": "Rename",
                                "style": {"width": "expand"},
                            },
                            {
                                "name": "m2",
                                "widget": "ListItem",
                                "text": "Duplicate",
                                "style": {"width": "expand"},
                            },
                        ],
                    }
                ],
            },
            {
                "name": "dlg",
                "widget": "Card",
                "open": "{{ show.get() }}",
                "style": {
                    "width": 280,
                    "height": 140,
                    "placement": "center",
                    "modal": True,
                    "scrim": True,
                    "variant": "elevated",
                    "corner_radius": 28,
                    "padding": 24,
                },
                "children": [
                    {
                        "name": "dt",
                        "widget": "Text",
                        "text": "Modal dialog",
                        "style": {"font_size": 20},
                    }
                ],
            },
        ],
    }
    _, engine = render_scene(
        lambda dl: None, width=470, height=280, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.expose(show=Signal(True))
    app.attach(engine)
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("overlay", np.asarray(engine.canvas.draw()))


def test_overlay_components_baseline(render_scene, assert_golden) -> None:
    """The six real M3 overlay components, rather than hand-built stand-ins.

    Deliberately separate from `test_overlay_baseline`, which stays as it is:
    that one proves the *host* can float an arbitrary widget, this one proves
    the components themselves render to their M3 anatomy. A side sheet, an
    anchored menu, a tooltip and a snackbar are placed at once because their
    placements do not collide.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 20, "spacing": 12},
            "children": [
                {
                    "name": "top",
                    "widget": "Horizontal",
                    "style": {"width": "expand", "height": 40, "spacing": 12},
                    "children": [
                        {
                            "name": "menu_btn",
                            "widget": "Button",
                            "text": "Actions",
                            "style": {"width": 130, "height": 40, "variant": "outlined"},
                        },
                        {"name": "gap", "widget": "Spacer", "style": {"width": 30}},
                        {
                            "name": "tip_btn",
                            "widget": "IconButton",
                            "icon": "info",
                            "style": {"variant": "standard"},
                        },
                    ],
                },
            ],
        },
        "overlays": [
            {
                "name": "menu",
                "widget": "Menu",
                "open": "true",
                "style": {"placement": "anchor", "anchor": "menu_btn", "width": 200},
                "children": [
                    {"name": "cut", "widget": "MenuItem", "text": "Cut", "supporting_text": "^X"},
                    {"name": "copy", "widget": "MenuItem", "text": "Copy", "supporting_text": "^C"},
                    {"name": "paste", "widget": "MenuItem", "text": "Paste"},
                ],
            },
            {
                "name": "tip",
                "widget": "Tooltip",
                "text": "More information",
                "open": "true",
                "style": {"placement": "anchor", "anchor": "tip_btn"},
            },
            {
                "name": "sheet",
                "widget": "SideSheet",
                "open": "true",
                "style": {"placement": "right", "width": 190},
                "children": [
                    {
                        "name": "sheet_title",
                        "widget": "Text",
                        "text": "Side sheet",
                        "style": {"font_size": 16},
                    }
                ],
            },
            {
                "name": "snack",
                "widget": "Snackbar",
                "text": "Item archived",
                "supporting_text": "Undo",
                "open": "true",
                "style": {"placement": "bottom", "width": 320},
            },
        ],
    }
    _, engine = render_scene(
        lambda dl: None, width=560, height=320, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("overlay_components", np.asarray(engine.canvas.draw()))


def test_dialog_baseline(render_scene, assert_golden) -> None:
    """A modal Dialog over its 32% scrim, shrink-wrapped around its content.

    Its own frame: a centred modal dialog would sit on top of the
    bottom-anchored snackbar in the frame above.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 20, "spacing": 12},
            "children": [
                {
                    "name": "bg",
                    "widget": "ListItem",
                    "text": "Background content",
                    "supporting_text": "Dimmed by the 32% scrim",
                    "style": {"width": "expand"},
                }
            ],
        },
        "overlays": [
            {
                "name": "dlg",
                "widget": "Dialog",
                "text": "Delete this item?",
                "supporting_text": "This action cannot be undone, and the item "
                "will not be recoverable.",
                "open": "true",
                "style": {"modal": True, "scrim": True, "width": 360},
                "children": [
                    {
                        "name": "actions",
                        "widget": "Horizontal",
                        "style": {
                            "width": "expand",
                            "height": 40,
                            "spacing": 8,
                            "main_alignment": "end",
                        },
                        "children": [
                            {
                                "name": "cancel",
                                "widget": "Button",
                                "text": "Cancel",
                                "style": {"width": 90, "height": 40, "variant": "text"},
                            },
                            {
                                "name": "delete",
                                "widget": "Button",
                                "text": "Delete",
                                "style": {"width": 90, "height": 40, "variant": "filled"},
                            },
                        ],
                    }
                ],
            },
        ],
    }
    _, engine = render_scene(
        lambda dl: None, width=460, height=300, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("dialog", np.asarray(engine.canvas.draw()))


def test_bottom_sheet_baseline(render_scene, assert_golden) -> None:
    """A BottomSheet with its drag handle, flush with the window's bottom edge.

    Its own frame too -- it shares the bottom placement with the snackbar.
    The handle is drawn but not draggable; see `BottomSheetElement`.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 20},
            "children": [
                {
                    "name": "bg",
                    "widget": "Text",
                    "text": "Background content",
                    "style": {"font_size": 16},
                }
            ],
        },
        "overlays": [
            {
                "name": "sheet",
                "widget": "BottomSheet",
                "open": "true",
                "style": {"handle": True, "scrim": True, "modal": True},
                "children": [
                    {
                        "name": "sheet_title_pad",
                        "widget": "Container",
                        "style": {"padding": [16, 16, 16, 4]},
                        "children": [
                            {
                                "name": "sheet_title",
                                "widget": "Text",
                                "text": "Bottom sheet",
                                "style": {"font_size": 16},
                            }
                        ],
                    },
                    {
                        "name": "sheet_item",
                        "widget": "ListItem",
                        "text": "An action",
                        "supporting_text": "With supporting text",
                        "style": {"width": "expand"},
                    },
                ],
            },
        ],
    }
    _, engine = render_scene(
        lambda dl: None, width=440, height=300, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("bottom_sheet", np.asarray(engine.canvas.draw()))


def test_scroll_baseline(render_scene, assert_golden) -> None:
    """A scrolled viewport: rows clipped at both edges, scrollbar part-way down.

    The mid-scroll position is the point -- it proves the clip is real (the
    first visible row is cut off at the top, not merely absent) and that the
    scrollbar thumb tracks the offset.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16, "spacing": 10},
            "children": [
                {
                    "name": "heading",
                    "widget": "Text",
                    "text": "Scrollable list",
                    "style": {"font_size": 16},
                },
                {
                    "name": "sv",
                    "widget": "ScrollView",
                    "style": {
                        "height": 180,
                        "width": "expand",
                        "background": "surface_container",
                        "corner_radius": 12,
                    },
                    "children": [
                        {
                            "name": "col",
                            "widget": "Vertical",
                            "style": {"width": "expand"},
                            "children": [
                                {
                                    "name": f"row{i}",
                                    "widget": "ListItem",
                                    "text": f"Item {i}",
                                    "supporting_text": "Supporting text",
                                    "style": {"width": "expand"},
                                }
                                for i in range(10)
                            ],
                        }
                    ],
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=380, height=260, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    app.root.find("sv").set_scroll(90.0)
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("scroll", np.asarray(engine.canvas.draw()))


def test_arc_baseline(render_scene, assert_golden) -> None:
    """Circular progress at several values, thicknesses and a tint.

    The top row is the widget at 0/25/50/75/100%, which is what verifies the
    sweep direction: M3 fills clockwise from 12 o'clock, so 25% must light the
    right-hand quadrant and nothing else. The bottom row varies `thickness`
    (10 vs 2) and swaps both the active and track colour via `color`/
    `background`. The raw arc primitive itself -- an offset start angle and a
    full ring's seamless join -- is exercised directly in `test_arc.py` and
    `tests/golden/test_primitives.py`, not here.

    This baseline is captured under lavapipe (CI's own software Vulkan, run
    with `WGPU_FORCE_ADAPTER=cpu`), not a real GPU -- confirmed on 2026-09-09
    that the two rasterise this specific arc's antialiased edge ~0.2%
    differently (stable and reproducible either direction, not flaky), just
    past `TOLERANCE`. CI is the environment this baseline has to agree with,
    so a real-GPU run of this one test locally showing the same small,
    expected delta is not a regression -- regenerate under lavapipe
    (`WGPU_FORCE_ADAPTER=cpu LIBGL_ALWAYS_SOFTWARE=1 PYSILVER_REGEN_GOLDEN=1
    pytest tests/golden/test_baselines.py::test_arc_baseline -m gpu`) if it
    ever needs updating again.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16, "spacing": 16},
            "children": [
                {
                    "name": "row",
                    "widget": "Horizontal",
                    "style": {"height": 48, "spacing": 14, "width": "expand"},
                    "children": [
                        {
                            "name": f"p{int(v * 100)}",
                            "widget": "CircularProgress",
                            "value": str(v),
                        }
                        for v in (0.0, 0.25, 0.5, 0.75, 1.0)
                    ],
                },
                {
                    "name": "row2",
                    "widget": "Horizontal",
                    "style": {"height": 56, "spacing": 14, "width": "expand"},
                    "children": [
                        {
                            "name": "thick",
                            "widget": "CircularProgress",
                            "value": "0.4",
                            "style": {"width": 56, "thickness": 10},
                        },
                        {
                            "name": "thin",
                            "widget": "CircularProgress",
                            "value": "0.65",
                            "style": {"width": 56, "thickness": 2},
                        },
                        {
                            "name": "tinted",
                            "widget": "CircularProgress",
                            "value": "0.85",
                            "style": {
                                "width": 56,
                                "color": "tertiary",
                                "background": "surface_container_highest",
                            },
                        },
                    ],
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=380, height=180, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("arc", np.asarray(engine.canvas.draw()))


def test_carousel_baseline(render_scene, assert_golden) -> None:
    """The three carousel layouts, with the multi-browse one advanced by two.

    The advanced strip is the interesting row: it shows a passed item clipped
    at the leading edge, the new large item snapped to the keyline, and the
    medium and small slots behind it -- which is the resize-and-snap behaviour
    M3 specifies, at rest.
    """

    def strip(name: str, variant: str, count: int = 6) -> dict:
        return {
            "name": name,
            "widget": "Carousel",
            "style": {"variant": variant, "height": 120, "width": "expand"},
            "children": [
                {
                    "name": f"{name}_{j}",
                    "widget": "CarouselItem",
                    "text": f"Item {j}",
                    "style": {"background": "primary_container" if j % 2 else "tertiary_container"},
                }
                for j in range(count)
            ],
        }

    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 8, "spacing": 8},
            "children": [
                strip("mb", "multi_browse"),
                strip("hero", "hero"),
                strip("adv", "multi_browse"),
                strip("mid", "multi_browse"),
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=440, height=540, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)

    clock = {"t": 0.0}
    app.clock = lambda: clock["t"]
    app.mount()
    app.paint(DisplayList())

    # Third strip: advanced two items and allowed to land, which is the layout
    # M3 actually specifies. Fourth: the same advance caught in flight, where
    # the items are between keyline sizes.
    app.root.find("adv").set_index(2)
    app.root.find("mid").set_index(1)
    app.paint(DisplayList())
    for _ in range(12):
        clock["t"] += 0.05
        app.paint(DisplayList())
        if app.root.find("adv").position >= 2.0:
            break

    # Restart the fourth strip's travel and stop part-way through it.
    app.root.find("mid").set_index(2)
    app.paint(DisplayList())
    clock["t"] += 0.09
    engine.canvas.request_draw(engine.draw_frame)

    assert_golden("carousel", np.asarray(engine.canvas.draw()))


def test_motion_baseline(render_scene, assert_golden) -> None:
    """Animated states, sampled at a fixed point rather than at rest.

    Determinism comes from ticking an exact delta instead of using wall-clock
    time: the switches are caught part-way through their 200ms travel and the
    indeterminate indicators part-way through a cycle, so the frame is
    reproducible while still showing motion actually applied.
    """
    from pysilver import Signal

    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16, "spacing": 14},
            "children": [
                {
                    "name": "switches",
                    "widget": "Horizontal",
                    "style": {"height": 32, "spacing": 16},
                    "children": [
                        {"name": "off", "widget": "Switch", "value": "false"},
                        {"name": "mid", "widget": "Switch", "value": "{{ flip.get() }}"},
                        {"name": "on", "widget": "Switch", "value": "true"},
                    ],
                },
                {
                    "name": "lin_i",
                    "widget": "LinearProgress",
                    "style": {"width": "expand"},
                },
                {
                    "name": "lin_d",
                    "widget": "LinearProgress",
                    "value": "0.6",
                    "style": {"width": "expand"},
                },
                {
                    "name": "circles",
                    "widget": "Horizontal",
                    "style": {"height": 48, "spacing": 20},
                    "children": [
                        {"name": "cir_i", "widget": "CircularProgress"},
                        {"name": "cir_d", "widget": "CircularProgress", "value": "0.6"},
                    ],
                },
            ],
        }
    }
    flip = Signal(False)
    _, engine = render_scene(
        lambda dl: None, width=360, height=260, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.expose(flip=flip)
    app.attach(engine)

    # Drive time by hand. `update()` ticks with a real frame delta, so a
    # wall-clock baseline would advance by however long the setup took and the
    # transition would be over before the frame was captured.
    clock = {"t": 0.0}
    app.clock = lambda: clock["t"]
    app.mount()

    # Paint the resting state first: `animated()` settles immediately on its
    # first call, having nothing to animate *from*, so a switch flipped before
    # it was ever painted arrives with no transition.
    app.paint(DisplayList())

    # Flipping and painting *starts* the transition -- this frame still shows
    # the resting position, because the retarget begins from it. The movement
    # happens on the frame after.
    flip.set(True)
    app.paint(DisplayList())

    # 30ms into a 200ms standard-eased transition. Sampled early on purpose:
    # `standard` is front-loaded, so by halfway the thumb is already ~85%
    # across and the frame would not look mid-transition at all.
    clock["t"] = 0.030
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("motion", np.asarray(engine.canvas.draw()))


def test_transitions_baseline(render_scene, assert_golden) -> None:
    """A dialog caught part-way through its entrance, over a partial scrim.

    Sampled 60ms into the 400ms emphasized-decelerate entrance. The scrim is
    visibly weaker than its settled 32%, which is the point: the fade is
    applied to the whole slice the overlay emitted, host-drawn scrim included.
    The button behind it is mid hover cross-fade at the same moment.
    """
    from pysilver import Signal

    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16, "spacing": 12},
            "children": [
                {
                    "name": "hovered",
                    "widget": "Button",
                    "text": "Hovered",
                    "style": {"width": 150, "height": 40, "variant": "filled_tonal"},
                },
                {
                    "name": "li",
                    "widget": "ListItem",
                    "text": "Background content",
                    "supporting_text": "Dimmed by a partial scrim",
                    "style": {"width": "expand"},
                },
            ],
        },
        "overlays": [
            {
                "name": "dlg",
                "widget": "Dialog",
                "text": "Delete this item?",
                "supporting_text": "Caught mid-entrance.",
                "open": "{{ show.get() }}",
                "style": {"modal": True, "scrim": True, "width": 300},
            }
        ],
    }
    show = Signal(False)
    _, engine = render_scene(
        lambda dl: None, width=420, height=280, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.expose(show=show)
    app.attach(engine)

    clock = {"t": 0.0}
    app.clock = lambda: clock["t"]
    app.mount()
    app.paint(DisplayList())  # resting frame establishes both animations

    show.set(True)
    app.root.find("hovered").state.hovered = True
    app.root.find("hovered").mark_needs_paint()
    app.paint(DisplayList())  # notices both changes; still at rest

    clock["t"] = 0.060  # 60ms into a 400ms entrance
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("transitions", np.asarray(engine.canvas.draw()))


def test_selection_controls_baseline(render_scene, assert_golden) -> None:
    """Checkbox, radio and filter chip: off, mid-transition, and on.

    The middle column is sampled 40ms into the 200ms transition M3 specifies
    for selection controls, so the checkbox container is half-filled, the radio
    dot half-grown, and the chip half-widened around its arriving checkmark.
    """
    from pysilver import Signal

    def column(name: str, value: str) -> dict:
        return {
            "name": name,
            "widget": "Vertical",
            "style": {"width": 120, "spacing": 14, "cross_alignment": "start"},
            "children": [
                {"name": f"{name}_cb", "widget": "Checkbox", "value": value},
                {"name": f"{name}_rd", "widget": "Radio", "value": value},
                {
                    "name": f"{name}_ch",
                    "widget": "Chip",
                    "text": "Filter",
                    "style": {"variant": "filter"},
                    "value": value,
                },
            ],
        }

    view = {
        "root": {
            "name": "root",
            "widget": "Horizontal",
            "style": {"background": "surface", "padding": 16, "spacing": 8},
            "children": [
                column("off", "false"),
                column("mid", "{{ flip.get() }}"),
                column("on", "true"),
            ],
        }
    }
    flip = Signal(False)
    _, engine = render_scene(
        lambda dl: None, width=400, height=150, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.expose(flip=flip)
    app.attach(engine)

    clock = {"t": 0.0}
    app.clock = lambda: clock["t"]
    app.mount()
    app.paint(DisplayList())  # resting frame establishes the animations
    flip.set(True)
    app.paint(DisplayList())  # notices the change and starts the transition

    clock["t"] = 0.040  # 40ms into 200ms
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("selection", np.asarray(engine.canvas.draw()))


def test_indicators_baseline(render_scene, assert_golden) -> None:
    """Tab, rail and segment indicators caught part-way between destinations.

    The tab indicator is the interesting one: it belongs to the container, so
    it travels between tabs and stretches on the way rather than disappearing
    from one and reappearing under another. Sampled 80ms into a 300ms move.
    """
    from pysilver import Signal

    view = {
        "root": {
            "name": "root",
            "widget": "Horizontal",
            "style": {"background": "surface", "spacing": 12},
            "children": [
                {
                    "name": "rail",
                    "widget": "NavigationRail",
                    "value": "{{ nav.get() }}",
                    "collapsed": "true",
                    "children": [
                        {
                            "name": "n1",
                            "widget": "NavItem",
                            "icon": "home",
                            "label": "Home",
                        },
                        {
                            "name": "n2",
                            "widget": "NavItem",
                            "icon": "search",
                            "label": "Search",
                        },
                        {
                            "name": "n3",
                            "widget": "NavItem",
                            "icon": "settings",
                            "label": "Settings",
                        },
                    ],
                },
                {
                    "name": "right",
                    "widget": "Vertical",
                    "style": {"width": "expand", "spacing": 20, "padding": 12},
                    "children": [
                        {
                            "name": "tabs",
                            "widget": "Tabs",
                            "value": "{{ tab.get() }}",
                            "style": {"width": "expand"},
                            "children": [
                                {"name": "t1", "widget": "Tab", "text": "One"},
                                {"name": "t2", "widget": "Tab", "text": "Two"},
                                {"name": "t3", "widget": "Tab", "text": "Three"},
                            ],
                        },
                        {
                            "name": "segs",
                            "widget": "SegmentedButton",
                            "value": "{{ seg.get() }}",
                            "children": [
                                {"name": "s1", "widget": "Segment", "text": "Day"},
                                {"name": "s2", "widget": "Segment", "text": "Week"},
                                {"name": "s3", "widget": "Segment", "text": "Month"},
                            ],
                        },
                    ],
                },
            ],
        }
    }
    tab, nav, seg = Signal("t1"), Signal("n1"), Signal("s1")
    _, engine = render_scene(
        lambda dl: None, width=460, height=220, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.expose(tab=tab, nav=nav, seg=seg)
    app.attach(engine)

    clock = {"t": 0.0}
    app.clock = lambda: clock["t"]
    app.mount()
    app.paint(DisplayList())  # resting frame establishes the animations

    tab.set("t3")
    nav.set("n3")
    seg.set("s3")
    app.paint(DisplayList())  # notices the changes and starts them

    clock["t"] = 0.080  # 80ms into a 300ms move
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("indicators", np.asarray(engine.canvas.draw()))


def test_app_bar_collapse_baseline(render_scene, assert_golden) -> None:
    """A large app bar half-collapsed over its scrolled list.

    Scroll-linked, so no clock is involved: setting the offset is enough, and
    the frame is reproducible without driving time. At half travel the
    headline sits between its expanded size and title-large, and the container
    is half-filled with `surface_container`.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface"},
            "children": [
                {
                    "name": "bar",
                    "widget": "TopAppBar",
                    "text": "Inbox",
                    "style": {"variant": "large", "collapses_with": "body", "width": "expand"},
                },
                {
                    "name": "body",
                    "widget": "ScrollView",
                    "style": {"height": "expand", "width": "expand"},
                    "children": [
                        {
                            "name": "col",
                            "widget": "Vertical",
                            "style": {"width": "expand"},
                            "children": [
                                {
                                    "name": f"row{i}",
                                    "widget": "ListItem",
                                    "text": f"Message {i}",
                                    "supporting_text": "Supporting text",
                                    "style": {"width": "expand"},
                                }
                                for i in range(10)
                            ],
                        }
                    ],
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=380, height=300, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.paint(DisplayList())
    app.root.find("body").set_scroll(44.0)  # half of the 88dp travel
    app.paint(DisplayList())
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("app_bar_collapse", np.asarray(engine.canvas.draw()))


def test_carousel_parallax_baseline(render_scene, assert_golden) -> None:
    """Item content panning relative to its container.

    Each item holds a two-tone block whose boundary sits at the content's
    centre. If the content were pinned to its item the boundary would land at
    every item's centre; parallax shifts it, one way at the leading edge and
    the other at the trailing one, so the boundaries fan across the strip.

    The item labels are drawn by the item itself, not by a child, so they do
    **not** pan -- M3 parallaxes the visual, not the caption.
    """

    def item(j: int) -> dict:
        return {
            "name": f"i{j}",
            "widget": "CarouselItem",
            "text": f"Item {j}",
            "children": [
                {
                    "name": f"row{j}",
                    "widget": "Horizontal",
                    "style": {"width": "expand", "height": "expand"},
                    "children": [
                        {
                            "name": f"a{j}",
                            "widget": "Container",
                            "style": {
                                "background": "primary_container",
                                "width": "50%",
                                "height": "expand",
                            },
                        },
                        {
                            "name": f"b{j}",
                            "widget": "Container",
                            "style": {
                                "background": "tertiary_container",
                                "width": "expand",
                                "height": "expand",
                            },
                        },
                    ],
                }
            ],
        }

    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 8, "spacing": 10},
            "children": [
                {
                    "name": "mb",
                    "widget": "Carousel",
                    "style": {"variant": "multi_browse", "height": 110, "width": "expand"},
                    "children": [item(j) for j in range(5)],
                },
                {
                    "name": "unc",
                    "widget": "Carousel",
                    "style": {"variant": "uncontained", "height": 110, "width": "expand"},
                    "children": [{**item(10 + j), "style": {"width": 150}} for j in range(5)],
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=440, height=260, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.paint(DisplayList())
    app.root.find("unc").set_scroll(70.0)  # part-way, so the pan differs per item
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("carousel_parallax", np.asarray(engine.canvas.draw()))


def test_disabled_baseline(render_scene, assert_golden) -> None:
    """Enabled controls beside their disabled counterparts.

    M3 replaces a disabled control's colours with `on_surface` — container at
    12%, content at 38% — rather than dimming what it had, so the filled and
    outlined buttons converge on the same look. The right column also shows a
    whole disabled container greying out the controls inside it.
    """

    def controls(suffix: str, disabled: str) -> dict:
        return {
            "name": f"col{suffix}",
            "widget": "Vertical",
            "style": {"width": 170, "spacing": 12},
            "disabled": disabled,
            "children": [
                {
                    "name": f"filled{suffix}",
                    "widget": "Button",
                    "text": "Filled",
                    "style": {"width": 140, "height": 40, "variant": "filled"},
                },
                {
                    "name": f"out{suffix}",
                    "widget": "Button",
                    "text": "Outlined",
                    "style": {"width": 140, "height": 40, "variant": "outlined"},
                },
                {
                    "name": f"row{suffix}",
                    "widget": "Horizontal",
                    "style": {"height": 40, "spacing": 14, "cross_alignment": "center"},
                    "children": [
                        {"name": f"cb{suffix}", "widget": "Checkbox", "value": "true"},
                        {"name": f"rd{suffix}", "widget": "Radio", "value": "true"},
                        {"name": f"sw{suffix}", "widget": "Switch", "value": "true"},
                    ],
                },
                {
                    "name": f"chip{suffix}",
                    "widget": "Chip",
                    "text": "Filter",
                    "style": {"variant": "filter"},
                    "value": "true",
                },
            ],
        }

    view = {
        "root": {
            "name": "root",
            "widget": "Horizontal",
            "style": {"background": "surface", "padding": 16, "spacing": 24},
            "children": [controls("a", "false"), controls("b", "true")],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=400, height=220, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("disabled", np.asarray(engine.canvas.draw()))


def test_stylesheet_baseline(render_scene, assert_golden) -> None:
    """The same three buttons, styled entirely from a sheet.

    Only `classes:` and `name:` appear on the nodes -- every dimension and
    colour below comes from `styles:`, resolved at load. The third button
    shows a name selector overriding a class one, and the fourth shows an
    inline `style:` beating the sheet.
    """
    view = {
        "styles": [
            {"style": {"corner_radius": 12}},
            {"widget": "Button", "style": {"height": 44, "width": 150, "variant": "filled"}},
            {"classes": "danger", "style": {"background": "error", "color": "on_error"}},
            {
                "name": "confirm",
                "style": {"width": 220, "background": "tertiary", "color": "on_tertiary"},
            },
        ],
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16, "spacing": 12},
            "children": [
                {"name": "plain", "widget": "Button", "text": "Plain"},
                {"name": "danger", "widget": "Button", "classes": "danger", "text": "Delete"},
                {"name": "confirm", "widget": "Button", "classes": "danger", "text": "Confirm"},
                {
                    "name": "inline",
                    "widget": "Button",
                    "classes": "danger",
                    "text": "Inline",
                    "style": {
                        "width": 110,
                        "background": "secondary_container",
                        "color": "on_secondary_container",
                    },
                },
            ],
        },
    }
    _, engine = render_scene(
        lambda dl: None, width=280, height=260, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("stylesheet", np.asarray(engine.canvas.draw()))


def test_type_scale_baseline(render_scene, assert_golden) -> None:
    """All fifteen M3 roles, each rendered by naming it and nothing else.

    A role resolves to three things -- size, weight and tracking -- and until
    now none of them had a picture. Sizes are visible as height, weights as the
    Medium rows (every `label-*`, `title-medium` and `title-small`), and
    tracking only as width, which is exactly the sort of change a property
    assertion can pass while the frame is wrong.

    The last row pairs a role with an explicit `letter_spacing:` well outside
    the scale, so the override is legible rather than a fraction of a pixel.
    """
    from pysilver.spec.models import TYPE_ROLES

    children: list[dict] = [
        {
            "name": role,
            "widget": "Text",
            "text": role,
            "style": {"text_style": role, "color": "on_surface"},
        }
        for role in TYPE_ROLES
    ]
    children.append(
        {
            "name": "tracked",
            "widget": "Text",
            "text": "label-large, spaced",
            "style": {"text_style": "label-large", "letter_spacing": 4.0, "color": "primary"},
        }
    )
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 12, "spacing": 2},
            "children": children,
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=420, height=560, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("type_scale", np.asarray(engine.canvas.draw()))


def test_text_field_baseline(render_scene, assert_golden) -> None:
    """Both M3 variants, in the states that look different.

    Every state here is one a user reaches by clicking or typing, and each is
    reached the same way rather than by setting a flag: the third field is
    focused through the dispatcher, so the frame shows what focus actually
    paints -- a 2dp indicator, a floated label in `primary`, and a caret.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16, "spacing": 12},
            "children": [
                {
                    "name": "empty",
                    "widget": "TextField",
                    "text": "Empty, label at rest",
                    "style": {"width": 288},
                },
                {
                    "name": "filled",
                    "widget": "TextField",
                    "text": "Name",
                    "value": "Ada Lovelace",
                    "supporting_text": "As it appears on your card",
                    "style": {"width": 288},
                },
                {
                    "name": "focused",
                    "widget": "TextField",
                    "text": "Focused",
                    "value": "with a caret",
                    "style": {"width": 288},
                },
                {
                    "name": "outlined",
                    "widget": "TextField",
                    "text": "Outlined",
                    "value": "notched label",
                    "style": {"width": 288, "variant": "outlined"},
                },
                {
                    "name": "wrong",
                    "widget": "TextField",
                    "text": "Email",
                    "value": "not-an-address",
                    "supporting_text": "Enter a valid address",
                    "error": "true",
                    "style": {"width": 288},
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=320, height=400, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.dispatcher.focus(app.root.find("focused"))
    # The caret blinks, so pin it: with the ticker never advanced the repeating
    # animation sits at zero, which is the visible half of the cycle.
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("text_field", np.asarray(engine.canvas.draw()))


def test_bidi_text_field_baseline(render_scene, assert_golden) -> None:
    """Real UAX #9 bidi, through a real App with the bundled Arabic and
    Hebrew fonts -- the demonstrable proof for the whole RTL rewrite this
    baseline exists to guard against a regression in.

    Two unfocused fields show real Arabic and Hebrew glyphs (not tofu boxes
    -- the fonts these need did not exist in the bundle until this feature).
    The third, focused field holds a selection that crosses the direction
    boundary in `"Hello مرحبا"` (offsets 3-9, spanning "lo " into "مرح"):
    it must paint as two disjoint rects, not one rect stretched across the
    gap between them -- `rects_for`'s multi-rect behaviour, the thing a
    property assertion on `_spans_x` cannot show but a rendered frame can.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16, "spacing": 16},
            "children": [
                {
                    "name": "arabic",
                    "widget": "TextField",
                    "text": "Arabic",
                    "value": "Hello مرحبا",
                    "style": {"width": 288},
                },
                {
                    "name": "hebrew",
                    "widget": "TextField",
                    "text": "Hebrew",
                    "value": "Shalom שלום",
                    "style": {"width": 288},
                },
                {
                    "name": "selected",
                    "widget": "TextField",
                    "text": "Selection across a boundary",
                    "value": "Hello مرحبا",
                    "style": {"width": 288},
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=320, height=280, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    field = app.root.find("selected")
    assert field is not None
    field.editor.select(3, 9)
    app.dispatcher.focus(field)
    # The caret blinks, so pin it: with the ticker never advanced the
    # repeating animation sits at zero, which is the visible half of the
    # cycle -- same reasoning as `test_text_field_baseline`.
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("bidi_text_field", np.asarray(engine.canvas.draw()))


def test_multiline_field_baseline(render_scene, assert_golden) -> None:
    """The three shapes M3 names, side by side and to scale.

    A single-line field with a value too long for it, a multi-line field grown
    to fit the same value, and a fixed-height text area holding more than it
    can show. The differences are entirely geometric, which is exactly what a
    property assertion cannot check.
    """
    long = "A value long enough that it has to wrap when the field lets it."
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16, "spacing": 12},
            "children": [
                {
                    "name": "single",
                    "widget": "TextField",
                    "text": "Single line",
                    "value": long,
                    "style": {"width": 288},
                },
                {
                    "name": "grown",
                    "widget": "TextField",
                    "text": "Multi-line",
                    "value": long,
                    "supporting_text": "Grows as it wraps",
                    "style": {"width": 288, "multiline": True},
                },
                {
                    "name": "area",
                    "widget": "TextField",
                    "text": "Text area",
                    "value": long * 3,
                    "style": {"width": 288, "multiline": True, "height": 120},
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=320, height=380, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("multiline_field", np.asarray(engine.canvas.draw()))


def test_text_spans_baseline(render_scene, assert_golden) -> None:
    """Per-glyph colour, which nothing but pixels can confirm.

    An instance assertion proves the right token reached the right glyph. It
    cannot prove the shader resolved it -- a mistake in the fill column or in
    `resolve` would leave every assertion passing and every word one colour.

    The lines mix both kinds deliberately: palette tokens, which follow a theme
    change, and a literal RGBA, which does not. A terminal needs the literal
    because ANSI's colours are not palette roles; a syntax theme should use
    tokens for exactly the opposite reason.
    """
    theme = Theme(seed=SEED, dark=True)
    engine_box: list = []

    KEYWORD, NAME, NUMBER, COMMENT = "primary", "tertiary", "secondary", "outline"

    def paint(dl):
        engine = engine_box[0]
        pal = engine.palette

        def at(text: str, word: str, role: str):
            """A span for `word` in `text`. Computed, not counted -- hand
            counting put two of these off by one, and the picture still looked
            plausible enough not to say so."""
            i = text.index(word)
            return (i, i + len(word), pal.index(role))

        line1 = "def total(items, rate=0.07):"
        spans1 = [
            at(line1, "def", KEYWORD),
            at(line1, "total", NAME),
            at(line1, "0.07", NUMBER),
        ]
        line2 = "    return sum(items) * rate  # tax"
        spans2 = [
            at(line2, "return", KEYWORD),
            at(line2, "sum", NAME),
            at(line2, "# tax", COMMENT),
        ]
        line3 = "ERROR  build failed"
        spans3 = [(0, 5, (0.94, 0.30, 0.30, 1.0))]

        for i, (text, spans) in enumerate([(line1, spans1), (line2, spans2), (line3, spans3)]):
            para = engine.text.layout(text, px=15.0)
            engine.text.emit(
                dl,
                para,
                x=12.0,
                y=14.0 + i * 26.0,
                pixel_ratio=1.0,
                token=pal.index("on_surface"),
                spans=spans,
            )

    _, engine = render_scene(lambda dl: None, width=300, height=104, theme=theme)
    engine_box.append(engine)
    engine.painter = paint
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("text_spans", np.asarray(engine.canvas.draw()))


def test_shapes_baseline(render_scene, assert_golden) -> None:
    """The polygon branch, which nothing but pixels can check.

    An SDF is right or it is subtly wrong -- a vertex off by a degree, a corner
    radius measured on the circumradius instead of the apothem, antialiasing
    that breaks where the sector folds. None of that shows up in an instance
    assertion; all of it shows up here.

    The two routes to a circle are both in frame: the 24-gon at top right
    approaches its circumcircle, and the fully rounded hexagon below it
    collapses to its inscribed circle. They are deliberately different sizes,
    because that is the consequence of rounding on the apothem.
    """

    def cell(name, **style):
        return {"name": name, "widget": "Shape", "style": {"width": 64, "height": 64, **style}}

    rows = [
        [
            cell("tri", sides=3, background="primary"),
            cell("sq", sides=4, background="secondary"),
            cell("pent", sides=5, background="tertiary"),
            cell("hex", sides=6, background="primary_container"),
        ],
        [
            cell("oct", sides=8, background="secondary_container"),
            cell("many", sides=24, background="tertiary_container"),
            cell("round_hex", sides=6, corner_radius=32, background="primary"),
            cell("half", sides=6, corner_radius=8, background="secondary"),
        ],
        [
            cell("spun", sides=3, rotation=30, background="primary"),
            cell("spun2", sides=4, rotation=45, background="secondary"),
            cell("frac", sides=5.5, background="tertiary"),
            {
                "name": "outlined",
                "widget": "Shape",
                "style": {
                    "width": 64,
                    "height": 64,
                    "sides": 6,
                    "background": "surface",
                    "border": {"width": 3, "color": "primary"},
                },
            },
        ],
    ]
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16, "spacing": 12},
            "children": [
                {"name": f"r{i}", "widget": "Horizontal", "style": {"spacing": 12}, "children": r}
                for i, r in enumerate(rows)
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=336, height=260, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("shapes", np.asarray(engine.canvas.draw()))


def test_unsized_widgets_baseline(render_scene, assert_golden) -> None:
    """Every self-sizing widget, with no `style:` at all.

    The corpus gap this fills: every other baseline gives its widgets an
    explicit size or a stylesheet class, so nothing exercised the intrinsic
    path. A Button laid out 0x0 and drew nothing for as long as that was true,
    and no golden noticed. Anything here that disappears has done the same.

    `cross_alignment: start` is the point of the arrangement -- stretched, each
    row would take the column's width and the widths under test would vanish.
    """
    row = {
        "name": "controls",
        "widget": "Horizontal",
        "style": {"spacing": 8, "cross_alignment": "center"},
        "children": [
            {"name": "cb", "widget": "Checkbox", "value": "true"},
            {"name": "rd", "widget": "Radio", "value": "true"},
            {"name": "sw", "widget": "Switch", "value": "true"},
            {"name": "ic", "widget": "Icon", "icon": "home"},
            {"name": "ib", "widget": "IconButton", "icon": "star"},
            {"name": "bg", "widget": "Badge", "value": "3"},
            {"name": "cp", "widget": "CircularProgress", "value": "0.4"},
        ],
    }
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {
                "background": "surface",
                "padding": 16,
                "spacing": 10,
                "cross_alignment": "start",
            },
            "children": [
                {"name": "label", "widget": "Text", "text": "Unsized, every one"},
                {"name": "btn", "widget": "Button", "text": "Confirm"},
                {"name": "short", "widget": "Button", "text": "OK"},
                {
                    "name": "chip",
                    "widget": "Chip",
                    "text": "Filter",
                    "style": {"variant": "filter"},
                },
                row,
                {"name": "fab", "widget": "Fab", "icon": "add"},
                {"name": "card", "widget": "Card"},
                {"name": "seg", "widget": "Segment", "text": "Week"},
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=320, height=420, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("unsized_widgets", np.asarray(engine.canvas.draw()))


def test_elevation_baseline(render_scene, assert_golden) -> None:
    """The six M3 elevation levels, on a light theme.

    Deliberately light: a 30%-alpha shadow over the dark theme's near-black
    surface is barely perceptible, so a dark baseline would pass whatever the
    shadows did. The whole point of this frame is that the levels are
    distinguishable from each other.

    Levels run 0 (flat) to 5, top to bottom. A `Card` draws no label, so the
    shadows are the whole content of the frame -- which is the point.

    Levels 0-3 are resting states; M3 reserves +4 and +5 for interacted states
    such as hover, which is why nothing rests there.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 20, "spacing": 18},
            "children": [
                {
                    "name": f"row{level}",
                    "widget": "Card",
                    "style": {
                        "variant": "elevated",
                        "elevation": level,
                        "width": 260,
                        "height": 34,
                        "background": "surface_container_lowest",
                    },
                }
                for level in range(6)
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=320, height=340, theme=Theme(seed=SEED, dark=False)
    )
    app = App(view, theme=Theme(seed=SEED, dark=False))
    app.attach(engine)
    app.mount()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("elevation", np.asarray(engine.canvas.draw()))


def test_context_menu_baseline(render_scene, assert_golden) -> None:
    """A context menu opened at the pointer by a right-click.

    Driven through the real dispatcher with a secondary press rather than by
    setting a signal, so the frame proves the whole path: button 2 becomes a
    CONTEXT_MENU event, the handler opens the overlay, and `placement: pointer`
    puts it where the click happened.
    """
    from pysilver import Signal
    from pysilver.runtime.events import MOUSE_SECONDARY, EventType, PointerEvent

    opened = Signal(False)
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16},
            "children": [
                {
                    "name": "canvas",
                    "widget": "Container",
                    "style": {
                        "width": "expand",
                        "height": "expand",
                        "background": "surface_container",
                        "corner_radius": 12,
                    },
                    "handlers": {"on_context_menu": "show"},
                }
            ],
        },
        "overlays": [
            {
                "name": "ctx",
                "widget": "Menu",
                "open": "{{ opened.get() }}",
                "style": {"placement": "pointer", "width": 190},
                "children": [
                    {"name": "cut", "widget": "MenuItem", "text": "Cut", "supporting_text": "^X"},
                    {"name": "copy", "widget": "MenuItem", "text": "Copy", "supporting_text": "^C"},
                    {
                        "name": "paste",
                        "widget": "MenuItem",
                        "text": "Paste",
                        "supporting_text": "^V",
                    },
                ],
            }
        ],
    }
    _, engine = render_scene(
        lambda dl: None, width=420, height=280, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.expose(opened=opened)

    @app.handler
    def show(event) -> None:
        opened.set(True)

    app.attach(engine)
    # Drive time by hand: an overlay fades in over 400ms, so the frame on
    # which the menu opens shows nothing at all.
    clock = {"t": 0.0}
    app.clock = lambda: clock["t"]
    app.mount()
    app.paint(DisplayList())

    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=90, y=70, button=MOUSE_SECONDARY))
    app.dispatcher.drain()
    for _ in range(12):
        clock["t"] += 0.05
        app.paint(DisplayList())

    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("context_menu", np.asarray(engine.canvas.draw()))


def test_text_selection_baseline(render_scene, assert_golden) -> None:
    """Selected text, single-line and wrapped.

    The highlight sits behind the glyphs, so the letters keep their own colour
    rather than being tinted by the band over them.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 16, "spacing": 14},
            "children": [
                {
                    "name": "one",
                    "widget": "Text",
                    "text": "Select a few words here",
                    "style": {
                        "font_size": 20,
                        "selectable": True,
                        "width": 300,
                        "height": 28,
                        "color": "on_surface",
                    },
                },
                {
                    "name": "many",
                    "widget": "Text",
                    "text": "A wrapped paragraph selects across every line it covers, "
                    "one highlight rectangle per line.",
                    "style": {
                        "font_size": 15,
                        "selectable": True,
                        "width": 300,
                        "height": 90,
                        "color": "on_surface",
                    },
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=340, height=180, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.paint(DisplayList())

    one = app.root.find("one")
    one.select(7, 18)  # a span in the middle of the line
    app.root.find("many").select_all()

    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("text_selection", np.asarray(engine.canvas.draw()))


def test_svg_icons_baseline(render_scene, assert_golden, tmp_path) -> None:
    """Route A end to end: SVG -> a real glyph -> the existing pipeline.

    Every property assertion in `test_svgicons.py` can pass while the shader
    still draws the wrong thing -- this is the one check that renders a
    compiled icon through the real `Icon` widget, in a real `App`, tinted by a
    real palette token, and looks at the pixels. The ring proves the hole
    survives to the screen, not just to `Face.rasterize`; the tint proves a
    custom icon takes a palette token exactly like Material Symbols does.
    """
    pytest.importorskip("svgelements")
    from pysilver.text.svgicons import load_svg_icons

    triangle = (
        '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M4 20 L20 20 L12 4 Z"/></svg>'
    )
    ring = (
        '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M12 2 A10 10 0 1 0 12.01 2 Z M12 8 A6 6 0 1 1 11.99 8 Z"/></svg>'
    )
    icons = load_svg_icons({"triangle": triangle, "ring": ring}, tmp_path / "icons.ttf")

    view = {
        "root": {
            "name": "root",
            "widget": "Horizontal",
            "style": {"background": "surface", "padding": 20, "spacing": 20},
            "children": [
                {"name": "tri", "widget": "Icon", "icon": "triangle", "style": {"icon_size": 48}},
                {
                    "name": "ring",
                    "widget": "Icon",
                    "icon": "ring",
                    "style": {"icon_size": 48, "color": "tertiary"},
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=140, height=88, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.text._icons = icons  # swap in the custom set before the first paint
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("svg_icons", np.asarray(engine.canvas.draw()))


def test_popover_baseline(render_scene, assert_golden) -> None:
    """M3's persistent rich tooltip, anchored below a trigger button.

    Proves the whole anatomy at once: shrink-to-fit width (this popover is
    nowhere near its 320dp maximum), the subhead/body colour split, the
    action row below the text, and anchor placement flipping the popover
    below the real trigger rather than centring it -- none of which a
    property assertion alone can confirm together.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 24},
            "children": [
                {"name": "trigger", "widget": "Button", "text": "Info", "style": {"width": 80}}
            ],
        },
        "overlays": [
            {
                "name": "pop",
                "widget": "Popover",
                "text": "New feature",
                "supporting_text": "Filters now save automatically.",
                "open": "true",
                "style": {"anchor": "trigger"},
                "children": [{"name": "learn", "widget": "Button", "text": "Learn more"}],
            }
        ],
    }
    _, engine = render_scene(
        lambda dl: None, width=280, height=200, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("popover", np.asarray(engine.canvas.draw()))


def test_accordion_baseline(render_scene, assert_golden) -> None:
    """One collapsed, one expanded, stacked in a Vertical.

    Proves the header/chevron/reveal/clip together: the collapsed panel shows
    only its 56dp header with `expand_more`, and the expanded one reveals its
    body -- clipped in-shader exactly like `ScrollView`, not a second draw
    call -- behind an `expand_less` chevron.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 24},
            "children": [
                {
                    "name": "collapsed",
                    "widget": "Accordion",
                    "text": "Shipping",
                    "supporting_text": "Standard, 3-5 days",
                    "value": "false",
                    "children": [{"name": "c_body", "widget": "Text", "text": "Free over $50."}],
                },
                {"name": "gap", "widget": "Divider", "style": {"opacity": 0}},
                {
                    "name": "expanded",
                    "widget": "Accordion",
                    "text": "Returns",
                    "value": "true",
                    "children": [
                        {
                            "name": "e_body",
                            "widget": "Text",
                            "text": "Returns are accepted within 30 days of delivery.",
                        }
                    ],
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=360, height=280, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("accordion", np.asarray(engine.canvas.draw()))


def test_tree_view_baseline(render_scene, assert_golden) -> None:
    """`src` expanded (one selected leaf, one collapsed nested branch) plus a
    top-level leaf.

    Proves indentation, the selected-item highlight, and that a collapsed
    branch's own children stay hidden even while its parent is expanded --
    the property `test_collapsing_an_ancestor_clips_every_descendant` checks
    at the display-list level.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 24},
            "children": [
                {
                    "name": "tv",
                    "widget": "TreeView",
                    "value": "main",
                    "children": [
                        {
                            "name": "src",
                            "widget": "TreeItem",
                            "text": "src",
                            "value": "true",
                            "children": [
                                {"name": "main", "widget": "TreeItem", "text": "main.py"},
                                {
                                    "name": "utils",
                                    "widget": "TreeItem",
                                    "text": "utils",
                                    "value": "false",
                                    "children": [
                                        {
                                            "name": "helpers",
                                            "widget": "TreeItem",
                                            "text": "helpers.py",
                                        }
                                    ],
                                },
                            ],
                        },
                        {"name": "readme", "widget": "TreeItem", "text": "README.md"},
                    ],
                }
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=360, height=320, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("tree_view", np.asarray(engine.canvas.draw()))


def test_submenu_baseline(render_scene, assert_golden) -> None:
    """A main menu with a submenu open beside its trigger item.

    Proves the whole feature at once: the trigger's trailing chevron (not a
    keyboard shortcut), the submenu positioned beside the item rather than
    below the whole menu, and both menus rendering simultaneously without
    overlapping.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 24},
            "children": [
                {"name": "trigger", "widget": "Button", "text": "File", "style": {"width": 80}}
            ],
        },
        "overlays": [
            {
                "name": "main",
                "widget": "Menu",
                "open": "true",
                "style": {"anchor": "trigger"},
                "children": [
                    {"name": "new", "widget": "MenuItem", "text": "New", "supporting_text": "^N"},
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
                "open": "true",
                "style": {"anchor": "recent"},
                "children": [
                    {"name": "r1", "widget": "MenuItem", "text": "report.docx"},
                    {"name": "r2", "widget": "MenuItem", "text": "notes.txt"},
                ],
            },
        ],
    }
    _, engine = render_scene(
        lambda dl: None, width=640, height=260, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("submenu", np.asarray(engine.canvas.draw()))


def test_link_baseline(render_scene, assert_golden) -> None:
    """A link inline with body text, plus a standalone tertiary-variant link.

    Proves the underline sits under the label at a real font-metric-derived
    position (not a rough guess), and that `primary`/`tertiary` differ.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 24, "spacing": 16},
            "children": [
                {
                    "name": "row",
                    "widget": "Horizontal",
                    "style": {"spacing": 4},
                    "children": [
                        {"name": "lead", "widget": "Text", "text": "Read our"},
                        {"name": "terms", "widget": "Link", "text": "terms of service"},
                    ],
                },
                {
                    "name": "muted",
                    "widget": "Link",
                    "text": "Learn more",
                    "style": {"variant": "tertiary"},
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=320, height=140, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("link", np.asarray(engine.canvas.draw()))


def test_spin_box_baseline(render_scene, assert_golden) -> None:
    """One mid-range, one pinned to its minimum.

    Proves the anatomy (icon buttons flanking the number) and the at-bound
    dimming: the second one's decrement side should read visibly fainter
    than its own increment side.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 24, "spacing": 20},
            "children": [
                {"name": "mid", "widget": "SpinBox", "value": "3", "style": {"min": 0, "max": 5}},
                {"name": "floor", "widget": "SpinBox", "value": "0", "style": {"min": 0, "max": 5}},
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=200, height=120, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("spin_box", np.asarray(engine.canvas.draw()))


def test_pagination_baseline(render_scene, assert_golden) -> None:
    """One at the first page, one in the middle of a large range.

    Proves the whole feature at once: the collapsed "..." runs, the current
    page's secondary_container fill, and the dimmed prev arrow with nothing
    behind it to go back to.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 24, "spacing": 20},
            "children": [
                {"name": "first", "widget": "Pagination", "value": "1", "style": {"count": 10}},
                {"name": "mid", "widget": "Pagination", "value": "5", "style": {"count": 10}},
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=420, height=120, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("pagination", np.asarray(engine.canvas.draw()))


def test_status_bar_baseline(render_scene, assert_golden) -> None:
    """A status bar docked below some content, with a leading message and a
    trailing group split by a Spacer.

    Proves the anatomy (surface_container, thin 24dp height) and the fix
    that makes the Spacer split actually work: without overriding flex_of,
    the trailing text would be starved of width and vanish.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "width": "expand", "height": "expand"},
            "children": [
                {
                    "name": "content",
                    "widget": "Container",
                    "style": {"width": "expand", "height": "expand"},
                },
                {
                    "name": "bar",
                    "widget": "StatusBar",
                    "children": [
                        {"name": "lead", "widget": "Text", "text": "Ready"},
                        {"name": "gap", "widget": "Spacer", "style": {"width": "expand"}},
                        {"name": "branch", "widget": "Text", "text": "main"},
                        {"name": "encoding", "widget": "Text", "text": "UTF-8"},
                    ],
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=360, height=120, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("status_bar", np.asarray(engine.canvas.draw()))


def test_dock_baseline(render_scene, assert_golden) -> None:
    """An IDE-shaped layout: a narrower sidebar group beside a wider main
    group with two tabs, one of them active.

    Proves the whole feature at once: the split ratio, the tab strip's
    selected indicator and colour, and that the inactive tab's content
    (Output) contributes nothing to what's visible.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "DockSplit",
            "value": "0.3",
            "children": [
                {
                    "name": "sidebar",
                    "widget": "DockGroup",
                    "children": [
                        {
                            "name": "files",
                            "widget": "DockPanel",
                            "text": "Files",
                            "children": [
                                {
                                    "widget": "Container",
                                    "style": {
                                        "width": "expand",
                                        "height": "expand",
                                        "background": "surface",
                                    },
                                }
                            ],
                        }
                    ],
                },
                {
                    "name": "main",
                    "widget": "DockGroup",
                    "value": "editor",
                    "children": [
                        {
                            "name": "editor",
                            "widget": "DockPanel",
                            "text": "main.py",
                            "children": [
                                {
                                    "widget": "Container",
                                    "style": {
                                        "width": "expand",
                                        "height": "expand",
                                        "background": "surface_container_low",
                                    },
                                }
                            ],
                        },
                        {
                            "name": "output",
                            "widget": "DockPanel",
                            "text": "Output",
                            "children": [{"widget": "Text", "text": "log output"}],
                        },
                    ],
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=480, height=280, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("dock", np.asarray(engine.canvas.draw()))


def test_canvas_baseline(render_scene, assert_golden) -> None:
    """One `on_paint` handler exercising every primitive at once: a filled
    rect, a stroked line, a filled circle, a stroked arc, a hexagon, and a
    label -- proving the whole vocabulary renders, not just that the display
    list contains the right instance kinds (`test_canvas.py` already checks
    that at the CPU level with no GPU involved)."""
    view = {
        "root": {
            "name": "root",
            "widget": "Canvas",
            "style": {"width": 240, "height": 160, "background": "surface_container"},
            "handlers": {"on_paint": "draw"},
        }
    }
    app = App(view, theme=Theme(seed=SEED, dark=True))

    @app.handler
    def draw(canvas):
        canvas.rect(16, 16, 60, 32, color="primary", corner_radius=6)
        canvas.line(16, 64, 220, 64, thickness=3, color="on_surface_variant")
        canvas.circle(40, 110, 20, color="tertiary")
        canvas.arc(100, 110, 20, thickness=4, start=0.0, sweep=4.5, color="secondary")
        canvas.polygon(160, 90, 40, 40, sides=6, color=(0.9, 0.4, 0.2, 1.0))
        canvas.text(16, 136, "Canvas", color="on_surface")

    _, engine = render_scene(
        lambda dl: None, width=240, height=160, theme=Theme(seed=SEED, dark=True)
    )
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("canvas", np.asarray(engine.canvas.draw()))


def test_nodegraph_baseline(render_scene, assert_golden) -> None:
    """Two nodes wired by one edge, panned part-way: proves the title bar,
    port dots, and the edge segment between them all render together, and
    that the pan offset (`state.scroll`) actually moves what's painted --
    not just that the display list contains the right instance kinds
    (`test_nodegraph.py` already checks that at the CPU level)."""
    from pysilver.layout import Offset

    view = {
        "root": {
            "name": "graph",
            "widget": "NodeGraph",
            "style": {"width": 320, "height": 200, "background": "surface_container_lowest"},
            "edges": [{"source": "src.out", "target": "dst.in"}],
            "children": [
                {
                    "name": "src",
                    "widget": "Node",
                    "text": "Source",
                    "outputs": "out",
                    "style": {"x": 20, "y": 20},
                },
                {
                    "name": "dst",
                    "widget": "Node",
                    "text": "Sink",
                    "inputs": "in",
                    "style": {"x": 200, "y": 100},
                },
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=320, height=200, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.root.state.scroll = Offset(10.0, 5.0)
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("nodegraph", np.asarray(engine.canvas.draw()))


def test_codeeditor_baseline(render_scene, assert_golden) -> None:
    """A short Python snippet: proves the gutter, the divider, and Pygments
    syntax highlighting all render together -- not just that the display
    list contains the right instance kinds (`test_codeeditor.py` already
    checks that at the CPU level with no GPU involved)."""
    code = "def add(a, b):\n    return a + b\n"
    view = {
        "root": {
            "name": "editor",
            "widget": "CodeEditor",
            "value": code,
            "style": {"width": 280, "height": 140, "language": "python"},
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=280, height=140, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("codeeditor", np.asarray(engine.canvas.draw()))


def test_terminal_baseline(render_scene, assert_golden) -> None:
    """A prompt line, a coloured line, and a focused blinking cursor: proves
    the cell grid, per-run background/foreground colour, and cursor all
    render together. Bytes are fed directly into a `bittty` board attached to
    the mounted element rather than through a real spawned shell -- the real
    PTY pipeline is proven end to end in `test_terminal.py`; a golden image
    only needs deterministic content, not a race with a live process."""
    from bittty.devices.board import Board

    view = {
        "root": {
            "name": "term",
            "widget": "Terminal",
            "style": {"width": 280, "height": 140},
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=280, height=140, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()

    term = app.root.find("term")
    # `app.mount()` already started a real PTY session (`set_ticker` fires
    # from `App.__init__`) -- stop it before swapping in a fake one, or it
    # leaks a live shell process and its reader thread for the rest of the
    # test run. A trivial always-alive stand-in keeps the cursor (drawn only
    # while `_session.alive`) in the golden without a real subprocess.
    if term._session is not None:
        term._session.stop()

    class _AlwaysAlive:
        alive = True

        def drain(self) -> bytes:
            return b""

    term._session = _AlwaysAlive()
    term._board = Board(command="/bin/sh", width=term._cols, height=term._rows)
    term._feed(b"$ \x1b[32mgit status\x1b[0m\r\n")
    term._feed(b"\x1b[41mon branch main\x1b[0m\r\n")
    app.dispatcher.focus(term)

    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("terminal", np.asarray(engine.canvas.draw()))


def test_image_baseline(render_scene, assert_golden, tmp_path) -> None:
    """A real decoded file sampled through the real texture pipeline --
    `Kind.IMAGE`'s first GPU render. Two placements of the same asymmetric
    source (left half red, right half blue) at each `fit` that can crop or
    letterbox, so a wrong UV crop or a wrong destination rect both show up
    as visibly wrong colour placement, not just an instance count."""
    import numpy as np
    from PIL import Image as PILImage

    source = np.zeros((40, 80, 4), dtype=np.uint8)
    source[:, :40] = (200, 60, 60, 255)
    source[:, 40:] = (60, 90, 200, 255)
    png = tmp_path / "split.png"
    PILImage.fromarray(source, "RGBA").save(png)

    view = {
        "root": {
            "name": "root",
            "widget": "Horizontal",
            "style": {"spacing": 16, "padding": 16, "background": "surface"},
            "children": [
                {
                    "name": "contain",
                    "widget": "Image",
                    "path": str(png),
                    "style": {"width": 100, "height": 100, "fit": "contain"},
                },
                {
                    "name": "cover",
                    "widget": "Image",
                    "path": str(png),
                    "style": {"width": 100, "height": 100, "fit": "cover", "corner_radius": 12},
                },
            ],
        }
    }
    app = App(view, theme=Theme(seed=SEED, dark=True))
    _, engine = render_scene(
        lambda dl: None, width=232, height=132, theme=Theme(seed=SEED, dark=True)
    )
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("image", np.asarray(engine.canvas.draw()))


def test_video_baseline(render_scene, assert_golden) -> None:
    """A pushed frame sampled through the real texture pipeline, then
    *replaced* by a second, differently-coloured same-shape frame before the
    asserted render -- proving `push_frame` -> `ImageAtlas.update` ->
    `Engine._upload` -> the shader's sample all actually connect. If the
    in-place overwrite or the per-frame upload were broken, this would show
    the first frame's colours instead of the second's."""
    view = {
        "root": {
            "name": "root",
            "widget": "Video",
            "style": {
                "width": 100,
                "height": 100,
                "fit": "cover",
                "corner_radius": 12,
                "background": "surface",
            },
        }
    }
    app = App(view, theme=Theme(seed=SEED, dark=True))
    _, engine = render_scene(
        lambda dl: None, width=100, height=100, theme=Theme(seed=SEED, dark=True)
    )
    app.attach(engine)
    app.mount()
    app.update()

    stale = np.zeros((40, 80, 4), dtype=np.uint8)
    stale[:] = (150, 150, 150, 255)
    app.root.find("root").push_frame(stale)
    engine.canvas.request_draw(engine.draw_frame)
    engine.canvas.draw()  # render once so the "stale" frame is not what gets asserted

    live = np.zeros((40, 80, 4), dtype=np.uint8)
    live[:, :40] = (60, 160, 90, 255)
    live[:, 40:] = (220, 190, 60, 255)
    app.root.find("root").push_frame(live)
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("video", np.asarray(engine.canvas.draw()))


def test_tree_view_deep_collapse_baseline(render_scene, assert_golden) -> None:
    """A collapsed branch two levels deep, with a genuinely expanded and
    visibly-labelled grandchild inside it.

    This is the specific shape `test_collapsing_an_ancestor_clips_every_
    descendant` (test_navigation.py) checks at the display-list level --
    but that test only verifies the *clip rect's own math*, not that the
    renderer actually honours it. It doesn't: `ui.wgsl` only applies a clip
    when both its width AND height are strictly greater than zero, so a
    mathematically-correct zero-height intersection was silently read as
    "unclipped" and the grandchild's label rendered anyway. Confirmed by
    rendering this exact frame before the fix and finding the label really
    was on screen. Fixed by flooring the intersected clip's dimensions to
    a real, sub-pixel `HIDDEN_EXTENT` instead of the literal zero
    `Rect.intersect` produces for a no-overlap case.
    """
    view = {
        "root": {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface", "padding": 24},
            "children": [
                {
                    "name": "a",
                    "widget": "TreeItem",
                    "text": "a",
                    "value": "false",
                    "children": [
                        {
                            "name": "b",
                            "widget": "TreeItem",
                            "text": "b",
                            "value": "true",
                            "children": [
                                {
                                    "name": "c",
                                    "widget": "TreeItem",
                                    "text": "must not be visible",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    }
    _, engine = render_scene(
        lambda dl: None, width=280, height=260, theme=Theme(seed=SEED, dark=True)
    )
    app = App(view, theme=Theme(seed=SEED, dark=True))
    app.attach(engine)
    app.mount()
    app.update()
    engine.canvas.request_draw(engine.draw_frame)
    assert_golden("tree_view_deep_collapse", np.asarray(engine.canvas.draw()))
