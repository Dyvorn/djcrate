# Contributing to DJ Crate

First off, thank you for considering contributing to DJ Crate! It's people like you that make open source such a great community.

## 🛠️ Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/dj-crate.git
   cd dj-crate
   ```

2. **Set up a Virtual Environment:**
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: Ensure you have `yt-dlp` and `ffmpeg` installed on your system or placed in the project directory).*

4. **Run the App:**
   ```bash
   python main.py
   ```

## 📝 Pull Request Guidelines

- **Create a Branch:** Always branch off of `main` for your work. Name it descriptively (e.g., `feature/smart-crates`, `fix/ui-transparency`).
- **Keep it Focused:** Try to limit each PR to a single feature or bug fix.
- **Code Style:** We try to adhere to PEP 8. Please run a formatter like `black` or `ruff` before submitting.
- **Test:** Before opening a PR, run the app and manually verify your changes don't break existing UI transitions or downloads.

## 🐛 Found a Bug?

If you find a bug in the source code, you can help us by submitting an issue to our GitHub Repository using our Bug Report template.

Thanks again for your interest in making DJ Crate better!
