"""Search Bar demo -- its own window, own process.

python examples/widgets/search_bar/app.py
"""

from pathlib import Path

from SearchBar_ViewModel import SearchBarDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "SearchBar_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Search Bar", width=760, height=780),
)
app.bind_view_model(VIEW.name, SearchBarDemo())

if __name__ == "__main__":
    app.run()
