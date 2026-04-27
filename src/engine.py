import wgpu
import numpy as np
import struct
from collections import deque
from typing import Optional, Tuple

SHADER_SOURCE = """
struct Params {
    char_w: u32,
    char_h: u32,
    num_cols: u32,
};

@group(0) @binding(0) var<storage, read> indices: array<u32>;
@group(0) @binding(1) var<storage, read> colors: array<u32>;
@group(0) @binding(2) var atlas_tex: texture_2d<f32>;
@group(0) @binding(3) var out_tex: texture_storage_2d<rgba8unorm, write>;
@group(0) @binding(4) var<uniform> params: Params;

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) grid_pos: vec3<u32>) {
    let dims = textureDimensions(out_tex);
    if (grid_pos.x >= dims.x || grid_pos.y >= dims.y) { return; }

    let col = grid_pos.x / params.char_w;
    let row = grid_pos.y / params.char_h;
    let raw_color = colors[row * params.num_cols + col];
    
    // 1. EXTRACT (Based on your successful Hard Swap)
    var r = f32(raw_color & 0xffu) / 255.0;
    var g = f32((raw_color >> 8u) & 0xffu) / 255.0;
    var b = f32((raw_color >> 16u) & 0xffu) / 255.0;

    // 2. LINEAR CONVERSION (De-gamma)
    // This removes the "comic book" harshness
    r = pow(r, 2.2);
    g = pow(g, 2.2);
    b = pow(b, 2.2);

    // 3. VIBRANCE (Subtle boost, not a crush)
    let luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    r = mix(luma, r, 1.4);
    g = mix(luma, g, 1.4);
    b = mix(luma, b, 1.4);

    // 4. RE-APPLY GAMMA (sRGB conversion for monitor)
    let final_r = pow(max(r, 0.0), 1.0 / 2.2);
    let final_g = pow(max(g, 0.0), 1.0 / 2.2);
    let final_b = pow(max(b, 0.0), 1.0 / 2.2);

    let char_idx = indices[row * params.num_cols + col];
    let atlas_x = (char_idx * params.char_w) + (grid_pos.x % params.char_w);
    let atlas_y = grid_pos.y % params.char_h;
    let glyph_pixel = textureLoad(atlas_tex, vec2<u32>(atlas_x, atlas_y), 0).r;

    if (glyph_pixel > 0.1) {
        // Multiply by glyph_pixel to smooth edges
        textureStore(out_tex, grid_pos.xy, vec4<f32>(final_r * glyph_pixel, final_g * glyph_pixel, final_b * glyph_pixel, 1.0));
    } else {
        textureStore(out_tex, grid_pos.xy, vec4<f32>(0.01, 0.01, 0.015, 1.0));
    }
}
"""


class GPUBlitzEngine:
    """Manages WGPU compute resources and frame synchronization."""
    
    def __init__(self, char_w: int, char_h: int, atlas_data: np.ndarray, num_cols: int):
        # Auto-selects best GPU (Vulkan, Metal, D3D12, or Software)
        self.adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        if not self.adapter:
            raise RuntimeError("No suitable GPU adapter found.")
            
        self.device = self.adapter.request_device_sync()
        self.char_w, self.char_h, self.num_cols = char_w, char_h, num_cols
        
        self.module = self.device.create_shader_module(code=SHADER_SOURCE)
        self.pipeline = self.device.create_compute_pipeline(
            layout="auto", 
            compute={"module": self.module, "entry_point": "main"}
        )
        
        # Initialize Atlas Texture
        self.atlas_tex = self.device.create_texture(
            size=(atlas_data.shape[1], atlas_data.shape[0], 1),
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
            format=wgpu.TextureFormat.r8unorm
        )
        self.device.queue.write_texture(
            {"texture": self.atlas_tex}, 
            atlas_data, 
            {"bytes_per_row": atlas_data.shape[1], "rows_per_image": atlas_data.shape[0]}, 
            (atlas_data.shape[1], atlas_data.shape[0], 1)
        )
        
        self.param_buffer = self.device.create_buffer_with_data(
            data=struct.pack("III", char_w, char_h, num_cols), 
            usage=wgpu.BufferUsage.UNIFORM
        )
        
        self.inflight_queue = deque()
        self.pool = []
        self.max_inflight = 3

    def submit_frame(self, indices: np.ndarray, colors: np.ndarray, out_w: int, out_h: int):
        """Dispatches compute shader for a single frame."""
        padded_bpr = (out_w * 4 + 255) & ~255 # Alignment for GPU-to-CPU copy
        
        if not self.pool:
            idx_b = self.device.create_buffer(size=indices.nbytes, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST)
            col_b = self.device.create_buffer(size=colors.nbytes, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST)
            dst_b = self.device.create_buffer(size=padded_bpr * out_h, usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ)
            out_t = self.device.create_texture(size=(out_w, out_h, 1), usage=wgpu.TextureUsage.STORAGE_BINDING | wgpu.TextureUsage.COPY_SRC, format=wgpu.TextureFormat.rgba8unorm)
            resources = (idx_b, col_b, dst_b, out_t)
        else:
            resources = self.pool.pop()

        idx_b, col_b, dst_b, out_t = resources
        self.device.queue.write_buffer(idx_b, 0, indices)
        self.device.queue.write_buffer(col_b, 0, colors)

        encoder = self.device.create_command_encoder()
        bg = self.device.create_bind_group(layout=self.pipeline.get_bind_group_layout(0), entries=[
            {"binding": 0, "resource": {"buffer": idx_b}},
            {"binding": 1, "resource": {"buffer": col_b}},
            {"binding": 2, "resource": self.atlas_tex.create_view()},
            {"binding": 3, "resource": out_t.create_view()},
            {"binding": 4, "resource": {"buffer": self.param_buffer}},
        ])

        cpass = encoder.begin_compute_pass()
        cpass.set_pipeline(self.pipeline)
        cpass.set_bind_group(0, bg, [])
        cpass.dispatch_workgroups(int(np.ceil(out_w / 8)), int(np.ceil(out_h / 8)), 1)
        cpass.end()
        
        encoder.copy_texture_to_buffer(
            {"texture": out_t}, 
            {"buffer": dst_b, "offset": 0, "bytes_per_row": padded_bpr, "rows_per_image": out_h}, 
            (out_w, out_h, 1)
        )
        self.device.queue.submit([encoder.finish()])
        self.inflight_queue.append((dst_b, out_h, padded_bpr, out_w * 4, resources))

    def get_finished_frame(self) -> Optional[np.ndarray]:
        """Maps GPU memory back to CPU. Returns NumPy array."""
        if not self.inflight_queue: return None
        buf, h, pbpr, ubpr, resources = self.inflight_queue.popleft()
        buf.map_sync(wgpu.MapMode.READ)
        data = np.frombuffer(buf.read_mapped(), dtype=np.uint8).reshape((h, pbpr))[:, :ubpr].copy()
        buf.unmap()
        self.pool.append(resources)
        return data