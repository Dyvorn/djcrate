# Credits & Acknowledgements

DJ Crate stands on the shoulders of giants. We'd like to extend our deepest gratitude to the following open-source projects that make this application possible:

## Core Dependencies

* **[yt-dlp](https://github.com/yt-dlp/yt-dlp)**: The incredible backbone of our downloading engine. Without yt-dlp, fetching audio from various platforms would be nearly impossible.
* **[FFmpeg](https://ffmpeg.org/)**: The industry standard for audio and video processing. DJ Crate relies on FFmpeg for audio conversion, metadata embedding, and generating waveform visualisations.
* **[Librosa](https://librosa.org/)**: Powers our audio analysis engine, enabling accurate BPM and Key detection.
* **[PyQt6](https://riverbankcomputing.com/software/pyqt/)**: The robust Python binding for the Qt cross-platform UI framework that powers our desktop interface.
* **[QtAwesome](https://github.com/spyder-ide/qtawesome)**: Provides all the beautiful font icons (FontAwesome) used throughout the application UI.
* **[Mutagen](https://mutagen.readthedocs.io/)**: Used heavily for parsing and writing ID3 metadata tags (including high-res cover art) directly into our audio files.
* **[Requests](https://requests.readthedocs.io/)**: Used to interface with the Apple iTunes API for pulling accurate metadata and album art.

## Inspiration
Inspired by the workflows of professional DJ software like Serato, Rekordbox, and Mixxx. DJ Crate is designed to be the ultimate companion tool for these platforms.
