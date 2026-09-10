"""Canvas demo -- its own window, own process.

python examples/widgets/canvas/app.py
"""

from pathlib import Path

from Canvas_ViewModel import CanvasDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Canvas_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Canvas", width=760, height=780),
)
app.bind_view_model(VIEW.name, CanvasDemo())

if __name__ == "__main__":
    app.run()
