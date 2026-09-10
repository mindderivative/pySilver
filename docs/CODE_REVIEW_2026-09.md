# Full codebase review — September 2026

A complete, foundation-first review of pySilver's Python source and test
suite, run in four phases by 60 subagents (16 + 9 + 11 + 24) plus manual
orchestrator follow-up, with every fix verified against the full test suite
and the GPU/golden suite before landing. Scope: all 63 `src/pysilver/`
files, all 66 `tests/` files, `examples/`, and the top-level docs
(`ARCHITECTURE.md`, `docs/view-reference.md`, `README.md`, `CLAUDE.md`).
Excluded as non-project or regenerable: `.venv`, `.claude`, `.git`,
`.github`, `.cursor`, `.vscode`, `.hypothesis`, `dist/`, and
`M3-References/` (a scraped third-party reference library, not our code).

Commits: `13da50f`..`e335f02` (7 commits: one per phase, plus three small
standalone follow-ups). 652 insertions, 198 deletions across 63 files.
Final state: `ruff check`/`ruff format --check` clean, `mypy` strict clean,
1788 tests passing (up from 1766 — the review added 22 net new tests), 93
GPU/golden tests passing, 12 pre-existing intrinsic-size skips unaffected.

## How it was run

Foundation-first, by actual import dependency, so a reviewer of a higher
layer could trust the layer below had already been looked at:

1. **Phase A** — layout, motion, paint, theme, config, spec, text, render (16 subagents)
2. **Phase B** — tree (element/reconcile), runtime (signals/events/overlay/accessibility/engine/etc.) (9 subagents)
3. **Phase C** — widgets/ (11 subagents, one file each except image+video paired)
4. **Phase D** — app.py, public API, all tests, docs consistency (24 subagents)

Each subagent got the same brief: find real correctness bugs, code-quality
issues judged against *this codebase's own* conventions (not generic
style), and Python performance issues (particularly violations of the
documented "vectorised assembly" hot-path rule) — apply only high-confidence,
low-risk fixes directly, report anything needing a design judgment call
instead of guessing. Findings that surfaced in one phase but belonged to a
file already reviewed or not yet reached were threaded into the next
phase's brief explicitly, so nothing that couldn't be fixed in place was
dropped. After each phase, the orchestrator (not a subagent) ran the full
verification suite, reviewed every diff, fixed anything a subagent got
wrong, and committed before starting the next phase.

## What was fixed

### Real correctness bugs (the significant ones)

- **A GPU texture leak**, one per `App.attach()` call: `bind_glyph_atlas`/
  `bind_image_atlas` never destroyed the texture they replaced. Landed at
  the correct call site (`App.attach`, the one place that actually knows a
  texture is being orphaned) after a first attempt — destroying inside the
  lower-level pipeline methods themselves broke the GPU test harness's
  direct-bind usage pattern, caught by the full suite before it shipped.
- **A repeat-animation leak that permanently broke "an idle app renders
  zero frames."** A `repeat=True` animation (a text caret blink, an
  indeterminate progress spinner) never finishes on its own, so nothing
  ever removed it from the `Ticker`. Fixed in three places once the whole
  chain was traced: `Ticker.discard()` (new), `ElementMixin.dispose()`
  (calls it for every animation an element owned), and
  `LinearProgress`/`CircularProgress` (call it directly when a live
  `value:` binding flips the widget from indeterminate to determinate on
  the *same* element, with no dispose involved at all).
- **A real race in the reactive core.** `Signal.set()`'s notify call
  wasn't wrapped in its own batch, so an `Effect` and a `Computed` both
  subscribed to the same signal could run out of two-phase order — the
  `Effect` observing the `Computed`'s stale value, then re-running a
  second time once it caught up. Reproduced empirically (~60% of trials
  hit it before the fix, 0/2000 after).
- **A D-Bus thread race** in the accessibility bridge: `drain()`
  snapshotted a deque with `list()` then `clear()`ed it, silently dropping
  any request AccessKit's own thread appended in the gap. Fixed to pop one
  at a time (an atomic operation under the GIL).
- **A checked checkbox hid its own hover/focus/press feedback.** The state
  layer painted *before* the selected-state fill, so at full opacity the
  fill covered it entirely.
- **A scrollbar thumb painted underneath its own scrolled content**
  instead of over it, because it was emitted in `paint_self` (before
  children) instead of `paint_foreground` (after).
- **`Canvas.rect()`'s border defaulted to opaque white** instead of
  transparent when no `border_color` was given — every bordered rect drawn
  without one got a solid white outline.
- **Card's asymmetric `corner_radius` was silently discarded** — only the
  first of four values was ever read, while the focus ring (computed
  separately) already honoured all four.
- **A `DockGroup` of entirely unnamed panels showed all of them "active"
  simultaneously**, fully overlapping — `None == None` matched every
  child at once.
- **Word-wrap glued text onto an overflowing line instead of starting a
  new one** whenever the text right after an unbreakable overflowing token
  needed its own break. Verified with a targeted repro plus 2000+ fuzzed
  sequences.
