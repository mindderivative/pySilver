"""List Item demo -- its own window, own process.

python examples/widgets/list_item/app.py
"""

from pathlib import Path

from ListItem_ViewModel import ListItemDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "ListItem_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- List Item", width=760, height=860),
)
app.bind_view_model(VIEW.name, ListItemDemo())

if __name__ == "__main__":
    app.run()
