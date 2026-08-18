import urllib.request
import json
import re
import os
import sys
import tempfile
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal, QCoreApplication
from djcrate import __version__
from djcrate.logger import logger

class AutoUpdaterThread(QThread):
    """
    Background worker thread that checks GitHub Releases API for updates.
    Repo target: https://github.com/Dyvorn/djcrate
    """
    # (version, body/notes, html_url, download_url)
    update_available = pyqtSignal(str, str, str, str)
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
                    
                    # Search for installer asset URL (.exe)
                    installer_url = ""
                    assets = data.get("assets", [])
                    for asset in assets:
                        asset_name = asset.get("name", "")
                        if asset_name.lower().endswith(".exe") and "installer" in asset_name.lower():
                            installer_url = asset.get("browser_download_url", "")
                            break
                    if not installer_url and assets:
                        for asset in assets:
                            if asset.get("name", "").lower().endswith(".exe"):
                                installer_url = asset.get("browser_download_url", "")
                                break

                    latest_clean = tag_name.lstrip("v")
                    current_clean = __version__.lstrip("v")

                    if self._is_newer_version(latest_clean, current_clean):
                        logger.info(f"Update available: {tag_name} (Current: {__version__})")
                        self.update_available.emit(tag_name, body, html_url, installer_url)
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


class UpdateDownloaderThread(QThread):
    """
    Downloads the new installer executable in the background with progress reporting.
    """
    progress = pyqtSignal(int, int)  # (bytes_downloaded, total_bytes)
    download_completed = pyqtSignal(str)  # local file path
    download_failed = pyqtSignal(str)

    def __init__(self, download_url: str, version: str = "latest", parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.version = version
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            target_dir = tempfile.gettempdir()
            filename = f"DJ_Crate_Installer_{self.version.replace('.', '_')}.exe"
            dest_path = os.path.join(target_dir, filename)

            headers = {
                "User-Agent": "DJCrate-AutoUpdater"
            }
            req = urllib.request.Request(self.download_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, 'wb') as out_file:
                total_size = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                chunk_size = 64 * 1024  # 64KB chunks

                while not self._is_cancelled:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    self.progress.emit(downloaded, total_size)

            if self._is_cancelled:
                try:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                except Exception:
                    pass
                return

            self.download_completed.emit(dest_path)
        except Exception as e:
            logger.error(f"Failed to download update: {e}")
            self.download_failed.emit(str(e))


def launch_installer_and_exit(installer_path: str):
    """
    Launches the downloaded installer executable and terminates the current application
    so that the installer can silently uninstall the old version and upgrade cleanly.
    """
    try:
        if sys.platform.startswith('win'):
            # Launch detached so the installer process continues independently
            subprocess.Popen([installer_path], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            subprocess.Popen([installer_path])
        
        # Gracefully exit the app
        app = QCoreApplication.instance()
        if app:
            app.quit()
        else:
            sys.exit(0)
    except Exception as e:
        logger.error(f"Error launching installer: {e}")
        try:
            os.startfile(installer_path)
            sys.exit(0)
        except Exception as e2:
            logger.error(f"Fallback os.startfile failed: {e2}")
