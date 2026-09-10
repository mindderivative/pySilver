"""Slider demo -- its own window, own process.

python examples/widgets/slider/app.py
"""

from pathlib import Path

from Slider_ViewModel import SliderDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Slider_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Slider", width=760, height=760),
)
app.bind_view_model(VIEW.name, SliderDemo())

if __name__ == "__main__":
    app.run()
