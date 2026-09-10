"""Virtualised scrolling: not painting what the clip would discard.

A **paint** optimisation rather than a different kind of list. Content is still
laid out, so scroll extents, hit testing and the scrollbar are untouched; what
stops happening is building instances the shader would throw away. Clipping is
analytic and in-shader, so anything wholly outside the clip contributes nothing
to the frame -- skipping it is exactly equivalent, not an approximation, and
the golden suite passing unchanged is the evidence for that.

Measured on a 2000-row list in a 600px viewport: 138 ms per scroll frame and
52,891 instances before, 1.29 ms and 194 after.
"""

from __future__ import annotations

import pytest

from pysilver.layout import Constraints, Offset, Size
from pysilver.paint import DisplayList
from pysilver.spec import parse_view
from pysilver.theme import Palette, Theme
from pysilver.tree.element import PaintContext
from pysilver.widgets import build_element

PALETTE = Palette(Theme(dark=True))
ROW_HEIGHT = 56.0


def list_view(rows: int = 60, height: float = 200.0):
    view = {
        "root": {
            "name": "sv",
            "widget": "ScrollView",
            "style": {"width": 300, "height": height},
            "children": [
                {
                    "name": "col",
                    "widget": "Vertical",
                    "children": [
                        {"name": f"r{i}", "widget": "ListItem", "text": f"Row {i}"}
                        for i in range(rows)
                    ],
                }
            ],
        }
    }
    root = build_element(parse_view(view).root)
    root.layout(Constraints.tight(Size(300.0, height)))
    return root


def paint(root, scroll: float = 0.0) -> DisplayList:
    root.set_scroll(scroll)
    dl = DisplayList()
    ctx = PaintContext(display_list=dl, palette=PALETTE, text=root.text_engine, pixel_ratio=1.0)
    root.paint(ctx, Offset(0.0, 0.0))
    return dl


# ------------------------------------------------------------------- culling


def test_a_long_list_costs_what_is_visible_not_what_exists() -> None:
    """The whole point. Two lists differing only in length must paint the same
    amount, or cost still tracks the data rather than the viewport.

    Each is painted once first: the extent is measured *from* a paint, so the
    very first frame has nothing to cull against and draws everything. That is
    the one frame that still costs what the list is long.
    """
    short, long = list_view(rows=30), list_view(rows=3000)
    paint(short)
    paint(long)
    assert len(paint(short, scroll=100.0)) == len(paint(long, scroll=100.0))


@pytest.mark.parametrize("scroll", [100.0, 900.0, 1500.0, 3000.0])
def test_the_painted_count_stays_bounded_wherever_you_scroll(scroll: float) -> None:
    """Not an exact count -- how many rows a 200px viewport shows depends on
    whether one straddles an edge. What must hold is that it is bounded by the
    viewport rather than by the list."""
    view = list_view(rows=60)
    unculled = len(paint(view))  # the first pass has no extents to cull against
    assert len(paint(view, scroll=scroll)) < unculled / 5


def test_a_row_straddling_the_viewport_edge_is_still_painted() -> None:
    """The case culling must NOT get wrong. A row half over the top edge is
    partly visible; the shader clips the rest. Culling it would leave a gap
    that only appears at particular scroll offsets."""
    view = list_view(rows=60)
    paint(view)
    dl = paint(view, scroll=ROW_HEIGHT / 2.0)
    tops = [float(s["rect"][1]) for s in dl.view]
    assert min(tops) < 0.0, "the straddling row is painted, and clipped in the shader"


def test_an_unclipped_context_never_culls() -> None:
    """Without a clip there is nothing to be outside of, so a plain Vertical must
    paint every child however far down the page it is."""
    view = {
        "root": {
            "name": "col",
            "widget": "Vertical",
            "children": [
                {"name": f"r{i}", "widget": "ListItem", "text": f"Row {i}"} for i in range(40)
            ],
        }
    }
    root = build_element(parse_view(view).root)
    root.layout(Constraints(0.0, 300.0, 0.0, 100.0))
    dl = DisplayList()
    ctx = PaintContext(display_list=dl, palette=PALETTE, text=root.text_engine, pixel_ratio=1.0)
    root.paint(ctx, Offset(0.0, 0.0))
    assert len(dl) > 40, "every row painted despite overflowing a 100px box"


