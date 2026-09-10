"""Window resize: the frame must be correct, and it must be affordable.

Both of these are regressions from real bugs seen in a screen recording of the
gallery, and neither showed up in any other test because both need the *same
tree laid out twice at different sizes* -- everything else here builds a tree,
lays it out once, and asserts on that.

The first was silent: rows kept painting at their old width, and because only
rows that also moved vertically repainted, one frame showed several different
widths at once. The second was not silent but was easy to blame on the window
manager: a resize frame cost more than a frame's budget, so a drag queued
events and the window trailed the pointer by seconds.
"""

from __future__ import annotations

import time

import pytest

from pysilver.layout import Constraints, Offset, Size
from pysilver.paint import DisplayList
from pysilver.spec import parse_view
from pysilver.text.segment import _break_opportunities, _clusters
from pysilver.theme import Palette, Theme
from pysilver.tree.element import PaintContext
from pysilver.widgets import build_element

PALETTE = Palette(Theme())

STRETCHED = {
    "name": "root",
    "widget": "Vertical",
    "style": {
        "width": "expand",
        "height": "expand",
        "padding": 20,
        "spacing": 16,
        "cross_alignment": "stretch",
    },
    "children": [
        {"name": "bar", "widget": "Container", "style": {"height": 40, "background": "primary"}},
        {
            "name": "body",
            "widget": "Text",
            "text": "A paragraph long enough that it has to wrap, and therefore long "
            "enough that re-wrapping it is the expensive part of a resize.",
            "style": {"color": "on_surface"},
        },
    ],
}


def paint_at(root, width: float, height: float) -> DisplayList:
    root.layout(Constraints.tight(Size(width, height)))
    display_list = DisplayList()
    ctx = PaintContext(
        display_list=display_list, palette=PALETTE, text=root.text_engine, pixel_ratio=1.0
    )
    root.paint(ctx, Offset(0.0, 0.0))
    return display_list


def widest(display_list: DisplayList) -> float:
    return max(
        float(instance["rect"][0]) + float(instance["rect"][2]) for instance in display_list.view
    )


# ------------------------------------------------------- the stale-cache bug


def test_a_row_that_kept_its_origin_is_repainted_at_its_new_width() -> None:
    """The bug, in the smallest form that shows it.

    The paint cache was keyed on an element's absolute origin alone. A row
    stretched across a Vertical keeps its origin when the window widens and
    changes only its width, so it passed the check and was spliced from its
    old, narrower slice -- correct geometry in the element tree, stale
    geometry on screen.
    """
    root = build_element(parse_view(STRETCHED).root)
    paint_at(root, 400.0, 300.0)
    resized = paint_at(root, 800.0, 300.0)

    bar = root.find("bar")
    assert bar.size.width == 760.0, "the element itself laid out correctly all along"
    painted = [
        float(i["rect"][2]) for i in resized.view if float(i["rect"][1]) == bar.absolute_rect().y
    ]
    assert 760.0 in painted, f"the bar was painted at {painted}, not at its actual width"


def test_a_resized_tree_paints_what_a_fresh_one_does() -> None:
    """The general statement of the same thing: how a tree arrived at a size
    must not change what it draws there."""
    reused = build_element(parse_view(STRETCHED).root)
    paint_at(reused, 400.0, 300.0)
    paint_at(reused, 620.0, 300.0)
    after_resize = paint_at(reused, 800.0, 300.0)

    fresh = build_element(parse_view(STRETCHED).root)
    from_scratch = paint_at(fresh, 800.0, 300.0)

    assert len(after_resize) == len(from_scratch)
    assert widest(after_resize) == widest(from_scratch)


