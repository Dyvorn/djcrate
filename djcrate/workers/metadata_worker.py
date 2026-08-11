import os
import sys
import json
import subprocess
import urllib.parse
from PyQt6.QtCore import QThread, pyqtSignal

class MetadataProbeThread(QThread):
    metadata_ready = pyqtSignal(str, float, str)  # path, seconds, artist
    all_done = pyqtSignal()

    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        self.file_paths = file_paths

    def run(self):
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW

        for path in self.file_paths:
            try:
                args = [
                    'ffprobe', '-v', 'quiet',
                    '-show_entries', 'format=duration,tags=artist,ARTIST',
                    '-of', 'json', path
                ]
                result = subprocess.run(
                    args, capture_output=True, text=True,
                    encoding='utf-8', errors='replace',
                    creationflags=creationflags, timeout=10
                )
                data = json.loads(result.stdout)
                fmt = data.get('format', {})
                dur = float(fmt.get('duration', 0))
                
                artist = ""
                tags = fmt.get('tags', {})
                for key in tags:
                    if key.lower() == 'artist':
                        artist = tags[key]
                        break

                self.metadata_ready.emit(path, dur, artist)
            except Exception:
                pass
        self.all_done.emit()

class AnalysisThread(QThread):
    progress = pyqtSignal(str, str) # file_path, status message
    completed = pyqtSignal(str, dict) # file_path, {'bpm': bpm, 'key': key}
    error_occurred = pyqtSignal(str, str) # file_path, error message
    all_finished = pyqtSignal()

    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        self.file_paths = file_paths

    def _get_camelot_key(self, chroma, sr):
        import numpy as np
        major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        
        major = major / np.linalg.norm(major)
        minor = minor / np.linalg.norm(minor)

        chroma_sum = np.sum(chroma, axis=1)
        
        best_corr = -1
        best_key = "8A"
        
        camelot_major = ['8B', '3B', '10B', '5B', '12B', '7B', '2B', '9B', '4B', '11B', '6B', '1B']
        camelot_minor = ['5A', '12A', '7A', '2A', '9A', '4A', '11A', '6A', '1A', '8A', '3A', '10A']
        
        for i in range(12):
            shifted_major = np.roll(major, i)
            shifted_minor = np.roll(minor, i)
            
            corr_major = np.corrcoef(chroma_sum, shifted_major)[0,1]
            corr_minor = np.corrcoef(chroma_sum, shifted_minor)[0,1]
            
            if corr_major > best_corr:
                best_corr = corr_major
                best_key = camelot_major[i]
            
            if corr_minor > best_corr:
                best_corr = corr_minor
                best_key = camelot_minor[i]
                
        return best_key

    def run(self):
        try:
            import librosa
            import numpy as np
            import mutagen
            from mutagen.id3 import ID3, TKEY, TBPM, ID3NoHeaderError
            from mutagen.flac import FLAC
            from mutagen.wave import WAVE
            from mutagen.mp4 import MP4
        except ImportError as e:
            self.error_occurred.emit("ALL", f"Missing dependency: {e}")
            return

        for path in self.file_paths:
            if not os.path.exists(path):
                continue

            try:
                self.progress.emit(path, f"Analyzing BPM & Key...")
                # Fast 30s sample analysis
                y, sr = librosa.load(path, sr=22050, mono=True, duration=30)
                
                tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                bpm = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
                bpm_str = str(round(bpm))
                
                chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
                key_str = self._get_camelot_key(chroma, sr)
                
                self.progress.emit(path, f"Writing ID3 Tags: {bpm_str} BPM · {key_str}")
                
                ext = path.lower().rsplit('.', 1)[-1]
                if ext == 'mp3':
                    try:
                        audio = ID3(path)
                    except ID3NoHeaderError:
                        audio = ID3()
                    audio.add(TBPM(encoding=3, text=bpm_str))
                    audio.add(TKEY(encoding=3, text=key_str))
                    audio.save(path)
                elif ext == 'flac':
                    audio = FLAC(path)
                    audio['bpm'] = bpm_str
                    audio['key'] = key_str
                    audio.save()
                elif ext == 'wav':
                    try:
                        audio = WAVE(path)
                        if not audio.tags:
                            audio.add_tags()
                        audio.tags.add(TBPM(encoding=3, text=bpm_str))
                        audio.tags.add(TKEY(encoding=3, text=key_str))
                        audio.save()
                    except Exception:
                        pass
                elif ext in ('m4a', 'mp4'):
                    try:
                        audio = MP4(path)
                        audio.tags['tmpo'] = [int(bpm_str)]
                        audio.tags['----:com.apple.iTunes:initialkey'] = [key_str.encode('utf-8')]
                        audio.save()
                    except Exception:
                        pass

                self.completed.emit(path, {'bpm': bpm_str, 'key': key_str})
                
            except Exception as e:
                self.error_occurred.emit(path, str(e))

        self.all_finished.emit()

