---
name: m3-widget-design
description: Design, build, restyle, or audit a pySilver widget using Material Design 3 as the baseline design system, translated into pySilver's spec/element/layout/paint architecture. Use whenever the user asks to add a new pySilver widget, redesign or restyle an existing one, or compare a widget against Material Design -- even without saying "M3", e.g. "let's build a radio button", "add a switch widget", "make the Slider look more standard", "does our Button match the M3 spec", "we need a card widget".
---

# M3-Baseline Widget Design for pySilver

Material Design 3 is pySilver's guiding design system for widget anatomy,
sizing, colour, and interaction. This is the process for turning an M3 spec
into a real widget in this codebase, and for the two related tasks: restyling
an existing widget toward M3, and auditing one against its spec without
changing anything.

**This is a living skill.** The framework is under active construction; the
"Current framework state" section at the bottom records what exists today and
what is still stubbed. Update that section (and anything else here that has
gone stale) as part of the work whenever a milestone changes the answer.
`ARCHITECTURE.md` is the authority if the two ever disagree.

## Step 1: Get the M3 baseline

Use the `m3-lookup` skill to find the component's spec before designing or
judging anything: variants, dp dimensions, corner radii, colour-role tokens,
states. If the spec points at a cross-cutting topic -- a colour role, an
elevation level, a motion pattern -- follow `m3-lookup`'s style path for that
topic too, rather than treating the component page as the whole story.

If the widget has no clean M3 analogue (pySilver's `Horizontal`, `Vertical`, `Stack`,
`Spacer` are layout primitives with no catalogue entry), say so and design from
pySilver's own precedent instead of forcing a mapping.

## Step 2: Translate the spec

pySilver's architecture happens to line up with M3 unusually well, so most of
this is direct. State each choice anyway -- a reader should see what M3 says,
what pySilver does, and why they differ.

- **dp -> logical px is 1:1.** Layout runs entirely in logical, device-
  independent units and only converts to physical pixels in the paint pass
  (`ARCHITECTURE.md` §7). An M3 `40dp` container is `height: 40` in a view
  file. Do not scale for DPI anywhere in a widget -- `PaintContext.pixel_ratio`
  handles it, once, at emit time.
- **Colour roles map to real tokens.** pySilver implements MD3 dynamic colour
  through `materialyoucolor`, so `md.sys.color.primary` is the token
  `"primary"`, `md.sys.color.on-surface-variant` is `"on_surface_variant"`.
  Names are **snake_case** in view files (the library's own attributes are
  camelCase; `theme/tokens.py` holds the generated mapping). Check a name with
  `pysilver.theme.is_token()`; the full frozen vocabulary is `TOKEN_ORDER`
  (59 tokens). Never hard-code a hex value for something that has a role.
- **Emit tokens, not colours.** Pass `token=palette.index("primary")` to the
  display list and leave the literal `color=` at `(1, 1, 1, 1)`. The shader
  resolves the index against the palette buffer, which is what makes a theme
  switch a single buffer upload with no relayout and no display-list rebuild.
  A literal colour opts that element out of theming entirely -- only correct
  for a genuinely fixed colour.
- **Shape scale maps to `corner_radius`.** M3's `none/4/8/12/16/28/full`
  becomes a number or `[tl, tr, br, bl]`. For "full", use half the height.
  Per-corner radii are supported all the way through to the shader.
- **State layers are the established pattern.** M3's hover 8% / focus 10% /
  press 10% / drag 16% overlays. Call the shared `_emit_state_layer` rather
  than emitting the box yourself -- it cross-fades between states, so a private
  copy silently misses the animation (which is exactly what happened to
  `Button`). Follow it rather than swapping to a different container colour per
  state.
- **Ignore touch-specific rules.** pySilver is a DESKTOP framework with no
  touch support (`ARCHITECTURE.md` §1.2.1). M3 is written mobile-first, so part
  of translating it is knowing which rules are about fingers. Touch-origin
  ripple and the compact (<600dp) breakpoint do **not** apply; do not record
  them as gaps.

  The 48x48dp minimum target is the one to be careful with. It is off by
  default for the same reason -- a pointer is pixel-precise, so a control is
  hit-tested at the size it is drawn -- but a view can now ask for it with
  `min_hit_size: 48`, which grows the hit rect without touching layout or
  paint. **Never paint a 48dp container to get a 48dp target.** Quote the
  figure and say it is available as an application's choice, rather than
  recording it as something pySilver cannot express.
