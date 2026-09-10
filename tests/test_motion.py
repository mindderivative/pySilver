"""Motion: M3 easing and durations, the animation clock, and idleness.

The load-bearing test is `test_an_app_with_nothing_animating_stays_idle`.
Animation is the one subsystem that can legitimately ask for frames forever,
so the thing worth guarding is that it stops asking.
"""

from __future__ import annotations

import itertools

import pytest

from pysilver import App, Settings, Signal, Theme
from pysilver.motion import DURATION, EASING, Animation, Ticker, curve, duration
from pysilver.motion.animation import MAX_FRAME_DELTA
from pysilver.paint import DisplayList

# --------------------------------------------------------------- easing


@pytest.mark.parametrize("name", sorted(EASING))
def test_every_curve_is_anchored_at_both_ends(name: str) -> None:
    f = EASING[name]
    assert f(0.0) == pytest.approx(0.0, abs=1e-6)
    assert f(1.0) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("name", sorted(EASING))
def test_every_curve_is_monotonic(name: str) -> None:
    """None of M3's easing curves overshoot, so progress never goes backwards."""
    f = EASING[name]
    values = [f(i / 200) for i in range(201)]
    assert all(b >= a - 1e-9 for a, b in itertools.pairwise(values))


@pytest.mark.parametrize("name", sorted(EASING))
def test_every_curve_is_clamped_outside_the_unit_range(name: str) -> None:
    f = EASING[name]
    assert f(-1.0) == 0.0
    assert f(2.0) == 1.0


def test_emphasized_is_a_two_segment_path_not_a_cubic() -> None:
    """M3 gives `emphasized` as `M 0,0 C ... 0.166666,0.4 C ... 1,1`, and its
    own CSS row says N/A because cubic-bezier() cannot express two segments.
    The join must land exactly on the control point the spec states.
    """
    assert EASING["emphasized"](0.166666) == pytest.approx(0.4, abs=1e-4)


def test_accelerate_and_decelerate_are_the_right_way_round() -> None:
    """A decelerate curve covers most of its distance early; accelerate late."""
    for family in ("standard", "emphasized"):
        assert EASING[f"{family}_decelerate"](0.25) > 0.5
        assert EASING[f"{family}_accelerate"](0.25) < 0.25


def test_the_duration_tokens_are_the_m3_values_in_seconds() -> None:
    """The spec states milliseconds; the conversion happens once, in easing.py."""
    assert DURATION["short4"] == 0.200
    assert DURATION["medium4"] == 0.400
    assert DURATION["long4"] == 0.600
    assert DURATION["extra_long4"] == 1.000
    assert len(DURATION) == 16


def test_resolving_an_unknown_name_names_the_alternatives() -> None:
    with pytest.raises(KeyError, match="unknown easing"):
        curve("swoosh")
    with pytest.raises(KeyError, match="unknown duration token"):
        duration("ages")


def test_a_raw_number_or_callable_passes_through() -> None:
    """An application may supply its own timing without the framework knowing."""
    assert duration(0.35) == 0.35
    assert curve(lambda t: t)(0.5) == 0.5


# ------------------------------------------------------------ animation


def test_an_animation_interpolates_between_its_endpoints() -> None:
    a = Animation(0.0, 100.0, duration=1.0, curve="linear")
    assert a.value == 0.0
    a.advance(0.5)
    assert a.value == pytest.approx(50.0)
    a.advance(0.5)
    assert a.value == pytest.approx(100.0)
    assert a.done


def test_advance_reports_when_it_has_finished() -> None:
    a = Animation(0.0, 1.0, duration=0.1, curve="linear")
    assert a.advance(0.05) is True
    assert a.advance(0.05) is False


def test_retargeting_continues_from_the_current_value() -> None:
    """M3 interruptions glide. Restarting from the original start would make a
    switch toggled twice snap backwards before setting off again."""
    a = Animation(0.0, 1.0, duration=1.0, curve="linear")
    a.advance(0.5)
    midpoint = a.value
    a.retarget(0.0)
    assert a.start == pytest.approx(midpoint)
    assert a.value == pytest.approx(midpoint), "the value jumped on retarget"
    a.advance(1.0)
    assert a.value == pytest.approx(0.0)


def test_retargeting_to_the_same_end_is_a_no_op() -> None:
    a = Animation(0.0, 1.0, duration=1.0, curve="linear")
    a.advance(0.5)
    a.retarget(1.0)
    assert a.progress == pytest.approx(0.5), "an identical retarget restarted the clock"


def test_a_repeating_animation_wraps_instead_of_finishing() -> None:
    a = Animation(0.0, 1.0, duration=1.0, curve="linear", repeat=True)
    a.advance(0.75)
    assert a.value == pytest.approx(0.75)
    a.advance(0.5)  # past the end
    assert a.value == pytest.approx(0.25)
    assert not a.done


