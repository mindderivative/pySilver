"""Carousel demo -- its own window, own process.

python examples/widgets/carousel/app.py
"""

from pathlib import Path

from Carousel_ViewModel import CarouselDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Carousel_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Carousel", width=800, height=760),
)
app.bind_view_model(VIEW.name, CarouselDemo())

if __name__ == "__main__":
    app.run()
