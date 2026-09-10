"""Segmented Button demo -- its own window, own process.

python examples/widgets/segmented_button/app.py
"""

from pathlib import Path

from SegmentedButton_ViewModel import SegmentedButtonDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "SegmentedButton_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Segmented Button", width=760, height=800),
)
app.bind_view_model(VIEW.name, SegmentedButtonDemo())

if __name__ == "__main__":
    app.run()
