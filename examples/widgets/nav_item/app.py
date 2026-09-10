"""Nav Item demo -- its own window, own process.

python examples/widgets/nav_item/app.py
"""

from pathlib import Path

from NavItem_ViewModel import NavItemDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "NavItem_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Nav Item", width=760, height=780),
)
app.bind_view_model(VIEW.name, NavItemDemo())

if __name__ == "__main__":
    app.run()
