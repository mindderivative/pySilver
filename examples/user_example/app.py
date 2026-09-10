"""Accordion demo -- its own window, own process.

python examples/widgets/accordion/app.py
"""

from pathlib import Path

from Window_ViewModel import WindowDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Window_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Window", width=760, height=800),
)
app.bind_view_model(VIEW.name, WindowDemo())

if __name__ == "__main__":
    app.run()
