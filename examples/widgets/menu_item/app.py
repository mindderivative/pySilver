"""Menu Item demo -- its own window, own process.

python examples/widgets/menu_item/app.py
"""

from pathlib import Path

from MenuItem_ViewModel import MenuItemDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "MenuItem_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Menu Item", width=760, height=780),
)
app.bind_view_model(VIEW.name, MenuItemDemo())

if __name__ == "__main__":
    app.run()
