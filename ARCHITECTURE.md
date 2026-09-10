# pySilver — Architecture

**A GPU-accelerated declarative desktop GUI framework for Python 3.14**

Status: Design. Revision 1. Last updated 2026-08-31.

---

## 1. Purpose, Scope, and Non-Goals

pySilver is a **distributable** desktop GUI framework: users `pip install pysilver`, author their interface declaratively in YAML, write application logic in Python, and get a hardware-accelerated Material Design 3 interface with no C toolchain on their machine.

### 1.1 In scope

- Declarative, hot-reloadable YAML layout with Pydantic validation.
- Fine-grained reactive state binding between Python logic and the view.
- A constraint-based layout engine that is deterministic, single-pass, and testable without a GPU.
- A single instanced WebGPU pipeline rendering every UI primitive — boxes, borders, shadows, glyphs, images — in one draw call, with analytic antialiasing.
- Full Material Design 3 dynamic colour from a seed, with zero-relayout theme switching.
- Non-blocking `asyncio` integration for application work.

### 1.2 Explicit non-goals (v1)

| Non-goal | Rationale |
|---|---|
| Web, mobile, or embedded targets | **Desktop-only, and not merely for now** — see §1.2.1. |
| Touch input | No touch, stylus, or gesture handling. Pointer, keyboard, and scroll wheel only. |
| Complex text shaping (Arabic, Devanagari, CJK vertical) | Requires HarfBuzz; a seam is designed in, see §5.7. |
| Screen-reader bridge (UIA / NSAccessibility) | Native and per-OS. The *semantic tree* is built (§5.11), and the AT-SPI bridge that pushes it to Linux is too (v1.5, `runtime/accesskit_bridge.py`); Windows and macOS need their own AccessKit platform wheels and are untested here. |
| CSS compatibility | The style vocabulary is MD3-shaped, not CSS-shaped. |
| Hot-reload of Python application logic | YAML reload only. Python reload is a different, much harder problem. |
| Multi-window | Single window in v1; the engine is written so the canvas is not a singleton. |

#### 1.2.1 What "desktop-only" changes

This is a design stance, not a deferral, and it settles a class of questions
that would otherwise be argued repeatedly.

**M3 is written mobile-first.** Applying it faithfully to a desktop framework
means knowing which of its rules are about *fingers* and which are about
*design*. Rules that do not apply here:

- **The 48×48dp minimum touch target, by default.** A finger-precision
  requirement; a mouse pointer is precise to the pixel, so a control is
  hit-tested at the size it is drawn unless a view asks otherwise. It *can* now
  be asked for — `min_hit_size: 48` (§5.9.1) — because "expressible but off by
  default" and "not expressible" are different things, and only the first lets
  an application decide.
- **Touch ripple radiating from the contact point.** State layers still apply;
  the ripple's touch-origin behaviour does not.
- **Compact breakpoints (<600dp).** Desktop windows live in M3's Expanded,
  Large, and Extra Large classes. Window *resizing* still matters; phone-shaped
  layout does not.
- **Bottom-anchored navigation.** Navigation Bar and Bottom App Bar are
  explicitly mobile patterns in M3's own catalogue. Navigation Rail is its
  desktop counterpart and takes priority (M3 Expressive folded Navigation
  Drawer into Navigation Rail's own expanded state — see §5.12's
  `NavigationRail` entry — so there is no separate desktop-drawer widget
  to weigh here either).

Correspondingly, affordances M3 treats as secondary are **primary** here, and
should be built before mobile-shaped components:

- **Hover** is a first-class state, not a progressive enhancement.
- **Focus rings and keyboard traversal** are how a desktop application is
  navigated (§5.11.1, built).
- **Visible scrollbars** and wheel-driven scrolling (§5.14, built).
- **Right-click and context menus**, **cursor shape**, and **mouse text
  selection** are desktop conventions with no mobile analogue — built in v1.2
  (§5.17.4, §5.17.5, §5.17.6).

### 1.3 Design principles

1. **Separate the document from the runtime.** Parsed YAML is inert data. Live UI is a mutable tree. Never conflate them (§4).
2. **Layout must not know the GPU exists.** It is pure Python over numbers, so it is unit-testable and fast to iterate.
3. **Do the least work per frame.** Python, not the GPU, is the frame-time bottleneck. Every subsystem is designed around caching and dirty-subtree invalidation.
4. **Validate at the boundary.** Untrusted YAML becomes strictly-typed data once, at parse time. Nothing downstream re-checks or defensively guards.
5. **One draw call is a design constraint, not an aspiration.** Any feature that would force a pipeline or bind-group switch (scissor clipping, per-widget textures) is rejected or redesigned (§5.8).

---

## 2. Dependency Stack

Versions are those verified present in the project virtual environment on Python 3.14.6.

### 2.1 Windowing and graphics

| Package | Ver | Role |
|---|---|---|
| `wgpu` | 0.32.0 | Graphics API. Targets Vulkan / Metal / DX12 through `wgpu-native`. Ships prebuilt binaries — no user toolchain. |
| `rendercanvas` | 2.7.2 | Owns the window, the surface, the event loop, and the frame scheduler. See §5.10 — this is a larger role than it first appears. |
| `glfw` | 2.10.2 | Backend for `rendercanvas.glfw`. Used **directly** only for capabilities rendercanvas does not surface (monitor enumeration, clipboard). |
| `cffi`, `pycparser` | 2.1.1, 3.0 | GLFW binding substrate. Transitive; never imported by pySilver. |

> **Correction to prior plan.** `wgpu.gui` was removed in wgpu-py; it does not exist in 0.32.0. The canvas import is `from rendercanvas.glfw import RenderCanvas`. Adapter and device acquisition are async by default: synchronous call sites must use `wgpu.gpu.request_adapter_sync()` and `adapter.request_device_sync()`.

### 2.2 Data, validation, configuration

| Package | Ver | Role |
|---|---|---|
| `PyYAML` | 6.0.3 | Parses view documents. **`safe_load` only** — view files are treated as untrusted input. |
| `pydantic` / `pydantic-core` | 2.13.5 | Validates the YAML dictionary into the strict Spec tree (§5.1). The single validation boundary in the system. |
| `pydantic-settings`, `python-dotenv` | 2.15.0, 1.2.3 | Framework configuration: DPI override, log level, vsync, backend selection, hot-reload toggle. |
| `numpy` | 2.5.2 | **Load-bearing.** Structured dtypes are the in-memory representation of the GPU instance buffer; display-list assembly is vectorised, not per-widget Python. Was omitted from the prior plan. |
| `annotated-types`, `typing_extensions`, `typing-inspection` | — | Pydantic transitive. |

### 2.3 Styling and text

| Package | Ver | Role |
|---|---|---|
| `materialyoucolor` | 3.0.4 | Derives the full MD3 tonal token set from a seed colour. Used as a **class**, not instantiated: `MaterialDynamicColors.primary.get_rgba(scheme)`. |
| `pillow` | 12.3.0 | Decodes user-supplied image assets (PNG/JPEG) into RGBA arrays for atlas upload. Not used for glyph staging; numpy suffices there. |

### 2.3.1 Text stack

Text is the one subsystem where a single library is not enough. Five packages divide the work along clean seams; each does exactly one job and none overlaps another.

| Package | Ver | Role | Standard |
|---|---|---|---|
| `uharfbuzz` | 0.56.1 | **Shaping.** Text + font + script + direction → positioned glyph IDs. Applies `GSUB` (ligatures, contextual forms) and `GPOS` (real kerning, mark attachment). | OpenType |
| `freetype-py` | 2.5.1 | **Rasterisation only.** Glyph ID + pixel size → 8-bit coverage bitmap, plus hinting and outline metrics. | — |
| `fontTools` | 4.64.0 | **Script itemisation** (`fontTools.unicodedata`), **font metadata** (`name`/`OS/2`/`head` tables), coverage indexing for the fallback chain. | UAX #24 |
| `python-bidi` | 0.6.11 | **Bidirectional reordering** — logical order → visual order for mixed LTR/RTL text. Rust-backed. | UAX #9 |
| `uniseg` | 0.10.1 | **Line break opportunities** and **grapheme cluster** segmentation. | UAX #14, UAX #29 |

`uharfbuzz` ships as a `cp310-abi3` wheel — it uses the CPython stable ABI, so it does not need recompilation for 3.14 or any future release. `python-bidi` and `fontTools` publish native `cp314` wheels. No user toolchain is required on any platform.

**Two corrections to the previous revision.** `freetype-py` was described as calculating "kerning and text layout"; it does neither in the sense required. Its role is now narrowly and accurately scoped to rasterisation. And the previous plan deferred shaping to a post-1.0 tier — with `uharfbuzz` present from the start, correct shaping is a v1 feature (§5.7).

Combined wheel footprint for the text stack is ≈16 MB, dominated by `uniseg`'s Unicode tables (8.2 MB) and `fontTools` (5.3 MB). Acceptable for a desktop framework; noted because it roughly triples install size.

### 2.4 Concurrency and tooling

| Package | Ver | Role |
|---|---|---|
| `anyio`, `idna` | 4.14.2, 3.19 | Structured concurrency primitives for application-level background work. |
| `watchfiles` | 1.2.0 | Rust-backed filesystem watching for YAML hot-reload (§5.11). |

---

## 3. System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│  APPLICATION                                                                │
│  view.yaml  ──bindings──▶  Signals  ◀──reads/writes──  app.py (async)       │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  FRAMEWORK CORE                          (single-threaded, engine thread)   │
│                                                                             │
│   spec/      ─▶  tree/       ─▶  layout/      ─▶  paint/                    │
│   Pydantic       Element         Constraints      Display list              │
│   Spec tree      tree +          down, sizes      (numpy structured         │
│   (immutable)    reconciler      up               array of instances)       │
│                                                                             │
│   runtime/  engine · events · signals · hot-reload                          │
│   theme/    MD3 token palette (one GPU buffer)                              │
│   text/     shaping seam · line breaking · glyph run cache                  │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  RENDER                                                                     │
│  atlas (glyph R8 + image RGBA8) · ring-buffered instance upload             │
│  ONE render pass ─▶ ONE instanced draw ─▶ ui.wgsl (SDF + analytic AA)       │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  wgpu-native  ▸  Vulkan (Linux) · Metal (macOS) · DirectX 12 (Windows)      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. The Four-Tree Model

The most important structural decision in pySilver. Four representations exist, each with a distinct lifetime and mutability. Collapsing any two of them causes a class of bugs that is very expensive to unwind later.

| # | Tree | Type | Mutable | Lifetime | Owns |
|---|---|---|---|---|---|
| 1 | **Spec** | Pydantic models | No | Replaced wholesale on hot-reload | Declared structure, static style, binding expressions |
| 2 | **Element** | Plain Python objects | Yes | Persists across reloads | Resolved style, focus, scroll offset, hover state, animation clocks, signal subscriptions |
| 3 | **Layout** | Fields on Element | Yes | Per layout pass | `constraints`, `size`, `offset`, `relayout_boundary` |
| 4 | **Display list** | numpy structured array | Rebuilt | Per paint pass, cached per subtree | Flat, painter-ordered GPU instances |

Hot-reload is therefore **reconciliation**, not replacement: parse a new Spec tree, diff it against the previous one, and patch the Element tree in place, preserving runtime state wherever a node's `id` and widget type match. A user editing `corner_radius` in their YAML does not lose scroll position, focus, or text-field contents.

This is also what makes fine-grained invalidation possible: because Elements are stable objects, a signal can hold a durable subscription to one.

---

## 5. Subsystem Specifications

### 5.1 Spec layer — `spec/`

`spec/loader.py` reads YAML via `yaml.safe_load`. `spec/models.py` defines the Pydantic hierarchy.

```python
class StyleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    width: SizeSpec = SizeSpec.AUTO  # px | "auto" | "expand" | flex(n) | pct(n)
    height: SizeSpec = SizeSpec.AUTO
    padding: EdgeInsets = EdgeInsets.zero()
    margin: EdgeInsets = EdgeInsets.zero()
    background: TokenRef | None = None  # MD3 token name -> resolved to palette index
    corner_radius: Corners = Corners.all(0.0)
    border: BorderSpec | None = None
    shadow: ShadowSpec | None = None


class WidgetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    widget: WidgetKind  # enum, not str
    style: StyleSpec = StyleSpec()
    bindings: dict[str, Expression] = {}  # "text": {{ user.name }}
    handlers: dict[str, str] = {}  # "on_click": "submit_form"
    children: list["WidgetSpec"] = []
```

Three deliberate choices:

- **`extra="forbid"`.** A typo in a YAML key is a startup error with a line number, not a silently ignored style.
- **`frozen=True`.** Spec nodes are immutable and safely shareable. Reconciliation compares them *structurally* (`==`) to skip untouched subtrees, and by identity as the fast path. They are deliberately not hashable — `handlers` is a mapping — and nothing requires them to be.
- **`WidgetKind` is an enum, and `background` is a validated `TokenRef`.** The prior plan's `background: str` deferred the failure to render time; here an unknown token name fails at load, where the error is actionable.

Note the **structural fix** to the prior `view.yaml`: `children` was nested under `style`. Children are structure, not styling; they belong on `WidgetSpec`.

`spec/expressions.py` parses `{{ … }}` binding expressions with :mod:`ast` — which does not execute anything — then walks the result against a strict node whitelist: attribute access, indexing, comparison, arithmetic, conditionals, and a small table of pure functions. **`eval` is never used on view content.** View files are data.

Rejected and covered by tests: `__import__`, `open`, `eval`, dunder and underscore-prefixed attributes, comprehensions, lambdas, and any method outside a short safe list. This matters because a view file is exactly the kind of artefact users copy from the internet.

### 5.2 Reactivity — `runtime/signals.py`

Fine-grained reactivity, in the SolidJS/Preact-signals tradition.

```python
class Signal[T]:
    def get(self) -> T: ...    # registers a dependency on the active tracking scope
    def set(self, value: T) -> None: ...   # notifies subscribers if != current

class Computed[T]:             # lazily recomputed, memoised, itself a dependency
class Effect:                  # side-effecting subscriber, used to drive Elements
```

A module-level tracking stack records which Element is currently rebuilding. Any `Signal.get()` during that rebuild adds the Element to the signal's subscriber set. A later `Signal.set()` therefore knows the exact set of Elements to invalidate.

**Invalidation is typed.** A single global dirty flag would redraw everything on every change; instead each Element carries three independent flags:

| Flag | Set when | Triggers |
|---|---|---|
| `needs_build` | A bound signal changed | Re-evaluate bindings; recompute resolved style |
| `needs_layout` | Resolved geometry changed | Layout pass from the nearest relayout boundary |
| `needs_paint` | Only visual properties changed | Display-list rebuild for that subtree |

Changing a button's colour sets `needs_paint` alone; layout does not run. Changing its label sets `needs_layout`, but propagation stops at the nearest relayout boundary (§5.4), so a label change inside a fixed-size panel never reaches the root.

**Threading contract:** signals are engine-thread-only. Background tasks marshal writes via `loop.call_soon_threadsafe` (§8).

### 5.3 Element tree and reconciliation — `tree/`

`tree/element.py` defines the mutable runtime node:

```python
class Element:
    spec: WidgetSpec
    parent: Element | None
    children: list[Element]

    # resolved
    style: ResolvedStyle  # tokens -> palette indices, sizes -> floats
    # layout (§5.4)
    constraints: Constraints
    size: Size
    offset: Offset  # relative to parent
    relayout_boundary: Element | None
    # runtime state — survives hot reload
    state: WidgetState  # focus, hover, pressed, scroll, animations
    subscriptions: set[Signal]
    # caching
    cached_instances: np.ndarray | None
    needs_build: bool
    needs_layout: bool
    needs_paint: bool
```

`tree/reconcile.py` implements keyed diffing. For each level, children are matched by `(id, widget)`. Matched nodes are updated in place and keep `state`; unmatched old nodes are disposed (subscriptions released); unmatched new nodes are constructed. Reordering is handled by index remapping rather than destroy-and-rebuild.

Structurally identical subtrees are **skipped entirely** — if `old.spec == new.spec`, nothing below can differ either, so the whole branch is left alone. `ReconcileStats` reports `created`/`updated`/`reused`/`disposed`/`skipped`, and the tests assert on those counts rather than merely on the resulting tree, which is what catches an accidental rebuild.

A widget kind change or an id change forces a rebuild: the old element is disposed and a fresh one constructed. Anything else would leave state attached to a node that no longer means the same thing.

### 5.4 Layout engine — `layout/`

**Constraints down, sizes up, parent positions children.** Single pass, O(n), no solver, fully deterministic.

```python
@dataclass(frozen=True, slots=True)
class Constraints:
    min_w: float
    max_w: float
    min_h: float
    max_h: float

    def tight(self) -> bool:
        return self.min_w == self.max_w and self.min_h == self.max_h
```

The protocol every widget implements:

```python
def layout(self, c: Constraints) -> Size:
    """Choose a size satisfying c. Call child.layout(...) for each child
    and assign child.offset. Must not read own offset or parent size."""
```

The final clause is the invariant that makes the whole thing work: a node's size depends only on its constraints and its children, never on its position or siblings. That is what permits subtree-local relayout.

**Relayout boundaries.** A node is a boundary when nothing beneath it can change its size, so dirt cannot propagate upward past it. There are **two independent conditions**, and the implementation found the second to be the more valuable one:

1. **Tight constraints** — the parent has already fixed the child's size.
2. **`parent_uses_size=False`** — the parent does not read the child's size at all, so it cannot care if it changes. This is strictly cheaper: it applies even under loose constraints, and it is the common case for `Align`, `Stack`, and any container that fills its own constraints.

`layout()` computes the boundary; subclasses implement `perform_layout()` and never call it directly. Marking `needs_layout` walks up only to the nearest boundary and schedules it on a `LayoutOwner`, which flushes dirty boundaries in **depth order** so a parent never relayouts a child twice.

Two consequences worth stating, both surfaced by tests:

- A fixed-size box containing padding makes **every** descendant a boundary, because deflating a tight constraint leaves it tight. This is the cheapest possible arrangement — dirt cannot escape the leaf at all.
- Relayout of a boundary uses `_layout_without_resize()`: its size provably cannot change, so the parent is never notified. That is precisely what makes subtree-local layout valid rather than merely an optimisation.

**Intrinsic sizing** (`get_min_intrinsic_width` etc.) is supported but explicitly opt-in and memoised per layout pass, because it is the one construct in this model that can go quadratic.

**Shapes are a shader branch, not a rasterised path** (`Kind.POLYGON`, the
`Shape` widget). M3 has no shape *component* but it does have a shape *system*
— "the Material shape library contains many types of shapes that can all morph
seamlessly into each other", with shape morph on the expressive motion scheme.
The obvious implementation is to compile shapes into glyph outlines and reuse
the text atlas; that is right for static SVG artwork and wrong here, because a
glyph is cached by `(glyph, size, axes)` and the atlas has no per-entry
eviction (§5.7.3). A shape that morphs or spins changes that key every frame.
This is the third design this trap has decided, after the icon `FILL` axis and
the resize pixel ratio (§5.8.1), so shapes stay parametric: `sides`, `rotation`
and `corner_radius` are instance floats, animating them is paint-only, and a
morph costs nothing beyond the interpolation itself. Cost is independent of
side count — the fragment folds a sample point into one sector, so a triangle
and a 64-gon are the same price. Rounding is measured on the **apothem**, not
the circumradius, so a rounded hexagon stays the size of a sharp one; at the
maximum it collapses to its inscribed circle, which is one of the two ways to
morph to a circle (raising `sides` is the other, and reaches the circumcircle).

`layout/algorithms.py` provides: `Box` (single child + padding/alignment), `Horizontal` / `Vertical` (main-axis flex distribution in two sub-passes — inflexible children first, then remaining space to flex weights), `Stack` (z-ordered overlay), `Scroll` (unbounded child constraint on one axis, clipping viewport), and `TextBox` (delegates to §5.7).

**This module imports nothing from `render/` or `wgpu`.** It is exercised entirely by unit tests.

### 5.5 Paint and the display list — `paint/`

The paint pass walks the Element tree in painter order (back to front, depth-first, children after parent) and emits GPU instances into a preallocated numpy structured array.

```python
INSTANCE_DTYPE = np.dtype(
    [
        ("rect", np.float32, 4),  # x, y, w, h — physical px, y-down
        ("radii", np.float32, 4),  # tl, tr, br, bl
        ("clip", np.float32, 4),  # ancestor clip rect
        ("clip_radii", np.float32, 4),
        ("fill", np.float32, 4),  # premultiplied RGBA, or tint for glyphs/images
        ("border", np.float32, 4),
        ("uv", np.float32, 4),  # atlas u0, v0, u1, v1
        ("params", np.float32, 4),  # border_width, shadow_blur, shadow_dx, shadow_dy
        ("flags", np.uint32, 4),  # kind, atlas_index, _, _
    ]
)  # 144 bytes; 10k instances = 1.4 MB/frame
```

Everything is `vec4`-aligned by construction, sidestepping WGSL alignment traps.

`flags.x` (kind) selects fragment behaviour: `0` = SDF box, `1` = glyph (atlas coverage × fill), `2` = image (atlas RGBA × tint), `3` = shadow, `4` = arc.

**Arcs are a fifth branch, not extra geometry** (§5.15). A test parses
`ui.wgsl` and asserts its `KIND_*` constants equal the Python `Kind` enum —
nothing else ties the two together, so a renumbered enum would silently draw
every box as a glyph rather than fail.

**Subtree caching.** Each Element caches the instance slice it produced. A clean subtree's cached slice is copied wholesale into the frame buffer; only `needs_paint` subtrees re-emit. Because instances carry absolute coordinates, a subtree that merely *moved* still needs re-emission — this is a deliberate simplicity trade, revisitable by adding a per-instance transform index.

**The cache key is the whole geometry the slice was built from** — absolute origin, size, pixel ratio, and the inherited clip — not the origin alone. Keying on origin alone shipped, and made window resizing paint stale frames: a row stretched across a Vertical keeps its origin when the window widens and changes only its width, so it passed the check and was spliced from its older, narrower slice. The symptom was not an obviously frozen window but *several different widths in one frame*, because rows that also shifted vertically did repaint and rows that did not stayed stale. Everything in the key is baked into the physical coordinates the slice holds, and nothing downstream can notice that they are wrong.

### 5.6 Theme — `theme/`

The MD3 token set is computed once from the seed via `materialyoucolor` and packed into a **single contiguous `float32` palette buffer** uploaded as a storage buffer.

Elements store a **`u32` palette index**, not an RGBA value.

The consequence is the point of the design: switching light/dark, changing the seed, or animating contrast is **one buffer write**. No relayout, no display-list rebuild, no Element traversal. A theme animation is free.

```python
class Palette:
    """Ordered, stable mapping of MD3 token name -> index -> RGBA."""

    def rebuild(self, seed: Hct, dark: bool, contrast: float) -> np.ndarray:
        scheme = SchemeTonalSpot(seed, dark, contrast)
        for i, name in enumerate(TOKEN_ORDER):
            r, g, b, a = getattr(MaterialDynamicColors, name).get_rgba(scheme)
            self.data[i] = (r / 255.0, g / 255.0, b / 255.0, a / 255.0)
        return self.data
```

#### 5.6.1 Colour space — a verified trap

The preferred surface format on this stack is **`rgba8unorm-srgb`**. That format treats every value written to it — clear values and fragment shader output alike — as **linear**, and applies the sRGB transfer function on write.

`materialyoucolor` returns **sRGB-encoded** 8-bit values. Dividing by 255 therefore yields sRGB-encoded floats, and handing those to an `-srgb` target double-encodes them.

This was measured, not theorised. The MD3 dark `surface` token is `(15, 13, 18)`. Uploaded naively as `15/255` and cleared to an `rgba8unorm-srgb` target, the rendered pixel reads back as **`(69, 64, 75)`** — a dark near-black rendered as mid-grey, and the error is largest exactly where MD3 puts its surface tones.

The palette builder therefore **linearises on upload**, and this is the only place the conversion occurs:

```python
def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
```

Consequences that are load-bearing elsewhere:

- The palette buffer holds **linear** RGBA. All shader blending is therefore physically correct — alpha compositing and shadow falloff in linear space is the right answer, not an approximation.
- Alpha is **not** transformed; it is already linear.
- Colours the user supplies as literal hex in YAML go through the same function at parse time, so authored and tokenised colours agree.
- Golden-image tests compare in the sRGB output space, so this conversion is covered by them (§11).

**Public token names are snake_case; the library's are camelCase.** `materialyoucolor` exposes `surfaceVariant`, `onPrimaryContainer`, and so on. YAML authors write `surface_variant`, which is idiomatic for both YAML and Python, and `theme/tokens.py` holds the generated mapping. The vocabulary is 59 tokens, including the five `*_palette_key_color` entries — included for completeness because appending to a frozen order is safe and inserting into it is not.

Token order is a frozen, versioned constant — indices are baked into cached display lists, so reordering it is a breaking change.

### 5.7 Text — `text/`

Text is the largest subsystem in the framework and the one most often underestimated. It is specified here in full because retrofitting it is not practical: shaping, fallback, and bidi each change the data structures that layout and paint consume.

#### 5.7.1 The pipeline

Seven stages, each owned by exactly one dependency. Everything below the line was verified working against the installed versions (§5.7.6).

```text
  input: str + TextStyle (family, size, weight, features, lang)
    │
    ├─1─ Bidi resolution ......... python-bidi     UAX #9   → runs + embedding levels
    ├─2─ Script itemisation ...... fontTools.ud    UAX #24  → runs + script + direction
    ├─3─ Font resolution ......... FontDB coverage          → runs bound to a concrete face
    ├─4─ Shaping ................. uharfbuzz       OpenType → PositionedGlyph[] per run
    ├─5─ Line breaking ........... uniseg          UAX #14  → lines, from measured advances
    ├─6─ Rasterisation ........... freetype-py              → coverage bitmaps → atlas
    └─7─ Instance emission .......                          → display list (§5.5)
```

**Stage order is load-bearing.** Bidi runs first because it operates on the whole paragraph and produces the embedding levels every later stage needs. Itemisation then splits by script, and font resolution splits further by face — shaping requires a run that is uniform in *all three* of script, direction, and font.

**Stages 4 and 5 interleave.** Line breaking needs measured advances, which only shaping produces; but shaping context can cross a break.

Each block is shaped **once**. Candidate breaks are measured by looking up cumulative advances — one shaped pass attributes every glyph's advance to the source offset of its cluster, so any span costs a subtraction — and only the lines actually emitted are shaped again. That second shaping is not overhead: a line needs its own runs to paint, and shaping context legitimately differs either side of a break, which is also what corrects the table's two approximations (kerning across a cut, and a break falling inside a ligature).

**The M4 implementation did not do this**, and re-shaped the growing candidate prefix at every break opportunity. The cost that removed is worth stating precisely, because the original note here had it in the wrong variable. `line_start` advances after each emitted line, so the prefix restarts every line and the quadratic term is in break opportunities **per line**, not per paragraph — which is why paragraph length always measured linear and the regression hid. The cost therefore scaled with *how wide the window was*: one 351-character paragraph at a 120 px wrap width cost 15.5 ms, and the same text on one 3840 px line cost **107.9 ms**. A wide window holding a long line was the worst case, which is an entirely ordinary thing for a desktop application to be.

Measured after the change, the same sweep is flat at 13–15 ms across every width from 120 px to 3840 px — the worst case improving **8.4×** — and the width dependence is gone rather than reduced (§12.2).

**A femtopixel of slack is required, and that is not a fudge.** A `Text` shrink-wraps to its ink extent and the paint pass then lays it out again at *exactly* that width, so the fit test is evaluated at precise equality on every frame drawing unwrapped text. `np.sum` adds pairwise and `np.cumsum` sequentially; for `"title-small"` the two orders differ by 7e-15 px, which was enough to wrap it to "title-" / "small" so the widget measured one line and painted two. `FIT_EPSILON` is set far below a subpixel and far above float64 noise, and `test_text_laid_out_at_its_own_ink_width_stays_on_one_line` pins the invariant for all fifteen type-scale roles.

**Glyphs can be coloured individually.** `TextEngine.emit` takes `spans` --
`(start, end, value)` over **paragraph source offsets**, where the value is a
palette token or a literal RGBA. This is what syntax highlighting and ANSI
colour both need, and they are the same requirement.

Source offsets rather than glyph indices, because that is what a lexer or an
escape-sequence parser produces and because the two do not correspond: a
ligature is one glyph for several characters, and a blank glyph is dropped
entirely, so `"def foo"` emits six quads and not seven. Doing the mapping once
here is what stops every consumer getting ligatures wrong differently.
`GlyphPlacement.offset` carries the paragraph-absolute offset for it, correct
regardless of direction — `TextLine.run_starts` records each run's true
logical start once, at layout time, rather than reconstructing it later by
accumulating run lengths in visual order (which only works for pure LTR;
§5.7.7 covers the fix in full).

The mapping is a `searchsorted` over span starts, not a lookup per glyph, and
the result is written as whole columns like every other instance field. **990
glyphs with 124 spans cost 1.659 ms against 1.599 ms unspanned** — a 4%
difference, where a per-glyph Python loop would have reproduced the scalar-emit
problem §12.2 records. Text with no spans builds no arrays at all and follows
exactly the path it did before.

A token themes with the rest of the interface and a literal colour does not,
which makes the literal correct only where the colour genuinely is fixed: an
ANSI escape's is, a syntax theme's should be tokens.

#### 5.7.2 Fonts, coverage, and fallback — `text/fontdb.py`

`FontDB` maps `(family, weight, style)` to a concrete face and owns the fallback chain.

Coverage is queried in bulk. `hb.Face.unicodes` returns the face's full codepoint set in one call — 5918 entries for DejaVu Sans — so a fallback index is built without opening every font through `fontTools`:

```python
class FontDB:
    def coverage(self, face_id: FaceId) -> frozenset[int]: ...  # from hb.Face.unicodes
    def resolve(self, cluster: str, style: TextStyle) -> FaceId:
        """First face in the chain covering every codepoint in the cluster."""
```

**Fallback resolves per grapheme cluster, not per codepoint.** Splitting a cluster across two faces produces visibly broken output for combining marks and ZWJ emoji sequences. Failure of the whole chain yields glyph `0` (`.notdef`), rendered as the font's missing-glyph box — a visible, debuggable result rather than a silent gap.

