"""Text on the GPU: real glyphs through the atlas and the single draw call."""

from __future__ import annotations

import numpy as np
import pytest

from pysilver import Theme
from pysilver.paint import Kind

pytestmark = pytest.mark.gpu


def ink(frame: np.ndarray) -> int:
    """Pixels differing from the background."""
    bg = frame[0, 0, :3].astype(int)
    return int((np.abs(frame[:, :, :3].astype(int) - bg).sum(axis=2) > 20).sum())


def test_text_actually_renders(render_scene) -> None:
    def paint(dl):
        pass

    frame, engine = render_scene(paint, width=320, height=80)
    blank = ink(frame)

    def paint_text(dl):
        para = engine.text.layout("Hamburgefons", px=28)
        engine.text.emit(dl, para, x=10, y=20, token=engine.palette.index("on_surface"))

    engine.painter = paint_text
    engine.canvas.request_draw(engine.draw_frame)
    drawn = np.asarray(engine.canvas.draw())
    assert ink(drawn) > blank + 200, "no glyph coverage reached the framebuffer"


def test_glyphs_are_one_draw_call(render_scene) -> None:
    def paint(dl):
        pass

    _, engine = render_scene(paint, width=400, height=120)

    def paint_lots(dl):
        para = engine.text.layout(
            "The quick brown fox jumps over the lazy dog", px=14, max_width=360
        )
        engine.text.emit(dl, para, x=10, y=10, token=engine.palette.index("on_surface"))

    engine.painter = paint_lots
    engine.canvas.request_draw(engine.draw_frame)
    engine.canvas.draw()
    assert engine.instance_count > 30
    assert all(i["flags"][0] == Kind.GLYPH for i in engine.display_list.view)


def test_larger_text_covers_more_pixels(render_scene) -> None:
    _, engine = render_scene(lambda dl: None, width=320, height=120)

    def render_at(px: float) -> int:
        engine.text.clear_caches()
        engine.painter = lambda dl: engine.text.emit(
            dl,
            engine.text.layout("Wave", px=px),
            x=10,
            y=10,
            token=engine.palette.index("on_surface"),
        )
        engine.canvas.request_draw(engine.draw_frame)
        return ink(np.asarray(engine.canvas.draw()))

    assert render_at(32) > render_at(12)


def test_text_is_antialiased(render_scene) -> None:
    """Glyph coverage is 8-bit, so edges must produce intermediate values."""
    _, engine = render_scene(lambda dl: None, width=200, height=80)
    engine.painter = lambda dl: engine.text.emit(
        dl,
        engine.text.layout("O", px=48),
        x=20,
        y=10,
        token=engine.palette.index("on_surface"),
    )
    engine.canvas.request_draw(engine.draw_frame)
    frame = np.asarray(engine.canvas.draw())
    values = np.unique(frame[:, :, 0])
    assert len(values) > 4, f"only {len(values)} distinct levels: {values[:8]}"


def test_text_colour_comes_from_the_palette(render_scene) -> None:
    theme = Theme(seed="#6750A4", dark=True)
    _, engine = render_scene(lambda dl: None, width=200, height=80, theme=theme)
    engine.painter = lambda dl: engine.text.emit(
        dl,
        engine.text.layout("HHHH", px=40),
        x=10,
        y=10,
        token=engine.palette.index("primary"),
    )
    engine.canvas.request_draw(engine.draw_frame)
    frame = np.asarray(engine.canvas.draw())

    linear = np.array(engine.palette.linear("primary")[:3])
    expected = np.round(
        np.where(linear <= 0.0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - 0.055) * 255
    )
    pixels = frame[:, :, :3].reshape(-1, 3).astype(float)
    brightest = pixels[np.argmax(pixels.sum(axis=1))]
    assert brightest == pytest.approx(expected, abs=3.0)


def test_atlas_is_uploaded_before_the_draw(render_scene) -> None:
    """A glyph packed during paint must reach the GPU in the same frame."""
    _, engine = render_scene(lambda dl: None, width=200, height=80)
    engine.painter = lambda dl: engine.text.emit(
        dl,
        engine.text.layout("Fresh", px=24),
        x=10,
        y=10,
        token=engine.palette.index("on_surface"),
    )
    engine.canvas.request_draw(engine.draw_frame)
    frame = np.asarray(engine.canvas.draw())
    assert len(engine.text.atlas) > 0
    assert not engine.text.atlas.dirty, "atlas was not uploaded"
    assert ink(frame) > 50


def test_app_text_renders_through_the_element_tree(render_scene) -> None:
    from pysilver import App

    view = {
        "name": "root",
        "widget": "Vertical",
        "style": {"background": "surface", "padding": 12},
        "children": [
            {
                "name": "label",
                "widget": "Text",
                "text": "Rendered",
                "style": {"color": "on_surface", "font_size": 24},
            }
        ],
    }
    _, engine = render_scene(lambda dl: None, width=300, height=100)
    app = App(view, theme=Theme(dark=True))
    app.attach(engine)
    engine.canvas.request_draw(engine.draw_frame)
    frame = np.asarray(engine.canvas.draw())

    kinds = set(engine.display_list.view["flags"][:, 0].tolist())
    assert Kind.GLYPH in kinds, "widget text did not emit glyphs"
    assert ink(frame) > 100