- **Desktop affordances rank higher.** Hover is a first-class state, not a
  nicety. Focus rings, keyboard traversal, right-click, cursor shape, and
  visible scrollbars have no mobile analogue and matter more here than they do
  in the M3 source material.
- **Elevation is a level, not a shadow you choose.** Give the widget a
  `RESTING_ELEVATION` (or a `resting_elevation` property if it depends on the
  variant, as Card and Button do) from M3's resting-level table, and call
  `elevation_shadow(...)` with `self.elevation`. Never hand-tune a blur: three
  widgets used to, and components at the same M3 level did not look like they
  were at the same height. Do **not** reach for a surface tint overlay -- M3
  deprecated it; tonal separation comes from the `surface_container_*` roles,
  which are explicitly not tied to elevation.

## Step 3: Build it

The concrete sequence in this codebase. Read the neighbouring code first --
`src/pysilver/widgets/base.py` is short and every existing widget is a worked
example.

1. **Add the kind.** A new member of `WidgetKind` in `src/pysilver/spec/models.py`.
   That enum is the authoritative list of what a view file may name; an unknown
   widget fails at load.
2. **Add style properties if needed.** `StyleSpec` is `extra="forbid"` and
   `frozen=True`, so any new property must be declared there or the view file
   is rejected. Prefer reusing existing properties over adding near-duplicates.
   Validate MD3 token fields with the `TokenRef` annotation so a bad token
   fails at load with a path, not at render.
3. **Write the element class** in `src/pysilver/widgets/base.py`:
   `class FooElement(_StyledMixin, <LayoutAlgorithm>)`, choosing the M1 layout
   node that matches the widget's geometry (`Padding` for a styled box, `Flex`
   for a linear arrangement, `Stack` for overlays).
   - Declare **no `__slots__`** -- the mixin supplies `__dict__` and the layout
     base supplies slots. Two non-empty slotted bases would conflict.
   - `__init__` calls the layout base's `__init__` explicitly, then
     `self.init_element(spec)`.
   - Implement **`configure()`** if the constructor captures anything derived
     from the spec (padding, alignment, spacing). Reconciliation calls it on
     reload; without it, an edited view file updates the spec but keeps the old
     layout parameters.
   - Implement `perform_layout(constraints) -> Size`. It **must** return a size
     satisfying its constraints, and must not read its own offset or the
     parent's size. Pass `parent_uses_size=False` when the child's size genuinely
     doesn't affect yours -- that makes the child a relayout boundary.
   - Implement `paint_self(ctx, absolute)` for anything beyond the default
     background/border/shadow. Override `child_paint_context` to clip children.
   - Emit in back-to-front order: shadow, container, state layer, content.
4. **Register it** in `_REGISTRY`.
5. **Wire handlers** if it's interactive. View files name handlers under
   `handlers:` with `on_`-prefixed keys; the dispatcher resolves them against
   the app's registry at mount and errors on an unknown name. Read state from
   `self.state` (`hovered`, `pressed`, `focused`, `scroll`, `data`).
6. **Invalidate correctly.** `mark_needs_paint()` for a visual-only change,
   `mark_needs_layout()` when geometry changes. Using the heavier one "to be
   safe" silently costs frames and is exactly what the tests below catch.

## Step 4: Test it

Most of a widget is testable with no GPU. Match the existing suites:

- **Layout** (`tests/test_layout_*.py` style, no GPU): constraints in, size
  out; padding, alignment, and flex behaviour; the invariant that size depends
  only on constraints and children.
- **Spec** (`tests/test_spec.py`): the new kind parses, bad tokens and unknown
  style keys are rejected with a useful path.
- **Paint** (`tests/test_app.py` style): assert the widget emits the expected
  number of instances, in the expected order, **with palette token indices
  rather than literal colours**.
- **Invalidation**: assert that a state change marks paint and *not* layout.
- **Golden** (`tests/golden/`, marked `@pytest.mark.gpu`): render offscreen and
  assert real pixels for anything whose correctness is visual -- corner
  rounding, borders, clipping, state layers.

## Step 5: Verify and document

```bash
.venv/bin/ruff check . && .venv/bin/ruff format . && .venv/bin/mypy && .venv/bin/python -m pytest -q
```

`mypy` runs strict and the suite must be fully green, GPU tests included, before
the widget is done. Then update `ARCHITECTURE.md` -- the widget list, and the
M3-versus-pySilver translation notes from Step 2, so the reasoning survives.

