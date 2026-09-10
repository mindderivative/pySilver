"""Split Button demo -- its own window, own process.

python examples/widgets/split_button/app.py
"""

from pathlib import Path

from SplitButton_ViewModel import SplitButtonDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "SplitButton_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Split Button", width=760, height=780),
)
app.bind_view_model(VIEW.name, SplitButtonDemo())

if __name__ == "__main__":
    app.run()
