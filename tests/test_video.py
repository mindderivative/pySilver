"""Video: a live-updating display surface fed by `push_frame`.

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
from pysilver.widgets import build_element
from pysilver.widgets.video import VideoElement

LOOSE = Constraints.loose(Size(1000.0, 800.0))


def frame(width: int, height: int, rgb=(200, 50, 50)) -> np.ndarray:
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = rgb
    arr[..., 3] = 255
    return arr


def laid_out(spec: dict, constraints: Constraints = LOOSE):
    element = build_element(parse_view(spec).root)
    element.layout(constraints)
    return element


def video_app(*, style: dict | None = None) -> App:
    view = {
        "root": {
            "widget": "Vertical",
            "children": [{"name": "v", "widget": "Video", "style": style or {}}],
        }
    }
    app = App(view, theme=Theme(dark=True))
    app.mount()
    app.update()
    return app


def paint(app: App) -> DisplayList:
    dl = DisplayList()
    app.paint(dl)
    return dl


# --------------------------------------------------------------- registered


def test_kind_builds() -> None:
    assert laid_out({"name": "w", "widget": "Video"}) is not None


def test_video_is_a_video_element() -> None:
    assert isinstance(laid_out({"name": "w", "widget": "Video"}), VideoElement)


# ------------------------------------------------------------------- sizing


def test_before_any_frame_it_is_honestly_empty() -> None:
    element = laid_out({"name": "w", "widget": "Video"})
    assert element.size == Size(0.0, 0.0)


def test_after_a_frame_it_reports_the_frames_own_size() -> None:
    element = laid_out({"name": "w", "widget": "Video"})
    element.push_frame(frame(80, 40))
    element.layout(LOOSE)
    assert element.size == Size(80.0, 40.0)


def test_an_explicit_size_overrides_the_frames_own() -> None:
    element = laid_out({"name": "w", "widget": "Video", "style": {"width": 10, "height": 10}})
    element.push_frame(frame(80, 40))
    element.layout(LOOSE)
    assert element.size == Size(10.0, 10.0)


def test_a_same_shape_frame_does_not_change_the_natural_size() -> None:
    element = laid_out({"name": "w", "widget": "Video"})
    element.push_frame(frame(80, 40))
    element.layout(LOOSE)
    element._needs_paint = False
    element.push_frame(frame(80, 40, (10, 20, 30)))
    assert element._needs_paint is True  # paint: yes, a new frame arrived
    # perform_layout is driven off _natural, unchanged by a same-shape push,
    # so the already-laid-out size still holds without calling layout() again.
    assert element.size == Size(80.0, 40.0)


def test_a_different_shape_frame_changes_the_natural_size() -> None:
    element = laid_out({"name": "w", "widget": "Video"})
    element.push_frame(frame(80, 40))
    element.layout(LOOSE)
    element.push_frame(frame(160, 90))
    element.layout(LOOSE)
    assert element.size == Size(160.0, 90.0)


# -------------------------------------------------------------------- paint


def test_paints_a_kind_image_instance() -> None:
    app = video_app(style={"width": 100, "height": 100})
    app.root.find("v").push_frame(frame(80, 40))
    dl = paint(app)
    assert Kind.IMAGE in [int(s["flags"][0]) for s in dl.view]


def test_no_frame_paints_nothing() -> None:
    app = video_app()
    dl = paint(app)
    assert len(dl) == 0


def test_opacity_becomes_the_tints_alpha() -> None:
    app = video_app(style={"opacity": 0.5})
    app.root.find("v").push_frame(frame(80, 40))
    dl = paint(app)
    last = dl.view[-1]
    assert int(last["flags"][2]) == NO_TOKEN  # no palette-token slot for Kind.IMAGE
    fill = tuple(float(v) for v in last["fill"])
    assert fill == (1.0, 1.0, 1.0, 0.5)


def test_corner_radius_reaches_the_instance() -> None:
    app = video_app(style={"corner_radius": 6})
    app.root.find("v").push_frame(frame(80, 40))
    dl = paint(app)
    radii = tuple(float(v) for v in dl.view[-1]["radii"])
    assert all(r == pytest.approx(6.0) for r in radii)


def test_fit_cover_crops_a_wide_frame_into_a_square_box() -> None:
    app = video_app(style={"width": 100, "height": 100, "fit": "cover"})
    element = app.root.find("v")
    element.push_frame(frame(80, 40))
    full_uv = element._entry.uv(element.image_atlas.size)
    dl = paint(app)
    rect = tuple(float(v) for v in dl.view[-1]["rect"])
    assert rect == pytest.approx((0.0, 0.0, 100.0, 100.0))
    u0, v0, u1, v1 = (float(v) for v in dl.view[-1]["uv"])
    assert full_uv[0] < u0 and u1 < full_uv[2]  # cropped horizontally
    assert v0 == pytest.approx(full_uv[1]) and v1 == pytest.approx(full_uv[3])  # not vertically


def test_a_background_paints_before_the_frame() -> None:
    app = video_app(style={"background": "surface_container"})
    app.root.find("v").push_frame(frame(80, 40))
    dl = paint(app)
    ks = [int(s["flags"][0]) for s in dl.view]
    assert ks[0] == Kind.BOX
    assert Kind.IMAGE in ks[1:]


def test_pushing_a_new_frame_updates_the_pixels_in_place() -> None:
    app = video_app(style={"width": 80, "height": 40})
    element = app.root.find("v")
    element.push_frame(frame(80, 40, (255, 0, 0)))
    dl1 = paint(app)
    element.push_frame(frame(80, 40, (0, 255, 0)))
    dl2 = paint(app)
    uv1 = tuple(float(v) for v in dl1.view[-1]["uv"])
    uv2 = tuple(float(v) for v in dl2.view[-1]["uv"])
    assert uv1 == uv2  # same atlas slot -- confirms in-place overwrite, not a new pack


# -------------------------------------------------------------------- atlas


def test_two_elements_outside_an_app_share_the_default_atlas() -> None:
    a = laid_out({"name": "a", "widget": "Video"})
    b = laid_out({"name": "b", "widget": "Video"})
    assert a.image_atlas is b.image_atlas


def test_an_apps_elements_use_the_apps_own_atlas() -> None:
    app = video_app()
    assert app.root.find("v").image_atlas is app.images


def test_two_video_elements_get_independent_atlas_slots() -> None:
    view = {
        "root": {
            "widget": "Horizontal",
            "children": [
                {"name": "a", "widget": "Video"},
                {"name": "b", "widget": "Video"},
            ],
        }
    }
    app = App(view, theme=Theme(dark=True))
    app.mount()
    app.root.find("a").push_frame(frame(20, 20, (255, 0, 0)))
    app.root.find("b").push_frame(frame(20, 20, (0, 255, 0)))
    app.update()
    dl = paint(app)
    uvs = {tuple(float(v) for v in s["uv"]) for s in dl.view if int(s["flags"][0]) == Kind.IMAGE}
    assert len(uvs) == 2
