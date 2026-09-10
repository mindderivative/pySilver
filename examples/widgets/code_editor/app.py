"""Code Editor demo -- its own window, own process.

python examples/widgets/code_editor/app.py
"""

from pathlib import Path

from CodeEditor_ViewModel import CodeEditorDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "CodeEditor_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Code Editor", width=800, height=800),
)
app.bind_view_model(VIEW.name, CodeEditorDemo())

if __name__ == "__main__":
    app.run()
