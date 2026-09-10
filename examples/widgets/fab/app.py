"""Fab demo -- its own window, own process.

python examples/widgets/fab/app.py
"""

from pathlib import Path

from Fab_ViewModel import FabDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Fab_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Fab", width=900, height=780),
)
app.bind_view_model(VIEW.name, FabDemo())

if __name__ == "__main__":
    app.run()
