"""Node Graph demo -- its own window, own process.

python examples/widgets/node_graph/app.py
"""

from pathlib import Path

from NodeGraph_ViewModel import NodeGraphDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "NodeGraph_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Node Graph", width=800, height=780),
)
app.bind_view_model(VIEW.name, NodeGraphDemo())

if __name__ == "__main__":
    app.run()
