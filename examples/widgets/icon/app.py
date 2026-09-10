"""Icon demo -- its own window, own process.

python examples/widgets/icon/app.py
"""

from pathlib import Path

from Icon_ViewModel import IconDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Icon_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Icon", width=760, height=760),
)
app.bind_view_model(VIEW.name, IconDemo())

if __name__ == "__main__":
    app.run()
