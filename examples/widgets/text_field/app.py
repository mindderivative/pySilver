"""Text Field demo -- its own window, own process.

python examples/widgets/text_field/app.py
"""

from pathlib import Path

from TextField_ViewModel import TextFieldDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "TextField_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Text Field", width=860, height=780),
)
app.bind_view_model(VIEW.name, TextFieldDemo())

if __name__ == "__main__":
    app.run()
