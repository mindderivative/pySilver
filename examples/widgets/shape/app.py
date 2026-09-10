"""Shape demo -- its own window, own process.

python examples/widgets/shape/app.py
"""

from pathlib import Path

from Shape_ViewModel import ShapeDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Shape_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Shape", width=760, height=780),
)
app.bind_view_model(VIEW.name, ShapeDemo())

if __name__ == "__main__":
    app.run()