Measured on the installed stack, DejaVu Sans covers `U+0041 A` (gid 36) and `U+0627 ا` (gid 1365) but **not** `U+4F60 你` or `U+1F642 🙂`. Fallback is not a theoretical concern; it is needed for any font, for very ordinary text.

**A default font is bundled with the package.** This is not a convenience — it is required by two other parts of the architecture. Golden-image tests (§11) cannot be deterministic against whatever fonts a CI runner happens to have, and a framework that renders nothing until the user configures a font path is not usable out of the box. System font *enumeration* (fontconfig on Linux, DirectWrite on Windows, CoreText on macOS) is genuinely platform-specific and is deferred past v1; explicit font paths are supported from M4.

#### The bundled stack

Material Design 3 names **Roboto** as the default typeface of its type scale and **Noto Sans** as the fallback collection, with the chain `Roboto Flex → Roboto → Noto Sans`. Roboto Flex is excluded deliberately: M3 states it "isn't yet part of the M3 typescale".

| File | Size | Weight | Codepoints | Role |
|---|---|---|---|---|
| `Roboto-Regular.ttf` | 154 KB | 400 | 927 | Default face |
| `Roboto-Medium.ttf` | 154 KB | 500 | 927 | `label-large` and other medium-weight roles |
| `NotoSans-Regular.ttf` | 612 KB | 400 | 3,094 | Fallback tier — Latin/Greek/Cyrillic |
| `NotoSansArabic-Regular.ttf` | 190 KB | 400 | 1,561 | Fallback tier — Arabic |
| `NotoSansHebrew-Regular.ttf` | 47 KB | 400 | 464 | Fallback tier — Hebrew |
| `MaterialSymbolsOutlined-Subset.ttf` | 102 KB | variable | 218 icons | Icons (§5.7.8) |

**≈3.8 MB total**, exposed through `pysilver.assets` (`DEFAULT_FONT`, `MEDIUM_FONT`, `FALLBACK_CHAIN`) and `pysilver.text.icons`.

Three decisions worth recording:

- **M3's fallback collection cannot be shipped.** The full Noto Sans set is 119 MB, plus 299 MB for CJK — against PyPI's ~60 MB project cap. Only Latin/Greek/Cyrillic, Arabic, and Hebrew Noto families are bundled — one small per-script member each, nowhere near the excluded omnibus case. `NotoSans-Regular.ttf` adds **2,187 codepoints** over Roboto (841 extended Latin, 289 Greek, 533 combining marks and modifiers, 129 Devanagari, 115 Cyrillic); `NotoSansArabic-Regular.ttf`/`NotoSansHebrew-Regular.ttf` add real Arabic and Hebrew coverage, making Tier 2/3 RTL support (§5.7.7) demonstrable without a system font. Fallback is genuinely exercised in v1 rather than being dead code, but still adds no CJK or emoji. Broader fallback waits on system font discovery.
- **Static instances, not variable fonts.** `google/fonts` publishes both families only as variable fonts. The bundled faces are produced with `fontTools.varLib.instancer`, pinning `wght` and `wdth`. That saves ~1.6 MB and keeps the loader free of variation-axis configuration.
- **Roboto's coverage matches Tier 1 exactly.** Its 927 codepoints span Latin, Greek, and Cyrillic — precisely the scope §5.7.7 commits to, so the bundled font and the documented text tier agree without either being bent to fit.

#### 5.7.3 Shaping — `text/shaping.py`

```python
@dataclass(frozen=True, slots=True)
class ShapedRun:
    face: FaceId
    glyphs: np.ndarray  # uint32 glyph IDs
    advances: np.ndarray  # float32, font units
    offsets: np.ndarray  # float32 (x, y) pairs — mark positioning
    clusters: np.ndarray  # uint32 byte index back into source text
```

`clusters` is what makes hit testing, caret placement, and selection possible after shaping has reordered and merged characters — it is the only link from a rendered glyph back to the source string, and it must be preserved through every later stage.

Output is numpy from the start, so stage 7 writes glyph instances vectorised (§12).

**Glyph IDs from HarfBuzz index the same table freetype rasterises from.** This is the seam the whole two-library design rests on, and it was verified directly: HarfBuzz returns gid 36 for `'A'` in DejaVu Sans, and `freetype.Face.get_char_index('A')` returns 36. No translation layer is needed or wanted.

#### 5.7.4 Caching

Four caches, in descending hit rate. Without them the perf budget in §12 is unreachable.

| Cache | Key | Value | Invalidated by |
|---|---|---|---|
| **Shaped run** | `(text, face, size, script, direction, features, lang)` | `ShapedRun` | Text or style change |
| **Paragraph layout** | `(run ids, available width, align)` | Line boxes | Reflow / resize |
| **Segmentation** | `text` | UAX #14 break positions, UAX #29 clusters | Nothing — bounded LRU |
| **Glyph raster** | `(face, px_size, gid, subpixel_bucket)` | Atlas rect | DPI change, LRU eviction |

Static labels — the majority of any interface — hit all four and cost nothing per frame beyond copying a cached instance slice.

**The segmentation cache is keyed on text alone**, which is what makes it the one that saves a resize. Break positions and grapheme clusters do not depend on the width being tried, but wrapping asks for them once per *candidate line* and again on every relayout — so dragging a window recomputed the same UAX #14 and #29 answers hundreds of times a second. Profiling a gallery resize put uniseg at **54% of the frame**; memoising these two pure functions took a resize frame from 17.6 ms to 7.3 ms, and 1.3 ms once line breaking was memoised as well. Bounded LRU, because the keys are arbitrary user text.

#### 5.7.5 Rasterisation and the atlas

Grayscale coverage bitmaps at exact device pixel size, as established in §5.8 — sharper and cheaper than SDF for UI text at known sizes. Three horizontal subpixel buckets. The `R8Unorm` glyph atlas with skyline packing and LRU eviction is unchanged.

**Colour emoji route to the RGBA8 image atlas instead.** freetype rasterises `CBDT`/`sbix`/`COLRv0` glyphs as colour bitmaps, which do not belong in an R8 coverage texture. The display-list `flags.x` kind is set to `2` (image) rather than `1` (glyph), so a colour emoji is an atlas-textured quad and needs no shader change at all — the existing two-texture bind group (§5.8) already accommodates it. `COLRv1` (gradient-capable) is out of scope.

#### 5.7.6 Verified behaviour

Each claim below was executed against the installed stack, not inferred from documentation:

| Capability | Evidence |
|---|---|
| GPOS kerning applied | `"AVA Wa To"` measured 10548 units shaped, 11289 with `kern` disabled — 6.6% tighter |
| Ligature substitution | `"fi film"` → 5 glyphs from 7 characters |
| HarfBuzz ↔ freetype gid agreement | Both return 36 for `'A'`; freetype rasterised gid 36 to a 23×22 bitmap, 213 ink pixels |
| Script itemisation with direction | `"Hello مرحبا 你好 हिन्दी!"` → `Latn`/LTR, `Arab`/RTL, `Hani`/LTR, `Deva`/LTR |
| Bidi reordering | `"The title is مرحبا today"` reorders the Arabic run for display |
| UAX #14 line breaking | `"can't"` kept intact; break offered after `dog-` |
| UAX #29 grapheme clusters | 13 code points → 6 clusters; `👩‍👩‍👧` and `🇯🇵` each one cluster |
| Coverage query | DejaVu Sans covers `A` and `ا`, not `你` or `🙂` |

#### 5.7.8 Icons

**M3's icon set is a variable icon font**, which is the single most useful fact
about it: an icon is a *glyph*, so icons need no rendering path of their own.
They flow through `FontDB`, the freetype rasteriser, the glyph atlas, and the
`GLYPH` instance kind unchanged — an icon costs **no extra draw call**.

Material Symbols exposes four axes; the bundle keeps two:

| Axis | Range | Kept | Why |
|---|---|---|---|
| `FILL` | 0–1 | ✅ | Load-bearing, not decorative — M3 uses it for the selected/unselected transition on navigation items and toggles |
| `wght` | 100–700 | ✅ | Pairs icon stroke weight with typography |
| `GRAD` | −50–200 | pinned | Fine-tuning |
| `opsz` | 20–48 | pinned | Fine-tuning |

**The bundle is a subset.** The full outlined variable font is **10.6 MB** for
~4,275 icons. Subsetting with `fontTools` to a curated 218-icon core set —
covering every component in the M3 catalogue — and pinning `GRAD`/`opsz` yields
**102 KB**, a 102× reduction. An icon outside the set raises a `KeyError`
naming the problem rather than silently rendering `.notdef`.

**Axis coordinates are part of the atlas key.** A filled and an unfilled icon
are the same glyph id at the same size, and would otherwise collide.

Two facts worth recording, both found by measurement:

- **`freetype-py`'s `set_var_design_coords` takes plain design values, not
  16.16 fixed point.** Passing scaled values silently clamps every axis to its
  maximum, which presents as "the axis does nothing" rather than as an error.
- **Material Symbols embeds no licence name record.** Its terms — Apache-2.0,
  unlike the OFL text faces — come from the repository `LICENSE`, vendored
  alongside it. The licence test therefore asserts per font rather than
  assuming one licence across the bundle.

The `Icon` widget takes its name from `icon:`, so binding expressions work on
it: `icon: "{{ 'star' if saved.get() else 'star_border' }}"` switches the icon
with state exactly the way a label does.

#### 5.7.9 SVG icons — `text/svgicons.py`

