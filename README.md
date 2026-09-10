# pySilver

A GPU-accelerated declarative desktop GUI framework for Python.

Author your interface in YAML, write logic in Python, get a hardware-accelerated
Material Design 3 interface — rendered through WebGPU in **a single draw call**.

```yaml
# view.yaml
root:
  name: root
  widget: Vertical
  style: {background: surface, padding: 24, spacing: 16, width: expand}
  children:
    - name: label
      widget: Text
      text: "Clicked {{ clicks.get() }} times"
      style: {color: on_surface, font_size: 22}

    - name: go
      widget: Button
      text: "Click me"
      style: {width: 160, height: 40, variant: filled}
      handlers: {on_click: bump}
```

```python
# app.py
from pysilver import App, Signal, Theme

app = App("view.yaml", theme=Theme(seed="#6750A4", dark=True))

clicks = Signal(0)
app.expose(clicks=clicks)


@app.handler
def bump(event) -> None:
    clicks.update(lambda n: n + 1)


if __name__ == "__main__":
    app.run()
```

```bash
python app.py
```

Edit `view.yaml` while it runs and the window updates without losing the click
count, focus, or scroll position.

## Goals

Everything below this section describes pySilver's current implementation: a
`wgpu`-based, single-draw-call Python renderer. That renderer is a waypoint,
not the destination. The direction of travel is to replace it with the
**Tesserae Render Engine (TRE)** — a from-scratch, zero-allocation Rust
rendering core built as this project's dedicated GPU backend, with pySilver
as its first and primary consumer.

- **Rust core, Python framework.** TRE owns the render loop — 64-bit sort-key
  batching, atlas management with LRU eviction, MSDF typography, native
  static and animated SVG, and RHI submission over Vulkan, DirectX 12, and
  Metal — so pySilver's Python layer stays focused on the view tree, layout,
  reactivity, and widgets, rather than owning a GPU pipeline itself.
- **A first-party binding, not a generic plugin.** pySilver binds directly to
  TRE's native Rust types through [PyO3](https://pyo3.rs/), bypassing the
  stable C-ABI (`tre-ffi`) that every other language integrates through —
  no shadow-type marshalling, no opaque-handle round trip per call, and
  Rust's own `Drop` semantics integrating with CPython's reference counting
  natively.
- **A real performance floor, not a target.** TRE is designed around a
  zero-allocation render-loop steady state and frame delivery up to 240 Hz
  with single-digit draw calls per frame — headroom the current `wgpu`
  pipeline has no equivalent, mechanically-enforced guarantee for.
- **No change to the authoring surface.** The view format, `Signal`s,
  `ViewModel`s, and the widget catalogue are explicitly not part of this
  migration — an application's `view.yaml` and `app.py` should not need to
  change because the renderer underneath them did.

TRE lives in its own repository and is still pre-implementation: its Cargo
workspace is scaffolded and lint-clean, but no engine logic exists yet. This
section describes the destination pySilver's rendering layer is being
rebuilt toward, not something already shipping.

## Why

- **Native GPU, not OpenGL.** `wgpu` targets Vulkan, Metal, and DirectX 12 directly.
- **One draw call.** Every box, border, shadow, glyph, icon, and arc renders from
  a single instanced draw over a signed-distance-field shader — with analytic
  antialiasing and rounded clipping, and no MSAA.
- **Real text.** HarfBuzz shaping with kerning and ligatures, Unicode line
  breaking and grapheme segmentation, bidi, and font fallback. Not a bitmap-font
  approximation.
- **Material Design 3.** A full 59-token tonal palette from one seed colour,
  and 64 widgets — the great majority built to M3's own published specs, the
  rest pySilver's own for gaps M3 doesn't cover (layout primitives, `Canvas`,
  `Terminal`, and the like). Switching theme is a single buffer upload — no
  relayout, no display-list rebuild.
- **Fine-grained reactivity.** A signal write invalidates exactly the affected
  subtree with a typed reason — build, layout, or paint — not the frame.
- **Genuinely idle.** An app that is not doing anything renders zero frames.
- **Desktop-first.** Hover, focus rings, keyboard traversal, wheel scrolling and
  visible scrollbars are primary, not progressive enhancements.

