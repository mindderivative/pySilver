"""Checkbox demo -- its own window, own process.

python examples/widgets/checkbox/app.py
"""

from pathlib import Path

from Checkbox_ViewModel import CheckboxDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Checkbox_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Checkbox", width=760, height=820),
)
app.bind_view_model(VIEW.name, CheckboxDemo())

if __name__ == "__main__":
    app.run()
