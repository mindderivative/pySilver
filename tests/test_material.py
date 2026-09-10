"""The M3 component catalogue: dimensions, variants, tokens, and state."""

from __future__ import annotations

import pytest

from pysilver import App, Signal, Theme
from pysilver.layout import Constraints, Size
from pysilver.paint import NO_TOKEN, DisplayList, Kind
from pysilver.runtime.events import EventType, PointerEvent
from pysilver.spec import SpecError, WidgetKind, parse_view
from pysilver.widgets import build_element
from pysilver.widgets.base import measure_text

LOOSE = Constraints.loose(Size(400, 400))


def element(**spec):
    return build_element(parse_view({"name": "w", **spec}).root)


def laid_out(**spec):
    e = element(**spec)
    e.layout(LOOSE)
    return e


def painted(theme: Theme | None = None, **spec) -> DisplayList:
    """Paint one widget through a real App so tokens resolve."""
    app = App(
        {
            "name": "root",
            "widget": "Vertical",
            "style": {"background": "surface"},
            "children": [{"name": "w", **spec}],
        },
        theme=theme or Theme(dark=True),
    )
    app.mount()
    dl = DisplayList()
    app.paint(dl)
    return dl


def tokens_in(dl: DisplayList) -> set[int]:
    return {int(s["flags"][2]) for s in dl.view} - {NO_TOKEN}


# ------------------------------------------------------- registered kinds


def test_every_kind_has_an_element() -> None:
    from pysilver.widgets.base import _REGISTRY, create_element

    create_element(parse_view({"name": "x", "widget": "Card"}).root)  # force lazy load
    assert set(_REGISTRY) == set(WidgetKind)


@pytest.mark.parametrize(
    "kind",
    [
        "Card",
        "Divider",
        "Checkbox",
        "Radio",
        "Switch",
        "Chip",
        "IconButton",
        "Fab",
        "Badge",
        "Accordion",
    ],
)
def test_kind_parses_and_builds(kind: str) -> None:
    assert laid_out(widget=kind) is not None


def test_unknown_variant_is_rejected_at_load() -> None:
    with pytest.raises(SpecError):
        parse_view({"name": "x", "widget": "Chip", "style": {"variant": "nope"}})


# ---------------------------------------------------- M3 dimensions (dp 1:1)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("Checkbox", Size(18, 18)),  # M3 5.1: 18x18dp box
        ("Radio", Size(20, 20)),  # M3 5.5: 20dp outer circle
        ("Switch", Size(52, 32)),  # M3 5.7: 52x32dp track
        ("IconButton", Size(40, 40)),  # M3 1.3: 40x40dp container
    ],
)
def test_control_matches_the_m3_size(kind: str, expected: Size) -> None:
    assert laid_out(widget=kind).size == expected


def test_a_button_sizes_itself_without_being_told() -> None:
    """A Button written with no `style:` used to lay out 0x0 and draw nothing.

    It paints its label rather than holding it as a child, so the container
    layout it inherited measured an absent child and returned nothing --
    while HEIGHT and MIN_WIDTH sat declared and unused. Every example carried
    an explicit size or a stylesheet class, so no golden ever caught it.

    M3: "Container Height: 40dp", "Minimum Width: 64dp", "Padding: Horizontal
    24dp".
    """
    from pysilver.widgets.base import ButtonElement

    button = laid_out(widget="Button", text="Confirm")
    assert button.size.height == ButtonElement.HEIGHT == 40.0
    assert button.size.width > ButtonElement.MIN_WIDTH, "it grew to fit its label"

    label = measure_text("Confirm", ButtonElement.LABEL_ROLE, engine=button.text_engine)
    assert button.size.width == pytest.approx(label.width + 2 * ButtonElement.PAD_X)


def test_a_button_with_no_label_still_meets_the_minimum() -> None:
    from pysilver.widgets.base import ButtonElement

    assert laid_out(widget="Button").size == Size(ButtonElement.MIN_WIDTH, ButtonElement.HEIGHT)


def test_an_explicit_size_still_wins() -> None:
    """The intrinsic size is a floor, not an override -- every existing view
    sets its own and must keep it."""
    button = laid_out(widget="Button", text="Confirm", style={"width": 130, "height": 44})
    assert button.size == Size(130, 44)


def test_a_stretched_button_keeps_its_height() -> None:
    """`cross_alignment: stretch` gives it the row's width. It used to take
    the width and stay zero high, which is the same bug wearing a disguise."""
    from pysilver.layout import Constraints
    from pysilver.spec import parse_view
    from pysilver.widgets import build_element

    view = {
        "name": "col",
        "widget": "Vertical",
        "style": {"cross_alignment": "stretch"},
        "children": [{"name": "b", "widget": "Button", "text": "Wide"}],
    }
    root = build_element(parse_view(view).root)
    root.layout(Constraints(0.0, 300.0, 0.0, 200.0))
    assert root.find("b").size == Size(300.0, 40.0)


@pytest.mark.parametrize(
    ("variant", "side"),
    [("small", 40.0), ("standard", 56.0), ("large", 96.0)],  # M3 1.2
)
def test_fab_sizes(variant: str, side: float) -> None:
    e = laid_out(widget="Fab", style={"variant": variant})
    assert e.size == Size(side, side)


