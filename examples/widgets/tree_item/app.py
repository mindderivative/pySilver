"""Tree Item demo -- its own window, own process.

python examples/widgets/tree_item/app.py
"""

from pathlib import Path

from TreeItem_ViewModel import TreeItemDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "TreeItem_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Tree Item", width=760, height=780),
)
app.bind_view_model(VIEW.name, TreeItemDemo())

if __name__ == "__main__":
    app.run()