Commit when the user asks, using the `commit` skill or matching the existing
message style in `git log`. Pushing is always a separate, explicit request.

## Restyle and audit requests

If the ask is "make X match M3 better" or "does X match the spec" for a widget
that already exists, **do not jump to changing code**. Produce a gap list
first: dimensions, colour roles, shape, states, behaviour -- each with the M3
value, pySilver's current value, and a suggested target where there's a clear
opinion. Some gaps are deliberate decisions already reasoned through, and some
are blocked on framework features that don't exist yet. Let the user choose
what to close before implementing.

## Current framework state

*Last updated: after M3 component wave 2 (post-M5). Update this section whenever a milestone changes it.*

**Available:** spec/Pydantic validation with binding expressions; fine-grained
signals; element tree with state-preserving reconciliation; constraint layout
(Padding, Align, SizedBox, ConstrainedBox, Flex/Horizontal/Vertical, Stack, Flexible,
Spacer, ScrollView); the single instanced SDF pipeline with per-corner radii, borders,
shadows, analytic antialiasing and rounded in-shader clipping; the full 59-token
MD3 palette with one-upload theme switching; events with hit testing,
capture/bubble, pointer capture, hover and focus.

**Text is real as of M4.** Shaped through HarfBuzz with GPOS kerning and
ligatures, wrapped per UAX #14, fallback resolved per grapheme cluster, and
rasterised into the shared glyph atlas. Roboto Regular/Medium and Noto Sans are
bundled (`pysilver.assets`), so M3's `label-large` medium weight is available.
Measure with `TextEngine.measure` / `measure_text`, paint with `paint_text` --
both take `font_size` in logical px, matching M3's `sp`/`dp` figures 1:1.

**Focus rings are automatic.** `ElementMixin.paint()` draws M3's 2dp indicator
for any focused widget -- do not implement one per component. Two things a new
widget must do: add its kind to `FOCUSABLE_KINDS` in `runtime/events.py` if it
is interactive, and override `effective_radii` if it computes its own corner
radius at paint time, or the ring will be the wrong shape.

**Nodes have three identity fields, and they are not interchangeable.** `id` is
positional and assigned by the loader — never author one. `name` is optional,
unique, and the handle for `find()`, `anchor:`, and a selection `value:`; it is
also the reconciliation key, so a named node keeps its state across a reorder
and an unnamed one keeps state by *position*. `classes` is optional and
repeatable, and selected on by the stylesheet (`styles:`). Only name what something
references; a handler names a *function*, not the node, so a button with an
`on_click` needs no name. Names must be unique within a view and the
loader enforces it. See ARCHITECTURE.md §5.1.0.

**Views compose across files.** A `source:` key pulls a subtree in from another
file; the fragment declares `params:` and the call site passes `with:`. A
`source:` node accepts only `id:` and `with:` — there is no key merging, so
anything configurable must be a declared parameter. Ids inside a fragment are
namespaced by the call-site id. See ARCHITECTURE.md §5.1.1.

**Overlays are available.** Anything that must float above the tree —  dialog,
menu, tooltip, snackbar, sheet — is declared in the view's top-level
`overlays:` list, never as a child of what opens it. `open:` is a templated
binding; `placement` is `center`, `anchor` (with `anchor: <id>`), or an edge;
`modal`, `scrim`, and `dismissable` are style flags. See ARCHITECTURE.md §5.13.

**Single-child containers reject a second child.** Container, Card, Text, Icon
and the selection controls are `Padding`-based and take one child — wrap
several in a Horizontal or Vertical.

**Widgets today (39 kinds):** primitives — Container, Horizontal, Vertical, Stack,
Spacer, Text, Icon, ScrollView. M3 components — Button (5 variants), Card,
Divider, Checkbox, Radio, Switch, Chip, IconButton, Fab, Badge,
NavigationRail, NavItem, TopAppBar, Tabs, Tab,
SegmentedButton, Segment, ListItem, LinearProgress, CircularProgress,
Carousel, CarouselItem, **TextField**. Overlays — Dialog, Menu, MenuItem,
Tooltip, Snackbar, BottomSheet, SideSheet.

`TextField` is the only one that owns state rather than reading it; its rules
live in `text/editing.py`, deliberately apart from the widget.