Arbitrary SVG artwork gets the same property Material Symbols has for free —
no rendering path of its own — by *becoming* a font rather than by adding a
second one next to the pipeline above. **The pipeline:** SVG path commands
(`svgelements`, an optional extra — `pip install 'pysilver[svg]'`) → cubic
curves refit to quadratic (`fontTools.pens.cu2quPen`, since `glyf` is
quadratic and SVG's curves are cubic) → a real glyph (`TTGlyphPen`) → a real
font file on disk (`fontTools.fontBuilder`) → `Face`, identical to loading
Roboto. `Face` only ever opens a path — HarfBuzz, FreeType, and fontTools all
read the same file — which is the seam that makes this reuse everything
above with no change to it at all: `emit_icon` needed zero modification.

**Why compile to a glyph rather than render the path directly**, stated
plainly because the more obvious-looking design was tried first and rejected
for `Shape` (§5.8.5's neighbour in spirit): a glyph's cache key includes its
rasterised size, and the atlas has no per-entry eviction, so anything that
changes size or content every frame thrashes it. Static artwork — an icon
that does not morph — has no such problem; it rasterises once and the cache
does the rest. Content that *does* need to animate stays off the atlas
entirely (`Shape`'s parametric SDF, §5.8), which this module does not
attempt to replace.

**A real limitation, found by testing a ring with a hole, not by reading the
spec.** `glyf` has no per-contour fill-rule flag; FreeType always fills by
the nonzero winding rule. An SVG using the default `fill-rule="nonzero"`,
with a hole wound opposite to the shape it cuts from — what every common
export tool produces — compiles and rasterises correctly. An SVG that
instead sets `fill-rule="evenodd"` and winds every contour the *same*
direction is equally valid SVG and loses the hole: confirmed by compiling
both windings of the same ring and rasterising each. There is no fix inside
this module for `evenodd` source; it would need rewinding first.

**Every icon is scaled from its own viewBox**, independently, so a tiny
`viewBox="0 0 2 2"` icon and a `viewBox="0 0 2000 2000"` one land at the same
visual size — checked, not assumed, since a shared scale would make one
icon's units leak into another's proportions.

**The regression this module actually produced while being built:**
`IconSet(face)` with no `names` argument silently falls back to the *bundled*
218-name Material Symbols table, so `load_svg_icons` — which constructs an
`IconSet` from a freshly compiled `Face` — must pass its own names
explicitly, or every real lookup on a custom set raises "unknown icon" while
the font itself compiled without error. Caught by testing the constructed set
against a real name before assuming it worked. `tests/golden/
test_baselines.py::test_svg_icons_baseline` renders a compiled triangle and a
compiled ring — with its hole — through a real `App`, tinted by a real
palette token, so a shader-level regression here fails on pixels rather than
on a property that can pass while the picture is wrong.

#### 5.7.7 Scope tiers

Revised upward from the previous revision, which deferred all shaping past v1. With the stack proven, the honest boundary is now much further out.

| Tier | Coverage | Status |
|---|---|---|
| **1** | Full OpenType shaping — ligatures, GPOS kerning, mark attachment, contextual forms. Grapheme clusters, UAX #14 breaking, font fallback. | ✅ **shipped, M4** |
| **2** | RTL and mixed-direction *rendering*. `text/bidi.py` drives real UAX #9 embedding-level resolution (not a single-flip heuristic — nested LTR-in-RTL-in-LTR resolves correctly per rule I2); `itemize.py` splits level-runs before script/font runs, so a level boundary always produces a separate `ItemRun` even where script alone would not. `NotoSansArabic-Regular.ttf`/`NotoSansHebrew-Regular.ttf` are bundled, so Arabic and Hebrew render as real glyphs, not tofu. | ✅ **shipped** |
| **3** | RTL *editing* — caret movement, affinity at direction boundaries, selection spanning runs. `EditState.affinity` (`Affinity.UPSTREAM`/`DOWNSTREAM`) disambiguates a caret sitting exactly at a direction boundary; `Editor.move()`'s left/right walk steps through a precomputed, full visual ordering of every caret position (`editing._visual_positions`) rather than deriving each step incrementally — an earlier incremental design oscillated forever near a boundary instead of making progress, caught by live testing before it shipped. `rects_for` emits one rect per disjoint span, so a selection crossing a direction boundary paints as multiple rects rather than one stretched across the gap. | ✅ **shipped** |
| **4** | Vertical CJK, ruby annotation, `COLRv1` gradient emoji, variable-font axes. | post-1.0 |

The tier the release supports is stated in user-facing documentation. Reordering was always the easy half; a caret that moves sensibly through `"The title is مرحبا today"` — including landing on the correct one of two valid on-screen positions when the offset sits exactly at a direction boundary — was the hard half, and is what Tier 3 closes.

### 5.8 GPU pipeline — `render/`, `render/shaders/ui.wgsl`

One pipeline. One render pass. One instanced draw call per frame.

**Geometry.** A 4-vertex unit quad in a static vertex buffer, `triangle_strip`. Per-instance data arrives as a second vertex buffer with `step_mode="instance"`, chosen over a storage buffer for maximum backend portability.

**Colour resolution happens in the fragment stage, not the vertex stage.** The palette is a storage buffer, and storage-buffer visibility in the vertex stage is not guaranteed across backends (it is zero in some compatibility profiles). Resolving per-fragment costs nothing measurable and removes the portability risk entirely.

**Bind group 0** (bound once per frame):

| Binding | Resource |
|---|---|
| 0 | `uniform Globals { projection: mat4x4<f32>, viewport: vec2f, dpr: f32, _pad: f32 }` |
| 1 | `storage<read> palette: array<vec4<f32>>` — MD3 tokens (§5.6) |
| 2 | `texture_2d<f32>` — glyph atlas, R8Unorm |
| 3 | `texture_2d<f32>` — image atlas, RGBA8UnormSrgb |
| 4 | `sampler` — linear, clamp-to-edge |

**Signed distance field core.** A rounded box with independent corner radii:

```wgsl
fn sd_rounded_box(p: vec2<f32>, half: vec2<f32>, r: vec4<f32>) -> f32 {
    var rr: vec2<f32> = select(r.wz, r.xy, p.y < 0.0);   // top pair vs bottom pair
    let radius: f32   = select(rr.y, rr.x, p.x < 0.0);   // left vs right
    let q = abs(p) - half + radius;
    return min(max(q.x, q.y), 0.0) + length(max(q, vec2<f32>(0.0))) - radius;
}
```

**Analytic antialiasing.** Because the fragment shader has a true distance field, the coverage of an edge is available exactly — no MSAA, no post-process, no resolve target, and it is correct at any radius:

```wgsl
let d  = sd_rounded_box(local, half_size, in.radii);
let aa = fwidth(d);
var alpha = 1.0 - smoothstep(-aa, aa, d);
```

**Clipping in the shader, not the scissor rect.** Scissor state changes force the draw call to split, which would forfeit the central design constraint. Instead every instance carries its ancestor clip rect and radii, and coverage is multiplied by a second SDF evaluation:

```wgsl
let dc = sd_rounded_box(frag_pos - clip_center, clip_half, in.clip_radii);
alpha *= 1.0 - smoothstep(-fwidth(dc), fwidth(dc), dc);
```

This yields correctly antialiased **rounded** clipping — which scissor rects cannot express at all — while preserving one draw call.

**Borders** are a second SDF evaluation inset by `border_width`. The ring is the *difference* of the two coverages, so fill and border occupy disjoint regions and can simply be summed — they never double-composite, which a naive over-blend would do at every rounded corner.

**Shadows are a separate instance** (`kind = 3`) emitted *before* the box they sit behind, rather than a second pass inside the box's own fragment. This keeps the shader branch flat and lets a shadow be positioned, blurred, and clipped independently. The Gaussian is approximated by `smoothstep` across the blur radius over the offset distance field.

**`flags.z` and `flags.w` carry palette token indices** for fill and border, with `0xFFFFFFFF` meaning "use the literal colour in the instance". This is what makes a theme switch a single buffer upload while still allowing authored hex colours.

**Buffer strategy.** A ring of three instance buffers, rotated per frame so the CPU never writes a buffer the GPU may still be reading. Buffers grow by doubling and never shrink within a session. Upload is a single `queue.write_buffer` of a contiguous numpy slice.

### 5.9 Events and hit testing — `runtime/events.py`

Events arrive from `rendercanvas` callbacks and are pushed onto a queue drained once per frame (§6), so a burst of mouse-move events coalesces rather than triggering redundant work.

**Hit testing walks the Element tree in reverse painter order** and returns the topmost hit path, respecting ancestor clip rects. A naive full-tree recursion that visits every node — as in the prior draft — both ignores z-order and cannot express "the panel above intercepted this click".

The path is **the target followed by its ancestors**, not everything under the cursor. An occluded sibling that also contains the point is absent from it and receives nothing, which is the whole point of respecting paint order.

#### 5.8.1 Resize: every frame is drawn, and why

**During a resize, rendercanvas draws and presents once per compositor
configure, synchronously** — "during a resize, the `glfw.poll_events()`
function blocks, so our event-loop is on pause … we can use these to draw, to
get a smoother experience" (`rendercanvas/glfw.py`), via
`_draw_and_present(force_sync=True)`, which bypasses its own `max_fps`
throttle. Measured on KDE Plasma Wayland: **250 genuinely new sizes a second**.

The obvious response is to throttle — draw the latest size and skip the rest.
**That was tried, shipped, and reverted, and the reason is worth keeping.** A
Wayland client is expected to commit a buffer in response to a configure.
Declining a frame means not committing, which leaves the compositor waiting
before it offers the next size. The throttle did not merely fail to help; it
was the cause of the choppiness it was meant to fix:

| | redraws/s | gap between drawn frames | worst gap |
|---|---|---|---|
| throttled, vsync on | 12 | 86 ms | 1.1 s |
| throttled, vsync off | 12 | 66 ms | 0.7 s |
| unthrottled, vsync on | 99 | 0.04 ms | 7.9 s |
| unthrottled, vsync off | **466** | **0.04 ms** | none |

The inter-frame gap collapses by three orders of magnitude the moment
declining stops. So `draw_frame` presents every frame it is asked for, and
`vsync` is the only lever: with it on, this path still produces multi-second
stalls under a fast drag; with it off, a live resize runs at several hundred
redraws a second with none.

**`Settings.vsync` therefore defaults to False**, which is not the conventional
choice for an interface and is a deliberate trade. A window that lurches around
for seconds while being dragged is a worse defect than tearing during an
animation, and the usual argument for vsync — that an unsynchronised loop burns
the GPU — does not apply here: an idle pySilver application renders no frames at
all (§5.10), so there is no loop to burn anything. Set it True on a platform
where the resize path behaves and tearing matters more.

**What remains, and where it lives.** With every frame drawn, a live resize on
KDE Plasma runs at several hundred redraws a second with no stall, and the
window still trails the pointer slightly. That residue is measured rather than
assumed. A resize frame is ~1.94 ms, split roughly half to pySilver and half to
the platform:

| stage | median | share |
|---|---|---|
| layout | 0.34 ms | 27% |
| paint | 0.58 ms | 32% |
| upload | 0.01 ms | 1% |
| acquire (`get_current_texture`) | 0.48 ms | 33% |
| submit | 0.10 ms | 7% |

pySilver's half is not waste: during a resize about half the element tree is
still spliced from its paint cache, no element is left spuriously dirty, and
the ones that rebuild are exactly those whose width changed.

**`acquire` is the swapchain rebuild**, and that was worth testing rather than
assuming — splitting it by whether the size actually changed gives a **12×
difference**: 0.476 ms median across 2346 rebuild frames against 0.039 ms
across 24 that reused the swapchain. wgpu reconfigures the surface whenever the
size differs, so during a drag it tears down and recreates the
`VkSwapchainKHR` on every pixel.

**That rebuild is now amortised, and the note that said it could not be is
corrected below.** `Settings.resize_bucket` (256 px, 0 disables) rounds the
size the surface is configured at *up* to a multiple while the window is
changing size, so the swapchain is rebuilt once per bucket instead of once per
pixel. Measured on KDE Plasma during a live drag:

| during a drag | acquire | redraws/s |
|---|---|---|
| exact size (before) | 1.35 – 1.88 ms | 350 – 455 |
| pinned to 256 px | **0.043 – 0.053 ms** | **720 – 965** |

Acquire falls ~35× and the resize path roughly doubles its frame rate, so the
saving is larger than the acquire line alone. The pointer trailing is gone.

**What the previous version of this paragraph got wrong.** It claimed pySilver
"supplies only a draw callback and has no seam at which to hold a stale
swapchain". That is false. `GPUCanvasContext.set_physical_size` is public
wgpu-py API — "External code needs to set the framebuffer size ... the
application must call this" — and the size reaches wgpu along a chain pySilver
sits on the end of:

```
GLFW framebuffer callback -> rendercanvas _size_info -> _rc_set_size_dict
    -> wgpu_context.set_physical_size() -> _has_new_size -> wgpuSurfaceConfigure
```

`Engine._pin_surface` overrides the last step. The claim was asserted from
reading the call path rather than from trying it, and stood for several
milestones.

**The compositor scales an oversized buffer; it does not crop it.** The old
paragraph guessed "an oversized one is displayed oversized", which is also
wrong. This was settled by eye, because the two are indistinguishable from any
number pySilver can measure: a buffer 1024 px wide in a 900 px window is
squeezed to fit. **That is why nothing else changes.** `_upload` already
projects the *window* size, so content is drawn across the whole oversized
buffer and the compositor's squeeze undoes the stretch exactly. Geometry comes
out pixel-exact — this was checked with a 1 px grid, not assumed.

The cost is one non-integer resample, which softens text: rendered at 900 px
and displayed through a 1024→900 squeeze, small type is legible but visibly
less crisp than native. Raising the pixel ratio to compensate makes it near
perfect, and is deliberately **not** done — the glyph atlas has no per-entry
eviction (§5.7.3), so changing the rasterisation size mid-drag trades a
swapchain rebuild for an atlas rebuild. Instead the pin is released
`SETTLE_FRAMES` after the last size change: soft while a drag is in flight,
when nobody is reading, and exact the moment it stops. The engine requests
those settling frames itself, because an `ondemand` application otherwise stops
drawing when the drag does and would stay pinned indefinitely.

Nothing here skips or throttles a frame. Every frame is still drawn and
committed, which the reverted throttle above proved is not optional.

**The same trailing symptom came back in 2026-09, from a different cause,
and the fix here is not the one that removed it.** Adding `Terminal` to the
example gallery reintroduced periodic stutter during a live resize drag —
measured with a purpose-built per-stage instrumentation harness
(`examples/gallery/resize_probe.py`, kept in the repo for the next time this
needs re-diagnosing) rather than assumed from the symptom. `acquire`
(the swapchain rebuild this section fixes) stayed at its post-fix ~0.03–0.1
ms throughout the drag — **not a swapchain regression**. Instead, `paint`
spiked 8–22 ms roughly every 12 px of width change, matching a monospace
cell width to the pixel. `TerminalElement.perform_layout` reflows the
terminal library's video memory (`board.resize()`, `bittty` as of
2026-09-08 -- `screen.resize()` under the `pyte` it replaced, same
mechanism) every time the computed (cols, rows) changes, and a reflow
changes exactly which characters land in which row — so the next
paint's per-run `text_engine.layout()` calls see brand-new text the shape
cache has never seen, forcing a full HarfBuzz re-shape of the whole visible
grid once per column crossed. Benchmarked directly: `screen.resize()` and
`pexpect`'s `setwinsize()` are both sub-millisecond on their own: the cost is
entirely the forced re-shape that follows, not the reflow call itself.

**Fixed the same way as the swapchain, adapted for a real difference.**
`TerminalElement` now defers reflowing an *already-settled* grid until the
target (cols, rows) has sat unchanged for `GRID_SETTLE_SECONDS` (0.1s) — a
fast drag never reflows at all until it pauses. Two things make this not a
literal copy of `_pin_surface`: the very first sizing (tracked by
`_grid_settled_once`, not "a screen exists" — `set_ticker()` creates the
real screen before the first `perform_layout` call an `App`-managed
Terminal ever gets, so a screen already existing does not mean a prior grid
to protect) applies immediately, since there is no prior content to keep
stable against; and the countdown is wall-clock, checked from `paint_self`
rather than `perform_layout`, because layout is not guaranteed to run again
after a drag stops the way `draw_frame` runs every frame regardless — a
frame-count settle counter here would get stuck forever on a window that is
never resized again. The terminal's own `terminal_poll` heartbeat (already
running for the cursor blink) is what guarantees a check happens soon after
the drag ends. Verified with the same offscreen-drag technique: a 300-pixel
continuous shrink was 0–22 ms/frame before this fix and 5.4 ms mean / 7.5 ms
max after it, with the deferred grid confirmed to catch up correctly a few
frames after the drag stops.

**Neither of the above was the actual complaint, and the real one lived
one layer further out than anything `Engine` measures.** After both fixes
above, per-frame cost was clean (p50 2.8 ms, p99 6.1 ms across ~5300
frames) but the window still visibly trailed the pointer — and, tellingly,
releasing the mouse mid-flick did not stop it: the window kept working
through a sequence of sizes the pointer had already passed, "like it's
following a queue" (reported verbatim, and it was exactly right). Video
analysis of the symptom was inconclusive on purpose-forced grounds: a
screen-recorder duplicating frames to hit its target rate is
indistinguishable, from the recording alone, from a genuine render lag, so
a second capture on a plain white background with automated edge-tracking
was still not enough to settle it. What settled it was reading `glfw`'s
raw, unbuffered cursor position (`glfw.get_cursor_pos`, logged next to the
window size on every frame) directly from the running process — no
recording in between at all — followed by a decisive cross-check: the
identical corner-drag on another window entirely (Dolphin) tracked the
cursor with no trailing whatsoever on the same compositor and hardware,
which ruled out KWin/Wayland itself as the cause.

**The actual mechanism, found by reading `rendercanvas.glfw`'s own
source.** `_rc_gui_poll` calls `glfw.poll_events()`, which the library's
own comment documents as blocking "when the window is being resized" —
because it drains *every* pending native event before returning. Each
queued configure event fires `GlfwRenderCanvas._on_size_change`, which
synchronously calls `_time_to_paint()` — a full render — for every single
one, with **no coalescing at all**, despite the class's own comment on the
callback registrations claiming otherwise ("we may get notified too often,
but that's ok, they'll result in a single draw"). That claim holds for
backends where painting is scheduled through an event loop that naturally
collapses repeated requests; it does not hold here, where the call is
direct and synchronous. A fast drag can queue native configure events
faster than pySilver renders them, and the mouse-up event that ends the
drag sits in that *same* native queue, behind every one of them —
`poll_events()` will not return, and the app will not even see the
mouse-up, until the entire backlog has been rendered. That is a real,
measured behaviour, not a metaphor: the window keeps visibly resizing for
however long the backlog takes to drain, entirely independent of how fast
any single frame is.

This is why disabling `resize_bucket` (`PYSILVER_RESIZE_BUCKET=0`) made no
measurable difference when tested live — that lever controls the *cost* of
one render, not the *count* of renders queued up, and the two problems
turned out to be unrelated despite sharing a symptom.

**The fix rate-limits eager, input-driven repaints — `Engine.
_coalesce_resize_paints` — patched onto `GlfwRenderCanvas._on_size_change`
at the class level before any canvas is constructed.** It must be the
class, not the instance: `weakbind` (rendercanvas's own wrapper around the
glfw callback) captures the underlying function object at bind time, which
happens inside `GlfwRenderCanvas.__init__` — patching the instance
attribute afterward would silently do nothing, confirmed by hand before
writing the fix. The throttle caps eager repaints at 120 Hz
(`RESIZE_REPAINT_MIN_INTERVAL`), far above anything perceptible, which
bounds how large a backlog a burst of native events can force before the
input event behind it is delivered. `_determine_size()` still runs on
*every* notification, unthrottled, so the canvas's own size state is never
stale; only the eager `_time_to_paint()` call is rate-limited, and every
draw that does happen re-reads the size fresh, so a skipped intermediate
notification can never show as a wrong size — only ever one a later,
permitted draw in the same burst already supersedes.

**This is a different rule from the one the reverted throttle established
above, not a reversal of it.** That experiment was about declining a frame
the *compositor* explicitly asked for, and found that doing so caused
multi-second stalls because Wayland expects a client to commit in response
to a configure. This throttle never declines a compositor-requested
present — it only limits how often pySilver *itself* opportunistically
offers an extra one in response to raw, input-driven notifications arriving
faster than any display could show them. The two are easy to conflate and
worth keeping distinct.

`wp_viewporter` appears nowhere in wgpu-py, and `xdg_surface` geometry is not
reachable either — `glfw.get_wayland_window` does expose the raw `wl_surface`,
but GLFW owns the `xdg_surface` and fighting it for geometry is unnecessary now
that the size seam works. The residual upstream observation is narrower than
before: wgpu reconfigures on any size difference at all, and a toolkit that
wants coarse swapchains has to lie to it about the size to get them.

**X11 is not the way out, and that was tested rather than assumed.** GLFW can
be pointed at its X11 backend with a `PLATFORM` init hint, and under a Wayland
session that runs through XWayland. The obvious hope is that X11's lack of a
configure/commit handshake — the constraint that made the throttle backfire —
would help. It does the opposite. The same drag:

| | Wayland | X11 via XWayland |
|---|---|---|
| redrawn at a new size | **425/s** | 151/s |
| frame median | 1.94 ms | 0.18 ms |
| gap mid-drag median | 0.04 ms | 0.34 ms |
| surface errors | none | continuous |

The 0.18 ms frame is not speed: wgpu could not obtain a usable surface texture
and returned a dummy for runs of 5, 12 and 25 frames at a time, logging
`SuccessSuboptimal` throughout. Only 151 frames a second produced a visible
update. It would also *look* worse — wgpu notes that on Linux a suboptimal
surface is "blitted to the window leaving either part of the texture invisible,
or making part of the window black/transparent". No `platform` setting is
exposed, because its only non-default value is strictly worse.

**The diagnosis took four wrong turns**, each from reasoning past the data
rather than measuring the next thing: blaming the frame cost (it was 2 ms),
blaming vsync alone (throttled-and-vsync-off was still 12/s), concluding the
compositor's present was an immovable ceiling (it was 0.04 ms unthrottled),
and only then instrumenting the throttle itself — which showed declines
clustering within 16 ms of a present and then 85 ms of total silence, the
signature of a stalled handshake rather than a busy GPU. The lesson worth
carrying: a *gap between* our frames is not evidence about what happens inside
them, and "the platform is slow" is the hypothesis to test last, not first.

### 5.8.2 Shutdown

`Engine.close()` releases the GPU objects in the order the surface requires —
context, then the atlas texture and pipeline buffers, then the device — and
`run()` calls it in a `finally`. Not left to the garbage collector: rendercanvas
terminates GLFW from a class attribute's `__del__` *specifically* so it happens
late, because "the release of the surface should happen before the termination
of glfw" or the process segfaults (citing pygfx/pygfx#642). An `Engine` reached
from a module-level `App` — how every example here is written — outlives even
that, so closing the window destroyed the native window and left a live wgpu
surface pointing at it.

#### 5.8.3 Virtualised scrolling: not painting what the clip discards

Clipping is analytic and in-shader, so an instance wholly outside its clip
contributes nothing to the frame. Building it is pure waste, and on a long list
it is most of the frame: a 2000-row list in a 600px viewport cost **138 ms per
scroll frame** and emitted **52,891 instances** for the ten rows a reader could
see, because cost tracked the length of the data rather than the size of the
viewport.

`ElementMixin._culled` skips a subtree whose painted extent lies outside the
inherited clip. Measured after: **1.4 ms and 194 instances**, and the instance
count is *constant* in list length — 50 rows and 2000 rows both emit 194. The
residual growth in time (0.69 → 1.40 ms) is the walk itself: every child is
still visited and tested, so this is linear with a very small constant rather
than constant. Skipping the walk as well would need an ordering assumption
about children that the layout model does not make.

**A paint optimisation, not a different kind of list.** Content is still laid
out, so scroll extents, hit testing and the scrollbar are untouched and there
is no item-builder concept to adopt. It is also not an approximation: the
shader was already discarding this work, so the frame is identical — which the
golden suite passing unchanged is the evidence for.

Three things make it safe, and one of them was a bug first:

- **The extent is measured from what was painted**, never inferred from the
  element's size. A shadow reaches past its box, a focus ring sits outside its
  control, and a child may overflow its parent; a size-derived bound culls all
  three, and only near a viewport edge, which is the worst way to be wrong.
  Shadows are padded by the same formula the vertex stage uses for them.
- **Only a clean element is skipped.** The extent is exact while the content
  has not changed; position may change freely, which is the case that matters,
  since scrolling moves every row and changes what none of them draws. A dirty
  element repaints and re-measures rather than trusting a stale bound.
- **An extent measured while descendants were skipped is a lower bound rather
  than the truth**, and is refused. Without this the mechanism eats itself: a
  `Vertical` that painted four rows reports a four-row extent, and at the next
  scroll position that extent falls outside the viewport and takes the whole
  list with it. Found by watching a 60-row list paint one instance.

The first frame still draws everything, because the extent is measured *from* a
paint and there is nothing to cull against until one has happened.

#### 5.8.4 Image atlas packing

`ImageAtlas` (`render/atlas.py`) is `GlyphAtlas`'s counterpart for `Kind.IMAGE`
— built on the same `SkylinePacker`, with the same wholesale-eviction
contract, but **decode-agnostic**: it never opens a file or touches Pillow. A
caller decodes (`Image.open(...).convert("RGBA")` and `np.asarray`, already a
hard dependency) and hands over an `(h, w, 4)` uint8 array; the atlas only
packs, caches, and uploads. Deliberately not a shared base class with
`GlyphAtlas` — a glyph atlas rasterises through FreeType and keys on shaping
parameters, an image atlas keys on whatever identifies the source, and forcing
a common parent over that difference buys an abstraction for its own sake.

**RGBA costs four bytes a pixel against the glyph atlas's one**, so the same
default 1024² size costs 4× the VRAM: 4 MiB against 1 MiB. Stated rather than
left to be found by a memory profiler.

**Now wired into `Engine` and `App`, mirroring `TextEngine`/`GlyphAtlas`
exactly** (§5.22): `Engine` owns a device-bound instance bound to
`UIPipeline.bind_image_atlas` at construction and uploaded every frame;
`App` owns a CPU-only one, promoted to the device in `attach`. `Image`
(§5.22) calls `add`/`get_or_add` once per decoded file; `Video` (§5.23)
calls the later-added `update` every pushed frame instead, to avoid
thrashing the packer at frame rate; `Canvas` (§5.21) deliberately does
**not** call any of them — `image()` was left unbuilt there so this
convention got designed once, by `Image`, rather than twice.

**The atlas texture must declare `rgba8unorm-srgb`, and that is not a style
choice.** An image from a decoder is sRGB-encoded bytes, the same as
`materialyoucolor`'s output (§5.6.1). The render target is `rgba8unorm-srgb`,
which treats what it is given as linear and re-encodes on write. A plain
`rgba8unorm` atlas texture does no decode when sampled, so an sRGB byte would
be read as linear and then re-encoded — the identical double-encoding failure
§5.6.1 records for the palette, reappearing here for images and caught the
same way: measured, not theorised. A swatch written as `(0, 200, 0)` came back
as `(0, 229, 0)` with the plain format and `(0, 200, 0)` once the atlas texture
was declared `-srgb`, which makes `textureSample` decode it back to linear
before the fragment shader's `premultiply(texel * fill)` ever sees it. The
glyph atlas is correctly `r8unorm` with no `-srgb` variant: coverage has no
colour to decode.

#### 5.8.5 Considered and rejected: a general vector engine as the rendering layer

**ThorVG** (MIT; Godot vendors it, specifically as an SVG-to-texture *import*
decoder in `modules/svg`, not wired into Godot's own UI layout) was proposed as
the layer between pySilver and wgpu/GL/WebGPU — replacing this section's own
pipeline rather than sitting on top of it. **Rejected, deliberately, not on
sunk cost alone.** Benchmarked at pySilver's own scale (1000 rounded rects,
40×24, 8px radius, 1px border — the exact geometry `tests/bench/bench_paint.py`
already uses) via `thorvg-python` (ctypes, real wheels, LGPL-2.1), with the
mechanism verified against ThorVG's own C API docs rather than assumed:

- **Construction dominates, and it is backend-agnostic.** Building 1000
  `Shape` objects (create, configure, `canvas.add`) cost 5.74 ms — 91% of the
  cold-path total — against 0.56 ms to actually rasterise them, a number in
  pySilver's own ballpark (0.512 ms full-frame, §12.1). ThorVG's per-shape
  imperative API has no bulk-construction path; the cost is structurally
  identical to pySilver's own *rejected* scalar emit (3.3 ms/1000, over
  budget), not its adopted vectorised one (0.02 ms/1000). A better binding
  could cut ctypes overhead; it cannot invent an API ThorVG doesn't expose.
- **No incremental-update benefit, tested three times over.** A single shape
  changed among 1000 cost the same as redrawing all 1000, with
  `TVG_ENGINE_OPTION_SMART_RENDER` correctly enabled (verified via ThorVG's
  own C API docs that `EngineOption` belongs on `tvg_swcanvas_create`, not
  `tvg_engine_init` — an earlier attempt using the latter was invalid and is
  not the figure recorded here), in both a scattered and a clustered layout,
  and with the canvas scaled 64× in area while holding content fixed. Cost
  tracked total canvas area in every configuration, never the size of what
  actually changed. `SmartRender` is undocumented-as-supported on `GlCanvas`
  and explicitly documented as ignored on `WgCanvas` — of the three backends,
  only the one already tested claims to support it at all.
- **WebGPU batching is real, and excludes most of what pySilver draws.**
  Confirmed from ThorVG's own source (`tvgWgSolidBatch.cpp`): eligibility
  requires a solid fill (no gradient), convex geometry, **no clip**, **no
  stroke**, and consecutive submission at one viewport. pySilver propagates an
  ancestor clip through its whole element tree and uses borders constantly —
  the two things this rule excludes are two things pySilver's content does
  everywhere.
- **The backend is real but unreachable without new native work.** The
  `WgCanvas`/`GlCanvas` C++ classes are genuinely compiled into the shipped
  wheel (confirmed via `nm`, contradicting the wrapper's own docstring
  warning). Driving one for real needs an actual `WGPUTexture`, which needs
  either building ThorVG from source with confirmed WebGPU linkage or writing
  new interop code to extract wgpu-py's raw device pointer and hand it to a
  separately-linked backend of unproven ABI compatibility — precisely the
  category of work this project is not taking on now.

**What survives, unrelated to this decision:** ThorVG's `SwCanvas` for
rasterising vector *content* — SVG art beyond the icon subset, and Lottie —
into a bitmap that then flows through §5.8.4's image atlas like any other
image. That is a one-shot or per-animation-frame cost paid by content that
needs it, not a per-UI-frame tax on everything, so none of the above bears on
it: SW's construction cost is irrelevant for one icon, its
lack-of-incremental-redraw is irrelevant for a job that already runs once, and
the GPU-interop wall does not need crossing to get a `PIL.Image` out of a
`SwCanvas`.

Revisit a general vector engine once the project is stable enough to justify
designing a pluggable rendering backend around one — not as a drop-in swap for
this section's own pipeline, which none of the above showed a need to replace.

#### 5.8.6 A zero-size clip means *unclipped*, not *hidden*

`ui.wgsl` applies a clip only when **both** dimensions are strictly positive:
`if (clip.z > 0.0 && clip.w > 0.0)`. Either one being zero — not both, just
one — reads as "no clip at all", the same as the display list's own
`(0, 0, 0, 0)` sentinel for an element with no ancestor clip. This is fine for
every clip a widget computes directly from its own size, since a real
control's own rect never has a zero dimension. It stops being fine the moment
a clip is computed by **intersecting** two rects, because `Rect.intersect`
correctly floors a no-overlap result to an exact zero in the degenerate
dimension — mathematically right, and silently read by the shader as "draw
this anyway."

Found twice from the same root cause, in both cases by rendering a real frame
rather than trusting the clip math: `TreeItemElement.child_paint_context`
intersects a collapsed ancestor's clip with each descendant's own rect
(§5.12's `TreeView` entry), and `DockPanelElement.child_paint_context` needs
to hide an inactive tab's content outright (§5.20). Both produced a
mathematically correct zero-height clip for "this must not be visible", and
both leaked the hidden content onto the actual rendered frame because that
zero satisfied the shader's own definition of "unclipped". The existing unit
test for the `TreeView` case (`test_collapsing_an_ancestor_clips_every_
descendant`) had the identical bug in its own `visible()` helper — it only
special-cased the exact `(0, 0)` sentinel, not "either dimension zero" — so
it reported the broken behaviour as passing. A golden render at a taller
canvas than the original (`tree_view_deep_collapse`) is what actually caught
it: the earlier canvas happened to crop the leaking content by coincidence,
which is why this survived one full "verified" ship cycle.

**The fix in both places is the same shape**: never emit a clip whose width
or height is exactly zero when the intent is "hide this". Each hiding path
floors the degenerate dimension to `HIDDEN_EXTENT` (`0.01`, in already-scaled
physical px) — real enough to satisfy the shader's `> 0.0` gate, small enough
that no rasterised fragment can land inside it. This is not a new primitive
or a new clip *format*; it is the one extra `max(value, HIDDEN_EXTENT)` an
intersection-based clip needs that a size-based one never does.

### 5.11 The accessibility tree — `runtime/accessibility.py`

`App.accessibility_tree()` snapshots what the interface *means*: roles, names,
descriptions, values, states and bounds, derived from the element tree on
demand. Built when asked rather than maintained, because nothing consumes it
per frame and a tree rebuilt on request cannot go stale.

**The bridge is optional and lives in `accesskit_bridge.py`.** AccessKit owns
the per-platform half — AT-SPI over D-Bus on Linux, UIA on Windows,
NSAccessibility on macOS — so pySilver does not. It is a native wheel, so it is
an extra (`pip install 'pysilver[a11y]'`) and an application opts in with
`App.bind_accessibility`. Without one bound, nothing reaches a screen reader.
Today's build serves AT-SPI; `available()` returns a *sentence* rather than a
bool, because "not available" with no reason is the least useful thing an
accessibility feature can say.

**Verified against the live accessibility bus**, not just unit-tested. With
`org.a11y.Status.ScreenReaderEnabled` set true, the gallery appears in the
AT-SPI registry and its window object reports `Name: 'pySilver gallery'` with
its content beneath. Three things only that exercise could have found:

- **AccessKit stays dormant while nothing is listening.** With no screen reader
  the adapter never registers, which is `update_if_active` doing its job and is
  why a per-frame push costs nothing.
- **The tree's root must be a `WINDOW` carrying the title.** Handing AccessKit
  our own root — a `Vertical`, which converts to `GROUP` — left AT-SPI listing
  the application as `python3.14`, the process name, for want of anything
  better. The bridge now wraps the view in a titled window node.
- **The adapter must be shut down deterministically.** AccessKit runs a D-Bus
  task that calls back into Python, and left alive at interpreter shutdown it
  panics — "The Python interpreter is not initialized", from pyo3's GIL
  handling. Exactly the shape of the wgpu surface outliving its window (§5.8.2).
  `AccessKitBridge.close()` drops it and `App.run` calls it in a `finally`; a
  test suite that leaked one took the whole run down at exit, which is how this
  was found.

**Actions cross a thread boundary.** A reader activating a button calls back
from AccessKit's D-Bus task, and pySilver's signals are thread-affine — acting
there raises `ThreadAffinityError`, the guardrail working. Requests are queued
and `App.update` drains them on the engine thread. A bridge that could only
*read* would be half a feature: announcing a button nobody can press is not
access.

The tree is worth its keep with or without a bridge: it is what the bridge is
handed, and it lets a test ask for "the button named Confirm" instead of for a
rectangle.

**Roles are sourced where M3 states one**, which is rarely: "The role is
'textbox'", the "role of 'progressbar'", a list is a "List box" so its items
are options, a navigation item's "role is 'tab'", and a navigation container's
"role is not announced". Everything else is the conventional ARIA role and is
marked as convention, so a reader can tell a quotation from a judgement. A test
asserts that every `WidgetKind` is either mapped or explicitly silenced, so a
new widget cannot quietly default to "group" — the role that says nothing.

Three rules the tree enforces, each of which is a bug it prevents:

- **A view file's `name:` is never announced.** It is a developer handle;
  "sw_primary" read aloud is worse than silence. It travels as `key` so tests
  can still find a node by it.
- **An icon name is never announced.** For `IconButton`, `Fab` and `NavItem`,
  the accessible name comes from `label:` rather than `text:` — a navigation
  item announced itself as "home" rather than "Home" back when `text:` did
  double duty as the glyph name, until a test caught it. `text:` no longer
  carries anything for these widgets at all (their glyph moved to `icon:`),
  and an icon-only control with no `label:` reports *no* name, which is a
  real gap in the view rather than something to paper over.
- **Silent nodes do not bury their children.** A `Spacer` disappears and a
  navigation container's items are lifted into its place, so a reader never
  walks through a level that says only "group".

### 5.9.1 Editable text — `text/editing.py`, `widgets/textfield.py`

`TextField` is the only widget that *owns* state rather than reading it, which
is why the split runs where it does. **`text/editing.py` holds every rule and
knows nothing about pixels**: what a backspace removes, where a word ends, when
two keystrokes are one undo step. All of it is testable without a window, a
font, or a GPU, and a test that had to open a canvas to check Ctrl-Backspace is
a test nobody runs.

An `EditState` is frozen — text, anchor, focus — so an operation returns a new
one and **the undo stack is a list of states, not a list of inverse
operations**. At the sizes a field holds that is cheaper as well as simpler: no
operation needs an inverse, and no inverse can be subtly wrong. Anchor and
focus rather than start and length, so shift-arrow knows which end to move and
a backwards selection is representable instead of normalised away.

Every offset sits on a **grapheme cluster** boundary, reusing the segmenter
selection already went through. Backspace removes an accented character rather
than its accent. Word boundaries are the whitespace rule `selection.word_at`
uses, not UAX #29 — asserted equal to it in a test, because double-clicking a
word and then Ctrl-Backspacing it taking different amounts of text would be a
genuinely baffling bug.

Typing coalesces into one undo step, broken by a caret move, a replaced
selection, or a different kind of edit. A bound `value:` changing from the
application clears the history instead of recording a step: that text did not
come from the user, so offering to undo back to what they typed would restore
something the application has already moved past.

The widget half is the parts that need pixels. Its vertical layout is the
sourced M3 figures tiling the container exactly — 8dp padding, a 16dp floated
label line, a 24dp input line, 8dp padding, summing to the specified 56dp — and
a test asserts the sum so that changing one figure cannot silently decentre the
input. The label animates between `body-large` and `body-small` off one
animation value, so it cannot be caught half-floated in size and settled in
position. A field is one line and scrolls sideways to follow the caret, and
back rather than leaving empty space when text is deleted.

Two things it does not do. The **outlined** variant cannot notch its border,
because the shader draws no notch: the floating label gets a `surface`-coloured
patch behind it instead, which is wrong if the field sits on a tinted
container, and is stated at the call site rather than hidden. And the caret
**stops blinking under `reduce_motion`** rather than blinking on — the setting
makes timed transitions arrive at once everywhere else, and the equivalent for
something that never arrives is to stop it moving.

### 5.9.2 Hit rects are not paint rects

A control may accept clicks in an area larger than the one it draws. Two style
properties say so: `hit_padding` grows each edge, and `min_hit_size` states a
minimum square, which is how M3 writes the rule it actually cares about — "at
least 48×48dp" stays correct when the control's size changes, where 15dp of
hand-computed padding does not. Neither affects layout or paint: the control
keeps its size, its neighbours keep their positions, and the display list is
byte-identical.

Three consequences, each of which had to be handled rather than assumed away:

- **A hit rect can leave its parent.** The old walk returned early from any
  element that did not contain the point, which is correct only while a child
  cannot reach past its parent's edge — precisely the edges an enlarged target
  exists to cover. Each element therefore caches `_hit_overflow`, the furthest
  any descendant's hit rect can reach beyond its own, and descends into that
  wider region while still *accepting* only within its exact rect.

  That cache only ever has to be an **upper bound**. Too large costs a little
  wasted recursion and can never produce a wrong answer, which is what makes it
  safe to grow the value up the ancestor chain and never shrink it — instead of
  tracking invalidation for a property that changes about as often as a view
  file is edited. Recomputing the union per pointer move would put an O(n) walk
  on the most frequent event there is.

  The reach is therefore **pushed up at layout time by the few elements that
  ask for a target**, rather than pulled down by every element polling its
  children. An element with neither property does two attribute loads and
  stops. The first version did poll, and read the properties off the pydantic
  spec inside `hit_test`; measured against the gallery that cost +17% on a
  layout pass and +54% on a hit test. The version that ships costs +3% and +8%
  — a hit test is ~7µs against a 16ms frame, and it is stated here because
  "some overhead" is not a number.

- **A widget that clips what it paints must clip what it hits.** `ScrollView`,
  `Carousel`, `CarouselItem` and `SegmentedButton` set `CLIPS_CHILDREN`, so a
  control scrolled just past the edge cannot take a click it has no way to show
  a response to.

- **Enlarged targets can overlap where the drawn controls do not.** M3 asks for
  8dp between targets and nothing here can enforce it. The tie breaks the same
  way overlapping paint does: reverse sibling order, so the one on top wins.

The entire drain runs inside one signal `batch()`, so a handler writing several signals triggers dependent work once rather than once per write.

Dispatch follows a **capture → target → bubble** path over that hit path, with `Event.stop_propagation()`. Beyond raw clicks the system provides:

- **Pointer capture** — a widget may capture the pointer on press so drags continue outside its bounds.
- **Enter/leave** — computed by diffing the current hit path against the previous one.
- **Focus tree** — a tab-order traversal derived from document order, with `Tab`/`Shift-Tab` and focus-visible state.
- **Text input** — GLFW `char` callbacks for committed text, delivered as `EventType.TEXT` to the focused element. IME preedit is a known gap (§13).

**Modifier names are normalised on arrival.** `rendercanvas` reports GLFW's spellings — `"Control"`, `"Shift"`, `"Alt"`, `"Meta"` — and matching a raw string against one spelling is how Shift+Tab back-traversal and `Text`'s Ctrl+A both came to be dead in a running window while their tests passed: the tests posted `"shift"` and `"ctrl"`, which GLFW never sends. `modifiers_of()` folds every spelling to one vocabulary and `is_accelerator()` answers "is the platform's shortcut key held" without branching on platform. Both bugs were found while wiring the text field, and the tests for it deliberately use GLFW's spellings.

Handlers named in YAML (`on_click: submit_form`) resolve against a registry the application populates by decorator:

```python
@app.handler
def submit_form(event: PointerEvent) -> None: ...
```

Resolution happens at load time, so a handler named in YAML but absent in Python is a startup error.

### 5.10 Engine and the frame loop — `runtime/engine.py`

**The prior plan's hand-rolled loop is removed.** `rendercanvas` already owns a scheduler that does precisely what that loop attempted, and running `glfw.poll_events()` alongside it double-pumps the event queue.

Concretely, `rendercanvas` supplies:

| Prior plan | rendercanvas equivalent |
|---|---|
| `while not canvas.is_closed()` | `loop.run()` from `rendercanvas.asyncio` |
| `glfw.poll_events()` | Handled internally by the canvas group |
| `self._is_dirty = True` | `canvas.request_draw()` |
| `await asyncio.sleep(1/60 - elapsed)` | `update_mode="ondemand"`, `max_fps=60` |
| Idle redraw suppression | `min_fps=0` — genuinely zero frames when idle |

The engine's job is consequently much smaller: own the four trees, install the draw callback, drain the event queue, and run the frame pipeline.

```python
canvas = RenderCanvas(
    title="pySilver",
    size=(1024, 768),
    update_mode="ondemand",  # draw only when requested
    min_fps=0,  # true idle: no frames at all
    max_fps=60,
)
adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
device = adapter.request_device_sync()
canvas.request_draw(engine.draw_frame)
loop.run()
```

`power_preference` is `"high-performance"`, not `"low-power"`: on hybrid-GPU laptops `"low-power"` selects the integrated GPU, which is the correct default for a compositor but the wrong one for a framework that must handle full-window resizes at 60fps. It is exposed as configuration.

`wayland_decorations` chooses who draws the window frame. `"auto"` leaves it to GLFW, which prefers libdecor — client-side decorations drawn by a plugin — and is the default because it is the only thing that works everywhere: GNOME does not offer server-side decorations for xdg-shell, so disabling libdecor there leaves a window with no title bar and no close button. `"server"` disables libdecor before GLFW initialises, which on a compositor that does offer server-side decorations (KDE Plasma) avoids the libdecor path entirely, including the `Failed to load plugin 'libdecor-gtk.so'` fallback a missing GTK produces. It must be set before `glfw.init()`, and rendercanvas defers that until the first canvas is constructed, so `_make_canvas` is the last moment it can take effect.

It is **not** a performance setting, and measurement says so: the same drag under both modes gave a 4.30 ms and a 4.17 ms median frame, the same p95 band, and one over-budget frame each. libdecor was never the cost.

### 5.11 Hot reload — `runtime/hotreload.py`

`watchfiles` runs in a background thread. On a change to a watched YAML file it posts a reload request to the engine thread — it never touches the trees itself.

The engine then: re-reads and re-validates the Spec tree; **on validation failure, logs the Pydantic error with file and line and keeps the previous tree running** (a syntax error mid-edit must not kill the app); on success, reconciles (§5.3), preserving all runtime state for nodes whose `id` and widget kind are unchanged; and requests a draw.

Handler *bindings* are re-resolved, but handler *bodies* are not reloaded — that is Python-level reload and is out of scope (§1.2).

### 5.11.1 Focus rings and keyboard traversal

M3 requires a focused element to render a **2dp high-visibility stroke around
its boundary**. On a pointer-and-keyboard framework this is not cosmetic:
keyboard traversal is a primary input path, so an invisible focus state is a
defect (§1.2.1).

Three decisions:

- **Drawn once, centrally.** `ElementMixin.paint()` emits the ring after the
  element's own subtree, so it lands on top and every focusable widget gets a
  correct ring without opting in.
- **`focus_visible` is separate from `focused`.** A mouse click focuses
  *silently*; Tab shows the ring. This is standard desktop behaviour, and
  without the split every click leaves a ring behind, which reads as a bug.
- **The ring follows the control's shape**, via `Element.effective_radii`.
  `style.corner_radius` is not enough: several components compute their own
  radius at paint time — a Button is a pill at height/2 when the view sets
  none — so a ring keyed on the raw style draws a rectangle around a circle.

`Tab` and `Shift+Tab` traverse the focus order, and `Escape` clears focus. Tab
is handled before delivery to the focused element, so it works from the
nothing-focused state an application starts in. Focus order is document order,
and `FOCUSABLE_KINDS` makes every interactive control reachable whether or not
the view file wired a handler.

### 5.1.0 Node identity: `id`, `name`, and `classes`

Three separate concerns that were once a single overloaded `id` field:

| Field | Written by | Cardinality | Purpose |
|---|---|---|---|
| `id` | **the loader** | unique | Positional identity, derived from the node's path (`/0/1/`). Never authored. |
| `name` | the designer, optionally | unique | The handle: `find()`, `anchor:`, a selection `value:`, and the reconciliation key. |
| `classes` | the designer, optionally | **repeatable** | Categories for the theme engine and stylesheet to select on. |

**Why the split.** Requiring an `id` on every node meant naming things nobody
referenced — the gallery declared 58 ids and referenced none of them by
`anchor:` or `find()`. Meanwhile a *category* (several buttons that should
style alike) and an *identity* (this specific button) are genuinely different
needs, and one field cannot be both: a repeatable value cannot be a lookup key.

**The reconciliation rule follows from it, in one line:**

> A **named** node has stable identity and keeps its state across a reorder.
> An **unnamed** node has positional identity: its state stays with the *slot*,
> not with the content that moved.

That second half is the honest cost, and it is precise — an unnamed node is not
rebuilt on a reorder, it is reused in place and handed the other node's spec.
For a `Divider` that is meaningless; for anything holding focus, scroll, or
text, it is exactly why you give it a name.

Positional ids use `/` as a separator, which the `name` pattern forbids, so an
authored name and a generated id can never collide.

**Uniqueness is enforced at load**, not merely documented. A duplicate name does
not fail loudly on its own — `find()` just returns whichever node was reached
first — so the loader walks the validated tree and rejects a collision with both
positional ids in the message (`duplicate name 'badge' (used at /6/1/ and
/8/8/)`). The gallery had exactly this bug: a `Badge` widget and an unrelated
`Container` both named `badge`. At load it is a one-line fix; at runtime it
looks like a widget mysteriously ignoring its handler.

`classes` was added before it had a consumer, deliberately: retrofitting a
selector target into a shipped view language costs far more than reserving one.
The stylesheet (§5.17.1) is that consumer, and it landed without changing the
identity model at all — which is the argument for having reserved it.

### 5.1.1 View composition — `spec/include.py`

A `source:` key pulls a subtree in from another file:

```yaml
# parts/confirm.yaml
params: [title, open]
id: dialog
widget: Card
open: "{{ open }}"
children:
  - {id: heading, widget: Text, text: "{{ title }}"}

# call site
overlays:
  - id: delete_confirm
    source: parts/confirm.yaml
    with: {title: "Delete file?", open: "{{ show.get() }}"}
```

**Resolution happens on the decoded YAML, before validation.** A resolved
include is therefore indistinguishable from inline content: the spec models,
reconciliation, and the renderer never learn a file boundary existed. That is
why this feature needed no changes below the loader.

**Parameters are the interface; there is no merge.** A `source:` node accepts
only `id:` and `with:`. The alternative — letting the call site override keys —
needs precedence rules nobody can predict ("does a local `style:` replace the
fragment's or merge into it?"). The cost is real and worth stating: *everything*
a call site needs to control must be a declared parameter, including `open:`.
In exchange there is nothing to memorise.

**Parameters substitute textually**, which is what makes them compose with
bindings. Passing `title: "Delete?"` leaves static text; passing
`title: "{{ user.get() }}"` leaves a live template evaluated against the
application context. No separate reactive path exists or is needed.

Four things this had to get right:

- **Name namespacing.** Positional ids are inherently scoped by path, but
  `name`s are not: including a fragment twice would give two nodes the same
  name, and `find()` would return the wrong one. Names inside a fragment are
  qualified with the call-site name (`delete_confirm.heading`), and `.` is
  reserved in the name pattern for exactly this.
- **Hot reload watches the whole graph.** `App.sources` records every file
  touched, and **a change to any of them reloads the entry view** — not the
  file that changed, which is not a view on its own and would fail on its
  `params:` block.
- **Error provenance.** Failures report the include chain
  (`a.yaml -> b.yaml -> a.yaml`), not just a line number.
- **Cycles and path confinement.** A cycle is refused with its chain, and an
  include may not escape the view directory — view files are untrusted input.
- **The walk is scoped to actual widget-tree keys.** Found in the 2026-09
  gallery rebuild: `_walk` used to check *every* dict in the decoded YAML for
  a `source` key, recursing into every value regardless of what field it lived
  under. `EdgeSpec` (`NodeGraph.edges:`) has its own `source`/`target` fields
  — unrelated to view composition — and a `{source: "a.out", target: "b.in"}`
  entry was misread as an include, failing with a confusing "included file not
  found" naming the port string as a path. No existing test caught it because
  every `NodeGraph` test builds its spec as a Python dict directly, bypassing
  `load_view`/`resolve_includes` entirely. `_walk` now only recurses into
  `root`, `children`, `overlays`, and `styles` — the only keys that can hold a
  widget-tree node — mirroring the restriction `stamp_view` already applied
  for the same reason. `style:`, `handlers:`, and any future per-widget data
  field are now correctly opaque to the include walk.

Deliberately absent: conditional includes, computed paths, and loops. This is
where a view format starts becoming a programming language. In particular
**includes are not the way to repeat a row a hundred times** — that needs a
`repeat:` construct with stable identity for reconciliation, which is a
separate and larger decision.

### 5.13 The overlay layer — `runtime/overlay.py`

Six M3 components — Dialog, Menu, Tooltip, Snackbar, and both Sheet types —
share one requirement the four-tree model cannot otherwise express: they render
**above** everything, positioned independently of whatever opened them and
clipped by nothing.

**Overlays are declared in a top-level `overlays:` list, not hoisted out of the
tree.** A dialog is not laid out or clipped by the button that opened it, so
declaring it as that button's child would be a lie about the geometry — and
would leave the parent's Flex reserving space for something that floats.

```yaml
root: { ... }
overlays:
  - name: confirm
    widget: Dialog
    open: "{{ show.get() }}"          # templated, like text: and value:
    style: { modal: true, scrim: true }
```

The host runs its own layout and paint pass after the main tree's, and is
consulted **first** during hit testing because it is on top.

| Concern | Behaviour |
|---|---|
| Placement | `center`, `anchor` (to another element's `name`), or an edge |
| Anchoring | placed below the anchor, **flipping above** when it would overflow |
| Scrim | M3's 32% `scrim` token, sized to the window |
| Modality | a modal swallows every press outside itself; the tree beneath is unreachable |
| Dismissal | Escape closes the topmost overlay *before* clearing focus; a press outside closes a modal |
| Z-order | declaration order — a later overlay's scrim dims an earlier one |

Dismissals are tracked separately from the `open:` binding and reconciled each
frame, so an overlay closed by clicking outside can still be reopened by its
signal — otherwise the dismissal would outlive the state change.

#### 5.13.2 Fading, and why rendered ≠ visible

Overlays enter and leave on M3's own pairs: **Emphasized decelerate over 400ms
to enter, Emphasized accelerate over 200ms to exit**, straight from the
suggested-pairs table. A thing arrives gently and departs briskly, which is why
the two are not symmetric.

Fading out forces a distinction the host did not previously need:

| Set | Contains | Used by |
|---|---|---|
| `visible()` | overlays the application wants up | hit testing, modality, dismissal |
| `rendered()` | those, **plus any still fading out** | layout and paint |

A dismissed modal must stop swallowing clicks the instant it is dismissed, not
200ms later, so it leaves `visible()` immediately while remaining in
`rendered()` until its exit finishes. Clicking through a half-faded dialog is
the deliberate consequence.

**Opacity is applied to the display-list slice**, not threaded through the
paint context. The host records the index before painting an overlay and scales
`fill.a` and `border.a` across everything emitted after it — one vectorised
numpy pass, in one place, instead of obliging every emit site to multiply. It
also catches a **cached subtree**, which is spliced in at full alpha and which
a context flag would have missed entirely, and the **scrim**, which the host
draws itself rather than the widget.

#### 5.13.1 Placement a component does not have to declare

`placement:` defaults to `center` for every widget, which is wrong for most of
the components that actually float: a widget named `BottomSheet` should not
have to be told it belongs at the bottom. Two rules fix that without taking
control away from the view, resolved in `ElementMixin.resolved_placement`:

1. An explicit `placement:` always wins. "Explicit" is decided by pydantic's
   `model_fields_set`, so a written `center` is distinguishable from the
   field's default of `center` — which a plain equality check cannot do.
2. Failing that, an `anchor:` implies `placement: anchor`. Naming an anchor and
   then centring the overlay is never what was meant.
3. Failing that, the component's own `DEFAULT_PLACEMENT`: `bottom` for
   Snackbar and BottomSheet, `right` for SideSheet, `center` for Dialog.

**Docked versus floating.** A sheet sits flush against its window edge; a
snackbar, menu or tooltip keeps an 8dp margin from it. This is not decoration:
M3 rounds only a sheet's *inner* corners, and a gap outside a square corner
leaves it hanging in mid-air. Components set `DOCKED` and the host drops the
margin for them.

Two bugs this work surfaced, both pre-existing and both now fixed:

- **A single-child container silently dropped extra children.** `Padding`-based
  widgets lay out `children[0]` only, but paint walks all of them — so a Card
  with two children rendered them unpositioned on top of each other with no
  error. Adding a second child now raises, naming the fix.
- **A Vertical sized only on `width` filled vertically.** `main_size` was chosen
  from `style.width` regardless of axis, and a Vertical's main axis is its
  *height*. An anchored menu stretched to the bottom of the window.

And one surfaced by building the components on top of it:

- **M3 minimum widths violated their constraints.** A Menu clamped itself to
  its 112dp minimum regardless of the space offered, so a Menu laid out in
  50dp raised outright (`layout/node.py` asserts that a node returns a size its
  constraints permit) while a Dialog was silently clipped. An M3 minimum is an
  aspiration that yields to a narrower parent, not a floor — see
  `_clamped_width`.

#### 5.13.3 Submenus: an anchor that lives inside another overlay

A `MenuItem` opens a submenu by naming itself as the *anchor* of a second
`Menu` overlay, declared after it — no new widget kind, since a submenu is
just another `Menu` with an unusual anchor target. Two consequences of that
target being a `MenuItem`, both handled in `_anchored`:

- **The lookup falls back past `root`.** `root.find(name)` only ever finds
  things in the main tree; a submenu's trigger lives inside its *parent*
  overlay's own element tree. `_anchored` now tries `self.find(name)` — which
  already searches every overlay, for handler resolution — when `root` comes
  up empty. `style.has_submenu` is the item's own visual affordance (a
  trailing `chevron_right` in place of `supporting_text`) and is unrelated to
  this lookup; nothing stops any overlay from anchoring to any `MenuItem`.
- **Positioning switches to beside rather than below.** M3: "Submenus should
  open next to the parent menu item without overlapping it." `_anchored`
  checks the resolved target's own kind and routes to `_anchored_beside` —
  the same flip-on-overflow shape as the below/above case, on the other axis.

**A real one-frame bug this surfaced, now fixed.** `entry.element.offset` used
to be set only in `paint`, never in `layout`. `absolute_rect()` for anything
inside an overlay bottoms out at that overlay's root offset (a root has no
parent to compose a position from), so a submenu opening on the *same* frame
its parent first appears anchored against the parent's stale — or, on a
brand-new entry, zero — offset for exactly one frame, before snapping to the
correct position once `paint` ran. `layout` now sets `element.offset` itself,
immediately after `_place` resolves it, so a later entry in the same pass sees
an up-to-date position from an earlier one. This is why a submenu must be
declared **after** the menu it anchors into: entries are placed in declaration
order, and `main` needs its own offset set before `sub`'s anchor lookup runs.

### 5.12 Material Design 3 components — `widgets/material.py`, `navigation.py`, `overlays.py`

Components translated from their M3 specs. Dimensions are M3's own dp
figures used directly, since layout runs in logical units and dp maps 1:1 (§7).

| Widget | M3 spec | Notes |
|---|---|---|
| `Card` | 12dp radius, 16dp padding | `elevated` / `filled` / `outlined` |
| `Divider` | 1dp, `outline_variant` | `full_bleed` / `inset` |
| `Checkbox` | 18dp box, 2dp radius | checkmark glyph when selected; `indeterminate:` (M3's third state) swaps it for a dash, taking precedence over `value:` for which glyph paints but not changing `value:` itself |
| `Radio` | 20dp outer, 10dp dot | a circle is a rounded box at radius = side/2 |
| `Switch` | 52×32dp track, 16/24dp thumb | thumb grows when selected. M3's own interaction table names both "Tap" and "Drag"; tap already worked for free (the dispatcher's own generic click rule needs no widget-specific `on_click`), but dragging past the track's far edge needed `on_pointer_down`/`_up` added to recognise it as a distinct gesture and commit to that side |
| `Chip` | 32dp high, 8dp radius, 18dp icon | filter variant shows a leading checkmark |
| `IconButton` | 40dp container, 24dp icon | `standard` / `filled` / `filled_tonal` / `outlined` |
| `Fab` | 56dp standard, 40 small, 96 large | `primary_container`, elevation level 3. `variant: extended` (`COMPONENT_EXTENDED_FABS.md`) is the fifth size: 56dp tall like `standard` but a dynamic width (80dp floor) fitting an icon plus a `label:` label, 16dp padding, 8dp gap between them |
| `Badge` | 6dp dot, or 16dp-high pill | `value:` carries the count |
| `SpinBox` | Two 40dp `IconButton`-anatomy regions (`remove`/`add`) flanking a number | No M3 component; named to dodge M3's own "Stepper" (a multi-step flow indicator). Grounded in the Sliders page's "icon buttons placed outside the slider" convention instead. `on_change` carries the new value already clamped to `style.min`/`max` and stepped by `style.step` |
| `Pagination` | 40dp prev/next arrows around 40dp page-number buttons | No M3 component — "pagination" appears once in the whole reference library, as a prohibition on Cards. Windows around the current page, collapsing runs into `...`; below 8 total pages nothing is ever collapsed. The current page uses `Chip`/`Segment`'s own selected pairing (`secondary_container`/`on_secondary_container`) |

**Wave 2** added navigation and structure in `widgets/navigation.py`:

| Widget | M3 spec | Notes |
|---|---|---|
| `NavigationRail` + `NavItem` | collapsed: 80dp, 56×32dp indicator. Expanded: 240–360dp, 56dp items, 28dp pill | icon FILL 0→1 marks the active destination. `collapsed:` (`WidgetSpec`, not `style` — `style.width` is a load-time value, confirmed not `{{ }}`-bindable; default false, so an unset rail starts expanded) animates continuously between the two widths (`animated(..., invalidates="layout")`, the same pattern `Accordion` uses), never hides the widget — M3 Expressive folded the old, separate `NavigationDrawer` into this widget's own expanded state ("the expanded nav rail is meant to replace the [modal] navigation drawer"), so there is no longer a second widget kind. `NavItem`'s row-vs-stacked anatomy *swaps*, not morphs, at the transition's halfway point — the same "swap don't interpolate" precedent `Accordion`'s chevron already establishes for a shape change with no continuous parameter |
| `TopAppBar` | 64dp small, 112dp medium, 152dp large | medium and large collapse on scroll (§5.19) |
| `StatusBar` | 24dp, `surface_container`, 16dp horizontal padding | no M3 component, and the phrase does not appear anywhere in M3's own vocabulary either; the docked *toolbar* is a different thing (action buttons, not information). Fixes a real gap `TopAppBar` shares: extending `Flex` directly, not `_FlexElement`, means a `Spacer` styled `width: expand` is invisible to the base `flex_of` and starves whatever comes after it — `StatusBar` overrides `flex_of` to recognise it, the same way `_FlexElement` already does for `Horizontal`/`Vertical` |
| `Tabs` + `Tab` | 48dp, 3dp indicator; 64dp when any tab has an `icon:` (24dp; `style.icon_position` is `stacked` (default, above the label) or opt-in `leading`/`trailing` (beside it, 8dp gap) -- every tab in the bar shares the taller height regardless, `TabsElement` stretches icon-less siblings to match via `CrossAxisAlignment.STRETCH`) | primary rounds the indicator, secondary is flat. A `Tab`'s optional `badge:` (`style.badge_variant`: `numbered` (default) or `dot`) either overlaps a stacked icon's own top-right corner (6dp, no width change) or trails the whole content block with a 4dp gap when there's no stacked icon to overlap (widens the tab) -- reuses `Badge`'s own sizing constants and `error`/`on_error` tokens rather than re-deriving them |
| `SegmentedButton` + `Segment` | 40dp, 20dp outer corners | checkmark on the active segment. `style.multi_select` (M3 names both a single- and multi-select form) is `_SelectionContainer.apply_selection`'s own shared switch -- `value:` becomes a comma-separated set instead of one name, off by default so `Tabs`/`NavigationRail` (which share the same base class but have no M3 multi-select form of their own) are unaffected |
| `ListItem` | 56 / 72 / 88dp | headline plus bindable `supporting_text` |
| `Accordion` | 56 / 72dp header, `ListItem`'s anatomy | M3 has no component for this — only Lists' "expand and collapse" behaviour statement; disclosure state is `value:`, animated height reveal clipped like `ScrollView`, chevron **swaps** `expand_more`/`expand_less` rather than rotating (a glyph instance has no rotation parameter) |
| `TreeView` + `TreeItem` | Accordion's mechanism, recursive | same M3 gap, same reveal/clip/chevron-swap machinery, applied to a `TreeItem` that nests further `TreeItem`s; a leaf has no chevron. Two things a single level of nesting never needed: per-level **indentation** (one chevron-width per depth, not M3-sourced — no tree page exists to source it from) and a **clip that intersects its ancestor's** rather than replacing it, since — unlike Accordion or `ScrollView` — a tree item is routinely nested inside its own kind, so collapsing a node must hide every descendant regardless of which of them are individually expanded. The intersection's own degenerate case needed a further fix, covered in §5.8.6. `TreeView` generalises `_SelectionContainer`'s `value:`-names-the-selected-child shape to select at any depth |
| `LinearProgress` | 4dp, rounded ends | both determinate and indeterminate; omitting `value:` selects the indeterminate animation (shipped in M7, §5.17) |
| `CircularProgress` | 4dp ring, clockwise from 12 o'clock | both determinate and indeterminate, same `value:`-omitted convention; needs the arc primitive (§5.15). The 48dp default diameter is **not** sourced — that page's size table is an image |
| `Carousel` + `CarouselItem` | 28dp items, 16dp leading/trailing, 8dp gaps | three layouts; items resize and snap (§5.16). Drag-to-scroll (`on_pointer_down`/`_move`/`_up`) is additive to the existing wheel support -- M3's own guidelines describe moving through a carousel as swiping, and a pointer drag is that gesture's direct-manipulation equivalent |

**Wave 3** added the six components the overlay layer (§5.13) exists for, in
`widgets/overlays.py`. They contribute M3 *anatomy* only — container token,
shape, and the padding between the parts — because the host already owns
placement, scrim, modality and dismissal. A Dialog does not know it is centred.

| Widget | M3 spec | Notes |
|---|---|---|
| `Dialog` | 28dp radius, 24dp padding, 280–560dp wide, height **dynamic** | headline + `supporting_text` + actions as its child; optional `icon:` (24dp, `secondary`) centres itself and the headline as a column -- confirmed against the actual M3 annotated example, fetched live, that the supporting text stays start-aligned regardless |
| `Popover` | M3's persistent rich tooltip; 12dp radius, max 320dp, **shrink-to-fit** width | subhead + `supporting_text` + actions as its child; `surface_container_high`; defaults to `placement: anchor` |
| `Menu` | 4dp radius, 112–280dp wide, 8dp vertical padding | `surface_container` |
| `MenuItem` | 48dp high, 12dp side padding | denser than `ListItem`'s 56/72/88dp; `supporting_text` is the trailing shortcut. Optional `icon:` (24dp leading icon, `on_surface_variant`, `COMPONENT_MENUS.md`'s own "List item leading icon" anatomy) needed no schema change — already a generic `TEMPLATED_FIELDS` entry from the earlier Icon/IconButton/Fab/NavItem/SearchBar migration; independent of the trailing slot, so an icon and a shortcut/chevron can coexist. `style.has_submenu` swaps that trailing slot for a `chevron_right` instead (mutually exclusive with the shortcut) — the submenu is a second `Menu` overlay anchored to the item's `name`, positioned beside it rather than below it ("Submenus should open next to the parent menu item without overlapping it"). Anchoring to something inside *another* overlay is the one case `OverlayHost._anchored` falls back past `root` |
| `Tooltip` | 24dp high, 8dp side padding | `inverse_surface` / `inverse_on_surface` |
| `Snackbar` | 48dp growing to 64dp | `inverse_surface`; action label in `inverse_primary`; `style.auto_dismiss` (seconds, opt-in) auto-dismisses an actionless snackbar -- ignored whenever an action (`supporting_text:`) is present, per "snackbars with actions shouldn't auto-dismiss" |
| `BottomSheet` | 28dp **top** corners, max 640dp wide | optional 32×4dp drag handle, 22dp above and below |
| `SideSheet` | 16dp leading corners, max 400dp, 24dp padding | corners follow the docked edge |

Three notes on fidelity, since the point of citing a spec is that the citation
can be checked:

- **Snackbar's page carries no measurement table.** Its 4dp radius is inferred
  from the extra-small step of the shape scale and its 600dp width cap is a
  desktop-reasonable choice. Both are marked as inferred in the source; every
  other number in the module is quoted.
- **Tooltip's table is internally inconsistent** — a 24dp container with "8dp
  padding" cannot also fit a body-small label, so the 8dp is read as the
  horizontal inset and the vertical one is whatever centres the label.
- **The menu implemented is M3's *baseline* menu, not the vertical menu** M3
  now leads with. The newer variant's shape morphing and vibrant colour need a
  theme engine, which does not exist yet.

**Bottom-anchored navigation is deliberately absent.** M3's Navigation Bar and
Bottom App Bar are mobile patterns (§1.2.1); the rail and drawer are their
desktop counterparts. A `BottomSheet` is not an exception to this: it is a
desktop-legitimate surface for secondary content. Its drag handle (`style.handle`,
off by default, opt-in the way a view chooses any other affordance) **is
draggable** — `BottomSheetElement.on_pointer_down`/`on_pointer_move`/
`on_pointer_up` (§5.17.2) drag-and-dismiss with or without the handle drawn,
using the motion system §5.17 added in M7, after this paragraph was first
written.

Four of these share one shape — a container of items where exactly one is
selected — modelled once as `_SelectionContainer`: the container carries
`value:`, the id of the selected child; during layout it calls `set_selected`
on each child; the item renders its own selected appearance. That is also where
the icon **FILL** axis finally earns its place, since it is exactly what M3 uses
to distinguish a selected destination.

Two sizing decisions worth recording:

- **A segmented group shrinks to its content by default**, and divides the
  width equally among segments only when the view gives it one. Filling by
  default left the outline running on past the last segment.
- **The group's outline is drawn once around the whole container**, with a 1dp
  divider between each pair — not per segment, which would double every
  internal edge.

`Button` gained the same treatment: M3 describes its five variants as **one
component in five configurations**, so they are one widget with a `variant`,
not five widget kinds.

**`Link` (`widgets/base.py`) has no page of its own** — the source is the
typography guidance, not a component spec: "For hyperlinked text appearing on
top of a surface color, use primary. However, tertiary can be used to make
links less prominent" and "Hyperlinked text must also be underlined". Its
anatomy is deliberately unlike `Button`'s: M3 states the two are not
interchangeable ("Don't underline the text button. Use hyperlinked body text
instead to emphasize links"), so `Link` carries **no container and no state
layer** — only the label and its underline, sized with `font_size` directly
rather than a fixed type-scale role, since it is meant to sit inline with
whatever body text surrounds it. The underline itself is a 1dp box positioned
from the resolved face's real ascent/descent (`Face.metrics`), not a rough
fraction of the label's measured height — but exactly how far into the
descent it sits is not sourced, since no measurement table exists for it.

**`SpinBox` (`widgets/material.py`) also has no M3 page.** M2's own "Steppers"
component is a multi-step flow indicator, not a numeric control, which is why
this widget is named `SpinBox` rather than the more familiar "Stepper" —
deliberately, to keep the collision from ever landing in a view file. The
nearest M3 grounding is the Sliders page's own convention for the same need:
"Icon buttons placed outside the slider should have the button role", applied
here as two flanking `IconButton`-anatomy regions (no container, plain
`on_surface_variant` icons) rather than a slider's own thumb. A side at its
bound dims to M3's disabled-content opacity (38%) by analogy, not because the
side is actually `disabled`; hover is tracked per side (new state, since
nothing else in the framework needs sub-element hover), but press and focus
are not, to avoid building that machinery for one widget. Typing a value
directly is deliberately unsupported — that needs `TextField`'s full editing
stack, and a half-built version of it would be worse than not having one.

**`Pagination` (`widgets/material.py`) has no M3 page either**, checked
directly rather than assumed: "pagination" appears in the whole reference
library exactly once, as a prohibition on Cards. Its anatomy borrows
`IconButton`'s (prev/next arrows) and `Chip`/`Segment`'s own selected pairing
(`secondary_container`/`on_secondary_container`, for the current page) rather
than inventing new tokens. The windowing rule — always show the first, last,
and the current page's neighbours, collapsing anything larger into a
non-interactive `...`, never collapsing below eight pages — is not sourced
either, since nothing here is. **Hover deliberately breaks from `SpinBox`'s
own pattern**: `SpinBox` animates a fixed two keys, but a page count is
unbounded, and `animated()` leaves a permanent entry in `self._animations`
that nothing evicts — keying one per page number a session ever hovered would
leak. Hover here is one tracked slot, painted at a flat opacity instead of
cross-fading, which is real feedback without state that grows without bound.

**Selection is a binding, not style.** `Checkbox`, `Radio`, `Switch`, and the
filter `Chip` read a new `value:` field on the spec, templated exactly like
`text:` — so `value: "{{ checked.get() }}"` tracks a signal. `Element.checked`
and `Element.number` parse it. Style describes appearance; what a control *is*
is application state.

**Colour defaults live with the widget.** `style.color` is now `None` by
default, meaning "use this component's M3 default for its variant". An explicit
token always wins. Without this a global default would silently override every
variant's correct content colour.

**State layers are shared.** `_emit_state_layer` applies M3's 8% hover / 10%
focus / 10% press overlay above the container and below the content, so every
interactive component behaves identically rather than each reimplementing it.

Two gaps these components inherit, both stated rather than approximated:

- **No motion.** A switch thumb jumps between positions; M3 animates it.

M3's 48dp minimum touch target is deliberately **not** implemented: it is a
finger-precision rule and pySilver is pointer-only (§1.2.1).

**One correction made later:** `LinearProgress` drew its track in
`surface_variant`, which the spec does not say. M3 gives progress indicators a
single colour-role table covering both variants — active `primary`, track
`secondary container` — so the track was corrected when `CircularProgress`
arrived and the two had to agree. A test now asserts they use the same token.

### 5.14 Scrolling — `widgets/scroll.py`

**Scrolling is a paint-time translation, not a relayout.** That single decision
shapes everything else here. Content is measured once against *unbounded* space
on the scroll axis and keeps the offsets layout gave it; moving the scroll
position only changes the origin its subtree is painted from
(`ElementMixin.child_origin`). A wheel notch costs one paint of the viewport,
not a layout pass over every row.

That matters more here than in a typical toolkit. Python, not the GPU, is this
framework's bottleneck (§12) — relaying out a thousand-row list per wheel event
would be plainly visible, while re-emitting its instances is the operation the
display list is already built for.

```yaml
- name: list
  widget: ScrollView
  style: {height: 300, width: expand}   # bounded on the scroll axis
  children:
    - widget: Vertical
      children: [ ... ]
```

| Concern | Behaviour |
|---|---|
| Extent | content measured unbounded along the axis, bounded across it, so text still wraps |
| Bounds | `max_scroll = content + padding − viewport`; the offset is clamped every layout |
| Clipping | in-shader, via the paint context — never scissor, which would break the single draw call (§5.8) |
| Hit testing | threads the same translated origin, so the pointer follows the pixels |
| Wheel | goes to whatever is under the **pointer**, not to the focused element |
| Chaining | propagation stops only if the content actually moved |
| State | the offset lives in `WidgetState.scroll`, so it survives hot reload like focus does |

Three decisions worth recording:

- **An unbounded scroll axis raises.** A `ScrollView` that shrink-wrapped would
  be exactly as tall as the content it is meant to be scrolling, and would
  simply never scroll. The error names the fix, matching what `Flex` already
  does for flexible children in unbounded space.
- **`scroll_by` returns whether it moved**, and the wheel handler stops
  propagation only then. At the end of an inner list the wheel keeps
  travelling outwards — swallowing it unconditionally would trap the pointer
  in a fully-scrolled pane.
- **The offset is re-clamped during layout**, not only when set. A hot reload
  that deletes rows would otherwise leave the view scrolled past the new end.

**The scrollbar is not Material.** M3 specifies none — the catalogue only notes
that a scrolling menu "shows a persistent scrollbar" — so its 4dp thickness and
32dp minimum thumb are pySilver's own, and it is drawn as an indicator rather
than a drag target, since dragging it needs pointer capture wiring that is not
built. Visible scrollbars are a desktop convention with no mobile analogue
(§1.2), which is why one exists at all.

### 5.15 Arc rendering — `KIND_ARC`

The SDF shader drew only rounded boxes, so anything circular and *stroked* —
a circular progress indicator, a ring gauge — could not be expressed at all.
Arcs are a fifth fragment branch rather than tessellated geometry, which keeps
the single instanced draw call intact (§5.8): an arc is one more instance of
the same unit quad, and costs no extra draw call.

The distance field is the standard two-case arc:

```wgsl
fn sd_arc(p: vec2<f32>, sc: vec2<f32>, ra: f32, rb: f32) -> f32 {
    let q = vec2<f32>(abs(p.x), p.y);
    if (sc.y * q.x > sc.x * q.y) { return length(q - sc * ra) - rb; }  // past the cap
    return abs(length(q) - ra) - rb;                                   // on the ring
}
```

Inside the wedge the nearest point is on the circle, so the distance is to the
ring; outside it the nearest point is the cap centre, so the distance is to
that point. **That second case is what gives round caps for free** — M3's
rounded progress ends need no extra geometry, and antialiasing stays analytic
because the result is still a true distance field.

Three details that are not obvious:

- **A full turn takes a separate `sd_ring` branch.** At a half-aperture of π
  the wedge test degenerates and leaves a visible seam at the join. A test
  samples the ring's brightness at every degree and asserts it is uniform.
- **Angles are clockwise from 12 o'clock**, because M3 says circular
  indicators "animate from the top of the track, clockwise by default". Screen
  y grows downward, so the arc is rotated to put its midpoint on −Y before the
  +Y-symmetric field is evaluated.
- **`params` is reinterpreted per kind.** For an arc the vec4 that normally
  carries `(border_w, blur, shadow_dx, shadow_dy)` carries
  `(thickness, start, sweep, _)`. No struct growth: the instance stays 144
  bytes, and every field stays vec4-aligned.

### 5.15.1 Segment/capsule rendering — `KIND_SEGMENT`, `add_segment`

There is no transform anywhere in the instance struct (§4), and arcs are
circular only, so **a diagonal straight line could not be drawn at all**. This
was flagged while surveying the seventeen-widget backlog: it blocks Canvas and
node-graph edges specifically, the two widgets with no M3 grounding that are
built from pySilver's own primitives. It is a sixth fragment branch, following
`KIND_POLYGON` exactly — one more instance of the same unit quad, no new draw
call.

The distance field is exact, not a swept-circle approximation:

```wgsl
fn sd_segment(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
    let pa = p - a;
    let ba = b - a;
    let h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
    return length(pa - ba * h);
}
```

Subtracting a radius from this field gives a capsule, and every point on the
segment is rounded uniformly by doing so — **round caps come free**, exactly
the way `sd_arc`'s wedge/cap split gives arcs theirs (§5.15), with no separate
cap geometry to draw. `max(dot(ba, ba), 1e-6)` guards the degenerate `a == b`:
without it a zero-length segment divides by zero; with it, the capsule becomes
a disc, which is the only sane rendering for a point anyway.

**No spare instance field held two endpoints, so `radii` carries them.** A
stroke has no corners, so the per-corner radii `KIND_BOX` uses there are
unused by every existing non-box kind already — `radii` becomes
`(ax, ay, bx, by)`, both endpoints in the same rect-centre-relative frame the
fragment shader's `p` is already in. `uv` was the other candidate and the
wrong one: it survives to the fragment stage as an *interpolated* `vec2`
(mixed across the quad's corners for texture sampling), not the flat `vec4`
the vertex stage receives, so it cannot carry two flat 2-D points the way
`radii` can. `add_segment` computes the instance's `rect` itself, as the tight
bounding box of both endpoints expanded by the radius — callers give it two
points and a thickness, not a box.

**`thickness` is the capsule's own width**, matching `add_arc`'s convention:
this is the shape being drawn, not a border added to something else, so
`KIND_SEGMENT` has no border and no separate stroke colour the way
`KIND_BOX`/`KIND_POLYGON` do.

No widget drew a segment at the time this primitive shipped — Canvas and
node-graph were still unbuilt, so it shipped as a tested engine primitive
alone, the way `KIND_BOX` and `KIND_SHADOW` were tested directly in
`tests/golden/test_primitives.py` before any widget existed at M2. `Canvas`
(§5.21) was the first consumer, via its `line()` method; `NodeGraph` (§5.24)
is the second, drawing each declared edge as one segment between two port
points.

`tests/test_segment.py` covers the instance
encoding; `tests/golden/test_primitives.py` renders it, including a test that
specifically distinguishes a round cap from a naively squared-off
bounding-box cap — a point inside the capsule's true circular cap but outside
the notional square one it would occupy if `sd_segment`'s rounding were done
wrong.

### 5.17 Motion — `motion/`

One property governs the whole design: **an idle pySilver application renders
zero frames** (§5.10). Animation is the one thing that legitimately needs
continuous frames, so it has to ask for them precisely while it is running and
stop the instant it is not. `Ticker.active` is that signal, and `App.paint`
requests the next frame only while it is true. A finished animation is dropped
from the ticker, so the application falls silent on its own.

**Easing and duration are M3's, not invented.** Six named curves and sixteen
duration tokens, quoted from the spec. The `emphasized` curve is the
interesting one: it is not a cubic bezier at all but a **two-segment path**,
and M3's own CSS row says "N/A (use Standard as a fallback)" because
`cubic-bezier()` cannot express two segments. pySilver is not bound by CSS's
limits, so it implements the real curve — a test asserts the join lands on
0.4 at x=0.166666, exactly where the spec's path data puts it.

Solving a curve means finding the Bezier parameter `t` for a given x before
reading y. Newton-Raphson does that, with a bisection fallback where the slope
is flat — which it is at both ends of every M3 curve, so the fallback is not
hypothetical.

| Concern | Behaviour |
|---|---|
| Interruption | **retarget, not restart** — a new animation begins from the current value, so a switch toggled twice glides rather than snapping back |
| Frame delta | measured **once per frame** and handed to the ticker, never sampled by whoever asks — otherwise layout and paint disagree about where a moving thing is |
| Stalls | a delta over 100 ms is clamped: a debugger pause would otherwise teleport every animation to its end |
| Repeat | wraps instead of finishing, for indeterminate indicators |
| Accessibility | `Settings.reduce_motion` makes animations *arrive immediately* rather than not exist — widget code needs no branch, so it cannot forget the case |
| Invalidation | `animated()` marks **paint**, never layout. It runs every frame |

`ElementMixin.animated(key, target)` is the whole widget-facing API: call it
where the value is needed and use what comes back. The first call settles on
its target at once — there is nothing to animate *from* — and a later call with
a different target retargets. Animations live in element state, so a hot reload
does not restart a transition mid-flight.

**Time is injectable.** `App.clock` defaults to `time.perf_counter` and can be
replaced. This is not a testing nicety: without it an animated golden image
advances by however long the test setup happened to take, and the transition is
over before the frame is captured. That is exactly what happened while building
the motion baseline.

Four things are wired to it. Overlays fade in and out (§5.13.2) and **state
layers cross-fade** — hover, focus and press opacities animate instead of
blinking, which reaches every component at once because `_emit_state_layer` is
shared. It reached every component *except* `Button`, which turned out to have
its own private copy of the state-layer code; unifying it was the fix, and is a
small argument for shared helpers over duplicated ones.

The state-layer duration (100ms, standard) is **not sourced**: M3 gives none,
and its "begin and end on screen" pair is about elements arriving rather than
an in-place emphasis change. 100ms is chosen because a hover response slower
than that reads as lag.

**Indicators travel.** A tab indicator belongs to the `Tabs` container rather
than to a tab, which is what lets it move *between* them — both its x and its
width animate, so it stretches on the way and arrives the right length for a
label-width destination. It costs paint only: the tabs themselves have not
moved. A navigation rail's pill grows outward from a circle around the icon,
and a segment widens around its arriving checkmark (layout, like the chip).

**The icon FILL axis is animated in steps, not continuously.** FILL is a
variable-font axis and the axis coordinates are part of the glyph atlas key
(§5.7); the atlas has no per-entry eviction, and resets wholesale when full.
A continuously animated FILL would therefore pack a fresh rasterisation every
frame and force repeated full resets, re-rasterising every glyph in the
application. Six steps still reads as a transition and bounds the entries per
icon — a test asserts the atlas does not grow across a nav transition.

**Every selection control transitions**, on the one line M3 states outright:
"Selection controls have a short duration of 200ms with Standard easing". A
checkbox cross-fades its outline for its filled container and fades the
checkmark in; a radio cross-fades its ring colour and grows the dot out of the
centre; a filter chip grows its checkmark into the space being made for it.

Two things fall out of the architecture there. **Palette tokens cannot be
interpolated** — they are resolved in the shader against the palette buffer, so
a colour cross-fade is two boxes at complementary alpha, not one lerp. And a
**filter chip's transition changes its width**, so it is the second widget to
use `invalidates="layout"`; the label and every sibling in the row move with
it, which is the behaviour M3 describes.

The `Switch` thumb slides and grows on
timing M3 states directly — "Selection controls have a short duration of 200ms
with Standard easing" — and **indeterminate progress** now works: omitting
`value:` selects it, which is also how M3 describes an indicator changing from
indeterminate to determinate as information arrives. Both use `linear` easing
for the looping animations, because an eased loop decelerates into the wrap and
jumps back to full speed, reading as a stutter once a second. Eased curves are
for transitions that end.

#### 5.16.2 Parallax, and `paint_foreground`

M3: "carousel items move at a different speed than their content". An item lays
its children out wider than itself by the pan range on each side, then pans them
by where the item sits across the strip — one way at the leading edge, the other
at the trailing one, not at all in the middle. It is a paint-time translation,
the same mechanism as scrolling, so it costs nothing beyond the repaint the
movement already required, and being a pure function of position it stays exact
under a drag. The 12% pan range is **not sourced**; M3 describes the effect
without giving a figure.

Building it exposed a gap. `paint_self` runs *before* an element's children,
which is right for a background and wrong for anything that must sit over
content — and M3 carousel items hold images, so the item's label was drawn
underneath the very content it captions and was invisible in every realistic
use. `ElementMixin.paint_foreground` runs after the children and **inside the
cached range**, so a clean subtree still splices correctly.

### 5.17.1 Stylesheets — `spec/stylesheet.py`

`classes` was reserved as a selector target when node identity was split
(§5.1.0); this is its consumer.

**Resolved once, at load.** A rule's properties are folded into the node's own
`StyleSpec` before the element tree is built, so layout and paint read `style`
exactly as they always have and a stylesheet costs **nothing per frame**. The
alternative — resolving selectors during paint — would put a matching pass on
the hot path in the one language where that is least affordable (§12).

The merge rests on Pydantic's `model_fields_set`, the same mechanism that lets
a component distinguish an authored `placement:` from the field default
(§5.13.1). Only fields a rule actually wrote are applied. Without it every rule
would impose the full set of `StyleSpec` defaults, the last match would erase
every earlier one, and a node's own `style:` could never win — its unset fields
would be indistinguishable from deliberate values.

That composition matters in both directions: a stylesheet value lands on the
**explicit** side of `model_fields_set`, so a sheet can override a component's
own default (`CircularProgress`'s 4dp thickness, `BottomSheet`'s bottom
placement). A stylesheet is authorial intent, not a fallback.

| Precedence | |
|---|---|
| 1 | rules with no selector (a baseline) |
| 2 | `widget:` |
| 3 | `classes:` — more classes beat fewer |
| 4 | `name:` |
| 5 | the node's own inline `style:` |

Ties go to document order, later winning. Selectors are **structured**, not
CSS-like strings: `#name` would need quoting in every rule, since YAML reads
`#` as a comment, and a structured rule validates with a field path like the
rest of the format.

**Restyling a running application is a reload**, and reload reconciles rather
than replaces (§5.3) — so changing a stylesheet keeps focus, scroll, and text.

**Sheets share across files.** A `styles:` entry of the form `- source:`
splices in the rules that file names, and a sheet may import another. Rules
land in place, so ordering reads as written and an import placed after a local
rule overrides it.

This is a separate expansion path from widget includes, not a reuse of
`_expand`. A stylesheet is a **list** and a fragment is a **mapping**, so
including one where the other belongs reports that directly instead of failing
later as a validation error about a file that was perfectly valid. The guards
are the same, because a stylesheet reached from a view file is exactly as
untrusted as the view: confinement to the view directory, cycle detection, a
depth limit, and `yaml.safe_load` only.

Every sheet is registered in `sources`, so hot reload watches the whole graph —
editing a theme restyles a running application, and because reload reconciles,
it keeps focus, scroll and text. `examples/gallery` uses one.

### 5.17.2 Drag gestures

Two affordances were drawn long before they did anything: a scrollbar thumb and
a bottom sheet's handle. Both now work, and both needed the same missing piece.

**Claiming a drag.** Capture went to whatever was topmost under the press, which
is wrong for a control drawn *over* something else — a scrollbar thumb sits on
top of the rows, so the press lands on a row and the thumb would move for one
frame and then stop. `PointerEvent.capture()` lets an element handling the press
on the way up take the drag instead. `Event.current` was added alongside it: the
element whose handler is running, which during bubble is an ancestor of the
target, and which a shared handler needs in order to know which element it is
running for.

**A widget cannot reach the overlay host**, and giving it one would let any
element reach into the runtime. A sheet that wants to close raises
`dismiss_requested` on its own state and the host reads it once a frame.

| | |
|---|---|
| Thumb grab | its painted rect plus 6dp of slop — **pointer** precision, not M3's finger target (§1.2.1), since 4dp is unhittable with a mouse |
| Thumb travel | maps to scroll travel, so content keeps pace with the pointer |
| Cost | paint only, like every other scroll |
| Sheet handle | 48dp band, quoted from M3 |
| Sheet drag | downwards only — it is docked, and lifting it exposes the square corners the edge hides |
| Release | past 35% of its height dismisses (**not sourced**), short of it settles back on Emphasized decelerate |
| Click | closes, which is M3's required single-pointer alternative |

A drag tracks the pointer **exactly** — only the release is animated. Easing a
drag would make the sheet lag behind the thing moving it.

### 5.17.3 Elevation

This one began as "implement the tonal half of elevation" and turned into a
correction, because the spec says: **"Surface tint color is deprecated. Use
elevation level tokens (0–5) instead."** The tonal-overlay mechanism these docs
had recorded as the missing half is the mechanism M3 has withdrawn. Tonal
separation now comes from the `surface` and `surface_container_*` roles, which
the spec says are "not tied to elevation" — so choosing a container role and
setting a level are independent decisions, and the widget catalogue was already
doing the first correctly.

What was actually missing was the level system itself. Six levels, each with a
dp height, both quoted:

| Level | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| Height | 0dp | 1dp | 3dp | 6dp | 8dp | 12dp |

Levels 0–3 are resting states; "+4 and +5 are reserved for user-interacted
states such as hover and dragged". Each component carries the resting level
M3's own table assigns it, and `elevation:` in a view overrides that. Hovering
or focusing something **already raised** lifts it one level — the spec says
"usually", which is not licence to give every flat button a shadow under the
pointer.

**Shadows are derived, not chosen.** Three widgets had hand-tuned blur values,
so a dialog and a FAB at the same M3 level did not look like they were at the
same height. `elevation_shadow` now maps a level to one shadow for everything.
The dp→blur mapping is **not sourced** — the spec describes the relationship
("larger, softer shadows express more distance") in prose and images without
figures — so the constants are anchored on the value the Card already used at
level 1, letting the family scale out from a shape that had been reviewed
rather than from an invention.

**One bug worth recording.** The paint sites resolved their level as
`self.elevation or FALLBACK`, and `or` cannot tell an explicit `0` from unset —
so `elevation: 0` silently re-raised the component it was meant to flatten. It
survived the first round of tests because those asserted on the property, which
was correct, rather than on what was painted. Fixing it exposed the real
structure: Card and Button rest at level 1 only in their `elevated` variant, so
the resting level is a **property**, not a class constant.

### 5.17.4 Context menus

Two pieces, and both belong in the runtime rather than in a widget.

**A `CONTEXT_MENU` event**, synthesised from a secondary press the way `CLICK`
is synthesised from a press and release. A view writes `on_context_menu:` and
never learns which integer the backend calls "right" — which is worth hiding,
because the numbering is **one-based** (1 primary, 2 secondary, 3 middle),
checked against `rendercanvas/glfw.py` rather than assumed. Guessing it wrong
fails silently: nothing would ever fire.

The secondary button also no longer presses, focuses or clicks. It used to,
because `_dispatch_pointer` did not look at which button was down — so
right-clicking a button left it stuck in its pressed state, a bug that would
have appeared the first time anyone tried this feature.

**`placement: pointer`**, an overlay positioned at a *point* rather than
against an element. A context menu has no anchor element by definition. The
host records where the request happened and opens down and to the right of it,
flipping near an edge instead of clipping — the same rule anchoring already
uses — then clamps, so a menu taller than the window still starts on screen.

It dismisses on an outside press or Escape like any other transient surface.

### 5.17.5 Cursor shapes

The pointer shape is resolved from the element under it: the topmost one with
an opinion wins, falling back to the platform default. `cursor_at(x, y)` takes
a position rather than being a plain property, because some widgets want
different shapes in different regions — a scroll view is a resize cursor over
its thumb and has no opinion at all over its content.

Two details that are not obvious:

**It resolves from the *unfiltered* hit path.** A disabled control is removed
from the event path, correctly — it must receive nothing — but it still has to
show `not-allowed`. The cursor is feedback, not an event, so it reads the raw
path while dispatch reads the filtered one.

**The shape is pushed only when it changes.** The backend destroys and
recreates a native cursor object on every `set_cursor` call, so setting it each
frame would churn GLFW resources sixty times a second. `App` tracks the last
value; a test asserts three unchanged frames push nothing.

Names are the backend's own CSS-style vocabulary, validated at load so an
unknown one fails with a path instead of raising from inside a frame.

### 5.17.6 Text selection — `text/selection.py`

Selection needs two inverse questions answered: which character is under a
point, and which rectangles cover a character range. Both are derived from
`Paragraph` as it already existed, with **no change to the shaping structures
or the shape cache's key** — which matters, because that cache is on the text
hot path.

The obstacle was that a `ShapedRun` carries cluster indices into *its own* text
and no offset back to the paragraph. Adding one would have meant threading an
offset through itemisation, shaping, and the cache. It turned out to be
unnecessary: the runs of a line concatenate in order, so walking them while
accumulating `len(run.text)` recovers the paragraph offset exactly.

Offsets snap to **grapheme cluster** boundaries via the existing UAX #29
segmentation (§5.7), so an edge never lands inside a flag emoji or between a
base character and its combining mark — a test asserts the caret cannot reach
the interior of a combining sequence. Hit testing picks the **nearest edge**
rather than the containing glyph, which is what makes click-and-drag feel like
it tracks the pointer instead of lagging a character behind.

**Selectable text is focusable.** Key events go to the focused element, so
without that Ctrl+C reaches nothing at all — and being able to Tab to a block
of text and copy it is the accessible behaviour rather than an accident.

**The highlight is painted in `paint_self`**, before the glyphs. In
`paint_foreground` it would sit *over* the letters it is meant to be behind.

#### No system clipboard, deliberately

`rendercanvas` exposes no clipboard, and the only route to one is the backend's
private `canvas._window` handed to GLFW — platform-specific as well as private,
and it fails outright on Wayland without a real surface, which was checked
rather than assumed. Depending on that would be a contract that breaks on a
dependency upgrade.

Copying therefore fills an in-process clipboard, so copy-and-paste *within* an
application works, and `clipboard.install(...)` is the seam for an application
that wants the system one in three lines. A failing backend can never break a
frame: the in-process copy happens first and exceptions are swallowed.

#### Not implemented, and stated

Selection across widgets. Bidirectional selection (risk R9) is closed — see
§5.7.7 Tier 3 — `rects_for` now emits one rect per disjoint span, and
`EditState.affinity` disambiguates a caret offset that sits exactly at a
direction boundary. (Editable text was listed here until `TextField` shipped
-- see 5.9.1.) Double-click uses whitespace delimiting rather than UAX #29
word segmentation — simple and predictable, and labelled as such rather than
presented as Unicode-correct.

### 5.17.7 Type-scale roles — `spec/typescale.py`

`text_style: title-large` resolves to `font_size` **once at load**, the same
decision the stylesheet makes (§5.17.1), so every widget downstream keeps
reading a plain float and a role costs nothing per frame. All fifteen roles
work out of the box; a view's `type_scale:` overrides them role by role, and a
scale can live in its own file and be shared.

**The sourcing is the interesting part**, and is recorded because it was not
straightforward. The spec page serves a JavaScript shell with **no body content
at all** — which is why the token table in `M3-References` scraped empty. That
was not a scraping mistake; the page has nothing to scrape. The figures come
instead from Google's autogenerated token source in the Material Web Components
repository (`tokens/versions/latest/sass/_md-sys-typescale.scss`, Material 3
version 34.0.21), converted from `rem` at 16px/rem.

Two independent checks make that trustworthy rather than merely convenient:

- it **agrees with all four values** the reference library corroborates on its
  own — headline-medium 28, title-large 22, title-small 14, label-medium 12;
- it **settles the one contradiction** in the library, where `headline-large`
  appeared as both 32sp and 36sp in the same file. It is 32.

Tests pin both, so a future change to the table that broke either would fail
rather than pass quietly.

**Size and weight are both applied.** A role resolves to `font_size` and
`font_weight`, and the bundled Roboto ships the Regular and Medium faces the
scale asks for, so `title-medium` is genuinely Medium rather than emboldened
Regular. The font database resolves an unavailable weight to the nearest within
the family, so a request for 700 renders as Medium instead of a smeared
Regular.

A weight is a **different face with different metrics**, which makes one rule
non-negotiable: a label's `measure_text` and its `paint_text` must pass the
same weight, or the box is sized for one face and drawn in another. Applying
this caught exactly that bug mid-change — a partial edit had left one widget
measuring at 400 and painting at 500 — and a test now walks the widget source
asserting every label call carries a weight.

Components take the weight their own M3 role specifies, where the reference
library documents one: a common button is `label-large`, quoted as "(14sp /
20dp line height, **medium weight**)"; nav labels are `label-medium`; tabs are
`title-small`. A segmented button reuses the tab's constants — only the tab's
role is sourced, and looking different from its sibling control would be worse
than following it.

**Tracking is applied too**, as `letter_spacing`. It is an absolute figure in
logical px — that is how the token source states it, and it is why a role's
tracking is only right at that role's size. Nine of the fifteen roles carry
one; the largest is half a pixel.

Letter spacing lands in exactly one place: `ShapedRun.advances_px(px, tracking)`.
Shaping stays size- and spacing-independent, so the shape cache is untouched
and one shaped run still serves every size and every spacing the same string is
drawn at. Everything downstream — a paragraph's width, the paint pen, caret
placement, selection rectangles — reads that one array rather than repeating
the arithmetic, because the same class of bug that a weight mismatch caused
would otherwise have three more places to appear.

Spacing is added per **grapheme cluster**, not per glyph: a ligature is one
glyph for several characters and a combining mark is several glyphs for one, and
spacing either apart from the inside would be wrong. It is added after the last
cluster on a line as well, as CSS `letter-spacing` is, which leaves centred text
off-centre by half a tracking value — a quarter-pixel at the scale's largest.
Trimming it would mean special-casing line ends in the measurement, the caret
and the pen independently, and those drifting apart is the worse bug.

Because three numbers now have to agree between a widget's measure and its
paint, a role travels as **one object**: `ButtonElement.LABEL_ROLE` is the
`TypeStyle` itself, and `measure_text`/`paint_text` take `float | TypeStyle`.
A role cannot half-arrive. The test for it uses the paragraph cache as a
mismatch detector — a label measured and painted with different metrics leaves
two entries where there should be one — and a deliberate mutation confirms it
fails when the tracking is dropped.

**Line height completes the scale.** A role's height replaces the font's own,
and the difference is split evenly above and below the glyphs -- CSS
half-leading. That distribution is the whole design: it means raising a line's
height does not move centred text. A button's label measures 20dp tall instead
of 17 and its baseline lands in exactly the same place, which is why applying
line height moved only three baselines out of a dozen. Text positioned from its
top does move, by half the difference.

Negative leading is allowed and occurs in the real scale -- Roboto wants 67px
at `display-large` where M3 asks for 64 -- so lines close up rather than glyphs
being cropped.

All four of a role's tokens are now applied. The `TypeStyle` a widget holds
carries every one of them, so the "cannot half-arrive" property scales with the
token set rather than degrading as it grows; the mismatch test compares the
whole metric tuple, and a positional `key[-1]` in it silently moved from
tracking to line height the moment the fourth token landed, which is why it now
indexes by name.

### 5.18 Disabled state

M3 states it outright: "Disabled: Container opacity 12% (0.12), Content opacity
38% (0.38)". Two details matter. It is a **replacement** with the `on_surface`
role, not a dimming of the control's own colours — which is why a disabled
filled button and a disabled outlined one look alike. And it is **state, not
style**: `disabled:` is a templated node field beside `value:` and `open:`, not
a `StyleSpec` property, because it changes what a control *is*.

**Inherited.** Disabling a container disables everything inside it, which is the
case people actually reach for. `effective_disabled` walks the parent chain;
nothing caches it, because a cached answer goes stale the moment a signal flips
an ancestor.

**Inert, and invisible to the keyboard.** A disabled element is removed from the
focus order as well as from the pointer path — leaving it Tab-reachable when the
mouse cannot touch it is the accessibility failure the state exists to prevent.
The hit path is **truncated, not filtered**: an enabled ancestor of a disabled
control still receives the event, so a disabled button inside a clickable card
does not swallow the card.

**Painting** reuses the display-list slice mechanism (§5.13.2): one vectorised
pass recolours everything the element drew. Container and content need different
opacities, and the split is made by geometry — a box covering the element's own
bounds is its container, anything else is content. Splitting on primitive *kind*
would have been simpler and wrong: a radio's dot and a switch's thumb are
content drawn as boxes, and at 12% they are all but invisible.

#### One thing found and deliberately not changed

A handler declared in a view is invoked in **both** the capture and bubble
phases, so a handler on an *ancestor* of the target runs twice for one event.
That looks like a bug and is not: an ancestor intercepting during capture is a
tested feature, and the view format registers one handler with no phase to
choose between them. Changing it would break a frozen 1.x API, so it is
documented in the view reference instead. `event.phase` distinguishes them.

Native widget behaviour (a scroll view consuming a wheel notch) *is* guarded to
the non-capture phases, because running it twice would double the scroll.

### 5.19 The collapsing app bar — scroll-linked motion

M3: "when scrolled, medium and large app bars can transform into small app
bars; they should remain small until the page is scrolled back to the top",
and "on scroll, the container changes color to surface container".

This is the one piece of motion in the framework that is **not driven by the
clock**. The bar's height is a direct function of a scroll offset, so it tracks
a drag exactly rather than chasing it, and the ticker is never involved. A view
links the two by name:

```yaml
- {name: bar,  widget: TopAppBar, style: {variant: large, collapses_with: body}}
- {name: body, widget: ScrollView, style: {height: expand}}
```

The bar registers as a **follower** of that view. Scrolling marks paint on the
view alone (§5.14), so anything whose *geometry* depends on the offset must be
told separately — `ScrollView.follow()` relayouts its followers when it moves.
The scrolled content itself is untouched and still travels at paint time.

#### The feedback loop, and where it had to be cut

The bar and the view size each other: collapsing the bar enlarges the viewport,
which shrinks `max_scroll`, which clamps the offset down, which un-collapses the
bar. Measured, the first implementation did not oscillate — it settled into a
**wrong** fixed point, a list back at its top with the bar stuck collapsed.

The instinct is to invalidate harder. That fails for a specific reason worth
recording: a `mark_needs_layout()` issued *during* a layout pass is cleared when
its ancestor finishes laying out, leaving the element permanently dirty and
never relaid out.

So the cycle is cut at its source instead. `ScrollView` measures its scrollable
extent against a viewport with its followers' collapse travel **added back**, so
`max_scroll` is identical whether the bar is expanded or collapsed. There is
then no loop to invalidate around, and a test asserts the extent does not vary
across a full collapse. The degenerate case — content only as tall as the
collapse frees — now scrolls exactly that far, collapses the bar, and stops.

### 5.16.1 The frozen surface

`pysilver.__all__` is the whole public API — 31 names — and is covered by
semantic versioning: adding to it is a minor release, removing or re-signing
anything in it is a major one. `tests/test_public_api.py` pins the list, so a
change to it is a decision rather than an accident.

Two things that audit surfaced:

- **The event classes were not exported.** Annotating a handler
  (`def save(event: PointerEvent)`) required importing from
  `pysilver.runtime.events`, i.e. from a private module. A surface that cannot
  type its own callbacks is not finished, so `Event`, `EventType`,
  `PointerEvent`, `KeyEvent`, and `WheelEvent` are public.
- **There was no `LICENSE` file**, despite `pyproject.toml` declaring MIT since
  M0. MIT requires the notice travel with the distribution, and the three
  bundled font licences needed the same guarantee — all four are now declared
  through `license-files` and verified present in the built wheel.

### 5.16 Carousel — `widgets/carousel.py`

M3 draws an explicit line through the carousel layouts, and it is the line
this implementation is built on:

- **uncontained** items "don't change size", and both free and snap scrolling
  suit it. So this scrolls by **pixels**, translating at paint time through
  `child_origin` exactly as a `ScrollView` does.
- **hero** and **multi_browse** items "automatically change size and snap into
  place to maintain the same layout". So these scroll by **item**, and an
  item's width comes from its position in the strip, not from its content.

That second mode is what makes a carousel a carousel rather than a horizontal
list, and it is why this is a widget rather than a styled `ScrollView`.

**It is also the deliberate exception to §5.14's rule.** A snapping carousel
*must* relayout to scroll, because which item sits on the leading keyline is
what decides every item's width — the two cannot be separated. That is
affordable precisely where the general rule is not: a carousel holds a handful
of items, while a `ScrollView` must assume a thousand rows. The two behaviours
live in one widget and each takes the mechanism that suits it.

Widths per layout, with the leftover going to the large item (M3 calls it
"Dynamic"):

| Layout | Slots |
|---|---|
| `multi_browse` | large, medium, small, then small |
| `hero` | large, small, then small |
| `uncontained` | each item's own `width:` |

**What is missing is the transition, not the layout.** M3 resizes items
continuously as they travel and snaps them home; here the snap is
instantaneous and the resize happens in one step. At rest the geometry is
exactly what M3 specifies — it is the movement between rest states that is
absent. The **medium item width
(112dp) is not sourced**: M3 calls it "dynamic" and gives no figure.

**The snap now travels** (§5.17). `position` is a continuous animated value
and every width and offset derives from it, so items resize *as they move*.

This is the single place in the framework where a transition invalidates
**layout** rather than paint. Item widths genuinely depend on position here, so
repainting alone would draw stale geometry — `animated(..., invalidates="layout")`
makes that cost explicit at the call site rather than hiding it. Measured, one
carousel layout per frame while travelling:

| Items | ms/frame | Share of a 16.7 ms budget |
|---|---|---|
| 6 | 0.20 | 1.2% |
| 100 | 0.79 | 4.8% |
| 300 | 2.24 | 13.4% |

Affordable at any sane carousel length — and precisely why `ScrollView`, which
must assume a thousand rows, may never do the same thing. The timing is M3's
"Standard | 300ms | Begin and end on screen" rather than the Emphasized/500ms
row on the same table: a snap is driven by a wheel notch and repeats as fast as
the user turns it, so half a second of emphasis would queue up behind itself.

One fix this surfaced: a `CarouselItem` label used `on_surface` whatever its
container, so it turned near-invisible the moment a view set a light
background. `paired_content_token` now follows M3's container/`on_` pairing —
`primary_container` implies `on_primary_container`. It is applied only where
the whole surface belongs to the widget; a component whose background is one
part of a larger anatomy keeps its variant's content token.

---

### 5.20 Dock layout — `widgets/dock.py`

Three widgets, no M3 component behind any of them: checked directly, the same
way `Pagination` and `StatusBar` were, rather than assumed absent. `DockSplit`
divides exactly two children with a draggable divider; `DockGroup` is a
tabbed stack of `DockPanel`s, exactly one visible at a time; `DockPanel` is
one pane, its `text:` the tab label. This is **the static half only** — the
tree is arranged once in the view file, the way a `Horizontal`/`Vertical`/`Stack` tree
already is. Runtime drag-and-drop, dragging a tab onto an edge to split or
rearrange the layout while the app runs, is a separate and substantially
larger feature (drop-zone hit-testing, tree mutation, tab reordering, drag
previews) that was scoped out deliberately rather than half-built.

**`DockGroup` owns content-switching that `Tabs` does not.** `Tabs` is only
ever the strip — an application swaps content elsewhere based on its
`value:`. A dock layout has nowhere else for that swap to live, so
`DockGroup` reuses `Tabs`' own anatomy (48dp, 3dp bottom indicator, `primary`
selected / `on_surface_variant` unselected — there being no M3 page for a
dock tab either) but also lays out only the active `DockPanel` at its full
share of the space each frame, giving every other one `Size(0, 0)`. Hover is
tracked and **animated** per tab (`state.data["tab_hover"]` plus one
`animated()` key per panel name) — safe here, unlike `Pagination`'s
deliberate choice not to animate its own per-slot hover, because a dock
group's set of tabs is small and fixed for the widget's lifetime rather than
unbounded.

**`Size(0, 0)` alone does not hide an inactive panel's content** — painting
always emits full geometry regardless of the parent's clip, so an inactive
`DockPanel`'s own children can still paint at whatever size *they* want,
positioned right on top of the active one's. `DockPanelElement` clips itself
to nothing when not selected — which surfaced the zero-size-clip-means-
unclipped gap covered in full in §5.8.6, found here and in `TreeView`'s
existing clip-intersection code from the same underlying cause.

**`DockSplit`'s `axis` default needed a real fix, not a guess.** `axis` is
shared with `ScrollView`, whose own sensible default is `vertical` — so the
bare Pydantic field default cannot also mean "horizontal, side by side" for
this widget, which is the more common reading of "split." Checking
`"axis" in style.model_fields_set` (the same idiom `resolved_placement`
already uses to tell an explicit `center` apart from the field's own
default) lets `DockSplit` default to horizontal while an explicit
`axis: vertical` still wins — confirmed by actually laying out a split
before and after the fix: without it, two panes meant to sit side by side
were stacked top to bottom instead, silently, since a wrong-but-valid
layout raises nothing.

Dragging the divider reuses the exact shape `BottomSheet`'s own drag handle
already established (§5.17.2): `on_pointer_down` claims the drag with
`event.capture()` only when the press lands on the divider (its own rect
plus 3dp of slop, the same "unhittable with a mouse otherwise" reasoning the
scrollbar thumb's slop already has), `on_pointer_move` tracks the pointer
exactly and writes the new ratio straight to `value:`, firing `on_change`
with it already computed — the same split `SpinBox` and `Pagination` make
between updating a widget's own state and telling the application what
changed. Because a `DockSplit`'s two children fill it entirely except for
the divider's own few pixels, hovering or pressing it is naturally isolated
by the framework's existing hit-testing with no extra state of its own —
unlike `SpinBox` or `Pagination`, each of which needed to track *which*
internal region was hovered, `DockSplit` has only the one, so it reuses the
ordinary whole-element hover every other component already does.

ARIA gave this one no approximating to do: `DockGroup` is `tablist`,
`DockPanel` is `tabpanel`, and `DockSplit` is `separator` — precisely
WAI-ARIA's own Window Splitter pattern, which is also where the divider's
arrow-key step (2% per press, along the split's own axis) comes from; not
sourced from M3, but a real convention for the exact role this widget
already reports.

### 5.21 Canvas — `widgets/canvas.py`

No M3 component exists for this either, checked the same way as every other
ungrounded widget. `Canvas` is the first consumer of two engine primitives
that had none until now: `DisplayList.add_segment` (§5.15.1, built for
oriented lines) and the palette-token colour convention every other widget
already emits through. `add_image`/`ImageAtlas` had no consumer at the time `Canvas` landed —
`Canvas.image()` was deliberately left unbuilt so the convention for
loading, caching and keying a source got designed once, by the `Image`
widget itself (§5.22), rather than reinvented here first and reconciled
later. `Image` has since become that consumer; `Canvas.image()` remains
unbuilt.

**Why an imperative callback and not a declarative shape list.** Every other
widget's content is data a view file states once; `Canvas` exists precisely
for the content that doesn't hold still long enough to be data — a live
chart, a custom gauge, a scatter whose count changes every frame. `Shape`
(§5.12) already covers the static case of one polygon declared once;
reconciling N of those for something whose N changes at runtime would fight
the reconciler rather than use it. Flutter's `CustomPainter` and HTML5's
`<canvas>` both land on the same shape for the same reason: the view names a
handler, the handler receives a drawing context, and it calls methods on it
directly. `CanvasElement` follows them rather than inventing a third shape.

**The handler is wired through the existing `handlers:` mechanism with no
changes to it.** `WidgetSpec` validates every handler key with `on_` — a bare
`painter:` key would fail that validator, so the handler is named `on_paint`
instead, resolved by the unmodified `bind_handlers` path exactly like
`on_click` or `on_change`. The difference is only in who calls it:
`EventDispatcher._invoke` calls a real handler in response to a dispatched
`Event`, but there is no event here, so `CanvasElement.paint_self` looks it
up in `self.handlers` and calls it directly, with one argument — a
`CanvasContext` — the same one-argument shape every other handler already
has.

**Only primitives the shader already has a branch for are exposed**: a
stroked line (`add_segment`), a filled and optionally bordered/rounded box
(`add_box`), a filled circle (`add_box` with its corner radius at half its
own size — the same collapse `Shape`'s corner-radius-to-maximum morph
already relies on), a stroked ring segment (`add_arc`), a regular polygon
(`add_polygon`), and text (`paint_text`). §12's single-draw-call rule is what
already ruled out rasterising arbitrary vector paths for `Shape`; the same
limit applies to a handler-driven surface just as much as a declarative one.
`CanvasContext`'s coordinates are logical px relative to the canvas's own
top-left and its own physical-px conversion happens once, inside the
context, so a handler never touches the pixel ratio — consistent with every
other widget's `paint_self`. Colour is either a palette token name (themed,
the vocabulary every other widget uses) or a literal RGBA tuple, for the
real case of data-driven colour — a chart bar tinted by its value — that has
no semantic role to name.

**Clipping reuses §5.8.6's fix rather than repeating the bug it fixes.**
`CanvasElement` computes its own clip by intersecting its rect with whatever
an ancestor already set — the identical `TreeItemElement`/`DockPanelElement`
formula, flooring a degenerate intersection to `HIDDEN_EXTENT` rather than
the literal zero that reads as "unclipped" to `ui.wgsl`'s `clip.z/w > 0.0`
gate — then hands that already-clipped context to `CanvasContext`, so every
primitive it emits is clipped to the canvas's own bounds without the handler
needing to know clipping exists.

**Sizing needed its own concrete fallback, the same lesson `ButtonElement`'s
`HEIGHT` exists to avoid relearning.** A `Canvas` has no content of its own
to measure — no label, no children — so with no explicit `width`/`height`
and no bound from its parent it would otherwise lay out `0×0` and silently
draw nothing. It fills a bounded parent's available space; failing that, it
falls back to a fixed `DEFAULT_SIZE` (200dp) rather than collapsing to zero.

**Invalidation is the application's job, not a new API.** The handler is an
opaque Python closure — the framework cannot know its drawing changed
without calling it, so it is called exactly when this element itself
repaints, same as every widget's `paint_self`, and skipped via the ordinary
paint cache (§6) exactly as often as any other clean subtree is. An
application whose drawing depends on state outside the normal binding path
calls `app.root.find(name).mark_needs_paint()` — the same public method
every element already has.

ARIA has a role for exactly this shape: `Canvas` reports `img`, HTML5's own
convention for opaque raster content with no structure of its own to expose.

**A literal `color` tuple is converted from sRGB to linear before it reaches
the display list.** Found while building `Terminal` (§5.26): the render
target is `rgba8unorm-srgb`, which applies sRGB encoding on write, so an
unconverted literal read back lighter than intended — verified empirically
that `color=(0.5, 0.5, 0.5, 1.0)` produced pixel `(188, 188, 188)`, not
`(128, 128, 128)`. The same double-encoding mistake §5.6.1 already
documents for the palette upload path, recurring here on an application's
own literal colour rather than a token. `CanvasContext._fill` and `.text`'s
literal-colour branch both now route through a small `_linear()` helper
(`theme.srgb_to_linear`, the same conversion the palette itself already
uses) before the colour reaches `add_box`/`add_segment`/`add_arc`/
`add_polygon`/`emit`, so a handler passes the ordinary sRGB value a colour
picker would show and gets what it asked for — the conversion is the
widget's problem, not the application's. `1.0`/`0.0` are fixed points of
the sRGB curve, which is why the original literal-colour test
(`color=(1.0, 0.0, 0.0, 1.0)`) never caught this; a second test using a
genuine mid-range value (`0.5`) does. `test_canvas_baseline`'s hexagon
(`color=(0.9, 0.4, 0.2, 1.0)`) rendered visibly richer after the fix and
its golden baseline was regenerated.

### 5.22 Image — `widgets/image.py`

No M3 component either — images only ever appear as content *inside* other
components (Carousel, Cards), never with an anatomy of their own. The second
consumer of an engine prerequisite left dormant since it was built:
`DisplayList.add_image` (`Kind.IMAGE`) and `ImageAtlas` (skyline-packed,
decode-agnostic, built alongside `bind_image_atlas`) both had zero callers
before this widget.

**Wiring the atlas into the engine took more than adding a widget class.**
`ImageAtlas`'s own docstring was explicit that nothing had done this yet:
"a widget that draws images should own an `ImageAtlas` the way `TextEngine`
owns a `GlyphAtlas`." That meant mirroring the text pipeline's plumbing
exactly, at every layer `GlyphAtlas` already touches:

- `Engine.__init__` owns a device-bound `ImageAtlas` and binds it to the
  pipeline's already-existing placeholder slot (`bind_image_atlas`, dormant
  since the atlas-packing milestone); `Engine._upload` uploads it every
  frame alongside the glyph atlas; `Engine.close` destroys it.
- `App` owns a CPU-only `ImageAtlas`, promotes it to the device in `attach`
  the same way it promotes `TextEngine`, and re-propagates it in `reload`
  (hot reload rebuilds `self.root`, so a stale reference would silently
  fall back to the process-wide default atlas otherwise).
- `PaintContext` gained an `images: ImageAtlas` field (`default_image_atlas`
  mirrors `default_text_engine`'s process-wide CPU-only singleton, for
  measuring an `Image` in a unit test with no App standing behind it).
- `ElementMixin` gained `image_atlas`/`set_image_atlas`, mirroring
  `text_engine`/`set_text_engine` exactly — and for the identical reason:
  `perform_layout` receives only `Constraints`, no `PaintContext`, so
  `Image` needs an atlas reachable *without* one to learn a decoded image's
  natural size during layout, not only to sample it during paint.

**Fixed a real, if latent, circular import while wiring this in.**
`render/atlas.py` imported `Face`/`GlyphBitmap` from `text.font` for type
annotations only; `text/__init__.py` imports `GlyphAtlas` back from
`render.atlas`. This was already a cycle, silently surviving only because
nothing had imported `render.atlas` before `text` finished loading first.
Adding `from ..render.atlas import ImageAtlas` to `runtime/engine.py`
changed which side loaded first and made it a real `ImportError`. Fixed at
the source rather than by reordering imports to keep tripping the same
latent wire: `Face`/`GlyphBitmap` moved under `TYPE_CHECKING` in
`render/atlas.py`, which costs nothing since `from __future__ import
annotations` already makes every annotation a string there.

**`path:`, not `source:`.** `source:` is already view-*composition* syntax —
`spec/include.py` walks the raw YAML and splices in a fragment wherever it
finds that key, before Pydantic ever validates a node. A widget field
reusing the name would be silently swallowed as an include attempt rather
than reaching `WidgetSpec` at all. `path:` is a new templated field on
`WidgetSpec`, added to `ElementMixin`'s existing `_text`/`_value`/`_open`/
`_disabled`/`_error` binding list (`init_element`, `update_spec`, `bind`'s
`bound` list) the same way `disabled:` was added after the fact — so
`path: "{{ avatar.get() }}"` swaps the decoded picture when a signal
changes. It resolves the way a running process resolves any filesystem
path (absolute as given, relative to the working directory otherwise) —
deliberately **not** relative to the view file the way a `source:` include
is confined, since threading the view root through to arbitrary widget
paint time would be a substantially larger plumbing change than one widget
justifies; an application wanting that resolves the path itself.

**Sizing has real intrinsic content, unlike `Canvas`.** With no explicit
`width`/`height`, `perform_layout` reports the decoded image's own pixel
dimensions (one image px, one logical px) as its preferred size and lets
`outer.constrain(natural)` do the rest — the same one-line shape every
widget with an intrinsic size already uses, `Shape` included. An axis the
view did size wins outright, because `sized()` already made that axis tight
before `constrain` ever sees it; no cross-axis aspect coupling was added for
the case of only one axis being explicit — every other axis in this layout
system is decided independently, and inventing a coupling for one widget
would be a wrinkle nothing else has.

**`fit` is CSS's `object-fit` vocabulary, not an M3 one.** `contain`
(default), `cover`, `fill`, `none` — the standard four, chosen because M3
states nothing here at all and this is a widely understood convention to
reach for instead. `contain`/`none` can leave part of the box uncovered,
which is why `ImageElement.paint_self` calls the inherited background/
border/shadow painter first: a letterboxed image over an explicit
`background:` shows that colour in the gap, the same layering `Canvas` uses
for the same reason. Only `cover` crops, and it crops the *source* — the UV
rect narrows symmetrically rather than the destination rect shrinking,
so no extra geometry is needed for the cropped part to simply not be
sampled. The math (`_fit_image`) is a pure function taking a box, a natural
size, and a UV rect, independently unit-testable with no GPU and no App.

**No tint.** `Kind.IMAGE`'s shader branch has no palette-token slot — only
`Shape`/`Icon`/glyphs do, because each of those clears its own atlas key on
every colour-affecting parameter change, which an already-decoded image has
no equivalent hook for. Baking a literal tint from `ctx.palette.linear(...)`
would silently stop re-theming on a live palette swap, which is exactly what
§2's "emit tokens, not colours" rule exists to prevent — so `color:` is not
read at all; `opacity:` still reaches the instance's tint alpha, since that
is not a colour choice.

**A bad `path:` degrades to nothing rather than crashing a frame.** Decoding
happens lazily, inside `_entry()`, cached per resolved `Path` on the element
itself (comparing against the last-resolved key, not re-decoding every
layout). A missing file or a decode failure raises inside that cache
boundary, is logged to stderr once, and is remembered as "nothing to draw"
until `path:` changes to something that decodes — the same reasoning
`reload_errors` already applies to a broken hot reload: a bad asset
reference should degrade visibly, not take the whole frame down with it.

ARIA reports `img` here too, HTML5's own convention, same as `Canvas`.

### 5.23 Video — `widgets/video.py`

No M3 component either. Unlike every other widget this session, this one
is not a case of "no anatomy exists" alone -- pySilver has no codec
dependency at all (Pillow decodes still images; nothing decodes
`.mp4`/`.webm`), and adding one, realistically PyAV wrapping FFmpeg, would
mean taking on its install size and licensing considerations for every
application, not just the ones that show video. Put to the user directly
rather than assumed: **`Video` is a frame sink.** The application decodes
however it likes and calls `push_frame(rgba)`; this widget owns only
displaying whatever the latest one was.

**The only addition below the widget layer was `ImageAtlas.update`.**
`ImageAtlas.add` always allocates a fresh rectangle through the skyline
packer -- correct for "this source decoded to a different picture," wrong
for a stream arriving 30-60 times a second at the same resolution, which
would churn the packer's own bookkeeping for pixels that were only ever
going to land back in the same slot and eventually force a wholesale
eviction for no reason. `update` overwrites an existing entry's pixels in
place with one numpy slice write when the shape still matches, and falls
back to `add` on a genuine miss, a stale generation (the atlas was reset
since), or a size change -- a decoder renegotiating resolution mid-stream
is exactly "a different image." Everything else was already in place: no
new texture slot, no shader change, no exception to the single-draw-call
model. A video frame is one `Kind.IMAGE` instance sampling the same
`image_atlas` every `Image` on screen already does -- confirmed by a golden
that pushes a stale grey frame, renders once, pushes a live green/yellow
one at the same shape, and asserts the second frame's colours: if the
in-place overwrite or the per-frame `Engine._upload` were wrong, the stale
frame's grey would be what showed instead.

**Each `VideoElement` gets its own atlas key, not a spec-derived one.**
`id`/`name` identify a *position* in the tree, not the object; keying on
`object()` created once in `__init__` ties the slot to this specific
instance, which is exactly what reconciliation preserves across an
ordinary update (the same instance keeps calling `push_frame` on the same
key). A `Video` that is genuinely removed and replaced orphans its old
region until the atlas next resets -- a real, minor cost, the same shape as
any atlas key nobody explicitly evicts, not treated as a defect to solve
now.

**No decode-adjacent state lives on the widget.** No `value:` for
play/pause, no scrub bar, no clock -- the application already owns the
decode loop, so it is the natural owner of transport state too, composed
from ordinary widgets (`IconButton` for play/pause, `LinearProgress` or a
`Canvas`-drawn bar for position) around a `Video` the way a page composes
around anything else. Sizing, `fit`, corner rounding, and the absence of a
`color:` tint all reuse `Image`'s own reasoning verbatim (`_fit_image` is
imported from `widgets/image.py` rather than duplicated) -- the only
genuine difference is where the pixels come from.