- **A real, silent name-collision bug in fragment `source:` includes** —
  when a nested node's own name happened to equal its enclosing include's
  call-site name, it was left unprefixed instead of namespaced, producing
  duplicate widget names. Reproduced and verified fixed against the real
  loader.
- **A stale-atlas-entry bug in `Image`**: a wholesale `ImageAtlas.reset()`
  (forced by some other image needing room) left a widget whose `path:`
  never changed pointing at a rectangle the atlas had since overwritten,
  indefinitely. Fixed with the same generation check `GlyphAtlas` already
  makes for exactly this reason.
- **Hot reload silently did nothing for three things** it should have:
  overlays (`Dialog`/`Menu`/`Sheet`/etc.) were never rebuilt on reload,
  overlay elements never got the app's real image atlas (only the main
  tree did), and both `app.py` and `runtime/hotreload.py` compared a
  deleted-file event against the literal string `"DELETED"` when the real
  `watchfiles` enum values are lowercase — so the "file disappeared, skip
  it" branch never actually fired in either place. All three fixed
  together, since fixing only one half of the last one would have made
  the other miscount a skipped reload as applied.
- **A cross-cutting `PaintContext` bug found by the Canvas reviewer and
  fixed by the orchestrator across every file it touched**: nine separate
  places (`canvas.py`, `navigation.py` x2, `material.py`, `textfield.py`,
  `dock.py`, `carousel.py` x2, `scroll.py`) — every widget that clones a
  `PaintContext` to apply a paint-time clip — omitted `images=ctx.images`,
  silently falling back to an empty default atlas. Any `Image`/`Video`
  painted inside a clipped or scrolled region would have sampled the
  wrong atlas.
- **`assert_golden`'s own duplicate-baseline-name guard didn't work.** The
  `used: set[str]` it checks against was rebuilt fresh on every test
  function (function-scoped fixture), so it could never catch two
  *different* tests reusing the same golden name — precisely the
  regression its own code comment says it prevents. Fixed to session
  scope.
- A dozen smaller real bugs: `Link` ignoring `style.font_weight` when
  measuring/painting its label; `NavigationDrawer` silently ignoring a
  percent width; `Popover`'s action row squeezed to its text's width
  instead of the popover's real available width; a filled `TextField`'s
  state layer bleeding into its supporting-text row; `Carousel` reading a
  fixed height's raw unclamped value instead of the tightened one;
  `DockPanel` laying its child out against the wrong constraints;
  `DockSplit`'s divider hand-rolling its hover/press alpha instead of the
  shared, documented helper (so it snapped instead of cross-fading and
  never reflected keyboard focus); `SizeSpec`'s `"flex"` parsing accepting
  any string starting with those four letters; a missing non-negativity
  check on percent sizes; `padding:`'s dict form silently ignoring
  misspelled keys instead of failing at load; slicing (`items[1:3]`) and
  dict-unpacking (`{**x}`) in the binding-expression sandbox each doing
  the wrong thing instead of the validator's intended rejection; a
  variable font's axis coordinates not resetting between an icon rendered
  filled and one rendered outlined right after it; a secondary
  (right-button) click synthesizing a spurious `on_click` alongside the
  context menu.

### Performance

