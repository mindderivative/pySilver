"""Status Bar demo -- its own window, own process.

python examples/widgets/status_bar/app.py
"""

from pathlib import Path

from StatusBar_ViewModel import StatusBarDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "StatusBar_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Status Bar", width=760, height=780),
)
app.bind_view_model(VIEW.name, StatusBarDemo())

if __name__ == "__main__":
    app.run()
