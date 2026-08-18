import pytest
import os
import json
from unittest.mock import patch, MagicMock
from djcrate.updater import AutoUpdaterThread, UpdateDownloaderThread
from djcrate.app import _acquire_app_mutex

def test_updater_version_comparison():
    updater = AutoUpdaterThread()
    # Newer versions
    assert updater._is_newer_version("0.6.0", "0.5.0") is True
    assert updater._is_newer_version("1.0.0", "0.9.9") is True
    assert updater._is_newer_version("0.5.1", "0.5.0") is True
    assert updater._is_newer_version("v1.2.3", "v1.2.2") is True
    
    # Same or older versions
    assert updater._is_newer_version("0.5.0", "0.5.0") is False
    assert updater._is_newer_version("0.4.9", "0.5.0") is False
    assert updater._is_newer_version("0.3.0", "0.5.0") is False

def test_updater_asset_url_extraction():
    updater = AutoUpdaterThread(repo_owner="Dyvorn", repo_name="djcrate")
    
    mock_payload = {
        "tag_name": "v99.0.0",
        "html_url": "https://github.com/Dyvorn/djcrate/releases/tag/v99.0.0",
        "body": "Major performance updates.",
        "assets": [
            {
                "name": "checksums.txt",
                "browser_download_url": "https://github.com/Dyvorn/djcrate/releases/download/v99.0.0/checksums.txt"
            },
            {
                "name": "DJ_Crate_Installer.exe",
                "browser_download_url": "https://github.com/Dyvorn/djcrate/releases/download/v99.0.0/DJ_Crate_Installer.exe"
            }
        ]
    }
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        emitted_values = []
        updater.update_available.connect(lambda *args: emitted_values.append(args))
        
        updater.run()
        
        assert len(emitted_values) == 1
        version, body, html_url, installer_url = emitted_values[0]
        assert version == "v99.0.0"
        assert body == "Major performance updates."
        assert html_url == "https://github.com/Dyvorn/djcrate/releases/tag/v99.0.0"
        assert installer_url == "https://github.com/Dyvorn/djcrate/releases/download/v99.0.0/DJ_Crate_Installer.exe"

def test_update_downloader_thread_init():
    downloader = UpdateDownloaderThread("https://example.com/installer.exe", version="0.6.0")
    assert downloader.download_url == "https://example.com/installer.exe"
    assert downloader.version == "0.6.0"
    assert downloader._is_cancelled is False
    
    downloader.cancel()
    assert downloader._is_cancelled is True

def test_app_mutex_acquisition():
    # Should run cleanly without throwing exceptions
    _acquire_app_mutex()
