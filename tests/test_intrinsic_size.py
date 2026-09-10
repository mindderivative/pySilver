"""What a widget is the size of when nothing tells it.

Every other suite gives its widgets an explicit `width:`/`height:` or a
stylesheet class, so until this existed nothing exercised the intrinsic path at
all. `ButtonElement` laid out 0x0 for as long as that was true -- it returned
the constrained outer box and never consulted its own label -- and the whole
suite stayed green, because a button that draws nothing still draws nothing
correctly. One test worked around it by adding a size rather than reporting it.

So the rule here is deliberately blunt: a widget with no style laid out under
loose constraints must come back with a real size. The exceptions are listed
individually, because "it is allowed to be zero" is a claim that should have to
be written down.
"""

from __future__ import annotations

import pytest

from pysilver.layout import Constraints
from pysilver.spec import WidgetKind, parse_view
from pysilver.widgets import build_element

#: Room to be any reasonable intrinsic size, and no pressure to be a particular
#: one -- a tight box would measure the constraints rather than the widget.
LOOSE = Constraints(0.0, 400.0, 0.0, 300.0)

#: Kinds that are legitimately zero with nothing in them, and why. Making one
#: of these claim a size would put phantom space into every layout that used
#: it, so each is a decision rather than an oversight -- which is what having
#: to write the reason down is for.
EMPTY_IS_HONEST = {
    "Container": "a box around nothing",
    "Horizontal": "as wide as its children, and it has none",
    "ButtonGroup": "an invisible container hugging its buttons, and it has none",
    "Vertical": "as tall as its children, and it has none",
    "TreeView": "as wide as its items, and it has none",
    "Spacer": "space is all it is; with no flex or size there is none to take",
    "SegmentedButton": "as wide as its segments; it keeps its 40dp height",
    "BottomSheet": "as tall as its content, and its drag handle is opt-in",
    "Text": "no text is no ink -- it keeps a line's height and no width",
    "Link": "no label is nothing to underline either -- there is nothing to draw",
    "DockPanel": "a box around nothing, same as Container -- it has no content",
    "Image": "no path is no picture -- there is nothing to decode or to size",
    "Video": "no pushed frame is no picture either -- same reasoning as Image",
}


def laid_out(kind: str, **fields: object):
    spec = parse_view({"root": {"name": "w", "widget": kind, **fields}}).root
    element = build_element(spec)
    return element.layout(LOOSE)


@pytest.mark.parametrize("kind", [str(k) for k in WidgetKind])
def test_an_unsized_widget_has_an_intrinsic_size(kind: str) -> None:
    size = laid_out(kind)
    if kind in EMPTY_IS_HONEST:
        pytest.skip(f"{kind}: {EMPTY_IS_HONEST[kind]}")
    assert size.width > 0.0, f"{kind} laid out zero-width and would draw nothing"
    assert size.height > 0.0, f"{kind} laid out zero-height and would draw nothing"


def test_the_exemptions_are_still_earning_their_place() -> None:
    """The other half of the rule. If one of these grows an intrinsic size it
    should leave the list, and nothing else would notice."""
    for kind in sorted(EMPTY_IS_HONEST):
        size = laid_out(kind)
        assert size.width == 0.0 or size.height == 0.0, (
            f"{kind} now sizes itself ({size}) -- drop it from EMPTY_IS_HONEST"
        )


def test_a_label_is_what_makes_a_button_wide() -> None:
    """The specific regression. A Button ignored its label entirely and came
    back 0x0; the failure was invisible because nothing rendered."""
    wide = laid_out("Button", text="A considerably longer label")
    narrow = laid_out("Button", text="OK")
    assert narrow.width < wide.width
    assert narrow.width >= 64.0, "M3's minimum width still applies to a short label"


@pytest.mark.parametrize("kind", ["Chip", "Segment", "Tab", "Tooltip", "Link", "Badge"])
def test_the_other_label_bearing_widgets_measure_theirs_too(kind: str) -> None:
    """Checked because Button's bug looked like it should have been shared --
    these paint a label the same way and were the obvious suspects. All four
    were already correct, and this is what keeps that true rather than an
    assumption that happened to hold once."""
    assert laid_out(kind, text="Wide enough to matter").width > laid_out(kind, text="x").width


@pytest.mark.parametrize("kind", ["MenuItem", "ListItem", "Snackbar", "TopAppBar"])
def test_a_full_width_widget_is_not_sized_by_its_label(kind: str) -> None:
    """The deliberate opposite, so the rule above is not read as universal. A
    menu item as wide as its own text would leave a ragged menu; these take the
    width they are offered and their label only decides their height."""
    assert laid_out(kind, text="Wide enough to matter").width == LOOSE.max_width
