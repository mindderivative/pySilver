"""Card demo -- its own window, own process.

python examples/widgets/card/app.py
"""

from pathlib import Path

from Card_ViewModel import CardDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Card_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Card", width=900, height=780),
)
app.bind_view_model(VIEW.name, CardDemo())

if __name__ == "__main__":
    app.run()
