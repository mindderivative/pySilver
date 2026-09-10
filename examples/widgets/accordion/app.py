"""Accordion demo -- its own window, own process.

python examples/widgets/accordion/app.py
"""

from pathlib import Path

from Accordion_ViewModel import AccordionDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Accordion_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Accordion", width=760, height=800),
)
app.bind_view_model(VIEW.name, AccordionDemo())

if __name__ == "__main__":
    app.run()
