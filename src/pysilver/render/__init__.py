"""Render: the single universal WebGPU pipeline."""

from .buffers import InstanceRing, ortho_projection
from .pipeline import UIPipeline

__all__ = ["InstanceRing", "UIPipeline", "ortho_projection"]
