# 🎛️ DJ Crate

**DJ Crate** is a powerful desktop companion application for DJs, designed to streamline your workflow by integrating YouTube and SoundCloud directly into your music management process. Built with Python and PyQt6, DJ Crate allows you to search, download, organize, and preview tracks seamlessly.

---

## ✨ Features

- **Search & Discover:** Quickly search YouTube and SoundCloud for tracks, remixes, and sets.
- **Fast Downloading:** Powered by `yt-dlp` for high-quality, reliable audio extraction.
- **Advanced Metadata Engine:** Automatically hits the iTunes API to download high-res cover art and embeds official ID3 tags (Artist, Title, Album) directly into the file.
- **SQLite Database:** Lightning-fast library management, smart crate queries, and reliable download history backing.
- **Waveform & Key Analysis:** Uses `ffmpeg` and `librosa` to analyze BPM, Camelot Key, and generate waveforms to preview drops instantly.
- **Smart Crates:** Automatically organize your library based on BPM, Key, or Title rules.
- **Mini Player:** A compact overlay player to listen to tracks while you do other tasks.
- **Theming:** Beautiful, customizable PyQt6 user interface with dynamic theming.

---

## 🛠️ Technology Stack

- **[Python 3.11+](https://www.python.org/)** - Core programming language.
- **[PyQt6](https://riverbankcomputing.com/software/pyqt/)** - Modern, responsive GUI framework.
- **[SQLite](https://www.sqlite.org/)** - Built-in relational database for robust library management.
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** - Backend engine for downloading media.
- **[FFmpeg](https://ffmpeg.org/) & [Librosa](https://librosa.org/)** - Audio conversion, key/BPM analysis, and waveform generation.
- **[Mutagen](https://mutagen.readthedocs.io/)** - For embedding ID3 metadata and cover art.
- **[PyInstaller](https://pyinstaller.org/) & [Inno Setup](https://jrsoftware.org/isinfo.php)** - Packaging and Windows Installer generation.

---

## 📂 Project Structure

DJ Crate is built with a modular architecture to separate the user interface from heavy background processing:

```text
djcrate/
├── .github/                  # GitHub Actions workflows for automated releases
├── assets/                   # Application icons and images
├── djcrate/                  # Core application package
│   ├── ui/                   # User Interface components
│   │   ├── main_window.py    # Main application window and layout
│   │   ├── mini_player.py    # Compact player overlay
│   │   ├── dialogs.py        # Settings and prompt dialogs
│   │   ├── widgets.py        # Reusable custom PyQt6 widgets
│   │   └── theme.py          # Stylesheet and color management
│   │
│   ├── workers/              # Asynchronous background threads (QThread)
│   │   ├── download_worker.py # Handles media downloading
│   │   ├── search_worker.py   # Handles YouTube/SoundCloud searching
│   │   ├── metadata_worker.py # iTunes metadata, tag embedding, and Librosa analysis
│   │   └── waveform_worker.py # Generates audio waveforms via FFmpeg
│   │
│   ├── app.py                # Main QApplication initialization and dependency checks
│   ├── database.py           # SQLite manager for crates, tracks, and settings
│   ├── config.py             # Settings manager and database abstraction
│   ├── logger.py             # Application logging and error handling
│   └── utils.py              # Helper functions (dependency checks, metadata extraction)
│
├── build.spec                # PyInstaller configuration for building the .exe
├── djcrate_installer.iss     # Inno Setup script to compile the Windows installer
├── main.py                   # The main entry point script to launch the app
└── RELEASE_INSTRUCTIONS.md   # Guide for triggering automated GitHub releases
```

---

## 🚀 Installation & Setup

### For Users
Simply download the latest installer from the **[Releases Tab](https://github.com/Dyvorn/djcrate/releases)** and run it on your Windows machine.

### For Developers
1. Clone the repository:
   ```bash
   git clone https://github.com/Dyvorn/djcrate.git
   cd djcrate
   ```
2. Install Python dependencies:
   ```bash
   pip install PyQt6 yt-dlp Pillow qtawesome mutagen
   ```
3. Ensure **FFmpeg** is installed and added to your System PATH.
4. Run the app locally:
   ```bash
   python main.py
   ```

---

## 📦 Building from Source

This project uses a GitHub Actions workflow to automatically build and publish the `.exe`. However, you can build it manually:

1. **Create the Executable:**
   ```bash
   pyinstaller build.spec
   ```
2. **Create the Installer (Windows only):**
   Open `djcrate_installer.iss` in **Inno Setup** and compile it.

---

## 🤖 AI Assistance Notice

> **Note on AI-Assisted Development:**  
> Portions of this codebase, including this documentation, architecture design, and specific module implementations, were developed with the assistance of Artificial Intelligence (AI). AI tools were used to accelerate development, write boilerplate code, troubleshoot bugs, and generate UI layouts. All AI-generated code has been reviewed, modified, and tested by human developers to ensure security, performance, and functionality.

---

## 📜 License & Credits

- See `LICENSE` for distribution rights.
- See `CREDITS.md` for acknowledgments to the open-source libraries used.
- Please check `CONTRIBUTING.md` if you wish to help improve DJ Crate!
