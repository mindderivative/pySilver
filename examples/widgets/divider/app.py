"""Divider demo -- its own window, own process.

python examples/widgets/divider/app.py
"""

from pathlib import Path

from Divider_ViewModel import DividerDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Divider_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Divider", width=760, height=780),
)
app.bind_view_model(VIEW.name, DividerDemo())

if __name__ == "__main__":
    app.run()
