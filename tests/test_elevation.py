"""M3 elevation levels.

The spec's own words drove this: "Surface tint color is deprecated. Use
elevation level tokens (0-5) instead." The tonal-overlay mechanism pySilver's
docs described as missing is the one M3 has withdrawn -- tonal separation now
comes from the surface container roles, which are explicitly "not tied to
elevation" and which the widget catalogue already uses.
"""

from __future__ import annotations

import pytest

from pysilver import App, Settings, Theme
from pysilver.paint import DisplayList, Kind
from pysilver.spec import SpecError, parse_view
from pysilver.widgets import build_element
from pysilver.widgets.material import ELEVATION_DP


def hosted(children):
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": children,
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=300, height=400),
    )
    app.mount()
    return app


def shadows(app: App) -> list:
    dl = DisplayList()
    app.paint(dl)
    return [s for s in dl.view if int(s["flags"][0]) == int(Kind.SHADOW)]


# ------------------------------------------------------------------ tokens


def test_the_dp_heights_are_m3s_own() -> None:
    """Quoted from the elevation token table."""
    assert ELEVATION_DP == {0: 0.0, 1: 1.0, 2: 3.0, 3: 6.0, 4: 8.0, 5: 12.0}


def test_a_level_outside_the_scale_fails_at_load() -> None:
    for bad in (-1, 6, 12):
        with pytest.raises(SpecError):
            parse_view({"name": "c", "widget": "Card", "style": {"elevation": bad}})


# ------------------------------------------------------------- resolution


def test_a_component_uses_its_m3_resting_level() -> None:
    """M3's resting-level table: FAB and modal dialog at 3, Menu at 2, elevated
    Card and modal sheets at 1, everything else at 0."""
    cases = {
        "Fab": 3,
        "Dialog": 3,
        "Menu": 2,
        "BottomSheet": 1,
        "SideSheet": 1,
        "Button": 0,
        "Checkbox": 0,
    }
    for kind, level in cases.items():
        element = build_element(parse_view({"name": "w", "widget": kind}).root)
        assert element.elevation == level, f"{kind} rests at the wrong level"


def test_a_view_can_override_the_resting_level() -> None:
    element = build_element(
        parse_view({"name": "w", "widget": "Fab", "style": {"elevation": 0}}).root
    )
    assert element.elevation == 0


def test_zero_is_an_override_not_an_absence() -> None:
    """`elevation: 0` must flatten a FAB, not fall through to its resting 3."""
    raised = build_element(parse_view({"name": "w", "widget": "Fab"}).root)
    flat = build_element(parse_view({"name": "w", "widget": "Fab", "style": {"elevation": 0}}).root)
    assert raised.elevation == 3
    assert flat.elevation == 0


def test_hover_raises_an_elevated_component_by_one_level() -> None:
    """M3: hovered or focused "usually raises elevation by one level"."""
    element = build_element(parse_view({"name": "w", "widget": "Fab"}).root)
    assert element.elevation == 3
    element.state.hovered = True
    assert element.elevation == 4


def test_focus_raises_it_too() -> None:
    element = build_element(parse_view({"name": "w", "widget": "Menu"}).root)
    element.state.focused = True
    assert element.elevation == 3


def test_a_flat_component_stays_flat_on_hover() -> None:
    """ "Usually" is not licence to give every filled button a shadow the
    moment a pointer crosses it."""
    element = build_element(parse_view({"name": "w", "widget": "Button"}).root)
    element.state.hovered = True
    assert element.elevation == 0


def test_the_raise_cannot_exceed_the_scale() -> None:
    element = build_element(
        parse_view({"name": "w", "widget": "Card", "style": {"elevation": 5}}).root
    )
    element.state.hovered = True
    assert element.elevation == 5


# ------------------------------------------------------------------- paint


def test_level_zero_draws_no_shadow() -> None:
    """Also guards `self.elevation or FALLBACK`, a pattern that cannot tell an
    explicit 0 from unset and would silently re-raise a card asked to flatten."""
    app = hosted(
        [
            {
                "name": "c",
                "widget": "Card",
                "style": {"variant": "elevated", "elevation": 0, "width": 100, "height": 40},
            }
        ]
    )
    assert shadows(app) == []


def test_a_higher_level_gives_a_larger_softer_shadow() -> None:
    """M3: "larger, softer shadows express more distance"."""
    blurs = []
    for level in (1, 2, 3, 4, 5):
        app = hosted(
            [
                {
                    "name": "c",
                    "widget": "Card",
                    "style": {
                        "variant": "elevated",
                        "elevation": level,
                        "width": 100,
                        "height": 40,
                    },
                }
            ]
        )
        found = shadows(app)
        assert len(found) == 1
        blurs.append(float(found[0]["params"][1]))
    assert blurs == sorted(blurs)
    assert len(set(blurs)) == 5, "two levels produced the same shadow"


def test_the_offset_grows_with_the_level() -> None:
    offsets = []
    for level in (1, 3, 5):
        app = hosted(
            [
                {
                    "name": "c",
                    "widget": "Card",
                    "style": {
                        "variant": "elevated",
                        "elevation": level,
                        "width": 100,
                        "height": 40,
                    },
                }
            ]
        )
        offsets.append(float(shadows(app)[0]["params"][3]))
    assert offsets == sorted(offsets)
    assert offsets[0] == ELEVATION_DP[1]
    assert offsets[-1] == ELEVATION_DP[5]


def test_components_at_the_same_level_cast_the_same_shadow() -> None:
    """Three widgets used to hand-tune their own blur, so a dialog and a FAB
    at the same M3 level did not look like they were at the same height."""

    def blur_of(kind: str, style: dict) -> float:
        app = hosted([{"name": "w", "widget": kind, "style": style}])
        found = shadows(app)
        assert found, f"{kind} cast no shadow"
        return float(found[0]["params"][1])

    card = blur_of("Card", {"variant": "elevated", "elevation": 3, "width": 100, "height": 40})
    fab = blur_of("Fab", {"elevation": 3})
    assert card == fab


def test_a_cards_resting_level_follows_its_variant() -> None:
    """M3 elevates only the `elevated` card; filled and outlined sit at 0."""
    for variant, level in (("elevated", 1), ("filled", 0), ("outlined", 0)):
        element = build_element(
            parse_view({"name": "c", "widget": "Card", "style": {"variant": variant}}).root
        )
        assert element.elevation == level, f"{variant} card"


def test_a_buttons_resting_level_follows_its_variant() -> None:
    for variant, level in (("elevated", 1), ("filled", 0), ("outlined", 0), ("text", 0)):
        element = build_element(
            parse_view({"name": "b", "widget": "Button", "style": {"variant": variant}}).root
        )
        assert element.elevation == level, f"{variant} button"