`push_frame` is not thread-safe, the same rule every mutation in this
framework follows (§8): it must run on the engine thread. A decoder on its
own thread hands a frame back with `loop.call_soon_threadsafe(element.
push_frame, rgba)`, identical to what `Signal.set` already requires.

ARIA has no dedicated role for video either -- HTML-AAM exposes `<video>`
as `"video"` through platform accessibility APIs, but that is not a role
the abstract ARIA taxonomy itself defines, and this session could not
verify the mapping against a live spec rather than recall it. Reports
`img`, the same opaque-visual-content answer `Canvas`/`Image` already give,
rather than asserting a name this session could not check.

### 5.24 Node graph — `widgets/nodegraph.py`

No M3 component either, checked directly the way every other ungrounded
widget this session was. **A real interactive editor, not a thin surface
an application draws into itself the way `Canvas` is** -- `Node` is a
composed element with its own child content and its own drag handling,
chosen over a Canvas-based alternative because panning, dragging, and
hit-testing all have existing framework mechanisms to reuse rather than
needing a bespoke region system built on top of one opaque paint handler.

**Panning reuses `ScrollView`'s mechanism exactly (§5.14): `child_origin`
returns `absolute - state.scroll`.** Panning is a paint-time translation,
not a relayout, for the identical reason scrolling is -- Python is the
bottleneck (§12), and a relayout per pan delta would be visible. There is
no zoom. Scaling would either distort glyph rasterisation -- the same
per-frame-key atlas-thrashing trap `Icon`'s `icon_fill` axis quantisation
exists to avoid (§5.7) -- or force re-shaping text at a new pixel size on
every step, and would also need every hit rect scaled to match. That is a
real second feature, not a checkbox on this one, so v1 stops at pan and
drag, both useful and correct without it.

