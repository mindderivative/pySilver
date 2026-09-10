"""Tabs demo -- its own window, own process.

python examples/widgets/tabs/app.py
"""

from pathlib import Path

from Tabs_ViewModel import TabsDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Tabs_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Tabs", width=760, height=820),
)
app.bind_view_model(VIEW.name, TabsDemo())

if __name__ == "__main__":
    app.run()
