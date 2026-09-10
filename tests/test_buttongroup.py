"""Button Group: an invisible container that spaces buttons and, for the
connected variant, merges their outer shape into one pill.

See the module docstring in `buttongroup.py` for the shape morph/selection
split: the round<->square morph itself lives on `ButtonElement` (tested in
`test_material.py`), while this file covers what is genuinely
`ButtonGroup`-specific -- a standard group's selected button also growing
width, a connected group's own selection changing shape only, and the
group-level spacing/inner-radius ladder derived from its own `Button`
children's `style.size`.
"""

from __future__ import annotations

import pytest

from pysilver import App, Theme
from pysilver.layout import Offset
from pysilver.paint import DisplayList
from pysilver.spec import WidgetKind, parse_view
from pysilver.theme import Palette
from pysilver.tree.element import PaintContext
from pysilver.widgets.buttongroup import ButtonGroupElement
from pysilver.widgets.registry import _REGISTRY, create_element


def _app(variant: str, count: int = 3, size: str | None = None):
    button_style = {"size": size} if size else {}
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "bg",
                "widget": "ButtonGroup",
                "style": {"variant": variant},
                "children": [
                    {
                        "name": f"btn{i}",
                        "widget": "Button",
                        "text": f"Item {i}",
                        "style": button_style,
                    }
                    for i in range(count)
                ],
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    app.mount()
    app.update()
    group = app.root.find("bg")
    buttons = [app.root.find(f"btn{i}") for i in range(count)]
    return app, group, buttons


# --------------------------------------------------------------- registered


def test_kind_builds() -> None:
    create_element(parse_view({"name": "x", "widget": "ButtonGroup"}).root)
    assert WidgetKind.BUTTON_GROUP in _REGISTRY


# --------------------------------------------------------------------- spacing


def test_standard_variant_uses_the_m_size_between_space() -> None:
    _, group, _buttons = _app("standard")
    assert group._spacing == ButtonGroupElement.STANDARD_SPACING == 8.0


def test_connected_variant_uses_two_dp_at_every_size() -> None:
    _, group, _buttons = _app("connected")
    assert group._spacing == ButtonGroupElement.CONNECTED_SPACING == 2.0


def test_default_variant_is_standard_spacing() -> None:
    _, group, _buttons = _app("filled")  # not a button-group variant at all
    assert group._spacing == ButtonGroupElement.STANDARD_SPACING


# ----------------------------------------------------------------------- shape


def test_standard_variant_leaves_every_button_fully_rounded() -> None:
    _, _group, buttons = _app("standard")
    for button in buttons:
        assert button.effective_radii == (button.size.height / 2,) * 4


def test_connected_variant_rounds_only_the_two_outer_ends() -> None:
    _, _group, (first, middle, last) = _app("connected")
    outer = first.size.height / 2
    inner = ButtonGroupElement.INNER_RADIUS
    assert first.effective_radii == (outer, inner, inner, outer)
    assert middle.effective_radii == (inner, inner, inner, inner)
    assert last.effective_radii == (inner, outer, outer, inner)


def test_a_single_connected_button_is_rounded_on_both_outer_ends() -> None:
    _, _group, (only,) = _app("connected", count=1)
    outer = only.size.height / 2
    assert only.effective_radii == (outer, outer, outer, outer)


# ------------------------------------------------------------- size ladder


def test_an_unsized_groups_spacing_and_inner_radius_are_unchanged() -> None:
    """No `Button` child sets `size:` -- both figures must stay exactly
    what they were before the ladder existed (`STANDARD_SPACING`/
    `INNER_RADIUS`'s own bare values), the same zero-impact bar every
    other opt-in field in this codebase is held to."""
    _, standard_group, _ = _app("standard")
    assert standard_group._spacing == ButtonGroupElement.STANDARD_SPACING == 8.0

    _, _connected_group, (_first, middle, _last) = _app("connected")
    assert middle.effective_radii == (ButtonGroupElement.INNER_RADIUS,) * 4 == (8.0,) * 4


@pytest.mark.parametrize(
    ("size", "spacing"),
    [
        ("extra_small", 18.0),
        ("small", 12.0),
        ("medium", 8.0),
        ("large", 8.0),
        ("extra_large", 8.0),
    ],
)
def test_standard_spacing_follows_its_buttons_size(size: str, spacing: float) -> None:
    """`COMPONENT_BUTTON_GROUPS.md`'s own "between-space" table, every row."""
    _, group, _buttons = _app("standard", size=size)
    assert group._spacing == spacing


@pytest.mark.parametrize(
    ("size", "inner"),
    [
        ("extra_small", 4.0),
        ("small", 8.0),
        ("medium", 8.0),
        ("large", 16.0),
        ("extra_large", 20.0),
    ],
)
def test_connected_inner_radius_follows_its_buttons_size(size: str, inner: float) -> None:
    """`COMPONENT_BUTTON_GROUPS.md`'s own connected inner-corner table."""
    _, _group, (_first, middle, _last) = _app("connected", size=size)
    assert middle.effective_radii == (inner,) * 4


def test_connected_spacing_stays_flat_regardless_of_size() -> None:
    """ "For all connected button groups, use 2dp padding... at every size" --
    a real, explicit exception to the ladder, not an oversight."""
    for size in ("extra_small", "small", "medium", "large", "extra_large"):
        _, group, _buttons = _app("connected", size=size)
        assert group._spacing == ButtonGroupElement.CONNECTED_SPACING == 2.0


