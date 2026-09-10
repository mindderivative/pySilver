# Lessons Learned

A working record of what pySilver's development has taught us: bugs and their
root causes, decisions and why they were made, and what's been deliberately
deferred. This is a *summary index*, not the full detail — each entry says
where the complete account lives (a commit, an `ARCHITECTURE.md` section, or
a Claude Code memory/graph entity) so this document doesn't drift out of
sync with those sources.

**How to use this doc:** skim the headline, follow the reference if you need
the full reasoning before touching the same area again. Don't copy detail
back into this file — that's the exact duplication problem the project's own
memory-graph split (`CLAUDE.md`'s Memory policy, `memory-policy` in the
project's Claude memory) exists to prevent.

---

## 1. Architecture decisions (load-bearing, don't relitigate without reading the reasoning)

| Decision | Chosen over | Why |
|---|---|---|
| **Four separate trees** — Spec → Element → Layout → display list | Collapsing any two into one | Each tree changes at a different rate and for a different reason (a YAML edit vs. a resize vs. a repaint); collapsing them couples invalidation across unrelated causes. |
| **Flutter-style constraint layout** | Flexbox, Cassowary (constraint solver) | See `ARCHITECTURE.md` and the graph entity `pySilver Architecture` for the full comparison. |
| **Fine-grained signals with typed invalidation** (build / layout / paint) | A single "dirty" bit | Lets a colour change skip layout entirely and a resize skip re-running view logic. |
| **One instanced GPU draw call**; clipping is a second SDF evaluation in-shader, never a scissor rect | Per-widget draw calls, scissor-based clipping | Keeps the framework GPU-cheap even with many widgets — see [Performance findings](#5-performance-findings). |
| **Logical DIPs**, converted to physical pixels exactly once, in paint | Converting at multiple layers | Makes M3's `dp` figures map 1:1 into pySilver's `width`/`height`/`font_size`. |

Full reasoning for each: `ARCHITECTURE.md` (repo authority) and the graph
entity `pySilver Architecture`.

**Naming/versioning decisions:**
- `pysilver` is a **phase codename**, not the framework's final identity — a
  rename to `pySilver` then `pyGold` is planned, with a separate name for
  the stable release. It is **not registered on PyPI** and publishing it
  would burn a name meant to be temporary — raise this explicitly before
  any upload. `Development Status :: 4 - Beta` is *correct* even at v1.x —
  the classifier tracks the phase, the version tracks the frozen API
  contract. Don't "fix" this apparent mismatch.
- Commit identity is `phil <8371612+mindderivative@users.noreply.github.com>`
  — history was rewritten once (2026-09-01) to scrub a personal address from
  31 commits; don't "fix" it back.
- The 17-widget backlog set out at M12 is **fully complete** as of Terminal
  (2026-09-04). Only Windows/macOS accessibility-bridge platform gaps and
  the RTL/IME tier remain open on the original roadmap.

---

## 2. Process & workflow decisions

- **Commit automatically** once a milestone/feature is finished and
  verified — no need to ask first (superseded the earlier "never commit
  unless asked" convention on 2026-08-29, per direct request). **Pushing to
  a remote stays a separate, explicit ask every time**, and isn't implied
  by the commit policy.
- **Standard per-milestone shape**: build → `ruff check` + `ruff format` +
  `mypy --strict` + `pytest -q` all green → fold findings into
  `ARCHITECTURE.md` → commit with a descriptive message matching `git log`'s
  existing style. A rendering-affecting fix regenerates *and visually
  inspects* the golden baseline before accepting — never accept a pixel
  diff without looking at it.
- **Record deviations from the documented design honestly**, in
  `ARCHITECTURE.md` itself, rather than leaving the doc quietly wrong (e.g.
  the quadratic line-wrap note in §5.7.1).
- **When several valid next steps exist and none is mandated, pick the most
  reasonable one and proceed** — don't ask permission to use tools or to
  start work already requested. Reserve questions for genuine ambiguity in
  *what* was asked, not *which reasonable option* to start with.
- **Verify a `git push` actually landed** — its own success output isn't
  proof. A later `git fetch` once showed `origin/main` sitting at an
  *ancestor* of what a prior push output claimed had landed (root cause
  never identified — possibly a concurrent session or an external
  force-push). No work was lost, but `git fetch` + comparing
  `git rev-parse main` / `origin/main` after a push is cheap insurance
  before telling anyone something is pushed.
- **Never `git commit --amend`**, even to fix a mistake made in the same
  turn — always a new, clearly-labeled commit instead (applied even when a
  `git add` with an invalid pathspec silently failed and produced a commit
  whose message didn't match its tiny actual diff — fixed with a labeled
  follow-up commit, not an amend).
- **When phil says a fix is real but doesn't address what he actually
  reported, stop defending the fix and go one layer further out** — a
  different subsystem, or a cheap decisive cross-check (a different app
  doing the same action) — rather than adding more instrumentation to the
  same layer. See [§4](#4-debugging-methodology-lessons) for the resize
  saga this came from.

---

## 3. Verify-empirically: the standing rule

**Never assert library behaviour, M3 specs, or performance properties from
model recall on this project — run it, read the reference file, or
benchmark it.** This has repeatedly caught real errors confident recall
would have shipped:

- `wgpu.gui` no longer exists in `wgpu` 0.32 (removed).
- An *empty* `ShapeCache` is falsy, so `cache or ShapeCache()` silently
  discarded a real (but empty) cache.
- Only *two* non-empty `__slots__` bases conflict — a `__slots__ = ()` mixin
  was unnecessary paranoia.
- Roboto was **relicensed** from Apache-2.0 to OFL 1.1 — a remembered
  licence was stale.
- The MD3 `surface` token rendered as `(69,64,75)` instead of `(15,13,18)`
  because of double sRGB encoding — traced by actually sampling pixels, not
  reasoning about the shader.
- `watchfiles.Change.name` is **lowercase**, not `"DELETED"` — two call
  sites compared against the uppercase literal and their branch never fired.
- `rendercanvas`'s GLFW backend submits `{"data": ..., "char_str": ...}` for
  a "char" event, not `{"char": ...}` — the framework read `event["char"]`
  everywhere, so **every keystroke into every live TextField, since the
  framework's first commit, was silently dropped.** Fixed in
  `src/pysilver/app.py`'s `_on_canvas_event` (`event.get("data", "")`);
  found only by instrumenting a live window and printing the real payload.

**A stated *limitation* deserves the same probe as a stated *behaviour* —
especially one already written into the record**, because a negative claim
never fails a test and can stand for milestones unchallenged:

1. `ARCHITECTURE.md` once claimed *"there is no system clipboard... the
   only route is the backend's private `canvas._window`"*. Wrong — GLFW's
   clipboard functions accept `None` for that parameter. Shipped in M9.
2. It also claimed *"pySilver has no seam at which to hold a stale
   swapchain."* Wrong — `GPUCanvasContext.set_physical_size` is public API
   documented for exactly that. Pinning it removed ~35x of resize-acquire
   cost and the pointer-trailing symptom in M11.

**Exact-match string edits silently miss after `ruff format` reflows a
file** — happened four separate times, each producing an unapplied "fix"
followed by a hunt for a bug that had already been correctly diagnosed.
Rewrite by line range or re-read the file's current text; **verify an edit
actually landed before debugging what it was meant to fix.**

Full detail: Claude memory `feedback-verify-empirically.md`,
`pysilver-milestone-history.md`.

---

## 4. Debugging methodology lessons

**A "slow"/"laggy" report that survives a clean timing instrumentation pass
may not be a timing bug at all — check for static layout overflow first.**
During the 2026-09 resize investigation, a `Row` of fixed-width `Button`s
visually overlapped once the window narrowed past their combined width,
which reads exactly like lag even though nothing was actually slow. Fixing
it was real and worthwhile, but it was not the bug being reported.

**When a report survives a fix that measured clean *and* a second
plausible-looking bug fix, stop instrumenting the same layer and go one
layer further out.** The literal complaint ("the window keeps resizing
after I release the mouse, like it's following a queue") took three
separate real, committed fixes (a Terminal reflow debounce, a
NavigationRail/Drawer crash under narrow constraints, the button-overflow
fix above) before the actual mechanism was found — none of the three were
it, and phil had to say so explicitly ("I do not care about the shapes
overlapping") before the search moved on. The real cause was one layer
below the render loop entirely: `glfw.poll_events()` blocks draining every
queued native resize event before returning, and `rendercanvas`'s
`_on_size_change` fires one full synchronous render per event with no
coalescing — a genuine backlog, not a metaphor. Fixed with
`Engine._coalesce_resize_paints`, rate-limiting input-driven repaints to
120Hz.

**Decisive, cheap cross-checks beat more measurement of the same thing:**
asking phil to do the identical drag in Dolphin (a different app) — which
tracked perfectly — ruled out the entire compositor/Wayland layer as the
cause in one message, cheaper than another round of instrumentation.

**A user's plain description of a symptom is data, not colour.** "Like
it's following a queue" named the actual mechanism (an event-queue
backlog) before the investigation found it independently — take literal
wording seriously rather than translating it into whatever hypothesis is
already being tested.

**Video/recording evidence has a real ceiling**: frame duplication to hit a
target capture rate looks identical to genuine lag. Know when a measurement
technique has hit a wall (reading `glfw.get_cursor_pos` directly from the
running process showed only 10 distinct positions across ~3700 frames — a
real Wayland platform limitation, not a pySilver bug) and switch technique
rather than re-analyzing the same ambiguous recording harder.

Full account: Claude memory `feedback-debugging-under-pushback.md`,
`pysilver-widget-backlog.md` (resize saga), `ARCHITECTURE.md` §5.8.1.

---

## 5. Performance findings

**Python, not the GPU, is the bottleneck; the GPU is nearly free.**
Measured at M2 and reconfirmed at M4: assembling 1000 display-list
instances costs ~19x more than the GPU work consuming them, and scalar
per-widget emission exhausts the paint budget at ~610 instances.

**The rule that follows, non-negotiable:** display-list assembly is
**vectorised**, never a per-widget or per-glyph Python loop appending to a
list. M4 had to relearn this for text and rewrite it the same way.

Two long-standing costs, since closed:
- **Quadratic line wrap** — scaled with *window width*, not paragraph
  length (107.9ms for one wide line). Now flat at 13–15ms.
- **Wayland resize trailing** — the swapchain is pinned to a coarse size
  during a drag (acquire cost 1.8ms → 0.05ms). See §4 above for the
  *second*, unrelated resize issue found later (the event-queue backlog).

Caveat: all numbers are from one machine's integrated GPU over Vulkan —
don't quote them as universal.

Full numbers: Claude memory `pysilver-performance-findings.md`, graph
entity `pySilver Performance Findings`.

---

## 6. Tech stack traps

- **`wgpu.gui` was removed in wgpu 0.32.** Use
  `rendercanvas.glfw.RenderCanvas` and the `_sync()` adapter/device
  variants.
- **`rendercanvas` owns the event loop.** `update_mode="ondemand"` *is* the
  dirty flag — polling GLFW alongside it double-pumps events.
- **Colour space, the recurring trap:** surface formats are `*-srgb` and
  encode on write, so any value written to the display list must already be
  **linear**. `materialyoucolor` returns sRGB-encoded bytes (needs
  `srgb_to_linear` before upload) — and the identical bug bit **every**
  widget that later picked its own literal (non-token) colour:
  `CodeEditor`'s syntax-highlight palette, `Terminal`'s ANSI colours, and
  `Canvas`'s public `CanvasContext` API for application authors. All three
  fixed with a small `_srgb()`/`_linear()` helper wrapping the
  already-existing `theme.srgb_to_linear`. **Any future widget introducing
  its own literal RGBA must convert it the same way** — `(1,1,1,alpha)`
  white-tint overlays are the one safe exception (0 and 1 are fixed points
  of the sRGB curve).
- **`materialyoucolor` is used as a class, not instantiated**; its
  attributes are camelCase while pySilver's token names are snake_case.
- **Text is five packages, one job each:** `uharfbuzz` shapes,
  `freetype-py` rasterises *only*, `fontTools` itemises scripts,
  `python-bidi` does UAX #9, `uniseg` does UAX #14/#29. HarfBuzz and
  FreeType agree on glyph IDs — that's what makes the split work.
- **Toolkits cannot be embedded — not a licensing question.** `qtconsole`
  (BSD) and `pyqtconsole` (MIT) are both unusable regardless of licence:
  they render through their own surface and event loop. Only *headless*
  libraries help (`pexpect`+`bittty` for Terminal, `bittty` replacing
  `pyte` on 2026-09-08 after a real `pyte` parsing defect surfaced live —
  see `widgets/terminal.py`'s own docstring).
- **Licence traps for an MIT framework, verify from PyPI, never recall:**
  PyQt6 is GPL-3.0-only; `bittty` is WTFPL, even more permissive than
  `pyte` (LGPLv3, the reason it too was kept an optional-only extra);
  `filedialpy` declares **no licence at all**.
- **Native file dialogs must go through the XDG portal** — `jeepney` (MIT,
  pure Python) is the route, same seam shape as the clipboard and the
  accessibility bridge.

Full detail: Claude memory `pysilver-tech-stack-traps.md`, graph entity
`pySilver Tech Stack`.

---

## 7. Text rendering

Two real, fixed, verified bugs (full investigation in the graph entity
`pySilver Text Rendering Quality` — don't re-derive from scratch):

1. **Default FreeType hinting grid-fits curved glyphs** (d/p/g bowls) to
   the pixel grid and visibly flattens them. Fixed via `FT_LOAD_NO_HINTING`.
2. **Disabling hinting then left flat-edge glyphs** (E/l/v) with
   inconsistent top/bottom antialiasing. Fixed via a gamma=0.6 coverage LUT
   applied post-rasterisation — the same "stem darkening" idea
   Skia/DirectWrite use for unhinted text.

`FT_LOAD_TARGET_LIGHT` does **not** sidestep this trade-off for a font with
native hints (Roboto has its own hand-authored TT hint program) — it only
relaxes horizontal stem darkening, not the vertical grid-fitting causing
both symptoms.

**Still open**: phil's own words, "It looks good, I am still not happy with
how the text is being done, but we will look at that another time." A
Skia/Skrifa rasterizer swap was discussed (would need custom Rust bindings,
a multi-day migration) but not attempted — cost, not a rejected idea.

Commits: `b98471f` (disable hinting), `187223f` (gamma correction).

---

## 8. Engineering traps (grouped)

### Rendering / clipping
- **A zero-size clip rect means "unclipped" in this codebase's shader
  convention**, not "clip away everything." The shader only applies a clip
  when *both* dimensions are strictly positive — **either** being exactly
  zero (not both) reads as unclipped. This is a cross-cutting bug pattern:
  it hit `DockPanel`'s inactive-tab hiding *and* `TreeItem`'s existing,
  already-shipped clip-intersection code, silently, because a real GPU
  frame at a taller canvas leaked content that an earlier golden's
  coincidental cropping had hidden. **Fix: never emit a clip whose width or
  height is exactly zero when the intent is "hide this"** — floor the
  degenerate dimension to a small but non-zero `HIDDEN_EXTENT` (0.01,
  already-scaled physical px) instead. Documented once, in full, in
  `ARCHITECTURE.md` §5.8.6. Any future widget computing a clip via
  intersection (rather than directly from its own size) must apply this —
  a size-derived clip never hits zero by construction, an
  intersection-derived one silently can.
- **Cloning a `PaintContext` to apply a paint-time clip is easy to get
  half-right.** All nine existing clip-cloning call sites (across seven
  widget files) omitted `images=ctx.images`, silently falling back to an
  empty `ImageAtlas` for any `Image`/`Video` painted inside a
  clipped/scrolled subtree. Check *every* field of `PaintContext` is
  threaded through when adding a tenth clipping call site.
- **`paint_self` runs before children; use `paint_foreground` to sit over
  them.**
- **Palette tokens cannot be interpolated** — they resolve in the shader,
  so a colour cross-fade is emitted as two overlapping boxes at
  complementary alpha, not one interpolated colour.

### Layout / constraints
- **`constrain_width`/`constrain` on the way out of `perform_layout` is not
  optional — skipping it crashes instead of shrinking.** `NavigationRail`/
  the old `NavigationDrawer` built inner constraints from a flat M3 width
  (80dp/360dp) with zero regard for how much room the parent actually
  offered — a real, user-hit `AssertionError` when a gallery `Row`/
  `Horizontal` holding both was dragged narrow. Fixed by wrapping the
  resolved width in `constraints.constrain_width(...)` first, exactly like
  `overlays.py`'s `_resolved_width` already does correctly for
  Menu/Dialog/Popover/the sheets. **Any fixed-or-M3-sized widget must clamp
  through its incoming constraints before returning** — an M3 minimum is an
  aspiration, not something a narrower parent has to honour.
- **A `Flex` subclass that skips `_FlexElement` loses flexible-child
  awareness.** `StatusBar` and `TopAppBar` both extend `Flex` directly, so
  the base `flex_of` had no idea a `width: expand` `Spacer` child should be
  flexible — it was measured as inflexible, claimed nearly all remaining
  width, and starved whatever came after it to zero. Fixed for
  `StatusBar` (needed the Spacer pattern); **not** backported to
  `TopAppBar` since nothing there uses a `Spacer` yet — worth remembering
  if that changes.
- **`self.x or FALLBACK` is a bug wherever 0 is meaningful.** Bit
  `elevation: 0`; the first tests missed it by asserting on the *property*
  rather than on what actually got painted.

### Motion / animation
- **`Animation.tick(dt)` clamps `dt` to `MAX_FRAME_DELTA = 0.1`s per call.**
  A single `tick(1.0)` on a short (0.2s) transition only advances 50% — any
  test needing full settlement must loop `tick()` calls (established
  pattern: `for _ in range(4): a.motion.tick(1.0); a.update()`).
- **`animated()`'s layout-invalidating retarget "retargets but does not
  jump on the first `update()`"** — moving a value from an instant resize
  to `animated(..., invalidates="layout")` means any *new* test must use
  the two-step `set → update (assert unchanged) → motion.tick → update
  (assert changed)` pattern, not a naive single `set → update → assert`.
  Missing this broke `test_collapsed_is_bindable` when `NavigationRail`
  gained real animation.
- **A `repeat=True` animation never self-removes from `Ticker`.** `done` is
  always `False` for a repeating animation, so nothing drops it from
  `Ticker._running` on its own. Fixed via a new `Ticker.discard()`, called
  automatically from `ElementMixin.dispose()` for every animation an
  element owns — **but disposal alone doesn't cover a live state
  transition on a still-mounted element that stops calling
  `animated(..., repeat=True)`** (e.g. `LinearProgress`/`CircularProgress`
  flipping from indeterminate to determinate); those needed their own
  explicit `ticker.discard()` call. Without both halves, `Ticker.active`
  never returns to `False` again for the rest of the process, breaking "an
  idle app renders zero frames."
- **"Swap, don't interpolate" for discrete anatomy changes.** A glyph
  instance carries no rotation parameter, so `AccordionElement`'s chevron
  swaps `expand_more`/`expand_less` at the logical boolean state rather
  than continuously rotating — a mid-transition swap reads as a glitch,
  not a partial rotation. The same reasoning was reused verbatim for
  `NavItemElement` swapping its row-vs-stacked `Flex` anatomy at the
  parent's `progress() > 0.5` threshold, since nothing in the layout engine
  interpolates between two structurally different `Flex` arrangements
  frame-by-frame.
- **A settle-debounce keyed on frame count silently breaks if the trigger
  that decrements it isn't guaranteed to recur.** `Engine._pin_surface`'s
  frame-count debounce works because `draw_frame` runs every frame
  regardless. Copying that shape into `TerminalElement`'s grid-reflow
  debounce was a caught-before-shipping mistake: `perform_layout` only runs
  when something re-lays-out, which a window that stops resizing may never
  do again — a frame-count counter gets stuck forever. Fixed with
  wall-clock time, checked from `paint_self` (guaranteed to keep firing by
  the widget's own heartbeat) instead of `perform_layout`. **Before reusing
  `_pin_surface`'s exact shape elsewhere, confirm the new call site has the
  same "runs every frame no matter what" guarantee.**
- **`Animation.on_change` can silently skip firing on the exact frame
  `.done` becomes true, for an eased curve.** `advance()` only calls
  `on_change` when `.value` actually changed from the previous tick; the
  default `"standard"` M3 curve's derivative flattens near its endpoint, so
  two ticks close to completion can round to the identical float once
  eased — exactly the bug in `Snackbar`'s own auto-dismiss timer, found by
  tracing a real run where the countdown finished (`.done` became `True`,
  removed from `Ticker._running`) but never actually requested a dismiss.
  Fixed with `curve="linear"`: a one-shot wall-clock timer has no reason to
  ease in the first place, and a linear ramp has no flattening tail to
  collide on. **Any future "fire once when this animation completes"**
  built on `on_change` should default to `curve="linear"` unless there's a
  specific reason to ease it.
- **`style.*` (StyleSpec) fields are not `{{ }}`-bindable at all** — only
  `WidgetSpec`-level fields registered in `TEMPLATED_FIELDS` (`text:`,
  `value:`, `icon:`, `path:`, …) are resolved and reactively re-bound. A
  `style.some_field: "{{ signal.get() }}"` silently keeps the literal
  unprocessed template string as the value, no error. (`params:`-based
  view-composition macros, e.g. `swatch_View.yaml`'s `background: "{{
  token }}"`, look similar but are a completely different, include-time
  text-substitution mechanism — don't mistake one for evidence the other
  works.) A future StyleSpec field that needs live binding has to move to
  `WidgetSpec` (through `TEMPLATED_FIELDS`) instead.

### Events
- **A handler on an ancestor fires twice** — capture *and* bubble.
  Deliberate and tested, not a bug; check `event.phase` when it matters.
- **Invalidating during a layout pass leaves an element permanently
  dirty.** Cut the cycle at the source rather than chasing it with more
  invalidations.
- **A native `on_pointer_down` runs on the way *up* only, never during
  capture.** A naive "start panning on any press inside me" handler on
  `NodeGraph` would have panned the background under every click on a
  node's own content. Fixed by checking `event.target is self` — reading
  the dispatcher's already-computed hit-test result rather than doing a
  second, redundant one.
- **Tab is intercepted as focus-traversal *before* any element's own
  `on_key_down` ever runs.** `CodeEditor` needed to actually see Tab (for
  indent/dedent). Added `ElementMixin.CAPTURES_TAB` (default `False`, same
  shape as `CLIPS_CHILDREN`) so a focused element can opt in — Escape still
  defocuses unconditionally first, so trapping Tab this way never traps the
  keyboard entirely.

### Imports / hot reload / testing infra
- **A latent circular import survives only by import order.**
  `render.atlas` type-hinted against `text.font`; `text/__init__.py`
  imports `GlyphAtlas` back from `render.atlas`. Whichever module finished
  loading first "won," invisibly, until adding `ImageAtlas` changed load
  order and turned it into a real `ImportError`. Fixed at the source
  (type-only import moved under `TYPE_CHECKING`), not by reordering the
  import in whichever module tripped over it.
- **`watchfiles.Change.name` is lowercase**, not `"DELETED"` — two places
  (`app.py`, `runtime/hotreload.py`) compared against the uppercase literal
  and the "file disappeared" branch silently never fired.
- **Hot reload had three silent no-ops**, all found and fixed together:
  overlays were never rebuilt on reload (only the main tree was);
  `OverlayHost.build()` never threaded an `image_atlas` to overlay elements
  (only `text_engine`/`ticker`); and the `watchfiles` casing bug above. **If
  a fourth thing `App.reload()` needs to propagate to overlays is ever
  added, check both `App.__init__` and `App.reload()` pass it, not just
  one.**
- **A pytest fixture guarding cross-test state needs `scope="session"`**,
  not the default function scope. `tests/golden/conftest.py`'s
  `assert_golden` kept a `used: set[str]` specifically to catch two
  *different* tests reusing the same golden baseline name, but was
  function-scoped — a fresh empty set per test meant the check could never
  fire across two tests, only within one.
- **`spec/include.py`'s view-composition walk once checked *every* dict in
  a YAML file for a `source` key**, not just widget-tree nodes. Wiring
  `NodeGraph.edges:` (`EdgeSpec.source`/`.target`, `{source: "a.out",
  target: "b.in"}`) into a real gallery YAML file got misread as a
  `source: a.out` file include and failed. No test caught it because every
  `NodeGraph` test builds its spec as a Python dict directly, bypassing
  `load_view` entirely. Fixed by scoping `_walk`'s recursion to only the
  keys that can hold a widget-tree node (`root`/`children`/`overlays`/
  `styles`), mirroring `stamp_view`'s pre-existing identical restriction.
  **Any future `WidgetSpec` field literally named `source` will hit this
  again if `_walk` is ever loosened.**

### Naming
- **`Row`/`Column` were renamed to `Horizontal`/`Vertical`, repo-wide
  (2026-09-06)**, both at the YAML/`WidgetKind` layer and the internal
  `pysilver.layout.algorithms` layer. Reason: their spreadsheet meaning
  (rows stack vertically, columns sit side by side) is the *opposite* of
  what these layout widgets actually do, and it caused a real user-facing
  layout bug. Any older note still saying "Row"/"Column" means what is now
  `Horizontal`/`Vertical`.
- **Ambiguous widget names were resolved by asking, not guessing** —
  twice: "Stepper" (M3 reserves that name for a multi-step *flow*
  indicator, a different widget entirely; user picked `SpinBox` for the
  numeric-increment control actually wanted) and "Dock" (macOS-style icon
  dock vs. IDE-style dockable-panel system; user picked the latter, then
  confirmed shipping only its static half first once the runtime
  drag-to-redock scope was made concrete).

Full detail: Claude memory `pysilver-engineering-traps.md`, graph entity
`pySilver Engineering Traps`; the September 2026 full-codebase review
(`docs/CODE_REVIEW_2026-09.md`, commits `13da50f`..`ccb13b1`, 1788 tests
passing) is the single largest source of these — see also
`pysilver-code-review-2026-09.md`.

---

## 9. Widget-by-widget review (current pass) — bugs found and fixed

Systematic live-demo review, batch of ~8 widgets at a time, offscreen render
→ inspect → cross-check against M3 → fix-or-defer. Governed by the plan at
`/home/phil/.claude/plans/zesty-skipping-walrus.md`.

**Batch 3 (TextField → CircularProgress) — real bugs found and fixed:**

| Widget | Bug | Root cause | Fix | Commit |
|---|---|---|---|---|
| TextField | **Keyboard typing was completely broken in every live window**, since the framework's first commit | `rendercanvas`'s real "char" event dict uses key `data`, not `char`; `App._on_canvas_event` read the wrong key | `event.get("data", "")` | `4e43fec` |
| TextField | Caret invisible on an empty field | `caret_at()` returned a zero-height rect when a paragraph had no lines yet | Return `SelectionRect(0, 0, 0, para.size.height)` — shared fix, also benefits `CodeEditor` | `0971be5` |
| TextField | Outlined label/border interaction — three rounds of user-driven correction (blended letters → wrongly-placed-above-border → finally correct) | Erasure patch behind the floated label was sized to the border's thin stroke width, not the label's full line-height | Size the erase patch to `line_height`; keep the label centred *on* the border per the real M3 reference, not stacked above it | `8bb57ff` |
| SplitButton | Menu overlay rendered permanently inline (pushing the page down) regardless of open state | Declared as a plain nested child instead of under `ViewSpec`'s top-level `overlays:` key | Restructured YAML to explicit `root:`/`overlays:` split | `c3a1f11` |
| DatePicker | Month/year label overlapped the `chevron_left` icon | Label paint x-offset didn't account for the chevron's width | Offset by `+ self.CELL` | `1c31b04` |
| ListItem | Leading icon never actually laid out (`size == Size(0,0)`, `offset == Offset(0,0)`, always) | `perform_layout` never positioned `self.child` at all | Explicit icon layout + label x-offset accounting for icon width + gap | `69c1960` |

**Batch 4, NavigationRail/NavigationDrawer merge** — see §10.

**Overlay-as-plain-child bug: RESOLVED, all 8, 2026-09-08.** All eight
overlay-trigger widget demos (Dialog, Menu, Snackbar, BottomSheet,
SideSheet, Popover, Tooltip, SplitButton) originally declared their overlay
node as a plain nested child instead of under `overlays:`, same shape as
SplitButton's own reference fix (`c3a1f11`). Fixed for the remaining seven
when the review reached the overlay/trigger batch: Menu (`3bddd38`), Dialog
(`e3e60d6`), Snackbar (`a4e1766`, which also fixed the action label being
painted but never hit-tested), BottomSheet (`9e208ab`, plus a missing
`handle: true`), SideSheet (`7786e72`, plus `ededbf8`/`9049970` for a
missing close control), Popover (`ddef90a`), and Tooltip (`b999085`, plus a
click→hover trigger fix and a deliberate `phil`-approved colour override,
`37db852`/`f0ea09f`). No known remaining instance. Tracked in Claude memory
`pysilver-widget-review-backlog.md`, graph entity `pySilver Overlay Demo
YAML Bug`.

**Batches 4–9, plus the review's own follow-up features — summary, not
full detail (see the graph entities and `ARCHITECTURE.md` §14's M14 row for
the complete account).** The full 65-widget review finished 2026-09-08.
Real bugs fixed along the way beyond Batch 3's table: `Menu` filling the
offered width instead of shrink-wrapping to its widest `MenuItem`
(`3b652fc`); `Stack` ignoring each child's own `align_x`/`align_y`
(`7f42eb0`); `Tabs`' active indicator using the wrong height with no inset
(`f692749`); `TopAppBar`'s large variant using the wrong type-scale role
(`073be01`); `DockGroup`'s tab indicator missing the same inset `Tabs` had
(`bece365`); `DockSplit`'s divider cursor silently broken by a non-vocabulary
cursor name (`7f7f5a2`); `Node`'s title-bar cursor crashing the app on hover
(`2795281`); and the NavigationRail/NavigationDrawer merge itself (§10).
The review's own punch list then shipped as real, planned features, each
with its own `AskUserQuestion`/plan checkpoint where a real design branch
existed: the `TEMPLATED_FIELDS` refactor (`6abd57b`, one registry replacing
nine hand-wired bindable-field call sites, plus `icon:`/`label:` and the
migration of `Icon`/`IconButton`/`Fab`/`NavItem`/`SearchBar` off overloaded
`text:`/`supporting_text:`); icon anatomy for `Tab` (`037d174`, `9b45143`),
`Dialog` (`dd1f35f`, plus a real actions-row `main_alignment` bug,
`f85a033`), and `MenuItem` (`d0868e3`); `ButtonGroup`'s shape-morph and
toggle selection (`0c2f5e5`); `Slider`'s size ladder (`b4dcad8`) and
pluggable handle shapes (`cd39132` — square/hexagon/image; a true star was
asked for and dropped, since `add_polygon` only draws regular polygons and
cannot express one); `Snackbar`'s auto-dismiss timer (`387e8e4` — also
found a real `Animation.on_change` gotcha, see [§8](#8-engineering-traps-grouped));
and Dock's runtime drag-and-drop half (`3207f5b` plus a dozen live-feedback
follow-ups, `68c2086`..`804d3c2`). Also landed in this stretch, unrelated to
the review itself: held-key repeat synthesis (`6ab3b45`, `f365f38`) and the
Terminal `pyte`→`bittty` swap (`2b71227`, `fd2f944`, `063f796`).

---

## 10. Decision: merging NavigationRail + NavigationDrawer

**Trigger:** live-reviewing `NavigationDrawer`, phil observed "The
Navigation Drawer should collapse to just icons otherwise its not a
drawer." Checked directly against `M3-References/COMPONENT_NAVIGATION_RAIL.md`
(not from memory) — confirmed real: **M3 Expressive no longer treats
"Navigation Rail" and "Navigation Drawer" as two components.** There is one
component with two states: **collapsed** (narrow, icon-only, 80dp, "should
not be hidden") and **expanded** (wide, 240–360dp, labels — "meant to
replace the [modal] navigation drawer" entirely), which "can easily
transform into each other when the menu button is selected."

**Decision (asked, not assumed):** given a choice between a surgical
icon-only-mode patch on the existing separate `NavigationDrawerElement` and
a real merge matching M3's current model, phil chose the **real merge**
(spec-correct, gets the actual animated transform M3 describes) — then,
asked whether to scope the merge immediately or just log it for later,
chose to **scope it now**.

**What changed** (full plan: `/home/phil/.claude/plans/zesty-skipping-walrus.md`):
- `NavigationDrawerElement` and `WidgetKind.NAVIGATION_DRAWER` **deleted
  outright** — no deprecated alias, since `collapsed:` was read nowhere
  else and M3 itself redirects the old Drawer page to "use an expanded
  navigation rail."
- `collapsed:` redefined for the single remaining widget: `true` → narrow
  icon-only (80dp); `false` (default) → wide/labeled (240–360dp, same clamp
  as before). **The widget is now never hidden by its own state** — a real
  app wanting it fully hidden does so through ordinary view composition,
  not this field.
- Width **animates continuously** (`animated("expanded", ..., invalidates=
  "layout")`, same pattern as `Accordion`/`TreeItem`); `NavItemElement`
  **swaps** (doesn't morph) its row-vs-stacked anatomy at the parent's
  `progress() > 0.5` crossing — see [§8](#8-engineering-traps-grouped),
  "swap, don't interpolate."
- Background token corrected to `surface_container` (not `surface` or
  `surface_container_low`) per the M3 spec's own colour-role table.
- Gallery, docs (`ARCHITECTURE.md`, `docs/view-reference.md`), the
  `m3-widget-design` skill's catalogue, and all example demos updated;
  `examples/widgets/navigation_drawer/` deleted; its content merged into
  the `navigation_rail` demo.

**Real bugs caught during the merge, before shipping:**
- Un-prefixing gallery nav items to bare names (`home`, `foundations`, …)
  collided with `PageHost`'s own page files, which are literally named
  those same strings — `ViewSpec`'s global-uniqueness check would have
  rejected this at load time. Fixed with a single `nav_` prefix.
- A self-introduced overflow bug: choosing longer, "more descriptive"
  drawer-style labels for the merged single label set overflowed visibly in
  the new widget's *narrow* collapsed state (those labels only ever existed
  in the old wide-drawer form). Fixed by reverting to the short rail-style
  labels.

**Result:** 2229 tests passing, 13 skipped, fully committed (`744c94e` +
`809b411` — split across two commits after a `git add` pathspec mistake
was caught and fixed transparently with a second commit rather than an
amend, per §2's no-amend rule).

---

## 11. Open / deferred items (don't assume these are done)

- ~~7 of 8 overlay-trigger demos still have the "overlay-as-plain-child" YAML
  bug~~ **RESOLVED 2026-09-08 — all 8, see §9.**
- ~~Slider: size ladder not implemented; no pluggable handle shapes~~
  **RESOLVED 2026-09-08 — both shipped.** `style.size` (extra_small default
  through extra_large) scales track/handle height and track corner radius;
  `style.handle_shape` also takes `square`/`hexagon` (`Shape`'s own
  regular-polygon primitive), and `style.handle_image:` draws a raster
  image, winning over `handle_shape`. A true star was asked for and
  **deliberately dropped, not approximated** — `add_polygon` only draws
  regular polygons, so it cannot express a star at any setting; SVG was
  dropped the same way (Pillow has no decoder). Graph entity `pySilver
  Slider Design Backlog`. **Still open**: nothing on this widget.
- ~~ButtonGroup: no selection/toggle, no shape-morph~~ **RESOLVED
  2026-09-08 — shape-morph and toggle selection both shipped**, sourced
  from `COMPONENT_BUTTONS.md`'s own Corner sizes table, applied to every
  `Button` app-wide (phil's explicit choice), not just grouped ones. A
  standard group's selected button really does widen and shift its
  siblings — an ordinary `Flex` reflow consequence of the button reporting
  a wider `perform_layout` size, no new cross-element coupling built.
  Graph entity `pySilver ButtonGroup Design Backlog`. **Still open**: the
  XS/S/M/L/XL size ladder button groups are meant to span, which has
  nowhere to attach until `Button` itself grows a size axis (shares this
  gap with `Slider`'s own, now-shipped ladder).
- ~~Dock's runtime drag-to-redock half~~ **RESOLVED 2026-09-08 — shipped.**
  Dragging a tab into another `DockGroup` inserts it as a tab; dragging
  onto a `DockSplit` edge splits a new pane. New `widgets/dock_drag.py`,
  an `ElementMixin.dispatcher` seam, and `OverlayHost.push_transient` for
  the drag ghost. Explicitly still out of scope: layout serialization
  across reloads, floating/undocked windows, tab reordering within one
  group, multi-panel drag.
- **NodeGraph has no zoom** — deliberately scoped out: scaling would either
  thrash the glyph atlas (the same per-frame-rasterisation-key trap the
  icon `FILL` axis quantisation exists to avoid) or force re-shaping text
  at a new pixel size every step, plus every hit rect would need to scale
  to match. A real second feature, not a checkbox on the current one.
- **`TextEngine._layouts`' cache**: fixed (LRU eviction added,
  `layout_cache_size` default 512) — was previously unbounded, keyed by
  full text string, growing one entry per keystroke for any text-editing
  widget.
- **Known open issues from the September 2026 review** (full reasoning in
  `docs/CODE_REVIEW_2026-09.md`): `focus_order()` excludes all overlay
  content (Tab can't reach a Dialog/Menu/Sheet's own controls at all);
  `StyleSpec` padding/corner_radius can't distinguish "unset" from
  "explicit zero"; `ImageAtlas` has no per-key eviction on widget disposal;
  `Video` doesn't re-validate its cached atlas entry against generation
  the way `Image` now does.
- **Text rendering quality**: phil is not yet satisfied with the overall
  result even after both hinting/gamma fixes landed — see §7. A Skia/Skrifa
  rasterizer swap was discussed, not attempted (cost, not rejection).
- ~~RTL text: no Arabic/Hebrew glyphs, caret/selection across a direction
  boundary unimplemented~~ **RESOLVED 2026-09-09 — real UAX #9 bidi
  shipped (risk R9 closed).** `text/bidi.py` drives real embedding-level
  resolution (re-adopting `python-bidi`, which had been imported but its
  actual call site deleted as "dead code" in an earlier cleanup) instead
  of the previous single-whole-list-reverse heuristic. `NotoSansArabic-
  Regular.ttf`/`NotoSansHebrew-Regular.ttf` are now bundled, so Arabic and
  Hebrew render as real glyphs. `EditState.affinity` disambiguates a caret
  sitting exactly at a direction boundary; `Editor.move()` steps through a
  precomputed full visual ordering rather than deriving each step
  incrementally — an earlier incremental design oscillated forever near a
  boundary, caught by live testing before it shipped; `rects_for` emits
  one rect per disjoint span so a selection crossing a boundary paints as
  multiple rects. See `ARCHITECTURE.md` §5.7.7 Tier 3.
- **IME preedit** (R5) — likely needs a `rendercanvas` upstream
  contribution.
- **Windows/macOS accessibility bridges** — blocked on AccessKit platform
  wheels, untestable on this (Linux) machine.
- **Terminal on Windows** — needs a `pywinpty`/ConPTY backend; architected
  for (the platform branch exists) but not built, since nothing here could
  verify it.
- **Filing the wgpu swapchain-pin finding upstream** — not done.
- **PyPI upload** — deliberately not done; see §1's naming note.

---

## 12. Reference index

**In-repo authorities** (read these directly, don't rely on this doc for
detail):
- `ARCHITECTURE.md` — the project's single authority for design and
  deviations; §5.8.1 (resize coalescing), §5.8.6 (clip-degenerate-zero
  fix), §14 (milestone table).
- `docs/CODE_REVIEW_2026-09.md` — full September 2026 review writeup, every
  fixed bug and every deliberately-unfixed finding with its reasoning.
- `docs/view-reference.md` — pinned view-file schema reference.
- `M3-References/` — gitignored, ~2.2MB scrape of m3.material.io; access
  through the `m3-lookup` skill, not directly (filenames don't map 1:1 to
  component names; several files describe the May 2025 M3 Expressive
  revision).
- `/home/phil/.claude/plans/zesty-skipping-walrus.md` — the widget-by-widget
  review plan (batches 1–9, **complete** 2026-09-08) plus the completed
  NavigationRail/Drawer merge, Templated-fields, and Dock drag-and-drop
  plans it grew to include.

**Claude Code project memory** (`.claude` memory directory, this project):
`pysilver-architecture-decisions.md`, `pysilver-milestone-history.md`,
`pysilver-widget-backlog.md`, `pysilver-widget-review-backlog.md`,
`pysilver-engineering-traps.md`, `pysilver-code-review-2026-09.md`,
`pysilver-naming.md`, `pysilver-performance-findings.md`,
`pysilver-tech-stack-traps.md`, `pysilver-text-rendering.md`,
`pysilver-font-bundle.md`, `m3-references-library.md`,
`pysilver-skills.md`, `feedback-verify-empirically.md`,
`feedback-milestone-workflow.md`, `feedback-debugging-under-pushback.md`,
`user-phil-working-style.md`.

**Knowledge-graph entities** (canonical detail behind the memory pointers
above — per `CLAUDE.md`'s Memory policy, the graph wins on disagreement):
`pySilver Architecture`, `pySilver Milestone History`, `pySilver Widget
Backlog`, `pySilver Package Survey`, `pySilver Rendering Engine Evaluation`,
`pySilver Engineering Traps`, `pySilver Performance Findings`, `pySilver
Tech Stack`, `pySilver Text Rendering Quality`, `pySilver Font Bundle`,
`pySilver Slider Design Backlog`, `pySilver ButtonGroup Design Backlog`,
`pySilver Overlay Demo YAML Bug`.

---

*This document reflects the state of the project as of 2026-09-08. Update
it (or its pointed-to memory files) as new lessons land — don't let it
silently drift the way `ARCHITECTURE.md` almost did before the
verify-empirically discipline in §3 was established.*
