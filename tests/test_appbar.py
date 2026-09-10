"""The collapsing top app bar.

Scroll-linked rather than timed: the height is a direct function of the offset,
so it tracks a drag exactly instead of chasing it. The load-bearing test is
`test_the_scrollable_extent_does_not_change_as_the_bar_collapses` -- without
that invariant the bar and the view it follows feed back into each other.
"""

from __future__ import annotations

import pytest

from pysilver import App, Settings, Theme
from pysilver.layout import Offset
from pysilver.paint import NO_TOKEN, DisplayList
from pysilver.theme import Palette
from pysilver.tree.element import PaintContext
from pysilver.widgets.navigation import TopAppBarElement

PALETTE = Palette(Theme(dark=True))


def app_with(variant: str = "large", rows: int = 20, *, link: bool = True, height: int = 400):
    style = {"variant": variant, "width": "expand"}
    if link:
        style["collapses_with"] = "body"
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [
                    {"name": "bar", "widget": "TopAppBar", "text": "Inbox", "style": style},
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
                                        "name": f"r{i}",
                                        "widget": "ListItem",
                                        "text": f"Row {i}",
                                        "style": {"width": "expand"},
                                    }
                                    for i in range(rows)
                                ],
                            }
                        ],
                    },
                ],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=400, height=height),
    )
    app.mount()
    app.paint(DisplayList())
    return app, app.root.find("bar"), app.root.find("body")


def settle(app, frames: int = 4) -> None:
    for _ in range(frames):
        app.paint(DisplayList())


# ------------------------------------------------------------- geometry


@pytest.mark.parametrize(
    ("variant", "expected"),
    [("small", 64.0), ("center_aligned", 64.0), ("medium", 112.0), ("large", 152.0)],
)
def test_each_variant_has_its_expanded_height(variant: str, expected: float) -> None:
    _app, bar, _body = app_with(variant)
    assert bar.expanded_height == expected
    assert bar.size.height == expected


def test_a_small_bar_has_nothing_to_collapse() -> None:
    app, bar, body = app_with("small")
    body.set_scroll(500)
    settle(app)
    assert bar.collapse == 0.0
    assert bar.size.height == TopAppBarElement.HEIGHT


def test_the_bar_shrinks_to_a_small_one_as_the_page_scrolls() -> None:
    """M3: medium and large bars "transform into small app bars"."""
    app, bar, body = app_with("large")
    assert bar.size.height == 152.0

    body.set_scroll(44)
    settle(app)
    assert bar.size.height == pytest.approx(108.0), "half-way through the travel"

    body.set_scroll(88)
    settle(app)
    assert bar.size.height == TopAppBarElement.HEIGHT
    assert bar.collapse == 1.0


def test_it_stays_small_however_far_the_page_scrolls() -> None:
    """M3: "they should remain small until the page is scrolled back to the top"."""
    app, bar, body = app_with("large")
    body.set_scroll(5000)
    settle(app)
    assert bar.collapse == 1.0
    body.set_scroll(0)
    settle(app)
    assert bar.collapse == 0.0
    assert bar.size.height == 152.0


def test_the_collapse_tracks_the_offset_with_no_clock() -> None:
    """Scroll-linked, not timed: it must not need the animation ticker, or it
    would lag a drag."""
    app, bar, body = app_with("large")
    body.set_scroll(22)
    settle(app)
    assert bar.collapse == pytest.approx(0.25)
    assert not app.motion.active


def test_an_unlinked_bar_stays_expanded() -> None:
    app, bar, body = app_with("large", link=False)
    body.set_scroll(500)
    settle(app)
    assert bar.collapse == 0.0
    assert bar.size.height == 152.0


def test_naming_a_view_that_does_not_exist_is_not_fatal() -> None:
    """A typo in a view file leaves the bar expanded rather than raising
    mid-frame, which is the same choice `anchor:` makes for overlays."""
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [
                    {
                        "name": "bar",
                        "widget": "TopAppBar",
                        "text": "T",
                        "style": {"variant": "large", "collapses_with": "nope", "width": "expand"},
                    }
                ],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=400, height=300),
    )
    app.mount()
    app.paint(DisplayList())
    bar = app.root.find("bar")
    assert bar.collapse == 0.0
    assert bar.size.height == 152.0


# ------------------------------------------------------------ the invariant


