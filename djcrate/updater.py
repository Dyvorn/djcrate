import urllib.request
import json
import re
from PyQt6.QtCore import QThread, pyqtSignal
from djcrate import __version__
from djcrate.logger import logger

class AutoUpdaterThread(QThread):
    """
    Background worker thread that checks GitHub Releases API for updates.
    Repo target: https://github.com/Dyvorn/djcrate
    """
    update_available = pyqtSignal(str, str, str)  # (version, body/notes, html_url)
    no_update_found = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, repo_owner="Dyvorn", repo_name="djcrate", parent=None):
        super().__init__(parent)
        self.repo_owner = repo_owner
        self.repo_name = repo_name

    def run(self):
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        headers = {
            "User-Agent": "DJCrate-AutoUpdater",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    tag_name = data.get("tag_name", "").strip()
                    html_url = data.get("html_url", f"https://github.com/{self.repo_owner}/{self.repo_name}/releases")
                    body = data.get("body", "No release notes provided.")

                    latest_clean = tag_name.lstrip("v")
                    current_clean = __version__.lstrip("v")

                    if self._is_newer_version(latest_clean, current_clean):
                        logger.info(f"Update available: {tag_name} (Current: {__version__})")
                        self.update_available.emit(tag_name, body, html_url)
                    else:
                        logger.info(f"App is up to date (Current: {__version__}, Latest: {tag_name})")
                        self.no_update_found.emit()
                else:
                    self.no_update_found.emit()
        except Exception as e:
            logger.debug(f"Auto-updater check skipped/failed: {e}")
            self.error_occurred.emit(str(e))

    def _is_newer_version(self, latest: str, current: str) -> bool:
        def parse_version(v: str):
            return [int(x) for x in re.findall(r'\d+', v)]
        try:
            return parse_version(latest) > parse_version(current)
        except Exception:
            return False
