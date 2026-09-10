"""Badge demo -- its own window, own process.

python examples/widgets/badge/app.py
"""

from pathlib import Path

from Badge_ViewModel import BadgeDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Badge_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Badge", width=760, height=780),
)
app.bind_view_model(VIEW.name, BadgeDemo())

if __name__ == "__main__":
    app.run()