def test_extended_fab_is_fifty_six_high_like_standard() -> None:
    """COMPONENT_EXTENDED_FABS.md: "Container height 56dp"."""
    e = laid_out(widget="Fab", icon="add", label="Compose", style={"variant": "extended"})
    assert e.size.height == 56.0


def test_extended_fab_with_no_content_is_the_eighty_dp_floor() -> None:
    """COMPONENT_EXTENDED_FABS.md: "Container width Dynamic, 80dp min"."""
    e = laid_out(widget="Fab", style={"variant": "extended"})
    assert e.size.width == 80.0


def test_extended_fab_widens_for_a_longer_label() -> None:
    short = laid_out(widget="Fab", icon="add", label="Go", style={"variant": "extended"})
    long = laid_out(
        widget="Fab",
        icon="add",
        label="Compose a much longer message",
        style={"variant": "extended"},
    )
    assert long.size.width > short.size.width


def test_extended_fab_with_an_icon_is_wider_than_label_only() -> None:
    """The icon reserves 24dp plus an 8dp gap on top of the label alone."""
    label_only = laid_out(widget="Fab", label="Compose", style={"variant": "extended"})
    with_icon = laid_out(widget="Fab", icon="add", label="Compose", style={"variant": "extended"})
    assert with_icon.size.width - label_only.size.width == pytest.approx(24.0 + 8.0)


def test_extended_fab_paints_both_icon_and_label() -> None:
    """Icons and text both emit as GLYPH -- distinguished here by count, not
    kind: adding the icon must add glyph instances on top of the label alone."""
    label_only = painted(widget="Fab", label="Compose", style={"variant": "extended"})
    with_icon = painted(widget="Fab", icon="add", label="Compose", style={"variant": "extended"})
    glyphs = lambda dl: sum(1 for s in dl.view if s["flags"][0] == Kind.GLYPH)  # noqa: E731
    assert glyphs(with_icon) > glyphs(label_only) > 0


def test_badge_dot_is_six_dp() -> None:
    assert laid_out(widget="Badge", style={"variant": "dot"}).size == Size(6, 6)


def test_numbered_badge_is_sixteen_high_and_at_least_as_wide() -> None:
    e = laid_out(widget="Badge", value="8")
    assert e.size.height == 16.0
    assert e.size.width >= 16.0


def test_chip_is_thirty_two_high() -> None:
    assert laid_out(widget="Chip", text="Filter").size.height == 32.0


def test_divider_is_one_dp_and_fills_width() -> None:
    """M3 3.6: 1dp thick, spanning the available width.

    Given a *tight* constraint it must obey that instead -- a node cannot
    violate its constraints -- so this uses the constraint a Vertical actually
    hands its children: bounded width, loose height.
    """
    e = element(widget="Divider")
    e.layout(Constraints(min_width=300, max_width=300, min_height=0, max_height=300))
    assert e.size == Size(300, 1.0)


def test_divider_obeys_a_tight_constraint() -> None:
    e = element(widget="Divider")
    e.layout(Constraints.tight(Size(300, 300)))
    assert e.size == Size(300, 300)


def test_divider_thickness_is_configurable() -> None:
    e = laid_out(widget="Divider", style={"thickness": 4})
    assert e.size.height == 4.0


# ------------------------------------------------------------ value binding


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("", False),
        ("none", False),
    ],
)
def test_checked_parses_truthiness(raw: str, expected: bool) -> None:
    assert laid_out(widget="Checkbox", value=raw).checked is expected


def test_value_is_bindable_to_a_signal() -> None:
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [{"name": "cb", "widget": "Checkbox", "value": "{{ on.get() }}"}],
    }
    app = App(view, theme=Theme(dark=True))
    on = Signal(False)
    app.expose(on=on)
    app.mount()
    assert app.root.find("cb").checked is False
    on.set(True)
    assert app.root.find("cb").checked is True


def test_indeterminate_checkbox_paints_the_dash_glyph_not_a_checkmark() -> None:
    """COMPONENT_CHECKBOX.md's third state: a dash, unrelated to `value:`."""
    dl = painted(widget="Checkbox", value="false", indeterminate="true")
    # emit_icon writes the glyph's own codepoint into the instance's `uv`
    # rect (the atlas region), which is how "remove" and "check" are told
    # apart at this level -- comparing paints against the checked (checkmark)
    # case is a simpler, still-real way to prove a different glyph painted.
    checked_dl = painted(widget="Checkbox", value="true")
    indeterminate_glyph = next(s for s in dl.view if s["flags"][0] == Kind.GLYPH)
    checked_glyph = next(s for s in checked_dl.view if s["flags"][0] == Kind.GLYPH)
    assert tuple(indeterminate_glyph["uv"]) != tuple(checked_glyph["uv"])


def test_indeterminate_looks_filled_even_when_value_is_false() -> None:
    """The box fills (background painted) the same way a checked one does --
    only the glyph choice differs -- since M3 shows indeterminate as a
    filled state, not an empty box with a dash floating in it."""
    unchecked = tokens_in(painted(widget="Checkbox", value="false"))
    indeterminate = tokens_in(painted(widget="Checkbox", value="false", indeterminate="true"))
    checked = tokens_in(painted(widget="Checkbox", value="true"))
    assert indeterminate == checked
    assert indeterminate != unchecked


