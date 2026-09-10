"""Button demo -- its own window, own process.

python examples/widgets/button/app.py
"""

from pathlib import Path

from Button_ViewModel import ButtonDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Button_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Button", width=760, height=820),
)
app.bind_view_model(VIEW.name, ButtonDemo())

if __name__ == "__main__":
    app.run()
