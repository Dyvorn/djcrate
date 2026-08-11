import os
import sys
import re
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal
from djcrate.logger import logger

class MixSplitterThread(QThread):
    progress = pyqtSignal(int, int, str) # current, total, track_title
    track_completed = pyqtSignal(str) # output file path
    all_finished = pyqtSignal(list) # list of output file paths
    error_occurred = pyqtSignal(str)

    def __init__(self, input_file, tracks_info, output_dir, ffmpeg_path='ffmpeg', parent=None):
        """
        tracks_info is a list of dicts:
        [
            {'start_sec': 0, 'end_sec': 195, 'title': 'Track 1', 'artist': 'Artist 1'},
            ...
        ]
        """
        super().__init__(parent)
        self.input_file = input_file
        self.tracks_info = tracks_info
        self.output_dir = output_dir
        self.ffmpeg_path = ffmpeg_path or 'ffmpeg'
        self.is_cancelled = False

    def run(self):
        if not os.path.exists(self.input_file):
            self.error_occurred.emit(f"Input file not found: {self.input_file}")
            return

        os.makedirs(self.output_dir, exist_ok=True)
        ext = self.input_file.rsplit('.', 1)[-1].lower()
        output_paths = []

        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW

        total = len(self.tracks_info)
        for idx, t_info in enumerate(self.tracks_info, start=1):
            if self.is_cancelled:
                break

            start_sec = t_info['start_sec']
            end_sec = t_info.get('end_sec')
            title = t_info.get('title', f"Track {idx}")
            artist = t_info.get('artist', '')

            # Clean filename
            safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
            if artist:
                safe_artist = re.sub(r'[\\/*?:"<>|]', "", artist).strip()
                out_filename = f"{idx:02d} - {safe_artist} - {safe_title}.{ext}"
            else:
                out_filename = f"{idx:02d} - {safe_title}.{ext}"

            out_path = os.path.join(self.output_dir, out_filename)

            self.progress.emit(idx, total, title)

            args = [
                self.ffmpeg_path, '-y',
                '-ss', str(start_sec)
            ]
            if end_sec is not None and end_sec > start_sec:
                args.extend(['-to', str(end_sec)])

            args.extend([
                '-i', self.input_file,
                '-c', 'copy',
                out_path
            ])

            try:
                proc = subprocess.run(
                    args, capture_output=True, text=True,
                    creationflags=creationflags, timeout=120
                )
                if proc.returncode == 0 and os.path.exists(out_path):
                    output_paths.append(out_path)
                    self.track_completed.emit(out_path)
                else:
                    logger.warning(f"FFmpeg copy failed for track {idx}, attempting re-encode...")
                    # Fallback to re-encode if stream copy fails
                    fallback_args = [
                        self.ffmpeg_path, '-y',
                        '-ss', str(start_sec)
                    ]
                    if end_sec is not None and end_sec > start_sec:
                        fallback_args.extend(['-to', str(end_sec)])
                    fallback_args.extend([
                        '-i', self.input_file,
                        out_path
                    ])
                    proc2 = subprocess.run(
                        fallback_args, capture_output=True, text=True,
                        creationflags=creationflags, timeout=300
                    )
                    if proc2.returncode == 0 and os.path.exists(out_path):
                        output_paths.append(out_path)
                        self.track_completed.emit(out_path)
            except Exception as e:
                logger.error(f"Error splitting track {title}: {e}")

        self.all_finished.emit(output_paths)
