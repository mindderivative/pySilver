"""End-to-end: MD3 token -> palette -> GPU clear -> pixel readback.

This is the M0 acceptance test and the integration-level guard for the colour
space boundary (ARCHITECTURE.md 5.6.1). test_palette.py checks the maths; this
checks that the maths survives a real render pass on a real ``*-srgb`` surface.
"""

from __future__ import annotations

import numpy as np
import pytest
from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot

from pysilver import Theme

pytestmark = pytest.mark.gpu


def md3_srgb(token: str, theme: Theme) -> np.ndarray:
    scheme = SchemeTonalSpot(theme.hct(), theme.dark, theme.contrast)
    attr = getattr(MaterialDynamicColors, token)
    return np.array(attr.get_rgba(scheme)[:3], dtype=np.float64)


def test_frame_has_expected_shape(render_once) -> None:
    frame = render_once(width=64, height=64)
    assert frame.shape == (64, 64, 4)
    assert frame.dtype == np.uint8


def test_clear_matches_md3_surface_token(render_once) -> None:
    """The rendered pixel must equal the MD3 surface token, not a washed-out one."""
    theme = Theme(seed="#6750A4", dark=True)
    frame = render_once(theme=theme)

    actual = frame[32, 32, :3].astype(np.float64)
    expected = md3_srgb("surface", theme)

    assert actual == pytest.approx(expected, abs=2.0), (
        f"expected ~{expected} got {actual}; a large positive delta means the "
        f"palette was uploaded sRGB-encoded and double-encoded by the surface"
    )


def test_clear_is_uniform(render_once) -> None:
    frame = render_once()
    assert np.all(frame[:, :, :3] == frame[0, 0, :3])


def test_light_theme_is_brighter(render_once) -> None:
    dark = render_once(theme=Theme(dark=True))[32, 32, :3].astype(int).sum()
    light = render_once(theme=Theme(dark=False))[32, 32, :3].astype(int).sum()
    assert light > dark


def test_frame_counter_advances(offscreen_engine) -> None:
    engine = offscreen_engine()
    engine.canvas.request_draw(engine.draw_frame)
    assert engine.frame_count == 0
    engine.canvas.draw()
    assert engine.frame_count == 1


def test_closing_releases_gpu_objects_in_order(offscreen_engine) -> None:
    """Closing the window used to segfault the process.

    rendercanvas terminates GLFW from a class attribute's `__del__` precisely
    so it happens late, because "the release of the surface should happen
    before the termination of glfw" -- otherwise the process segfaults on exit
    (pygfx/pygfx#642). An `Engine` reached from a module-level `App`, which is
    how every example here is written, stays alive until interpreter shutdown
    and loses that race: closing the window destroyed the native window and
    left a live wgpu surface pointing at it.

    `Engine.close` releases the surface first, then what the device owns, then
    the device, and `run()` calls it in a `finally`. The segfault itself needs
    a real windowed surface to reproduce; what is checkable here is that the
    ordering runs cleanly and that calling it twice -- `run()`'s `finally` plus
    an application closing explicitly -- is harmless.
    """
    engine = offscreen_engine()
    engine.canvas.request_draw(engine.draw_frame)
    engine.canvas.draw()
    engine.close()
    engine.close()
    assert getattr(engine, "context", None) is None
    assert getattr(engine, "device", None) is None


def test_wayland_decorations_defaults_to_the_portable_choice() -> None:
    """`server` is opt-in on purpose. GNOME offers no server-side decorations
    for xdg-shell, so defaulting to it would leave those users with a window
    that has no title bar and no way to close it."""
    from pysilver import Settings

    assert Settings().wayland_decorations == "auto"
    assert Settings(wayland_decorations="server").wayland_decorations == "server"
    with pytest.raises(ValueError):
        Settings(wayland_decorations="client")


def test_vsync_defaults_off_and_is_settable() -> None:
    """Off by default, which is not the conventional choice.

    Measured on KDE Plasma Wayland: a fast drag with vsync on stalled for up
    to 7.9 seconds, and the same drag with it off ran at 466 redraws a second
    with no stall. A window that lurches for seconds is a worse defect than
    tearing, and the usual argument for vsync does not apply -- an idle
    application here renders no frames at all, so there is no loop to burn
    the GPU.
    """
    from pysilver import Settings

    assert Settings().vsync is False
    assert Settings(vsync=True).vsync is True
