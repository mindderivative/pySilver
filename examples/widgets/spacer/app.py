"""Spacer demo -- its own window, own process.

python examples/widgets/spacer/app.py
"""

from pathlib import Path

from Spacer_ViewModel import SpacerDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Spacer_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Spacer", width=800, height=780),
)
demo = SpacerDemo()
app.bind_view_model(VIEW.name, demo)
# See Container's app.py for why the handler and the {{ }} names are also
# registered globally: self.app.reload(...) rebuilds the view with no file
# origin, so the scoped lookups above have nothing to match against.
app.handler(demo.cycle_ratio)
app.expose(view_source=demo.view_source, viewmodel_source=demo.viewmodel_source)

if __name__ == "__main__":
    app.run()
