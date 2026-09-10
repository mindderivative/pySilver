"""Circular Progress demo -- its own window, own process.

python examples/widgets/circular_progress/app.py
"""

from pathlib import Path

from CircularProgress_ViewModel import CircularProgressDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "CircularProgress_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Circular Progress", width=780, height=800),
)
app.bind_view_model(VIEW.name, CircularProgressDemo())

if __name__ == "__main__":
    app.run()
