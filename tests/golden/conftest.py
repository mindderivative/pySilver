"""Offscreen rendering fixtures and the golden-image comparison harness.

The only tests that need a GPU adapter.

Baselines are committed. Regenerate with::

    PYSILVER_REGEN_GOLDEN=1 .venv/bin/python -m pytest tests/golden -m gpu

A regeneration run FAILS on purpose when it writes anything, so a baseline can
never be silently rewritten to match a regression -- the diff has to be looked
at and committed deliberately.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

BASELINES = Path(__file__).parent / "baselines"
FAILURES = Path(__file__).parent / "failures"

#: Per-channel tolerance. Rasterisation differs by a hair between drivers, so
#: an exact match would be unmaintainable; anything larger than this is a real
#: visual change.
TOLERANCE = 4

#: Fraction of pixels allowed to exceed TOLERANCE before a test fails.
MAX_DIFFERING = 0.002


@pytest.fixture(scope="session")
def gpu_available() -> bool:
    try:
        import wgpu

        wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    except Exception:
        return False
    return True


@pytest.fixture
def offscreen_engine(gpu_available: bool):
    """An Engine rendering to an offscreen canvas -- no window, deterministic."""
    if not gpu_available:
        pytest.skip("no wgpu adapter available")

    from rendercanvas.offscreen import RenderCanvas

    from pysilver import Engine, Settings

    def _make(width: int = 64, height: int = 64, **kw):
        canvas = RenderCanvas(size=(width, height))
        return Engine(canvas=canvas, settings=Settings(width=width, height=height), **kw)

    return _make


@pytest.fixture
def render_scene(offscreen_engine):
    """Render a painter callable and return the frame as (h, w, 4) uint8.

    Yields (frame, engine) so tests can also assert on the draw-call count.
    """

    def _render(painter, width: int = 128, height: int = 128, **kw):
        engine = offscreen_engine(width=width, height=height, **kw)
        engine.painter = painter
        engine.canvas.request_draw(engine.draw_frame)
        return np.asarray(engine.canvas.draw()), engine

    return _render


@pytest.fixture
def render_once(offscreen_engine):
    """Render a single frame and return it as an (h, w, 4) uint8 array."""

    def _render(**kw) -> np.ndarray:
        engine = offscreen_engine(**kw)
        engine.canvas.request_draw(engine.draw_frame)
        return np.asarray(engine.canvas.draw())

    return _render


@pytest.fixture(scope="session")
def regenerating() -> bool:
    return os.environ.get("PYSILVER_REGEN_GOLDEN") == "1"


@pytest.fixture(scope="session")
def assert_golden(regenerating: bool):
    """Compare a rendered frame against a committed baseline PNG."""
    from PIL import Image

    # Session-scoped so `used` survives across test functions: the collision
    # this guards against (two DIFFERENT tests sharing a baseline name) can
    # only be caught here if the set persists for the whole run, not just one
    # test's fixture instance.
    used: set[str] = set()

    def _check(name: str, frame: np.ndarray) -> None:
        # Two tests sharing a baseline name overwrite each other's image, so
        # neither tests what it claims. Cheap to catch, and it already happened.
        if name in used:
            pytest.fail(f"golden name {name!r} is used by more than one test")
        used.add(name)
        BASELINES.mkdir(parents=True, exist_ok=True)
        baseline_path = BASELINES / f"{name}.png"
        actual = np.asarray(frame)[:, :, :3].astype(np.int16)

        if regenerating or not baseline_path.exists():
            Image.fromarray(np.asarray(frame), "RGBA").save(baseline_path)
            pytest.fail(
                f"wrote baseline {baseline_path.name} -- inspect the image and "
                f"commit it deliberately, then re-run without PYSILVER_REGEN_GOLDEN"
            )

        expected = np.asarray(Image.open(baseline_path).convert("RGBA"))[:, :, :3]
        expected = expected.astype(np.int16)
        if expected.shape != actual.shape:
            pytest.fail(f"{name}: size changed {expected.shape} -> {actual.shape}")

        delta = np.abs(actual - expected).max(axis=2)
        differing = int((delta > TOLERANCE).sum())
        fraction = differing / delta.size

        if fraction > MAX_DIFFERING:
            FAILURES.mkdir(parents=True, exist_ok=True)
            Image.fromarray(np.asarray(frame), "RGBA").save(FAILURES / f"{name}.actual.png")
            heat = np.zeros((*delta.shape, 3), dtype=np.uint8)
            heat[..., 0] = np.clip(delta * 8, 0, 255).astype(np.uint8)
            Image.fromarray(heat, "RGB").save(FAILURES / f"{name}.diff.png")
            pytest.fail(
                f"{name}: {differing} px ({fraction:.2%}) differ by more than "
                f"{TOLERANCE}/255, max delta {int(delta.max())}. "
                f"Artifacts written to tests/golden/failures/"
            )

    return _check
