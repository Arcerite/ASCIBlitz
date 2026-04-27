# ⚡ ASCIIBLITZ v7.0

A high-performance, GPU-accelerated video-to-ASCII reconstruction engine using WGPU and FFmpeg.
## 🚀 Features

GPU Powered!: Uses custom Compute Shaders for real-time ASCII synthesis.

Hardware Agnostic!: Automatically detects Vulkan, Metal, D3D12, or VAAPI.

Smart I/O!: Integrated Native File Explorer and Auto-Versioning (prevents overwriting your renders).

Audio Preservation!: Keeps the original audio track synced with your ASCII masterpiece.

Auto-Encoder!: Smart detection for NVIDIA (NVENC), AMD (AMF), Intel (VAAPI), or Apple encoders.

## 🛠️ Installation

Ensure you have FFmpeg installed (Windows users: place ffmpeg.exe in the bin/ folder).

Install dependencies:

    pip install -r requirements.txt

## 💻 Usage

You can now run the script without arguments to enter the Interactive Menu:


    python main.py

The menu will open a file explorer for you to select your video and choose a preset.

CLI Mode (Advanced):


    python main.py -i input.mp4 -p 4 -o custom_name.mp4

## 📊 Quality Presets
| Preset | Name | Column Count | Vibe |
| :--- | :--- | :--- | :--- |
| 1 | POTATO | 80 | Classic Retro Terminal |
| 2 | STANDARD | 160 | Readable ASCII Art |
| 4 | CINEMATIC | 480 | Polished & Smooth |
| 5 | MASTERPIECE | 640 | Almost Original |
| 6 | EPIC | 1024 | High Fidelity |
| 7 | ULTIMA | 4096 | Perfection |
| 8 | CUSTOM | User Defined | Total Control |


## 📜 Credits

ASCII Engine: Developed by Caleb Peters.
Font: DejaVu Sans Mono.

## ⚖️ License

MIT - Caleb Peters
