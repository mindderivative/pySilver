"""Disabled state: inert to input, excluded from focus, recoloured by M3's rule.

M3 states the treatment outright -- "Disabled: Container opacity 12% (0.12),
Content opacity 38% (0.38)" -- and it is a *replacement* with the `on_surface`
role, not a fade of the control's own colours.
"""

from __future__ import annotations

import pytest

from pysilver import App, Settings, Signal, Theme
from pysilver.paint import NO_TOKEN, DisplayList, Kind
from pysilver.spec import parse_view
from pysilver.theme import Palette
from pysilver.tree.element import DISABLED_CONTAINER, DISABLED_CONTENT
from pysilver.widgets import build_element

PALETTE = Palette(Theme(dark=True))
ON_SURFACE = PALETTE.index("on_surface")


def hosted(children, **signals):
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
        settings=Settings(width=240, height=240),
    )
    app.expose(**signals)
    return app


def painted(app: App) -> list:
    dl = DisplayList()
    app.paint(dl)
    return list(dl.view)[1:]  # drop the root's own surface


# ------------------------------------------------------------------ state


def test_disabled_is_a_node_field_not_a_style() -> None:
    """It changes what a control *is*, not how a view chooses to paint it."""
    spec = parse_view({"name": "b", "widget": "Button", "disabled": "true"}).root
    assert spec.disabled == "true"
    assert not hasattr(spec.style, "disabled")


def test_it_defaults_to_enabled() -> None:
    element = build_element(parse_view({"name": "b", "widget": "Button"}).root)
    assert not element.disabled
    assert not element.effective_disabled


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("", False),
    ],
)
def test_the_flag_parses_like_the_other_bindings(value: str, expected: bool) -> None:
    element = build_element(parse_view({"name": "b", "widget": "Button", "disabled": value}).root)
    assert element.disabled is expected


def test_it_tracks_a_signal() -> None:
    valid = Signal(False)
    app = hosted(
        [
            {
                "name": "b",
                "widget": "Button",
                "text": "Save",
                "disabled": "{{ not valid.get() }}",
                "style": {"width": 100, "height": 40},
            }
        ],
        valid=valid,
    )
    app.mount()
    app.paint(DisplayList())
    assert app.root.find("b").disabled

    valid.set(True)
    app.paint(DisplayList())
    assert not app.root.find("b").disabled


def test_disabling_a_container_disables_what_is_inside_it() -> None:
    """The case people actually reach for: greying out a form section."""
    app = hosted(
        [
            {
                "name": "section",
                "widget": "Vertical",
                "disabled": "true",
                "children": [
                    {
                        "name": "b",
                        "widget": "Button",
                        "text": "Go",
                        "style": {"width": 80, "height": 40},
                    },
                    {"name": "c", "widget": "Checkbox"},
                ],
            }
        ]
    )
    app.mount()
    for name in ("b", "c"):
        child = app.root.find(name)
        assert not child.disabled, "the child was not marked directly"
        assert child.effective_disabled, "it did not inherit from the container"


def test_an_enabled_child_of_a_disabled_parent_stays_disabled() -> None:
    """Inheritance is not overridable; a disabled section means disabled."""
    app = hosted(
        [
            {
                "name": "section",
                "widget": "Vertical",
                "disabled": "true",
                "children": [
                    {
                        "name": "b",
                        "widget": "Button",
                        "disabled": "false",
                        "style": {"width": 80, "height": 40},
                    }
                ],
            }
        ]
    )
    app.mount()
    assert app.root.find("b").effective_disabled


# ------------------------------------------------------------------ input


def two_buttons() -> App:
    return hosted(
        [
            {
                "name": "on",
                "widget": "Button",
                "text": "On",
                "style": {"width": 100, "height": 40},
                "handlers": {"on_click": "hit"},
            },
            {
                "name": "off",
                "widget": "Button",
                "text": "Off",
                "disabled": "true",
                "style": {"width": 100, "height": 40},
                "handlers": {"on_click": "hit"},
            },
        ]
    )


def test_a_disabled_control_ignores_clicks() -> None:
    from pysilver.runtime.events import EventType, PointerEvent

    app = two_buttons()
    hits: list[int] = []

    @app.handler
    def hit(event) -> None:
        hits.append(1)

    app.mount()
    app.paint(DisplayList())

    def click(y: float) -> None:
        for kind in (EventType.POINTER_DOWN, EventType.POINTER_UP):
            app.dispatcher.post(PointerEvent(kind, x=50, y=y))
        app.dispatcher.drain()

    click(20)
    assert len(hits) == 1
    click(60)
    assert len(hits) == 1, "the disabled button fired its handler"


def test_a_disabled_control_does_not_hover() -> None:
    from pysilver.runtime.events import EventType, PointerEvent

    app = two_buttons()

    @app.handler
    def hit(event) -> None: ...

    app.mount()
    app.paint(DisplayList())
    app.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=50, y=60))
    app.dispatcher.drain()
    assert not app.root.find("off").state.hovered


def test_a_disabled_control_is_skipped_by_tab() -> None:
    """Leaving it focusable would let the keyboard reach what the mouse cannot,
    which is the accessibility failure the state exists to avoid."""
    app = two_buttons()

    @app.handler
    def hit(event) -> None: ...

    app.mount()
    assert [e.name for e in app.dispatcher.focus_order()] == ["on"]


