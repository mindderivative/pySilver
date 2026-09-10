"""Material Symbols icons: an icon is a glyph, so it reuses the text pipeline."""

from __future__ import annotations

import pytest

from pysilver import App, Signal, Theme
from pysilver.paint import DisplayList, Kind
from pysilver.text import TextEngine
from pysilver.text.icons import DEFAULT_ICON_SIZE, IconSet


@pytest.fixture(scope="module")
def icons() -> IconSet:
    return IconSet.bundled()


@pytest.fixture
def engine() -> TextEngine:
    return TextEngine()


# ------------------------------------------------------------------ the set


def test_bundled_set_is_loaded(icons: IconSet) -> None:
    assert len(icons) >= 200
    assert "home" in icons and "settings" in icons


def test_covers_the_m3_component_icons(icons: IconSet) -> None:
    """Each of these is required by a component in the M3 catalogue."""
    required = [
        "add",
        "edit",  # FAB
        "menu",
        "close",
        "arrow_back",
        "more_vert",  # app bars
        "home",
        "search",
        "settings",
        "person",  # navigation
        "check",
        "check_box",
        "check_box_outline_blank",  # selection
        "radio_button_checked",
        "radio_button_unchecked",
        "star",
        "favorite",
        "delete",
        "share",  # actions
        "expand_more",
        "chevron_right",  # menus, lists
    ]
    missing = [n for n in required if n not in icons]
    assert not missing, f"bundled subset is missing {missing}"


def test_unknown_icon_raises_with_a_useful_message(icons: IconSet) -> None:
    """A typo'd icon must be loud, not a silent .notdef box."""
    with pytest.raises(KeyError, match="unknown icon"):
        icons.glyph("definitely_not_an_icon")


def test_names_are_sorted(icons: IconSet) -> None:
    """`.names` sorts regardless of the underlying dict's insertion order --
    asserting `icons.names == sorted(icons.names)` against the bundled set
    alone is tautological (`names` always returns `sorted(...)`, and the
    bundled JSON already happens to be alphabetical), so this constructs an
    out-of-order set directly to make the property earn the assertion."""
    unordered = IconSet(icons.face, {"zebra": 1, "apple": 2, "mango": 3})
    assert unordered.names == ["apple", "mango", "zebra"]


# --------------------------------------------------------------- the axes


def test_font_exposes_fill_and_weight(icons: IconSet) -> None:
    """GRAD and opsz are pinned out; these two are kept live."""
    assert set(icons.face.axes) == {"FILL", "wght"}
    assert icons.face.is_variable


def test_fill_axis_changes_the_raster(icons: IconSet) -> None:
    """FILL 0->1 is M3's selected/unselected transition, so it must actually
    change the glyph."""
    gid = icons.glyph("favorite")
    outlined = icons.face.rasterize(gid, 48.0, 0, icons.coords(fill=0.0))
    filled = icons.face.rasterize(gid, 48.0, 0, icons.coords(fill=1.0))
    assert int(filled.coverage.sum()) > int(outlined.coverage.sum()) * 1.2


def test_weight_axis_changes_the_raster(icons: IconSet) -> None:
    gid = icons.glyph("favorite")
    light = icons.face.rasterize(gid, 48.0, 0, icons.coords(weight=200))
    heavy = icons.face.rasterize(gid, 48.0, 0, icons.coords(weight=700))
    assert int(heavy.coverage.sum()) > int(light.coverage.sum())


def test_axis_values_are_clamped(icons: IconSet) -> None:
    assert icons.coords(fill=5.0)[0] == 1.0
    assert icons.coords(fill=-1.0)[0] == 0.0
    assert icons.coords(weight=9000)[1] == 700.0
    assert icons.coords(weight=-50)[1] == 100.0


def test_light_weights_are_lifted_at_standard_size(icons: IconSet) -> None:
    """M3: don't use the lightest weight for 24dp icons; minimum is 200."""
    assert icons.suggested_weight(DEFAULT_ICON_SIZE, 100) == 200.0
    assert icons.suggested_weight(48.0, 100) == 100.0


# ------------------------------------------------------------- rendering


