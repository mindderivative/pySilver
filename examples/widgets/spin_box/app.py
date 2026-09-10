"""Spin Box demo -- its own window, own process.

python examples/widgets/spin_box/app.py
"""

from pathlib import Path

from SpinBox_ViewModel import SpinBoxDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "SpinBox_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Spin Box", width=760, height=780),
)
app.bind_view_model(VIEW.name, SpinBoxDemo())

if __name__ == "__main__":
    app.run()
