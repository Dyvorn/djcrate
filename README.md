<div align="center">

# 🎛️ DJ Crate

### *The High-Performance Desktop Companion for Modern DJs & Electronic Music Curators*

[![Release](https://img.shields.io/github/v/release/Dyvorn/djcrate?style=for-the-badge&color=C47D63)](https://github.com/Dyvorn/djcrate/releases)
[![Python Version](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-PyQt6-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://riverbankcomputing.com/software/pyqt/)
[![Tests](https://img.shields.io/badge/Tests-Passing%20(28%2F28)-00E676?style=for-the-badge&logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Dyvorn/djcrate/releases)

<p align="center">
  <b>Search</b> · <b>Extract</b> · <b>Harmonize</b> · <b>Tag</b> · <b>Sync to Serato & Rekordbox</b>
</p>

---

</div>

## 📌 Overview

**DJ Crate** is an advanced desktop workstation engineered specifically for DJs, selectors, and electronic music producers. It bridges the gap between digital discovery platforms (YouTube, SoundCloud, Bandcamp) and pro-DJ software (**Serato DJ Pro**, **Pioneer Rekordbox**, **Traktor Pro**, **VirtualDJ**).

Built on top of **PyQt6**, **SQLAlchemy**, and **yt-dlp**, DJ Crate delivers instant audio extraction, Librosa-driven BPM and Camelot harmonic key analysis, automatic ID3 tag enrichment, binary Serato crate generation, live OBS stream overlays, and intelligent set splitting.

---

## ✨ Core Capabilities

### 🎛️ 1. Authentic Pro-Audio Workstation & Customization
- **Tactile Console Aesthetics**: Deep obsidian and matte charcoal theme (`#0E0E10`, `#16161A`, `#1E1E24`, `#26262E`) with 1px precision borders and clean typography without blurry AI neon glow.
- **Custom Hex Color Picker & Hardware Presets**: Customize your console accent color to any hex value with live QSS theming, plus hardware presets (*Pioneer Blue, Technics Amber, Serato Red, Xone Slate, Emerald Green, Rust Amber*).
- **Library Density Modes**: Tailor your workspace density for high-DPI screens or compact DJ laptop displays (*Standard*, *Compact*, *Comfortable*).
- **Track Inspector Side Drawer**: Collapsible inspector displaying full ID3 metadata, Camelot keys, BPM, duration, format, file size, and quick actions (*Analyze, Edit Tags, Reveal in Explorer*).

### 🎧 2. Harmonic Mixing Engine & Live Pitch Shift
- **Camelot Quick-Filter Bar**: Scrollable strip of color-coded Camelot pills (`ALL`, `1A`–`12B`) to filter the library by key with one click.
- **Format & Status Filter Chips**: Instant filter chips for `ALL`, `MP3`, `WAV`, `FLAC`, `4★+`, and `Needs Analysis`.
- **Live Pitch & Semitone Transposition**: Moving the preview pitch fader (-20% to +20%) dynamically recalculates live effective BPM and transposed musical key (e.g. `128 BPM → 133.1 BPM (+4.0%) · 8A → 3A (+1 st)`).
- **Live Stream Previewing**: Stream and audition online tracks in real-time before downloading.
- **Interactive Hover Waveform Scrubber**: Dynamic hover time tooltip (`02:14`) tracking cursor position across the waveform with DJ quick jump (`-30s`, `-10s`, `+10s`, `+30s`) and pitch nudge (`-1%`, `+1%`) controls.
- **Match Assistant & Gig Matcher**: Surfaces the most compatible tracks in your library ranked by harmonic compatibility (Exact, Relative Major/Minor, +/-1 Step Energy Shift, and Energy Boost Jumps) and tempo proximity.

### 📁 3. Smart Crates & DJ Software Sync
- **Dynamic Smart Crates**: Define rule-based smart crates with numeric and harmonic operators (e.g., `BPM >= 126`, `Key compatible_with 8A`, `Rating >= 4`).
- **Native Binary Serato Crate Writer**: Automatically compiles native `.crate` binary structures directly into Serato's `_Serato_/Subcrates/` folder.
- **Multi-Format Playlist Exporters**: Export manual and smart crates to **M3U8** (with extended `#EXTINF` metadata), **CSV** (for Rekordbox and Excel), or **Formatted Text Tracklists** for Mixcloud and 1001Tracklists.
- **Drag & Drop Workflow**: Drag tracks directly out of DJ Crate into Serato DJ, Rekordbox, or your file system.

### ✂️ 4. Mix Splitter & Audio Processing
- **Timestamp Parsing Engine**: Paste YouTube/SoundCloud tracklists (e.g., `00:00 Artist - Track`, `03:45 Remix`) to automatically cut multi-hour DJ sets into individual, perfectly tagged audio files via FFmpeg.
- **SoundCloud Waveform Scrubber**: High-resolution waveform visualization with beat-grid cues, loudness meters (dBFS / peak clipping detection), and precision seeking.
- **Bulk Metadata Editor**: Batch-update Artist, Album, Genre, Year, and ID3 tags across multiple selected tracks simultaneously.

### 📡 5. Streamer & Live Performance HUDs
- **Live OBS Stream Overlay**: Automatically generates `now_playing.html` (glassmorphic animated stream widget) and `now_playing.txt` for OBS Studio and Streamlabs.
- **Floating Clipboard Grabber**: Non-intrusive bottom-right HUD that slides into view when a supported media URL is copied, enabling one-click background downloading without switching windows.
- **Always-On-Top Mini Player**: Ultra-compact 340×90px floating player designed to remain docked over Serato or Rekordbox during preparation sessions.
- **Keyboard Shortcuts Cheat Sheet**: Press `F1` or `?` anytime for an interactive DJ hotkey cheat sheet.

---

## 🏛️ System Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        PyQt6 UI Presentation Layer                     │
│  MainWindow  │  MiniPlayer  │  ClipboardHUD  │  GigMatcher  │ Dialogs │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ Qt Signals & Slots
┌──────────────────────────────────▼─────────────────────────────────────┐
│                     Asynchronous Worker Threadpool                     │
│  DownloadThread │ SearchThread │ AnalysisThread │ WaveformThread │ Split │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ Thread-safe Connection Pool
┌──────────────────────────────────▼─────────────────────────────────────┐
│                    Persistence & Audio Services Layer                  │
│  DatabaseManager (SQLite) │ SQLAlchemy ORM │ Mutagen Tagging │ Serato   │
└────────────────────────────────────────────────────────────────────────┘
```

### 📂 Repository Layout

```text
djcrate/
├── assets/                   # Application brand icons and visual assets
├── djcrate/                  # Core application package
│   ├── ui/                   # UI Presentation (MainWindow, Dialogs, Custom Widgets, Themes)
│   │   ├── main_window.py    # Primary application window & navigation
│   │   ├── mini_player.py    # Docked floating mini-player overlay
│   │   ├── clipboard_widget.py # Background clipboard capture HUD
│   │   ├── gig_matcher_widget.py # Live gig harmonic overlay
│   │   ├── dialogs.py        # Smart crate, metadata, and mix splitter dialogs
│   │   ├── widgets.py        # Waveform scrubber, track rows, rating stars, loudness meters
│   │   └── theme.py          # Dynamic QSS styling engine (Dark, OLED Black, Soft Slate)
│   │
│   ├── workers/              # Asynchronous background QThreads
│   │   ├── download_worker.py # yt-dlp audio stream extraction
│   │   ├── search_worker.py   # Multi-platform query parser
│   │   ├── metadata_worker.py # iTunes/Beatport API tagger & Librosa analysis
│   │   ├── split_worker.py    # FFmpeg mix splitter
│   │   └── waveform_worker.py # FFmpeg waveform & peak generator
│   │
│   ├── app.py                # Application entrypoint & dependency verification
│   ├── database.py           # DatabaseManager, SQLAlchemy models, and connection pooling
│   ├── config.py             # Settings manager & configuration abstraction
│   ├── logger.py             # Rotating logging and uncaught exception handler
│   ├── obs_overlay.py        # Live OBS stream widget generator
│   ├── serato.py             # Native Serato .crate binary serializer
│   ├── updater.py            # Automated GitHub release updater
│   └── utils.py              # Camelot harmonic matcher, pitch transposition, and audio helpers
│
├── tests/                    # Automated test suite
│   ├── conftest.py           # Pytest fixtures and database isolation
│   ├── test_database.py      # SQLite & SQLAlchemy CRUD and integrity tests
│   ├── test_exporters.py     # Serato .crate, OBS overlay, and playlist export tests
│   └── test_utils.py         # Camelot harmonic key, BPM, and pitch tests
│
├── build.spec                # PyInstaller packaging specification
├── djcrate_installer.iss     # Inno Setup Windows installer script
├── main.py                   # Root execution entrypoint
├── pytest.ini                # Pytest configuration
├── requirements.txt          # Production and development dependencies
└── LICENSE                   # MIT License
```

---

## 🚀 Installation & Quickstart

### Option A: Windows Installer (Recommended for DJs)
Download the latest executable installer from the **[Releases Tab](https://github.com/Dyvorn/djcrate/releases)** and launch the setup wizard.

### Option B: Running from Source (Developers)

#### 1. Prerequisites
- **[Python 3.11+](https://www.python.org/downloads/)**
- **[FFmpeg](https://ffmpeg.org/download.html)** (must be added to your system `PATH`)

#### 2. Clone & Install Dependencies
```bash
# Clone repository
git clone https://github.com/Dyvorn/djcrate.git
cd djcrate

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

#### 3. Launch DJ Crate
```bash
python main.py
```

---

## 🧪 Automated Testing

DJ Crate maintains a comprehensive test suite covering the database persistence layer, Camelot harmonic mathematics, audio metadata parsing, and binary playlist serialization.

Run the test suite with **pytest**:

```bash
pytest -v
```

```text
tests/test_database.py ..................                                [ 64%]
tests/test_exporters.py ...                                              [ 75%]
tests/test_utils.py .......                                              [100%]

============================= 28 passed in 0.67s ==============================
```

---

## 🎼 Camelot Harmonic Wheel Reference

DJ Crate's harmonic matcher evaluates energy transitions based on standard Camelot Wheel mathematics:

| Relationship | Rule | Transition Energy | Match Score |
| :--- | :--- | :--- | :---: |
| **Exact Match** | Same Key & Mode (`8A → 8A`) | Neutral / Smooth Blend | **100%** |
| **Relative Mode** | Same Number, Opposite Mode (`8A → 8B`) | Mood Shift (Minor/Major) | **95%** |
| **Harmonic Step** | Adjacent Step (`8A → 9A` or `8A → 7A`) | Subtle Energy Lift / Drop | **90%** |
| **Energy Boost** | +7 Camelot Steps (`1A → 8A`) | Noticeable Energy Spike | **85%** |
| **Diagonal Shift** | +1 Step, Opposite Mode (`8A → 9B`) | Complex Harmonic Shift | **85%** |

---

## 📦 Compiling Executables & Installers

### 1. Build Standalone Executable (PyInstaller)
```bash
pyinstaller build.spec
```
The compiled application will be generated in the `dist/DJ Crate/` directory.

### 2. Build Windows Installer (Inno Setup)
1. Open `djcrate_installer.iss` in **Inno Setup Compiler**.
2. Click **Build → Compile** (creates `DJ_Crate_Setup.exe`).

---

## 🤝 Contributing

Contributions, feature suggestions, and pull requests are warmly welcomed!
- Please read our [CONTRIBUTING.md](CONTRIBUTING.md) guide.
- Adhere to the [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

## 📜 License & Credits

- Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.
- Built with gratitude toward the open-source audio community (**yt-dlp**, **FFmpeg**, **Librosa**, **Mutagen**, **PyQt6**, **SQLAlchemy**). See [CREDITS.md](CREDITS.md).
