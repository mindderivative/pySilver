"""Top App Bar demo -- its own window, own process.

python examples/widgets/top_app_bar/app.py
"""

from pathlib import Path

from TopAppBar_ViewModel import TopAppBarDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "TopAppBar_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Top App Bar", width=760, height=860),
)
app.bind_view_model(VIEW.name, TopAppBarDemo())

if __name__ == "__main__":
    app.run()
