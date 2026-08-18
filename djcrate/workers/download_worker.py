"""
DownloadThread — Background yt-dlp audio download worker.

Spawns a ``yt-dlp`` sub-process to download and extract audio from YouTube,
SoundCloud, Bandcamp, or any yt-dlp-compatible URL.  Progress is parsed from
yt-dlp's ``--newline`` output and emitted as Qt signals so the UI can update
in real time without blocking the event loop.
"""

import os
import sys
import re
import time
import glob
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal


class DownloadThread(QThread):
    """
    QThread subclass that runs a ``yt-dlp`` download in the background.

    Signals
    -------
    progress(url, pct, speed, eta)
        Emitted after each parsed progress line from yt-dlp stdout.
    completed(url, ok, result)
        Emitted when the download finishes.  ``ok`` is True on success;
        ``result`` is the local file path on success or an error message on failure.
    log_line(url, line)
        Emitted for every raw output line from yt-dlp (for the log viewer).
    """

    progress = pyqtSignal(str, float, str, str)
    completed = pyqtSignal(str, bool, str)
    log_line = pyqtSignal(str, str)

    def __init__(self, url, title, download_dir, fmt, speed_limit_kbps=0, ytdlp_path='yt-dlp', ffmpeg_path='ffmpeg', cookies_path='', use_archive=False, parent=None):
        super().__init__(parent)
        self.url = url
        self.title = title
        self.download_dir = download_dir
        self.fmt = fmt
        self.speed_limit_kbps = speed_limit_kbps
        self.ytdlp_path = ytdlp_path or 'yt-dlp'
        self.ffmpeg_path = ffmpeg_path or 'ffmpeg'
        self.cookies_path = cookies_path
        self.use_archive = use_archive
        self.is_cancelled = False

    def run(self):
        start_time = time.time()
        os.makedirs(self.download_dir, exist_ok=True)

        output_template = os.path.join(self.download_dir, '%(title).200s.%(ext)s')

        args = [
            self.ytdlp_path, '-x',
            '--audio-format', self.fmt,
            '--audio-quality', '0',
            '-o', output_template,
            '--no-playlist',
            '--embed-metadata',
            '--extractor-args', 'youtube:player_client=android',
        ]
        
        if self.ffmpeg_path != 'ffmpeg':
            args.extend(['--ffmpeg-location', self.ffmpeg_path])

        if self.fmt != 'wav':
            args.append('--embed-thumbnail')

        if self.cookies_path and os.path.exists(self.cookies_path):
            args.extend(['--cookies', self.cookies_path])
            
        if self.use_archive:
            archive_file = os.path.join(self.download_dir, 'ytdlp_archive.txt')
            args.extend(['--download-archive', archive_file])

        if self.speed_limit_kbps > 0:
            args.extend(['--limit-rate', f'{self.speed_limit_kbps}K'])

        args.extend(['--newline', self.url])

        try:
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                creationflags=creationflags
            )

            final_path = None
            last_error = ""

            while True:
                if self.is_cancelled:
                    proc.terminate()
                    self.completed.emit(self.url, False, "Download cancelled")
                    return

                line = proc.stdout.readline()
                if not line:
                    break

                pct_match = re.search(r'(\d+(?:\.\d+)?)%', line)
                if pct_match:
                    pct = float(pct_match.group(1))
                    speed = ""
                    speed_match = re.search(r'at\s+(\S+iB/s|\S+B/s|\S+b/s)', line)
                    if speed_match:
                        speed = speed_match.group(1)
                    eta = ""
                    eta_match = re.search(r'ETA\s+(\d+:\d+|\d+:\d+:\d+)', line)
                    if eta_match:
                        eta = eta_match.group(1)
                    self.progress.emit(self.url, pct, speed, eta)
                
                self.log_line.emit(self.url, line.strip())
                
                if 'ERROR:' in line:
                    last_error = line.strip()

                if '[ExtractAudio] Destination:' in line:
                    final_path = line.split('[ExtractAudio] Destination:')[1].strip()
                elif '[download] Destination:' in line:
                    temp_path = line.split('[download] Destination:')[1].strip()
                    if not final_path:
                        final_path = temp_path

            proc.wait()

            if proc.returncode == 0:
                if not final_path or not os.path.exists(final_path):
                    time.sleep(0.5)
                    candidates = glob.glob(os.path.join(self.download_dir, f"*.{self.fmt}"))
                    if candidates:
                        newest = max(candidates, key=os.path.getmtime)
                        if os.path.getmtime(newest) >= start_time - 5:
                            final_path = newest

                if final_path and os.path.exists(final_path):
                    self.completed.emit(self.url, True, final_path)
                else:
                    self.completed.emit(self.url, False, "Could not determine downloaded file location")
            else:
                err_msg = last_error if last_error else f"yt-dlp download failed (code {proc.returncode})"
                self.completed.emit(self.url, False, err_msg)
        except Exception as e:
            self.completed.emit(self.url, False, str(e))
