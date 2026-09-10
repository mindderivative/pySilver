"""pySilver M2 -- a themed window rendering MD3 primitives in one draw call.

python examples/hello/app.py
"""

from pysilver import Engine, Theme
from pysilver.paint import DisplayList
from pysilver.theme import Palette

THEME = Theme(seed="#6750A4", dark=True)
PALETTE = Palette(THEME)

CARD = PALETTE.index("surface_container_high")
PRIMARY = PALETTE.index("primary")
ON_PRIMARY = PALETTE.index("on_primary")
OUTLINE = PALETTE.index("outline_variant")


def paint(dl: DisplayList) -> None:
    """Everything below becomes ONE instanced draw call."""
    # Elevated card: shadow first, then the surface above it.
    dl.add_shadow(
        60, 60, 360, 220, blur=18.0, offset=(0.0, 6.0), color=(0.0, 0.0, 0.0, 0.45), radii=(16,) * 4
    )
    dl.add_box(
        60, 60, 360, 220, token=CARD, radii=(16,) * 4, border_width=1.0, border_token=OUTLINE
    )

    # Filled button.
    dl.add_box(92, 220, 180, 48, token=PRIMARY, radii=(24,) * 4)

    # Stand-ins for a label, clipped to the button's rounded rect -- proof that
    # clipping is analytic and does not split the draw call.
    for i in range(6):
        dl.add_box(
            112 + i * 24,
            238,
            16,
            12,
            token=ON_PRIMARY,
            radii=(3,) * 4,
            clip=(92, 220, 180, 48),
            clip_radii=(24,) * 4,
        )

    # A row of tonal swatches.
    for i, name in enumerate(["primary", "secondary", "tertiary", "error", "outline"]):
        dl.add_box(92 + i * 64, 108, 48, 48, token=PALETTE.index(name), radii=(12,) * 4)


if __name__ == "__main__":
    engine = Engine(theme=THEME)
    engine.painter = paint
    print(
        f"adapter : {engine.adapter.info['adapter_type']} / {engine.adapter.info['backend_type']}"
    )
    print(f"format  : {engine.format}")
    engine.run()
