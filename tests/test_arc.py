"""Arc rendering: the SDF primitive and the M3 circular progress built on it."""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from pysilver import App, Settings, Theme
from pysilver.layout import Constraints, Size
from pysilver.paint import NO_TOKEN, DisplayList, Kind
from pysilver.spec import parse_view
from pysilver.theme import Palette
from pysilver.widgets import build_element
from pysilver.widgets.navigation import CircularProgressElement

PALETTE = Palette(Theme(dark=True))
SHADER = Path(__file__).resolve().parents[1] / "src/pysilver/render/shaders/ui.wgsl"
TAU = 2.0 * math.pi


def laid_out(**spec):
    element = build_element(parse_view({"name": "p", "widget": "CircularProgress", **spec}).root)
    element.layout(Constraints.loose(Size(400, 400)))
    return element


def arcs_of(**spec) -> list:
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [{"name": "p", "widget": "CircularProgress", **spec}],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=200, height=200),
    )
    app.mount()
    dl = DisplayList()
    app.paint(dl)
    return [s for s in dl.view if int(s["flags"][0]) == int(Kind.ARC)]


def params(instance) -> tuple[float, float, float, float]:
    return tuple(float(v) for v in instance["params"])  # type: ignore[return-value]


# ------------------------------------------------------ shader/python drift


def test_every_kind_matches_the_shader_constant() -> None:
    """`Kind` is a branch selector the shader reads out of `flags.x`.

    Nothing else ties the two together, so a renumbered enum would silently
    draw every box as a glyph rather than fail.
    """
    source = SHADER.read_text()
    declared = {
        name.removeprefix("KIND_"): int(value)
        for name, value in re.findall(r"const (KIND_\w+)\s*:\s*u32\s*=\s*(\d+)u", source)
    }
    assert declared == {k.name: int(k) for k in Kind}


# ------------------------------------------------------------- the primitive


def test_add_arc_encodes_geometry_into_params() -> None:
    dl = DisplayList()
    i = dl.add_arc(10, 20, 48, 48, thickness=4.0, start=0.5, sweep=1.25, token=7)
    s = dl.view[i]
    assert int(s["flags"][0]) == int(Kind.ARC)
    assert int(s["flags"][2]) == 7
    assert tuple(float(v) for v in s["rect"]) == (10.0, 20.0, 48.0, 48.0)
    assert params(s)[:3] == (4.0, 0.5, 1.25)


def test_add_arc_carries_the_clip_like_every_other_primitive() -> None:
    """Arcs must be clippable, or one inside a ScrollView would escape it."""
    dl = DisplayList()
    i = dl.add_arc(0, 0, 20, 20, thickness=2, start=0, sweep=1, clip=(1.0, 2.0, 30.0, 40.0))
    assert tuple(float(v) for v in dl.view[i]["clip"]) == (1.0, 2.0, 30.0, 40.0)


# -------------------------------------------------------------------- layout


def test_circular_progress_defaults_to_a_48dp_square() -> None:
    assert laid_out(value="0.5").size == Size(48.0, 48.0)


def test_an_explicit_width_sets_the_diameter() -> None:
    assert laid_out(value="0.5", style={"width": 72}).size == Size(72.0, 72.0)


def test_setting_one_axis_gives_a_square() -> None:
    assert laid_out(value="0.5", style={"width": 72}).size == Size(72.0, 72.0)
    assert laid_out(value="0.5", style={"height": 32}).size == Size(32.0, 32.0)


def test_a_non_square_box_inscribes_the_circle_rather_than_stretching_it() -> None:
    """Setting both axes is the designer's call and constraints are not
    negotiable, so the box stays 64x20 -- but the arc drawn inside it is a
    circle of the shorter side, centred, not an ellipse."""
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface"},
                "children": [
                    {
                        "name": "p",
                        "widget": "CircularProgress",
                        "value": "0.5",
                        "style": {"width": 64, "height": 20},
                    },
                ],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=200, height=200),
    )
    app.mount()
    dl = DisplayList()
    app.paint(dl)
    element = app.root.find("p")
    assert element.size == Size(64.0, 20.0)

    arc = next(s for s in dl.view if int(s["flags"][0]) == int(Kind.ARC))
    _, _, w, h = (float(v) for v in arc["rect"])
    assert w == h == 20.0, "the arc box is not square"


@pytest.mark.parametrize(
    ("value", "expected"), [("-1", 0.0), ("0", 0.0), ("0.5", 0.5), ("1", 1.0), ("2", 1.0)]
)
def test_progress_is_clamped_to_the_unit_range(value: str, expected: float) -> None:
    assert laid_out(value=value).progress == expected


def test_thickness_defaults_to_the_m3_4dp_not_the_divider_default() -> None:
    """`style.thickness` defaults to 1dp for Divider's sake, so this has to be
    distinguished from the field default rather than compared to it."""
    assert laid_out(value="0.5").thickness == CircularProgressElement.THICKNESS == 4.0
    assert laid_out(value="0.5", style={"thickness": 10}).thickness == 10.0
    # An explicit 1 is honoured, not mistaken for "unset".
    assert laid_out(value="0.5", style={"thickness": 1}).thickness == 1.0


# --------------------------------------------------------------------- paint


def test_a_track_and_an_active_arc_are_emitted() -> None:
    track, active = arcs_of(value="0.25")
    assert params(track)[2] == pytest.approx(TAU), "track is not a full turn"
    assert params(active)[2] == pytest.approx(TAU * 0.25)


def test_the_sweep_is_proportional_to_the_value() -> None:
    for fraction in (0.1, 0.33, 0.5, 0.9):
        _, active = arcs_of(value=str(fraction))
        assert params(active)[2] == pytest.approx(TAU * fraction)


def test_both_arcs_start_at_twelve_oclock() -> None:
    """M3: "circular indicators animate from the top of the track, clockwise"."""
    for arc in arcs_of(value="0.4"):
        assert params(arc)[1] == 0.0


def test_no_active_arc_is_emitted_at_zero() -> None:
    """A zero sweep would still paint a round cap -- a dot at 12 o'clock."""
    assert len(arcs_of(value="0")) == 1


def test_a_full_value_emits_a_complete_turn() -> None:
    _, active = arcs_of(value="1")
    assert params(active)[2] == pytest.approx(TAU)


def test_the_m3_colour_roles_are_palette_tokens() -> None:
    """M3: active indicator `primary`, track `secondary container`."""
    track, active = arcs_of(value="0.5")
    assert int(track["flags"][2]) == PALETTE.index("secondary_container")
    assert int(active["flags"][2]) == PALETTE.index("primary")
    assert int(track["flags"][2]) != NO_TOKEN


def test_colours_can_be_overridden_per_widget() -> None:
    track, active = arcs_of(value="0.5", style={"color": "tertiary", "background": "surface"})
    assert int(track["flags"][2]) == PALETTE.index("surface")
    assert int(active["flags"][2]) == PALETTE.index("tertiary")


def test_linear_and_circular_progress_agree_on_their_track() -> None:
    """They share one colour-role table in the spec, so they must not diverge."""
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface", "width": 200},
                "children": [
                    {
                        "name": "lin",
                        "widget": "LinearProgress",
                        "value": "0.5",
                        "style": {"width": "expand"},
                    },
                    {"name": "circ", "widget": "CircularProgress", "value": "0.5"},
                ],
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=240, height=200),
    )
    app.mount()
    dl = DisplayList()
    app.paint(dl)
    expected = PALETTE.index("secondary_container")
    tracks = [s for s in dl.view if int(s["flags"][2]) == expected]
    assert len(tracks) == 2, "linear and circular tracks use different tokens"
