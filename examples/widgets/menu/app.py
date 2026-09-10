"""Menu demo -- its own window, own process.

python examples/widgets/menu/app.py
"""

from pathlib import Path

from Menu_ViewModel import MenuDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Menu_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Menu", width=760, height=780),
)
app.bind_view_model(VIEW.name, MenuDemo())

if __name__ == "__main__":
    app.run()