**A container of items where one is selected** — rail, drawer, tabs, segmented
— subclasses `_SelectionContainer` in `widgets/navigation.py`. The container
carries `value:` (the selected child's id) and calls `set_selected` during
layout; the item reads `self.selected` and renders itself. Use the icon FILL
axis for the selected state, which is what M3 uses it for.

**Before adding a component, check `widgets/material.py` and
`widgets/navigation.py`** — together they hold nineteen worked examples and the shared helpers (`_emit_state_layer`, `_box`, `content_token`)
that a new one should reuse rather than reimplement.

**Selection is a binding, not style.** Controls read the `value:` spec field,
templated like `text:` — `value: "{{ on.get() }}"`. Use `element.checked` /
`element.number`. Do not add a style property for what is application state.

**`style.color` defaults to None**, meaning "use this component's M3 default
for its variant". Resolve it with `content_token(ctx, style, "your_default")`
so an explicit token still wins.

Where the widget *is* its whole surface -- a carousel item, a plain card --
use `paired_content_token` instead. M3 pairs a container role with an `on_`
role, so an overridden `background: primary_container` should carry
`on_primary_container` with it; otherwise the content keeps `on_surface` and
turns invisible on a light container. Do **not** use it where the background
is one part of a larger anatomy: there the variant's content token is right.

**Variants go in the `variant` style property**, validated centrally by the
`Variant` literal in `spec/models.py`. M3 usually describes variants as one
component in several configurations, so prefer that over new widget kinds.

**Icons are available.** Material Symbols ships as a 218-icon subset with the
`FILL` (0-1) and `wght` (100-700) axes live. Use the `Icon` widget with the
name in `text:` and `icon_size` / `icon_fill` / `icon_weight` in style. FILL is
how M3 expresses selected vs unselected on nav items and toggles -- reach for
it rather than swapping to a different icon name. Default size is 24 (M3's
standard), and weights below 200 are lifted automatically at that size per M3's
guidance. An unknown icon name raises; check membership with
`TextEngine.icons`.

**Sizing inside a Horizontal or Vertical:** a child styled `width: expand` (or `flex:n`)
along the main axis is flexible and shares the free space; anything else is
measured first and takes what it needs. A `Text` widget shrink-wraps to its ink
extent, so it will not starve its siblings.

**Motion exists.** Two things to know before animating colour or geometry:
palette tokens **cannot be interpolated** (they resolve in the shader), so a
colour cross-fade is two boxes at complementary alpha; if a fading border
reaches zero alpha its *width* must go to zero too, or the shader leaves a
transparent ring where the fill should reach; and never animate the icon
**FILL** axis continuously -- it is part of the glyph atlas key and the atlas
has no per-entry eviction, so quantise it (see `_stepped_fill`). Use `self.animated("key", target, duration="short4",
curve="standard")` inside `paint_self` and render what it returns; it settles
immediately on the first call and retargets on later ones. Durations and curves
are M3 tokens (`motion/easing.py`) -- look the component's timing up rather
than guessing, since M3 states many of them directly. Use `repeat=True` with
`curve="linear"` for a continuous loop; an eased loop stutters at the wrap.
`animated()` marks **paint**. If a transition genuinely changes geometry, pass
`invalidates="layout"` -- but measure first. The Carousel is the only widget
that does, and it is affordable there only because a carousel holds a handful
of items; the same choice in a `ScrollView` would relayout a thousand rows a
frame.

**Stylesheets exist.** A `styles:` list selects on widget kind, `classes:` and
`name:`, and is folded into each node's `StyleSpec` at load. A new widget needs
no work to participate -- it reads `style` as usual. Do remember that a
stylesheet value counts as **explicitly set**, so if your widget distinguishes
an authored value from a field default via `model_fields_set`, a sheet will
(correctly) win.

**Disabled state exists** and is handled centrally: `disabled:` is a templated
node field, it is inherited by children, and the M3 recolour (container
`on_surface` 12%, content 38%) is applied to the whole emitted slice in
`tree/element.py`. A new widget gets it for free -- do **not** add per-widget
disabled branches. Check `element.effective_disabled` only if a widget needs to
change *behaviour*, not appearance.

**Paint above your children with `paint_foreground`.** `paint_self` runs
*before* them, which is right for a background and wrong for a label over an
image -- the carousel item's caption was invisible until this existed.

**Text selection** lives in `text/selection.py` and works on any `Paragraph`.
If a widget needs caret geometry, use `index_at` / `rects_for` rather than
walking runs yourself -- and note offsets are snapped to grapheme clusters.

**Cursor shapes** come from a widget's `CURSOR` class attribute (or
`cursor_at(x, y)` when the shape varies by region). Anything clickable should
set `CURSOR = "pointer"`; disabled is handled centrally.

