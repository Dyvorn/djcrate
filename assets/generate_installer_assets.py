"""
Script to generate clean, professional 24-bit BMP graphics for Inno Setup installer.
- installer_sidebar.bmp: 164x314 (Left banner)
- installer_header.bmp: 55x58 (Top right banner)
"""

import os
import math
from PIL import Image, ImageDraw, ImageFont

def generate_assets():
    assets_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(assets_dir, exist_ok=True)

    # 1. Installer Sidebar (164 x 314 px)
    sidebar_w, sidebar_h = 164, 314
    sidebar = Image.new('RGB', (sidebar_w, sidebar_h), color=(18, 18, 22))
    draw = ImageDraw.Draw(sidebar)

    # Dark studio background gradient
    for y in range(sidebar_h):
        ratio = y / sidebar_h
        r = int(24 - ratio * 10)
        g = int(24 - ratio * 10)
        b = int(30 - ratio * 12)
        draw.line([(0, y), (sidebar_w, y)], fill=(r, g, b))

    # Decorative subtle vinyl grooves / waveform curves
    center_x, center_y = 82, 140
    for radius in range(30, 95, 8):
        draw.arc([center_x - radius, center_y - radius, center_x + radius, center_y + radius], 
                 start=0, end=360, fill=(38, 38, 48), width=1)

    # Center turntable disc
    draw.ellipse([center_x - 30, center_y - 30, center_x + 30, center_y + 30], fill=(28, 28, 36), outline=(196, 125, 99), width=2)
    draw.ellipse([center_x - 10, center_y - 10, center_x + 10, center_y + 10], fill=(196, 125, 99))
    draw.ellipse([center_x - 3, center_y - 3, center_x + 3, center_y + 3], fill=(18, 18, 22))

    # Waveform bars at bottom
    wave_y = 250
    for i, bar_h in enumerate([8, 14, 22, 35, 28, 18, 32, 40, 26, 16, 24, 38, 30, 14, 8]):
        x = 24 + i * 8
        draw.rectangle([x, wave_y - bar_h // 2, x + 4, wave_y + bar_h // 2], fill=(196, 125, 99))

    # App Title & Subtitle
    try:
        font_title = ImageFont.truetype("arial.ttf", 16)
        font_sub = ImageFont.truetype("arial.ttf", 10)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.text((20, 268), "DJ CRATE", fill=(240, 240, 245), font=font_title)
    draw.text((20, 288), "Pro DJ Companion", fill=(140, 140, 150), font=font_sub)

    sidebar_path = os.path.join(assets_dir, "installer_sidebar.bmp")
    sidebar.save(sidebar_path, "BMP")
    print(f"Generated: {sidebar_path}")

    # 2. Installer Header (55 x 58 px)
    header_w, header_h = 55, 58
    header = Image.new('RGB', (header_w, header_h), color=(22, 22, 26))
    draw_h = ImageDraw.Draw(header)

    cx, cy = 27, 29
    draw_h.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(30, 30, 38), outline=(196, 125, 99), width=2)
    draw_h.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(196, 125, 99))
    draw_h.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(22, 22, 26))

    header_path = os.path.join(assets_dir, "installer_header.bmp")
    header.save(header_path, "BMP")
    print(f"Generated: {header_path}")

if __name__ == "__main__":
    generate_assets()
