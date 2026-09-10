"""Dock Group demo -- its own window, own process.

python examples/widgets/dock_group/app.py
"""

from pathlib import Path

from DockGroup_ViewModel import DockGroupDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "DockGroup_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Dock Group", width=800, height=780),
)
app.bind_view_model(VIEW.name, DockGroupDemo())

if __name__ == "__main__":
    app.run()
