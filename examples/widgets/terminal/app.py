"""Terminal demo -- its own window, own process.

python examples/widgets/terminal/app.py
"""

from pathlib import Path

from Terminal_ViewModel import TerminalDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Terminal_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Terminal", width=800, height=800),
)
app.bind_view_model(VIEW.name, TerminalDemo())

if __name__ == "__main__":
    app.run()