def test_a_pixel_ratio_change_repaints() -> None:
    """A cached slice holds *physical* pixels, so moving a window to a display
    with a different scale invalidates it as surely as a resize does."""
    root = build_element(parse_view(STRETCHED).root)
    root.layout(Constraints.tight(Size(400.0, 300.0)))

    def at_ratio(ratio: float) -> DisplayList:
        display_list = DisplayList()
        ctx = PaintContext(
            display_list=display_list, palette=PALETTE, text=root.text_engine, pixel_ratio=ratio
        )
        root.paint(ctx, Offset(0.0, 0.0))
        return display_list

    single = widest(at_ratio(1.0))
    # abs, not rel=1e-6: whichever rect is widest can be a text glyph rather
    # than a solid box, and a glyph's physical extent is font-hinting-rounded
    # independently at each DPI, so it will not double exactly. The stale-slice
    # bug this test exists to catch would leave `ratio=2.0` close to `single`
    # (undoubled, a huge gap), not a couple of physical pixels off of double.
    assert widest(at_ratio(2.0)) == pytest.approx(single * 2, abs=2.0)


def test_a_changed_clip_repaints() -> None:
    """Clip rects are baked into the instances a slice holds, so an ancestor
    whose clip moves must not have children spliced from the old one."""
    root = build_element(parse_view(STRETCHED).root)
    root.layout(Constraints.tight(Size(400.0, 300.0)))

    def with_clip(clip):
        display_list = DisplayList()
        ctx = PaintContext(
            display_list=display_list,
            palette=PALETTE,
            text=root.text_engine,
            pixel_ratio=1.0,
            clip=clip,
        )
        root.paint(ctx, Offset(0.0, 0.0))
        return [tuple(i["clip"]) for i in display_list.view]

    with_clip((0.0, 0.0, 400.0, 300.0))
    narrowed = with_clip((0.0, 0.0, 200.0, 300.0))
    assert all(c[2] == 200.0 for c in narrowed), "children kept the old clip"


def test_an_unchanged_frame_still_reuses_the_cache() -> None:
    """The fix must not turn the cache off. Painting the same tree at the same
    size twice has to splice, or every frame pays a full rebuild."""
    root = build_element(parse_view(STRETCHED).root)
    paint_at(root, 400.0, 300.0)
    bar = root.find("bar")
    cached = bar._cached
    paint_at(root, 400.0, 300.0)
    assert bar._cached is cached, "the subtree was rebuilt when nothing had changed"


# --------------------------------------------------------- the cost of one


def test_segmentation_is_computed_once_per_string() -> None:
    """Where the resize frame went. Wrapping asks for a paragraph's break
    positions once per candidate line and again on every relayout, and none of
    it depends on the width being tried -- so a drag recomputed the same UAX
    #14 and #29 answers hundreds of times a second. Profiling put uniseg at
    54% of the frame.
    """
    text = "A paragraph that will be measured at many different widths in a row."
    _break_opportunities.cache_clear()
    _clusters.cache_clear()
    root = build_element(parse_view(STRETCHED).root)
    for width in range(300, 800, 5):
        paint_at(root, float(width), 300.0)
    breaks = _break_opportunities.cache_info()
    assert breaks.hits > breaks.misses * 20, f"line breaking was recomputed: {breaks}"
    assert _break_opportunities(text) is _break_opportunities(text), "same object, not recomputed"


def test_a_resize_frame_fits_in_a_frame() -> None:
    """A wall-clock assertion, kept deliberately loose.

    The measured regression was 17.6ms mean against a 16.7ms budget, which is
    what made a drag queue events and trail the pointer by seconds; the fix
    brought it to 1.3ms. A 10ms ceiling is far enough above the fix and far
    enough below the bug to fail on a return of the problem without failing on
    a slow machine.
    """
    root = build_element(parse_view(STRETCHED).root)
    for width in range(300, 400, 10):
        paint_at(root, float(width), 300.0)

    worst = 0.0
    for width in range(400, 900, 7):
        start = time.perf_counter()
        paint_at(root, float(width), 300.0)
        worst = max(worst, (time.perf_counter() - start) * 1000)
    assert worst < 10.0, f"the worst resize frame took {worst:.1f} ms"
