"""Snackbar demo -- its own window, own process.

python examples/widgets/snackbar/app.py
"""

from pathlib import Path

from Snackbar_ViewModel import SnackbarDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Snackbar_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Snackbar", width=760, height=780),
)
app.bind_view_model(VIEW.name, SnackbarDemo())

if __name__ == "__main__":
    app.run()
