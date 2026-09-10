"""Text demo -- its own window, own process.

python examples/widgets/text/app.py
"""

from pathlib import Path

from Text_ViewModel import TextDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Text_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Text", width=760, height=780),
)
app.bind_view_model(VIEW.name, TextDemo())

if __name__ == "__main__":
    app.run()
