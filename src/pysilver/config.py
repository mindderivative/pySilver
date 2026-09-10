"""Framework configuration. Every field is overridable via ``PYSILVER_*`` env vars."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PYSILVER_", env_file=".env", extra="forbid")

    title: str = "pySilver"
    width: int = Field(default=1024, gt=0)
    height: int = Field(default=768, gt=0)

    #: Honour a user who has asked for less movement: animations still run and
    #: settle on their target, they simply arrive at once. Widget code needs no
    #: branch, so it cannot forget the case.
    reduce_motion: bool = False

    #: 'ondemand' draws only when requested -- see ARCHITECTURE.md 5.10.
    update_mode: Literal["ondemand", "continuous", "manual"] = "ondemand"
    #: 0 means a truly idle app renders zero frames.
    min_fps: float = Field(default=0.0, ge=0)
    max_fps: float = Field(default=60.0, gt=0)

    #: Round the swapchain up to this many physical pixels while the window is
    #: being resized, so wgpu rebuilds the VkSwapchainKHR once per bucket
    #: instead of once per pixel. The buffer is then larger than the window and
    #: the compositor scales it back, which is exact for geometry and slightly
    #: soft for text -- so the pin is released a few frames after the drag
    #: stops (ARCHITECTURE.md 5.8.1). 0 disables it.
    resize_bucket: int = Field(default=256, ge=0)

    #: 'low-power' selects the integrated GPU on hybrid laptops -- wrong default
    #: for a framework that must handle full-window resizes at 60fps.
    power_preference: Literal["high-performance", "low-power"] = "high-performance"

    #: Wait for the display before showing a frame.
    #:
    #: **False by default**, which is not the conventional choice and is worth
    #: justifying. Waiting is normally free, but rendercanvas presents once per
    #: compositor configure during a resize -- 250 a second, measured -- and
    #: does so synchronously (ARCHITECTURE.md 5.8.1). On KDE Plasma Wayland a
    #: fast drag with vsync on produced **stalls of up to 7.9 seconds**; the
    #: same drag with it off ran at **466 redraws a second with no stall at
    #: all**. The frames cost ~2 ms either way. A window that lurches around
    #: for seconds is a worse defect than tearing, so the default goes to the
    #: one that does not do that.
    #:
    #: What it costs: tearing is possible while something is genuinely
    #: animating. It costs nothing at rest -- an idle pySilver application
    #: renders no frames at all (`update_mode` 'ondemand', `min_fps` 0), so
    #: this does not spin the GPU.
    #:
    #: Set it True on a platform where the resize path behaves and tearing
    #: during animation matters more.
    vsync: bool = False

    #: Who draws the window frame on Wayland.
    #:
    #: 'auto' leaves it to GLFW, which prefers libdecor -- client-side
    #: decorations drawn by a plugin. That is the right default because it is
    #: the only thing that works everywhere: GNOME does not offer server-side
    #: decorations for xdg-shell, so disabling libdecor there leaves a window
    #: with no title bar and no close button.
    #:
    #: 'server' asks the compositor for the frame instead, by disabling
    #: libdecor before GLFW initialises. On KDE Plasma -- which does offer
    #: server-side decorations -- that avoids libdecor entirely, including the
    #: "Failed to load plugin 'libdecor-gtk.so'" fallback that a missing GTK
    #: causes. Opt in only if you know your target offers them.
    wayland_decorations: Literal["auto", "server"] = "auto"

    #: Override the OS device-pixel-ratio. 0 means "use the OS value".
    force_pixel_ratio: float = Field(default=0.0, ge=0)

    hot_reload: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "WARNING"
