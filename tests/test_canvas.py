"""Canvas: a freeform drawing surface driven by an `on_paint` handler.

No M3 grounding exists for this either -- checked directly against
`M3-References`, the same way every other ungrounded widget this session was.
"""

from __future__ import annotations

import numpy as np
import pytest

from pysilver import App, Theme
from pysilver.layout import Constraints, Size
from pysilver.paint import NO_TOKEN, DisplayList, Kind
from pysilver.spec import parse_view
from pysilver.theme import Palette
from pysilver.widgets import build_element
from pysilver.widgets.canvas import CanvasElement

PAL = Palette(Theme(dark=True))
LOOSE = Constraints.loose(Size(1000.0, 800.0))


def laid_out(spec: dict, constraints: Constraints = LOOSE):
    element = build_element(parse_view(spec).root)
    element.layout(constraints)
    return element


def canvas_app(painter, *, style: dict | None = None) -> App:
    """A Canvas inside a Vertical, so its own style actually takes effect --
    the root element is force-fit to the window's own tight constraints, the
    same reason `test_dock.py` and every sizing test here wrap its subject."""
    view = {
        "root": {
            "widget": "Vertical",
            "children": [
                {
                    "name": "c",
                    "widget": "Canvas",
                    "style": style or {"width": 200, "height": 100},
                    "handlers": {"on_paint": "draw"},
                }
            ],
        }
    }
    app = App(view, theme=Theme(dark=True))
    painter.__name__ = "draw"
    app.handler(painter)
    app.mount()
    app.update()
    return app


def paint(app: App) -> DisplayList:
    dl = DisplayList()
    app.paint(dl)
    return dl


def kinds(dl: DisplayList) -> list[int]:
    return [int(s["flags"][0]) for s in dl.view]


# --------------------------------------------------------------- registered


def test_kind_builds() -> None:
    assert laid_out({"name": "w", "widget": "Canvas"}) is not None


def test_canvas_is_a_canvas_element() -> None:
    element = laid_out({"name": "w", "widget": "Canvas"})
    assert isinstance(element, CanvasElement)


# ------------------------------------------------------------------- sizing


def test_an_explicit_size_is_honoured() -> None:
    size = laid_out({"name": "w", "widget": "Canvas", "style": {"width": 300, "height": 150}}).size
    assert size == Size(300.0, 150.0)


def test_with_no_size_and_no_bound_it_falls_back_to_a_concrete_default() -> None:
    """The same trap `ButtonElement.HEIGHT` exists to avoid: a widget with no
    intrinsic content of its own that lays out 0x0 draws nothing, silently."""
    element = build_element(parse_view({"name": "w", "widget": "Canvas"}).root)
    size = element.layout(Constraints.unbounded())
    assert size.width == CanvasElement.DEFAULT_SIZE
    assert size.height == CanvasElement.DEFAULT_SIZE


def test_with_a_bounded_parent_and_no_explicit_size_it_fills_it() -> None:
    element = build_element(parse_view({"name": "w", "widget": "Canvas"}).root)
    size = element.layout(Constraints.tight(Size(640.0, 480.0)))
    assert size == Size(640.0, 480.0)


# ------------------------------------------------------------------- paint


def test_the_handler_receives_a_canvas_context_sized_to_the_element() -> None:
    seen = []

    def draw(canvas):
        seen.append(canvas.size)

    app = canvas_app(draw, style={"width": 200, "height": 100})
    paint(app)
    assert seen == [Size(200.0, 100.0)]


def test_no_handler_paints_nothing_but_still_lays_out() -> None:
    element = laid_out({"name": "w", "widget": "Canvas", "style": {"width": 50, "height": 50}})
    assert element.size == Size(50.0, 50.0)


def test_a_background_paints_before_the_handlers_own_drawing() -> None:
    def draw(canvas):
        canvas.rect(0, 0, 10, 10, color="primary")

    app = canvas_app(draw, style={"width": 200, "height": 100, "background": "surface_container"})
    dl = paint(app)
    ks = kinds(dl)
    assert ks[0] == Kind.BOX  # the background
    assert Kind.BOX in ks[1:]  # the handler's own rect


@pytest.mark.parametrize(
    ("method", "kind"),
    [
        (lambda c: c.line(0, 0, 10, 10), Kind.SEGMENT),
        (lambda c: c.rect(0, 0, 10, 10), Kind.BOX),
        (lambda c: c.circle(10, 10, 5), Kind.BOX),
        (lambda c: c.arc(10, 10, 5, thickness=2, start=0.0, sweep=3.0), Kind.ARC),
        (lambda c: c.polygon(0, 0, 10, 10, sides=6), Kind.POLYGON),
        (lambda c: c.text(0, 0, "hi"), Kind.GLYPH),
    ],
)
def test_each_primitive_emits_the_matching_kind(method, kind) -> None:
    app = canvas_app(lambda c: method(c))
    dl = paint(app)
    assert kind in kinds(dl)


def test_a_token_colour_resolves_through_the_palette() -> None:
    def draw(canvas):
        canvas.rect(0, 0, 10, 10, color="primary")

    app = canvas_app(draw)
    dl = paint(app)
    fill_token = int(dl.view[-1]["flags"][2])
    assert fill_token == PAL.index("primary")


