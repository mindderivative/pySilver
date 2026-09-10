"""Button Group demo -- its own window, own process.

python examples/widgets/button_group/app.py
"""

from pathlib import Path

from ButtonGroup_ViewModel import ButtonGroupDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "ButtonGroup_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Button Group", width=760, height=800),
)
app.bind_view_model(VIEW.name, ButtonGroupDemo())

if __name__ == "__main__":
    app.run()
