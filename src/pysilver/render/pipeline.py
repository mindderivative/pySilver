"""The single universal render pipeline.

One pipeline, one bind group, one render pass, one instanced draw per frame.
Anything that would force a second draw -- a scissor rect, a per-widget texture,
a second pipeline -- is redesigned instead (ARCHITECTURE.md 1.3, 5.8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import numpy as np
import wgpu

from ..paint.display_list import INSTANCE_SIZE, DisplayList
from ..theme.tokens import TOKEN_COUNT
from .buffers import InstanceRing, ortho_projection

__all__ = ["UIPipeline"]

SHADER_PATH: Final = Path(__file__).parent / "shaders" / "ui.wgsl"

#: Unit quad as a triangle strip: (0,0) (1,0) (0,1) (1,1).
QUAD: Final = np.array([0, 0, 1, 0, 0, 1, 1, 1], dtype=np.float32)

_GLOBALS_SIZE: Final = 80  # mat4x4 (64) + vec2 (8) + f32 + f32

# Nine vec4-sized instance attributes at shader locations 1..9.
_INSTANCE_ATTRS: Final = [
    {"format": "float32x4", "offset": 16 * i, "shader_location": i + 1} for i in range(8)
] + [{"format": "uint32x4", "offset": 128, "shader_location": 9}]


class UIPipeline:
    """Owns the shader, layouts, static geometry, atlases, and buffers."""

    def __init__(self, device: wgpu.GPUDevice, format: str) -> None:
        self.device = device
        self.format = format

        self.shader = device.create_shader_module(
            code=SHADER_PATH.read_text(encoding="utf-8"), label="ui.wgsl"
        )

        self.quad_buffer = device.create_buffer_with_data(data=QUAD, usage=wgpu.BufferUsage.VERTEX)
        self.globals_buffer = device.create_buffer(
            size=_GLOBALS_SIZE,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        self.palette_buffer = device.create_buffer(
            size=TOKEN_COUNT * 16,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        )
        self.instances = InstanceRing(device, INSTANCE_SIZE)

        # 1x1 placeholders so the bind group is complete before M4 fills the
        # real atlases. The pipeline shape is final; only contents change.
        self.glyph_atlas = self._placeholder("r8unorm", b"\xff")
        # `-srgb`: see `render/atlas.py`'s `ImageAtlas._create_texture` for why
        # an image texture must decode sRGB on sample, unlike the glyph atlas's
        # plain `r8unorm` -- coverage has no colour to decode.
        self.image_atlas = self._placeholder("rgba8unorm-srgb", b"\xff\xff\xff\xff")
        self.sampler = device.create_sampler(
            mag_filter=wgpu.FilterMode.linear,
            min_filter=wgpu.FilterMode.linear,
            address_mode_u=wgpu.AddressMode.clamp_to_edge,
            address_mode_v=wgpu.AddressMode.clamp_to_edge,
        )

        self.bind_group_layout = self._make_bind_group_layout()
        self.bind_group = self._make_bind_group()
        self.pipeline = self._make_pipeline()

        self._globals = np.zeros(_GLOBALS_SIZE // 4, dtype=np.float32)

    # ------------------------------------------------------------- resources

    def _placeholder(self, fmt: str, texel: bytes) -> wgpu.GPUTexture:
        texture = self.device.create_texture(
            size=(1, 1, 1),
            format=fmt,
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )
        self.device.queue.write_texture(
            {"texture": texture},
            texel,
            {"bytes_per_row": len(texel), "rows_per_image": 1},
            (1, 1, 1),
        )
        return texture

    def _make_bind_group_layout(self) -> wgpu.GPUBindGroupLayout:
        vf = wgpu.ShaderStage.VERTEX | wgpu.ShaderStage.FRAGMENT
        f = wgpu.ShaderStage.FRAGMENT
        texture = {"sample_type": wgpu.TextureSampleType.float, "view_dimension": "2d"}
        return self.device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": vf,
                    "buffer": {"type": wgpu.BufferBindingType.uniform},
                },
                {
                    "binding": 1,
                    "visibility": f,
                    "buffer": {"type": wgpu.BufferBindingType.read_only_storage},
                },
                {"binding": 2, "visibility": f, "texture": texture},
                {"binding": 3, "visibility": f, "texture": texture},
                {
                    "binding": 4,
                    "visibility": f,
                    "sampler": {"type": wgpu.SamplerBindingType.filtering},
                },
            ]
        )

    def _make_bind_group(self) -> wgpu.GPUBindGroup:
        return self.device.create_bind_group(
            layout=self.bind_group_layout,
            entries=[
                {
                    "binding": 0,
                    "resource": {"buffer": self.globals_buffer, "offset": 0, "size": _GLOBALS_SIZE},
                },
                {
                    "binding": 1,
                    "resource": {
                        "buffer": self.palette_buffer,
                        "offset": 0,
                        "size": TOKEN_COUNT * 16,
                    },
                },
                {"binding": 2, "resource": self.glyph_atlas.create_view()},
                {"binding": 3, "resource": self.image_atlas.create_view()},
                {"binding": 4, "resource": self.sampler},
            ],
        )

    def _make_pipeline(self) -> wgpu.GPURenderPipeline:
        # Premultiplied alpha, matching the shader's output convention.
        blend = {
            "color": {"src_factor": "one", "dst_factor": "one-minus-src-alpha", "operation": "add"},
            "alpha": {"src_factor": "one", "dst_factor": "one-minus-src-alpha", "operation": "add"},
        }
        return self.device.create_render_pipeline(
            layout=self.device.create_pipeline_layout(bind_group_layouts=[self.bind_group_layout]),
            vertex={
                "module": self.shader,
                "entry_point": "vs_main",
                "buffers": [
                    {
                        "array_stride": 8,
                        "step_mode": "vertex",
                        "attributes": [{"format": "float32x2", "offset": 0, "shader_location": 0}],
                    },
                    {
                        "array_stride": INSTANCE_SIZE,
                        "step_mode": "instance",
                        "attributes": _INSTANCE_ATTRS,
                    },
                ],
            },
            primitive={"topology": wgpu.PrimitiveTopology.triangle_strip},
            fragment={
                "module": self.shader,
                "entry_point": "fs_main",
                "targets": [{"format": self.format, "blend": blend}],
            },
        )

    # ---------------------------------------------------------------- frame

    def bind_glyph_atlas(self, texture: Any) -> None:
        """Swap in the real glyph atlas, replacing the 1x1 placeholder.

        Rebuilding the bind group is the only way to change a bound texture in
        WebGPU. It happens once at start-up, not per frame -- the atlas image
        changes, but the texture object it lives in does not.

        Deliberately does not destroy the outgoing texture: this is a low-
        level primitive with no opinion on who else might still hold a live
        reference to it (a test binding a texture directly, as
        `tests/golden/test_primitives.py` does; `Engine`'s own `TextEngine`
        before `App.attach()` replaces it). The caller that actually orphans
        a texture -- `App.attach()`, swapping its own atlas in for `Engine`'s
        -- is the one that knows that and destroys it there.
        """
        self.glyph_atlas = texture
        self.bind_group = self._make_bind_group()

    def bind_image_atlas(self, texture: Any) -> None:
        """Swap in a real image atlas, replacing the 1x1 placeholder.

        Mirrors `bind_glyph_atlas` exactly, including not destroying the
        outgoing texture -- see its docstring.
        """
        self.image_atlas = texture
        self.bind_group = self._make_bind_group()

    def destroy(self) -> None:
        """Release every GPU object this pipeline owns.

        Called from `Engine.close`, so the ordering there can be relied on
        rather than left to whenever the garbage collector gets round to it.
        """
        self.instances.destroy()
        for buffer in (self.quad_buffer, self.globals_buffer, self.palette_buffer):
            buffer.destroy()
        for texture in (self.glyph_atlas, self.image_atlas):
            if texture is not None:
                texture.destroy()

    def upload_palette(self, palette: np.ndarray) -> None:
        self.device.queue.write_buffer(
            self.palette_buffer, 0, np.ascontiguousarray(palette, dtype=np.float32)
        )

    def upload_globals(self, width: float, height: float, pixel_ratio: float) -> None:
        self._globals[:16] = ortho_projection(width, height)
        self._globals[16] = width
        self._globals[17] = height
        self._globals[18] = pixel_ratio
        self._globals[19] = 0.0
        self.device.queue.write_buffer(self.globals_buffer, 0, self._globals)

    def draw(self, render_pass: Any, display_list: DisplayList) -> int:
        """Record the frame's single instanced draw. Returns the instance count."""
        count = len(display_list)
        if count == 0:
            return 0
        instance_buffer = self.instances.upload(display_list.view)
        render_pass.set_pipeline(self.pipeline)
        render_pass.set_bind_group(0, self.bind_group)
        render_pass.set_vertex_buffer(0, self.quad_buffer)
        render_pass.set_vertex_buffer(1, instance_buffer)
        render_pass.draw(4, count, 0, 0)
        return count