def test_group_size_reads_the_first_child_that_actually_set_size() -> None:
    """`ButtonGroup` has no `size:` of its own -- it derives the ladder row
    from its children, per M3's own "all buttons in a group should be the
    same size" guidance. An earlier, unsized sibling must not block a later
    one's explicit `size:` from being picked up -- "first sized child",
    not "first child, sized or not"."""
    view = {
        "name": "root",
        "widget": "ButtonGroup",
        "style": {"variant": "standard"},
        "children": [
            {"name": "a", "widget": "Button", "text": "A"},  # unsized
            {"name": "b", "widget": "Button", "text": "B", "style": {"size": "extra_small"}},
        ],
    }
    app = App(view, theme=Theme(dark=True))
    app.mount()
    app.update()
    assert app.root._spacing == 18.0  # extra_small's row, not the 8.0 legacy default


# --------------------------------------------------------- selection / morph


def _toggle_app(variant: str):
    """Two buttons, the first `value:`-bound checked -- the minimal shape
    for exercising the standard-group width growth and its sibling-shift
    side effect. Labels long enough that the measured width is never
    floored at `MIN_WIDTH` (a short "A"/"B" label would be, which makes
    the width-growth arithmetic below compare against the wrong baseline)."""
    view = {
        "name": "root",
        "widget": "ButtonGroup",
        "style": {"variant": variant},
        "children": [
            {"name": "a", "widget": "Button", "text": "Confirm", "value": "true"},
            {"name": "b", "widget": "Button", "text": "Cancel"},
        ],
    }
    app = App(view, theme=Theme(dark=True))
    app.mount()
    app.update()
    # A single huge tick clamps to MAX_FRAME_DELTA by design
    # (`motion/animation.py`) -- several small ticks, the same pattern
    # `test_dock.py`'s own indicator-slide test uses, actually exhaust the
    # transition.
    for _ in range(20):
        app.motion.tick(0.1)
    app.update()
    return app, app.root.find("a"), app.root.find("b")


def test_a_standard_groups_selected_button_widens_and_shifts_its_sibling() -> None:
    """No new cross-element layout coupling: `ButtonGroup` is an ordinary
    `Flex` row, so `a`'s own wider `perform_layout` result is what shifts
    `b`'s offset -- the exact effect `COMPONENT_BUTTON_GROUPS.md` describes
    ("changes the width... of itself and adjacent buttons"), produced by
    Flex's own pre-existing reflow, not a new primitive."""
    from pysilver.widgets.base import ButtonElement

    baseline_app = App(
        {
            "name": "root",
            "widget": "ButtonGroup",
            "style": {"variant": "standard"},
            "children": [{"name": "a", "widget": "Button", "text": "Confirm"}],
        },
        theme=Theme(dark=True),
    )
    baseline_app.mount()
    baseline_app.update()
    baseline_width = baseline_app.root.find("a").size.width

    _, a, b = _toggle_app("standard")
    assert a.checked is True
    assert a.size.width == pytest.approx(baseline_width + 2 * ButtonElement.GROUP_SELECT_PAD_EXTRA)
    assert b.offset.x == pytest.approx(a.size.width + ButtonGroupElement.STANDARD_SPACING)


def test_a_connected_groups_selected_button_does_not_widen() -> None:
    """`COMPONENT_BUTTON_GROUPS.md`: connected groups "don't add any
    interaction between buttons when selected... only affect the shape.\""""
    from pysilver.widgets.base import ButtonElement

    baseline_app = App(
        {
            "name": "root",
            "widget": "ButtonGroup",
            "style": {"variant": "connected"},
            "children": [{"name": "a", "widget": "Button", "text": "Confirm"}],
        },
        theme=Theme(dark=True),
    )
    baseline_app.mount()
    baseline_app.update()
    baseline_width = baseline_app.root.find("a").size.width

    _, a, _b = _toggle_app("connected")
    assert a.checked is True
    assert a.size.width == pytest.approx(baseline_width)
    assert a.effective_radii == (ButtonElement.CHECKED_RADIUS,) * 4, "shape still morphs"


def test_switching_back_to_standard_clears_the_override() -> None:
    """Reconciliation must undo a shape override, not just stop setting it."""
    view_connected = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "bg",
                "widget": "ButtonGroup",
                "style": {"variant": "connected"},
                "children": [
                    {"name": "a", "widget": "Button", "text": "A"},
                    {"name": "b", "widget": "Button", "text": "B"},
                ],
            }
        ],
    }
    app = App(view_connected, theme=Theme(dark=True))
    app.mount()
    app.update()
    a = app.root.find("a")
    assert a.effective_radii != (a.size.height / 2,) * 4

    app.reload(
        {
            "name": "root",
            "widget": "Vertical",
            "children": [
                {
                    "name": "bg",
                    "widget": "ButtonGroup",
                    "style": {"variant": "standard"},
                    "children": [
                        {"name": "a", "widget": "Button", "text": "A"},
                        {"name": "b", "widget": "Button", "text": "B"},
                    ],
                }
            ],
        }
    )
    app.update()
    a = app.root.find("a")
    assert a.effective_radii == (a.size.height / 2,) * 4


# --------------------------------------------------------------------- paint


def test_painting_does_not_crash() -> None:
    app, _group, _buttons = _app("connected")
    dl = DisplayList()
    ctx = PaintContext(display_list=dl, palette=Palette(Theme(dark=True)))
    app.root.paint(ctx, Offset(0.0, 0.0))
    assert dl.view.shape[0] > 0