def test_an_enabled_ancestor_still_receives_the_event() -> None:
    """The hit path is truncated at the disabled element, not discarded --
    a disabled control inside a clickable card must not swallow the card."""
    from pysilver.runtime.events import EventType, PointerEvent

    app = hosted(
        [
            {
                "name": "card",
                "widget": "Container",
                "style": {"width": 200, "height": 80, "background": "surface_container"},
                "handlers": {"on_click": "outer"},
                "children": [
                    {
                        "name": "inner",
                        "widget": "Button",
                        "text": "No",
                        "disabled": "true",
                        "style": {"width": 100, "height": 40},
                    }
                ],
            }
        ]
    )
    fired: list[str] = []

    @app.handler
    def outer(event) -> None:
        fired.append("card")

    app.mount()
    app.paint(DisplayList())
    for kind in (EventType.POINTER_DOWN, EventType.POINTER_UP):
        app.dispatcher.post(PointerEvent(kind, x=50, y=20))
    app.dispatcher.drain()
    assert fired == ["card"]


# ---------------------------------------------------------------- painting


def test_the_container_takes_on_surface_at_12_percent() -> None:
    app = hosted(
        [
            {
                "name": "b",
                "widget": "Button",
                "text": "Save",
                "disabled": "true",
                "style": {"width": 120, "height": 40, "variant": "filled"},
            }
        ]
    )
    app.mount()
    container = next(
        s
        for s in painted(app)
        if int(s["flags"][0]) == int(Kind.BOX) and float(s["rect"][2]) == 120.0
    )
    assert int(container["flags"][2]) == ON_SURFACE
    assert float(container["fill"][3]) == pytest.approx(DISABLED_CONTAINER, abs=1e-6)


def test_the_content_takes_on_surface_at_38_percent() -> None:
    app = hosted(
        [
            {
                "name": "b",
                "widget": "Button",
                "text": "Save",
                "disabled": "true",
                "style": {"width": 120, "height": 40, "variant": "filled"},
            }
        ]
    )
    app.mount()
    glyphs = [s for s in painted(app) if int(s["flags"][0]) == int(Kind.GLYPH)]
    assert glyphs, "the label was not drawn"
    for glyph in glyphs:
        assert int(glyph["flags"][2]) == ON_SURFACE
        assert float(glyph["fill"][3]) == pytest.approx(DISABLED_CONTENT, abs=1e-6)


def test_content_drawn_as_a_box_still_gets_the_content_opacity() -> None:
    """A radio's dot and a switch's thumb are content that happens to be a box.
    At 12% they would be all but invisible, so the container is identified by
    covering the element's own bounds rather than by being a box."""
    app = hosted(
        [
            {"name": "r", "widget": "Radio", "value": "true", "disabled": "true"},
            {"name": "s", "widget": "Switch", "value": "true", "disabled": "true"},
        ]
    )
    app.mount()
    boxes = [s for s in painted(app) if int(s["flags"][0]) == int(Kind.BOX)]
    by_size = {round(float(s["rect"][2])): float(s["fill"][3]) for s in boxes}
    assert by_size[20] == pytest.approx(DISABLED_CONTAINER, abs=1e-6)  # radio ring
    assert by_size[10] == pytest.approx(DISABLED_CONTENT, abs=1e-6)  # radio dot
    assert by_size[52] == pytest.approx(DISABLED_CONTAINER, abs=1e-6)  # switch track
    assert by_size[24] == pytest.approx(DISABLED_CONTENT, abs=1e-6)  # switch thumb


def test_every_instance_is_recoloured_not_faded() -> None:
    """M3 replaces a disabled control's colours with `on_surface`; it does not
    dim whatever colour the control had."""
    app = hosted(
        [
            {
                "name": "b",
                "widget": "Button",
                "text": "Save",
                "disabled": "true",
                "style": {"width": 120, "height": 40, "variant": "filled"},
            }
        ]
    )
    app.mount()
    for instance in painted(app):
        assert int(instance["flags"][2]) == ON_SURFACE
        assert int(instance["flags"][2]) != NO_TOKEN


def test_a_disabled_subtree_is_recoloured_once() -> None:
    """Nested disabled flags must not compound into a darker result."""
    outer = hosted(
        [
            {
                "name": "section",
                "widget": "Vertical",
                "disabled": "true",
                "children": [
                    {
                        "name": "b",
                        "widget": "Button",
                        "text": "Go",
                        "disabled": "true",
                        "style": {"width": 100, "height": 40},
                    }
                ],
            }
        ]
    )
    outer.mount()
    alphas = {round(float(s["fill"][3]), 4) for s in painted(outer)}
    assert alphas <= {round(DISABLED_CONTAINER, 4), round(DISABLED_CONTENT, 4)}


def test_an_enabled_control_is_untouched() -> None:
    app = hosted(
        [
            {
                "name": "b",
                "widget": "Button",
                "text": "Save",
                "style": {"width": 120, "height": 40, "variant": "filled"},
            }
        ]
    )
    app.mount()
    container = next(
        s
        for s in painted(app)
        if int(s["flags"][0]) == int(Kind.BOX) and float(s["rect"][2]) == 120.0
    )
    assert int(container["flags"][2]) != ON_SURFACE
    assert float(container["fill"][3]) == pytest.approx(1.0)
