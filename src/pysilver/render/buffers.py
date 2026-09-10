"""GPU buffer management: a growing ring so the CPU never writes a buffer the
GPU may still be reading.

Buffers grow by doubling and are never shrunk within a session -- an interface
that once needed N instances will very likely need N again.
"""

from __future__ import annotations

import numpy as np
import wgpu

__all__ = ["InstanceRing", "ortho_projection"]


def ortho_projection(width: float, height: float) -> np.ndarray:
    """Top-left origin, Y down, into NDC. Column-major, as WGSL expects.

    Y is negated because UI coordinates grow downward while NDC grows upward;
    this is the single place that flip happens (ARCHITECTURE.md 7).
    """
    w = max(width, 1.0)
    h = max(height, 1.0)
    return np.array(
        [
            2.0 / w,
            0.0,
            0.0,
            0.0,  # column 0
            0.0,
            -2.0 / h,
            0.0,
            0.0,  # column 1
            0.0,
            0.0,
            1.0,
            0.0,  # column 2
            -1.0,
            1.0,
            0.0,
            1.0,  # column 3 (translation)
        ],
        dtype=np.float32,
    )


class InstanceRing:
    """A rotating set of instance buffers.

    ``frames`` buffers are cycled so a frame's writes never land in a buffer the
    GPU is still reading from an earlier frame.
    """

    __slots__ = ("_buffers", "_capacity", "_device", "_frames", "_index", "_itemsize")

    def __init__(
        self,
        device: wgpu.GPUDevice,
        itemsize: int,
        *,
        capacity: int = 1024,
        frames: int = 3,
    ) -> None:
        if frames < 1:
            raise ValueError("frames must be >= 1")
        self._device = device
        self._itemsize = itemsize
        self._capacity = max(1, capacity)
        self._frames = frames
        self._index = 0
        self._buffers: list[wgpu.GPUBuffer] = [
            self._allocate(self._capacity) for _ in range(frames)
        ]

    def _allocate(self, capacity: int) -> wgpu.GPUBuffer:
        return self._device.create_buffer(
            size=capacity * self._itemsize,
            usage=wgpu.BufferUsage.VERTEX | wgpu.BufferUsage.COPY_DST,
        )

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def frames(self) -> int:
        return self._frames

    def _grow(self, needed: int) -> None:
        capacity = self._capacity
        while capacity < needed:
            capacity *= 2
        for buffer in self._buffers:
            buffer.destroy()
        self._capacity = capacity
        self._buffers = [self._allocate(capacity) for _ in range(self._frames)]

    def upload(self, data: np.ndarray) -> wgpu.GPUBuffer:
        """Write *data* into the next buffer in the ring and return it."""
        if len(data) > self._capacity:
            self._grow(len(data))
        self._index = (self._index + 1) % self._frames
        buffer = self._buffers[self._index]
        if len(data):
            self._device.queue.write_buffer(buffer, 0, np.ascontiguousarray(data))
        return buffer

    def destroy(self) -> None:
        for buffer in self._buffers:
            buffer.destroy()
        self._buffers = []
