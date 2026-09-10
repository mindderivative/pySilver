"""Resize instrumentation harness for the pySilver gallery.

Runs the REAL, unmodified gallery (`import app as demo` — same View,
ViewModel, and Settings the app ships with) and instruments `Engine` with
per-stage timing, the same breakdown ARCHITECTURE.md 5.8.1 used to diagnose
and fix the original pointer-trailing bug: pin (swapchain reconfigure
check), paint (build + layout + paint), upload, acquire
(`get_current_texture`), submit. Nothing in `Engine` or the gallery is
changed — every hook wraps the existing method and calls straight through to
it, so this measures the exact code path a normal `python app.py` run uses.

**Also logs the raw OS cursor position, window-relative, from `glfw`
directly** (`glfw.get_cursor_pos`) alongside the window size Engine sees on
every frame. This is the direct way to answer "does the window trail the
cursor": during an edge/corner drag, the dragged edge's cursor coordinate
and the window's current size on that axis should stay coincident if there
is no lag. A screen recording cannot settle this on its own -- capture
tools commonly duplicate frames to hit their target frame rate, which looks
identical to a real render lag but isn't one. Reading both numbers from
inside the same process at the moment each frame is drawn has no such
confound.

Usage::

    python examples/gallery/resize_probe.py

A one-line summary prints to stdout roughly once a second while the app
runs, including the current cursor-vs-window-edge gap. Drag-resize the
window for several seconds (try both a slow drag and a fast one, and drag
from a corner so both axes are covered), then close it normally. The full
per-frame log is written to `examples/gallery/resize_probe_log.csv` next to
this file — send that file back along with whatever printed to the
terminal.
"""

from __future__ import annotations

import atexit
import csv
import sys
import time
from pathlib import Path

import glfw

sys.path.insert(0, str(Path(__file__).parent))

from pysilver.runtime.engine import Engine

LOG_PATH = Path(__file__).parent / "resize_probe_log.csv"

_rows: list[dict[str, float | int]] = []
_report_window: list[float] = []
_last_report = time.perf_counter()

# --- wrap the three named sub-stages Engine already calls as methods ---
_orig_pin_surface = Engine._pin_surface
_orig_upload = Engine._upload
_orig_draw_ui = Engine._draw_ui
_orig_draw_frame = Engine.draw_frame

_stage_ms: dict[str, float] = {}


def _timed_pin_surface(self: Engine) -> None:
    t0 = time.perf_counter()
    _orig_pin_surface(self)
    _stage_ms["pin_ms"] = (time.perf_counter() - t0) * 1000.0


def _timed_upload(self: Engine) -> None:
    t0 = time.perf_counter()
    _orig_upload(self)
    _stage_ms["upload_ms"] = (time.perf_counter() - t0) * 1000.0


def _timed_draw_ui(self: Engine, render_pass) -> None:
    t0 = time.perf_counter()
    _orig_draw_ui(self, render_pass)
    _stage_ms["draw_ui_ms"] = (time.perf_counter() - t0) * 1000.0


Engine._pin_surface = _timed_pin_surface
Engine._upload = _timed_upload
Engine._draw_ui = _timed_draw_ui


