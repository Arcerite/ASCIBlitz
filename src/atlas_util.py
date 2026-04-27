import numpy as np
from PIL import Image, ImageDraw

def generate_gpu_atlas(font, chars, char_w, char_h):
    sheet_w = char_w * len(chars)
    sheet_h = char_h
    canvas = Image.new('L', (sheet_w, sheet_h), 0)
    draw = ImageDraw.Draw(canvas)
    
    for i, char in enumerate(chars):
        bbox = draw.textbbox((0, 0), char, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        # Center character in the cell
        off_x = (char_w - w) // 2
        off_y = (char_h - h) // 2
        draw.text((i * char_w + off_x, off_y), char, fill=255, font=font)
    
    # Thresholding: 128 is the cutoff for pure B&W
    atlas_np = np.array(canvas, dtype=np.uint8)
    return np.where(atlas_np > 127, 255, 0).astype(np.uint8)