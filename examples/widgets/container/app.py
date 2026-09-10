"""Container demo -- its own window, own process.

python examples/widgets/container/app.py
"""

from pathlib import Path

from Container_ViewModel import ContainerDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Container_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Container", width=800, height=820),
)
demo = ContainerDemo()
app.bind_view_model(VIEW.name, demo)
# Also registered/exposed globally: self.app.reload(...) rebuilds the view
# as a plain dict with no file origin, so the rebuilt nodes carry no
# `view:` stamp for the scoped ViewModel/handler lookups above to match
# against. Handlers fall back to the global registry on a scoped miss, and
# `{{ }}` names fall back to the app's own shared context the same way --
# both needed for a reload-built tree with no origin of its own.
app.handler(demo.cycle_padding)
app.handler(demo.cycle_corner)
app.expose(view_source=demo.view_source, viewmodel_source=demo.viewmodel_source)

if __name__ == "__main__":
    app.run()