def _draw_frame(self: Engine) -> None:
    """Reimplements nothing -- wraps `painter`, `get_current_texture`, and
    `queue.submit` for this one frame only, then calls the real, unmodified
    `draw_frame`, which calls back into the wrapped pieces above."""
    _stage_ms.clear()

    size_before = tuple(self.canvas.get_physical_size())
    settle_before = self._settle
    last_before = self._last_size

    # `glfw.get_cursor_pos` is in the same window-relative LOGICAL coordinate
    # space as `get_logical_size` -- comparable directly, unlike
    # `get_physical_size` on a HiDPI display where the two would differ by
    # the pixel ratio for no reason related to resize lag at all.
    logical_size = tuple(self.canvas.get_logical_size())
    window = getattr(self.canvas, "_window", None)
    if window is not None:
        cursor_x, cursor_y = glfw.get_cursor_pos(window)
    else:
        cursor_x = cursor_y = float("nan")

    orig_painter = self.painter

    def timed_painter(dl):
        t0 = time.perf_counter()
        if orig_painter is not None:
            orig_painter(dl)
        _stage_ms["paint_ms"] = (time.perf_counter() - t0) * 1000.0

    self.painter = timed_painter

    orig_get_current_texture = self.context.get_current_texture

    def timed_get_current_texture(*a, **kw):
        t0 = time.perf_counter()
        result = orig_get_current_texture(*a, **kw)
        _stage_ms["acquire_ms"] = (time.perf_counter() - t0) * 1000.0
        return result

    self.context.get_current_texture = timed_get_current_texture

    orig_submit = self.device.queue.submit

    def timed_submit(*a, **kw):
        t0 = time.perf_counter()
        result = orig_submit(*a, **kw)
        _stage_ms["submit_ms"] = (time.perf_counter() - t0) * 1000.0
        return result

    self.device.queue.submit = timed_submit

    t_start = time.perf_counter()
    try:
        _orig_draw_frame(self)
    finally:
        self.painter = orig_painter
        self.context.get_current_texture = orig_get_current_texture
        self.device.queue.submit = orig_submit
    total_ms = (time.perf_counter() - t_start) * 1000.0

    gap_x = round(cursor_x - logical_size[0], 2)
    gap_y = round(cursor_y - logical_size[1], 2)
    row = {
        "t": t_start,
        "w": size_before[0],
        "h": size_before[1],
        "logical_w": round(logical_size[0], 2),
        "logical_h": round(logical_size[1], 2),
        "cursor_x": round(cursor_x, 2),
        "cursor_y": round(cursor_y, 2),
        "gap_x": gap_x,
        "gap_y": gap_y,
        "settle_before": settle_before,
        "settle_after": self._settle,
        "resized_this_frame": int(size_before != last_before),
        "pin_ms": round(_stage_ms.get("pin_ms", float("nan")), 4),
        "paint_ms": round(_stage_ms.get("paint_ms", float("nan")), 4),
        "upload_ms": round(_stage_ms.get("upload_ms", float("nan")), 4),
        "acquire_ms": round(_stage_ms.get("acquire_ms", float("nan")), 4),
        "draw_ui_ms": round(_stage_ms.get("draw_ui_ms", float("nan")), 4),
        "submit_ms": round(_stage_ms.get("submit_ms", float("nan")), 4),
        "total_ms": round(total_ms, 4),
        "instances": self._instance_count,
    }
    _rows.append(row)

    global _last_report
    _report_window.append(total_ms)
    now = time.perf_counter()
    if now - _last_report >= 1.0:
        n = len(_report_window)
        mean_ms = sum(_report_window) / n if n else 0.0
        max_ms = max(_report_window) if n else 0.0
        print(
            f"[{time.strftime('%H:%M:%S')}] {n} frames/s | "
            f"mean {mean_ms:.2f}ms max {max_ms:.2f}ms | "
            f"size {logical_size[0]:.0f}x{logical_size[1]:.0f} | "
            f"cursor ({cursor_x:.0f},{cursor_y:.0f}) | "
            f"gap ({gap_x:+.0f},{gap_y:+.0f}) | "
            f"settle {self._settle}",
            flush=True,
        )
        _report_window.clear()
        _last_report = now


Engine.draw_frame = _draw_frame


def _flush() -> None:
    if not _rows:
        print("No frames recorded.")
        return
    with LOG_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(_rows[0].keys()))
        writer.writeheader()
        writer.writerows(_rows)
    print(f"\nWrote {len(_rows)} frame records to {LOG_PATH}")


atexit.register(_flush)

import app as demo  # noqa: E402  (the real, unmodified gallery)

if __name__ == "__main__":
    print("Resize probe active -- drag-resize the gallery window (try slow and fast),")
    print(f"then close it normally. Log will be written to {LOG_PATH}.")
    demo.app.run()
