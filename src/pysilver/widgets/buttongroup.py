"""M3 Button Group: an invisible container that spaces buttons and, for the
connected variant, merges their outer shape into one pill.

**`COMPONENT_BUTTON_GROUPS.md`'s own words**: "Button groups are invisible
containers that add padding between buttons and modify button shape." A
`Flex` row with M3's spacing and, for `variant: connected`, per-child
corner overrides -- plus, now, the width/shape *morph* on press and
selection M3's own demo videos show. The morph itself (round<->square,
sourced dp figures) lives entirely on `ButtonElement` (`base.py`) -- it
applies to any toggle button, grouped or not. This module's own
contribution is narrower and specific to the "Selection & activation"
section of `COMPONENT_BUTTON_GROUPS.md`: a **standard** group's selected
button also grows WIDTH (unsourced amount -- the spec gives none, only
that it happens; see `ButtonElement.GROUP_SELECT_PAD_EXTRA`), which
visibly shifts every later sibling along the row as an ordinary
consequence of this already being a plain `Flex` row -- nothing new was
needed for that. A **connected** group's own selection changes shape only,
per the spec's own "don't add any interaction between buttons... only
affect the shape."

**The size ladder, shipped.** `ButtonElement` grew a real `style.size` axis
(`extra_small` through `extra_large`, see its own docstring for the sourced
table and why its bare default is a separate "legacy" shape rather than any
one of the five). This group reads that size from its own `Button` children
rather than carrying a redundant `size:` of its own -- M3's own guidance is
explicit that a group's buttons share one size ("By default, all buttons in
a standard group should be the same size... Avoid mixing sizes frequently"),
so a second field on the group that could silently disagree with its
children would only invite exactly the drift that guidance warns against.
`perform_layout` reads the first `Button` child that actually set `size:`
(via `model_fields_set`, the same check `ButtonElement._geometry` uses);
`None` (no child opted in) keeps every number below at its own pre-ladder
value, unchanged.

**Spacing**: `COMPONENT_BUTTON_GROUPS.md`'s own "between-space" table gives
one row per size -- XS 18dp, S 12dp, M/L/XL 8dp, confirmed against the same
page's own scraped token residue for the XS row (32dp container height,
18dp between-space, both matching exactly). `STANDARD_SPACING` (8.0) is
both the M/L/XL figure *and* this group's own pre-ladder legacy value, so
leaving `size:` unset changes nothing either way. Connected groups use a
flat 2dp at every size regardless, quoted directly ("For all connected
button groups, use 2dp padding... This provides visual consistency at
scale") -- no ladder needed there at all.

**Connected shape**: "the outer shape is fully round, and the inner shape
remains square with the following corner sizes" -- XS 4dp, S 8dp, M 8dp,
L 16dp, XL 20dp, the whole group's outward-facing ends staying fully
rounded while every corner where two buttons meet squares off to the
size-appropriate figure. `INNER_RADIUS` (8.0) is both the M figure and this
group's own pre-ladder legacy value, so -- like spacing -- an unsized group
is unaffected by the ladder's existence. Applied only to plain `Button`
children: M3 says a group "can contain buttons and icon buttons", but
`IconButtonElement.effective_radii` is hardcoded to full-round and does not
consult an override the way `ButtonElement`'s now does -- extending it is a
small follow-up, not done here.
"""

from __future__ import annotations

from typing import Final

from ..layout import Axis, Constraints, Flex, Size
from ..spec import WidgetSpec
from .base import ButtonElement, _StyledMixin

__all__ = ["ButtonGroupElement"]


class ButtonGroupElement(_StyledMixin, Flex):
    """M3 Button Group, every named Button size. See the module docstring."""

    #: Also this class's own LEGACY value (no `Button` child sets `size:`) --
    #: identical to the real ladder's own `"medium"`/`"large"`/`"extra_large"`
    #: row, so an unsized group is unaffected either way.
    STANDARD_SPACING: Final = 8.0
    CONNECTED_SPACING: Final = 2.0
    #: Also this class's own LEGACY value, same reasoning as above -- equals
    #: the real ladder's own `"medium"` row exactly.
    INNER_RADIUS: Final = 8.0

    #: `COMPONENT_BUTTON_GROUPS.md`'s own "between-space" table, standard
    #: groups: XS 18dp, S 12dp, M/L/XL 8dp (`STANDARD_SPACING` above).
    #: Confirmed against the same page's own scraped token residue for the
    #: XS row (32dp container height, 18dp between-space -- both agree).
    STANDARD_SPACING_BY_SIZE: Final = {
        "extra_small": 18.0,
        "small": 12.0,
        "medium": STANDARD_SPACING,
        "large": STANDARD_SPACING,
        "extra_large": STANDARD_SPACING,
    }
    #: `COMPONENT_BUTTON_GROUPS.md`'s own connected inner-corner table: XS
    #: 4dp, S 8dp, M 8dp, L 16dp, XL 20dp -- identical for round and square
    #: connected groups (the source gives the same five numbers twice, once
    #: per shape).
    INNER_RADIUS_BY_SIZE: Final = {
        "extra_small": 4.0,
        "small": 8.0,
        "medium": INNER_RADIUS,
        "large": 16.0,
        "extra_large": 20.0,
    }

    axis: Axis = Axis.HORIZONTAL

    def __init__(self, spec: WidgetSpec) -> None:
        Flex.__init__(self, axis=self.axis, spacing=self._spacing_for(spec.style.variant, None))
        self.init_element(spec)

    def _spacing_for(self, variant: str, size: str | None) -> float:
        if variant == "connected":
            return self.CONNECTED_SPACING
        return (
            self.STANDARD_SPACING_BY_SIZE.get(size, self.STANDARD_SPACING)
            if size
            else self.STANDARD_SPACING
        )

    def _inner_radius_for(self, size: str | None) -> float:
        return self.INNER_RADIUS_BY_SIZE.get(size, self.INNER_RADIUS) if size else self.INNER_RADIUS

    def configure(self) -> None:
        self._spacing = self._spacing_for(self.style.variant, None)

    def _apply_shape(self, size: str | None) -> None:
        buttons = [c for c in self.children if isinstance(c, ButtonElement)]
        if self.style.variant != "connected":
            for child in buttons:
                child._group_radii = None
            return
        inner = self._inner_radius_for(size)
        last = len(buttons) - 1
        for i, child in enumerate(buttons):
            outer = child.size.height / 2
            leading = outer if i == 0 else inner
            trailing = outer if i == last else inner
            child._group_radii = (leading, trailing, trailing, leading)

    def perform_layout(self, constraints: Constraints) -> Size:
        # Unlike `_apply_shape()` below (paint-only, needs each child's
        # already-computed `size.height`, so it runs after), the flags set
        # here need to happen BEFORE `super().perform_layout()` -- each
        # Button child's own `perform_layout` (called from inside that same
        # `super()` call) reads `_group_standard` to compute its own WIDTH,
        # and `self._spacing` is what `Flex.perform_layout` itself places
        # children by. The size a group's buttons share only exists once
        # those children are attached, which `__init__`/`configure()` are
        # too early for -- this is the first point in the lifecycle both
        # the real children and a not-yet-relaid-out spacing value can meet.
        standard = self.style.variant != "connected"
        size = None
        for child in self.children:
            if isinstance(child, ButtonElement):
                child._group_standard = standard
                if size is None and "size" in child.style.model_fields_set:
                    size = child.style.size
        self._spacing = self._spacing_for(self.style.variant, size)
        result = super().perform_layout(constraints)
        self._apply_shape(size)
        return result
