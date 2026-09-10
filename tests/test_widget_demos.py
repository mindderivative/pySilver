"""Every demo under `examples/widgets/` mounts headlessly, and its two code
panels show exactly what is on disk.

No GPU window needed -- every other widget test in this suite already
proves `App(...).mount()`/`.update()` work with no live surface, and that
is all a demo actually needs to be checked automatically. Real visual
verification of a native GLFW window is out of reach for this suite (no
attached display) -- see the demo-apps plan for that limitation stated in
full; this file is the automated backstop it describes, not a replacement
for someone actually looking at the window.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from pysilver import App, Theme

EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "widgets"
DEMO_DIRS = (
    sorted(p for p in EXAMPLES_DIR.iterdir() if p.is_dir() and (p / "app.py").exists())
    if EXAMPLES_DIR.exists()
    else []
)


def _load_viewmodel_class(vm_path: Path) -> type:
    spec = importlib.util.spec_from_file_location(vm_path.stem, vm_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `bind_view_model`'s own naming check reads `inspect.getfile(type(model))`,
    # which needs the module registered in `sys.modules` with a real
    # `__file__` -- otherwise it looks "built-in" to `inspect`, not merely
    # dynamically loaded.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    candidates = [v for k, v in vars(module).items() if k.endswith("Demo") and isinstance(v, type)]
    assert len(candidates) == 1, f"{vm_path}: expected exactly one *Demo class, found {candidates}"
    return candidates[0]


def _mount(demo_dir: Path) -> App:
    view_files = list(demo_dir.glob("*_View.yaml"))
    vm_files = list(demo_dir.glob("*_ViewModel.py"))
    assert len(view_files) == 1, f"{demo_dir}: expected exactly one *_View.yaml"
    assert len(vm_files) == 1, f"{demo_dir}: expected exactly one *_ViewModel.py"
    app_files = list(demo_dir.glob("app.py"))
    assert len(app_files) == 1, f"{demo_dir}: expected an app.py entry point"
    view_path, vm_path = view_files[0], vm_files[0]

    demo_cls = _load_viewmodel_class(vm_path)
    app = App(view_path, theme=Theme(dark=True))
    app.bind_view_model(view_path.name, demo_cls())
    app.mount()
    app.update()
    return app


@pytest.mark.parametrize("demo_dir", DEMO_DIRS, ids=lambda p: p.name)
def test_widget_demo_mounts_headlessly(demo_dir: Path) -> None:
    _mount(demo_dir)


@pytest.mark.parametrize("demo_dir", DEMO_DIRS, ids=lambda p: p.name)
def test_widget_demo_code_panels_match_disk(demo_dir: Path) -> None:
    app = _mount(demo_dir)
    view_path = next(demo_dir.glob("*_View.yaml"))
    vm_path = next(demo_dir.glob("*_ViewModel.py"))

    yaml_panel = app.root.find("yaml_source")
    python_panel = app.root.find("python_source")
    assert yaml_panel is not None, f"{demo_dir}: no 'yaml_source' CodeEditor found"
    assert python_panel is not None, f"{demo_dir}: no 'python_source' CodeEditor found"
    assert yaml_panel._value == view_path.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert python_panel._value == vm_path.read_text(encoding="utf-8")  # type: ignore[attr-defined]


def test_at_least_one_demo_exists() -> None:
    """Guards against the glob silently matching nothing -- an empty
    parametrize list would make every test above vacuously pass."""
    assert DEMO_DIRS, f"no demo directories found under {EXAMPLES_DIR}"