def test_the_scrollable_extent_does_not_change_as_the_bar_collapses() -> None:
    """The bar and the view size each other, so this has to be broken.

    Collapsing enlarges the viewport, which would shrink `max_scroll`, which
    would clamp the offset down, which would un-collapse the bar. Measured
    before the fix: a list that snapped back to its top with the bar stuck
    collapsed.
    """
    app, _bar, body = app_with("large")
    extents = []
    for offset in (0, 22, 44, 66, 88, 200):
        body.set_scroll(offset)
        settle(app)
        extents.append(round(body.max_scroll, 3))
    assert len(set(extents)) == 1, f"max_scroll varied with the collapse: {extents}"


def test_a_barely_scrollable_page_still_collapses_and_settles() -> None:
    """The degenerate case: content only as tall as the collapse frees."""
    app, bar, body = app_with("large", rows=6)
    body.set_scroll(10_000)
    states = [
        (round(body.scroll_offset, 1), round(bar.size.height, 1))
        for _ in range(5)
        if not app.paint(DisplayList())
    ]
    assert len(set(states)) == 1, f"it oscillated: {states}"
    assert bar.collapse == 1.0, "the bar failed to collapse at the end of a short page"
    assert body.scroll_offset == body.max_scroll


# ---------------------------------------------------------------- painting


def test_the_container_fills_with_surface_container_on_scroll() -> None:
    """M3: "on scroll, the container changes color to surface container"."""
    app, _bar, body = app_with("large")
    flat = DisplayList()
    app.paint(flat)
    fill = PALETTE.index("surface_container")
    assert not any(int(s["flags"][2]) == fill for s in flat.view)

    body.set_scroll(88)
    settle(app)
    scrolled = DisplayList()
    app.paint(scrolled)
    assert any(int(s["flags"][2]) == fill for s in scrolled.view)


def test_the_headline_shrinks_as_the_bar_collapses() -> None:
    """So the expanded and small forms agree at the moment of arrival."""
    app, bar, body = app_with("large")

    def bar_glyphs() -> list:
        """The bar's own glyphs, painted on their own.

        Filtering the app's display list by y does not work and the reason is
        worth keeping: a row straddling the top of the viewport IS painted, and
        the shader clips the part above it. So the frame legitimately contains
        glyphs above the viewport line, and counting them would make this test
        about scrolling rather than about the headline.
        """
        dl = DisplayList()
        ctx = PaintContext(
            display_list=dl,
            palette=Palette(Theme(dark=True)),
            text=bar.text_engine,
            pixel_ratio=1.0,
        )
        bar.paint(ctx, Offset(0.0, 0.0))
        return [s for s in dl.view if int(s["flags"][0]) == 1]

    big_glyphs = bar_glyphs()
    body.set_scroll(88)
    settle(app)
    small_glyphs = bar_glyphs()
    # Same title, so the same glyphs -- but a smaller box for them.
    assert len(big_glyphs) == len(small_glyphs)
    widths_big = max(float(s["rect"][2]) for s in big_glyphs)
    widths_small = max(float(s["rect"][2]) for s in small_glyphs)
    assert widths_small < widths_big


def test_an_explicit_background_overrides_the_scroll_fill() -> None:
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [
                    {
                        "name": "bar",
                        "widget": "TopAppBar",
                        "text": "T",
                        "style": {
                            "variant": "large",
                            "background": "primary_container",
                            "width": "expand",
                        },
                    }
                ],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=400, height=200),
    )
    app.mount()
    dl = DisplayList()
    app.paint(dl)
    tokens = {int(s["flags"][2]) for s in dl.view if int(s["flags"][2]) != NO_TOKEN}
    assert PALETTE.index("primary_container") in tokens
    assert PALETTE.index("surface_container") not in tokens


def test_a_large_bar_expands_its_headline_further_than_a_medium_one() -> None:
    """M3: headline-medium (28sp) expanded for medium, headline-large (32sp)
    expanded for large -- two different roles, not one size shared by both.
    """

    def title_glyphs(variant: str) -> list:
        _app, bar, _body = app_with(variant, link=False)
        dl = DisplayList()
        ctx = PaintContext(
            display_list=dl,
            palette=Palette(Theme(dark=True)),
            text=bar.text_engine,
            pixel_ratio=1.0,
        )
        bar.paint(ctx, Offset(0.0, 0.0))
        return [s for s in dl.view if int(s["flags"][0]) == 1]

    medium_glyphs = title_glyphs("medium")
    large_glyphs = title_glyphs("large")
    assert len(medium_glyphs) == len(large_glyphs)  # same title, "Inbox"
    medium_width = max(float(s["rect"][2]) for s in medium_glyphs)
    large_width = max(float(s["rect"][2]) for s in large_glyphs)
    assert large_width > medium_width
