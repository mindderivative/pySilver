"""Dock Panel demo -- its own window, own process.

python examples/widgets/dock_panel/app.py
"""

from pathlib import Path

from DockPanel_ViewModel import DockPanelDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "DockPanel_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Dock Panel", width=760, height=780),
)
app.bind_view_model(VIEW.name, DockPanelDemo())

if __name__ == "__main__":
    app.run()
