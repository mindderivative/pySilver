"""Scrolling: viewport extent, clipping, wheel handling, and scroll chaining.

The load-bearing test here is `test_scrolling_does_not_relayout`. Everything
else in this module describes behaviour; that one describes the design.
"""

from __future__ import annotations

import pytest

from pysilver import App, Settings, Theme
from pysilver.layout import INF, Constraints, Offset, Size
from pysilver.paint import NO_TOKEN, DisplayList
from pysilver.runtime.events import EventType, WheelEvent
from pysilver.spec import parse_view
from pysilver.theme import Palette
from pysilver.widgets import build_element
from pysilver.widgets.scroll import ScrollViewElement

PALETTE = Palette(Theme(dark=True))
ROW_HEIGHT = 56.0  # a one-line M3 ListItem


def rows(n: int, prefix: str = "r") -> list[dict]:
    """Names must be unique across a whole view, so nested lists take a prefix."""
    return [
        {
            "name": f"{prefix}{i}",
            "widget": "ListItem",
            "text": f"Row {i}",
            "style": {"width": "expand"},
        }
        for i in range(n)
    ]


def scroll_view(n: int = 12, **style) -> ScrollViewElement:
    base = {"height": 200, "width": 300}
    base.update(style)
    spec = {
        "name": "sv",
        "widget": "ScrollView",
        "style": base,
        "children": [
            {"name": "col", "widget": "Vertical", "style": {"width": "expand"}, "children": rows(n)}
        ],
    }
    element = build_element(parse_view(spec).root)
    element.layout(Constraints.loose(Size(400, 400)))
    return element


def app_with(inner: dict, size=(400, 300)) -> App:
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [inner],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=size[0], height=size[1]),
    )
    app.mount()
    app.update()
    return app


# ------------------------------------------------------------------ extent


def test_viewport_keeps_its_own_size_while_content_overflows() -> None:
    sv = scroll_view(12)
    assert sv.size == Size(300.0, 200.0)
    assert sv.content_size.height == 12 * ROW_HEIGHT
    assert sv.max_scroll == 12 * ROW_HEIGHT - 200.0


def test_content_that_fits_is_not_scrollable() -> None:
    sv = scroll_view(2)
    assert sv.content_size.height == 2 * ROW_HEIGHT
    assert sv.max_scroll == 0.0
    assert not sv.scrollable


def test_content_is_measured_against_unbounded_space_on_the_scroll_axis() -> None:
    """Otherwise the content would be clipped to the viewport at layout time
    and there would be nothing to scroll to."""
    sv = scroll_view(40)
    assert sv.content_size.height == 40 * ROW_HEIGHT > sv.size.height


def test_content_is_still_bounded_across_the_scroll_axis() -> None:
    """A vertical scroll view must not let its content grow sideways, or text
    inside it would never wrap."""
    sv = scroll_view(4)
    assert sv.children[0].size.width == 300.0


def test_an_unbounded_scroll_axis_raises_rather_than_silently_not_scrolling() -> None:
    spec = {
        "name": "sv",
        "widget": "ScrollView",
        "children": [{"widget": "Vertical", "children": rows(10)}],
    }
    element = build_element(parse_view(spec).root)
    unbounded = Constraints(min_width=0.0, max_width=300.0, min_height=0.0, max_height=INF)
    with pytest.raises(ValueError, match="bounded height"):
        element.layout(unbounded)


# --------------------------------------------------------------- clamping


def test_scroll_clamps_to_the_content_extent() -> None:
    sv = scroll_view(12)
    sv.scroll_by(10_000)
    assert sv.scroll_offset == sv.max_scroll


def test_scroll_cannot_go_negative() -> None:
    sv = scroll_view(12)
    sv.scroll_by(-500)
    assert sv.scroll_offset == 0.0


def test_scroll_reports_whether_it_actually_moved() -> None:
    """This return value is what makes scroll chaining work."""
    sv = scroll_view(12)
    assert sv.scroll_by(50) is True
    sv.set_scroll(sv.max_scroll)
    assert sv.scroll_by(50) is False
    sv.set_scroll(0.0)
    assert sv.scroll_by(-50) is False


def test_offset_is_reclamped_when_the_content_shrinks() -> None:
    """A hot reload that deletes rows must not leave the view scrolled past
    the new end."""
    sv = scroll_view(20)
    sv.set_scroll(sv.max_scroll)
    deep = sv.scroll_offset
    assert deep > 0.0

    shorter = parse_view(
        {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"height": 200, "width": 300},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": rows(5),
                }
            ],
        }
    ).root
    from pysilver.tree.reconcile import reconcile

    reconcile(sv, shorter, build_element)
    sv.layout(Constraints.loose(Size(400, 400)))
    assert sv.scroll_offset == sv.max_scroll < deep


# ------------------------------------------------------------------- paint