**A node's position is runtime state, not the spec.** `StyleSpec.x`/`y`
give a `Node`'s starting point only; `NodeElement.position` reads them into
`state.data` once and never again, the same split `ScrollView.state.scroll`
already makes between an author's declared value and the runtime's own. A
reload that reconciles the same `x`/`y` back in therefore does not reset a
node the user has already dragged, because `configure()` never touches
`state.data`.

**No special-case region hit-testing for dragging.** A `Node`'s title bar
is part of its own painted area, not a separate child element, so a press
there is simply a press on the `Node` element itself; `on_pointer_down`
checks the point against its own title-bar rect (`DockSplit._on_divider`'s
own pattern, §5.20) before starting a drag, so a press on the node's
content is left alone for whatever widget is actually there. The one place
this needed a genuine fix rather than falling out for free: a native
handler runs on the way up only, never during capture
(`EventDispatcher._invoke`, §5.9), so a press anywhere inside a `Node` --
content included -- bubbles through it to `NodeGraph` next. `NodeGraph.
on_pointer_down` therefore checks `event.target is self` before starting a
pan, rather than assuming "reached me" already means "missed every node" --
reading the dispatcher's own already-computed hit-test result, not running
a second one.

**Edges are declared, not drawn.** `WidgetSpec.edges` is a tuple of
`EdgeSpec(source, target)` -- `source`/`target` rather than `from`/`to`
because `from` is a Python keyword -- each a `"node.port"` pair reusing
`Identifier`'s existing dotted-name pattern verbatim rather than inventing
a second syntax for the same shape. `NodeGraph.paint_self` resolves each
edge to two points and draws one `add_segment` (§5.15.1) between them,
after its own background and before its children paint, so every node sits
visually on top of the wires touching it. A port's position along its
node's edge is evenly spaced by its index among that side's `inputs`/
`outputs` list -- not sourced from anywhere, since there is nothing to
source it from, but the ordinary node-editor convention. An edge naming a
node or port that does not exist is silently skipped rather than raising,
consistent with a declarative view file describing what *should* connect
without the loader needing to re-validate cross-references at parse time.

