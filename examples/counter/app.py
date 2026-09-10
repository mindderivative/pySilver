"""pySilver M3 -- a declarative, reactive counter.

    python examples/counter/app.py

The view is data (view.yaml); the logic is Python; signals connect them.
"""

from pathlib import Path

from pysilver import App, Signal, Theme

app = App(Path(__file__).parent / "view.yaml", theme=Theme(seed="#6750A4", dark=True))
count = Signal(0, name="count")
app.expose(count=count)


@app.handler
def increment(event) -> None:
    count.update(lambda n: n + 1)


@app.handler
def reset(event) -> None:
    count.set(0)


if __name__ == "__main__":
    app.run()
