import os
import sys
import re
import hashlib
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal

class WaveformGeneratorThread(QThread):
    waveform_ready = pyqtSignal(str, str)         # file_path, image_path
    peaks_ready = pyqtSignal(str, list)           # file_path, list of float peaks (0.05 to 1.0)
    loudness_ready = pyqtSignal(str, float, float) # file_path, max_db, mean_db

    def __init__(self, file_path, cache_dir, ffmpeg_path='ffmpeg', accent_color='#FF5500', parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.cache_dir = cache_dir
        self.ffmpeg_path = ffmpeg_path
        self.accent_color = accent_color

    def run(self):
        file_hash = hashlib.md5(f"{self.file_path}_soundcloud_peaks".encode('utf-8')).hexdigest()
        img_path = os.path.join(self.cache_dir, f"{file_hash}.png")
        
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW

        # 1. Waveform peak extraction using librosa / numpy
        peaks = []
        try:
            import numpy as np
            import librosa
            y, sr = librosa.load(self.file_path, sr=8000, mono=True, duration=300)
            if len(y) > 0:
                num_samples = 160
                hop = max(1, len(y) // num_samples)
                for i in range(num_samples):
                    seg = y[i*hop : (i+1)*hop]
                    if len(seg) > 0:
                        peaks.append(float(np.max(np.abs(seg))))
                max_p = max(peaks) if peaks and max(peaks) > 0 else 1.0
                peaks = [max(0.08, min(1.0, float(p / max_p))) for p in peaks]
        except Exception:
            pass

        if peaks:
            self.peaks_ready.emit(self.file_path, peaks)

        # 2. Waveform image generation (White peaks for fallback)
        if not os.path.exists(img_path):
            os.makedirs(self.cache_dir, exist_ok=True)
            args = [
                self.ffmpeg_path, '-y', '-i', self.file_path,
                '-filter_complex', 'aformat=channel_layouts=mono,showwavespic=s=800x100:colors=0xFFFFFF',
                '-frames:v', '1', img_path
            ]
            try:
                proc = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
                if proc.returncode == 0 and os.path.exists(img_path):
                    self.waveform_ready.emit(self.file_path, img_path)
            except Exception:
                pass
        else:
            self.waveform_ready.emit(self.file_path, img_path)

        # 3. Volume & Loudness probe
        vol_args = [
            self.ffmpeg_path, '-hide_banner', '-i', self.file_path,
            '-af', 'volumedetect', '-f', 'null', '-'
        ]
        try:
            res = subprocess.run(vol_args, capture_output=True, text=True, errors='replace', creationflags=creationflags, timeout=8)
            stderr = res.stderr or ''
            max_match = re.search(r'max_volume:\s+([-\d\.]+)\s+dB', stderr)
            mean_match = re.search(r'mean_volume:\s+([-\d\.]+)\s+dB', stderr)
            max_db = float(max_match.group(1)) if max_match else 0.0
            mean_db = float(mean_match.group(1)) if mean_match else -14.0
            self.loudness_ready.emit(self.file_path, max_db, mean_db)
        except Exception:
            pass
