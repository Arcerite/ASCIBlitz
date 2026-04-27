import cv2
import numpy as np
import subprocess
import os
import time
import platform
import traceback
from tqdm import tqdm
from typing import Tuple, List, Dict, Any, Optional

def get_ffmpeg_config(width: int, height: int) -> Tuple[str, str, List[str]]:
    """
    Detects OS and selects the best working hardware encoder.
    Automatically falls back to CPU for ultra-high resolutions (Computer Killer mode).
    """
    system = platform.system()
    ffmpeg_exe = "ffmpeg"
    
    if system == "Windows":
        local_path = os.path.join(os.path.dirname(__file__), "ffmpeg.exe")
        if os.path.exists(local_path):
            ffmpeg_exe = local_path

    # HARDWARE LIMIT CHECK (The "Safety Valve")
    # Most hardware encoders (VAAPI/NVENC) cap at 4096px. 
    # CPU (libx264) can render any resolution.
    limit = 4096
    is_ultra_res = width > limit or height > limit

    try:
        res = subprocess.run([ffmpeg_exe, "-encoders"], capture_output=True, text=True)
        available_encoders = res.stdout
    except Exception:
        available_encoders = ""

    # Only attempt Hardware Encoding if we are under the 4K limit
    if not is_ultra_res:
        # 1. NVIDIA
        if "h264_nvenc" in available_encoders:
            check_gpu = subprocess.run(["which", "nvidia-smi"], capture_output=True)
            if check_gpu.returncode == 0:
                return ffmpeg_exe, "h264_nvenc", ["-preset", "p4", "-cq", "20"]

        # 2. AMD / Intel VAAPI (Linux)
        if system == "Linux" and "h264_vaapi" in available_encoders:
            dri_path = "/dev/dri/renderD128"
            if not os.path.exists(dri_path) and os.path.exists("/dev/dri/card0"):
                dri_path = "/dev/dri/card0"
            if os.path.exists(dri_path):
                return ffmpeg_exe, "h264_vaapi", ["-vaapi_device", dri_path, "-vf", "format=nv12,hwupload", "-qp", "20"]

        # 3. macOS
        if "h264_videotoolbox" in available_encoders:
            return ffmpeg_exe, "h264_videotoolbox", ["-b:v", "6000k"]

        # 4. Windows AMD (AMF)
        if "h264_amf" in available_encoders:
            return ffmpeg_exe, "h264_amf", ["-rc", "cqp", "-qp_i", "20", "-qp_p", "20"]

    # 5. CPU FALLBACK (Killer Mode / High-Res Fallback)
    preset = "ultrafast" if is_ultra_res else "veryfast"
    return ffmpeg_exe, "libx264", ["-preset", preset, "-crf", "18"]

def get_progress_color(progress: float) -> str:
    """Calculates hex color from Red to Green based on progress."""
    if progress < 0.5:
        r, g, b = 255, int(255 * (progress * 2)), 0
    else:
        r, g, b = int(255 * (1 - (progress - 0.5) * 2)), 255, 0
    return f'#{r:02x}{g:02x}{b:02x}'

def process_video(input_path: str, config: Dict[str, Any], engine: Any) -> None:
    # Metadata
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"\033[91m[-] Error: Could not open {input_path}\033[0m")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Scaling Logic
    cols = config["columns"]
    rows = int(cols * (h / w) * (config["c_w"] / config["c_h"]))
    out_w, out_h = cols * config["c_w"], rows * config["c_h"]
    
    # Get Config based on final output resolution
    ffmpeg_exe, encoder, enc_args = get_ffmpeg_config(out_w, out_h)
    
    # Diagnostic header (preserved your formatting)
    print(f"\n\033[94mOS:{platform.system()} | {platform.release()} | Resolution: {out_w}x{out_h} | Encoder:{encoder}\033[0m")

    ffmpeg_cmd = [
        ffmpeg_exe, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{out_w}x{out_h}", "-pix_fmt", "bgra", "-r", str(fps),
        "-i", "-", "-i", input_path, "-map", "0:v:0", "-map", "1:a:0?",
        "-c:v", encoder, *enc_args, "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", config["final_video_path"]
    ]
    
    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**8)
    chars = config["char_set"]
    start_time = time.time()
    frames_done = 0

    pbar = tqdm(
        total=total_frames, 
        unit="fr", 
        bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
        colour='#ff0000'
    )

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # GPU Sync & Processing
            small = cv2.resize(frame, (cols, rows))
            bgra_frame = cv2.cvtColor(small, cv2.COLOR_BGR2BGRA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            indices = (gray.astype(np.float32) * (len(chars) - 1) / 255.0).astype(np.uint32)
            packed_colors = bgra_frame.view(np.uint32).flatten()

            engine.submit_frame(indices, packed_colors, out_w, out_h)
            
            # Pipe Safety
            if len(engine.inflight_queue) >= engine.max_inflight:
                out_chunk = engine.get_finished_frame()
                if out_chunk is not None and process.stdin is not None:
                    try:
                        process.stdin.write(out_chunk.tobytes())
                    except BrokenPipeError:
                        _, err = process.communicate()
                        print(f"\n\033[91m[-] FFmpeg Pipe Error: {err.decode()}\033[0m")
                        break
            
            frames_done += 1
            
            # Live FPS Stats
            elapsed = time.time() - start_time
            curr_fps = frames_done / elapsed if elapsed > 0 else 0
            pbar.set_description(f"Rendering ({curr_fps:.1f} FPS)")
            pbar.colour = get_progress_color(frames_done / total_frames)
            pbar.update(1)

        # Finalize Remaining Frames
        while engine.inflight_queue:
            out_chunk = engine.get_finished_frame()
            if out_chunk is not None and process.stdin is not None:
                process.stdin.write(out_chunk.tobytes())

    except Exception:
        traceback.print_exc()
    finally:
        pbar.close()
        if process.stdin:
            process.stdin.close()
        process.wait()
        cap.release()

    # Final Summary
    total_time = time.time() - start_time
    avg_fps = frames_done / total_time if total_time > 0 else 0
    print(f"\n\033[92mRENDER COMPLETE\033[0m")
    print(f"Total Time: {total_time:.2f}s")
    print(f"Avg Speed:  {avg_fps:.2f} FPS\n")