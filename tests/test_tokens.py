"""TOKEN_ORDER is a frozen, append-only constant. These tests guard that contract."""

from __future__ import annotations

from pysilver.theme import TOKEN_COUNT, TOKEN_INDEX, TOKEN_ORDER, is_token
from pysilver.theme.tokens import MYC_ATTR

# Snapshot of the vocabulary's leading entries. Palette indices are baked into
# cached display lists, so a change here is a BREAKING change, not a test fix.
FROZEN_PREFIX = ("background", "error", "error_container", "error_dim")


def test_prefix_is_frozen() -> None:
    assert TOKEN_ORDER[: len(FROZEN_PREFIX)] == FROZEN_PREFIX


def test_no_duplicates() -> None:
    assert len(set(TOKEN_ORDER)) == len(TOKEN_ORDER)


def test_index_matches_order() -> None:
    assert TOKEN_COUNT == len(TOKEN_ORDER) == len(TOKEN_INDEX)
    for i, name in enumerate(TOKEN_ORDER):
        assert TOKEN_INDEX[name] == i


def test_every_token_maps_to_a_real_attribute() -> None:
    from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors

    assert set(MYC_ATTR) == set(TOKEN_ORDER)
    for name in TOKEN_ORDER:
        assert hasattr(MaterialDynamicColors, MYC_ATTR[name]), name


def test_public_names_are_snake_case() -> None:
    for name in TOKEN_ORDER:
        assert name.islower(), name
        assert " " not in name and "-" not in name


def test_is_token() -> None:
    assert is_token("surface_variant")
    assert not is_token("surfaceVariant")  # camelCase is internal only
    assert not is_token("nope")