def test_indeterminate_is_bindable() -> None:
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "cb",
                "widget": "Checkbox",
                "value": "false",
                "indeterminate": "{{ some.get() }}",
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    some = Signal(False)
    app.expose(some=some)
    app.mount()
    assert app.root.find("cb").indeterminate is False
    some.set(True)
    assert app.root.find("cb").indeterminate is True


def test_badge_count_is_bindable() -> None:
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [{"name": "b", "widget": "Badge", "value": "{{ n.get() }}"}],
    }
    app = App(view, theme=Theme(dark=True))
    n = Signal(3)
    app.expose(n=n)
    app.mount()
    assert app.root.find("b").number == 3.0
    n.set(42)
    assert app.root.find("b").value == "42"


# ------------------------------------------------------------ M3 tokens


def test_widgets_emit_tokens_not_literal_colours() -> None:
    """Token indirection is what makes a theme switch one buffer upload."""
    for kind in ("Card", "Divider", "Checkbox", "Radio", "Switch", "Fab"):
        dl = painted(widget=kind)
        assert tokens_in(dl), f"{kind} emitted no palette token"


def test_selected_checkbox_uses_primary() -> None:
    app_dl = painted(widget="Checkbox", value="true")
    from pysilver.theme import Palette

    primary = Palette(Theme(dark=True)).index("primary")
    assert primary in tokens_in(app_dl)


def test_fab_defaults_to_primary_container() -> None:
    """M3 1.2: the default FAB colour mapping."""
    from pysilver.theme import Palette

    pal = Palette(Theme(dark=True))
    assert pal.index("primary_container") in tokens_in(painted(widget="Fab", icon="add"))


def test_explicit_background_overrides_the_variant_default() -> None:
    from pysilver.theme import Palette

    pal = Palette(Theme(dark=True))
    dl = painted(widget="Fab", icon="add", style={"background": "tertiary"})
    assert pal.index("tertiary") in tokens_in(dl)


# ------------------------------------------------------------- appearance


def test_selected_and_unselected_checkbox_differ() -> None:
    assert len(painted(widget="Checkbox", value="true")) != len(
        painted(widget="Checkbox", value="false")
    ) or tokens_in(painted(widget="Checkbox", value="true")) != tokens_in(
        painted(widget="Checkbox", value="false")
    )


def test_selected_checkbox_draws_a_checkmark() -> None:
    on = painted(widget="Checkbox", value="true")
    off = painted(widget="Checkbox", value="false")
    glyphs = lambda dl: sum(1 for s in dl.view if s["flags"][0] == Kind.GLYPH)  # noqa: E731
    assert glyphs(on) == glyphs(off) + 1


def test_selected_radio_draws_an_inner_dot() -> None:
    on = painted(widget="Radio", value="true")
    off = painted(widget="Radio", value="false")
    assert len(on) == len(off) + 1


def test_elevated_card_casts_a_shadow() -> None:
    dl = painted(widget="Card", style={"variant": "elevated"})
    assert any(s["flags"][0] == Kind.SHADOW for s in dl.view)


def test_filled_card_casts_no_shadow() -> None:
    dl = painted(widget="Card", style={"variant": "filled"})
    assert not any(s["flags"][0] == Kind.SHADOW for s in dl.view)


def test_outlined_card_has_a_border() -> None:
    dl = painted(widget="Card", style={"variant": "outlined"})
    assert any(s["params"][0] > 0 for s in dl.view)


def test_fab_is_elevated() -> None:
    """M3 1.2: resting elevation level 3."""
    assert any(s["flags"][0] == Kind.SHADOW for s in painted(widget="Fab", icon="add").view)


def test_filter_chip_shows_a_checkmark_when_selected() -> None:
    sel = painted(widget="Chip", text="F", style={"variant": "filter"}, value="true")
    unsel = painted(widget="Chip", text="F", style={"variant": "filter"}, value="false")
    assert len(sel) > len(unsel)


def test_selected_filter_chip_is_wider() -> None:
    """The leading checkmark takes real space, so layout must account for it."""
    sel = laid_out(widget="Chip", text="Filter", style={"variant": "filter"}, value="true")
    unsel = laid_out(widget="Chip", text="Filter", style={"variant": "filter"}, value="false")
    assert sel.size.width > unsel.size.width


# ------------------------------------------------------------ state layers


@pytest.mark.parametrize("kind", ["Checkbox", "Radio", "Switch", "IconButton", "Fab"])
def test_hover_adds_a_state_layer(kind: str) -> None:
    """M3 §0: hover is an 8% overlay, not a different container colour.

    The layer cross-fades in, so the frame on which the hover is noticed still
    shows nothing -- the clock has to advance before there is anything to
    assert. Driving time by hand keeps that deterministic.
    """
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {"name": "w", "widget": kind, "text": "add" if kind in ("IconButton", "Fab") else None}
        ],
    }
    app = App(view, theme=Theme(dark=True))
    now = 0.0
    app.clock = lambda: now
    app.mount()
    base = DisplayList()
    app.paint(base)
    w = app.root.find("w")
    w.state.hovered = True
    w.mark_needs_paint()

    app.paint(DisplayList())  # notices the hover and starts the fade
    now = 0.2  # past the 100ms state-layer duration
    hovered = DisplayList()
    app.paint(hovered)
    assert len(hovered) == len(base) + 1


