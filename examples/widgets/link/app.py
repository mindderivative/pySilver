"""Link demo -- its own window, own process.

python examples/widgets/link/app.py
"""

from pathlib import Path

from Link_ViewModel import LinkDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Link_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Link", width=760, height=780),
)
app.bind_view_model(VIEW.name, LinkDemo())

if __name__ == "__main__":
    app.run()
