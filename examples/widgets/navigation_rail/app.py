"""Navigation Rail demo -- its own window, own process.

python examples/widgets/navigation_rail/app.py
"""

from pathlib import Path

from NavigationRail_ViewModel import NavigationRailDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "NavigationRail_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Navigation Rail", width=760, height=800),
)
app.bind_view_model(VIEW.name, NavigationRailDemo())

if __name__ == "__main__":
    app.run()