def test_hover_does_not_trigger_layout() -> None:
    app = App(
        {"name": "root", "widget": "Vertical", "children": [{"name": "w", "widget": "Switch"}]},
        theme=Theme(dark=True),
    )
    app.mount()
    app.update()
    w = app.root.find("w")
    w.state.hovered = True
    w.mark_needs_paint()
    assert w.needs_paint and not w.needs_layout


# ------------------------------------------------------------ switch drag


def _switch_app(checked: bool = False):
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "sw",
                "widget": "Switch",
                "value": "{{ on.get() }}",
                "handlers": {"on_click": "toggle"},
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    on = Signal(checked)
    calls: list[int] = []

    def toggle(event) -> None:
        calls.append(1)
        on.update(lambda v: not v)

    app.handler(toggle)
    app.expose(on=on)
    app.mount()
    app.update()
    return app, app.root.find("sw"), on, calls


def _tap(app, element, x: float, y: float) -> None:
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=x, y=y))
    app.dispatcher.drain()
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=x, y=y))
    app.dispatcher.drain()


def test_a_plain_tap_toggles_once() -> None:
    """The dispatcher's own generic click rule already does this -- no
    `on_click`/`on_pointer_down` method is defined on the class for it, and
    none should be added, or a tap would fire twice (caught by testing)."""
    app, sw, _on, calls = _switch_app(checked=False)
    rect = sw.absolute_rect()
    _tap(app, sw, rect.x + 10, rect.y + 16)
    assert sw.checked is True
    assert calls == [1]


def test_a_drag_that_stays_on_the_track_also_toggles_exactly_once() -> None:
    app, sw, _on, calls = _switch_app(checked=False)
    rect = sw.absolute_rect()
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=rect.x + 5, y=rect.y + 16))
    app.dispatcher.drain()
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=rect.x + 45, y=rect.y + 16))
    app.dispatcher.drain()
    assert sw.checked is True
    assert calls == [1]


def test_dragging_off_the_far_edge_commits_to_that_side() -> None:
    """M3: "Touch: Tap, Drag" -- COMPONENT_SWITCH.md."""
    app, sw, _on, calls = _switch_app(checked=False)
    rect = sw.absolute_rect()
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=rect.x + 5, y=rect.y + 16))
    app.dispatcher.drain()
    app.dispatcher.post(
        PointerEvent(EventType.POINTER_UP, x=rect.x + rect.width + 30, y=rect.y + 16)
    )
    app.dispatcher.drain()
    assert sw.checked is True
    assert calls == [1]


def test_dragging_toward_the_side_already_showing_is_a_no_op() -> None:
    """A blind-toggle `on_click:` handler has no way to say "set to right"
    -- this is what keeps a redundant drag from flipping it the wrong way."""
    app, sw, _on, calls = _switch_app(checked=True)
    rect = sw.absolute_rect()
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=rect.x + 45, y=rect.y + 16))
    app.dispatcher.drain()
    app.dispatcher.post(
        PointerEvent(EventType.POINTER_UP, x=rect.x + rect.width + 30, y=rect.y + 16)
    )
    app.dispatcher.drain()
    assert sw.checked is True
    assert calls == []


def test_dragging_off_the_opposite_edge_commits_the_other_way() -> None:
    app, sw, _on, calls = _switch_app(checked=True)
    rect = sw.absolute_rect()
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=rect.x + 45, y=rect.y + 16))
    app.dispatcher.drain()
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=rect.x - 30, y=rect.y + 16))
    app.dispatcher.drain()
    assert sw.checked is False
    assert calls == [1]


# ---------------------------------------------------------- button variants


@pytest.mark.parametrize("variant", ["filled", "filled_tonal", "outlined", "elevated", "text"])
def test_button_variants_all_render(variant: str) -> None:
    dl = painted(widget="Button", text="Go", style={"variant": variant})
    assert len(dl) > 0


def test_outlined_button_has_a_border_and_no_fill() -> None:
    dl = painted(widget="Button", text="Go", style={"variant": "outlined"})
    assert any(s["params"][0] > 0 for s in dl.view)


def test_elevated_button_casts_a_shadow() -> None:
    dl = painted(widget="Button", text="Go", style={"variant": "elevated"})
    assert any(s["flags"][0] == Kind.SHADOW for s in dl.view)


def test_text_button_draws_no_container() -> None:
    text_btn = painted(widget="Button", text="Go", style={"variant": "text"})
    filled = painted(widget="Button", text="Go", style={"variant": "filled"})
    assert len(text_btn) < len(filled)


# ------------------------------------------------------- button shape morph


def test_an_unchecked_unpressed_button_stays_full_round() -> None:
    """A plain Button (the overwhelming majority -- no `value:` at all)
    must see zero behaviour change from the shape-morph feature."""
    from pysilver.widgets.base import ButtonElement

    button = laid_out(widget="Button", text="Go")
    assert button.effective_radii == (ButtonElement.HEIGHT / 2,) * 4