def test_a_zero_duration_animation_is_already_finished() -> None:
    a = Animation(0.0, 1.0, duration=0.0)
    assert a.done and a.value == 1.0


def test_on_change_fires_only_when_the_value_moves() -> None:
    calls: list[int] = []
    a = Animation(0.0, 1.0, duration=1.0, curve="linear", on_change=lambda: calls.append(1))
    a.advance(0.5)
    assert len(calls) == 1
    a.advance(0.0)
    assert len(calls) == 1, "a zero-length frame repainted"


# --------------------------------------------------------------- ticker


def test_the_ticker_drops_animations_as_they_land() -> None:
    ticker = Ticker()
    ticker.add(Animation(0.0, 1.0, duration=0.1, curve="linear"))
    assert ticker.active
    ticker.tick(0.05)
    assert ticker.active
    ticker.tick(0.05)
    assert not ticker.active, "a finished animation is still asking for frames"


def test_a_huge_frame_delta_is_clamped() -> None:
    """A debugger pause or a dragged window must not teleport every animation
    to its end; losing time is the failure nobody notices."""
    ticker = Ticker()
    a = ticker.add(Animation(0.0, 1.0, duration=1.0, curve="linear"))
    ticker.tick(30.0)
    assert a.value == pytest.approx(MAX_FRAME_DELTA)


def test_adding_the_same_animation_twice_runs_it_once() -> None:
    ticker = Ticker()
    a = Animation(0.0, 1.0, duration=1.0)
    ticker.add(a)
    ticker.add(a)
    assert ticker.count == 1


def test_reduce_motion_settles_immediately_and_never_asks_for_a_frame() -> None:
    """The animation still runs and still ends where it should -- widget code
    needs no branch, so it cannot forget the case."""
    ticker = Ticker(reduce_motion=True)
    a = ticker.add(Animation(0.0, 1.0, duration=10.0))
    assert a.value == 1.0
    assert not ticker.active


# -------------------------------------------------- element integration


def element(**spec):
    from pysilver.spec import parse_view
    from pysilver.widgets import build_element

    return build_element(parse_view({"name": "w", "widget": "Container", **spec}).root)


def test_the_first_call_settles_on_its_target_at_once() -> None:
    """There is nothing to animate *from* on the first frame."""
    e = element()
    e.set_ticker(Ticker())
    assert e.animated("x", 42.0) == 42.0
    assert not e.ticker.active


def test_a_changed_target_animates_rather_than_jumping() -> None:
    e = element()
    ticker = Ticker()
    e.set_ticker(ticker)
    e.animated("x", 0.0)
    assert e.animated("x", 100.0) == 0.0, "the value jumped straight to the target"
    assert ticker.active
    # A single huge tick is clamped to MAX_FRAME_DELTA by design, so advance
    # the way a real frame loop would.
    for _ in range(5):
        ticker.tick(0.05)
    assert e.animated("x", 100.0) == pytest.approx(100.0)


def test_animating_marks_paint_and_not_layout() -> None:
    """Animation runs every frame; marking layout would relayout at 60Hz."""
    from pysilver.layout import Constraints, Size

    e = element()
    ticker = Ticker()
    e.set_ticker(ticker)
    e.layout(Constraints.loose(Size(100, 100)))  # settle layout first
    assert not e.needs_layout

    e.animated("x", 0.0)
    e.animated("x", 1.0)
    e._needs_paint = False
    ticker.tick(0.05)
    assert e.needs_paint
    assert not e.needs_layout


def test_an_invalid_invalidates_argument_is_rejected() -> None:
    e = element()
    e.set_ticker(Ticker())
    with pytest.raises(ValueError, match="invalidates"):
        e.animated("x", 1.0, invalidates="repaint")


def test_animations_survive_a_spec_update() -> None:
    """They are runtime state, so a hot reload must not restart a transition
    that is mid-flight."""
    from pysilver.spec import parse_view

    e = element()
    e.set_ticker(Ticker())
    e.animated("x", 0.0)
    e.animated("x", 100.0)
    e.ticker.tick(0.1)
    mid = e.animation("x").value
    e.update_spec(parse_view({"name": "w", "widget": "Container"}).root)
    assert e.animation("x") is not None
    assert e.animation("x").value == pytest.approx(mid)


# ------------------------------------------------------ app integration


def hosted(children, *, signals: dict | None = None, **settings) -> App:
    app = App(
        {
            "root": {
                "name": "root",
                "widget": "Vertical",
                "style": {"background": "surface", "width": 300},
                "children": children,
            }
        },
        theme=Theme(dark=True),
        settings=Settings(width=320, height=240, **settings),
    )
    app.expose(**(signals or {}))
    app.mount()
    app.update()
    app.paint(DisplayList())
    return app


def test_an_app_with_nothing_animating_stays_idle() -> None:
    """The property the whole design protects: an idle app renders no frames."""
    app = hosted(
        [
            {"name": "p", "widget": "LinearProgress", "value": "0.5", "style": {"width": "expand"}},
            {"name": "c", "widget": "CircularProgress", "value": "0.5"},
            {"name": "s", "widget": "Switch", "value": "false"},
        ]
    )
    assert not app.motion.active


