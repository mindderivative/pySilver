"""Date Picker demo -- its own window, own process.

python examples/widgets/date_picker/app.py
"""

from pathlib import Path

from DatePicker_ViewModel import DatePickerDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "DatePicker_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Date Picker", width=800, height=800),
)
app.bind_view_model(VIEW.name, DatePickerDemo())

if __name__ == "__main__":
    app.run()
