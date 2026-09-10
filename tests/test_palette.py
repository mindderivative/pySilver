"""Palette correctness -- above all the sRGB/linear boundary (ARCHITECTURE.md 5.6.1)."""

from __future__ import annotations

import numpy as np
import pytest
from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot

from pysilver.theme import TOKEN_COUNT, Palette, Theme, parse_hex, srgb_to_linear


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    """Inverse of srgb_to_linear -- models what an ``*-srgb`` target does on write."""
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


# ------------------------------------------------------------------ conversion


@pytest.mark.parametrize("value", [0.0, 0.04045, 0.5, 1.0])
def test_srgb_linear_roundtrip(value: float) -> None:
    arr = np.array([value])
    assert linear_to_srgb(srgb_to_linear(arr)) == pytest.approx(arr, abs=1e-6)


def test_conversion_endpoints_exact() -> None:
    ends = np.array([0.0, 1.0])
    assert srgb_to_linear(ends) == pytest.approx(ends)


def test_conversion_darkens_midtones() -> None:
    """Linear values sit below sRGB ones -- the reason naive upload looks washed out."""
    mid = np.array([0.5])
    assert srgb_to_linear(mid)[0] < 0.5


# ------------------------------------------------------------------ regression


def test_surface_is_not_double_encoded() -> None:
    """Regression for the measured bug: surface rendered (69,64,75) instead of (15,13,18).

    Uploading linear values to an ``*-srgb`` target must round-trip back to the
    original MD3 bytes. Uploading sRGB floats directly would not.
    """
    theme = Theme(seed="#6750A4", dark=True)
    palette = Palette(theme)

    scheme = SchemeTonalSpot(theme.hct(), theme.dark, theme.contrast)
    expected = np.array(MaterialDynamicColors.surface.get_rgba(scheme)[:3], dtype=np.float64)

    stored = np.array(palette.linear("surface")[:3])
    encoded = np.round(linear_to_srgb(stored) * 255.0)

    assert encoded == pytest.approx(expected, abs=1.0)
    # And prove the naive path really would have been wrong:
    assert np.round(stored * 255.0) != pytest.approx(expected, abs=1.0)


# ------------------------------------------------------------------ palette


def test_shape_and_dtype() -> None:
    p = Palette()
    assert p.data.shape == (TOKEN_COUNT, 4)
    assert p.data.dtype == np.float32
    assert p.data.flags["C_CONTIGUOUS"]  # uploaded directly to the GPU


def test_values_in_unit_range() -> None:
    p = Palette()
    assert p.data.min() >= 0.0
    assert p.data.max() <= 1.0


def test_alpha_is_opaque_and_untransformed() -> None:
    assert np.all(Palette().data[:, 3] == 1.0)


def test_light_and_dark_differ() -> None:
    dark = Palette(Theme(dark=True)).linear("surface")
    light = Palette(Theme(dark=False)).linear("surface")
    assert dark != light
    assert dark[0] < light[0]


def test_contrast_changes_the_palette() -> None:
    low = Palette(Theme(dark=True, contrast=0.0)).linear("outline")
    high = Palette(Theme(dark=True, contrast=1.0)).linear("outline")
    assert low != high


def test_rebuild_marks_dirty() -> None:
    p = Palette(Theme(dark=True))
    p.mark_uploaded()
    assert not p.dirty
    p.rebuild(Theme(dark=False))
    assert p.dirty


def test_rebuild_mutates_in_place() -> None:
    """The buffer identity must be stable -- the GPU binding points at it."""
    p = Palette()
    before = p.data
    p.rebuild(Theme(dark=False))
    assert p.data is before


def test_unknown_token_raises() -> None:
    with pytest.raises(KeyError, match="unknown MD3 token"):
        Palette().index("chartreuse")


# ------------------------------------------------------------------ hex parsing


@pytest.mark.parametrize(
    ("text", "expected"),
    [("#6750A4", 0xFF6750A4), ("6750A4", 0xFF6750A4), ("#FF6750A4", 0xFF6750A4)],
)
def test_parse_hex(text: str, expected: int) -> None:
    assert parse_hex(text) == expected


@pytest.mark.parametrize("bad", ["#ABC", "", "#GGGGGG", "#1234567"])
def test_parse_hex_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_hex(bad)
