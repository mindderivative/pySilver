"""Carousel Item demo -- its own window, own process.

python examples/widgets/carousel_item/app.py
"""

from pathlib import Path

from CarouselItem_ViewModel import CarouselItemDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "CarouselItem_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Carousel Item", width=800, height=760),
)
app.bind_view_model(VIEW.name, CarouselItemDemo())

if __name__ == "__main__":
    app.run()