- `LayoutNode.clear_children()` was O(n^2) in child count (a loop over
  `remove_child()`'s own O(n) list search); rewritten to one O(n) pass,
  which also let `tree/reconcile.py`'s child-teardown loop — the same
  shape, one layer up — switch to it.
- Every pointer move ran hit-testing twice (once for dispatch, once for
  the cursor) for an identical result; computed once and reused.
- `ConstrainedBox` always kept a tightly-constrained child on its own
  dirty-propagation path instead of letting it become a relayout
  boundary, unlike the equivalent `SizedBox` a few lines above it.
- A hot-path helper (`paired_content_token`, called once per frame for
  every `CarouselItem`) did a local import with no circular-import reason
  forcing it local.
- One of four output arrays in the HarfBuzz shaping wrapper was still
  built with a per-glyph Python loop instead of `np.fromiter` like its
  three siblings.

### Quality

Removed confirmed-dead code throughout (`ElementMixin._own_hit_inset`,
`OverlayHost.reopen()`/`entry_at()`, `ChipElement._leading`,
`text/itemize.py`'s unused `reorder_for_display()` — which also drops
`python-bidi` as an actual runtime dependency of that module,
`app.py`'s never-exported, never-called `batched()` helper); removed one
byte-identical duplicate test and one dead always-false conditional
statement; corrected several stale docstrings and code comments
(`ImageAtlas`'s "not wired in" note, two golden-baseline docstrings that
overclaimed their own scope, `StyleSpec.handle`'s "not wired to the
pointer yet"); normalized a couple of unusual idioms to match the rest of
the codebase's own style.

### Test coverage

22 net new tests, each a one-line-away extension of an existing, passing
sibling test in the same file — not new test philosophy. Highlights:
`Constraints.expand()`/`copy_with`, `LayoutNode.remove_child`,
`SingleChildNode`'s second-child rejection, `Flexible`'s negative-flex
rejection, `Theme.contrast`, `Computed.peek()`, `disabled:` updating in
place on reconcile, a fragment-local anchor's namespacing, keyword-argument
and dict-unpacking rejection in the expression sandbox, the glyph atlas's
`coords`-as-cache-key contract, `selected`/`focused` reporting in the
accessibility tree, `TextField`'s `error:` accent, `DockSplit`'s
vertical-axis arrow-key stepping, a secondary-button release correctly not
firing a click, and `HotReloader.apply()`'s deleted-file skip branch.

## Known issues surfaced, not fixed

Every subagent was instructed to report rather than guess when a fix
needed a design decision. These are real and worth a maintainer's
attention, grouped by rough theme:

**Needs a design decision:**
- `focus_order()` excludes all overlay content — Tab can never reach a
  control inside an open `Dialog`/`Menu`/`Sheet` at all (worse than "no
  focus trap": there's no keyboard path in at all).
- `StyleSpec.padding`/`corner_radius` have no way to distinguish "unset"
  from "explicitly zero" (affects `Card`, `Dialog`, and others that
  substitute an M3 default whenever the value is exactly `(0,0,0,0)`).
- `StyleSpec.margin` is declared and validated but has zero consumers
  anywhere in the engine — possibly dead, possibly reserved.
- `ImageAtlas` has no per-key eviction on widget disposal — a `Video` or
  distinct-path `Image` that's frequently mounted/unmounted leaks one
  small cache entry per instance until a wholesale reset reclaims it.
  `Video.paint_self` also doesn't re-validate its cached entry against the
  atlas generation the way `Image` now does (fixed this pass) — a `Video`
  gone quiet during a wholesale reset would show stale pixels until its
  next `push_frame`.
- `Constraints.expand()` produces infinite `min_width`/`min_height`, which
  the class's own docstring says is illegal — currently unused and
  untested anywhere, so there's no call site to check intent against.
- `base.py`'s `ButtonElement`/`TextElement` are forced into per-call local
  imports from `material.py` by a real circular-import constraint; fixing
  it means extracting shared paint helpers into a third module.
- `TYPE_ROLES` (generated) and the `TypeRole` `Literal` (hand-written) are
  two independently-maintained copies of the same 15 strings that will
  silently drift if one is edited without the other.

**Real but low-confidence-reachable, flagged for awareness:**
- `Animation.finish()` (used under `reduce_motion`) doesn't fire
  `on_change`, unlike `advance()` — no current caller is affected, since
  all of them re-read `.value` or issue their own `mark_needs_paint()`
  immediately after.
- `animated(key, target, repeat=True)` silently produces a static value
  instead of a repeating one if the same `key` was previously used with
  `repeat=False` — no current call site reuses a key across repeat states.
- `NavItemElement.RAIL_H` is declared but never referenced — either dead,
  or a minimum-height floor that was meant to be applied and never was.
- `LinearProgress`/`DockSplit` fall back to `0.0`/collapse to zero size
  under unbounded constraints with no explicit style, unlike their
  siblings in the same files, which pick a sensible default.
- `TopAppBar` doesn't deflate/inflate around its children's layout the way
  `StatusBar` correctly does — untested and undocumented usage (no
  existing view gives a `TopAppBar` children), so low real-world impact.
- `_flush()` in the reactive core drops every other pending observer in
  the same batch if one observer's effect raises, with no diagnostic.
- `runtime/__init__.py`'s `__all__` is narrower than every sibling
  subpackage's and narrower than its own docstring claims — nothing
  currently imports through it except `Engine`, so may be intentional.
- Several test-coverage gaps reported but not filled because they'd need
  new test infrastructure or GPU-baseline regeneration this pass couldn't
  do: a dedicated `add_polygon` unit test (the established convention is
  one file per primitive, like `test_arc.py`), a `TypeScaleError`
  regression test (needs deliberately desyncing two vocabularies that are
  currently in sync), two new widget golden baselines (`NavigationDrawer`,
  `Stack`) that every sibling Wave-2/3 widget already has, and widening
  `test_primitives_baseline`'s actual scope to match its "every SDF kind"
  docstring claim (already corrected to describe current scope instead).

**Documentation-only:**
- `ARCHITECTURE.md`'s M11 milestone row ("1469 tests green") is well
  behind current reality (now ~1800) and doesn't list a dozen widgets
  shipped since — left alone since deciding whether this belongs under an
  updated M11 or a new M12 is an editorial call, not a fact correction.
- The `Canvas` drawing-context method table in `docs/view-reference.md`
  omits real keyword parameters (`opacity=1.0` on every method,
  `weight=`/`max_width=` on `text()`/`measure_text()`) — a completeness
  gap rather than a wrong claim.
- Whether `docs/view-reference.md`'s "modal drawer" elevation-level-1 row
  describes pySilver's own (single, non-elevated) `NavigationDrawer` or is
  general M3 background material is ambiguous from the surrounding prose.

## Memory and follow-through

Both the file-based session memory and the MCP knowledge graph have been
updated with the significant findings above, particularly the three
cross-cutting bugs (the ticker leak, the atlas-context omission, the
hot-reload/overlay gaps) whose fixes spanned several files landed across
different phases, so a future session doesn't need to rediscover the
reasoning behind them.
