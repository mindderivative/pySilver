---
name: m3-lookup
description: Look up Material Design 3 (M3) guidance from the local M3-References/ library -- a named component's specs (dimensions, shape/corner radius, colour-role tokens, variants, states, behaviour), a cross-cutting style topic (colour system/roles/schemes, elevation, icons, motion/transitions, shape, spacing, typography), or a gap analysis of which M3 components pySilver has no widget for yet. Use whenever the user asks what Material Design says about a component or style topic, requests M3 specs, dimensions, or tokens, or asks what's missing from pySilver's widget catalogue -- even without the words "M3" or "Material Design", e.g. "what's the standard size for a checkbox", "how should a dialog be sized", "what are M3's spacing tokens", "how does dynamic colour work", "what easing curve for a transition", "which widgets are we missing".
---

# M3 Lookup

Finds and summarises the right Material Design 3 reference material: a named
component, a cross-cutting style topic, or a gap list against pySilver's widget
catalogue.

**Read-only.** This skill never edits code. It surfaces reference information
for `m3-widget-design` (or for a direct question) to act on.

There are two lookup paths. Component specs and style guidance live in
different files behind different routers, so pick the path that matches the
question rather than funnelling everything through the component index. One
question can need both -- "what colour should a filled button's container be"
is a component question that bottoms out in a style answer. When that happens,
use the component path to find the colour *role*, then the style path to find
what that role means.

## Before anything else

Check that `M3-References/` exists in the repo root. **It is deliberately not
tracked in git**, so it is absent from every fresh clone -- including this one,
most likely.

If it is missing, say so plainly and stop. Do **not** fall back on training
knowledge of Material Design: the whole point of the library is an
authoritative current source, and recalled M3 detail is reliably stale or
version-mixed (M2 vs M3 vs M3 Expressive). Answering from memory is the one
failure this skill exists to prevent.

**What the library is, and why it is not in the repo.** It is a local extract
of the published Material Design 3 guidance from `m3.material.io` -- roughly
2.2 MB of component and style pages. It is Google's material, not this
project's, so it is not redistributed here.

**Without it**, say that the reference library is unavailable and point at
`m3.material.io` directly. Everything already built has its sourced figures
quoted in `ARCHITECTURE.md` and in the widget docstrings, so an existing
widget's spec can be checked there -- and where a value was *not* in the source
it is explicitly marked as unsourced. That is the right fallback: cite what was
recorded at the time, never a recollection of the spec.

## Path 1: A specific component

1. **Read `M3-References/M3_COMPONENT_INDEX.md` first.** It is the router: every
   component grouped by category (Action, Communication, Containment,
   Navigation, Selection & Input) with its variants, purpose, and a link into
   `M3_COMPONENT_SPECS.md`. Component names there are canonical M3
   terminology, so use it to resolve casual phrasing -- "checkbox" ->
   "Checkboxes", "popup menu" -> "Menus", "toast" -> "Snackbars", "spinner" ->
   "Progress Indicators".
2. **Read the matched section of `M3_COMPONENT_SPECS.md`.** The condensed
   baseline, always present for anything in the index: anatomy dimensions in
   dp, corner radii, and `md.sys.color.*` token names. Also holds the global
   tables at `## 0`: the shape scale and the state-layer opacities. Read this
   before saying anything concrete about a component.
3. **Look for a deeper `COMPONENT_*.md`.** Filenames do **not** map 1:1 to
   index names. Buttons span `COMPONENT_BUTTONS.md`, `COMPONENT_ALL_BUTTONS.md`,
   `COMPONENT_BUTTON_GROUPS.md`, `COMPONENT_SPLIT_BUTTONS.md`,
   `COMPONENT_SEGMENTED_BUTTONS.md`, `COMPONENT_ICON_BUTTONS.md`; FABs span
   `COMPONENT_FABS.md`, `COMPONENT_EXTENDED_FABS.md`, `COMPONENT_FAB_MENU.md`;
   app bars span `COMPONENT_APP_BARS.md` and `COMPONENT_TOOLBARS.md`. Some
   files have no index entry at all (`COMPONENT_LOADING_INDICATOR.md`,
   `COMPONENT_CAROUSEL.md`). List `M3-References/COMPONENT_*.md` and match on
   content, not filename guessing.

