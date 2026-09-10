"""Tree View demo -- its own window, own process.

python examples/widgets/tree_view/app.py
"""

from pathlib import Path

from TreeView_ViewModel import TreeViewDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "TreeView_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Tree View", width=760, height=820),
)
app.bind_view_model(VIEW.name, TreeViewDemo())

if __name__ == "__main__":
    app.run()
