"""Icon Button demo -- its own window, own process.

python examples/widgets/icon_button/app.py
"""

from pathlib import Path

from IconButton_ViewModel import IconButtonDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "IconButton_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Icon Button", width=760, height=760),
)
app.bind_view_model(VIEW.name, IconButtonDemo())

if __name__ == "__main__":
    app.run()
