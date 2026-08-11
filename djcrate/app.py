import sys
import os

# Set QtMultimedia backend to native Windows Media Foundation
os.environ.setdefault("QT_MEDIA_BACKEND", "windows")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from djcrate.logger import logger, exception_hook
from djcrate.utils import check_dependency, show_dependency_warning
from djcrate.ui.main_window import MainWindow

def main():
    sys.excepthook = exception_hook

    app = QApplication(sys.argv)
    app.setApplicationName("DJ Crate")
    app.setOrganizationName("DJ Crate")

    # Dependency checks
    ytdlp_ok, ytdlp_ver = check_dependency('yt-dlp', 'yt-dlp', 'https://github.com/yt-dlp/yt-dlp#installation')
    ffmpeg_ok, ffmpeg_ver = check_dependency('ffmpeg', 'FFmpeg', 'https://ffmpeg.org/download.html')

    if not ytdlp_ok:
        show_dependency_warning(
            app, 'yt-dlp', 'https://github.com/yt-dlp/yt-dlp#installation',
            'yt-dlp is required for downloading audio from YouTube and SoundCloud.'
        )

    if not ffmpeg_ok:
        show_dependency_warning(
            app, 'FFmpeg', 'https://ffmpeg.org/download.html',
            'FFmpeg is required for converting audio formats and generating waveform visualizers.'
        )

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()
