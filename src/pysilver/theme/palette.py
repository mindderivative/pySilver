"""MD3 palette: seed colour -> contiguous linear-RGBA buffer for the GPU.

See ARCHITECTURE.md 5.6 and 5.6.1. Two invariants matter here:

1. Widgets store a ``uint32`` palette *index*, never a colour. A theme change is
   therefore one buffer upload -- no relayout, no display-list rebuild.
2. The buffer holds **linear** RGBA. materialyoucolor returns sRGB-encoded bytes
   and the surface format is ``*-srgb``, which encodes on write; uploading
   sRGB floats would double-encode. This is the only place the conversion happens.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
from materialyoucolor.hct import Hct
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot

from .tokens import MYC_ATTR, TOKEN_COUNT, TOKEN_INDEX, TOKEN_ORDER

__all__ = ["Palette", "Theme", "parse_hex", "srgb_to_linear"]


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    """sRGB-encoded [0,1] -> linear [0,1]. Vectorised; alpha must not be passed."""
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def parse_hex(value: str) -> int:
    """``"#6750A4"`` / ``"6750A4"`` / ``"#FF6750A4"`` -> 0xAARRGGBB int."""
    h = value.lstrip("#")
    if len(h) == 6:
        h = "FF" + h
    if len(h) != 8:
        raise ValueError(f"expected 6- or 8-digit hex colour, got {value!r}")
    try:
        return int(h, 16)
    except ValueError as exc:
        raise ValueError(f"invalid hex colour {value!r}") from exc


@dataclass(frozen=True, slots=True)
class Theme:
    """User-facing theme description. Cheap to construct and compare."""

    seed: str = "#6750A4"
    dark: bool = True
    contrast: float = 0.0

    def hct(self) -> Hct:
        return Hct.from_int(parse_hex(self.seed))


class Palette:
    """Owns the token buffer uploaded to the GPU as a storage buffer."""

    __slots__ = ("_data", "_dirty", "_theme")

    def __init__(self, theme: Theme | None = None) -> None:
        self._data = np.zeros((TOKEN_COUNT, 4), dtype=np.float32)
        self._theme = theme or Theme()
        self._dirty = True
        self.rebuild(self._theme)

    @property
    def data(self) -> np.ndarray:
        """(TOKEN_COUNT, 4) float32, linear RGBA. Contiguous; upload directly."""
        return self._data

    @property
    def theme(self) -> Theme:
        return self._theme

    @property
    def dirty(self) -> bool:
        """True when the buffer changed and needs re-upload."""
        return self._dirty

    def mark_uploaded(self) -> None:
        self._dirty = False

    def rebuild(self, theme: Theme) -> np.ndarray:
        scheme = SchemeTonalSpot(theme.hct(), theme.dark, theme.contrast)
        srgb = np.empty((TOKEN_COUNT, 4), dtype=np.float64)
        for i, name in enumerate(TOKEN_ORDER):
            token = getattr(MaterialDynamicColors, MYC_ATTR[name])
            srgb[i] = np.asarray(token.get_rgba(scheme), dtype=np.float64) / 255.0

        self._data[:, :3] = srgb_to_linear(srgb[:, :3]).astype(np.float32)
        self._data[:, 3] = srgb[:, 3].astype(np.float32)  # alpha is already linear
        self._theme = theme
        self._dirty = True
        return self._data

    def index(self, name: str) -> int:
        """Palette index for a token name. Raises on unknown tokens (fail at load)."""
        try:
            return TOKEN_INDEX[name]
        except KeyError:
            raise KeyError(f"unknown MD3 token {name!r}") from None

    def linear(self, name: str) -> tuple[float, float, float, float]:
        """Linear RGBA for a token -- for clear values and tests."""
        r, g, b, a = self._data[self.index(name)]
        return (float(r), float(g), float(b), float(a))