def test_an_indeterminate_indicator_keeps_asking_for_frames() -> None:
    """It has to -- that is what makes it move."""
    app = hosted([{"name": "p", "widget": "LinearProgress", "style": {"width": "expand"}}])
    assert app.motion.active


def test_omitting_value_is_what_selects_indeterminate() -> None:
    app = hosted(
        [
            {"name": "i", "widget": "LinearProgress", "style": {"width": "expand"}},
            {"name": "d", "widget": "LinearProgress", "value": "0", "style": {"width": "expand"}},
        ]
    )
    assert app.root.find("i").indeterminate
    assert not app.root.find("d").indeterminate, "value 0 is a value, not an absence"


def _polygon_params(app: App) -> tuple[float, float, float, float]:
    from pysilver.paint.display_list import Kind

    dl = DisplayList()
    app.paint(dl)
    poly = next(i for i in dl.view if i["flags"][0] == Kind.POLYGON)
    border_w, sides, rotation, radius = poly["params"]
    return float(border_w), float(sides), float(rotation), float(radius)


def test_a_plain_shape_stays_idle() -> None:
    """No `spin:`/`morph:` -- nothing should keep asking for frames."""
    app = hosted([{"name": "s", "widget": "Shape", "style": {"sides": 4}}])
    assert not app.motion.active


def test_spin_keeps_asking_for_frames() -> None:
    app = hosted([{"name": "s", "widget": "Shape", "style": {"spin": True}}])
    assert app.motion.active


def test_morph_keeps_asking_for_frames() -> None:
    app = hosted([{"name": "s", "widget": "Shape", "style": {"morph": True}}])
    assert app.motion.active


def test_spin_rotates_the_shape_continuously() -> None:
    app = hosted([{"name": "s", "widget": "Shape", "style": {"sides": 4, "spin": True}}])
    _, _, start_rotation, _ = _polygon_params(app)
    # Close to 0 (a repeat=True animation starts there), not exactly -- real
    # wall-clock time already elapsed inside hosted()'s own mount()/update().
    assert abs(start_rotation) < 0.05, "a repeat=True animation starts near 0, not the target"

    app.motion.tick(0.5)
    _, _, mid_rotation, _ = _polygon_params(app)
    assert mid_rotation > start_rotation, "spin: true must actually move rotation over time"


def test_morph_oscillates_sides_within_its_range() -> None:
    app = hosted([{"name": "s", "widget": "Shape", "style": {"sides": 3, "morph": True}}])
    from pysilver.widgets.material import ShapeElement

    _, start_sides, _, _ = _polygon_params(app)
    assert start_sides == pytest.approx(3.0, abs=0.05), (
        "phase 0 is the declared sides:, not the peak"
    )

    app.motion.tick(0.5)
    _, mid_sides, _, _ = _polygon_params(app)
    assert mid_sides > start_sides, "morph: true must actually move sides over time"
    assert mid_sides <= 3.0 + ShapeElement.MORPH_RANGE + 1e-6, "must not overshoot its own range"


def test_a_switch_slides_instead_of_jumping() -> None:
    on = Signal(False)
    app = hosted([{"name": "s", "widget": "Switch", "value": "{{ on.get() }}"}], signals={"on": on})
    sw = app.root.find("s")
    assert sw.animation("thumb_pos").value == 0.0

    on.set(True)
    app.update()
    app.paint(DisplayList())
    assert sw.animation("thumb_pos").value == 0.0, "it jumped"
    assert app.motion.active

    app.motion.tick(0.1)
    midway = sw.animation("thumb_pos").value
    assert 0.0 < midway < 1.0
    app.motion.tick(0.2)
    assert sw.animation("thumb_pos").value == pytest.approx(1.0)
    assert not app.motion.active, "the switch kept rendering after arriving"


def test_reduce_motion_reaches_the_same_end_state() -> None:
    on = Signal(False)
    app = hosted(
        [{"name": "s", "widget": "Switch", "value": "{{ on.get() }}"}],
        signals={"on": on},
        reduce_motion=True,
    )
    on.set(True)
    app.update()
    app.paint(DisplayList())
    assert app.root.find("s").animation("thumb_pos").value == 1.0
    assert not app.motion.active


def test_the_frame_delta_is_measured_once_per_frame() -> None:
    """Sampled per caller instead, layout and paint would disagree about where
    a moving thing is within a single frame."""
    app = hosted([{"name": "p", "widget": "LinearProgress", "style": {"width": "expand"}}])
    times = iter([1.0, 1.4])
    app.clock = lambda: next(times)
    app._last_tick = None
    assert app._frame_delta() == 0.0, "the first frame has nothing to measure against"
    assert app._frame_delta() == pytest.approx(0.4)
