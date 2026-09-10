"""Linear Progress demo -- its own window, own process.

python examples/widgets/linear_progress/app.py
"""

from pathlib import Path

from LinearProgress_ViewModel import LinearProgressDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "LinearProgress_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Linear Progress", width=760, height=800),
)
app.bind_view_model(VIEW.name, LinearProgressDemo())

if __name__ == "__main__":
    app.run()
