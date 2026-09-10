"""Node demo -- its own window, own process.

python examples/widgets/node/app.py
"""

from pathlib import Path

from Node_ViewModel import NodeDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Node_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Node", width=800, height=780),
)
app.bind_view_model(VIEW.name, NodeDemo())

if __name__ == "__main__":
    app.run()
