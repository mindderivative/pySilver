"""Material Design 3 design tokens.

TOKEN_ORDER is a FROZEN, VERSIONED constant. Palette indices derived from it are
baked into cached display lists, so reordering or removing an entry is a BREAKING
change requiring a major version bump. New tokens may only be APPENDED.

Public token names are snake_case (the vocabulary used in view.yaml). The mapping
to materialyoucolor's camelCase attributes is an internal detail.
"""

from __future__ import annotations

__all__ = ["MYC_ATTR", "TOKEN_COUNT", "TOKEN_INDEX", "TOKEN_ORDER", "is_token"]

#: Frozen public token vocabulary (59 tokens). APPEND-ONLY.
TOKEN_ORDER: tuple[str, ...] = (
    "background",
    "error",
    "error_container",
    "error_dim",
    "error_palette_key_color",
    "inverse_on_surface",
    "inverse_primary",
    "inverse_surface",
    "neutral_palette_key_color",
    "neutral_variant_palette_key_color",
    "on_background",
    "on_error",
    "on_error_container",
    "on_primary",
    "on_primary_container",
    "on_primary_fixed",
    "on_primary_fixed_variant",
    "on_secondary",
    "on_secondary_container",
    "on_secondary_fixed",
    "on_secondary_fixed_variant",
    "on_surface",
    "on_surface_variant",
    "on_tertiary",
    "on_tertiary_container",
    "on_tertiary_fixed",
    "on_tertiary_fixed_variant",
    "outline",
    "outline_variant",
    "primary",
    "primary_container",
    "primary_dim",
    "primary_fixed",
    "primary_fixed_dim",
    "primary_palette_key_color",
    "scrim",
    "secondary",
    "secondary_container",
    "secondary_dim",
    "secondary_fixed",
    "secondary_fixed_dim",
    "secondary_palette_key_color",
    "shadow",
    "surface",
    "surface_bright",
    "surface_container",
    "surface_container_high",
    "surface_container_highest",
    "surface_container_low",
    "surface_container_lowest",
    "surface_dim",
    "surface_tint",
    "surface_variant",
    "tertiary",
    "tertiary_container",
    "tertiary_dim",
    "tertiary_fixed",
    "tertiary_fixed_dim",
    "tertiary_palette_key_color",
)

#: Public snake_case name -> materialyoucolor camelCase attribute.
MYC_ATTR: dict[str, str] = {
    "background": "background",
    "error": "error",
    "error_container": "errorContainer",
    "error_dim": "errorDim",
    "error_palette_key_color": "errorPaletteKeyColor",
    "inverse_on_surface": "inverseOnSurface",
    "inverse_primary": "inversePrimary",
    "inverse_surface": "inverseSurface",
    "neutral_palette_key_color": "neutralPaletteKeyColor",
    "neutral_variant_palette_key_color": "neutralVariantPaletteKeyColor",
    "on_background": "onBackground",
    "on_error": "onError",
    "on_error_container": "onErrorContainer",
    "on_primary": "onPrimary",
    "on_primary_container": "onPrimaryContainer",
    "on_primary_fixed": "onPrimaryFixed",
    "on_primary_fixed_variant": "onPrimaryFixedVariant",
    "on_secondary": "onSecondary",
    "on_secondary_container": "onSecondaryContainer",
    "on_secondary_fixed": "onSecondaryFixed",
    "on_secondary_fixed_variant": "onSecondaryFixedVariant",
    "on_surface": "onSurface",
    "on_surface_variant": "onSurfaceVariant",
    "on_tertiary": "onTertiary",
    "on_tertiary_container": "onTertiaryContainer",
    "on_tertiary_fixed": "onTertiaryFixed",
    "on_tertiary_fixed_variant": "onTertiaryFixedVariant",
    "outline": "outline",
    "outline_variant": "outlineVariant",
    "primary": "primary",
    "primary_container": "primaryContainer",
    "primary_dim": "primaryDim",
    "primary_fixed": "primaryFixed",
    "primary_fixed_dim": "primaryFixedDim",
    "primary_palette_key_color": "primaryPaletteKeyColor",
    "scrim": "scrim",
    "secondary": "secondary",
    "secondary_container": "secondaryContainer",
    "secondary_dim": "secondaryDim",
    "secondary_fixed": "secondaryFixed",
    "secondary_fixed_dim": "secondaryFixedDim",
    "secondary_palette_key_color": "secondaryPaletteKeyColor",
    "shadow": "shadow",
    "surface": "surface",
    "surface_bright": "surfaceBright",
    "surface_container": "surfaceContainer",
    "surface_container_high": "surfaceContainerHigh",
    "surface_container_highest": "surfaceContainerHighest",
    "surface_container_low": "surfaceContainerLow",
    "surface_container_lowest": "surfaceContainerLowest",
    "surface_dim": "surfaceDim",
    "surface_tint": "surfaceTint",
    "surface_variant": "surfaceVariant",
    "tertiary": "tertiary",
    "tertiary_container": "tertiaryContainer",
    "tertiary_dim": "tertiaryDim",
    "tertiary_fixed": "tertiaryFixed",
    "tertiary_fixed_dim": "tertiaryFixedDim",
    "tertiary_palette_key_color": "tertiaryPaletteKeyColor",
}

#: Public token name -> palette buffer index.
TOKEN_INDEX: dict[str, int] = {name: i for i, name in enumerate(TOKEN_ORDER)}

TOKEN_COUNT: int = len(TOKEN_ORDER)


def is_token(name: str) -> bool:
    """True if *name* is a valid MD3 token in the frozen vocabulary."""
    return name in TOKEN_INDEX
