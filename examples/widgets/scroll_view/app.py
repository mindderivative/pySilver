"""Scroll View demo -- its own window, own process.

python examples/widgets/scroll_view/app.py
"""

from pathlib import Path

from ScrollView_ViewModel import ScrollViewDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "ScrollView_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Scroll View", width=760, height=820),
)
app.bind_view_model(VIEW.name, ScrollViewDemo())

if __name__ == "__main__":
    app.run()