def test_scrolling_does_not_relayout() -> None:
    """The central claim of the design.

    Scrolling is a paint-time translation: the content keeps the offsets
    layout gave it and the subtree is simply painted from a different origin.
    A relayout per wheel notch would be visible, because Python -- not the
    GPU -- is this framework's bottleneck.
    """
    app = app_with(
        {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"height": 200, "width": "expand"},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": rows(12),
                }
            ],
        }
    )
    sv = app.root.find("sv")
    calls: list[int] = []
    original = type(sv).perform_layout
    type(sv).perform_layout = lambda self, c: (calls.append(1), original(self, c))[1]
    try:
        assert sv.scroll_by(100) is True
        assert sv.needs_paint
        app.update()
        assert calls == [], "scrolling triggered a layout pass"
        assert app.layout_owner.dirty_count == 0
    finally:
        type(sv).perform_layout = original


def test_child_origin_translates_the_content() -> None:
    sv = scroll_view(12)
    sv.set_scroll(120.0)
    assert sv.child_origin(Offset(0.0, 0.0)) == Offset(0.0, -120.0)


def test_children_are_clipped_to_the_viewport() -> None:
    """In-shader clipping, not scissor -- the display list is one draw call."""
    app = app_with(
        {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"height": 120, "width": "expand"},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": rows(12),
                }
            ],
        }
    )
    dl = DisplayList()
    app.paint(dl)
    sv = app.root.find("sv")
    clipped = [s for s in dl.view if s["clip"][3] > 0.0]
    assert clipped, "nothing was clipped"
    assert all(s["clip"][3] <= sv.size.height for s in clipped)


def test_the_scrollbar_appears_only_when_the_content_overflows() -> None:
    def bars(n: int) -> int:
        app = app_with(
            {
                "name": "sv",
                "widget": "ScrollView",
                "style": {"height": 200, "width": "expand"},
                "children": [
                    {
                        "name": "col",
                        "widget": "Vertical",
                        "style": {"width": "expand"},
                        "children": rows(n),
                    }
                ],
            }
        )
        dl = DisplayList()
        app.paint(dl)
        token = PALETTE.index("outline_variant")
        return sum(
            1
            for s in dl.view
            if int(s["flags"][2]) == token
            and abs(float(s["rect"][2]) - ScrollViewElement.BAR_THICKNESS) < 0.01
        )

    assert bars(2) == 0
    assert bars(20) == 1


def test_the_scrollbar_is_painted_with_a_palette_token() -> None:
    app = app_with(
        {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"height": 100, "width": "expand"},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": rows(20),
                }
            ],
        }
    )
    dl = DisplayList()
    app.paint(dl)
    assert PALETTE.index("outline_variant") in {
        int(s["flags"][2]) for s in dl.view if int(s["flags"][2]) != NO_TOKEN
    }


# ------------------------------------------------------------------ wheel


def wheel(app: App, x: float, y: float, dy: float) -> None:
    app.dispatcher.post(WheelEvent(EventType.WHEEL, x=x, y=y, dy=dy))
    app.dispatcher.drain()


def test_the_wheel_scrolls_whatever_is_under_the_pointer() -> None:
    app = app_with(
        {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"height": 200, "width": "expand"},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": rows(12),
                }
            ],
        }
    )
    sv = app.root.find("sv")
    wheel(app, 50, 50, 100.0)
    assert sv.scroll_offset > 0.0


def test_a_wheel_needs_no_declared_handler() -> None:
    """A scroll view responds natively; `on_wheel:` in a view is optional."""
    app = app_with(
        {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"height": 200, "width": "expand"},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": rows(12),
                }
            ],
        }
    )
    assert app.root.find("sv").handlers == {}
    wheel(app, 50, 50, 100.0)
    assert app.root.find("sv").scroll_offset > 0.0


def test_hit_testing_follows_the_scrolled_content() -> None:
    app = app_with(
        {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"height": 200, "width": "expand"},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": rows(12),
                }
            ],
        }
    )
    sv = app.root.find("sv")
    before = [e.name for e in app.dispatcher.hit_path(50, 10) if e.name]
    sv.set_scroll(ROW_HEIGHT * 3)
    app.update()
    after = [e.name for e in app.dispatcher.hit_path(50, 10) if e.name]
    assert before[0] == "r0"
    assert after[0] == "r3"


def test_absolute_rect_follows_the_scrolled_content() -> None:
    """`absolute_rect()` must agree with `hit_test` about where a scrolled
    descendant actually is. It used to sum raw `.offset`s and ignore
    `child_origin()`, so a widget inside a scrolled ScrollView -- every one
    of the widget demos' own root -- reported its PRE-SCROLL position from
    `absolute_rect()` while `hit_test` (which does thread `child_origin`
    correctly) still found it at its true, scrolled one: a `CodeEditor`
    computing a click's caret position from its own `absolute_rect()` put
    the caret several lines away from the actual click.
    """
    app = app_with(
        {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"height": 200, "width": "expand"},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": rows(12),
                }
            ],
        }
    )
    sv = app.root.find("sv")
    r3 = app.root.find("r3")
    before = r3.absolute_rect().y
    sv.set_scroll(ROW_HEIGHT * 3)
    app.update()
    after = r3.absolute_rect().y
    assert before - after == pytest.approx(ROW_HEIGHT * 3)