def test_a_checked_button_rests_at_the_sourced_selected_radius() -> None:
    """`COMPONENT_BUTTONS.md`'s own "Corner sizes" table, M size: 16dp."""
    from pysilver.widgets.base import ButtonElement

    button = laid_out(widget="Button", text="Go", value="true")
    assert button.checked is True
    assert button.effective_radii == (ButtonElement.CHECKED_RADIUS,) * 4 == (16.0,) * 4


def test_a_pressed_button_morphs_regardless_of_checked() -> None:
    """ "Both round and square buttons should have the same pressed shape" --
    pressed wins over both the round resting shape and the checked one."""
    from pysilver.widgets.base import ButtonElement

    unchecked = laid_out(widget="Button", text="Go")
    unchecked.state.pressed = True
    assert unchecked.effective_radii == (ButtonElement.PRESSED_RADIUS,) * 4 == (12.0,) * 4

    checked = laid_out(widget="Button", text="Go", value="true")
    checked.state.pressed = True
    assert checked.effective_radii == (ButtonElement.PRESSED_RADIUS,) * 4


def test_a_checked_connected_group_button_overrides_its_own_position_shape() -> None:
    """A connected group's own selected button still morphs -- the shape
    change is real Button behaviour, independent of `_group_radii`'s
    position-based override (`COMPONENT_BUTTON_GROUPS.md`: a connected
    group's selection "only affect[s] the shape of the button being
    selected")."""
    from pysilver.widgets.base import ButtonElement

    view = {
        "name": "root",
        "widget": "ButtonGroup",
        "style": {"variant": "connected"},
        "children": [
            {"name": "a", "widget": "Button", "text": "A", "value": "true"},
            {"name": "b", "widget": "Button", "text": "B"},
        ],
    }
    app = App(view, theme=Theme(dark=True))
    app.mount()
    app.update()
    a = app.root.find("a")
    assert a._group_radii is not None, "the connected override was set"
    assert a.effective_radii == (ButtonElement.CHECKED_RADIUS,) * 4, (
        "checked still wins over the connected group's own position-based shape"
    )


def test_group_select_pad_extra_does_not_apply_outside_a_standard_group() -> None:
    """A checked, standalone Button (no `ButtonGroup` parent at all) must
    not grow -- the width change is `ButtonGroup`-specific, not general
    toggle-button behaviour (`COMPONENT_BUTTON_GROUPS.md`'s own "Selection
    & activation" section is scoped to groups)."""
    from pysilver.widgets.base import ButtonElement

    unchecked = laid_out(widget="Button", text="Go")
    checked = laid_out(widget="Button", text="Go", value="true")
    assert (
        checked.size.width
        == unchecked.size.width
        == pytest.approx(
            measure_text("Go", ButtonElement.LABEL_ROLE, engine=unchecked.text_engine).width
            + 2 * ButtonElement.PAD_X
        )
    )


# -------------------------------------------------------------- size ladder


def test_a_button_with_no_size_keeps_its_legacy_dimensions() -> None:
    """`style.size`'s own bare Pydantic default is `"extra_small"` (correct
    for `Slider`, the field's first owner) -- a Button that never mentions
    `size:` at all must NOT silently become a 32dp extra_small button. Zero
    behaviour change is the bar every opt-in field in this codebase is held
    to; `model_fields_set` is what makes that possible here."""
    from pysilver.widgets.base import ButtonElement

    button = laid_out(widget="Button", text="Go")
    assert button.size.height == ButtonElement.HEIGHT == 40.0
    assert button.effective_radii == (ButtonElement.HEIGHT / 2,) * 4

    checked = laid_out(widget="Button", text="Go", value="true")
    assert checked.effective_radii == (ButtonElement.CHECKED_RADIUS,) * 4 == (16.0,) * 4


@pytest.mark.parametrize(
    ("size", "height", "checked_radius", "pressed_radius"),
    [
        ("extra_small", 32.0, 12.0, 8.0),
        ("small", 40.0, 12.0, 8.0),
        ("medium", 56.0, 16.0, 12.0),
        ("large", 96.0, 28.0, 16.0),
        ("extra_large", 136.0, 28.0, 16.0),
    ],
)
def test_button_size_ladder_matches_the_sourced_table(
    size: str, height: float, checked_radius: float, pressed_radius: float
) -> None:
    """The real M3 Expressive ladder, confirmed live against the actual
    diagram at m3.material.io (the scraped text carries no table for it) and
    cross-checked against COMPONENT_BUTTON_GROUPS.md's own scraped token
    residue for the extra_small row -- both agree."""
    button = laid_out(widget="Button", text="Go", style={"size": size})
    assert button.size.height == height

    checked = laid_out(widget="Button", text="Go", value="true", style={"size": size})
    assert checked.effective_radii == (checked_radius,) * 4

    pressed = laid_out(widget="Button", text="Go", style={"size": size})
    pressed.state.pressed = True
    assert pressed.effective_radii == (pressed_radius,) * 4


