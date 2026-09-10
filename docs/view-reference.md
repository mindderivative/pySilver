# View file reference

A pySilver interface is a YAML document. This is the complete vocabulary: every
node field, every widget, every style property.

For *why* it is shaped this way, see [ARCHITECTURE.md](../ARCHITECTURE.md).
This page is the what.

---

## Document shape

```yaml
root:                       # the widget tree
  name: root
  widget: Vertical
  children: [ ... ]

overlays:                   # optional: content that floats above the tree
  - name: confirm
    widget: Dialog
    open: "{{ confirming.get() }}"
```

A file containing a bare widget (no `root:`) is treated as the root, so the
smallest valid view is:

```yaml
widget: Text
text: Hello
```

---

## Node fields

Every node accepts these. Only `widget` is required.

| Field | Type | Meaning |
|---|---|---|
| `widget` | enum | Which widget. An unknown name fails at load. |
| `name` | string | Optional, **unique** handle. Used by `find()`, `anchor:`, and reconciliation. |
| `classes` | string or list | Optional, repeatable categories. Selected on by [stylesheets](#stylesheets). |
| `id` | — | **Assigned by the loader.** Never author one. |
| `view` | — | **Assigned by the loader.** The view file this node was written in. |
| `style` | mapping | See [Style properties](#style-properties). |
| `text` | string | Label, or an icon name for `Icon`/`IconButton`/`Fab`/`NavItem`. |
| `value` | string | State binding — what a control *is*. See [Bindings](#bindings). |
| `default` | string | `PageHost`'s fallback child name when `value:` matches none. **Not templated.** Meaningless outside `PageHost`. See [Page host](#page-host). |
| `supporting_text` | string | Second line, trailing text, or action label, per widget. |
| `icon` | string | A Material Symbols glyph name. Templated like `text`. Meaningless on a widget with no icon anatomy. |
| `label` | string | A widget's own visible/accessible label, distinct from `text:`'s primary-content role. Templated like `text`. Meaningless on a widget with no label anatomy of its own. |
| `badge` | string | `Tab`'s optional notification content — a count or short string. Templated like `text`. Ignored (but see `style.badge_variant: dot`) when unset. Meaningless outside `Tab`. |
| `open` | string | Whether an overlay is showing. Templated like `value`. |
| `disabled` | string | Whether the control is inert. Templated. Inherited by children. |
| `error` | string | Whether a `TextField` is showing an error. Templated like `disabled`. |
| `collapsed` | string | Whether `NavigationRail` shows its narrow, icon-only anatomy (true) or its wide, labelled one (false, default). Templated like `disabled`. Meaningless on anything else. |
| `indeterminate` | string | `Checkbox`'s third M3 state — a dash instead of a checkmark, for a parent whose children are only partly checked. Templated like `disabled`. Takes precedence over `value` for which glyph paints. Meaningless on anything else. |
| `path` | string | An `Image`'s file to decode. Templated like `value`. See [Image](#image). |
| `inputs`, `outputs` | string or list | A `Node`'s named ports. Meaningless outside `NodeGraph`. See [Node graph](#node-graph). |
| `edges` | list | A `NodeGraph`'s declared wires, each `{source, target}` as `"node.port"`. See [Node graph](#node-graph). |
| `handlers` | mapping | `on_*` keys to handler names registered in Python. |
| `children` | list | Child nodes. |

### `name` versus `classes`

`name` is an identity and must be unique — a duplicate is rejected at load,
because `find()` would otherwise silently return the wrong node. `classes` is a
category and repeats freely:

```yaml
- name: save_btn          # exactly one node is 'save_btn'
  classes: action primary # many nodes may be 'action'
  widget: Button
```

Only name what something references. A handler names a *function*, not a node,
so a button with an `on_click:` needs no `name`.

Leaving a node unnamed has one cost, and it is worth understanding: an unnamed
node's state is bound to its **position**, so after a reorder the element at
index 0 is reused and given the other node's spec. For a `Divider` that is
meaningless; for anything holding focus, scroll, or text, give it a name.

---

## Bindings

`text`, `value`, `open`, `supporting_text`, `path`, `icon`, `label`, and `badge` accept
`{{ expression }}` templates evaluated against signals exposed from Python:

```yaml
- name: count
  widget: Text
  text: "Clicked {{ clicks.get() }} times"

- name: dark_toggle
  widget: Switch
  value: "{{ dark.get() }}"
```

```python
app.expose(clicks=Signal(0), dark=Signal(True))
```

Expressions run in a sandbox. Attribute access, comprehensions, lambdas,
imports, and dunder access are rejected — a view file is exactly the kind of
artefact people copy from the internet.

Conditionals work, which is how a widget changes icon or label:

```yaml
text: "{{ 'favorite' if saved.get() else 'favorite_border' }}"
```

---

## Handlers

```yaml
handlers:
  on_click: save
```

```python
@app.handler
def save(event) -> None: ...
```

Available keys: `on_click`, `on_context_menu`, `on_pointer_down`,
`on_pointer_up`, `on_pointer_move`, `on_pointer_enter`, `on_pointer_leave`,
`on_wheel`, `on_key_down`, `on_text`, `on_focus`, `on_blur`, `on_change`,
`on_dismiss`.

`on_change` is the odd one: it is posted by a widget rather than by the window,
and its event carries `event.value` — the new text — so a handler does not have
to reach back into the field to find out what it is. `on_dismiss` is posted by
the overlay layer when the *runtime* closes an overlay — Escape, or a press
outside a dismissable one — so an application can clear whatever signal its
`open:` is bound to. See [Two ways for a dialog to behave](#two-ways-for-a-dialog-to-behave).

An unknown handler name fails at mount, not at the first click.

### Handlers run in two phases

An event travels down to the target (capture) and back up (bubble), and a
handler you declare is invoked in **both**. That lets an ancestor intercept an
event before the target ever sees it — call `event.stop_propagation()` during
capture and the target never runs.

The consequence is worth knowing: a handler on an **ancestor** of the target
runs **twice** for one event. Check the phase when that matters:

```python
@app.handler
def on_card_click(event) -> None:
    if event.phase is not Phase.CAPTURE:
        ...  # runs once, on the way back up
```

A handler on the target itself runs once, so the common case is unaffected.

---

## Composition

A view can pull in another file, so shared pieces live once:

```yaml
- name: card
  source: parts/info_card.yaml
  with:
    title: "Storage"
    body: "42% used"
```

The included file declares its interface:

```yaml
params: [title, body]
widget: Card
children:
  - {widget: Text, text: "{{ title }}"}
  - {widget: Text, text: "{{ body }}"}
```

There are no merge rules: a call site passes `name:`, `source:`, and `with:`,
and everything the fragment needs to be told must be a declared `param`. Names
inside a fragment are namespaced by the call site (`card.title`), so including
one twice does not collide. Includes cannot escape the view directory.

---

## Overlays

Content that floats above the tree — dialogs, menus, tooltips, snackbars,
sheets. Declared at the top level rather than nested, because an overlay is not
laid out or clipped by whatever opened it.

```yaml
overlays:
  - name: menu
    widget: Menu
    open: "{{ menu_open.get() }}"
    style: {anchor: menu_btn}      # implies placement: anchor
    children:
      - {widget: MenuItem, text: Cut, supporting_text: "Ctrl+X"}
```

| Property | Effect |
|---|---|
| `placement` | `center`, `anchor`, `pointer`, `top`, `bottom`, `left`, `right` |
| `anchor` | `name:` of the element to attach to |
| `modal` | blocks input to everything beneath |
| `scrim` | draws M3's 32% backdrop |
| `dismissable` | closes on Escape or a click outside (default `true`) |
| `offset` | gap from the anchor, in dp |
| `has_submenu` | a `MenuItem` draws a trailing `chevron_right` instead of `supporting_text` — see below |

### Submenus

A `MenuItem` that opens a submenu carries `has_submenu: true`, which draws a
trailing `chevron_right` in place of `supporting_text`. The submenu itself is
a second `Menu` overlay, declared *after* the parent menu, anchored to the
item's `name`:

```yaml
overlays:
  - name: main
    widget: Menu
    open: "{{ menu_open.get() }}"
    style: {anchor: menu_btn}
    children:
      - {name: new, widget: MenuItem, text: New}
      - name: recent
        widget: MenuItem
        text: Open Recent
        style: {has_submenu: true}
        handlers: {on_pointer_enter: openRecent}
  - name: recent_menu
    widget: Menu
    open: "{{ recent_open.get() }}"
    style: {anchor: recent}       # a name inside the OTHER overlay above
    children:
      - {widget: MenuItem, text: report.docx}
```

An anchor that names something inside another overlay resolves there once the
main tree has no match — this is the one case an anchor target is not a plain
widget. Anchoring to a `MenuItem` specifically also changes *how* it
positions: beside the item (flipping to the other side near an edge) rather
than below it, matching M3's stated submenu placement.

### Two ways for a dialog to behave

These three properties combine into the two behaviours a modal dialog usually
wants, and the difference is only `dismissable`.

**Dismissable** — clicking outside closes it. Wire `on_dismiss`, because that
is what actually closes it:

```yaml
- name: confirm
  widget: Dialog
  open: "{{ confirming.get() }}"
  style: {modal: true, scrim: true}          # dismissable defaults to true
  handlers: {on_dismiss: close_confirm}      # sets confirming to false
```

**Locked** — the parent is dimmed and unclickable, focus cannot leave, and the
dialog closes only through its own buttons:

```yaml
- name: confirm
  widget: Dialog
  open: "{{ confirming.get() }}"
  style: {modal: true, scrim: true, dismissable: false}
```

The gallery has one of each, built from the same `Dialog` and one property
apart: `parts/confirm_dialog_View.yaml` and `parts/locked_dialog_View.yaml`.

**`on_dismiss` is not optional for a dismissable overlay whose `open:` is
bound**, which is every overlay an application controls. The runtime closing it
is a *request*: the binding still says open, so without a handler to clear the
signal the overlay would reopen on the next frame. Escape goes through the same
path, so one handler covers both.

Most components know where they belong: `BottomSheet` and `Snackbar` default to
`bottom`, `SideSheet` to `right`, `Dialog` to `center`. Setting `anchor:` alone
implies `placement: anchor`. Declaration order is z-order.

---

## Stylesheets

`styles:` is a list of rules applied to every node before the interface is
built. It is what `classes:` exists for.

```yaml
styles:
  - style: {corner_radius: 12}                      # baseline: everything
  - widget: Button
    style: {height: 44, width: 150}
  - classes: danger
    style: {background: error, color: on_error}
  - name: confirm
    style: {width: 220}

root:
  widget: Vertical
  children:
    - {name: save,    widget: Button, text: Save}
    - {name: confirm, widget: Button, classes: danger, text: Confirm}
```

A rule matches on any combination of `widget:`, `classes:` (**all** listed
classes must be present), and `name:`. A rule with no selector matches
everything, which is how you set a baseline.

### Precedence

Lowest to highest:

1. rules with no selector
2. `widget:` rules
3. `classes:` rules — more classes beat fewer
4. `name:` rules
5. the node's own inline `style:`

Ties within a level go to document order, later winning — the same rule CSS
uses. **Rules merge rather than replace:** each contributes only the properties
it actually sets, so a `widget:` rule setting `height` and a `classes:` rule
setting `background` both apply.

### Sharing a sheet across files

A `styles:` entry of the form `- source:` splices in the rules that file names,
so a theme lives in one place:

```yaml
# theme.yaml -- a bare list of rules
- classes: action
  style: {width: 100, height: 40, variant: outlined}
- classes: action primary
  style: {variant: filled}
```

```yaml
# view.yaml
styles:
  - source: theme.yaml
  - widget: Button          # a local override: later, so it wins the tie
    style: {height: 48}
```

Rules land **in place**, so ordering reads as written — an import placed after
a local rule overrides it, not the other way round. A sheet may import another.

Every file is watched by hot reload, so editing a theme restyles a running
application without losing focus, scroll, or text.

A stylesheet is a **list**; a widget fragment is a **mapping**. Including one
where the other belongs says so directly rather than failing later as a
confusing error about a file that was perfectly valid. The same guards apply as
to widget includes: no escaping the view directory, no cycles, and a depth
limit.

**Do not use a selector-less rule to set `corner_radius` or other shape
properties globally.** It would override each component's own M3 shape — a
`Button` is a pill at half its height, a `Card` is 12dp — and flatten the
catalogue to one radius. A stylesheet is for the choices an application makes,
not for overwriting the design system beneath it.

### What it costs

Nothing per frame. Rules are folded into each node's style once, at load, so
layout and paint read `style` exactly as they do for a hand-written one.
Changing a stylesheet is a reload, which hot reload already handles — and
because reloading reconciles rather than replaces, restyling a running
application keeps focus, scroll, and text.

Selectors are structured rather than CSS-like strings, deliberately: a `#name`
selector would need quoting in every rule, because YAML reads `#` as a comment.

## Type scale

M3 defines fifteen type roles, from `display-large` to `label-small`. Name one
with `text_style:` instead of a raw size:

```yaml
type_scale:
  title-large: 22
  body-medium: 14

root:
  widget: Vertical
  children:
    - {widget: Text, text: Heading, style: {text_style: title-large}}
    - {widget: Text, text: Body,    style: {text_style: body-medium}}
```

A scale can live in its own file and be shared, like a stylesheet:

```yaml
type_scale: {source: typescale.yaml}
```

Roles resolve to `font_size` once at load, so nothing is paid per frame, and a
role beats an explicit `font_size` on the same node.

### The built-in scale

All fifteen roles work without declaring anything; `type_scale:` overrides them
role by role.

| | large | medium | small |
|---|---|---|---|
| **display** | 57 | 45 | 36 |
| **headline** | 32 | 28 | 24 |
| **title** | 22 | 16 | 14 |
| **body** | 16 | 14 | 12 |
| **label** | 14 | 12 | 11 |

**Where these come from.** The spec page at
<https://m3.material.io/styles/typography/type-scale-tokens> serves a
JavaScript shell with no table in the delivered HTML — which is why the copy in
this project's reference library is empty. The figures instead come from
Google's autogenerated token source in the Material Web Components repository
(`tokens/versions/latest/sass/_md-sys-typescale.scss`, Material 3 version
**34.0.21**), converted from `rem` at 16px/rem.

They agree with every value the reference library corroborates independently,
and settle the one it contradicts itself on: `headline-large` appears there as
both 32sp and 36sp, and the token source says **32**. Tests pin both facts.

A role carries three more tokens beside its size: **weight**, **tracking** and
**line height**. `title-medium`,
`title-small` and every `label-*` role are Medium (500), the rest Regular
(400); Roboto ships both faces, so those are genuinely Medium rather than
emboldened Regular. Tracking becomes `letter_spacing`, and nine of the fifteen
roles have some — `body-large` and the two smallest labels the most, at half a
pixel, and `display-large` the only negative one at −0.25.

| | tracking |
|---|---|
| `display-large` | −0.25 |
| `title-medium` / `body-small` | 0.15 / 0.4 |
| `title-small` / `label-large` | 0.1 |
| `body-medium` | 0.25 |
| `body-large`, `label-medium`, `label-small` | 0.5 |
| everything else | 0 |

Line height becomes `line_height`, a fixed height in logical px replacing the
font's own. The two do not differ much, and not always in the same direction:
Roboto wants 67px at `display-large` where M3 asks for 64, and 19px at
`body-large` where M3 asks for 24.

An explicit `font_weight:`, `letter_spacing:` or `line_height:` beside a role
wins — naming a role states an intent, and writing one of these beside it
states a more specific one. Overriding a role's size in `type_scale:` leaves
all three alone: they are separate tokens, and resizing a role says nothing
about them.

Tracking is **absolute**, in logical px, the way M3 states it — it does not
scale with `font_size`, so a role's tracking is only right at that role's size.
It is added after every grapheme cluster, including the last on a line, as CSS
`letter-spacing` is. That leaves centred text off-centre by half a tracking
value, a quarter-pixel at the largest figure in the scale; the alternative is
special-casing line ends in the measurement, the caret and the paint pen
separately, and those three drifting apart is a worse bug than a quarter-pixel.

Line height is **absolute** too, and the extra space is split evenly above and
below the glyphs, the way CSS distributes half-leading. That has a useful
consequence: raising a line's height does not move centred text. A button's
label measures 20px tall instead of 17 and sits in exactly the same place. Text
positioned from its *top* does move, by half the difference.

A line height shorter than the font's own is allowed and does occur in the
scale; the leading is simply negative, and lines close up rather than the
glyphs being cropped.

## ViewModels

A view file can own its logic. One view, one ViewModel — the familiar MVVM
shape, with the naming convention enforced rather than suggested.

```python
# parts/swatch_ViewModel.py
from pysilver import Signal, ViewModel


class Swatch(ViewModel):
    picked = Signal(False)

    def pick(self, event) -> None:
        self.picked.set(True)
```

```yaml
# parts/swatch_View.yaml
name: swatch
widget: Container
style: {background: "{{ 'primary' if picked.get() else 'surface' }}"}
handlers: {on_click: pick}
```

```python
# app.py -- the entry point, and the composition root
app.bind_view_model("parts/swatch_View.yaml", Swatch())
```

Public attributes become names the view's `{{ }}` can read; public methods
become handlers its `handlers:` can name. Nothing is registered twice.

**Binding is explicit, and deliberately not by filename.** A view file naming
its own Python module would let data decide what gets imported, and view files
are untrusted input here — `yaml.safe_load` only, includes confined to the view
directory, no `eval`. The application imports its own code and says what pairs
with what. The convention is then *checked*: a bound view must be
`*_View.yaml` and its ViewModel must live in `*_ViewModel.py`, or binding
raises. Views without a ViewModel need no suffix.

**Resolution order** is the view's own ViewModel, then the application's
`expose`/`handler` registry. Local wins, so a fragment can name things without
knowing what the rest of the application calls them, and an application-wide
signal still reaches a nested view without being threaded through every
include.

**One view file, one ViewModel.** Including a fragment five times gives five
copies of the *view* and one ViewModel behind them — right for logic belonging
to the view, so per-instance state stays on the widget's own `state`.

**Sharing between ViewModels is Python's job.** A parameter is textual
substitution into YAML, so a child cannot be handed an object through `with:`.
Pass it to the child's constructor where the application composes them — the
gallery's `app.py` hands its dialogs the signal each one opens on, and each
dialog publishes it under its own view's name.

Two consequences worth knowing:

- An expression written at a *call site* and passed through `with:` is
  evaluated in the *fragment's* scope, because that is where the node ends up.
  Give the fragment's ViewModel the name instead of borrowing the parent's.
- `self.app` reaches the application for the few things that genuinely are its
  own — switching the theme is the honest example. It is deliberately not
  visible to `{{ }}` expressions.

## Accessibility

pySilver builds the semantic tree — roles, names, states, bounds — and an
optional bridge pushes it to the platform.

```python
from pysilver.runtime.accesskit_bridge import AccessKitBridge, available

if available() is None:  # a sentence when it cannot run
    app.bind_accessibility(AccessKitBridge(window_title="My app"))
```

**It is opt-in and Linux-only today.** The bridge needs `accesskit`, a native
wheel, so it is an extra: `pip install 'pysilver[a11y]'`. AccessKit ships its
Windows and macOS adapters in their own platform wheels, so this build serves
AT-SPI and `available()` says so rather than leaving it to be discovered.
Without a bridge bound, nothing reaches a screen reader.

```python
tree = app.accessibility_tree()
confirm = tree.find(role="button", name="Confirm")
assert confirm.bounds.width == 130
```

The tree is worth having with or without a bridge: it is what the bridge is
handed, and it lets a test ask for *the button called Confirm* rather than for
a rectangle at some coordinate.

A reader can also *operate* the interface — every clickable role advertises the
click action, and requests are applied on the engine thread a frame later,
because AccessKit delivers them from its own D-Bus thread and pySilver's
signals are thread-affine.

**Roles are sourced where M3 states one** — a text field is `textbox`, a
progress indicator has the "role of 'progressbar'", a navigation item is `tab`,
and a navigation *container's* "role is not announced". The rest follow ARIA
convention, and the module marks which is which rather than smoothing over the
difference.

Three rules worth knowing when writing views:

- **`name:` is never announced.** It is a developer handle; reading out
  `sw_primary` would be worse than silence. It travels as `key` so tests can
  still find a node by it.
- **An icon name is never announced.** For `IconButton`, `Fab` and `NavItem`,
  the accessible name comes from `label:` rather than `text:` — `text:` no
  longer carries anything for these widgets (their glyph name lives in
  `icon:`). **An icon-only control with no `label:` has no accessible name at
  all** — that is a real gap in a view, and the tree reports an empty name
  rather than inventing one. Plain `Icon` is never announced at all, since it
  is decorative.
- **Layout and decoration disappear.** A `Spacer` is dropped entirely and a
  silent container's children are lifted into its place, so a reader never
  walks through a level that says only "group".

Visible overlays are appended to the root, because a dialog is not a child of
what it covers; a closed one is absent entirely rather than present-but-hidden.

## Hit targets

A control is clickable at the size it is drawn, which on a pixel-precise
pointer is what you want. Two properties widen that without touching anything
else:

```yaml
- name: agree
  widget: Checkbox
  style: {min_hit_size: 48}      # M3's "at least 48x48dp", on an 18dp box
```

`min_hit_size` is a minimum square centred on the painted control, and it is
the way to write M3's rule: the figure stays correct when the control's size
changes, where padding worked out by hand does not. `hit_padding` takes the
same forms as `padding` — one number, or `[left, top, right, bottom]` — for the
asymmetric cases a minimum cannot state.

**Neither affects layout or paint.** The control keeps its size, its neighbours
keep their positions, and what is drawn is identical. Only where clicks, hover,
and the cursor shape are picked up changes.

Three things worth knowing:

- A widened target **reaches outside its parent** if it needs to. A 48dp target
  on an 18dp checkbox in a 40dp row extends past the row, and clicks there
  still arrive.
- Two widened targets **can overlap** where the drawn controls do not. M3 asks
  for 8dp between targets and nothing here enforces it; where they overlap, the
  one drawn later wins, exactly as overlapping paint does.
- A widget that **clips** its children — `ScrollView`, `Carousel`,
  `SegmentedButton` — clips their targets too. A control scrolled just past the
  edge does not take clicks it cannot visibly respond to.

## Text fields

The only widget that takes typing.

```yaml
- name: email
  widget: TextField
  text: "Email"                     # the label
  value: "{{ email.get() }}"        # the content
  supporting_text: "We never share it"
  error: "{{ not valid.get() }}"
  style: {variant: outlined, width: 320}
  handlers: {on_change: set_email}
```

`text:` is the label, `value:` is the content and `supporting_text:` is the
line beneath — the same three fields every other widget already has, rather
than a `label:` invented for one component. Binding `value:` makes the field
controlled: the application can put text into it at any point, and each edit
fires `on_change` with the new value.

The label "floats upward to 12sp typography scale when focused or populated" —
M3's words, and the reason it animates between `body-large` and `body-small`
rather than between two chosen numbers. `variant: filled` (the default) has a
1dp bottom indicator that thickens to 2dp on focus; `variant: outlined` has a
border that does the same.

**What the keyboard does:**

| Keys | Effect |
|---|---|
| Arrows | Move by grapheme cluster; Home / End go to the ends |
| Ctrl+arrows | Move by word |
| Shift+anything | Extend the selection instead of moving |
| Backspace / Delete | Remove the selection, or one cluster; Ctrl to take a word |
| Ctrl+A / C / X / V | Select all, copy, cut, paste |
| Ctrl+Z, Ctrl+Shift+Z, Ctrl+Y | Undo and redo |

A run of typing is **one undo step**. The run breaks when the caret moves, when
a selection is replaced, or when a deletion intervenes — the three rules a text
editor uses, so undo takes back a word rather than a letter.

Editing is by **grapheme cluster** throughout: backspace removes an accented
character rather than its accent, and the caret never lands inside a flag
emoji. Word boundaries are whitespace-delimited, not UAX #29 — the same rule
double-click uses, so the two always agree.

**Three shapes, and M3 names all three.** A plain field is one line: text
longer than the box scrolls sideways to follow the caret, and scrolls back
rather than leaving empty space when you delete.

```yaml
- {name: note, widget: TextField, text: "Note", style: {multiline: true}}
- {name: body, widget: TextField, text: "Body",
   style: {multiline: true, height: 140}}
```

`multiline: true` gives M3's **multi-line field**, which "grows to accommodate
multiple lines of text" and "initially appears as a single-line field" — so an
empty one is exactly 56dp and it expands by a line at a time as the text wraps.
Adding a `height:` gives M3's **text area**: "fixed-height fields" that "scroll
vertically when the cursor reaches the bottom". The difference between the two
forms is only whether you fixed a height, so there is no second property.

In a multi-line field **Enter inserts a newline**; in a single-line one it is
left alone, so a view can put a handler on it. **Up and Down move by a line as
drawn**, preserving the column, so arrowing down from the end of a short line
lands at the same horizontal position on the next one rather than at its start.
Home and End become line-relative, and End stops before the newline.

Copy and paste use the system clipboard — see [The clipboard](#the-clipboard).

## Search bar

`SearchBar` is M3's search bar — a 56dp pill (never square, never floating a
label) with a fixed leading search icon. Built on the same underlying
editing model `TextField`/`CodeEditor` use, not by subclassing `TextField`
itself, since the anatomy is different enough (always single-line, always a
pill, no floating label) that subclassing would mean overriding nearly
everything.

```yaml
- name: search
  widget: SearchBar
  value: "{{ query.get() }}"
  supporting_text: "Search"
  handlers: {on_change: set_query}
```

`value:` is the typed query, the same convention `TextField` uses.
`supporting_text:` is a placeholder shown only while the field is empty and
unfocused — M3's own "Supporting text" anatomy element, not a caption below
the field the way `TextField`'s `supporting_text:` is. `icon:` names an
optional trailing icon (M3: "A search bar should have one or two trailing
icons"); leaving it unset means no trailing icon, just the leading search
glyph. Width is clamped to M3's own 360–720dp range regardless of what a
view asks for.

**The expanded "Search View" — a results list shown below the bar — is not
a second widget.** It is the same shape `Menu`/`MenuItem` already solve: an
application composes it from a `Menu` overlay anchored to the search bar's
own `name`, opened and closed from its own state, exactly the way a
`MenuItem` with `style.has_submenu` anchors its own submenu.

## Code editor

`CodeEditor` is a multi-line, syntax-highlighted, line-numbered text editor.
No M3 component exists for it — it is built on the same underlying editing
primitives `TextField` is, rather than on `TextField` itself, since a code
editor has none of a text field's M3 chrome (a floating label, an indicator
stroke).

```yaml
- name: source
  widget: CodeEditor
  value: "{{ file_contents.get() }}"
  style: {language: python, height: 400, width: expand}
  handlers: {on_change: set_source}
```

`value:` is the buffer, the same convention `TextField` uses. Unlike a
`TextField`, **`CodeEditor` needs a bounded height** — it never grows to fit
its content, and never wraps a long line (it scrolls sideways instead), so
that its line numbers always correspond 1:1 with the buffer's own lines.

**Syntax highlighting** comes from [Pygments](https://pygments.org/), an
optional dependency (`pysilver[code]`) rather than a hard one. Set
`style.language` to a Pygments lexer name or alias (`python`, `yaml`,
`javascript`, ...); leaving it unset, or naming a language Pygments does not
recognise, leaves the buffer uncoloured rather than raising. The colours
themselves are fixed, not part of the M3 theme — there is no dark/light
variant, and no way to override them from a view file today.

**Defaults to a bundled monospace font (Hack Nerd Font Mono)** when
`style.font_family` is unset — closing this widget's own former
proportional-default gap ("No monospace font ships with pySilver" used to
be true here; it no longer is). `style.font_family` still names any other
face by family name if the application wants to override it:

```python
app.text.db.load("/path/to/JetBrainsMono-Regular.ttf")
```

See `assets/fonts/README.md`'s "Monospace" section for the measurement and
provenance.

**What the keyboard does**, on top of everything [Text fields](#text-fields)
already lists (arrows, word motion, selection, clipboard, undo/redo — all
identical here):

| Keys | Effect |
|---|---|
| Home / End | Start / end of the current source line, not the whole buffer |
| Ctrl+Home / Ctrl+End | Start / end of the whole buffer |
| Tab | Inserts `style.tab_size` spaces; indents every line a selection touches instead, so it never just replaces a multi-line selection with four spaces |
| Shift+Tab | Dedents the current line, or every line a selection touches |
| Enter | Auto-indents the new line to match the current one's leading whitespace |

Tab does not move focus while a `CodeEditor` is focused — press **Escape**
first (which always defocuses, for any widget) to reach the next control by
keyboard.

**`style.read_only: true`** makes the buffer selectable but not editable —
for showing a fixed code sample with real syntax highlighting rather than a
plain `Text` block. It blocks typing and every mutating key (Tab, Enter,
Backspace, Delete, paste, undo/redo) while leaving caret motion, keyboard
and mouse selection, Ctrl+A, and copy fully working. `disabled:` is the
wrong tool for this — it also blocks pointer selection, which a read-only
sample still needs.

**Not implemented**: auto-closing or matching brackets, multiple cursors,
code folding, a minimap, a draggable scrollbar thumb (the wheel and the
keyboard both scroll; there is no visible, grabbable indicator yet), and
incremental re-parsing for very large files (Pygments re-lexes the whole
buffer on every edit). Language server integration is deliberately out of
scope for the widget itself — that is an application concern, composed from
whatever LSP client a project already uses, not something `CodeEditor`
hard-depends on.

## Terminal

`Terminal` is a real shell, spawned and parsed by pySilver itself. No M3
component exists for it. Unlike `Video`, which only displays frames an
application decodes and pushes, `Terminal` owns the whole pipeline: point it
at a shell and it works.

```yaml
- name: shell
  widget: Terminal
  style: {shell: "bash -l", width: expand, height: 400}
```

`style.shell` is the command line (`shlex.split`, so `"bash -l"` works);
left unset it resolves `$SHELL`, falling back to `/bin/sh`. The grid size
(columns × rows) follows the widget's own pixel size and cell size — there
is no separate `cols:`/`rows:` to keep in sync by hand, and resizing the
widget resizes the shell's own idea of its terminal size too.

**POSIX only in this pass.** Spawning a real pseudo-terminal needs
`pysilver[terminal]` (`bittty` for VT/ANSI parsing, `pexpect` for the PTY —
both optional, and neither can become a hard dependency: `bittty` is
WTFPL, `pexpect` is ISC). Without them, or on Windows (not yet
implemented — see the widget's own docstring for why), the terminal area
shows a message explaining what is missing instead of a shell.

**Defaults to a bundled monospace font (Hack Nerd Font Mono)** when
`style.font_family` is unset — [Code editor](#code-editor) shares the same
default now. Found live, 2026-09-08: with the previous default (Roboto,
proportional), the cursor visibly detached from typed text by several
columns after a few keystrokes, since the cell/cursor grid assumes every
glyph shares one advance width — confirmed by direct measurement, not just
visual impression (see `assets/fonts/README.md`'s "Monospace" section).
Hack Nerd Font Mono also carries ~9,000 Nerd Font icon glyphs, closing a
separate gap where icon-heavy shell prompt themes (starship, fish-pure,
`eza --icons`) rendered their own glyphs as visible missing-glyph boxes.
Set `style.font_family` to any other face to override.

**No scrollback.** `bittty` (swapped in for `pyte` on 2026-09-08, after a
real `pyte` parsing defect corrupted typed input under some shell prompt
plugins — see the widget's own docstring) keeps no scrollback buffer at
all, a documented limitation of the library, not an oversight. The mouse
wheel over a Terminal does nothing; re-implementing scrollback against
`bittty` is a tracked follow-up, not done yet.
**Ctrl+C is always the interrupt byte** sent to the shell, never a copy
shortcut — there is no text selection to copy in this pass, so nothing was
taken from Ctrl+C to make room for one.

**Not implemented**: mouse text selection and copy, underline and
strikethrough rendering, function keys beyond F1–F4, scrollback (see
above), and Windows support.

## Page host

`PageHost` mounts exactly one child at a time, chosen by name — the piece
this format is missing for a single-page-application shell: a navigation
rail switching between per-destination pages, none of which should exist
(or, for a `Terminal` page, keep a shell process running) while some other
page is showing. No M3 component; nothing in the reference library names
this shape.

```yaml
- name: content
  widget: PageHost
  value: "{{ current_page.get() }}"   # names the active child, by `name`
  default: home                        # shown if value: matches nothing
  children:
    - {name: home, widget: Vertical, source: pages/home_View.yaml}
    - {name: terminal, widget: Terminal}
```

`value:` follows the exact convention `Tabs` / `NavigationRail` /
`SegmentedButton` already use: the `name` of the active child. `default:` is
plain, **not templated** — it names a fixed fallback page chosen at design
time, shown whenever `value:` doesn't resolve to any declared child (unset,
a typo, a signal not yet initialised), not something a binding should move
around.

**Every declared child is built up front**, the same eager recursion every
other widget's children go through — but only the active one is ever
*alive*. A hidden page never ticks an animation, never paints, and a hidden
`Terminal` page holds no shell process, because `PageHost` exposes only the
active child through its own `children`, and every propagating mechanism in
the tree (`find()`, ticker/text-engine/image-atlas assignment, painting,
`dispose()`) reaches children through exactly that.

**Switching disposes the outgoing page and re-arms the incoming one.**
Local state that isn't tied to being alive — a `SpinBox`'s number, a
`Checkbox`'s value — survives a round trip, because the object itself is
never rebuilt. State that *is* tied to being alive does not: a `Terminal`
page's shell is stopped when its page goes dormant, and a fresh one starts
if that page is visited again; a scroll position or a dragged `NodeGraph`
node's transient state is not preserved either. This matches "loaded on
event" literally and is the standard behaviour of page-based navigation
elsewhere (WPF's `Frame`, for one).

## Text selection

A `Text` widget with `selectable: true` can be selected with the mouse:

```yaml
- name: quote
  widget: Text
  text: "Selectable, and copyable with Ctrl+C."
  style: {selectable: true, width: 400}
```

Click to place a caret, drag to extend, double-click for a word, **Ctrl+A** for
all of it, **Ctrl+C** to copy. Selection moves by **grapheme cluster**, so an
edge never lands inside a flag emoji or between a letter and its accent. A
selectable block takes focus and shows a text cursor.

It is **off by default**, because a selectable label shows a text cursor and
swallows drags — wrong for the labels most text in an interface is.

### The clipboard

**Ctrl+C and Ctrl+V use the system clipboard.** This previously said pySilver
shipped none, on the grounds that the only route was the backend's private
window handle. That was wrong: GLFW's clipboard functions take the window as a
*deprecated* parameter and accept `None`, so no private state is involved. A
window is created, GLFW is initialised, and the backend is installed.

Two constraints are worth knowing, both from Wayland rather than from pySilver:

- **Reading needs keyboard focus.** A client may only read the selection while
  focused. That is always true of a user pressing Ctrl+V, and never reliably
  true of a program driving the clipboard by itself.
- **Writing needs a recent input event.** A compositor accepts a new selection
  only with a serial from a real keystroke or click behind it. Again: true of
  Ctrl+C, not of a background thread.

A read that comes back empty falls back to whatever this process last copied,
so pasting inside an application keeps working when the system read is refused.
The trade is that clearing the clipboard elsewhere does not clear this one.

An application can still install its own backend, which takes precedence:

```python
from pysilver.runtime.clipboard import clipboard
import pyperclip


class SystemClipboard:
    def set_text(self, text: str) -> bool:
        pyperclip.copy(text)
        return True

    def get_text(self) -> str:
        return pyperclip.paste()


clipboard.install(SystemClipboard())
```

### What is not implemented

- **Editing.** This is selection on a `Text`, which is read-only. For typing,
  use [`TextField`](#text-fields).
- **Selection across widgets.** A drag selects within one `Text`.
- **UAX #29 word boundaries.** Double-click uses whitespace delimiting, which
  is simple and predictable rather than Unicode-correct.

Bidirectional text is handled: selecting across a left-to-right /
right-to-left boundary paints as separate rects rather than one span
stretched across the gap, and a caret sitting exactly at a direction
boundary lands at the correct on-screen position rather than one derived
by accident of iteration order.

The pointer changes shape over what it is on, without you asking:

| Over | Shape |
|---|---|
| anything clickable — button, checkbox, radio, switch, chip, menu item | `pointer` |
| a **disabled** control | `not-allowed` |
| a scrollbar thumb | `ns-resize` / `ew-resize` |
| a bottom sheet's drag handle | `ns-resize` |
| everything else | `default` |

`cursor:` overrides it on any node. The topmost element with an opinion wins, so
a button inside a container gets the button's shape and the container keeps its
own everywhere the button does not reach.

An unknown name fails at load rather than from inside a frame.

## Context menus

A right-click fires `on_context_menu`, and an overlay with `placement: pointer`
opens where the click happened:

```yaml
root:
  children:
    - name: canvas
      widget: Container
      handlers: {on_context_menu: show_menu}

overlays:
  - name: ctx
    widget: Menu
    open: "{{ menu_open.get() }}"
    style: {placement: pointer}
    children:
      - {widget: MenuItem, text: Cut,  supporting_text: "Ctrl+X"}
      - {widget: MenuItem, text: Copy, supporting_text: "Ctrl+C"}
```

```python
@app.handler
def show_menu(event) -> None:
    menu_open.set(True)
```

The event carries the point that was clicked, and the menu opens down and to the
right of it — flipping near an edge rather than being clipped. It closes on a
click outside or on Escape, like any other dismissable overlay.

A secondary press does **not** press, focus, or click the thing under it, so
right-clicking a button does not leave it stuck looking pressed.

## Elevation

M3 gives every component a resting **level**, 0 to 5, and each level a dp
height. A level says where a surface sits relative to others; the height is
what produces a shadow.

| Level | Height | Components that rest there |
|---|---|---|
| 0 | 0dp | filled/tonal/outlined buttons, filled/outlined cards, chips, tabs, lists, rail |
| 1 | 1dp | elevated button, elevated card, modal bottom sheet, modal side sheet, modal drawer |
| 2 | 3dp | menu, scrolled app bar, rich tooltip |
| 3 | 6dp | FAB, modal dialog |
| 4–5 | 8/12dp | not resting levels — reserved for interacted states |

Components take their own level, so you rarely set one:

```yaml
- {name: fab, widget: Fab, text: add}                    # level 3, from M3
- {name: flat, widget: Fab, style: {elevation: 0}}       # deliberately flat
```

Hovering or focusing something already raised lifts it one level, which is what
M3 describes. A level-0 component stays flat — a filled button growing a shadow
under the pointer is not what the spec means.

**On tonal elevation.** M3 used to express elevation partly as a surface *tint*
overlay. That mechanism is **deprecated**: "Surface tint color is deprecated.
Use elevation level tokens (0–5) instead." Tonal separation now comes from
choosing among the `surface` and `surface_container_*` roles, which the spec
says are "not tied to elevation" — so picking a container role and setting a
level are two independent decisions, and pySilver treats them that way.

## Dragging

Two things respond to a drag, and both are affordances that would otherwise be
decoration:

- **A scrollbar's thumb.** Grab it anywhere it is drawn — plus a few pixels
  either side, because a 4dp target is unusable with a mouse — and the content
  keeps pace with the pointer.
- **A bottom sheet's drag handle.** Drag the sheet down; release past about a
  third of its height to dismiss it, or short of that to let it settle back.
  Clicking the handle closes the sheet, which is the single-pointer alternative
  M3 requires: *"selecting the drag handle should toggle through preset heights
  or close the sheet"*. Preset heights are not implemented.

A sheet without `handle: true` cannot be dragged. Drawing the affordance is
what promises the gesture.

## Disabled controls

`disabled:` marks a control inert. It is templated like `value:`, so it tracks
a signal:

```yaml
- name: save
  widget: Button
  text: Save
  disabled: "{{ not form_valid.get() }}"
  handlers: {on_click: save}
```

A disabled control ignores the pointer, never shows hover or press, and is
skipped by Tab — leaving it keyboard-reachable when the mouse cannot touch it
is the accessibility failure the state exists to avoid. **Disabling a container
disables everything inside it**, which is how you grey out a whole form section.

It repaints per M3: the container becomes `on_surface` at 12% and the content
`on_surface` at 38%. Note that M3 *replaces* the colours rather than dimming the
control's own, so a disabled filled button and a disabled outlined one look
alike — that is intended.

## Widgets

Dimensions are Material Design 3's own dp figures. pySilver's logical units map
to dp 1:1, so an M3 `40dp` control is `height: 40`.

### Layout primitives

| Widget | Notes |
|---|---|
| `Container` | A styled box with padding and at most one child. |
| `Horizontal` / `Vertical` | Lay children along an axis. `spacing`, `main_alignment`, `cross_alignment`. |
| `Stack` | Overlays children; positioned with `align_x` / `align_y`. |
| `Spacer` | Empty space. `width: expand` pushes siblings apart. |
| `ScrollView` | A clipped viewport. **Must** have a bounded size on its scroll axis. |
| `TextField` | The editable one. 56dp, `filled` or `outlined`. See [Text fields](#text-fields). |
| `SearchBar` | M3's search bar: a 56dp pill, 360–720dp wide, a fixed leading search icon. `value:` is the typed query, `supporting_text:` a placeholder shown while empty, `icon:` an optional trailing icon. See [Search bar](#search-bar). |
| `CodeEditor` | Multi-line, line-numbered, optionally syntax-highlighted. No M3 component. See [Code editor](#code-editor). |
| `Terminal` | A real shell, spawned and parsed internally. No M3 component. See [Terminal](#terminal). |

Inside a `Horizontal` or `Vertical`, a child with `width: expand` (or `flex`) on the main
axis shares the free space; anything else is measured first and takes what it
needs. A `Text` shrink-wraps to its ink, so it will not starve its siblings.

### Content

| Widget | Notes |
|---|---|
| `Text` | Shaped, kerned, wrapped. `font_size` in dp. |
| `Icon` | Material Symbols. Name goes in `icon:`; `icon_size`, `icon_fill`, `icon_weight`. |
| `Divider` | 1dp `outline_variant`. `full_bleed` / `inset`. |
| `Shape` | A regular polygon: `sides`, `rotation`, `corner_radius`, `background`, `border`. 48dp unless sized. Drawn as a distance field, not a rasterised path, so every one of those is **free to animate** — `spin:`/`morph:` opt into a continuous rotation and sides oscillation using exactly that. |
| `Image` | A decoded raster image. `path:` names the file; `style: {fit}` controls how it fills a differently-shaped box. No M3 component — see [Image](#image) below. |
| `Video` | A live-updating video surface — the application decodes and pushes frames. No M3 component — see [Video](#video) below. |

### Buttons and controls

| Widget | M3 spec |
|---|---|
| `Button` | 40dp high, full radius, sized to its label with a 64dp floor. `filled`, `filled_tonal`, `outlined`, `elevated`, `text`. Shape-morphs on press (12dp corner, every button) and when toggled `checked` via a `value:` binding (16dp corner, resting) — the same `value:`/`on_click:` convention `Chip`'s filter variant and `Accordion` use; an un-`checked`, unpressed button is unaffected. |
| `ButtonGroup` | An invisible container spacing `Button` children: `standard` (default, 8dp gaps at `Button`'s legacy/medium/large/extra_large sizes, each button stays fully rounded unless selected/pressed) or `connected` (2dp gaps at every size, only the group's two outer ends stay fully rounded, every touching corner squares to a size-appropriate figure — a connected button still morphs its own shape when selected, independent of its neighbours). A `standard` group's selected/pressed button also grows width, shifting later siblings along the row. The group has no `size:` of its own — it reads its `Button` children's shared `style.size` (see that property's own row). |
| `IconButton` | 40dp container, 24dp icon. `standard`, `filled`, `filled_tonal`, `outlined`. Icon name in `icon:`, accessible name in `label:`. |
| `Fab` | 56dp standard, 40 small, 80 medium, 96 large, plus `extended` — same 56dp height, a dynamic width (80dp floor) fitting an icon (`icon:`) and a `label:` label side by side. |
| `Checkbox` | 18dp box, 2dp radius. `indeterminate:` shows a dash instead of a checkmark, M3's third state for a partly-checked group. |
| `Radio` | 20dp outer, 10dp dot. |
| `Switch` | 52×32dp track. |
| `Chip` | 32dp high. `assist`, `filter`, `input`, `suggestion`. |
| `Badge` | 6dp dot, or a 16dp pill carrying `value:`. |
| `Link` | Hyperlinked text: always underlined, `primary` (default) or `tertiary`. Sized with `font_size` like `Text`, not a fixed label role — it's meant to sit inline with body text. No container, no state layer. |
| `SpinBox` | A number with `remove`/`add` icon buttons either side (40dp, `IconButton`'s own anatomy). `value:` is the current number; `style: {min, max, step}` bound it (either end `None`/omitted means unbounded). Arrow keys step it too. Named to avoid M3's own "Stepper" (a multi-step flow indicator, a different widget) — not a component M3 has a page for either way. |
| `Slider` | Standard variant, every named M3 size via `style.size` (`extra_small` default, `small`, `medium`, `large`, `extra_large`): track height 16/24/40/56/96dp, handle height 44/44/52/68/108dp, track corner radius 8/8/12/16/28dp — handle width stays a constant 4dp at every size. `value:` is the current number; `style: {min, max, step}` bound it (unlike `SpinBox`, an unset `min`/`max` falls back to 0.0/1.0, not "unbounded" — a slider needs a real range to draw a track). Click or drag anywhere on the track to jump the handle there and keep dragging; Left/Right/Up/Down step by `style.step`; Home/End jump to the bounds. Fires `on_change` the same way `SpinBox` does. |
| `Pagination` | Prev/next arrows around page-number buttons (40dp). `value:` is the current page (1-indexed); `style: {count}` is the total. Below 8 pages every number shows; above that, only the first, last, and the current page's neighbours do, with the rest collapsed into `...`. Left/Right arrow keys step it. No M3 component — the word "pagination" appears exactly once in the whole reference library, as a prohibition on Cards. |
| `SplitButton` | A primary action (`text:`, 40dp) with an attached 40dp chevron trigger, 2dp apart, only the pair's outer corners fully rounded. `handlers: {on_leading_click, on_trailing_click}` — two independent handlers, deliberately not `on_click:`, since a widget's own native `on_click` method and a view's `on_click:` handler both fire for the same click (`EventDispatcher._invoke`); the trigger typically opens a `Menu` overlay anchored to this widget's `name`. |
| `DatePicker` | Modal variant, single date only. A 320dp calendar month grid; `value:` is the selected date as `YYYY-MM-DD`. Clicking a day commits immediately and fires `on_change` — no separate OK/Cancel step. A plain widget, not an overlay: place it as a `Dialog`'s child for the modal presentation M3 describes. |
| `TimePicker` | Input variant only (Dial is a deferred, separate lift). Two 96×72dp hour/minute steppers (click the top half to increment, the bottom half to decrement, both wrapping) plus a 52dp AM/PM toggle; `value:` is a 24-hour `HH:MM` string. Stepping, not typing — the same trade `SpinBox` makes, for the same reason. Commits immediately and fires `on_change`; a plain widget, placed as a `Dialog`'s child the same way `DatePicker` is. |

Selection is a **binding, not style**: `value: "{{ checked.get() }}"`.
A `SpinBox` or `Pagination` fires `on_change` with its new value already computed and clamped — the application does not do the arithmetic, only `qty.set(event.value)`.

### Structure

| Widget | M3 spec |
|---|---|
| `Card` | 12dp radius, 16dp padding. `elevated`, `filled`, `outlined`. |
| `ListItem` | 56 / 72 / 88dp by line count. |
| `Accordion` | 56 / 72dp header (M3 gives this no component of its own, only Lists' "expand and collapse" behaviour). `text:` headline + `supporting_text:`, an optional child body, `value:` for open/closed. |
| `TreeView` + `TreeItem` | Same M3 gap as `Accordion`, applied recursively. A `TreeItem` with `children:` is a branch (chevron, `value:` for open/closed); with none it's a leaf. `TreeView`'s own `value:` names the selected item by `name` at any depth. |
| `TopAppBar` | 64dp small, 112dp `medium`, 152dp `large`. |
| `StatusBar` | 24dp, `surface_container`. No M3 component or even the phrase "status bar" anywhere in M3's own vocabulary — the docked *toolbar* it might sound like is a row of action buttons, a different thing. A plain `Horizontal` a view populates freely; a `Spacer` splits it into leading/trailing groups. |
| `NavigationRail` + `NavItem` | One widget, two states, animated between them: collapsed (80dp, 56×32dp indicator, icon-only) and expanded (240–360dp, 56dp items, full-radius pill, with labels) — `collapsed: "{{ }}"` switches between them (default false, so an unset rail starts expanded). M3 Expressive's own merger of the old, separate NavigationDrawer into this widget's expanded state. |
| `Tabs` + `Tab` | 48dp, 3dp indicator. `primary`, `secondary`. A `Tab`'s optional `icon:` (24dp) grows the whole bar to 64dp — every tab in one bar shares the taller height, even an icon-less sibling. `style.icon_position`: `stacked` (default, above the label) or `leading`/`trailing` (opt-in, beside the label). A `Tab`'s optional `badge:` (with `style.badge_variant: numbered`/`dot`) overlaps a stacked icon's own top-right corner (6dp, no width change) or trails the label with a 4dp gap (widens the tab) when there's no stacked icon to overlap. |
| `SegmentedButton` + `Segment` | 40dp, 20dp outer corners. `style: {multi_select: true}` selects M3's multi-select form — `value:` becomes a comma-separated set instead of one name. |
| `DockSplit` + `DockGroup` + `DockPanel` | No M3 component at all. A resizable, tabbed panel layout arranged once in the view file — see [Dock layout](#dock-layout) below. |
| `Canvas` | No M3 component. A freeform drawing surface for an `on_paint` handler — see [Canvas](#canvas) below. |
| `NodeGraph` + `Node` | No M3 component. A pannable surface of draggable, wired nodes — see [Node graph](#node-graph) below. |
| `PageHost` | No M3 component. A single-active-child container, switched by name — see [Page host](#page-host) below. |

A selection container carries `value:` naming the selected child by `name`.

### Dock layout

Three widgets compose a resizable, tabbed panel layout the way an IDE's own
is arranged — but only the *static* half: the tree is declared once in the
view file, not dragged into shape at runtime.

```yaml
- name: workspace
  widget: DockSplit
  value: "0.25"                 # the left pane's share, 0..1
  handlers: {on_change: setSplit}
  children:
    - name: sidebar
      widget: DockGroup
      children:
        - {name: files, widget: DockPanel, text: Files, children: [...]}
    - name: main
      widget: DockGroup
      value: "{{ active_tab.get() }}"
      handlers: {on_change: setActiveTab}
      children:
        - {name: editor, widget: DockPanel, text: main.py, children: [...]}
        - {name: output, widget: DockPanel, text: Output, children: [...]}
```

| Widget | Role |
|---|---|
| `DockSplit` | Exactly two children, divided by a draggable divider. `style.axis` (shared with `ScrollView`) is `horizontal` (default, side by side) or `vertical` (stacked). `value:` is the first child's share, 0..1. Nest another `DockSplit` as a child for a third pane. |
| `DockGroup` | A tabbed stack of `DockPanel`s — exactly one visible at a time. `value:` names the active one by `name`; unset or unmatched falls back to the first. |
| `DockPanel` | One pane. `text:` is its tab label, its single child is its content. |

Both `DockSplit` and `DockGroup` fire `on_change` with the new value already
computed — dragging the divider or clicking a tab updates the widget's own
state and tells the application, the same as `SpinBox` and `Pagination`.

**Runtime drag-and-drop — dragging a tab onto an edge to split or rearrange
the tree while the app is running — is not implemented.** That is a
substantially larger feature (drop-zone detection, tree mutation, tab
reordering) than the static layout above, and is deliberately a separate,
later piece of work rather than a half-built version bundled in here.

### Image

`Image` decodes a raster file and draws it as one instance. No M3 component
exists for this either — images only ever appear as content *inside* other
components (Carousel, Cards), never with an anatomy of their own.

```yaml
- name: avatar
  widget: Image
  path: "{{ avatar_path.get() }}"
  style: {width: 48, height: 48, corner_radius: 24, fit: cover}
```

`path:` is templated like `value:`, so a signal can swap the picture at
runtime. It is **not** `source:` — that key already means "splice in a view
fragment from another file" (`spec/include.py` acts on it before Pydantic
ever sees the node), so a widget field reusing it would be silently
swallowed as an include rather than reaching `Image` at all. `path:` is
resolved exactly the way a running process resolves any other filesystem
path: absolute as given, relative to the working directory otherwise — **not**
relative to the view file the way a `source:` include is confined. An
application wanting a view-relative path resolves it itself, e.g. from
`Path(__file__).parent`.

With no `width`/`height`, `Image` reports the decoded picture's own pixel
size as its logical size (one image pixel, one logical pixel) — it has real
intrinsic content, unlike `Canvas`. An axis the view does size always wins.

`style: {fit}` controls how the picture fills a box whose aspect ratio
differs from its own, the same vocabulary CSS's `object-fit` uses since M3
states none:

| `fit` | Behaviour |
|---|---|
| `contain` (default) | Scales to fit entirely inside the box, preserving aspect ratio. Never crops, may letterbox. |
| `cover` | Scales to fill the box entirely, preserving aspect ratio. Never letterboxes, crops the overflow. |
| `fill` | Stretches to the box exactly. Distorts if the ratios differ. |
| `none` | Draws at its own natural size, centred in the box, regardless of the box's size. |

`corner_radius` rounds the picture's own visible corners, not just a
container around it. **There is no `color:` tint** — `Kind.IMAGE` has no
palette-token slot in the shader, the way `Shape`/`Icon`/text glyphs do, so
baking a literal tint would silently stop re-theming on a live palette
swap. An application wanting a tinted picture composites it before decoding.

A missing file or a decode failure is logged to stderr and treated as
"nothing to draw" rather than raised, so one bad asset reference does not
crash the whole frame.

### Video

`Video` is a live-updating display surface — the application decodes,
`Video` displays. No M3 component exists, and pySilver does not decode
video itself: nothing in the project depends on a codec library (Pillow
decodes still images; nothing decodes `.mp4`/`.webm`), and adding one —
realistically PyAV, which wraps FFmpeg — would mean taking on its install
size and licensing considerations for every application, not just the ones
that show video.

```yaml
- name: player
  widget: Video
  style: {width: 640, height: 360, fit: contain}
```

```python
import numpy as np


def on_new_frame(rgba: np.ndarray) -> None:
    app.root.find("player").push_frame(rgba)
```

`push_frame(rgba)` takes an `(h, w, 4)` uint8, straight-alpha array — the
same convention `Image` decodes into — and displays it in place of whatever
was showing before. There is no `path:`, no decoding, no codec awareness at
all: the application feeds frames from wherever it likes (PyAV, OpenCV, a
camera driver, a procedurally generated stream), and this widget only owns
showing the latest one. It sizes and fits exactly like `Image` — an unsized
axis reports the current frame's own pixel dimensions, `style: {fit}` takes
the same `contain`/`cover`/`fill`/`none` vocabulary, `corner_radius` rounds
the frame's own visible corners, and there is no `color:` tint for the same
reason `Image` has none.

**There is no play/pause, no scrub bar, no `value:` for position.** The
application already owns the decode loop — it is the thing deciding when a
new frame exists — so it is also the natural owner of transport controls,
composed from ordinary widgets (an `IconButton` for play/pause, a
`LinearProgress` or a `Canvas`-drawn bar for position) around a `Video` the
same way a page composes around anything else.

**`push_frame` is not thread-safe**, by the same rule every mutation in this
framework follows: it must run on the engine thread. A decoder on its own
thread hands a frame back with
`loop.call_soon_threadsafe(element.push_frame, rgba)`, the identical pattern
`Signal.set` already requires from a background thread.

### Canvas

`Canvas` is a freeform drawing surface for content a view file can't express
as data — a live chart, a custom gauge, anything whose shape depends on state
that changes at runtime. No M3 component exists for it either.

```yaml
- name: chart
  widget: Canvas
  style: {width: expand, height: 200}
  handlers: {on_paint: drawChart}
```

```python
def drawChart(canvas):
    for i, value in enumerate(readings):
        x = i * (canvas.size.width / len(readings))
        canvas.line(x, canvas.size.height, x, canvas.size.height - value, color="primary")
    canvas.text(4, 4, f"{readings[-1]:.1f}", color="on_surface_variant")
```

The handler is an ordinary Python function, registered with `@app.handler`
like any other, and named under `handlers:` the same way — `on_paint` rather
than a bare `painter:` key, since every handler name is required to start
with `on_`. It receives one argument, a drawing context, with these methods:

| Method | Draws |
|---|---|
| `line(x1, y1, x2, y2, thickness=1, color=...)` | A capsule — a stroked line with round caps. |
| `rect(x, y, w, h, color=..., corner_radius=0, border_width=0, border_color=None)` | A filled, optionally rounded and bordered rectangle. |
| `circle(cx, cy, radius, color=...)` | A filled circle. |
| `arc(cx, cy, radius, thickness=, start=, sweep=, color=...)` | A stroked ring segment — radians, clockwise from 12 o'clock, same as `CircularProgress`. |
| `polygon(x, y, w, h, sides=, rotation=0, corner_radius=0, color=...)` | A regular polygon, same shape `Shape` draws. |
| `text(x, y, text, font_size=14, color=..., alignment="start")` | Shaped text. |
| `measure_text(text, font_size=14) -> Size` | For positioning text before drawing it. |

`color` on every method takes a palette token name (`"primary"`, themed like
everything else) or a literal `(r, g, b, a)` tuple for data-driven colour that
has no semantic role to name. A literal tuple is the ordinary sRGB value it
looks like — `(0.2, 0.2, 0.2, 1.0)` for a dark grey, the same numbers a
colour picker would show — pySilver converts it to the linear RGBA the GPU
target actually wants; a handler never has to do that conversion itself. All
coordinates are logical px relative to the canvas's own top-left;
`canvas.size` is its current laid-out size. Drawing outside that size is
clipped.

**The application drives its own repaints.** The handler is an opaque Python
closure, so the framework only calls it again when this element itself
repaints — the same as every widget's own `paint_self`. If a chart's data
changes outside the normal binding path, tell it directly:

```python
app.root.find("chart").mark_needs_paint()
```

`image()` is deliberately not offered yet — that waits for the `Image`
widget itself, so the convention for loading and caching a source is
designed once rather than invented twice.

### Node graph

`NodeGraph` is a pannable surface of draggable `Node`s wired by declared
edges — a real interactive editor, not a thin surface an application draws
into itself the way `Canvas` is. No M3 component exists for either widget.

```yaml
- name: graph
  widget: NodeGraph
  style: {width: expand, height: expand}
  edges:
    - {source: source.out, target: sink.in}
  children:
    - name: source
      widget: Node
      text: Source
      outputs: out
      style: {x: 40, y: 40}
      children: [ ... ]
    - name: sink
      widget: Node
      text: Sink
      inputs: in
      style: {x: 280, y: 120}
      handlers: {on_change: onNodeMoved}
      children: [ ... ]
```

`style.x` / `y` is a `Node`'s **initial** world position only — dragging its
title bar moves it from there, tracked as runtime state the same way a
`ScrollView`'s scroll offset is, and a reload does not reset a node the user
has already moved. `inputs` / `outputs` name a node's ports (a string or a
list, parsed like `classes`), drawn evenly spaced down its left/right edge.
`edges` on the `NodeGraph` itself declares the wires between them, each
`source`/`target` a `"node.port"` pair — `source` and `target` rather than
`from`/`to` because `from` is a Python keyword.

Dragging a node's title bar moves it live and fires `on_change` with its new
`"x,y"` position once the drag ends; the arrow keys nudge a focused node the
same way and fire immediately, there being no separate release event for a
key press. Dragging anywhere else on the surface — wherever no `Node` covers
it — pans the whole graph, exactly like scrolling a `ScrollView`: a
paint-time translation, not a relayout.

**There is no zoom.** Scaling would either distort glyph rasterisation (the
same per-frame-key trap `Icon`'s `icon_fill` axis quantisation exists to
avoid) or require re-shaping text at a new pixel size on every step, and
would also need every hit rect scaled to match — a real second feature, not
a checkbox on this one. Panning and dragging are useful and correct without
it.

### Collapsing app bars

A `medium` or `large` app bar shrinks into a small one as its page scrolls,
which M3 describes as transforming "into small app bars... until the page is
scrolled back to the top". Name the scrolling view:

```yaml
- name: bar
  widget: TopAppBar
  text: Inbox
  style: {variant: large, collapses_with: body, width: expand}
- name: body
  widget: ScrollView
  style: {height: expand, width: expand}
  children: [ ... ]
```

The height is a direct function of the scroll offset — there is no animation
clock involved, so it tracks a drag exactly. The container also fills with
`surface_container` as it collapses, which is M3's own way of separating the
bar from the content beneath.

Without `collapses_with:` a medium or large bar simply stays expanded.

### Progress

| Widget | M3 spec |
|---|---|
| `LinearProgress` | 4dp, rounded ends. |
| `CircularProgress` | 4dp ring, clockwise from 12 o'clock. |

Supplying `value:` (the fraction, 0 to 1) gives the determinate form.
**Omitting `value:` entirely** gives the indeterminate form, which animates
continuously — a bar that grows, travels and shrinks, or a rotating arc. An
indicator bound to a signal that starts empty therefore changes from
indeterminate to determinate on its own as information arrives, which is what
M3 asks for.

### Carousel

| Widget | Notes |
|---|---|
| `Carousel` | `uncontained` (items keep their width, free scroll), `hero` (large + small), `multi_browse` (large + medium + small). |
| `CarouselItem` | 28dp radius. Sized by the strip, not by itself. Its children parallax as the strip moves; its `text:` label sits over them. |

`hero` and `multi_browse` resize their items and snap by item; `uncontained`
scrolls by pixels.

### Overlay components

| Widget | M3 spec |
|---|---|
| `Dialog` | 28dp radius, 24dp padding, 280–560dp, height dynamic. Optional `icon:` (24dp, `secondary` token) centers itself and the headline as a column above the (always start-aligned) supporting text — matching M3's own "center-aligned with icon, start-aligned without" rule. |
| `Popover` | M3's persistent rich tooltip. `text:` (subhead) + `supporting_text:` + an optional child action row. 12dp radius, max 320dp, **shrink-to-fit width** (unlike `Dialog`/`Menu`, no minimum). Defaults to `placement: anchor`. |
| `Menu` + `MenuItem` | 4dp radius, 112–280dp / 48dp rows. A `MenuItem`'s optional `icon:` (24dp, `on_surface_variant`) sits leading the label; independent of the trailing shortcut/chevron slot. |
| `Tooltip` | 24dp high, `inverse_surface`. |
| `Snackbar` | 48dp growing to 64dp; `supporting_text` is the action label. `style.auto_dismiss` (seconds, opt-in) auto-dismisses it when there's no action; ignored when there is one. |
| `BottomSheet` | 28dp top corners, max 640dp, optional `handle`. |
| `SideSheet` | 16dp leading corners, max 400dp. |

---

## Style properties

### Size and space

| Property | Values |
|---|---|
| `width`, `height` | a number (dp), `expand`, or a percentage like `50%` |
| `padding`, `margin` | one number, or `[left, top, right, bottom]` |
| `spacing` | gap between children of a `Horizontal`/`Vertical` |

### Colour and shape

| Property | Values |
|---|---|
| `background` | an MD3 token name, e.g. `surface_container` |
| `color` | content colour; defaults to the widget's own M3 role |
| `corner_radius` | one number, or `[tl, tr, br, bl]` |
| `border` | `{width, color}` |
| `shadow` | `{blur, offset_x, offset_y, color, opacity}` — hand-tuned; prefer `elevation` |
| `elevation` | M3 level 0–5. Omit to use the component's own resting level |
| `multiline` | a `TextField` takes more than one line — see [Text fields](#text-fields) |
| `selectable` | `Text` only — can its content be selected with the mouse |
| `cursor` | pointer shape: `default`, `pointer`, `text`, `crosshair`, `ns-resize`, `ew-resize`, `nesw-resize`, `nwse-resize`, `not-allowed`, `none` |
| `opacity` | 0–1 |

Colours are **token names, not hex** — that is what makes a theme switch a
single buffer upload. There are 59 tokens; `pysilver.is_token()` checks one and
`TOKEN_ORDER` lists them all. An unknown token fails at load with a path.

### Alignment

| Property | Values |
|---|---|
| `main_alignment` | `start`, `end`, `center`, `space_between`, `space_around`, `space_evenly` |
| `cross_alignment` | `start`, `end`, `center`, `stretch` |
| `align_x`, `align_y` | 0–1, for `Stack` children |

### Text and icons

| Property | Values |
|---|---|
| `font_size` | dp |
| `text_style` | an M3 type-scale role, resolved against `type_scale:` |
| `font_weight` | 400 or 500 (Roboto ships both); resolves to the nearest available |
| `letter_spacing` | tracking in logical px, added after each grapheme cluster |
| `line_height` | a fixed line height in logical px; unset keeps the font's own |
| `hit_padding` | extra clickable area around the paint rect; same form as `padding` |
| `min_hit_size` | smallest clickable square, in logical px, centred on the paint rect |
| `icon_size` | dp, default 24 |
| `icon_fill` | 0–1. M3 uses this for selected state — prefer it to swapping icon names. |
| `icon_weight` | 100–700 |
| `icon_position` | `Tab` — `stacked` (default, icon above the label) or `leading`/`trailing` (icon beside the label, opt-in) |
| `badge_variant` | `Tab` — `numbered` (default, shows `badge:`'s content) or `dot` (a bare notification dot; ignores `badge:`'s own content) |
| `sides` | `Shape` — 3 or more. A **float**: 5.5 is a real shape, so a square morphs continuously into a hexagon. |
| `rotation` | `Shape` — degrees, clockwise |
| `spin` | `Shape` — when true, spins continuously on top of `rotation:`'s own value. Free, like every other Shape parameter. |
| `morph` | `Shape` — when true, `sides` oscillates continuously between its own value and a wider polygon, through the same smooth non-regular intermediates a fractional `sides:` gives. |

### Component-specific

| Property | Applies to |
|---|---|
| `variant` | most components; the valid names are per widget |
| `thickness` | `Divider`, `CircularProgress` |
| `inset` | `Divider` |
| `axis` | `ScrollView` — `vertical` (default) or `horizontal` |
| `scrollbar` | `ScrollView` — show the indicator when content overflows |
| `handle` | `BottomSheet` — draw the drag handle |
| `collapses_with` | `TopAppBar` — `name:` of the `ScrollView` it collapses with |
| `multi_select` | `SegmentedButton` — M3's multi-select form (default off, single-select). On, `value:` is a comma-separated set of selected names instead of one |
| `min`, `max`, `step` | `SpinBox`/`Slider` — bounds and increment; `min`/`max` default to unbounded for `SpinBox`, 0.0/1.0 for `Slider` |
| `handle_shape` | `Slider` — `line` (default, current M3: a narrow vertical bar), `circle` (an opt-in back to M2's round handle), or pySilver's own `square`/`hexagon` (a regular polygon, same primitive `Shape` uses) |
| `handle_image` | `Slider` — a path to a raster image (PNG/JPG/etc, same resolution convention as `Image`'s own `path:`) drawn as the handle instead of any `handle_shape`; wins over it when set. No SVG support |
| `cradle_gap` | `Slider` — gap between the handle and each track segment, logical px (default 6) |
| `cradle_radius` | `Slider` — corner radius on each track segment's handle-facing end, more square than `track_radius` (default 2) |
| `track_radius` | `Slider` — corner radius on each track segment's outer end; defaults to the size-appropriate value below unless set explicitly (default 8, `extra_small`'s figure) |
| `size` | `Slider` — one of `extra_small` (default), `small`, `medium`, `large`, `extra_large`, `COMPONENT_SLIDERS.md`'s own named size scale; sets track height, handle height, and `track_radius`'s own default together. `Button` reads the same field and Literal — bare default (unset) keeps the widget's pre-ladder legacy shape unchanged (not any one of the five, since it never matched a real row); an explicit value opts into `COMPONENT_BUTTONS.md`'s own size table (height, horizontal padding, checked/pressed corner radii). `ButtonGroup` has no `size:` of its own and derives its spacing/connected-inner-radius from its `Button` children's shared value instead |
| `count` | `Pagination` — total number of pages |
| `auto_dismiss` | `Snackbar` — seconds after which an actionless snackbar dismisses itself; `None` (default) never auto-dismisses. Ignored outright whenever `supporting_text:` (its action) is set, per M3: actionable snackbars shouldn't auto-dismiss |
| `fit` | `Image` — `contain` (default), `cover`, `fill`, or `none` |
| `x`, `y` | `Node` — initial world position in its `NodeGraph`; see [Node graph](#node-graph) |
| `language` | `CodeEditor` — a Pygments lexer name/alias; unset or unrecognised means no highlighting |
| `line_numbers` | `CodeEditor` — show the gutter (default on) |
| `tab_size` | `CodeEditor` — spaces the Tab key inserts (default 4) |
| `read_only` | `CodeEditor` — blocks typing and every mutating key (Tab, Enter, Backspace, Delete, paste, undo/redo); caret motion, selection, Ctrl+A, and copy still work |
| `font_family` | `CodeEditor`, `Terminal` — request a face by name; see [Code editor](#code-editor) |
| `shell` | `Terminal` — the command line to run; unset resolves `$SHELL`, else `/bin/sh` |
| `placement`, `anchor`, `modal`, `scrim`, `dismissable`, `offset` | overlays |

---

## What does not exist yet

Stated plainly so you can design around it:

- **Motion.** Animated: overlay fades, state layers, every selection control,
  tab and navigation indicators, indeterminate progress, a carousel's snap and
  content parallax, and app-bar collapse. Set `reduce_motion` in `Settings` to
  make timed transitions arrive at once — it does not affect app-bar collapse
  or carousel parallax, which follow a position rather than a clock.
- **IME preedit.** Committed characters only, so an input method that composes
  before committing — CJK, in practice — is not supported.
- **Reading the clipboard without focus.** Copy and paste use the system
  clipboard, but Wayland only lets a client read the selection while it has
  keyboard focus, and only accept a *new* selection when a real input event is
  behind it. Both hold whenever a user presses Ctrl+C or Ctrl+V; neither holds
  for a program driving the clipboard on its own. A read that comes back empty
  falls back to whatever this process last copied.
- **The 48dp minimum touch target by default.** A pointer is pixel-precise, so
  a control is hit-tested at the size it is drawn. `min_hit_size:` asks for
  more where an application wants it — see [Hit targets](#hit-targets).
