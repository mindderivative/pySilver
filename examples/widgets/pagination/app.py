"""Pagination demo -- its own window, own process.

python examples/widgets/pagination/app.py
"""

from pathlib import Path

from Pagination_ViewModel import PaginationDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Pagination_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Pagination", width=760, height=780),
)
app.bind_view_model(VIEW.name, PaginationDemo())

if __name__ == "__main__":
    app.run()