def test_an_explicit_size_widens_the_horizontal_padding_too() -> None:
    """The ladder is not height-only -- `large`'s 48dp padding must actually
    reach `perform_layout`'s own width math, not just the container height."""
    from pysilver.widgets.base import ButtonElement

    default = laid_out(widget="Button", text="Launch")
    large = laid_out(widget="Button", text="Launch", style={"size": "large"})
    label_width = measure_text("Launch", ButtonElement.LABEL_ROLE, engine=default.text_engine).width
    assert default.size.width == pytest.approx(label_width + 2 * 24.0)
    assert large.size.width == pytest.approx(label_width + 2 * 48.0)


# ------------------------------------------------------------------- link


def test_link_underlines_its_label() -> None:
    """M3: "Hyperlinked text must also be underlined" -- not optional."""
    e = laid_out(widget="Link", text="Learn more")
    dl = painted(widget="Link", text="Learn more")
    underlines = [
        s for s in dl.view if s["flags"][0] == Kind.BOX and abs(float(s["rect"][3]) - 1.0) < 0.01
    ]
    assert len(underlines) == 1
    assert float(underlines[0]["rect"][2]) == pytest.approx(e.size.width)


def test_link_defaults_to_primary() -> None:
    from pysilver.theme import Palette

    pal = Palette(Theme(dark=True))
    assert pal.index("primary") in tokens_in(painted(widget="Link", text="Learn more"))


def test_link_tertiary_variant_uses_tertiary() -> None:
    from pysilver.theme import Palette

    pal = Palette(Theme(dark=True))
    dl = painted(widget="Link", text="Learn more", style={"variant": "tertiary"})
    assert pal.index("tertiary") in tokens_in(dl)
    assert pal.index("primary") not in tokens_in(dl)


def test_link_draws_only_its_label_and_underline() -> None:
    """No container, no state layer -- unlike a text Button, whose state
    layer is merely invisible at rest, a Link never has one to begin with.
    That contrast, not just the underline, is the whole anatomy M3 draws
    between the two."""
    dl = painted(widget="Link", text="Go")
    glyphs = sum(1 for s in dl.view if s["flags"][0] == Kind.GLYPH)
    # Excludes the wrapping Vertical's own background box, which `painted()`
    # always draws regardless of what widget is under test.
    own_boxes = [s for s in dl.view if s["flags"][0] == Kind.BOX and float(s["rect"][3]) < 10.0]
    assert glyphs == len("Go")
    assert len(own_boxes) == 1


# ------------------------------------------------------------- spin box


def test_spin_box_is_forty_high() -> None:
    e = laid_out(widget="SpinBox", value="3")
    assert e.size.height == 40.0


def test_spin_box_widens_for_a_bigger_number() -> None:
    small = laid_out(widget="SpinBox", value="1")
    big = laid_out(widget="SpinBox", value="1000000")
    assert big.size.width > small.size.width


def _spin_box_app(*, value="3", min=None, max=None, step=1, on_change=None):
    style = {"step": step}
    if min is not None:
        style["min"] = min
    if max is not None:
        style["max"] = max
    child = {"name": "sb", "widget": "SpinBox", "value": value, "style": style}
    if on_change is not None:
        child["handlers"] = {"on_change": "change"}
    view = {"name": "root", "widget": "Vertical", "children": [child]}
    app = App(view, theme=Theme(dark=True))
    if on_change is not None:
        app._handlers["change"] = on_change
    app.mount()
    app.update()
    return app


def _click(app, x, y):
    from pysilver.runtime.events import EventType, PointerEvent

    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=x, y=y))
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=x, y=y))
    app.dispatcher.drain()


def test_clicking_the_right_side_increments() -> None:
    app = _spin_box_app(value="3")
    sb = app.root.find("sb")
    rect = sb.absolute_rect()
    _click(app, rect.right - 5, rect.y + 20)
    assert sb.number == 4.0


def test_clicking_the_left_side_decrements() -> None:
    app = _spin_box_app(value="3")
    sb = app.root.find("sb")
    rect = sb.absolute_rect()
    _click(app, rect.x + 5, rect.y + 20)
    assert sb.number == 2.0


def test_clicking_the_middle_does_nothing() -> None:
    app = _spin_box_app(value="3")
    sb = app.root.find("sb")
    rect = sb.absolute_rect()
    _click(app, rect.x + rect.width / 2, rect.y + 20)
    assert sb.number == 3.0


def test_value_clamps_at_the_maximum() -> None:
    app = _spin_box_app(value="4", max=5)
    sb = app.root.find("sb")
    rect = sb.absolute_rect()
    for _ in range(3):
        _click(app, rect.right - 5, rect.y + 20)
    assert sb.number == 5.0


def test_value_clamps_at_the_minimum() -> None:
    app = _spin_box_app(value="1", min=0)
    sb = app.root.find("sb")
    rect = sb.absolute_rect()
    for _ in range(3):
        _click(app, rect.x + 5, rect.y + 20)
    assert sb.number == 0.0


def test_step_is_configurable() -> None:
    app = _spin_box_app(value="0", step=5)
    sb = app.root.find("sb")
    rect = sb.absolute_rect()
    _click(app, rect.right - 5, rect.y + 20)
    assert sb.number == 5.0


def test_on_change_carries_the_new_value() -> None:
    calls = []
    app = _spin_box_app(value="3", on_change=lambda e: calls.append(e.value))
    sb = app.root.find("sb")
    rect = sb.absolute_rect()
    _click(app, rect.right - 5, rect.y + 20)
    assert calls == ["4"]


