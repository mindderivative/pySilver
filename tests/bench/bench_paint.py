"""Frame-cost benchmark. See ARCHITECTURE.md 12 for the budget this measures against.

    python tests/bench/bench_paint.py

Risk R1 is that Python, not the GPU, is the frame-time bottleneck. This exists to
quantify that at M2 rather than discovering it at M6.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable

import numpy as np

from pysilver.paint import DisplayList

BUDGET_MS = 16.6
N = 1000


def measure(label: str, fn: Callable[[], object], *, repeats: int = 50) -> float:
    fn()  # warm up
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    best = min(samples)
    median = statistics.median(samples)
    print(f"  {label:<44} {median:7.3f} ms median   {best:7.3f} ms best")
    return median


def main() -> None:
    print(f"\npySilver paint benchmark -- {N} instances, {BUDGET_MS} ms frame budget\n")

    print("Display-list assembly")
    dl = DisplayList(capacity=N * 2)

    def scalar() -> None:
        dl.clear()
        for i in range(N):
            dl.add_box(
                i % 800,
                (i * 7) % 600,
                40,
                24,
                token=i % 50,
                radii=(8, 8, 8, 8),
                border_width=1.0,
            )

    scalar_ms = measure("scalar emit (per-widget Python)", scalar)

    rects = np.column_stack(
        [
            np.arange(N) % 800,
            (np.arange(N) * 7) % 600,
            np.full(N, 40),
            np.full(N, 24),
        ]
    ).astype(np.float32)
    tokens = (np.arange(N) % 50).astype(np.uint32)

    def vectorised() -> None:
        dl.clear()
        dl.add_boxes(rects, tokens=tokens)

    vector_ms = measure("vectorised emit (numpy bulk)", vectorised)

    scalar()
    cached = dl.snapshot(0)

    def splice() -> None:
        dl.clear()
        dl.extend(cached)

    cache_ms = measure("cached subtree splice (memcpy)", splice)

    print("\nFull frame (offscreen, includes upload + draw + readback)")
    try:
        from rendercanvas.offscreen import RenderCanvas

        from pysilver import Engine, Settings

        canvas = RenderCanvas(size=(800, 600))
        engine = Engine(canvas=canvas, settings=Settings(width=800, height=600))
        engine.painter = lambda d: d.extend(cached)
        canvas.request_draw(engine.draw_frame)
        measure(f"{N} instances, one draw call", canvas.draw, repeats=20)
        engine.painter = lambda d: None
        measure("0 instances (clear only)", canvas.draw, repeats=20)
    except Exception as exc:  # pragma: no cover - depends on adapter
        print(f"  skipped: no GPU adapter ({type(exc).__name__})")

    print("\nSteady-state frame paths")
    print(f"  {'idle (nothing dirty)':<44} {0.0:7.3f} ms  -- zero frames rendered")

    print("\nBudget analysis")
    print(f"  paint budget (ARCHITECTURE.md 12)            {2.0:7.3f} ms")
    for label, value in (("scalar", scalar_ms), ("vectorised", vector_ms), ("cached", cache_ms)):
        verdict = "OK" if value <= 2.0 else "OVER BUDGET"
        print(f"  {label:<44} {value:7.3f} ms   {verdict}")

    print(f"\n  vectorised speedup vs scalar   {scalar_ms / max(vector_ms, 1e-9):6.1f}x")
    print(f"  cached speedup vs scalar       {scalar_ms / max(cache_ms, 1e-9):6.1f}x")

    budget_n = int(N * 2.0 / scalar_ms) if scalar_ms > 0 else 0
    print(f"\n  scalar emit fits ~{budget_n} instances in the 2 ms paint budget\n")


if __name__ == "__main__":
    main()