def test_a_literal_colour_bypasses_the_palette() -> None:
    def draw(canvas):
        canvas.rect(0, 0, 10, 10, color=(1.0, 0.0, 0.0, 1.0))

    app = canvas_app(draw)
    dl = paint(app)
    last = dl.view[-1]
    fill_token = int(last["flags"][2])
    fill_color = tuple(float(v) for v in last["fill"])
    assert fill_token == NO_TOKEN
    assert fill_color == (1.0, 0.0, 0.0, 1.0)


def test_a_literal_colour_is_converted_from_srgb_to_linear() -> None:
    """The render target is `rgba8unorm-srgb` and encodes on write
    (ARCHITECTURE.md 5.6.1) -- a handler's literal colour is the sRGB value
    it looks like, so it must reach the display list already converted, or
    it renders lighter than intended. 1.0/0.0 are fixed points of the sRGB
    curve (see the test above), which is why this needs a mid-range value
    to actually exercise the conversion -- 0.5 sRGB is well below 0.5
    linear."""
    from pysilver.theme import srgb_to_linear

    def draw(canvas):
        canvas.rect(0, 0, 10, 10, color=(0.5, 0.5, 0.5, 1.0))

    app = canvas_app(draw)
    dl = paint(app)
    fill_color = tuple(float(v) for v in dl.view[-1]["fill"])
    expected = float(srgb_to_linear(np.array([0.5]))[0])
    assert fill_color[0] == pytest.approx(expected)
    assert fill_color[0] < 0.3
    assert fill_color[3] == 1.0


def test_a_literal_colour_in_text_spans_is_also_converted() -> None:
    def draw(canvas):
        canvas.text(0, 0, "x", color=(0.5, 0.5, 0.5, 1.0))

    app = canvas_app(draw)
    dl = paint(app)
    glyph = next(s for s in dl.view if int(s["flags"][0]) == Kind.GLYPH)
    assert float(glyph["fill"][0]) < 0.3


def test_circle_is_a_fully_rounded_box() -> None:
    def draw(canvas):
        canvas.circle(20, 20, 8, color="primary")

    app = canvas_app(draw)
    dl = paint(app)
    last = dl.view[-1]
    rect = tuple(float(v) for v in last["rect"])
    radii = tuple(float(v) for v in last["radii"])
    assert rect[2] == pytest.approx(16.0)
    assert rect[3] == pytest.approx(16.0)
    assert all(r == pytest.approx(8.0) for r in radii)


# ---------------------------------------------------------------- clipping


def test_every_primitive_carries_the_canvas_own_rect_as_its_clip() -> None:
    """The clip a shape's own geometry is tested against at the pixel level
    is the shader's job (`clip.z/w > 0.0` in `ui.wgsl`), not this CPU-side
    data -- what belongs to `Canvas` is emitting the *right* clip rect, which
    is its own bounds intersected with whatever an ancestor already set."""

    def draw(canvas):
        canvas.rect(-1000, -1000, 10, 10, color="primary")  # off past the edge

    app = canvas_app(draw, style={"width": 50, "height": 50})
    dl = paint(app)
    clip = tuple(float(v) for v in dl.view[-1]["clip"])
    assert clip[2] == pytest.approx(50.0)
    assert clip[3] == pytest.approx(50.0)


def test_scrolled_fully_out_of_view_the_clip_floors_to_hidden_extent() -> None:
    """Direct unit test of `_clipped`, the same intersect-and-floor formula
    `TreeItemElement`/`DockPanelElement` use -- see ARCHITECTURE.md 5.8.6 for
    why an exact-zero clip dimension is silently read as "unclipped" rather
    than "hidden" by the shader, which is what the floor avoids."""
    from pysilver.layout import Offset
    from pysilver.paint import DisplayList as _DisplayList
    from pysilver.tree.element import PaintContext

    element = laid_out({"name": "w", "widget": "Canvas", "style": {"width": 50, "height": 50}})
    ctx = PaintContext(display_list=_DisplayList(), palette=PAL, clip=(0.0, 0.0, 10.0, 10.0))
    clipped = element._clipped(ctx, Offset(1000.0, 1000.0))
    assert clipped.clip[2] == CanvasElement.HIDDEN_EXTENT
    assert clipped.clip[3] == CanvasElement.HIDDEN_EXTENT


# ------------------------------------------------------------- invalidation


def test_the_handler_runs_again_only_after_mark_needs_paint() -> None:
    calls = []

    def draw(canvas):
        calls.append(None)
        canvas.rect(0, 0, 5, 5, color="primary")

    app = canvas_app(draw)
    paint(app)
    assert len(calls) == 1

    paint(app)  # nothing invalidated -- the cached slice is spliced instead
    assert len(calls) == 1

    app.root.find("c").mark_needs_paint()
    paint(app)
    assert len(calls) == 2


def test_measure_text_reports_a_real_size() -> None:
    sizes = []

    def draw(canvas):
        sizes.append(canvas.measure_text("hello", font_size=16.0))

    app = canvas_app(draw)
    paint(app)
    assert sizes[0].width > 0.0
    assert sizes[0].height > 0.0
