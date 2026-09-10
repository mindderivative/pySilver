"""Page Host demo -- its own window, own process.

python examples/widgets/page_host/app.py
"""

from pathlib import Path

from PageHost_ViewModel import PageHostDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "PageHost_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Page Host", width=760, height=800),
)
app.bind_view_model(VIEW.name, PageHostDemo())

if __name__ == "__main__":
    app.run()