def test_the_wheel_chains_to_an_outer_view_once_the_inner_one_is_done() -> None:
    """Swallowing the wheel unconditionally would trap the pointer inside a
    fully-scrolled pane -- the one thing every desktop toolkit avoids."""
    app = app_with(
        {
            "name": "outer",
            "widget": "ScrollView",
            "style": {"height": 200, "width": "expand"},
            "children": [
                {
                    "name": "ocol",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": [
                        {
                            "name": "inner",
                            "widget": "ScrollView",
                            "style": {"height": 100, "width": "expand"},
                            "children": [
                                {
                                    "name": "icol",
                                    "widget": "Vertical",
                                    "style": {"width": "expand"},
                                    "children": rows(6),
                                }
                            ],
                        },
                        *rows(8, "out"),
                    ],
                }
            ],
        }
    )
    outer, inner = app.root.find("outer"), app.root.find("inner")
    assert inner.scrollable and outer.scrollable

    wheel(app, 50, 50, 100.0)
    assert inner.scroll_offset > 0.0
    assert outer.scroll_offset == 0.0, "outer moved while the inner one still had room"

    inner.set_scroll(inner.max_scroll)
    app.update()
    wheel(app, 50, 50, 100.0)
    assert outer.scroll_offset > 0.0, "wheel did not chain outwards at the inner limit"


# ------------------------------------------------------------- horizontal


def test_a_horizontal_scroll_view_measures_and_scrolls_on_x() -> None:
    spec = {
        "name": "sv",
        "widget": "ScrollView",
        "style": {"width": 200, "height": 60, "axis": "horizontal"},
        "children": [
            {
                "name": "row",
                "widget": "Horizontal",
                "children": [
                    {"name": f"c{i}", "widget": "Container", "style": {"width": 80, "height": 40}}
                    for i in range(6)
                ],
            }
        ],
    }
    sv = build_element(parse_view(spec).root)
    sv.layout(Constraints.loose(Size(400, 400)))
    assert sv.content_size.width == 480.0
    assert sv.max_scroll == 280.0
    sv.scroll_by(100.0)
    assert sv.state.scroll.x == 100.0
    assert sv.state.scroll.y == 0.0
    assert sv.child_origin(Offset(0.0, 0.0)) == Offset(-100.0, 0.0)


def test_a_horizontal_view_ignores_vertical_wheel_movement() -> None:
    spec = {
        "name": "sv",
        "widget": "ScrollView",
        "style": {"width": 200, "height": 60, "axis": "horizontal"},
        "children": [
            {
                "name": "row",
                "widget": "Horizontal",
                "children": [
                    {"name": f"c{i}", "widget": "Container", "style": {"width": 80, "height": 40}}
                    for i in range(6)
                ],
            }
        ],
    }
    sv = build_element(parse_view(spec).root)
    sv.layout(Constraints.loose(Size(400, 400)))
    sv.on_wheel(WheelEvent(EventType.WHEEL, dy=100.0))
    assert sv.scroll_offset == 0.0
    sv.on_wheel(WheelEvent(EventType.WHEEL, dx=100.0))
    assert sv.scroll_offset > 0.0


# ------------------------------------------------------------------ state


def test_scroll_position_survives_a_reload() -> None:
    """`state.scroll` is element state, which is exactly what reconciliation
    exists to preserve."""
    from pysilver.tree.reconcile import reconcile

    sv = scroll_view(20)
    sv.set_scroll(200.0)
    same = parse_view(
        {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"height": 200, "width": 300},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": rows(20),
                }
            ],
        }
    ).root
    result, _ = reconcile(sv, same, build_element)
    assert result is sv
    assert result.scroll_offset == 200.0


def test_the_canvas_wheel_payload_drives_scrolling() -> None:
    """Guards the boundary with rendercanvas.

    The keys and sign convention here are copied from what
    `rendercanvas/glfw.py` actually submits -- notably that it pre-negates
    `dy`, so positive means scrolling down. A dependency upgrade that changed
    either would otherwise fail silently, since a wheel event nothing consumes
    looks exactly like no wheel event at all.
    """
    app = app_with(
        {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"height": 200, "width": "expand"},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "style": {"width": "expand"},
                    "children": rows(12),
                }
            ],
        }
    )
    sv = app.root.find("sv")
    payload = {
        "event_type": "wheel",
        "dx": 0.0,
        "dy": 100.0,
        "x": 50.0,
        "y": 50.0,
        "buttons": (),
        "modifiers": (),
    }

    app._on_canvas_event(payload)
    app.dispatcher.drain()
    assert sv.scroll_offset == 100.0 * ScrollViewElement.WHEEL_SCALE

    app._on_canvas_event({**payload, "dy": -100.0})
    app.dispatcher.drain()
    assert sv.scroll_offset == 0.0
