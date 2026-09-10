"""Tab demo -- its own window, own process.

python examples/widgets/tab/app.py
"""

from pathlib import Path

from Tab_ViewModel import TabDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Tab_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Tab", width=760, height=780),
)
app.bind_view_model(VIEW.name, TabDemo())

if __name__ == "__main__":
    app.run()
