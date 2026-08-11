import os
import sys
import json
import subprocess
import tempfile
import urllib.request
from PyQt6.QtCore import QThread, pyqtSignal

class SearchThread(QThread):
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, query, source='YouTube', duration_filter='Any Duration', max_results=10, ytdlp_path='yt-dlp', cookies_path='', parent=None):
        super().__init__(parent)
        self.query = query
        self.source = source
        self.duration_filter = duration_filter
        self.max_results = max_results
        self.ytdlp_path = ytdlp_path or 'yt-dlp'
        self.cookies_path = cookies_path
        self.source_prefixes = {
            'YouTube': f'ytsearch{self.max_results}:',
            'SoundCloud': f'scsearch{self.max_results}:',
            'Bandcamp': f'bcsearch{self.max_results}:',
        }

    def run(self):
        is_url = self.query.startswith("http://") or self.query.startswith("https://")

        if is_url:
            args = [self.ytdlp_path, '--dump-json', '--no-download', '--flat-playlist', '--socket-timeout', '15', '--no-warnings', self.query]
        elif self.source == 'All Sources':
            all_results = []
            for src_name, prefix in self.source_prefixes.items():
                try:
                    partial = self._run_search(f"{prefix}{self.query}")
                    all_results.extend(partial)
                except Exception:
                    pass
            self.results_ready.emit(all_results)
            return
        else:
            prefix = self.source_prefixes.get(self.source, f'ytsearch{self.max_results}:')
            args = [self.ytdlp_path, '--dump-json', '--no-download', '--flat-playlist', '--socket-timeout', '15', '--no-warnings', f"{prefix}{self.query}"]

        if self.duration_filter == "Short (< 5m)":
            args.extend(['--match-filter', 'duration < 300'])
        elif self.duration_filter == "Medium (5-10m)":
            args.extend(['--match-filter', 'duration >= 300 & duration <= 600'])
        elif self.duration_filter == "Long (> 10m)":
            args.extend(['--match-filter', 'duration > 600'])

        if self.cookies_path and os.path.exists(self.cookies_path):
            args.extend(['--cookies', self.cookies_path])

        try:
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace',
                creationflags=creationflags
            )
            stdout, stderr = proc.communicate()

            if proc.returncode != 0:
                self.error_occurred.emit(f"Search failed: {stderr.strip() or 'yt-dlp returned an error'}")
                return

            results = self._parse_results(stdout)
            self.results_ready.emit(results)
        except FileNotFoundError:
            self.error_occurred.emit("yt-dlp executable not found. Make sure it is installed and added to PATH.")
        except Exception as e:
            self.error_occurred.emit(f"Search failed: {str(e)}")

    def _run_search(self, query_with_prefix):
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW
        args = [self.ytdlp_path, '--dump-json', '--no-download', '--flat-playlist',
                '--socket-timeout', '15', '--no-warnings', query_with_prefix]

        if self.duration_filter == "Short (< 5m)":
            args.extend(['--match-filter', 'duration < 300'])
        elif self.duration_filter == "Medium (5-10m)":
            args.extend(['--match-filter', 'duration >= 300 & duration <= 600'])
        elif self.duration_filter == "Long (> 10m)":
            args.extend(['--match-filter', 'duration > 600'])

        if self.cookies_path and os.path.exists(self.cookies_path):
            args.extend(['--cookies', self.cookies_path])

        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace',
            creationflags=creationflags
        )
        stdout, _ = proc.communicate()
        return self._parse_results(stdout)

    @staticmethod
    def _parse_results(stdout):
        results = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                dur = d.get('duration') or 0
                m = int(dur // 60)
                s = int(dur % 60)
                duration_str = f"{m}:{s:02d}"

                thumbnail = d.get('thumbnail', '')
                if not thumbnail and d.get('thumbnails'):
                    thumbnail = d['thumbnails'][-1].get('url', '')

                url = d.get('webpage_url') or d.get('url') or ''
                source_label = 'YouTube'
                if 'soundcloud.com' in url:
                    source_label = 'SoundCloud'
                elif 'bandcamp.com' in url:
                    source_label = 'Bandcamp'

                results.append({
                    'id': d.get('id', ''),
                    'title': d.get('title', 'Unknown'),
                    'artist': d.get('uploader') or d.get('channel') or d.get('artist') or 'Unknown',
                    'duration': duration_str,
                    'durationSecs': dur,
                    'url': url or f"https://www.youtube.com/watch?v={d.get('id')}",
                    'thumbnail': thumbnail,
                    'source': source_label
                })
            except Exception:
                pass
        return results

class ThumbnailDownloader(QThread):
    downloaded = pyqtSignal(str, str)

    def __init__(self, video_id, url, parent=None):
        super().__init__(parent)
        self.video_id = video_id
        self.url = url

    def run(self):
        if not self.url:
            return
        try:
            cache_dir = os.path.join(os.path.expanduser('~'), '.djcrate_cache', 'thumbs')
            os.makedirs(cache_dir, exist_ok=True)
            local_path = os.path.join(cache_dir, f"{self.video_id}.jpg")

            if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
                req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    with open(local_path, 'wb') as f:
                        f.write(response.read())

            self.downloaded.emit(self.video_id, local_path)
        except Exception:
            pass
