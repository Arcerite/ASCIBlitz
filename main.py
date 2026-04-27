import argparse
import os
import sys
import subprocess
import platform
import tkinter as tk
from tkinter import filedialog
from typing import Dict, Any, Optional
from PIL import ImageFont

# Deferred imports for faster startup
def get_engine_tools():
    from src.atlas_util import generate_gpu_atlas
    from src.engine import GPUBlitzEngine  # Ensure this matches your filename
    from src.video_handler import process_video # Ensure this matches your filename
    return generate_gpu_atlas, GPUBlitzEngine, process_video

PRESETS = {
    "1": {"name": "POTATO",     "cols": 80,   "w": 12, "h": 24},
    "2": {"name": "STANDARD",   "cols": 160,  "w": 9,  "h": 18},
    "3": {"name": "HIGH-RES",   "cols": 240,  "w": 8,  "h": 16},
    "4": {"name": "CINEMATIC",  "cols": 480,  "w": 5,  "h": 10},
    "5": {"name": "MASTERPIECE", "cols": 640, "w": 4,  "h": 8},
    "6": {"name": "EPIC",        "cols": 1024, "w": 3, "h": 6}, 
    "7": {"name": "ULTIMA",      "cols": 4096, "w": 1, "h": 2}, 
    "8": {"name": "CUSTOM",      "cols": 0,    "w": 0, "h": 0}
}

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def open_video(file_path: str):
    """Opens the video file using the system's default player."""
    try:
        if platform.system() == "Windows":
            os.startfile(file_path) # type: ignore
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(["open", file_path])
        else:  # Linux
            subprocess.Popen(
                ["xdg-open", file_path],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
    except Exception as e:
        print(f"\033[91m[-] Could not open video player: {e}\033[0m")

def get_input_file() -> Optional[str]:
    """Opens a native file explorer to select a video."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(
        title="Select Video for ASCII Blitzing",
        filetypes=[("Video Files", "*.mp4 *.mkv *.avi *.mov *.flv"), ("All Files", "*.*")]
    )
    root.destroy()
    return file_path if file_path and os.path.exists(file_path) else None

def get_unique_output_path(base_name: str) -> str:
    """Ensures outputs go to an /outputs folder and prevents overwriting."""
    out_dir = os.path.join(os.path.dirname(__file__), "outputs")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    name_part = os.path.splitext(base_name)[0]
    ext = ".mp4"
    
    counter = 0
    while True:
        suffix = f"_{counter}" if counter > 0 else ""
        candidate = os.path.join(out_dir, f"{name_part}{suffix}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1

def resolve_path(path: str) -> Optional[str]:
    if not path: return None
    p = os.path.abspath(path)
    if os.path.exists(p): return p
    script_p = os.path.join(os.path.dirname(__file__), path)
    if os.path.exists(script_p): return os.path.abspath(script_p)
    return None

def get_custom_config() -> Dict[str, int]:
    clear_screen()
    print("\033[96m" + "="*50)
    print("            CUSTOM CONFIGURATION")
    print("="*50 + "\033[0m")
    print("\033[93m[!] Warning: Above 4096px width, system swaps to CPU.\033[0m")
    print("\033[93m[!] Warning: Custom Configs are unstable at extreme resolutions.\033[0m\n")

    def prompt_int(message: str, default: Optional[int] = None) -> int:
        while True:
            display_msg = f"{message} [{default}]: " if default else f"{message}: "
            user_input = input(display_msg).strip()
            if not user_input and default is not None: return default
            try:
                val = int(user_input)
                if val <= 0: raise ValueError
                return val
            except ValueError:
                print("\033[91m    Invalid input. Enter a positive number.\033[0m")

    cols = prompt_int("Enter Column Count")
    w = prompt_int("Enter Character Width (Pixels)", default=4)
    h = prompt_int("Enter Character Height (Pixels)", default=w*2)
    return {"cols": cols, "w": w, "h": h}

def execute_blitz(config: Dict[str, Any]) -> bool:
    gen_atlas, Engine, processor = get_engine_tools()
    try:
        # Look inside the src folder for the font
        font_path = resolve_path("src/DejaVuSansMono.ttf") or "arial.ttf"
        font = ImageFont.truetype(font_path, 15)
        config["char_set"] = ".:;!+*?%S#$@@@@@@" 
        
        atlas = gen_atlas(font, config["char_set"], config["c_w"], config["c_h"])
        engine = Engine(config["c_w"], config["c_h"], atlas, config["columns"])
        
        processor(config["input_video_path"], config, engine)
        return True
    except Exception as e:
        print(f"\n\033[91m[-] Pipeline Error: {e}\033[0m")
        return False

def run_interactive():
    while True:
        clear_screen()
        print("\033[96m" + "="*45)
        print("       ⚡  ASCIIBLITZ INTERACTIVE v6.0  ⚡")
        print("="*45 + "\033[0m")
        
        print("\n[1] Select Video File")
        print("[Q] Quit")
        
        menu_choice = input("\nSelection > ").lower()
        if menu_choice == 'q': break
        if menu_choice != '1': continue
            
        src = get_input_file()
        if not src:
            input("\033[91m[-] No file selected. Press Enter...\033[0m")
            continue
            
        print(f"\033[92m[+] Loaded: {os.path.basename(src)}\033[0m")
        print("\nSelect Quality Preset:")
        for k in sorted(PRESETS.keys()):
            v = PRESETS[k]
            print(f" {k}) {v['name']:<12} | {v['cols'] if v['cols'] > 0 else '???'} Columns")
            
        choice = input("\nSelection > ")
        if choice in PRESETS:
            p = PRESETS[choice]
            
            if p["name"].strip() == "CUSTOM":
                custom = get_custom_config()
                p = {"name": "CUSTOM", **custom}
            
            # Generate unique path in /outputs
            out_path = get_unique_output_path(f"blitz_{p['name'].strip().lower()}")
            
            config = {
                "input_video_path": src,
                "final_video_path": out_path,
                "columns": p["cols"], 
                "c_w": p["w"], 
                "c_h": p["h"]
            }
            
            if execute_blitz(config):
                print(f"\n\033[92m[+] Success! Output saved to: {out_path}\033[0m")
                
                # The prompt
                watch = input("\n[?] Watch the render now? (y/n): ").lower()
                if watch == 'y':
                    open_video(out_path)
                
                input("\nPress Enter to return to menu...")
        else:
            input("\033[91m[-] Invalid selection. Press Enter...\033[0m")

def main():
    parser = argparse.ArgumentParser(description="High-Performance Video-to-ASCII via WGPU.")
    parser.add_argument("-i", "--input", help="Input video file")
    parser.add_argument("-p", "--preset", choices=PRESETS.keys(), help="Quality: 1-8")
    parser.add_argument("-o", "--out", help="Output filename")
    
    args = parser.parse_args()

    if args.input and args.preset:
        src = resolve_path(args.input)
        if not src: print(f"Error: {args.input} not found."); sys.exit(1)
        
        p = PRESETS[args.preset]
        # Use CLI out name or generate a unique one
        out_path = args.out if args.out else get_unique_output_path(f"blitz_{p['name'].strip().lower()}")
        
        config = {
            "input_video_path": src, "final_video_path": out_path,
            "columns": p["cols"], "c_w": p["w"], "c_h": p["h"]
        }
        execute_blitz(config)
    else:
        run_interactive()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\033[93m[!] Aborted by user.\033[0m")
        sys.exit(0)