# -------------------------------------------------------------------- safety


def test_a_dirty_element_is_never_culled() -> None:
    """The rule that makes this safe. The extent is exact only while the
    content has not changed; a dirty element repaints and re-measures. Trusting
    a stale extent would let something that grew off-screen stay wrongly
    hidden."""
    view = list_view(rows=60)
    paint(view)
    row = view.find("r50")
    assert row is not None
    row.mark_needs_paint()
    assert row._needs_paint is True
    ctx = PaintContext(
        display_list=DisplayList(), palette=PALETTE, text=view.text_engine, pixel_ratio=1.0
    )
    ctx = PaintContext(
        display_list=ctx.display_list,
        palette=PALETTE,
        text=view.text_engine,
        pixel_ratio=1.0,
        clip=(0.0, 0.0, 300.0, 200.0),
    )
    assert row._culled(ctx, Offset(0.0, 5000.0)) is False, "dirty, so it must repaint"


def test_an_element_measured_at_another_scale_is_never_culled() -> None:
    """The extent is in physical pixels. A DPI change makes the stored numbers
    describe a different frame, so they must not be trusted."""
    view = list_view(rows=60)
    paint(view)
    row = view.find("r0")
    ctx = PaintContext(
        display_list=DisplayList(),
        palette=PALETTE,
        text=view.text_engine,
        pixel_ratio=2.0,
        clip=(0.0, 0.0, 300.0, 200.0),
    )
    assert row._culled(ctx, Offset(0.0, 5000.0)) is False


def test_the_extent_is_measured_from_what_was_painted() -> None:
    """Not inferred from the element's size, which would be wrong for a shadow
    reaching past its box, a focus ring outside its control, or a child
    overflowing its parent -- and wrong only near a viewport edge, which is the
    worst way for it to be wrong."""
    view = list_view(rows=10)
    paint(view)
    row = view.find("r0")
    assert row._paint_extent is not None
    x0, y0, x1, y1 = row._paint_extent
    assert x1 > x0 and y1 > y0
    # A ListItem with no background paints its label and nothing else, so the
    # extent is the ink -- about 16px -- and NOT the 56dp row. That is the
    # point: it measures what was drawn, not what was reserved.
    assert y1 - y0 < ROW_HEIGHT


@pytest.mark.parametrize("scroll", [0.0, 57.0, 200.0, 1000.0])
def test_culling_never_changes_what_is_visible(scroll: float) -> None:
    """The equivalence claim, checked against the ground truth: every instance
    painted with culling on must be one the unculled frame also had. The golden
    suite passing unchanged says the same thing in pixels."""
    view = list_view(rows=60)
    paint(view)
    culled = paint(view, scroll=scroll)

    fresh = list_view(rows=60)  # never painted, so nothing to cull against
    fresh.set_scroll(scroll)
    dl = DisplayList()
    ctx = PaintContext(display_list=dl, palette=PALETTE, text=fresh.text_engine, pixel_ratio=1.0)
    fresh.paint(ctx, Offset(0.0, 0.0))

    def visible(d):
        """Instances that actually intersect the 200px viewport. A looser
        window would count rows the shader clips away, which are exactly the
        ones culling is allowed to skip."""
        return {
            (round(float(s["rect"][0]), 2), round(float(s["rect"][1]), 2), int(s["flags"][0]))
            for s in d.view
            if float(s["rect"][1]) + float(s["rect"][3]) > 0.0 and float(s["rect"][1]) < 200.0
        }

    assert visible(culled) == visible(dl)
