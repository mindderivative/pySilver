"""Tooltip demo -- its own window, own process.

python examples/widgets/tooltip/app.py
"""

from pathlib import Path

from Tooltip_ViewModel import TooltipDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Tooltip_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Tooltip", width=760, height=780),
)
app.bind_view_model(VIEW.name, TooltipDemo())

if __name__ == "__main__":
    app.run()
