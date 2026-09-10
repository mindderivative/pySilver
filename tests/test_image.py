"""Image: a decoded raster image, and the `fit` math that positions it.

No M3 grounding exists for this either -- checked directly against
`M3-References`, the same way every other ungrounded widget this session was.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image as PILImage

from pysilver import App, Signal, Theme
from pysilver.layout import Constraints, Size
from pysilver.paint import NO_TOKEN, DisplayList, Kind
from pysilver.spec import parse_view
from pysilver.widgets import build_element
from pysilver.widgets.image import ImageElement, _fit_image

LOOSE = Constraints.loose(Size(1000.0, 800.0))


def make_png(path, width: int, height: int, rgb=(200, 50, 50)) -> None:
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = rgb
    arr[..., 3] = 255
    PILImage.fromarray(arr, "RGBA").save(path)


def laid_out(spec: dict, constraints: Constraints = LOOSE):
    element = build_element(parse_view(spec).root)
    element.layout(constraints)
    return element


def image_app(path: str, *, style: dict | None = None) -> App:
    view = {
        "root": {
            "widget": "Vertical",
            "children": [{"name": "img", "widget": "Image", "path": path, "style": style or {}}],
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
    assert laid_out({"name": "w", "widget": "Image"}) is not None


def test_image_is_an_image_element() -> None:
    assert isinstance(laid_out({"name": "w", "widget": "Image"}), ImageElement)


# ---------------------------------------------------------------- _fit_image


def test_fill_stretches_to_the_box_ignoring_aspect() -> None:
    x, y, w, h, uv = _fit_image(Size(100, 100), Size(80, 40), "fill", (0, 0, 1, 1))
    assert (x, y, w, h) == (0.0, 0.0, 100.0, 100.0)
    assert uv == (0, 0, 1, 1)


def test_contain_letterboxes_preserving_aspect() -> None:
    x, y, w, h, uv = _fit_image(Size(100, 100), Size(80, 40), "contain", (0, 0, 1, 1))
    assert (w, h) == pytest.approx((100.0, 50.0))
    assert y == pytest.approx(25.0)
    assert x == pytest.approx(0.0)
    assert uv == (0, 0, 1, 1)  # contain never crops the source


def test_cover_fills_the_box_and_crops_the_source() -> None:
    x, y, w, h, uv = _fit_image(Size(100, 100), Size(80, 40), "cover", (0, 0, 1, 1))
    assert (x, y, w, h) == (0.0, 0.0, 100.0, 100.0)  # cover never letterboxes the box
    u0, v0, u1, v1 = uv
    assert v0 == 0.0 and v1 == 1.0  # height was the limiting axis -- no vertical crop
    assert u0 > 0.0 and u1 < 1.0  # width crops symmetrically
    assert u0 == pytest.approx(1.0 - u1)


def test_none_centres_at_natural_size_regardless_of_the_box() -> None:
    x, y, w, h, uv = _fit_image(Size(100, 100), Size(80, 40), "none", (0, 0, 1, 1))
    assert (w, h) == (80.0, 40.0)
    assert (x, y) == pytest.approx((10.0, 30.0))
    assert uv == (0, 0, 1, 1)


def test_a_zero_natural_size_falls_back_to_the_box_rather_than_dividing_by_zero() -> None:
    x, y, w, h, _ = _fit_image(Size(100, 50), Size(0, 0), "contain", (0, 0, 1, 1))
    assert (x, y, w, h) == (0.0, 0.0, 100.0, 50.0)


# ------------------------------------------------------------------- sizing


def test_with_no_style_it_reports_its_own_natural_size(tmp_path) -> None:
    png = tmp_path / "logo.png"
    make_png(png, 80, 40)
    element = laid_out({"name": "w", "widget": "Image", "path": str(png)})
    assert element.size == Size(80.0, 40.0)


def test_an_explicit_size_overrides_the_natural_one(tmp_path) -> None:
    png = tmp_path / "logo.png"
    make_png(png, 80, 40)
    element = laid_out(
        {"name": "w", "widget": "Image", "path": str(png), "style": {"width": 10, "height": 10}}
    )
    assert element.size == Size(10.0, 10.0)


def test_with_no_path_it_is_honestly_empty() -> None:
    element = laid_out({"name": "w", "widget": "Image"})
    assert element.size == Size(0.0, 0.0)


def test_a_missing_file_is_also_honestly_empty(tmp_path, capsys) -> None:
    element = laid_out({"name": "w", "widget": "Image", "path": str(tmp_path / "nope.png")})
    assert element.size == Size(0.0, 0.0)
    assert "nope.png" in capsys.readouterr().err


def test_a_broken_path_does_not_retry_every_layout(tmp_path, monkeypatch) -> None:
    calls = []
    import pysilver.widgets.image as image_module

    def fake_decode(path):
        calls.append(path)
        raise OSError("boom")

    monkeypatch.setattr(image_module, "_decode", fake_decode)
    element = laid_out({"name": "w", "widget": "Image", "path": str(tmp_path / "bad.png")})
    element.layout(LOOSE)
    element.layout(LOOSE)
    assert len(calls) == 1


# -------------------------------------------------------------------- paint


def test_paints_a_kind_image_instance(tmp_path) -> None:
    png = tmp_path / "logo.png"
    make_png(png, 80, 40)
    app = image_app(str(png))
    dl = paint(app)
    assert Kind.IMAGE in [int(s["flags"][0]) for s in dl.view]


def test_no_path_paints_nothing() -> None:
    app = image_app("")
    dl = paint(app)
    assert len(dl) == 0


def test_opacity_becomes_the_tints_alpha(tmp_path) -> None:
    png = tmp_path / "logo.png"
    make_png(png, 80, 40)
    app = image_app(str(png), style={"opacity": 0.5})
    dl = paint(app)
    last = dl.view[-1]
    assert int(last["flags"][2]) == NO_TOKEN  # no palette-token slot for Kind.IMAGE
    fill = tuple(float(v) for v in last["fill"])
    assert fill == (1.0, 1.0, 1.0, 0.5)


def test_corner_radius_reaches_the_image_instance(tmp_path) -> None:
    png = tmp_path / "logo.png"
    make_png(png, 80, 40)
    app = image_app(str(png), style={"corner_radius": 6})
    dl = paint(app)
    radii = tuple(float(v) for v in dl.view[-1]["radii"])
    assert all(r == pytest.approx(6.0) for r in radii)


def test_a_background_paints_before_the_image(tmp_path) -> None:
    png = tmp_path / "logo.png"
    make_png(png, 80, 40)
    app = image_app(str(png), style={"background": "surface_container"})
    dl = paint(app)
    ks = [int(s["flags"][0]) for s in dl.view]
    assert ks[0] == Kind.BOX
    assert Kind.IMAGE in ks[1:]


# -------------------------------------------------------------------- atlas


def test_two_elements_outside_an_app_share_the_default_atlas() -> None:
    a = laid_out({"name": "a", "widget": "Image"})
    b = laid_out({"name": "b", "widget": "Image"})
    assert a.image_atlas is b.image_atlas


def test_an_apps_elements_use_the_apps_own_atlas(tmp_path) -> None:
    png = tmp_path / "logo.png"
    make_png(png, 80, 40)
    app = image_app(str(png))
    assert app.root.find("img").image_atlas is app.images


# --------------------------------------------------------------- reactivity


def test_path_is_bindable_to_a_signal(tmp_path) -> None:
    small = tmp_path / "small.png"
    big = tmp_path / "big.png"
    make_png(small, 20, 10)
    make_png(big, 80, 40)
    view = {
        "root": {
            "widget": "Vertical",
            "children": [{"name": "img", "widget": "Image", "path": "{{ p.get() }}"}],
        }
    }
    app = App(view, theme=Theme(dark=True))
    p = Signal(str(small))
    app.expose(p=p)
    app.mount()
    app.update()
    assert app.root.find("img").size == Size(20.0, 10.0)
    p.set(str(big))
    app.update()
    assert app.root.find("img").size == Size(80.0, 40.0)
