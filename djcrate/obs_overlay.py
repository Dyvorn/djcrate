import os
from djcrate.logger import logger

class ObsOverlayWriter:
    """
    Generates now_playing.txt and a sleek glassmorphic now_playing.html overlay
    for OBS Studio / Streamlabs stream widgets.
    """
    @staticmethod
    def get_overlay_dir():
        app_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'DJ Crate', 'obs')
        os.makedirs(app_dir, exist_ok=True)
        return app_dir

    @classmethod
    def update_now_playing(cls, title: str, artist: str = "", bpm: str = "", key: str = "", accent_color: str = "#FF5500"):
        overlay_dir = cls.get_overlay_dir()

        txt_path = os.path.join(overlay_dir, "now_playing.txt")
        html_path = os.path.join(overlay_dir, "now_playing.html")

        # Format plain text file
        parts = []
        if artist: parts.append(artist)
        if title: parts.append(title)
        txt_content = " - ".join(parts) if parts else "No Track Playing"

        meta_parts = []
        if bpm: meta_parts.append(f"{bpm} BPM")
        if key: meta_parts.append(f"Key {key}")
        if meta_parts:
            txt_content += f" [{ ' · '.join(meta_parts) }]"

        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(txt_content)
        except Exception as e:
            logger.error(f"Error writing now_playing.txt: {e}")

        # Format HTML widget file with auto-refresh & glassmorphism
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="3">
    <title>DJ Crate OBS Overlay</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;800&display=swap');
        body {{
            margin: 0;
            padding: 10px;
            background: transparent;
            font-family: 'Inter', sans-serif;
            color: #FFFFFF;
            overflow: hidden;
        }}
        .card {{
            display: inline-flex;
            align-items: center;
            gap: 12px;
            background: rgba(18, 16, 16, 0.85);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-left: 4px solid {accent_color};
            border-radius: 10px;
            padding: 10px 18px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
        }}
        .icon {{
            width: 24px;
            height: 24px;
            border-radius: 50%;
            background: {accent_color};
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
        }}
        .info {{
            display: flex;
            flex-direction: column;
        }}
        .title {{
            font-size: 14px;
            font-weight: 800;
            color: #FFFFFF;
            letter-spacing: 0.5px;
        }}
        .artist {{
            font-size: 12px;
            color: #A39E9A;
            font-weight: 600;
        }}
        .badge {{
            background: rgba(255, 85, 0, 0.15);
            border: 1px solid {accent_color};
            color: {accent_color};
            font-size: 10px;
            font-weight: 800;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 6px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
        </div>
        <div class="info">
            <div class="title">{title or 'DJ Crate'} {f'<span class="badge">{key}</span>' if key else ''}</div>
            <div class="artist">{artist or 'Stream Companion'} {f'· {bpm} BPM' if bpm else ''}</div>
        </div>
    </div>
</body>
</html>
"""
        try:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        except Exception as e:
            logger.error(f"Error writing now_playing.html: {e}")
