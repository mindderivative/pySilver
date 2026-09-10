"""Dock Split demo -- its own window, own process.

python examples/widgets/dock_split/app.py
"""

from pathlib import Path

from DockSplit_ViewModel import DockSplitDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "DockSplit_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Dock Split", width=800, height=800),
)
app.bind_view_model(VIEW.name, DockSplitDemo())

if __name__ == "__main__":
    app.run()
