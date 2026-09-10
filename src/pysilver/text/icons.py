"""Material Symbols icons.

M3's icon set is a **variable icon font**, which means icons need no rendering
path of their own: an icon is a glyph, and flows through the existing FontDB,
rasteriser, and glyph atlas unchanged.

Two of its four axes are exposed (ARCHITECTURE.md 5.7.8):

* **FILL** (0..1) is load-bearing, not decorative -- M3 uses it for the
  selected/unselected transition on navigation items and toggles.
* **wght** (100..700) pairs icon stroke weight with typography.

GRAD and opsz are pinned in the bundled subset: they are fine-tuning, and
dropping them keeps the font at 102 KB instead of 10.6 MB.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Final

from ..assets import FONT_DIR
from .font import Face

__all__ = ["DEFAULT_ICON_SIZE", "IconSet", "IconStyle"]

ICON_FONT: Final = FONT_DIR / "MaterialSymbolsOutlined-Subset.ttf"
ICON_NAMES: Final = FONT_DIR / "material_symbols.json"

#: M3's standard icon size. Component specs assume it almost everywhere.
DEFAULT_ICON_SIZE: Final = 24.0

#: M3 warns against the lightest weights at 24dp; 200 is the stated minimum.
MIN_WEIGHT_AT_STANDARD_SIZE: Final = 200.0


class IconStyle:
    OUTLINED = "outlined"  # the only style bundled; rounded/sharp are separate fonts


@lru_cache(maxsize=1)
def _load_names() -> dict[str, int]:
    return {k: int(v) for k, v in json.loads(ICON_NAMES.read_text(encoding="utf-8")).items()}


class IconSet:
    """Maps icon names to glyphs in the Material Symbols face."""

    __slots__ = ("_names", "face")

    def __init__(self, face: Face, names: dict[str, int] | None = None) -> None:
        self.face = face
        self._names = dict(names) if names is not None else _load_names()

    @classmethod
    def bundled(cls) -> IconSet:
        """The bundled outlined subset -- 218 icons covering the M3 components."""
        return cls(Face(ICON_FONT))

    # ------------------------------------------------------------- lookup

    def __contains__(self, name: str) -> bool:
        return name in self._names

    def __len__(self) -> int:
        return len(self._names)

    @property
    def names(self) -> list[str]:
        return sorted(self._names)

    def codepoint(self, name: str) -> int:
        try:
            return self._names[name]
        except KeyError:
            raise KeyError(
                f"unknown icon {name!r}; {len(self._names)} icons are bundled "
                f"(see pysilver.text.icons.IconSet.names)"
            ) from None

    def glyph(self, name: str) -> int:
        """Glyph id for an icon name. Raises on an unknown name rather than
        silently rendering .notdef, since a typo'd icon should be loud."""
        return self.face.glyph_for(self.codepoint(name))

    # -------------------------------------------------------------- axes

    def coords(self, *, fill: float = 0.0, weight: float = 400.0) -> tuple[float, ...]:
        """Axis coordinates for the face, in fvar order."""
        return self.face.clamp_coords(FILL=fill, wght=weight)

    def suggested_weight(self, size: float, weight: float) -> float:
        """M3 advises against the lightest weights at standard size."""
        if size <= DEFAULT_ICON_SIZE:
            return max(MIN_WEIGHT_AT_STANDARD_SIZE, weight)
        return weight