def test_arrow_keys_step_the_value() -> None:
    from pysilver.runtime.events import EventType, KeyEvent

    app = _spin_box_app(value="3")
    sb = app.root.find("sb")
    app.dispatcher.focus(sb)
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Up"))
    app.dispatcher.drain()
    assert sb.number == 4.0
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Down"))
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Down"))
    app.dispatcher.drain()
    assert sb.number == 2.0


def test_a_maxed_out_side_stops_responding_and_dims() -> None:
    """Clicking past the bound is a silent no-op, and the icon dims to M3's
    disabled-content opacity -- reused by analogy, not because the whole
    control is `disabled`."""
    app = _spin_box_app(value="5", max=5)
    dl = painted_app(app)
    glyphs = [s for s in dl.view if s["flags"][0] == Kind.GLYPH]
    dimmed = [g for g in glyphs if float(g["fill"][3]) < 1.0]
    assert dimmed, "expected the maxed-out side's icon to be dimmed"


def test_a_minned_out_side_stops_responding_and_dims() -> None:
    """The mirror of the maxed-out case: `at_min` dims the decrement side the
    same way `at_max` dims the increment side."""
    app = _spin_box_app(value="0", min=0)
    dl = painted_app(app)
    glyphs = [s for s in dl.view if s["flags"][0] == Kind.GLYPH]
    dimmed = [g for g in glyphs if float(g["fill"][3]) < 1.0]
    assert dimmed, "expected the minned-out side's icon to be dimmed"


def painted_app(app) -> DisplayList:
    dl = DisplayList()
    app.paint(dl)
    return dl


# ----------------------------------------------------------- pagination


def _pagination_app(*, value="1", count=10, on_change=None):
    style = {"count": count}
    child = {"name": "pg", "widget": "Pagination", "value": value, "style": style}
    if on_change is not None:
        child["handlers"] = {"on_change": "change"}
    view = {"name": "root", "widget": "Vertical", "children": [child]}
    app = App(view, theme=Theme(dark=True))
    if on_change is not None:
        app._handlers["change"] = on_change
    app.mount()
    app.update()
    return app


def _slot_center(element, index: int) -> float:
    """The x of a slot's centre, re-derived from the element's CURRENT
    layout -- Pagination's own width changes as the current page moves, so a
    coordinate computed before a click can be stale after it."""
    rect = element.absolute_rect()
    return rect.x + index * (element.BUTTON + element.GAP) + element.BUTTON / 2


def _click_slot(app, element, index: int) -> None:
    from pysilver.runtime.events import EventType, PointerEvent

    rect = element.absolute_rect()
    x = _slot_center(element, index)
    y = rect.y + element.BUTTON / 2
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=x, y=y))
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=x, y=y))
    app.dispatcher.drain()


def test_pagination_is_forty_high() -> None:
    e = laid_out(widget="Pagination", value="1", style={"count": 5})
    assert e.size.height == 40.0


def test_small_counts_show_every_page_with_no_ellipsis() -> None:
    e = laid_out(widget="Pagination", value="1", style={"count": 7})
    assert e._slots() == [("prev", None)] + [("page", n) for n in range(1, 8)] + [("next", None)]


def test_large_counts_collapse_around_the_current_page() -> None:
    e = laid_out(widget="Pagination", value="5", style={"count": 10})
    kinds = [k for k, _ in e._slots()]
    assert kinds.count("ellipsis") == 2
    assert ("page", 1) in e._slots()
    assert ("page", 10) in e._slots()
    assert ("page", 5) in e._slots()


def test_the_edges_never_need_two_ellipses() -> None:
    first = laid_out(widget="Pagination", value="1", style={"count": 10})
    assert [k for k, _ in first._slots()].count("ellipsis") == 1
    last = laid_out(widget="Pagination", value="10", style={"count": 10})
    assert [k for k, _ in last._slots()].count("ellipsis") == 1


def test_clicking_a_page_number_jumps_to_it() -> None:
    app = _pagination_app(value="5", count=10)
    pg = app.root.find("pg")
    index = pg._slots().index(("page", 10))
    _click_slot(app, pg, index)
    assert pg.number == 10.0


def test_clicking_next_advances_by_one() -> None:
    app = _pagination_app(value="5", count=10)
    pg = app.root.find("pg")
    _click_slot(app, pg, len(pg._slots()) - 1)
    assert pg.number == 6.0


def test_clicking_prev_goes_back_one() -> None:
    app = _pagination_app(value="5", count=10)
    pg = app.root.find("pg")
    _click_slot(app, pg, 0)
    assert pg.number == 4.0


def test_next_stops_at_the_last_page() -> None:
    app = _pagination_app(value="10", count=10)
    pg = app.root.find("pg")
    _click_slot(app, pg, len(pg._slots()) - 1)
    assert pg.number == 10.0


def test_prev_stops_at_the_first_page() -> None:
    app = _pagination_app(value="1", count=10)
    pg = app.root.find("pg")
    _click_slot(app, pg, 0)
    assert pg.number == 1.0


def test_clicking_an_ellipsis_does_nothing() -> None:
    app = _pagination_app(value="5", count=10)
    pg = app.root.find("pg")
    index = pg._slots().index(("ellipsis", None))
    _click_slot(app, pg, index)
    assert pg.number == 5.0