`inputs`/`outputs` reuse the existing `Classes` annotated type verbatim --
the same `BeforeValidator(_parse_classes)` a view's `classes:` field
already uses to accept either a list or a space-separated string -- since
a port-name list is the identical shape with no reason to parse it twice.

`FOCUSABLE_KINDS` gains `Node`, and its arrow keys nudge the focused node
by a fixed step and fire `on_change` immediately, mirroring `DockSplit`'s
own keyboard-driven affordance (§5.20) -- there being no separate release
event for a key press the way there is for a pointer drag, `on_change`
there fires only once the drag actually ends.

ARIA has no node-graph role either. The W3C Graphics-ARIA module defines
exactly this shape, though: `"graphics-document"` for a diagram's own
container, `"graphics-object"` for one figure within it -- used directly
rather than approximated, unlike `Canvas`/`Image`/`Video`'s shared `"img"`
fallback where no closer role exists at all.

### 5.25 Code editor — `widgets/codeeditor.py`

No M3 component either. Built on the shared editing model
(`text/editing.py`'s `Editor`/`EditState`, `text/selection.py`'s point/offset
helpers) rather than on `TextField` (§5.9.1) itself -- that model's own
docstring already anticipates more than one consumer ("`TextFieldElement`
supplies keys and pixels; this supplies the answers"), and `TextField`'s
layout and paint methods are saturated with M3-specific chrome (a floating
label, an indicator stroke that thickens on focus) a code editor has none
of. Subclassing `TextFieldElement` would have meant overriding nearly every
method on it; building on the shared model instead reuses everything that
actually is shared -- grapheme-aware caret motion, undo/redo, selection
ranges, click-to-offset -- with none of the M3 baggage.

**Never wraps, and therefore needs a genuinely bounded height.** Line
numbers only mean something if they correspond 1:1 with the buffer's own
source lines, so `max_width=None` is always passed to `text_engine.layout()`
-- `layout_text`'s own contract already guarantees a hard break (`\n`)
starts a new `TextLine` regardless of wrapping, so this alone is "one
`TextLine` per source line," and a long line scrolls sideways instead of
wrapping into a visual line the gutter could not label. Because nothing
wraps, an unbounded height would try to grow to fit the entire buffer and
never scroll -- the identical reasoning `ScrollView` (§5.14) raises for.

**Syntax highlighting is optional Pygments (BSD-2), not a hard dependency
-- asked of the user directly.** The real fork was Pygments against
tree-sitter: tree-sitter's incremental re-parsing and real syntax tree are
more capability than a v1 highlighter needs, at the cost of a new, heavier
native dependency; Pygments is simpler, already commonly present, and its
whole-buffer re-lex per edit is an accepted, real limitation for very large
files edited live, the same shape of trade-off `NodeGraph` (§5.24) made by
deferring zoom. `pygments` is imported lazily inside the one module that
uses it (`pysilver[code]`, a new optional extra alongside `a11y`/`svg`); with
it absent, or `style.language` unset or unrecognised by
`pygments.lexers.get_lexer_by_name`, the widget still works as a plain
editable multi-line control, just uncoloured -- `Image`'s (§5.22) "degrade
rather than crash" choice for a bad path, applied here to a missing optional
capability instead of bad data. Colours are literal RGBA, not palette
tokens, for the identical reason `CanvasContext`'s (§5.21) own colour
parameter accepts a literal tuple: there are only four true M3 colour roles
(primary/secondary/tertiary/error) against the ten-odd categories a real
syntax theme needs, and no semantic role exists to map the rest onto -- a
stated departure from "emit tokens, not colours" (§5.6), not an oversight.
Getting the source-offset accounting right needed one thing verified rather
than assumed: Pygments strips input by default, which would desync a
running offset count from the buffer's real length, so the lexer is
constructed with `stripnl=False, stripall=False, ensurenl=False` and this
was checked empirically (`"".join(v for _, v in lex(text, lexer)) == text`)
before relying on it.

**No monospace font ships with pySilver.** Roboto and Noto Sans (§2.3.1) are
both proportional. `style.font_family` requests a family by name through
the same `FontRequest`/`FontDB` machinery every widget already resolves
against; an application that wants true monospace alignment loads one
itself with `app.text.db.load(path)` -- already a public method, no new API
surface -- before this widget ever asks for it. Left unset, or naming a
family nobody loaded, `FontDB.face_for` already falls back to the primary
bundled face rather than raising, so an app that does nothing gets working,
if proportional, text.

**A new dispatcher capability was needed, not just a new widget.** Tab is
intercepted and treated as focus traversal before any element's own
`on_key_down` ever runs (`EventDispatcher._dispatch_to_focused`) -- there was
no way for a widget to see the keypress at all, let alone insert indentation
with it. `ElementMixin.CAPTURES_TAB` (default `False`, the same shape as the
existing `CLIPS_CHILDREN` flag, §5.9) lets a focused element opt in;
`CodeEditor` is the first, and so far only, one that does. `Escape` still
defocuses unconditionally before per-element delivery too, so trapping Tab
this way never traps the keyboard -- Escape, then Tab, always reaches the
next control, the same escape hatch real code editors themselves rely on.

**Tab/Shift+Tab operate on whole lines, not just the caret, whenever there
is a selection.** `insert()`'s own semantics replace a selection outright,
so a naive `insert(state, " " * tab_size)` on a multi-line selection would
have destroyed the selected code and left four spaces in its place -- a
real correctness bug caught by reasoning through the existing model's
contract before shipping, not after. With no selection, Tab inserts spaces
at the caret like ordinary typing instead, since re-indenting a whole line
from a mid-line caret is not what a user pressing Tab there expects.

ARIA has no dedicated role either. `"textbox"` -- the same role `TextField`
(§5.9.1) already carries, with `aria-multiline` the only difference a
multi-line `<textarea>` would add -- is the closest real anatomy, used
directly rather than invented.

**`style.read_only`: selectable, not editable, for showing a real code
sample without letting a viewer change it.** `disabled:` was the wrong
tool -- `effective_disabled` also gates `on_pointer_down`/`on_pointer_move`,
which would block selection entirely, not just editing. `read_only`
(`StyleSpec`, since it is a display choice rather than a validity state the
way `disabled`/`error` are) gates only the mutating branches of
`on_key_down` (Tab/Enter/Backspace/Delete/paste/undo/redo, and the delete
half of Ctrl+X) and blocks `on_text` outright, leaving caret motion,
keyboard and mouse selection, Ctrl+A, and copy fully functional. Built for
`examples/gallery`'s per-page code samples (§5.27).

**Deliberately out of scope for this pass**: auto-closing/matching
brackets, multi-cursor editing, code folding, a minimap, a draggable
scrollbar thumb (wheel and keyboard scrolling both work; only the visible,
grabbable indicator is missing), incremental re-lexing for very large
files, and any language server integration -- the package survey that
grounded this widget's design was explicit that an LSP client is an
application concern, not something a widget should hard-depend on.

**A pre-existing `TextEngine.layout` cache-growth concern applied more
sharply here than anywhere it was already true, and has since been fixed.**
`TextEngine._layouts` was keyed by the full text string among other
parameters and nothing ever evicted it (`text/__init__.py`), so a widget
whose content changes on every keystroke accumulated one new full-
`Paragraph` entry per keystroke for the life of the process -- already true
of `TextField`, but worse here because a code buffer is typically much
larger than a text field's value and a long editing session performs many
more edits than a form field usually receives. `_layouts` is now an
`OrderedDict` bounded to `layout_cache_size` entries (default 512, set at
`TextEngine` construction), evicting the least-recently-used paragraph once
full; a cache hit moves its entry to the end, so actively-reused static
labels are not the ones evicted. This keeps "static labels cost nothing
after frame one" for the common case while capping worst-case memory for
`TextField` and `CodeEditor`.

### 5.26 Terminal — `widgets/terminal.py`

No M3 component either. Asked of the user directly, the same fork `Video`
(§5.23) faced: should this widget only render a cell grid an application
feeds it, or own the whole pipeline -- spawning the shell and parsing its
output -- internally? Unlike `Video`, where the app-supplies-frames answer
won because decoding needs a heavy, licence-sensitive dependency (FFmpeg),
here the answer was the opposite: `pysilver[terminal]` owns the shell, and
a view just says `widget: Terminal, style: {shell: "/bin/bash"}`.

**Three layers, two of them someone else's problem.** `pexpect` (ISC) gives
POSIX PTY spawning; `bittty` (WTFPL) gives the VT/ANSI state machine every
terminal emulator implements identically. What is actually left for
pySilver to build is the third layer -- rendering whatever cell grid
`bittty`'s video memory currently says is true, and turning keystrokes into
the bytes a shell expects. Both licences keep the whole `pysilver[terminal]`
extra optional, never a hard dependency, the same rule `accesskit` already
follows.

**`bittty` replaced `pyte` here (2026-09-08), found live.** A single real
keystroke, under zsh with zsh-syntax-highlighting active, could corrupt the
whole input line ("echo hi" rendering as "echoo o hi") -- confirmed a real
`pyte` (0.8.2, the latest release; no meaningful update in years) parsing
defect, not a pySilver bug: reproduced with zero pySilver code involved
(bare `pexpect` + `pyte` fed the identical bytes), independent of typing
speed and of how the byte stream was chunked, and gone once the responsible
shell plugin was disabled. `bittty` renders the same stream correctly.
`bittty.devices.board.Board` is used purely as a parser -- its own PTY
spawning (`start_process()`) is never called, since `pexpect`/`_PtySession`
already own that reliably; `Board.pty` is instead wired to a small
`Connection`-protocol shim over `_PtySession.write`, so the board's own
internal auto-replies (DSR and similar shell queries) still reach the real
pty. **Regression from the swap: no scrollback** -- `bittty` keeps none (a
documented limitation, not an oversight); re-implementing it is a tracked
follow-up, not done in this pass.

**Only POSIX is implemented and verified.** `pexpect.spawn` was exercised
directly -- spawn a shell, read its output through `read_nonblocking`, feed
it to `bittty`, read the resulting cell grid back -- before being relied
on. Windows would need `pywinpty` wrapping ConPTY entirely, a different
backend, not `pexpect.spawn`, which is POSIX-only; the platform check is a
real branch, but nothing here could verify a Windows implementation rather
than guess at one, so it is left unstarted -- `AccessKit`'s own "untested on
Windows and macOS" precedent, applied here as "not built" rather than
"built and hoped."

**No PTY mutation happens off the engine thread**, the identical rule
`Signal.set` and `HotReloader` (§5.11) already follow. The background
reader thread's only job is appending raw bytes to a lock-guarded buffer;
feeding them into `bittty` and repainting both happen later, back on the
engine thread. When a real `asyncio` loop can be captured, the reader
thread also calls `loop.call_soon_threadsafe(...)` to wake an idle app
promptly -- `VideoElement.push_frame`'s (§5.23) own docstring already
prescribes this exact pattern for "a worker thread has news." Whether or
not that wake succeeds, `paint_self` unconditionally drains pending bytes
on every call, and a `repeat=True` animation keeps a repaint scheduled
roughly twice a second for as long as a session is alive, focused or not --
so PTY output is never permanently stuck even if loop capture fails; the
wake is an optimisation for instant updates, not a correctness requirement.

**Cell backgrounds and the cursor are grid-accurate regardless of font
metrics; glyphs inside a run are not, without a genuinely monospace face.**
No monospace font ships with pySilver -- the identical gap `CodeEditor`
(§5.25) documents. Rather than rely on natural text-shaping advances to
land glyphs on cell boundaries (correct only for a real monospace face,
silently wrong otherwise), each row is walked as runs of cells sharing one
foreground/background colour; a run's background box and its text's start
position are both placed at an analytically computed `column * cell_width`,
so the grid itself never drifts even when the requested font is
proportional -- only the glyphs drawn inside one run can visually
misalign, a strictly smaller and more honest failure mode than a
background box landing in the wrong place.

**A real bug, caught and fixed before shipping, not after: literal colours
were being treated as sRGB when the render target wants linear.** The
surface format is `rgba8unorm-srgb` (§5.6.1), which encodes on write --
verified empirically that a literal `color=(0.5, 0.5, 0.5, 1.0)` reads back
as `(188, 188, 188)`, not `(128, 128, 128)`, unless converted first. This
widget's own ANSI colour table was originally written as plain "looks about
right" floats -- exactly the double-encoding mistake §5.6.1 already
documents for the palette upload path, recurring on a literal colour
instead of a token. Fixed with a small `_srgb()` helper (`theme.
srgb_to_linear`, already used for the palette itself) that every literal
colour in this widget now goes through; `CodeEditor`'s own syntax-highlight
colours had the identical bug and were fixed the same way in the same
pass, with both golden baselines regenerated afterward. A broader audit of
literal colours reaching application code through `Canvas` (§5.21) is
tracked separately, not fixed here.

ARIA/AT-SPI has a real, dedicated role for this -- unlike most of this
session's ungrounded widgets, which settle for the nearest ARIA
approximation, AT-SPI's own role vocabulary defines `TERMINAL` outright
(verified against the installed `accesskit` package's `Role` enum, not
assumed), and it is wired all the way through, including
`accesskit_bridge.py`'s own role table, not just the abstract vocabulary in
`runtime/accessibility.py`.

**Deliberately out of scope for this pass**: mouse text selection and
copy (Ctrl+C is always the interrupt byte sent to the shell here, never a
copy shortcut -- there is no selection to copy without one), underline and
strikethrough rendering, function keys beyond F1-F4, true-colour-aware
theme adaptation (the ANSI palette is fixed, not part of the M3 theme), and
Windows support.

### 5.27 Page host — `widgets/pagehost.py`

No M3 component -- a pySilver-only navigation primitive closing a real gap
in the view format: no way to say "mount exactly one of these children,
chosen by a signal" (`spec/include.py`'s own docstring calls the absence of
a conditional include out deliberately). Built for a real single-page-
application shell (`examples/gallery`'s navigation rail), not a toy: a
`Stack` with every candidate alive and hidden would have kept every
inactive page's animations ticking and, worse, kept an inactive `Terminal`
page's real shell process running in the background forever.

`value:` follows the exact name-of-the-selected-child convention
`Tabs`/`NavigationRail`/`SegmentedButton` already use (§5.12) rather than
inventing a second selection idiom; `default:` (`WidgetSpec`, deliberately
**not** templated, unlike `value:`) names a fixed fallback page chosen at
design time for when `value:` matches nothing.

**Every declared child is built eagerly, by the ordinary `build_element`
recursion, but only the active one is ever alive.** Construction alone has
no side effects for any widget in the catalogue -- checked directly:
`TerminalElement`'s PTY spawns from `set_ticker()`, never `__init__` -- so
building every page up front costs only memory. `PageHostElement` overrides
the public `children` property to expose only the active child; every
mechanism that already propagates by walking `self.children`
(`set_ticker`/`set_text_engine`/`set_image_atlas`, the generic `paint()`,
`walk_elements()` and therefore `find()`/`dispose()`) therefore reaches only
the active page automatically, with no changes to any of those methods. A
dormant page never animates, never paints, and a dormant `Terminal` holds no
shell process.

**Switching disposes the outgoing page and reactivates the incoming one.**
The object itself is never rebuilt -- state not tied to being alive (a
`SpinBox`'s number, a `Checkbox`'s value) survives a round trip; state that
is tied to being alive does not (`Terminal`'s shell stops and a fresh one
starts on return, confirmed against `_ensure_started()`'s only guard being
`self._session is not None`, which `dispose()` clears).

**A new propagation mechanism, `ElementMixin.mounter`/`set_mounter`, was a
necessary consequence of the design, not part of the original plan.**
`App.mount()`'s own bind-and-resolve-handlers walk runs exactly once, over
`root.walk_elements()` -- which, like everything else, sees only whichever
page is active *at mount time*. A page built later and switched into is
therefore structurally invisible to that one-time pass, so its own
`{{ }}` bindings and `handlers:` would never resolve. `mounter` mirrors
`ticker`/`text_engine`/`image_atlas` exactly (a propagated attribute with a
no-op default, threaded down via `set_mounter`); `App._mount_subtree` is
`mount()`'s own per-element bind-and-resolve work, extracted so `PageHost`
can call it on just the newly active subtree.

**Cost accepted deliberately**: switching away from a page and back does
not preserve local UI state -- scroll position, a dragged `NodeGraph` node,
an open `Terminal` session -- the new instance starts fresh. This matches
"loaded on event" literally and is standard behaviour for page-based
navigation elsewhere (WPF's `Frame`, for one).

No M3-sourced role exists (no M3 component to source one from); ARIA
convention has no single role for "a container that shows one of several
things," so it is treated as a plain `"group"`, the same as `Container`/
`Horizontal`/`Vertical`/`Stack` -- not silenced the way `NavigationRail` is,
since it has a stated "role is not announced" in M3 itself and `PageHost`
has no such statement to point to.

### 5.28 Slider — `widgets/slider.py`

The one gap that mattered most from the M3-catalogue review this session
opened: `SpinBox` (§5.12) was built once already citing this exact page
("Icon buttons placed outside the slider should have the button role"), but
the actual slider -- a track with a draggable handle -- was never built.
Standard variant, every named M3 size: `style.size` selects one of
`extra_small` (M3's own stated default), `small`, `medium`, `large`, or
`extra_large`, all four sourced from `COMPONENT_SLIDERS.md`'s own
Measurements table (confirmed twice -- the table itself, and again in its
own "Size" guideline section, agreeing exactly):

| Size | Track height | Handle height | Track corner radius |
|------|-------------|----------------|----------------------|
| extra_small (default) | 16dp | 44dp | 8dp |
| small | 24dp | 44dp | 8dp |
| medium | 40dp | 52dp | 12dp |
| large | 56dp | 68dp | 16dp |
| extra_large | 96dp | 108dp | 28dp |

Handle *width* stays a constant 4dp across every size -- the one dimension
of the four the table gives no per-size variation for. Size lives in its
own `StyleSpec.size` field rather than `style.variant`, unlike `Fab`'s own
small/standard/medium/large ladder (`§5.x`, read from `style.variant`) --
`Fab` has no separate M3 "variant" concept of its own, but Sliders do
(Standard/Centered/Range, `COMPONENT_SLIDERS.md`'s own "Variants" section),
and Range is already named as a real, deliberately-deferred future feature
below; folding size into `variant` now would collide with it the moment it
exists. Discrete (stop indicators) and Range (two handles) are real M3
variants, deliberately out of scope -- each is a materially different widget
shape, not a style tweak on this one.

**Not part of the sourced ladder, and not scaled by size**: `cradle_gap`,
`cradle_radius`, the hover/press/focus halo, the circle-handle diameter
(`style.handle_shape: circle`), and this widget's own minimum width --
`COMPONENT_SLIDERS.md` gives no size-dependent figure for any of them, so
each stays the single fixed value it already was before the ladder existed.
A disclosed, known risk rather than an oversight: a 32dp halo sized for a
44dp XS handle may not read right around a 108dp XL one.

Colour roles are not fully specified in the scraped tokens table (an
interactive image, not text -- the same gap `CircularProgress`'s default
diameter has), so this reuses M3's own established selection-control pairing
directly: `primary` for the active track and the handle,
`secondary_container` for the inactive track, the same role `Chip`/`Segment`
already use for "filled and selected". The handle is taller than the track
by design at every size (M3's visual refresh: "a vertical handle that
narrows when pressed", not a circular thumb the way `Switch`'s is).

**All three of M3's own named behaviours are implemented, not just one.**
"Select & drag" (`on_pointer_down` jumps to the press position and starts a
drag; `on_pointer_move` while pressed keeps committing the value under the
pointer, since "Changes made with sliders must take effect immediately", not
only on release) and "Select jump" ("Select a value by selecting part of the
track" -- the identical first frame of a drag here, not a second code path)
share one implementation; "Select & arrow" is `on_key_down` -- Left/Down
decrement, Right/Up increment by `style.step`, Home/End jump to the bound
minimum/maximum, exactly the page's own keyboard table.

`value:` is the current number, the same `ElementMixin.number` property
every other value-bearing widget already reads. `style.min`/`max` bound it
but fall back to 0.0/1.0 when unset rather than `SpinBox`'s "unbounded" --
`StyleSpec.min`'s own docstring states why: an unbounded slider has no track
to draw a handle on. `on_change` fires with the value already clamped and
snapped to the nearest step, the same split `SpinBox._step` and
`TextField._commit` already make between updating the display and telling
the application what changed.

ARIA has a real, dedicated `"slider"` role -- M3's own accessibility page
states it outright ("It should have the slider role"), used directly rather
than approximated.

**Deliberately out of scope**, matching M3's own "optional" anatomy: the
value indicator (a label above the handle while dragging), stop indicators,
the inset icon, and vertical orientation.

**Pluggable handle shapes, pySilver's own -- not M3.** phil asked directly
for a genuinely pluggable handle rather than just the shipped line/circle
pair. `style.handle_shape` also takes `"square"`/`"hexagon"` now, both free
reuses of `Shape`'s own regular-polygon primitive (`DisplayList.
add_polygon`, `sides=4`/`6` -- no new engine work); a new `style.
handle_image:` draws a decoded image as the handle instead, winning over
`handle_shape` when set, via `resolve_image` (factored out of `Image`'s own
`_entry` in `image.py` once this needed the identical resolve/cache/
staleness dance) -- raster only, since Pillow has no SVG decoder and
pySilver has none of its own yet. A true star was asked for and explicitly
dropped rather than approximated: `add_polygon` is strictly a *regular*
polygon (one `sides` count, no alternating inner/outer radius) and cannot
draw a star shape at all; asked phil directly (`AskUserQuestion`) rather
than shipping something star-shaped-but-not-really, and he chose to drop it
over a hexagram workaround or new shader work -- a real, disclosed gap, not
solved here.

### 5.29 Search — `widgets/search.py`

M3's search bar, built new on the shared editing model `TextField`/
`CodeEditor` already use rather than by subclassing `TextField` -- the same
reasoning `CodeEditor`'s own docstring gives: `TextField`'s layout and paint
are saturated with its own chrome (a floating label, an indicator stroke
that thickens on focus, filled/outlined containers) a search bar has none
of. It is always a 56dp pill with a fixed leading icon, always single-line,
different enough anatomy that subclassing would mean overriding nearly
every method.

**Search Bar only -- the expanded "Search View" is deliberately not a
second widget kind.** It is the same shape `Menu`/`MenuItem` already solve:
a results list anchored to a trigger, opened and closed by the
application's own state, composed the same way a `MenuItem` with
`style.has_submenu` anchors its own submenu overlay. No new framework
capability was needed for it.

**Anatomy** (`COMPONENT_SEARCH.md`'s own docked-style measurement table):
56dp height, 16dp leading/trailing padding, a full-pill radius, 360-720dp
width clamped regardless of what a view asks for. Icon size (24dp) and
container colour (`surface_container_high`) follow the same M3 defaults
`IconButton`/`TextField` already use; the exact token is not in the scraped
tokens table (an interactive image, the same gap `CircularProgress`'s own
default diameter has). The floating bar's separate unfocused/focused
padding values are collapsed to one fixed figure -- a stated simplification,
not an oversight.

`value:` is the typed query, `TextField`'s own convention. `supporting_text:`
is a placeholder shown only while empty and unfocused (M3's own anatomy
names this "Supporting text"), not a caption below the field the way
`TextField`'s is. `icon:` names an optional trailing icon -- M3: "A search
bar should have one or two trailing icons" -- unset means the leading
search glyph alone, M3's own stated baseline.

ARIA has a real, dedicated `"searchbox"` role, distinct from `TextField`'s
plain `"textbox"`, used directly rather than approximated.

### 5.30 Split Button — `widgets/splitbutton.py`

M3's split button: a primary action attached to a menu trigger, sized M
only -- XS/S/L/XL are real M3 variants, the same size ladder `Fab` already
models, but a second ladder here is a materially separate piece of work.
The two regions sit 2dp apart (`COMPONENT_SPLIT_BUTTONS.md`'s own
measurements); the touching corners are squared to 4dp while every outer
corner stays fully rounded, so the pair still reads as one pill split in
two -- the closest existing precedent is `SpinBox`'s own two icon-button
regions flanking a number (`material.py`), and `_side_at`/per-side hover
tracking is that same pattern, adapted to two filled regions.

**A real bug, caught by testing, not by inspection: a widget's own method
literally named `on_click` double-fires against a view's `on_click:`
handler.** `EventDispatcher._invoke` (`runtime/events.py`) calls a
view-declared handler for an event type *and*, separately, a same-named
native method on the element, for every dispatched event -- documented
there as deliberate ("some widgets respond to an event natively rather than
through a view-declared handler"), but it means a widget cannot *also* use
that same reserved name to relay to the view's own handler without calling
it twice. First written with a native `on_click` that itself called
`self.handlers.get("on_click")`; a plain click produced two invocations,
caught immediately by a test asserting exactly one. The fix routes both
regions from `on_pointer_down`/`_up` instead (the same fix `Switch`'s own
drag support needed, for the identical underlying reason), dispatching to
two names the framework has no built-in opinion about:
`handlers.on_leading_click` and `handlers.on_trailing_click`. A press and
release that land on *different* regions commit to neither, matching how a
real button behaves when a press is dragged off it before release.

The trailing trigger typically opens a `Menu` overlay anchored to this
widget's own `name` from `on_trailing_click` -- M3's own placement rule
("The menu should be 4dp from the split button") needs no new framework
support, the identical anchor mechanism `MenuItem.style.has_submenu`
already uses for its own submenu.

ARIA has no dedicated role for a compound two-region control; treated the
same opaque way `Pagination`'s own two internal buttons already are.

### 5.31 Date Picker — `widgets/datepicker.py`

M3's modal date picker, single-date selection only -- Modal Input (typed
date with validation) and Date Range (two handles across the grid) are real
M3 variants, each a materially separate piece of work rather than a style
tweak, deferred the same way `Slider`'s own Discrete/Range variants were.

**A plain widget, not a second overlay type.** M3 anatomy calls this
"modal", but the modality itself is `Dialog`'s job -- a view places this as
`Dialog`'s child exactly the way `parts/confirm_dialog_View.yaml` places
`Text`/`Button` inside one, rather than teaching `runtime/overlay.py` a new
overlay shape for what is really just different content.

**Commits immediately on click, with no separate OK/Cancel step.** M3's own
anatomy lists "Text buttons" (OK/Cancel) as part of this widget, implying a
staged "pick, then confirm" flow this pass does not build -- clicking a day
commits `value:` (a `YYYY-MM-DD` string) and fires `on_change` right away, a
stated simplification rather than a silent one. An application wanting a
staged flow gets one for free regardless: `Dialog` is already dismissable,
so "OK" is just closing it once a date has been picked.

**Measurements are not fully sourced** -- `COMPONENT_DATE_PICKERS.md`'s
modal size tables are images, the same gap `CircularProgress`'s default
diameter and `Carousel`'s medium item width already have. 320dp width and
40dp day cells are pySilver's own reasonable choice, tiling seven 40dp
columns with a little margin either side, not a quoted figure.

The calendar grid itself is computed with the standard library's
`calendar` module (leap years, month lengths, weekday offsets) rather than
by hand -- the one part of this widget with a genuinely correct, boring
answer already available, cited rather than reimplemented.

ARIA has no dedicated "datepicker" role; the grid itself uses ARIA's own
`"grid"` role, the closest real anatomy.

### 5.32 Time Picker — `widgets/timepicker.py`

M3's Input variant only. The Dial variant -- dragging a clock hand around a
256dp analog face -- is a real M3 variant but an entirely different
interaction and paint model, deferred the same way `DatePicker`'s own Modal
Input and Date Range were.

**A plain widget, not a second overlay type**, for the same reason as
`DatePicker`: M3 calls this a "Modal time picker", but the modality is
`Dialog`'s job. A view places this as `Dialog`'s own child.

**Stepping, not typing.** M3's own anatomy for the Input variant puts a
keyboard caret inside each field -- the entire point of "Input" versus
"Dial". Real digit entry needs `TextField`'s whole caret/selection/IME
machinery for what would otherwise be a half-built text field wearing this
widget's paint; `SpinBox` already made and stated this exact trade for the
same reason. Each field is instead a stepper: click its top half to
increment, its bottom half to decrement, wrapping (hour 1-12, minute 0-59)
independently of each other -- like two separate `SpinBox`-style fields
rather than one clock with a borrow between them, so decrementing past 12
o'clock does not flip AM/PM on its own.

**Commits immediately, with no separate OK/Cancel step** -- the same stated
simplification `DatePicker` makes. `value:` is a 24-hour `"HH:MM"` string;
clicking any control commits it and fires `on_change` right away.

**Measurements**: the 96×72dp field containers and the 52dp period selector
are `COMPONENT_TIME_PICKERS.md`'s own quoted Input figures. The gaps between
elements and the 8dp field corner radius are not quoted -- the source's
tables give component sizes, not the space between them -- and are
pySilver's own reasonable choice, the same kind of gap `DatePicker`'s 320dp
width and 40dp cells already have.

No dedicated ARIA "timepicker" role exists either; the widget uses `"group"`,
the same fieldset-like grouping ARIA offers for independent adjacent controls.

### 5.33 Button Group — `widgets/buttongroup.py`

Not in `M3_COMPONENT_INDEX.md` at all -- `COMPONENT_BUTTON_GROUPS.md` is a
real, separately-scraped M3 Expressive component with no index entry.
Quoted directly: "Button groups are invisible containers that add padding
between buttons and modify button shape. They don't contain any buttons by
default." That sentence is this widget's entire scope: a `Flex` row that
spaces `Button` children and, for the connected variant, overrides their
corner radii -- nothing paints its own container.

**Spacing.** The source's "between-space" table has one row per size (XS
18dp, S 12dp, M/L/XL 8dp), confirmed against the same page's own scraped
token residue for the XS row (32dp container height, 18dp between-space --
both agree). `STANDARD_SPACING` (8dp) is both the M/L/XL figure and this
group's own pre-ladder legacy value, so an unsized group sees it either way.
Connected groups use a flat 2dp "at every size", quoted directly -- no
ladder applies there at all.

**Connected shape.** "the outer shape is fully round, and the inner shape
remains square with the following corner sizes" -- XS 4dp, S 8dp, M 8dp,
L 16dp, XL 20dp -- read here as: the group's two outward-facing ends stay
fully round, every corner where two buttons meet squares to the
size-appropriate figure. `INNER_RADIUS` (8dp) is both the M figure and this
group's own pre-ladder legacy value, the same "unsized group unaffected"
shape spacing has.

**Shape morph and selection, built.** The round<->square morph itself
lives entirely on `ButtonElement`, not here -- `COMPONENT_BUTTONS.md`'s own
"Corner sizes" table gives exact per-size figures: pressed always morphs to
a size-appropriate corner ("both round and square buttons should have the
same pressed shape"), and a toggle button (`checked`, the same
`value:`-bound convention `Chip`'s filter variant and `Accordion` already
use) rests at a size-appropriate corner when selected instead of full
round. This applies to *every* `Button`, grouped or not -- the source page
describes it as ordinary Button behaviour. `ButtonGroup`'s own, narrower
contribution is what `COMPONENT_BUTTON_GROUPS.md`'s "Selection &
activation" section actually adds: a **standard** group's selected/pressed
button also grows WIDTH (`ButtonElement.GROUP_SELECT_PAD_EXTRA`, not
sourced -- the spec gives no number, only that it happens, and not scaled
by size either since no size-specific figure exists for it at any size),
which visibly shifts every later sibling along the row as an ordinary
consequence of `ButtonGroup` already being a plain `Flex` row -- no new
cross-element layout coupling was built or needed for that. A **connected**
group's own selection changes shape only, per the spec's own "don't add any
interaction between buttons... only affect the shape."

**The XS/S/M/L/XL size ladder, built.** `ButtonElement.SIZES` (`extra_small`
through `extra_large` -- height, horizontal padding, checked/pressed corner
radii) is sourced from the actual annotated diagram at m3.material.io,
fetched live since `COMPONENT_BUTTONS.md`'s own "Padding and size
measurements" section carries no scraped table for it, only an image;
cross-checked against `COMPONENT_BUTTON_GROUPS.md`'s own scraped token
residue for the `extra_small` row (32dp height), which agrees exactly. The
widget's pre-existing single size (40dp height, 24dp padding) turns out to
match neither the real ladder's `"small"` (40dp height, 16dp padding) nor
its `"medium"` (56dp height, 24dp padding) -- a pre-Expressive figure that
predates the 5-size ladder entirely -- so it stays `style.size`'s bare
default rather than being folded into either real row, via the same
`model_fields_set` "explicit beats default" check `SliderElement.
_track_radius`/`DockSplitElement.horizontal` already use. `ButtonGroup` has
no `size:` of its own; it derives its spacing/connected-inner-radius from
the first `Button` child that actually set one, since M3 expects a group's
buttons to share a size ("By default, all buttons in a standard group
should be the same size... Avoid mixing sizes frequently"). `MIN_WIDTH` and
`LABEL_ROLE` are not scaled by size -- no source gives a per-size figure
for either.

`ButtonElement` gained `_group_radii` (`None` by default, so every button
with no `ButtonGroup` parent is unaffected; `effective_radii` checks it
after pressed/checked, before falling back to `style.corner_radius`) and
`_group_standard` (set only by a `standard`-variant `ButtonGroup` parent,
gating the width growth to exactly the groups the spec describes it for).
`IconButtonElement`'s own `effective_radii` is hardcoded to full-round and
does not consult an equivalent override, so a connected group's shape
merging currently applies only to `Button` children, not `IconButton` ones
M3 also allows in a group -- a small, explicitly deferred follow-up.

**Also flagged in the same plan, not built as separate widgets**:

- **FAB Menu** -- `COMPONENT_FAB_MENU.md` states directly, for the target
  platform: "On web, the FAB menu opens from the FAB, and inherits its
  states and specs from the baseline menu component." That is pySilver's
  existing `Menu` overlay, already anchorable above its trigger
  (`style: {placement: top, anchor: <fab-name>, offset: 4}`, the spec's own
  quoted 4dp gap) -- a view composes this today with zero new widget code,
  which is more faithful to M3's own stated web behaviour than a bespoke
  expand/collapse widget would be.
- **Loading Indicator** -- M3 Expressive's shape-morphing replacement for
  indeterminate `CircularProgress`. Deferred: the existing indeterminate
  `CircularProgress` already serves the same functional need, and the
  morphing-shape animation is a materially separate build for a purely
  cosmetic upgrade.

---

## 6. Frame Lifecycle

The authoritative sequence. Every step is skippable when nothing dirtied it.

```text
 0. Wake            rendercanvas scheduler fires (input, timer, or request_draw)
 1. Drain           pop OS + cross-thread event queue; coalesce motion
 2. Dispatch        hit-test -> capture/target/bubble -> handlers write Signals
 3. Notify          flush signal writes -> set needs_build/layout/paint flags
 4. Build           re-evaluate bindings on needs_build Elements; resolve styles
 5. Layout          from each dirty relayout boundary: constraints down, sizes up
 6. Paint           re-emit instances for needs_paint subtrees; splice cached rest
 7. Upload          palette (if theme dirty) | atlas (if new glyphs) | instances
 8. Encode          one render pass, one instanced draw of N instances
 9. Submit          device.queue.submit(); canvas presents
```

Idle costs zero frames. A hover highlight runs steps 0–4, 6–9 and skips layout entirely. A theme toggle runs 0, 3, 7 (palette write only), 8, 9 — no tree traversal at all.

---

## 7. Coordinate Systems and DPI

Three spaces, never mixed implicitly:

| Space | Unit | Used by |
|---|---|---|
| **Logical (DIP)** | Device-independent px | YAML authoring, layout, hit testing, all public API |
| **Physical** | Framebuffer px | Display list, atlas, shader, viewport |
| **Clip** | NDC, −1..1 | Vertex shader output only |

`scale = canvas.get_pixel_ratio()`. Conversion happens at exactly one place — the paint pass, when writing `rect` into the instance array. Layout never sees physical pixels; the shader never sees logical ones.

**Origin is top-left, Y grows downward**, matching every UI convention and both input APIs. The orthographic projection in `Globals` performs the Y flip into NDC, so no other code compensates.

On DPI change or monitor move, `scale` changes: the atlas is invalidated (glyphs were rasterised at the old scale), the display list is fully rebuilt, but **layout is untouched** because it operates in logical units.

---

## 8. Threading and Concurrency

**The engine thread owns everything mutable**: the wgpu device and surface, all four trees, all signals, the atlas. This is not a limitation to work around; it is what makes the invalidation model sound.

Application background work runs as `asyncio` tasks on the same loop that drives `rendercanvas`, so ordinary `async def` handlers need no marshalling. Work on genuine OS threads (blocking I/O, `anyio.to_thread`) must return to the engine thread before touching a signal:

```python
loop.call_soon_threadsafe(my_signal.set, value)
```

`Signal.set` asserts thread affinity in debug builds, converting a latent race into an immediate, located error.

Glyph rasterisation is synchronous in v1. It is a measured candidate for a worker thread (freetype releases the GIL for `FT_Render_Glyph`), deferred until profiling justifies the complexity.

---

## 9. Directory Structure

```text
pySilver/
├── pyproject.toml               # hatchling; project metadata, deps, extras
├── ARCHITECTURE.md
├── README.md
├── src/
│   └── pysilver/
│       ├── __init__.py          # THE public API surface (§10)
│       ├── app.py               # App: view + state + handlers + engine (§6)
│       ├── config.py            # pydantic-settings: PYSILVER_* env overrides
│       ├── spec/
│       │   ├── loader.py        # yaml.safe_load + include resolution
│       │   ├── models.py        # Pydantic Spec tree
│       │   ├── expressions.py   # {{ }} restricted AST — no eval
│       │   ├── include.py       # `source:` view composition (§5.1.1)
│       │   ├── stylesheet.py    # `styles:` rule resolution (§5.17.1)
│       │   └── typescale.py     # M3 type-scale roles (§5.17.7)
│       ├── runtime/
│       │   ├── engine.py        # frame pipeline, canvas/device ownership
│       │   ├── signals.py       # Signal / Computed / Effect, tracking scope
│       │   ├── events.py        # queue, hit test, capture/bubble, focus
│       │   ├── hotreload.py     # watchfiles -> reconcile
│       │   ├── overlay.py       # dialog/menu/tooltip/snackbar/sheets host (§5.13)
│       │   ├── accessibility.py # semantic tree snapshot (§5.11)
│       │   ├── accesskit_bridge.py # optional AccessKit bridge (§5.11)
│       │   ├── clipboard.py     # in-process clipboard, optional system seam (§5.17.6)
│       │   └── viewmodel.py     # per-view-file signal/handler namespace
│       ├── tree/
│       │   ├── element.py       # mutable runtime node
│       │   └── reconcile.py     # keyed diff, state preservation
│       ├── layout/
│       │   ├── constraints.py   # Constraints, Size, Offset, EdgeInsets
│       │   └── algorithms.py    # Box, Horizontal, Vertical, Stack, Scroll, TextBox
│       ├── paint/
│       │   ├── display_list.py  # INSTANCE_DTYPE, painter-order walk, caching
│       │   └── commands.py      # box/glyph/image emitters
│       ├── render/
│       │   ├── pipeline.py      # bind groups, pipeline, render pass
│       │   ├── buffers.py       # ring buffer, growth, uploads
│       │   ├── atlas.py         # skyline packer, LRU, R8 + RGBA8 textures
│       │   └── shaders/
│       │       └── ui.wgsl      # the single universal primitive shader
│       ├── text/
│       │   ├── fontdb.py        # face registry, coverage index, fallback chain
│       │   ├── font.py          # freetype wrapper: rasterise gid -> coverage bitmap
│       │   ├── shaping.py       # uharfbuzz -> ShapedRun (numpy), shaped-run cache
│       │   ├── itemize.py       # bidi (UAX #9) + script runs (UAX #24)
│       │   ├── segment.py       # line breaks (UAX #14), graphemes (UAX #29)
│       │   ├── layout.py        # line assembly, alignment, caret/selection geometry
│       │   ├── editing.py       # EditState + operations, no pixels (§5.9.1)
│       │   ├── selection.py     # point <-> offset mapping (§5.17.6)
│       │   ├── icons.py         # Material Symbols variable-font icons (§5.7.8)
│       │   └── svgicons.py      # arbitrary SVG compiled to glyph outlines (§5.7.9)
│       ├── motion/
│       │   ├── easing.py        # M3 curves + duration tokens (§5.17)
│       │   └── animation.py     # Ticker, retarget-not-restart animations (§5.17)
│       ├── assets/
│       │   ├── __init__.py      # DEFAULT_FONT, MEDIUM_FONT, FALLBACK_CHAIN
│       │   └── fonts/           # BUNDLED fonts — required by golden tests (§11)
│       │       ├── Roboto-Regular.ttf   Roboto-Medium.ttf
│       │       ├── NotoSans-Regular.ttf # fallback tier
│       │       └── LICENSE-*.txt        # OFL 1.1, must ship with the fonts
│       ├── theme/
│       │   ├── tokens.py        # frozen TOKEN_ORDER (versioned!)
│       │   └── palette.py       # materialyoucolor -> float32 palette buffer
│       └── widgets/
│           ├── base.py          # primitives: container, row/column, stack, text, button, icon
│           ├── material.py      # M3 catalogue: card, checkbox, chip, fab, ...
│           ├── navigation.py    # rail (collapsed/expanded, no separate drawer), app bar, tabs, list item, progress
│           ├── overlays.py      # dialog, menu, tooltip, snackbar, sheets
│           ├── scroll.py        # clipped viewport + wheel handling
│           ├── textfield.py     # TextField (§5.9.1)
│           ├── carousel.py      # Carousel + CarouselItem (§5.16)
│           ├── dock.py          # DockSplit / DockGroup / DockPanel (§5.20)
│           ├── dock_drag.py     # Dock's runtime half: drag a tab, drop as a tab or split an edge
│           ├── canvas.py        # Canvas: imperative drawing surface (§5.21)
│           ├── image.py         # Image (§5.22)
│           ├── video.py         # Video: frame-sink widget (§5.23)
│           ├── nodegraph.py     # NodeGraph + Node (§5.24)
│           ├── codeeditor.py    # CodeEditor (§5.25)
│           ├── terminal.py      # Terminal: real PTY spawning (§5.26)
│           ├── pagehost.py      # PageHost: single-active-child container (§5.27)
│           ├── slider.py        # Slider: drag/click/keyboard value picker (§5.28)
│           ├── search.py        # SearchBar: M3 search bar (§5.29)
│           ├── splitbutton.py   # SplitButton: primary action + menu trigger (§5.30)
│           ├── datepicker.py    # DatePicker: modal calendar month grid (§5.31)
│           ├── timepicker.py    # TimePicker: hour/minute steppers + AM/PM (§5.32)
│           └── buttongroup.py   # ButtonGroup: standard/connected spacing + shape (§5.33)
├── examples/
│   ├── hello/            {app.py, view.yaml}
│   ├── counter/          # signals + handlers
│   ├── gallery/          # a real navigation-shell app covering every widget; doubles as the golden-image corpus
│   └── widgets/          # one standalone demo window per widget kind (64), <Name>_View.yaml + _ViewModel.py + app.py each -- the widget-by-widget design review's own corpus
├── tests/
│   ├── test_layout.py           # pure, no GPU — the largest suite
│   ├── test_constraints.py
│   ├── test_signals.py          # dependency tracking, invalidation typing
│   ├── test_reconcile.py        # state preservation across reload
│   ├── test_spec_validation.py  # bad YAML -> good errors
│   ├── test_hit_testing.py
│   ├── test_palette.py
│   └── golden/
│       ├── conftest.py          # rendercanvas.offscreen fixture
│       └── baselines/*.png
└── docs/
```

**This is an installable package, not an application.** The prior root-level `core/` + `app.py` + `view.yaml` layout describes a program that happens to have a UI; `src/pysilver/` plus `examples/` describes a framework other people can depend on.

---

## 10. Public API Surface

Everything not re-exported from `pysilver/__init__.py` is private and may change without a major version bump. The v1 surface is deliberately small:

```python
from pysilver import App, Signal, Computed, Theme, run

theme = Theme(seed="#6750A4", dark=True)
app = App("view.yaml", theme=theme)

count = Signal(0)


@app.handler
def increment(event):
    count.set(count.get() + 1)


app.expose(count=count)  # names visible to {{ }} expressions
run(app)
```

Semantic versioning applies to this surface, to the YAML schema, and to `TOKEN_ORDER`. The YAML document carries a `version:` key so the loader can migrate or reject old documents explicitly.

---

## 11. Testing Strategy

The architecture was shaped partly by testability; this is the payoff.

| Layer | Approach | GPU? |
|---|---|---|
| Layout | Direct `Constraints` in, `Size` out. **Hypothesis** property tests over randomly generated trees (avg ~10 nodes, up to 49, depth 5) assert the invariant *a node's size depends only on its constraints and children* — by moving every node and re-laying out, then requiring identical sizes. Also: every layout result satisfies its constraints, layout is deterministic, and flex distribution sums exactly. | No |
| Signals | Assert exact invalidation sets: which Elements dirtied, and with which flag. Catches over-invalidation, which is silent but is the main performance risk. | No |
| Reconciliation | Reload a mutated Spec; assert scroll/focus/text state survived. | No |
| Spec validation | Malformed YAML corpus; assert error type, key path, and line number. | No |
| Hit testing | Synthetic trees with overlaps and clips; assert the hit path. | No |
| Intrinsic size | Lay every `WidgetKind` out with **no style at all** under loose constraints; assert a real size, with the legitimately-empty kinds listed individually alongside the reason. Every other suite hands its widgets an explicit size, so this is the only thing exercising the path. | No |
| Text pipeline | Shaping against the **bundled** font: assert glyph IDs, advances, cluster mapping. Fallback chain resolution. Break opportunities and grapheme counts against UAX test data. | No |
| Rendering | `rendercanvas.offscreen` → render → read texture → compare against a **committed baseline PNG**. Tolerance is 4/255 per channel with at most 0.2% of pixels allowed to exceed it — an exact match would be unmaintainable across drivers, anything looser stops catching real changes. `examples/gallery` is the corpus, plus an **unsized-widget** baseline that gives nothing a size and so catches a widget that draws nothing. | Yes |
| Shader | Covered indirectly by goldens. WGSL is kept small and branch-light for this reason. | Yes |

The overwhelming majority of the framework's logic is testable in CI with no GPU, on any runner. Golden tests run on a Linux runner with `lavapipe` (software Vulkan) for determinism, and are the only tests permitted to be platform-conditional.

**Every text test uses the bundled font, never a system font.** Shaping output, advances, and rasterised coverage all vary between font versions, so a test that resolves `"sans-serif"` through the OS produces different bytes on every machine and every CI image. This is the second architectural reason the default font is bundled (§5.7.2), and it is why system font discovery stays out of the golden path even after it ships.

---

## 12. Performance Budget

At 60fps the whole frame is **16.6ms**, and the realistic constraint is Python, not the GPU. Targets for a 1000-visible-element interface:

| Step | Budget | Strategy |
|---|---|---|
| Event dispatch | 0.5 ms | Coalesce motion; hit-test path, not full tree |
| Build (dirty only) | 1.0 ms | Fine-grained signals; typically <10 elements |
| Text (dirty only) | 1.5 ms | Three-level cache (§5.7.4); static labels cost zero |
| Layout (dirty only) | 2.0 ms | Relayout boundaries; typically a small subtree |
| Paint (dirty only) | 2.0 ms | Cached subtree instance slices, spliced |
| Upload | 1.0 ms | One contiguous `write_buffer` from numpy |
| Encode + submit | 0.5 ms | One pass, one draw |
| **Headroom** | **~8.1 ms** | |

Two rules follow directly and are non-negotiable in review:

1. **No per-widget Python in the steady state.** A frame in which nothing changed must execute zero tree traversals. The idle cost of a pySilver app is a sleeping event loop.
2. **Display-list assembly is vectorised.** Instances are written into preallocated numpy slices. A per-widget Python loop appending to a list will not meet this budget and is the first thing to check when it is missed.
3. **No text is shaped twice.** HarfBuzz itself is fast C, but building buffers and marshalling results is Python, and shaping is the single most expensive text operation. A shaped-run cache miss on unchanged text is a bug, and is asserted against directly in tests.

A benchmark harness (`tests/bench/`) tracks steady-state idle cost, single-property invalidation cost, and full-rebuild cost, and is run per release.

### 12.2 Text measurements (M4)

Measured on the reference machine. The text budget from the table above is 1.5 ms:

| Path | Median | Verdict |
|---|---|---|
| Layout, warm cache | **0.001 ms** | ✅ |
| Cached subtree splice (static text) | **0.003 ms** | ✅ |
| Emit ~1000 glyphs, vectorised | **1.77 ms** | ⚠️ worst case only |
| Emit ~1000 glyphs, scalar (before optimisation) | 4.26 ms | ❌ replaced |
| Layout, cold cache (43 chars, wrapped) | **1.92 ms** | ⚠️ one-time per string; was 4.89 before §5.7.1 |
| Wrap, 351 chars on one 3840 px line | **12.8 ms** | ✅ was 107.9; the cost no longer scales with line width |

Two things this establishes:

1. **The M2 lesson repeats exactly.** The first `emit` wrote instances one glyph at a time and cost 4.26 ms per 1000 glyphs — over budget, for the same reason scalar box emission was. Collecting into arrays and writing whole columns (`DisplayList.add_glyphs`) cut it to 1.77 ms. §12 rule 2 is not specific to boxes.
2. **Steady state is essentially free.** A frame whose text has not changed costs 0.003 ms, because the display-list subtree cache turns it into a `memcpy`. The 1.77 ms figure is the pathological case of a thousand glyphs *all changing at once*, which no realistic interface does.

The remaining per-glyph cost is `Paragraph.placements()` allocating one object per glyph. Returning arrays instead would remove it; not done, because the cache makes it invisible in practice.

### 11.1 Regenerating golden baselines

```bash
PYSILVER_REGEN_GOLDEN=1 .venv/bin/python -m pytest tests/golden -m gpu
```

**A regeneration run fails on purpose whenever it writes a file.** A baseline
that silently rewrote itself to match the current output would assert nothing;
forcing a failure means the new image has to be looked at and committed
deliberately. On a mismatch the harness writes `actual` and `diff` images to
`tests/golden/failures/` (gitignored) so the change can be seen rather than
guessed at.

### 12.1 First measurements (M2)

Measured on the reference machine, 1000 instances, integrated GPU over Vulkan:

| Path | Median | vs 2 ms paint budget |
|---|---|---|
| Scalar emit — per-widget Python loop | **3.27 ms** | ❌ **over budget** |
| Vectorised emit — numpy bulk write | **0.020 ms** | ✅ 165× faster |
| Cached subtree splice — memcpy | **0.002 ms** | ✅ 1451× faster |
| Full frame, 1000 instances, one draw call | 0.47 ms | includes upload + readback |
| Full frame, 0 instances (clear only) | 0.30 ms | — |

**R1 is confirmed, and the mitigations work.** Two conclusions follow, and neither is now a matter of opinion:

1. **The GPU is nearly free; Python is the whole cost.** Drawing 1000 instances costs roughly **0.17 ms** of GPU time (0.47 minus the 0.30 ms clear baseline). The Python that *assembles* those same instances costs **3.27 ms** — about **19× more than the work it feeds**. Every future performance decision should start from this ratio.
2. **The naive path genuinely does not fit.** Scalar per-widget emission exhausts the entire 2 ms paint budget at roughly **610 instances** — well below a realistic interface. This is precisely why §12 rule 2 is written as a hard rule rather than advice, and why display-list assembly is specified as numpy from the start.

The subtree cache is the strongest lever available: reusing a clean subtree's instance slice is a `memcpy` at 0.002 ms, three orders of magnitude cheaper than rebuilding it. That validates the four-tree model's cached `instances` field (§4) as a performance necessity, not a convenience.

---

## 13. Risks and Open Questions

| # | Risk | Severity | Mitigation / status |
|---|---|---|---|
| R1 | Python frame budget insufficient at high element counts | High | Retained mode + typed invalidation + numpy paint are all aimed here. Benchmark early, at M2, not at M6. |
| R2 | ~~Text scope creep~~ | **Closed** | **Delivered in M4.** Shaping, fallback, segmentation, itemisation, atlas, and paragraph layout all ship and are tested. R9 (RTL caret semantics) is also closed; the quadratic wrap in §5.7.1 is closed. |
| R3 | `wgpu-native` backend variance across Vulkan/Metal/DX12 | Medium | Keep WGSL conservative; golden tests per platform; no optional GPU features. |
| R4 | Single draw call broken by a future feature | Medium | Stated as a design constraint (§1.3). Clipping already solved analytically; transforms and blend modes are the next pressure points. |
| R5 | IME / CJK text *input* unsupported | Medium | **Open, investigated 2026-09-09, deliberately staying blocked.** GLFW itself ships zero IME support in any released version — the upstream fix (glfw/glfw#2130) is unmerged with no ETA, and even once merged its first working platform is Win32 only (macOS/X11/Wayland follow). Confirmed empirically: the installed GLFW (3.5.1) and `pyglfw` binding expose no IME-related symbol at all. rendercanvas's Qt backend is closer (Qt itself has full native IME support) but still gapped: `QRenderWidget.inputMethodEvent()` forwards only `commitString()`, silently drops `preeditString()`, and never implements `inputMethodQuery()` (needed for candidate-window placement) — a rendercanvas contribution would be needed even after adding Qt as a dependency, which pySilver deliberately does not want to do for one feature. phil's explicit call (`AskUserQuestion`): stay blocked rather than add a heavy GUI-toolkit dependency or build three platform-specific native IME bridges (XIM/IBus, IMM32, NSTextInputClient) to duplicate GLFW's own stalled effort. Note this is input only — CJK *rendering* is covered by Tier 1. |
| R9 | ~~RTL caret/selection semantics (Tier 3)~~ | **Closed** | **Resolved.** `text/bidi.py` drives real UAX #9 embedding-level resolution; `EditState.affinity` disambiguates a boundary offset; `Editor.move()` steps through a precomputed global visual ordering rather than an incremental heuristic (an earlier incremental design oscillated forever near a boundary, caught by live testing before it shipped); `rects_for` emits multiple rects for a selection crossing a direction boundary. `NotoSansArabic-Regular.ttf`/`NotoSansHebrew-Regular.ttf` are bundled so this is demonstrable without a system font. See §5.7.7 Tier 3. |
| R10 | ~~Bundled font licensing and size~~ | **Closed** | **Resolved.** Roboto and every bundled Noto family are **SIL OFL 1.1**, compatible with MIT, with licence texts redistributed alongside them (§5.7.2). Note Roboto was *relicensed*: builds predating its move to `ofl/` in `google/fonts` — including the v2.137 copy some distributions still ship — are Apache-2.0 instead. Size resolved at ≈3.8 MB by instancing static faces and bundling only small per-script Noto members (Latin/Greek/Cyrillic, Arabic, Hebrew), nowhere near the omnibus multi-script build's own PyPI-cap-busting size. |
| R6 | ~~No accessibility tree~~ | **Closed** | **Delivered.** `runtime/accessibility.py` builds the semantic tree from the Element tree as reserved; `runtime/accesskit_bridge.py` pushes it to AT-SPI through AccessKit and was verified against a live screen reader. Windows and macOS need their own AccessKit platform wheels and are untested here, which `available()` reports rather than leaving to be discovered. |
| R7 | Over-invalidation silently costs frames | Medium | Tested directly (§11) rather than left to profiling. |
| R8 | Atlas thrashing under many fonts/sizes | Low | LRU + skyline; budgeted at 2048², growable to 4096². |

---

## 14. Milestones

| M | Deliverable | Proves |
|---|---|---|
| **M0** ✅ | `pyproject.toml`, package skeleton, CI matrix, `theme/` complete, a window that clears to an MD3 surface colour | **Done.** 33 tests green (5 on GPU), `ruff` clean, `mypy --strict` clean across 17 files |
| **M1** ✅ | `layout/` — constraints algebra, boundary/caching protocol, `LayoutOwner`, and `Padding`/`Align`/`SizedBox`/`ConstrainedBox`/`Horizontal`/`Vertical`/`Flex`/`Stack`/`Spacer`. No rendering. | **Done.** 129 tests green, including Hypothesis property tests over random trees asserting the size invariant |
| **M2** ✅ | Instanced pipeline + `ui.wgsl`: rounded boxes, per-corner radii, borders, shadows, analytic AA, rounded shader clipping, palette tokens. **First benchmark.** | **Done.** 180 tests green (24 GPU); 500 mixed primitives verified as one draw call; **R1 quantified — see §12.1** |
| **M3** ✅ | `spec/` (Pydantic + sandboxed expressions), `runtime/signals.py`, `tree/` (element + reconcile), `runtime/events.py`, `widgets/`, and the public `App` | **Done.** 293 tests green. Full slice works: YAML → elements → layout → paint → click → signal → re-render, with state-preserving reload |
| **M4** ✅ | `text/` — Face/FontDB with coverage fallback, uharfbuzz shaping with a size-independent cache, bidi + script itemisation, UAX #14/#29 segmentation, paragraph layout with wrapping and alignment; `render/atlas.py` skyline packer; real `Text`/`Button` labels | **Done.** 371 tests green. Shaped, kerned, ligature-forming Roboto renders through the atlas in the same single draw call |
| **M5** ✅ | `runtime/hotreload.py` (watchfiles → engine thread), golden-image suite with six committed baselines, `examples/gallery` | **Done.** 390 tests green. Editing a view file updates the window without losing click count, focus, or scroll |
| **M6** ✅ | API freeze, `docs/view-reference.md`, `LICENSE`, packaging metadata, reproducible sdist/wheel | **Done.** 893 tests green. The public surface is pinned by `tests/test_public_api.py`; the reference is pinned by `tests/test_docs.py`, which fails when a widget, style property, node field, or handler key is added without documenting it. The wheel installs into a clean environment and renders text, icons, arcs, a carousel, and a modal overlay with no source tree present. **Publishing to PyPI is a separate, explicit step and has not been done.** |
| **M7** ✅ `1.1.0` | `motion/` — the animation system, and its use across the widget set: Switch and indeterminate progress, overlay fades, state-layer cross-fades, the carousel snap, selection controls, tab and navigation indicators, the collapsing app bar, carousel parallax | **Done.** 944 tests green. Motion is a property of the widget rather than of each call site, so a widget cannot forget `reduce_motion` |
| **M8** ✅ `1.2.0` | Styling and interaction: the stylesheet and cross-file sharing, disabled state, M3 elevation levels, right-click context menus, cursor shapes, mouse text selection, drag gestures, **the M3 type scale** (size, weight, tracking, line height), separated hit and paint rects, and the `TextField` | **Done.** 1316 tests green. The type scale is sourced from material-web rather than invented — the scraped token tables were empty and the scattered values disagreed with themselves. Hit rects separate from paint rects, so M3's 48dp touch target no longer implies a 48dp button |
| **M9** ✅ `1.3.0` | Platform integration: the resize investigation and its reversal (§5.8.1), `vsync` defaulting to False, server-side decorations, the **system clipboard**, multi-line text entry, explicit modal-dialog semantics, and **per-file ViewModels** | **Done.** 1362 tests green. A view file still cannot decide what Python is imported: `_View.yaml`/`_ViewModel.py` naming is enforced, binding is explicit, and `app.py` stays the entry point rather than the logic holder |
| **M10** ✅ `1.4.0`–`1.5.0` | Accessibility: `runtime/accessibility.py` (the semantic tree, `1.4.0`) and `runtime/accesskit_bridge.py` (AT-SPI through AccessKit, `1.5.0`) | **Done.** 1392 tests green, and verified against a live screen reader rather than only against the tree it would be handed. Windows and macOS need their own AccessKit platform wheels and say so instead of pretending |
| **M11** ✅ | Correctness and latency: intrinsic widget sizes locked in by golden and by assertion, the quadratic line wrap closed (§5.7.1), and the swapchain pinned during a resize (§5.8.1) | **Done.** The pointer trailing on Wayland is gone — the swapchain rebuild it came from is amortised, after the note saying that was impossible turned out to be wrong. Did not touch the view format or `__all__`, so no version moved for it |
| **M12** ✅ `1.6.0` | The desktop widget catalogue: sixteen widgets with no M3 catalogue entry of their own — `Popover`, `Accordion`, `TreeView`/`TreeItem`, submenu support for `Menu`/`MenuItem`, `Link`, `SpinBox`, `Pagination`, `StatusBar`, `DockSplit`/`DockGroup`/`DockPanel` (§5.20), `Canvas` (§5.21), `Image` (§5.22), `Video` (§5.23), `NodeGraph`/`Node` (§5.24), `CodeEditor` (§5.25), and `Terminal` (§5.26) — plus SVG icon compilation. Two new optional extras, neither a hard dependency: `pysilver[code]` (Pygments syntax highlighting) and `pysilver[terminal]` (`pyte`/`pexpect`, POSIX only). A full-codebase review (60 subagents, four phases, `docs/CODE_REVIEW_2026-09.md`) ran alongside it | **Done.** 1917 tests collected. Genuinely cross-cutting bugs found and fixed along the way, not scoped to one widget: a `repeat=True` `Ticker` animation leak, `PaintContext` clones silently dropping `images` at nine clip sites, three hot-reload no-ops (overlays never rebuilt, `image_atlas` never threaded to them, a `watchfiles` enum-casing miss), a `Signal.set` ordering race, and literal (non-token) display-list colours being written as sRGB when the render target treats them as linear, washing out every one that was not re-derived from a palette token |
| **M13** ✅ | A real navigation-shell redesign of `examples/gallery`: `PageHost` (§5.27, a genuine single-active-child container, not a workaround), `CodeEditor.read_only` (§5.25), and a `NavigationRail`/`NavigationDrawer` `collapsed:` field, all built for it rather than speculatively. The gallery itself became seven pages behind a collapsible rail/drawer, each with real M3-grounded documentation prose and a read-only Python code sample. Alongside it, the resize-trailing report was traced past two real-but-tangential fixes to its actual cause: `rendercanvas.glfw`'s uncoalesced per-native-event synchronous repaint, fixed by rate-limiting `RenderCanvas._on_size_change` at the class level before any canvas is constructed | **Done.** 1944 tests collected. Two things assumed from the plan and found wrong by testing rather than by reading: `style.width` cannot be `{{ }}`-bound (state fields like `disabled:`/`collapsed:` can; style fields are load-time only), and a zero-size *clip* rect is this codebase's own sentinel for "unclipped," not "clip away everything" — a collapsed rail's children needed `paint()` skipped outright, not clipped to nothing |
| **M14** ✅ `1.7.0` | The widget-by-widget design review: a standalone one-window demo for all 64 widgets (`examples/widgets/`), then a systematic live pass over each against its M3 source — offscreen render, cross-check, fix-or-defer, live native window per widget by request. Real, previously-invisible bugs found and fixed along the way rather than scoped to one widget: keyboard typing silently broken in every live window since the framework's first commit (`rendercanvas`'s "char" event carries `data`, not `char`); all **eight** overlay-trigger demos (Dialog, Menu, Snackbar, BottomSheet, SideSheet, Popover, Tooltip, SplitButton) declaring their overlay as a plain nested child instead of under `overlays:`, so it rendered permanently inline; `ListItem`'s leading icon never laid out at all; `Snackbar`'s action label painted but never hit-tested; `Stack` ignoring each child's own `align_x`/`align_y`; `Menu` filling the offered width instead of shrink-wrapping to its widest item; plus outlined-`TextField` label/border and caret bugs, `DatePicker`/`Tabs`/`TopAppBar`/`DockGroup` indicator and label-overlap fixes, and `Node`'s title-bar cursor crashing the app on hover. `NavigationRail`/`NavigationDrawer` merged into one widget with two animated states, matching M3 Expressive's current model (`WidgetKind.NAVIGATION_DRAWER` removed, no alias). The review's own punch list then shipped as real features: `TEMPLATED_FIELDS` collapsed nine hand-wired bindable-field call sites into one registry, and added `icon:`/`label:` on top of it (migrating `Icon`/`IconButton`/`Fab`/`NavItem`/`SearchBar` off overloaded `text:`/`supporting_text:`); `Tab`, `Dialog`, and `MenuItem` gained icon anatomy on those same fields; `Tab` also gained a `badge:` field (`style.badge_variant`: `numbered`/`dot`) that overlaps a stacked icon's own corner or trails a label-only/inline tab with a 4dp gap, closing the widget-review backlog's last open item; `ButtonGroup` gained M3's shape-morph (press → 12dp, selected → 16dp, for every `Button` app-wide) and toggle selection, including a standard group's selected button widening and shifting its siblings — an ordinary `Flex` reflow consequence, no new cross-element coupling needed; `Slider` gained its full XS–XL size ladder (`style.size`) and pluggable handle shapes (`square`/`hexagon` via `Shape`'s own polygon primitive, plus a raster `handle_image:` — a true star was asked for and deliberately dropped, since the polygon primitive can only draw regular shapes); `Snackbar` gained its `style.auto_dismiss` timer, gated to actionless snackbars per M3's own rule; and `Dock` gained the runtime half it had shipped without — dragging a tab into another group as a new tab, or onto an edge to split a pane, via a new element-to-dispatcher seam and an `OverlayHost.push_transient` escape hatch for the drag ghost. Also landed in this stretch: held-key repeat synthesized at the `App` level (`rendercanvas`'s GLFW backend drops OS key-repeat, breaking Backspace/Delete/arrows everywhere), and `Terminal` moved off `pyte` onto `bittty` after a real `pyte` parsing defect corrupted typed input under zsh-syntax-highlighting (scrollback dropped as a disclosed, to-be-reimplemented regression) | **Done.** 2365 tests collected. A `curve="standard"` M3 easing curve's derivative flattening near its endpoint can silently eat an `Animation.on_change` completion callback — the exact bug in `Snackbar`'s own auto-dismiss timer, found by tracing a real run where the countdown finished but never fired; fixed with `curve="linear"` for any one-shot completion timer built the same way |

---

## Appendix A — Bootstrap and M0 Findings

Three things surfaced while building M0 that belong in the record:

- **Surface formats differ by canvas.** The GLFW window reports `bgra8unorm-srgb`; the offscreen canvas reports `rgba8unorm-srgb`. Clear values and shader output are written in logical RGBA order either way, so nothing in the framework compensates — but golden tests read pixels back and must therefore run **offscreen only**, where channel order is known.
- **`requires-python = ">=3.12"`**, not 3.14. Nothing in the stack needs 3.14, and restricting a distributable framework to the newest interpreter costs most of its audience. Only 3.14.6 is verified locally; the CI matrix (3.12/3.13/3.14 × Linux/macOS/Windows) is what actually proves the floor.
- **`py.typed` is required.** Without the marker, `mypy` refuses to check the installed package at all and downstream users get no types from a fully-annotated library.

### A.1 Minimal bootstrap

The minimal M0 program. This was **executed** against the installed stack (Python 3.14.6, wgpu 0.32.0, rendercanvas 2.7.2): it acquires an adapter and device, reports `rgba8unorm-srgb` as the preferred format, and renders a frame whose pixels read back correctly. Contrast with the prior draft's `wgpu.gui` import and hand-rolled loop, neither of which functions on wgpu 0.32.0.

```python
import wgpu
from rendercanvas.glfw import RenderCanvas, loop
from materialyoucolor.hct import Hct
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot
from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors


def srgb_to_linear(c: float) -> float:  # see 5.6.1 - required
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


scheme = SchemeTonalSpot(Hct.from_int(0xFF6750A4), True, 0.0)
r, g, b, a = MaterialDynamicColors.surface.get_rgba(scheme)  # class, not instance
surface = (*(srgb_to_linear(v / 255) for v in (r, g, b)), a / 255)

canvas = RenderCanvas(
    title="pySilver",
    size=(1024, 768),
    update_mode="ondemand",
    min_fps=0,
    max_fps=60,  # replaces the manual loop
)
adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
device = adapter.request_device_sync()
context = canvas.get_context("wgpu")
context.configure(device=device, format=context.get_preferred_format(adapter))


def draw_frame() -> None:
    encoder = device.create_command_encoder()
    rp = encoder.begin_render_pass(
        color_attachments=[
            {
                "view": context.get_current_texture().create_view(),
                "clear_value": surface,
                "load_op": wgpu.LoadOp.clear,
                "store_op": wgpu.StoreOp.store,
            }
        ]
    )
    # M2: bind pipeline, bind group 0, quad VB + instance VB, one instanced draw
    rp.end()
    device.queue.submit([encoder.finish()])


canvas.request_draw(draw_frame)
loop.run()
```

Swapping `rendercanvas.glfw` for `rendercanvas.offscreen` and calling `canvas.draw()` instead of `loop.run()` returns the frame as a `(h, w, 4)` array — this is verified working, and is the mechanism the golden-image suite is built on (§11).

## Appendix B — Changes from the Original Plan

The original `architectural_plan.md` has been superseded by this document and removed. Its substance is preserved below as a record of what changed and why.

| Area | Prior plan | Now | Why |
|---|---|---|---|
| Canvas | `wgpu.gui.glfw.WgpuCanvas` | `rendercanvas.glfw.RenderCanvas` | `wgpu.gui` does not exist in wgpu 0.32.0 |
| Adapter/device | `request_adapter()`, `request_device()` | `*_sync()` variants | Async by default in wgpu-py |
| Event loop | Hand-rolled `while` + `glfw.poll_events()` + `sleep` | rendercanvas scheduler, `ondemand` | Existing scheduler; manual polling double-pumps |
| Dirty state | One global `_is_dirty` | Typed per-element `build`/`layout`/`paint` | Global flag redraws everything on any change |
| UI tree | Pydantic `WidgetNode` used as live tree | Four-tree model (§4) | Pydantic models cannot hold runtime state |
| Hot reload | Re-parse and replace | Reconcile with state preservation | Replacement wipes focus, scroll, text on every save |
| Layout | One sentence, no module | `layout/` — Flutter constraints, boundaries | The core subsystem; needs a design and tests |
| Bindings | MVVM claimed, none present | `signals.py` + `{{ }}` + handler registry | The claim now has an implementation |
| MD3 colours | `MaterialDynamicColors()` instance | Class attributes | It is a class of class attributes |
| Theme storage | Per-widget RGBA arrays | Palette buffer + `u32` indices | Theme change becomes one buffer write |
| `children` | Nested under `style:` | On `WidgetSpec` | Children are structure, not styling |
| Clipping | Unaddressed | Analytic, in-shader, rounded | Scissor rects would split the draw call |
| Text | "freetype does layout" | Five-package pipeline (§2.3.1, §5.7), all verified | freetype rasterises; it does not shape, break, or reorder |
| Shaping | Deferred to v1.1 | **In v1** via `uharfbuzz` | Dependency proven on 3.14; GPOS kerning and ligatures confirmed working |
| Bidi / RTL | "post-1.0" | Rendering and editing both shipped | `python-bidi` drives real UAX #9 embedding levels; caret affinity and multi-rect selection close the editing half too |
| Font fallback | Unaddressed | `FontDB` coverage index, per-grapheme resolution | DejaVu Sans covers neither CJK nor emoji — fallback is required, not optional |
| Default font | Unaddressed | Bundled with the package | Golden tests cannot be deterministic against system fonts |
| Colour emoji | Unaddressed | Routed to the RGBA8 image atlas as kind=2 | Colour bitmaps do not belong in an R8 coverage texture; needs no shader change |
| `numpy` | Unlisted, used | First-class dependency | It is the instance-buffer representation |
| Colour space | Unaddressed | sRGB→linear on palette upload (§5.6.1) | Measured: `surface` rendered (69,64,75) instead of (15,13,18) |
| Power pref | `"low-power"` | `"high-performance"` | Picks the discrete GPU on hybrid laptops |
| Layout on disk | `core/` + root `app.py` | `src/pysilver/` + `examples/` | It is a distributable framework |
| Testing | Absent | §11, GPU-free majority + goldens | Shaped the architecture, not bolted on |