def test_icons_emit_glyph_instances(engine: TextEngine) -> None:
    """An icon costs no extra draw call -- it is a glyph like any other."""
    dl = DisplayList()
    assert engine.emit_icon(dl, "home", x=0, y=0)
    assert len(dl) == 1
    assert dl.view[0]["flags"][0] == Kind.GLYPH


def test_fill_variants_are_separate_atlas_entries(engine: TextEngine) -> None:
    """Same glyph, same size -- they would collide if FILL were not in the key."""
    dl = DisplayList()
    engine.emit_icon(dl, "favorite", x=0, y=0, fill=0.0)
    before = len(engine.atlas)
    engine.emit_icon(dl, "favorite", x=0, y=0, fill=1.0)
    assert len(engine.atlas) == before + 1


def test_weight_variants_are_separate_atlas_entries(engine: TextEngine) -> None:
    """Same glyph, same size -- they would collide if wght were not in the
    key either (the FILL case above covers only one of the two live axes).
    Rendered at 48dp, above `DEFAULT_ICON_SIZE`, so the M3 minimum-weight
    lift in `suggested_weight` doesn't mask the two requested weights into
    the same coordinate."""
    dl = DisplayList()
    engine.emit_icon(dl, "favorite", x=0, y=0, size=48, weight=200)
    before = len(engine.atlas)
    engine.emit_icon(dl, "favorite", x=0, y=0, size=48, weight=700)
    assert len(engine.atlas) == before + 1


def test_repeat_icons_reuse_the_atlas(engine: TextEngine) -> None:
    dl = DisplayList()
    for _ in range(5):
        engine.emit_icon(dl, "home", x=0, y=0)
    assert len(engine.atlas) == 1
    assert len(dl) == 5


def test_larger_icons_rasterise_larger(engine: TextEngine) -> None:
    dl = DisplayList()
    engine.emit_icon(dl, "home", x=0, y=0, size=16)
    engine.emit_icon(dl, "home", x=0, y=0, size=48)
    assert dl.view[1]["rect"][2] > dl.view[0]["rect"][2]


def test_icon_font_is_loaded_lazily() -> None:
    """An app with no icons should not pay for the font."""
    e = TextEngine()
    assert e._icons is None
    _ = e.icons
    assert e._icons is not None


# ---------------------------------------------------------------- widget


ICON_VIEW = {
    "name": "root",
    "widget": "Horizontal",
    "style": {"background": "surface", "padding": 8, "spacing": 8, "height": 48},
    "children": [
        {
            "name": "a",
            "widget": "Icon",
            "icon": "home",
            "style": {"color": "on_surface", "icon_size": 24},
        },
        {
            "name": "b",
            "widget": "Icon",
            "icon": "{{ 'star' if on.get() else 'star_border' }}",
            "style": {"color": "primary", "icon_size": 32},
        },
    ],
}


def make_app():
    app = App(ICON_VIEW, theme=Theme(dark=True))
    on = Signal(False)
    app.expose(on=on)
    app.mount()
    return app, on


def test_icon_widget_sizes_to_icon_size() -> None:
    app, _ = make_app()
    app.update()
    assert app.root.find("a").size.width == 24
    assert app.root.find("b").size.width == 32


def test_icon_widget_paints() -> None:
    app, _ = make_app()
    dl = DisplayList()
    app.paint(dl)
    assert sum(1 for s in dl.view if s["flags"][0] == Kind.GLYPH) == 2


def test_icon_name_is_bindable() -> None:
    """`icon:` carries the name, so an icon switches with state like a label."""
    app, on = make_app()
    assert app.root.find("b").icon == "star_border"
    on.set(True)
    assert app.root.find("b").icon == "star"


def test_unknown_icon_in_a_view_is_reported() -> None:
    bad = {
        **ICON_VIEW,
        "children": [
            {
                "name": "x",
                "widget": "Icon",
                "icon": "nope_not_real",
                "style": {"color": "on_surface"},
            }
        ],
    }
    app = App(bad, theme=Theme(dark=True))
    app.mount()
    with pytest.raises(KeyError, match="unknown icon"):
        app.paint(DisplayList())


def test_icon_kind_is_in_the_spec_vocabulary() -> None:
    from pysilver.spec import WidgetKind

    assert WidgetKind.ICON.value == "Icon"