def test_on_change_carries_the_new_page() -> None:
    calls = []
    app = _pagination_app(value="5", count=10, on_change=lambda e: calls.append(e.value))
    pg = app.root.find("pg")
    _click_slot(app, pg, len(pg._slots()) - 1)
    assert calls == ["6"]


def test_arrow_keys_change_the_page() -> None:
    from pysilver.runtime.events import EventType, KeyEvent

    app = _pagination_app(value="5", count=10)
    pg = app.root.find("pg")
    app.dispatcher.focus(pg)
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Right"))
    app.dispatcher.drain()
    assert pg.number == 6.0
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Left"))
    app.dispatcher.post(KeyEvent(EventType.KEY_DOWN, key="Left"))
    app.dispatcher.drain()
    assert pg.number == 4.0


def test_the_current_page_and_a_boundary_arrow_are_visually_distinct() -> None:
    """The selected page gets a secondary_container fill; a spent arrow (at
    page 1, nothing to go back to) dims instead -- two different signals,
    not the same one reused."""
    from pysilver.theme import Palette

    pal = Palette(Theme(dark=True))
    dl = painted(widget="Pagination", value="1", style={"count": 10})
    tokens = tokens_in(dl)
    assert pal.index("secondary_container") in tokens
    glyphs = [s for s in dl.view if s["flags"][0] == Kind.GLYPH]
    assert any(float(g["fill"][3]) < 1.0 for g in glyphs), "expected the spent prev arrow to dim"


# --------------------------------------------------------------- accordion


def _accordion_view(*, value: str):
    return {
        "name": "acc",
        "widget": "Accordion",
        "text": "Headline",
        "value": value,
        "children": [
            {"name": "body", "widget": "Text", "text": "Body content", "style": {"height": 200}}
        ],
    }


def test_collapsed_accordion_is_header_height_only() -> None:
    e = laid_out(**_accordion_view(value="false"))
    assert e.size.height == 56.0


def test_expanded_accordion_reveals_the_body() -> None:
    e = laid_out(**_accordion_view(value="true"))
    assert e.size.height > 56.0


def test_two_line_header_is_seventy_two_dp() -> None:
    e = laid_out(widget="Accordion", text="Headline", supporting_text="Supporting", value="false")
    assert e.size.height == 72.0


def test_accordion_chevron_swaps_rather_than_stacking() -> None:
    """`expand_more` swaps for `expand_less` -- the glyph does not rotate (no
    rotation parameter on a glyph instance) and both are never drawn at once.
    Same glyph *count* in both states is exactly what rules out stacking;
    the display list always emits a fully laid-out subtree regardless of the
    in-shader clip, so a body child would add the same glyphs either way and
    is deliberately omitted here to isolate the chevron itself."""
    collapsed = painted(widget="Accordion", text="Headline", value="false")
    expanded = painted(widget="Accordion", text="Headline", value="true")
    glyphs = lambda dl: sum(1 for s in dl.view if s["flags"][0] == Kind.GLYPH)  # noqa: E731
    assert glyphs(collapsed) == glyphs(expanded) >= 1


def test_accordion_expand_state_is_bindable() -> None:
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "acc",
                "widget": "Accordion",
                "text": "Headline",
                "value": "{{ open.get() }}",
                "children": [{"name": "body", "widget": "Text", "text": "x"}],
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    open_ = Signal(False)
    app.expose(open=open_)
    app.mount()
    app.update()
    collapsed_height = app.root.find("acc").size.height

    open_.set(True)
    app.update()  # retargets the animation; does not jump (see test_motion.py)
    assert app.root.find("acc").size.height == collapsed_height

    app.motion.tick(1.0)  # past the expand transition
    app.update()  # relayout picks up the now-advanced value
    assert app.root.find("acc").size.height > collapsed_height


def test_accordion_hover_state_layer_does_not_cover_the_body() -> None:
    """The state layer is scoped to the header row -- `_emit_state_layer`
    sizes from the whole (animated) element, which would wrongly tint the
    revealed body too, so this widget emits its own header-sized box."""
    view = {
        "name": "root",
        "widget": "Vertical",
        "children": [
            {
                "name": "acc",
                "widget": "Accordion",
                "text": "Headline",
                "value": "true",
                "children": [
                    {"name": "body", "widget": "Text", "text": "x", "style": {"height": 200}}
                ],
            }
        ],
    }
    app = App(view, theme=Theme(dark=True))
    now = 0.0
    app.clock = lambda: now
    app.mount()
    base = DisplayList()
    app.paint(base)
    assert not any(
        s["flags"][0] == Kind.BOX and s["fill"][3] > 0 and s["rect"][3] <= 56.0 for s in base.view
    )

    w = app.root.find("acc")
    w.state.hovered = True
    w.mark_needs_paint()
    app.paint(DisplayList())  # notices the hover and starts the fade
    now = 0.2  # past the state-layer duration
    hovered = DisplayList()
    app.paint(hovered)
    assert len(hovered) == len(base) + 1
    assert any(
        s["flags"][0] == Kind.BOX and s["fill"][3] > 0 and s["rect"][3] <= 56.0
        for s in hovered.view
    )
