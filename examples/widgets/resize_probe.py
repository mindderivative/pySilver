"""Resize instrumentation harness for a single widget demo.

Generic version of `examples/gallery/resize_probe.py`, pointed at any
`examples/widgets/<slug>/` directory instead of the gallery. Runs the REAL,
unmodified demo (its own `app.py`, View, and ViewModel) and instruments
`Engine` with the same per-stage timing ARCHITECTURE.md 5.8.1 used to
diagnose the original pointer-trailing bug: pin (swapchain reconfigure
check), paint (build + layout + paint), upload, acquire
(`get_current_texture`), submit. Nothing in `Engine` or the demo is changed
-- every hook wraps the existing method and calls straight through to it, so
this measures the exact code path a normal `python app.py` run uses.

**Also logs the raw OS cursor position, window-relative, from `glfw`
directly** (`glfw.get_cursor_pos`) alongside the window size Engine sees on
every frame -- the direct way to answer "does the window trail the cursor",
without the frame-duplication confound a screen recording has.

Usage::

    python examples/widgets/resize_probe.py <slug>
    python examples/widgets/resize_probe.py terminal

A one-line summary prints to stdout roughly once a second while the app
runs, including frame rate, per-frame mean/max time, and the current
cursor-vs-window-edge gap. Drag-resize the window for several seconds (try
both a slow drag and a fast one, and drag from a corner so both axes are
covered), then close it normally. The full per-frame log is written to
`examples/widgets/<slug>/resize_probe_log.csv` -- send that file back along
with whatever printed to the terminal.
"""

from __future__ import annotations

import atexit
import csv
import importlib.util
import sys
import time
from pathlib import Path

import glfw

if len(sys.argv) != 2:
    print(f"usage: python {Path(__file__).name} <widget-slug>", file=sys.stderr)
    print("example: python examples/widgets/resize_probe.py terminal", file=sys.stderr)
    raise SystemExit(2)

DEMO_DIR = Path(__file__).parent / sys.argv[1]
if not DEMO_DIR.is_dir():
    print(f"no such demo directory: {DEMO_DIR}", file=sys.stderr)
    raise SystemExit(2)

LOG_PATH = DEMO_DIR / "resize_probe_log.csv"

sys.path.insert(0, str(DEMO_DIR))

from pysilver.app import App  # noqa: E402
from pysilver.layout import OFFSET_ZERO, Constraints  # noqa: E402
from pysilver.runtime.engine import Engine  # noqa: E402
from pysilver.tree.element import PaintContext  # noqa: E402

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

# --- break down App.update()/App.paint() themselves: paint_ms above wraps
# the WHOLE of App.paint(), which was found to cost ~10ms/frame live while
# an identical headless call to the same method cost <1ms -- so whatever is
# expensive must be something that is a no-op or trivial when `self.engine`
# is None (as it is headless) but does real work once a real engine/canvas
# is attached. This isolates which specific sub-step that is. ---
_app_stage_ms: dict[str, float] = {}
_app_stage_totals: dict[str, float] = {}
_app_stage_count = 0


def _timed(label: str, fn, *a, **kw):
    t0 = time.perf_counter()
    result = fn(*a, **kw)
    _app_stage_ms[label] = (time.perf_counter() - t0) * 1000.0
    return result


def _update(self) -> None:
    _timed("poll_reload", self.poll_reload)
    _timed("dispatch_drain", self.dispatcher.drain)
    _timed("motion_tick", self.motion.tick, self._frame_delta())
    _timed("layout_flush", self.layout_owner.flush)
    _timed("drain_a11y", self._drain_accessibility)
    size = _timed("logical_size", self.logical_size)
    _timed("root_layout", self.root.layout, Constraints.tight(size))
    _timed("overlays_layout", self.overlays.layout, size, self.root)
    _timed("sync_cursor", self._sync_cursor)


def _paint(self, display_list) -> None:
    global _app_stage_count
    _app_stage_ms.clear()
    _timed("update", _update, self)
    ctx = PaintContext(
        display_list=display_list,
        palette=self.palette,
        text=self.text,
        images=self.images,
        pixel_ratio=self.engine.pixel_ratio if self.engine else 1.0,
    )
    _timed("root_paint", self.root.paint, ctx, OFFSET_ZERO)
    _timed("overlays_paint", self.overlays.paint, ctx, self.palette, self.logical_size())
    if self._a11y is not None:
        _timed("a11y_update", lambda: self._a11y.update(self.accessibility_tree()))
    if self.motion.active and self.engine is not None:
        self.engine.request_draw()
    _app_stage_count += 1
    for k, v in _app_stage_ms.items():
        _app_stage_totals[k] = _app_stage_totals.get(k, 0.0) + v
    if _app_stage_count % 60 == 0:
        ranked = sorted(_app_stage_totals.items(), key=lambda kv: -kv[1])
        breakdown = " | ".join(f"{k}={v / _app_stage_count:.3f}ms" for k, v in ranked)
        print(f"[App stages, {_app_stage_count} frames avg] {breakdown}", flush=True)


App.paint = _paint


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

_app_spec = importlib.util.spec_from_file_location("_probed_app", DEMO_DIR / "app.py")
assert _app_spec is not None and _app_spec.loader is not None
_demo = importlib.util.module_from_spec(_app_spec)
sys.modules[_app_spec.name] = _demo
_app_spec.loader.exec_module(_demo)  # the real, unmodified demo app.py

if __name__ == "__main__":
    print(f"Resize probe active for '{sys.argv[1]}' -- drag-resize the window (try slow and fast),")
    print(f"then close it normally. Log will be written to {LOG_PATH}.")
    _demo.app.run()