## Install

Requires Python 3.12+. Every dependency ships prebuilt wheels — no toolchain
needed, and the fonts are bundled.

```bash
pip install pysilver
```

## Documentation

- **[View file reference](https://github.com/mindderivative/pySilver/blob/main/docs/view-reference.md)** — every widget, every style
  property, bindings, handlers, composition, and overlays.
- **[ARCHITECTURE.md](https://github.com/mindderivative/pySilver/blob/main/ARCHITECTURE.md)** — the design and the reasoning: the
  four-tree model, constraint layout, the single-draw-call pipeline, the text
  stack, and the measurements behind each decision.
- **[examples/](https://github.com/mindderivative/pySilver/tree/main/examples)** — `hello`, `counter`, and `gallery`, which exercises
  every widget and doubles as the golden-image corpus.

## Status

**pySilver is a phase name, not the framework's final identity.** It is the
first beta phase; later phases will carry their own names, and the stable
release will be named separately. That is why this is classified *Beta* despite
a 1.x version number — the version tracks the API contract, the classifier
tracks the phase.

**The public API is frozen.** `pysilver.__all__` is covered by semantic
versioning and pinned by a test; adding to it is a minor release, changing or
removing anything in it is a major one. (1.1 was that rule in action: motion
added four names and nothing else moved.)

**v1.7 — the widget-by-widget design review.** Every widget got its own
standalone demo window (`examples/widgets/<slug>/`, all 64), then a systematic
live pass over each one against its M3 source, finding and fixing real bugs
that had shipped invisibly: keyboard typing silently broken in every window
since the framework's first commit (`rendercanvas`'s "char" event uses `data`,
not `char`), eight overlay-trigger demos declaring their own overlay as a
plain child instead of under `overlays:`, `ListItem`'s leading icon never
actually laid out, and a dozen more, each fixed and golden-verified rather
than deferred. `NavigationRail` and `NavigationDrawer` — separate widgets
before this release — are now one, matching M3 Expressive's own current model
of a single rail with a collapsed (icon-only) and expanded (labelled) state
that animates between them; `WidgetKind.NAVIGATION_DRAWER` is gone, with no
deprecated alias. The review's own punch list became real features: `Tab`,
`Dialog`, and `MenuItem` gained icon anatomy (on the already-generic
`icon:`/`label:` fields, added by collapsing nine hand-wired bindable fields
into one `TEMPLATED_FIELDS` registry so a new one costs a schema line, not a
five-spot change); `ButtonGroup` gained M3's real shape-morph and toggle
selection; `Slider` gained its full XS–XL size ladder and pluggable handle
shapes (`square`/`hexagon`, plus an arbitrary `handle_image:`); `Snackbar`
gained its auto-dismiss timer; and `Dock` gained the runtime half it shipped
without — dragging a tab into another group or onto an edge to split a new
pane. None of it touched `__all__`; the version moves for the view format's
sake, the same rule v1.2 established.

**v1.6 — the desktop widget catalogue.** Sixteen widgets with no M3 catalogue
entry of their own, designed from pySilver's own precedent and grounded in the
nearest real M3 guidance where any existed: `Popover`, `Accordion`, `TreeView`/
`TreeItem`, submenu support for `Menu`/`MenuItem`, `Link`, `SpinBox`,
`Pagination`, `StatusBar`, `DockSplit`/`DockGroup`/`DockPanel`, `Canvas`,
`Image`, `Video`, `NodeGraph`/`Node`, `CodeEditor`, and `Terminal` — plus SVG
icon compilation (`pysilver[svg]`). `CodeEditor` and `Terminal` are optional
capabilities, not hard dependencies: Pygments syntax highlighting
(`pysilver[code]`) and a real spawned shell via `bittty`/`pexpect`
(`pysilver[terminal]`, POSIX only — Windows needs a ConPTY backend not yet
built). None of it touched `__all__`; the version moves for the view format's
sake, the same rule v1.2 established. A full-codebase review (60 subagents,
four phases) accompanied this release: a real ticker leak, a `PaintContext`
field silently dropped at nine clip sites, three hot-reload no-ops, and a
`Signal` race were all found and fixed along the way — see
`docs/CODE_REVIEW_2026-09.md`.

**v1.5 — the screen-reader bridge.** `app.bind_accessibility(AccessKitBridge(...))`
pushes the semantic tree to AT-SPI, and a reader can activate controls as well
as read them. Optional: `pip install 'pysilver[a11y]'`. Verified against the
live accessibility bus on KDE Plasma.

**v1.4 — the accessibility tree.** `AccessibleNode` joins `__all__`.
`app.accessibility_tree()` reports roles, names, states and bounds. There is no
screen-reader bridge, and the docs say so rather than implying otherwise.

**v1.3 — ViewModels.** `ViewModel` and `ViewModelError` join `__all__`, which
by the rule above is a minor release. A view file can now have its own logic:
one view, one ViewModel, bound explicitly, so an entry point stays an entry
point instead of accumulating every handler in the application.

**v1.2 — the view format grew, `__all__` did not.** Type-scale weight, letter
spacing and line height; `hit_padding` and `min_hit_size`; an `error:` state,
an `on_change` handler, and the `TextField` widget. All additive, none of it in
`__all__`, so the version moves for the *view format's* sake — a view file
written against 1.2 will not load on 1.1, and that is what a minor number is
for.

**Stylesheets are built.** A `styles:` list selects on widget kind, `classes:`,
and `name:`, with CSS-like precedence, resolved once at load so nothing is paid
per frame. Sheets are shareable across files and watched by hot reload, so
editing a theme restyles a running application.

**Motion is built.** M3 easing curves and duration tokens, an injectable clock,
and a `reduce_motion` setting. It drives overlay fades, state layers, every
selection control, tab and navigation indicators, indeterminate progress, the
carousel snap and content parallax, and scroll-linked app-bar collapse.

**The M3 type scale is built.** All fifteen roles are named styles —
`style: {text_style: title-large}` — and each resolves to a size, a weight, a
letter spacing and a line height. The figures come from Google's autogenerated
token source rather than the spec page, which serves a JavaScript shell with no
extractable table. A view can override the scale role by role.

**Text is editable.** `TextField` is M3's filled and outlined text field with a
floating label, supporting text and an error state, in all three of the shapes
M3 names: single-line, multi-line that grows with its content, and a
fixed-height text area that scrolls. Arrows and Ctrl+arrows,
shift-selection, cut/copy/paste, and undo that takes back a word rather than a
letter. Editing is by grapheme cluster, so backspace removes an accented
character and not its accent.

Frozen does not mean finished. What is deliberately **not** built yet:

| Absent | Consequence |
|---|---|
| A Windows or macOS screen-reader bridge | The AT-SPI bridge works; the other two need AccessKit's platform wheels and are untested |
| IME preedit | Committed characters only, so CJK input methods are unsupported |
| Clipboard access without focus | Copy and paste use the system clipboard, but Wayland grants that only to a focused window with a real keypress behind it — true of Ctrl+C/Ctrl+V, not of a background thread |
| `Terminal` on Windows | `pexpect.spawn` is POSIX-only; a `pywinpty`/ConPTY backend is architected for but not built |

Mobile and touch are explicit non-goals.

## Performance

Python, not the GPU, is the bottleneck — which is what the architecture is
organised around. Retained mode, typed invalidation, numpy display-list
assembly, cached subtree splicing, and paint-time scrolling all exist to keep
work off the per-frame path. §12 of ARCHITECTURE.md has the measurements.

## Testing

2365 tests, `ruff` and `mypy --strict` clean. Golden-image baselines cover the
rendered output; everything else — layout, reactivity, reconciliation, text
segmentation, event dispatch — runs with no GPU on any runner.

```bash
pytest                    # everything
pytest -m "not gpu"       # no GPU required
```

## License

MIT. See [LICENSE](https://github.com/mindderivative/pySilver/blob/main/LICENSE).

Bundled fonts keep their own licences: Roboto and Noto Sans under the SIL Open
Font License 1.1, Material Symbols under Apache 2.0. All three travel with every
distribution.
