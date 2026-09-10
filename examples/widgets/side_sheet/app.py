"""Side Sheet demo -- its own window, own process.

python examples/widgets/side_sheet/app.py
"""

from pathlib import Path

from SideSheet_ViewModel import SideSheetDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "SideSheet_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Side Sheet", width=800, height=780),
)
app.bind_view_model(VIEW.name, SideSheetDemo())

if __name__ == "__main__":
    app.run()
