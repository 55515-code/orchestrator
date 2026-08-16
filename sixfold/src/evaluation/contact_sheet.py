#!/usr/bin/env python3
"""Build a contact sheet of two images side by side for comparison."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def sheet(images, out, cols=None, label=None, cell_w=720):
    imgs = [Image.open(p) for p in images]
    if cols is None:
        cols = len(imgs)
    rows = (len(imgs) + cols - 1) // cols
    cell_h = int(cell_w * imgs[0].size[1] / imgs[0].size[0])
    W = cell_w * cols
    H = cell_h * rows
    sheet = Image.new("RGB", (W, H), (8, 8, 8))
    for i, im in enumerate(imgs):
        im2 = im.resize((cell_w, cell_h), Image.LANCZOS)
        sheet.paste(im2, ((i % cols) * cell_w, (i // cols) * cell_h))
    if label:
        d = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 18)
        except Exception:
            font = ImageFont.load_default()
        d.text((10, 10), label, fill=(200, 200, 200), font=font)
    sheet.save(out)
    print(f"saved {out}")

if __name__ == "__main__":
    out = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else None
    sheet(sys.argv[3:], out, label=label)
