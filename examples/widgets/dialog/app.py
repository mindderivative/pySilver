"""Dialog demo -- its own window, own process.

python examples/widgets/dialog/app.py
"""

from pathlib import Path

from Dialog_ViewModel import DialogDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Dialog_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Dialog", width=760, height=780),
)
app.bind_view_model(VIEW.name, DialogDemo())

if __name__ == "__main__":
    app.run()
