"""Radio demo -- its own window, own process.

python examples/widgets/radio/app.py
"""

from pathlib import Path

from Radio_ViewModel import RadioDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Radio_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Radio", width=760, height=820),
)
app.bind_view_model(VIEW.name, RadioDemo())

if __name__ == "__main__":
    app.run()