class AutoTagThread(QThread):
    progress = pyqtSignal(str, str)
    completed = pyqtSignal(str, dict)
    error_occurred = pyqtSignal(str, str)
    
    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        self.file_paths = file_paths
        
    def run(self):
        try:
            import requests
            import mutagen
            from mutagen.id3 import ID3, TCON, TDRC, APIC, ID3NoHeaderError
            from mutagen.flac import FLAC, Picture
            from mutagen.wave import WAVE
        except ImportError as e:
            self.error_occurred.emit("ALL", f"Missing dependency: {e}")
            return
            
        for path in self.file_paths:
            try:
                self.progress.emit(path, "Fetching metadata...")
                name = os.path.basename(path).rsplit('.', 1)[0]
                if ' - ' in name:
                    artist_str, title_str = name.split(' - ', 1)
                else:
                    artist_str, title_str = "", name
                
                query = f"{artist_str} {title_str}".strip()
                url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=song&limit=1"
                resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()

                genre, year, art_url = "", "", ""
                fetch_artist, fetch_title, fetch_album = "", "", ""

                if resp.get('results'):
                    track_info = resp['results'][0]
                    genre = track_info.get('primaryGenreName', '')
                    year = track_info.get('releaseDate', '')[:4]
                    art_url = track_info.get('artworkUrl100', '').replace('100x100bb.jpg', '600x600bb.jpg')
                    fetch_artist = track_info.get('artistName', '')
                    fetch_title = track_info.get('trackName', '')
                    fetch_album = track_info.get('collectionName', '')
                else:
                    self.progress.emit(path, "Searching Beatport catalog...")
                    bp_url = f"https://www.beatport.com/api/v4/catalog/search?q={urllib.parse.quote(query)}&per_page=1"
                    try:
                        bp_resp = requests.get(bp_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
                        if bp_resp.get('tracks'):
                            bp_track = bp_resp['tracks'][0]
                            fetch_title = bp_track.get('name', '')
                            fetch_artist = ", ".join([a.get('name', '') for a in bp_track.get('artists', [])])
                            fetch_album = bp_track.get('release', {}).get('name', '')
                            genre = bp_track.get('genre', {}).get('name', '')
                            year = bp_track.get('publish_date', '')[:4]
                            art_url = bp_track.get('release', {}).get('image', {}).get('uri', '')
                        else:
                            self.error_occurred.emit(path, "No match found on iTunes or Beatport")
                            continue
                    except Exception:
                        self.error_occurred.emit(path, "No match found on iTunes or Beatport")
                        continue
                
                img_data = None
                if art_url:
                    self.progress.emit(path, "Downloading artwork...")
                    img_resp = requests.get(art_url, timeout=5)
                    if img_resp.status_code == 200:
                        img_data = img_resp.content
                        
                self.progress.emit(path, "Writing tags...")
                
                from mutagen.id3 import TPE1, TIT2, TALB
                ext = path.lower().split('.')[-1]
                if ext == 'mp3':
                    try:
                        audio = ID3(path)
                    except ID3NoHeaderError:
                        audio = mutagen.id3.ID3()
                        
                    if genre: audio.add(TCON(encoding=3, text=genre))
                    if year: audio.add(TDRC(encoding=3, text=year))
                    if fetch_artist: audio.add(TPE1(encoding=3, text=fetch_artist))
                    if fetch_title: audio.add(TIT2(encoding=3, text=fetch_title))
                    if fetch_album: audio.add(TALB(encoding=3, text=fetch_album))
                    if img_data:
                        audio.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_data))
                    audio.save(path)
                    
                elif ext == 'flac':
                    audio = FLAC(path)
                    if genre: audio['genre'] = genre
                    if year: audio['date'] = year
                    if fetch_artist: audio['artist'] = fetch_artist
                    if fetch_title: audio['title'] = fetch_title
                    if fetch_album: audio['album'] = fetch_album
                    if img_data:
                        pic = Picture()
                        pic.type = 3
                        pic.mime = "image/jpeg"
                        pic.desc = "Cover"
                        pic.data = img_data
                        audio.add_picture(pic)
                    audio.save()
                    
                self.completed.emit(path, {
                    'genre': genre, 'year': year, 'has_art': bool(img_data),
                    'artist': fetch_artist, 'title': fetch_title, 'album': fetch_album
                })
            except Exception as e:
                self.error_occurred.emit(path, str(e))