**Right-click** is `on_context_menu:`, synthesised in the dispatcher; pair it
with an overlay using `placement: pointer` to open a menu where the click
happened. Mouse buttons are one-based (1 primary, 2 secondary).

**Dragging** needs `PointerEvent.capture()` in `on_pointer_down`: capture
otherwise goes to whatever was topmost under the press, so a control drawn over
something else (a scrollbar thumb over rows) would move for one frame and stop.
Track the pointer exactly while it is down and animate only the release. Give a
thin affordance a grab band wider than its visual -- pointer precision, not M3's
finger target.

**Not all motion is timed.** A collapsing app bar is a direct function of a
scroll offset, not of a clock -- so it tracks a drag exactly and never touches
the ticker. If you build another scroll-linked widget, register it with
`ScrollView.follow()` (scrolling marks paint only, so geometry that depends on
the offset must be told), and check whether your widget's size feeds back into
that view's scrollable extent. Two things that size each other need the cycle
cut at the source: a `mark_needs_layout()` issued *during* a layout pass is
cleared when its ancestor finishes and never runs.

**Carousels exist**, and show the one case where relayout-on-scroll is right:
a snapping layout's item widths depend on scroll position, so it marks layout,
while the uncontained layout translates at paint time like any viewport. If a
widget's geometry genuinely depends on the offset, say so and mark layout; if
it does not, never do.

**Arcs exist.** The shader has a `KIND_ARC` branch (`DisplayList.add_arc`,
or the `_arc` helper in `material.py` for logical coordinates). Angles are
radians clockwise from 12 o'clock; round caps come free from the distance
field; a full turn is handled as a ring to avoid a seam. Use it for anything
circular and stroked rather than approximating with boxes.

**Scrolling exists.** Wrap content in a `ScrollView` with a bounded size on its
scroll axis (`style: {height: 300}` for the default vertical axis, or
`axis: horizontal`). It clips in-shader, handles the wheel natively with no
declared handler, and chains to an outer view at its limit. Scrolling marks
**paint only** -- if you write a widget that scrolls, never mark layout for it.
A `ScrollView` given unbounded space on its scroll axis raises, by design.

**Building an overlay component:** declare it in the top-level `overlays:` list
and let `runtime/overlay.py` own placement, scrim, modality and dismissal --
the widget supplies anatomy only. Give it a `DEFAULT_PLACEMENT` so the view
need not state the obvious, and `DOCKED = True` if it sits flush with a window
edge. Remember that an M3 minimum width **cannot** override the constraints it
is given: a node must return a size its constraints permit, so clamp with
`_clamped_width` rather than returning the minimum unconditionally.

**Verifying a widget visually:** add it to `examples/gallery/view.yaml` and
regenerate the golden baseline (ARCHITECTURE.md §11.1). The gallery is the
golden corpus, so a widget that appears there is regression-tested from then
on. Run the example with hot reload on and edit the YAML live while iterating.

**Not available yet -- design around these, and say so when a spec needs one:**

- **The type scale is fully applied.** A `text_style:` role resolves to size,
  weight, tracking *and* line height, so use one rather than a raw `font_size`
  whenever a component's M3 role is known. Line height is distributed as CSS
  half-leading, which means it changes what a label *measures* without moving
  a centred one.

  Inside a widget, hold the role itself -- `LABEL_ROLE: Final =
  TYPE_SCALE["label-large"]` -- and pass that one object to both `measure_text`
  and `paint_text`, which accept `float | TypeStyle`. Three loose numbers that
  have to match between a widget's measure and its paint are three chances to
  disagree, and a half-applied weight already caused exactly that bug. Only
  reach for a raw size plus `weight=`/`tracking=` when the size is genuinely
  computed, as the collapsing app-bar title's is.
- **RTL text.** Direction and run ordering work, but the bundled fonts carry no
  Arabic or Hebrew glyphs, and selection across a direction boundary is
  unimplemented -- the highlight is contiguous in character order, which is not
  what a bidi caret should do (risk R9).
- **Multi-line text entry and IME preedit.** `TextField` exists and is a full
  single-line editor -- caret, selection, word motion, undo, cut/copy/paste --
  but it does not wrap, and it takes committed characters only, so a composing
  input method is unsupported. Editing rules live in `text/editing.py`, apart
  from the widget and testable without a window; put new ones there.

