"""Popover demo -- its own window, own process.

python examples/widgets/popover/app.py
"""

from pathlib import Path

from Popover_ViewModel import PopoverDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Popover_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Popover", width=760, height=780),
)
app.bind_view_model(VIEW.name, PopoverDemo())

if __name__ == "__main__":
    app.run()