These deep-dive files are scraped from m3.material.io and keep the site's
structure: Overview, M3 Expressive update, Differences from M2, Specs,
Variants, Tokens & specs, Anatomy, Color, States, Measurements, Guidelines,
Accessibility (including a keyboard-navigation table). They also contain image
placeholders and interactive-widget residue ("arrow_drop_down", "content_copy")
where the site had a live token table -- ignore that noise, and when a token
table is empty, fall back to `M3_COMPONENT_SPECS.md` for the value.

**Watch for M3 Expressive.** Several files document a May 2025 revision that
changed recommendations -- FABs gained a medium size and the small FAB is no
longer recommended; colour styles were renamed. Say which revision an answer
reflects when the file distinguishes them.

Report as:

- **Variants** -- the named sub-types (Filled / Outlined / Elevated / Text).
- **Anatomy & dimensions** -- sizes, corner radii, **in the source's own dp**.
  Report touch targets where a spec gives them, but flag them as
  **mobile-only**: pySilver is a desktop, pointer-only framework and
  deliberately does not implement M3's 48x48dp minimum (`ARCHITECTURE.md`
  §1.2.1). The same applies to touch ripple and the compact breakpoint.
- **Colour-role tokens** -- the `md.sys.color.*` role names the spec assigns,
  never invented hex values. M3 has no fixed hex; real values derive from a
  seed through HCT.
- **States and behaviour** -- state-layer opacities, gestures, motion notes.
- **Which file(s)** the answer came from, so it's clear whether it is the
  condensed spec or a full deep-dive.

Leave the dp figures as dp. Converting them is `m3-widget-design`'s job (in
this framework it is usually identity -- see that skill), and baking a
conversion into the reference answer hides the decision.

## Path 2: A style / cross-cutting topic

For colour, elevation, icons, motion, shape, spacing, or typography as
*systems* rather than as one component's properties.

1. **Read `M3-References/styles/M3-Styles-Index.md` first.** Its own router,
   grouped by topic, each row summarising a file and linking to it. Topics
   split finely -- Colour alone divides into system fundamentals, schemes
   (static baseline / static custom / dynamic), and advanced customisation, so
   "how does colour work" and "what's a dynamic source colour" land in
   different files. Match against the table rather than guessing a filename;
   the naming convention is `M3-Styles-<Topic>-<Subtopic>.md`.
2. **Read the matched file(s).** Each is a focused single-topic extract, so one
   file is usually the whole answer. Read several when the index shows an
   overview + applying + tokens split (Elevation, Spacing, and Typography all
   split this way).

Report as:

- **The system and its principle** -- tonal palettes from a seed colour, the
  spacing scale, physics-based motion versus legacy easing.
- **Tokens and values** -- named tokens or scale values in the source's units
  (`md.sys.color.*` roles, elevation levels 0-5, the 15-style type scale and
  its emphasised counterpart, corner-radius scale).
- **Application guidance**, including anything explicitly legacy or
  deprecated. Motion in particular documents an older easing/duration system
  alongside a newer physics-based one -- always say which you're describing.
- **Which file(s)** the answer came from.

## Path 3: What pySilver doesn't have yet

Cross-reference `M3_COMPONENT_INDEX.md` against pySilver's actual widget
registry. **Read it, don't recall it** -- it changes as widgets land:

- `src/pysilver/widgets/base.py` -> the `_REGISTRY` dict, keyed by `WidgetKind`.
- `src/pysilver/spec/models.py` -> the `WidgetKind` enum, which is the
  authoritative list of what a view file may name.

This is not a strict name match. Reason about real analogues even under
different names, and state each mapping explicitly rather than assuming it.
Some pySilver widgets are layout primitives with no M3 catalogue entry at all
(`Horizontal`, `Vertical`, `Stack`, `Spacer`, `Container`) -- that is expected; don't
force a mapping. Present two lists: covered (M3 component -> pySilver widget),
and not yet covered.

When the gap list is the input to actual work, hand off to `m3-widget-design`
rather than designing here.
