"""Video demo -- its own window, own process.

python examples/widgets/video/app.py
"""

from pathlib import Path

import numpy as np
from Video_ViewModel import VideoDemo

from pysilver import App, Settings, Theme

VIEW = Path(__file__).parent / "Video_View.yaml"

app = App(
    VIEW,
    theme=Theme(seed="#6750A4", dark=True),
    settings=Settings(title="pySilver widgets -- Video", width=760, height=780),
)
app.bind_view_model(VIEW.name, VideoDemo())


def _synthetic_frame() -> np.ndarray:
    """`Video` has no file to decode -- an application feeds it frames
    directly through `push_frame`. One static gradient frame, the same
    technique `examples/gallery/app.py` uses for its own Video demo, is
    enough to prove the widget paints what it is given.
    """
    h, w = 160, 260
    y, x = np.mgrid[0:h, 0:w]
    t = (x / w + y / h) / 2.0
    top = np.array([0x00, 0x69, 0x6B], dtype=np.float32)  # teal
    bottom = np.array([0x6A, 0x1B, 0x9A], dtype=np.float32)  # violet
    rgb = top[None, None, :] + (bottom - top)[None, None, :] * t[:, :, None]
    frame = np.empty((h, w, 4), dtype=np.uint8)
    frame[:, :, :3] = rgb.astype(np.uint8)
    frame[:, :, 3] = 255
    return frame


# `mount()` is idempotent and `run()` calls it again -- doing it here just
# makes `app.root.find(...)` available so a frame can be pushed before the
# window ever opens.
app.mount()
app.root.find("video_demo").push_frame(_synthetic_frame())

if __name__ == "__main__":
    app.run()
