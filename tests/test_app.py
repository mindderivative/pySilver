"""End-to-end: view -> elements -> layout -> paint -> click -> signal -> repaint."""

from __future__ import annotations

import pytest

from pysilver import App, Signal, SpecError, Theme
from pysilver.layout import Offset
from pysilver.paint import DisplayList, Kind
from pysilver.runtime.events import EventType, PointerEvent

VIEW = {
    "name": "root",
    "widget": "Vertical",
    "style": {"padding": 16, "spacing": 12, "background": "surface"},
    "children": [
        {
            "name": "card",
            "widget": "Container",
            "style": {
                "width": 300,
                "height": 80,
                "background": "surface_container_high",
                "corner_radius": 16,
            },
        },
        {
            "name": "btn",
            "widget": "Button",
            "style": {
                "width": 200,
                "height": 48,
                "background": "primary",
                "corner_radius": 24,
                "color": "on_primary",
            },
            "text": "Clicked {{ count.get() }}x",
            "handlers": {"on_click": "increment"},
        },
    ],
}


@pytest.fixture
def app():
    a = App(VIEW, theme=Theme(dark=True))
    count = Signal(0)
    a.expose(count=count)

    @a.handler
    def increment(event):
        count.update(lambda n: n + 1)

    a.mount()
    a.count = count  # type: ignore[attr-defined]
    return a


def click(app, element) -> None:
    app.update()  # hit testing needs laid-out geometry
    r = element.absolute_rect()
    x, y = r.x + r.width / 2, r.y + r.height / 2
    app.dispatcher.post(PointerEvent(EventType.POINTER_DOWN, x=x, y=y))
    app.dispatcher.post(PointerEvent(EventType.POINTER_UP, x=x, y=y))
    app.dispatcher.drain()


# ------------------------------------------------------------------ wiring


def test_view_builds_an_element_tree(app) -> None:
    assert [e.name for e in app.root.walk_elements()] == ["root", "card", "btn"]


def test_layout_applies_padding_and_spacing(app) -> None:
    app.update()
    assert app.root.find("card").offset == Offset(16, 16)
    assert app.root.find("btn").offset.y == 16 + 80 + 12


def test_unregistered_handler_fails_at_mount() -> None:
    bad = {
        **VIEW,
        "children": [{"name": "x", "widget": "Button", "handlers": {"on_click": "nonexistent"}}],
    }
    with pytest.raises(SpecError, match="not registered"):
        App(bad).mount()


# ------------------------------------------------------------------- paint


def test_paint_emits_instances(app) -> None:
    dl = DisplayList()
    app.paint(dl)
    assert len(dl) > 0
    kinds = set(dl.view["flags"][:, 0].tolist())
    assert kinds <= {Kind.BOX, Kind.SHADOW, Kind.GLYPH}


def test_paint_emits_real_glyphs_for_the_button_label(app) -> None:
    """The button's label is shaped text, not boxes standing in for it."""
    dl = DisplayList()
    app.paint(dl)
    glyphs = [i for i in dl.view if i["flags"][0] == Kind.GLYPH]
    assert glyphs, "no glyph instances emitted"
    # Every glyph samples a real sub-rectangle of the atlas.
    for g in glyphs:
        u0, v0, u1, v1 = g["uv"]
        assert 0.0 <= u0 < u1 <= 1.0 and 0.0 <= v0 < v1 <= 1.0


def test_paint_order_is_parent_then_children(app) -> None:
    dl = DisplayList()
    app.paint(dl)
    # root background is emitted before the card that sits on top of it
    assert dl.view[0]["rect"][2] > dl.view[1]["rect"][2]


def test_background_uses_a_palette_token_not_a_literal(app) -> None:
    """Token indirection is what makes a theme switch one buffer upload."""
    dl = DisplayList()
    app.paint(dl)
    assert dl.view[0]["flags"][2] == app.palette.index("surface")


def test_clean_repaint_is_stable(app) -> None:
    first, second = DisplayList(), DisplayList()
    app.paint(first)
    app.paint(second)
    assert len(first) == len(second)


# -------------------------------------------------------------- interaction


def test_click_runs_the_handler_and_updates_the_signal(app) -> None:
    click(app, app.root.find("btn"))
    assert app.count.peek() == 1


def test_binding_re_renders_the_label(app) -> None:
    btn = app.root.find("btn")
    assert btn.text == "Clicked 0x"
    click(app, btn)
    assert btn.text == "Clicked 1x"


def test_click_focuses_the_button(app) -> None:
    click(app, app.root.find("btn"))
    assert app.dispatcher.focused.name == "btn"


def test_clicking_the_card_does_not_run_the_button_handler(app) -> None:
    click(app, app.root.find("card"))
    assert app.count.peek() == 0


def test_signal_change_marks_only_the_bound_element_dirty(app) -> None:
    """Fine-grained invalidation: the card must not be dirtied by the label."""
    dl = DisplayList()
    app.paint(dl)
    card, btn = app.root.find("card"), app.root.find("btn")
    assert not card.needs_paint and not btn.needs_paint

    app.count.set(5)
    assert btn.needs_paint, "bound element was not invalidated"
    assert not card.needs_paint, "an unrelated sibling was invalidated"


def test_hover_marks_the_button_for_repaint_only(app) -> None:
    dl = DisplayList()
    app.paint(dl)
    app.dispatcher.post(PointerEvent(EventType.POINTER_MOVE, x=100, y=130))
    app.dispatcher.drain()
    btn = app.root.find("btn")
    assert btn.state.hovered
    assert btn.needs_paint
    assert not btn.needs_layout, "a hover should never trigger layout"


# ------------------------------------------------------------- hot reload


def test_reload_preserves_state_and_reuses_elements(app) -> None:
    btn = app.root.find("btn")
    click(app, btn)
    btn.state.data["draft"] = "keep me"

    recoloured = {
        **VIEW,
        "children": [
            {
                **VIEW["children"][0],
                "style": {**VIEW["children"][0]["style"], "background": "error"},
            },
            VIEW["children"][1],
        ],
    }
    stats = app.reload(recoloured)

    assert app.root.find("btn") is btn
    assert btn.state.data["draft"] == "keep me"
    assert app.count.peek() == 1
    assert stats.created == 0 and stats.disposed == 0
    assert stats.skipped >= 1, "unchanged subtree was not skipped"


def test_reload_applies_the_new_style(app) -> None:
    recoloured = {
        **VIEW,
        "children": [
            {
                **VIEW["children"][0],
                "style": {**VIEW["children"][0]["style"], "background": "error"},
            },
            VIEW["children"][1],
        ],
    }
    app.reload(recoloured)
    dl = DisplayList()
    app.paint(dl)
    tokens = set(dl.view["flags"][:, 2].tolist())
    assert app.palette.index("error") in tokens


def test_reload_keeps_bindings_live(app) -> None:
    app.reload(VIEW)
    btn = app.root.find("btn")
    click(app, btn)
    assert btn.text == "Clicked 1x"


# ------------------------------------------------------------------ theme


def test_theme_switch_does_not_dirty_layout(app) -> None:
    app.update()
    app.set_theme(Theme(dark=False))
    assert not app.root.needs_layout, "a theme change must not trigger relayout"
    assert app.palette.dirty, "palette should need re-upload"
