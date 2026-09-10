"""Bottom Sheet demo -- its own window, own process.

python examples/widgets/bottom_sheet/app.py
"""

from pathlib import Path

from BottomSheet_ViewModel import BottomSheetDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "BottomSheet_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Bottom Sheet", width=760, height=780),
)
app.bind_view_model(VIEW.name, BottomSheetDemo())

if __name__ == "__main__":
    app.run()
