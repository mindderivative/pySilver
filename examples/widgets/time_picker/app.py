"""Time Picker demo -- its own window, own process.

python examples/widgets/time_picker/app.py
"""

from pathlib import Path

from TimePicker_ViewModel import TimePickerDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "TimePicker_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Time Picker", width=800, height=800),
)
app.bind_view_model(VIEW.name, TimePickerDemo())

if __name__ == "__main__":
    app.run()
