import os
import sys
import subprocess
from djcrate.logger import logger

def check_dependency(cmd, name, install_url):
    """Returns (ok: bool, version: str). Check if a binary command line dependency exists."""
    try:
        result = subprocess.run(
            [cmd, '--version'], capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        version = (result.stdout or result.stderr).strip().splitlines()[0]
        return True, version
    except FileNotFoundError:
        return False, ''
    except Exception:
        return False, ''

def show_dependency_warning(app, name, install_url, detail):
    from PyQt6.QtWidgets import QMessageBox
    msg = QMessageBox()
    msg.setWindowTitle(f"DJ Crate — {name} Not Found")
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setText(f"<b>{name}</b> was not found on your system.")
    msg.setInformativeText(
        f"{detail}<br><br>"
        f"Install it from: <a href='{install_url}'>{install_url}</a><br>"
        "Then restart DJ Crate."
    )
    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg.exec()

def extract_file_audio_metadata(file_path: str) -> dict:
    """
    Extracts BPM, Key, Artist, Title, Album, Duration, and Bitrate from an audio file.
    Uses mutagen if available, with graceful fallback.
    """
    metadata = {
        'bpm': '',
        'key': '',
        'artist': '',
        'title': '',
        'album': '',
        'duration': 0,
        'bitrate': ''
    }

    if not os.path.exists(file_path):
        return metadata

    try:
        import mutagen
        audio = mutagen.File(file_path)
        if audio is not None:
            if hasattr(audio.info, 'length'):
                metadata['duration'] = int(audio.info.length)
            if hasattr(audio.info, 'bitrate') and audio.info.bitrate:
                metadata['bitrate'] = f"{int(audio.info.bitrate / 1000)} kbps"

            tags = audio.tags
            if tags:
                if hasattr(tags, 'get'):
                    bpm_tag = tags.get('TBPM') or tags.get('bpm') or tags.get('BPM')
                    if bpm_tag:
                        metadata['bpm'] = str(bpm_tag.text[0] if hasattr(bpm_tag, 'text') else bpm_tag).strip()
                    
                    key_tag = tags.get('TKEY') or tags.get('initialkey') or tags.get('key')
                    if key_tag:
                        metadata['key'] = str(key_tag.text[0] if hasattr(key_tag, 'text') else key_tag).strip()

                    artist_tag = tags.get('TPE1') or tags.get('artist') or tags.get('ARTIST')
                    if artist_tag:
                        metadata['artist'] = str(artist_tag.text[0] if hasattr(artist_tag, 'text') else artist_tag).strip()

                    title_tag = tags.get('TIT2') or tags.get('title') or tags.get('TITLE')
                    if title_tag:
                        metadata['title'] = str(title_tag.text[0] if hasattr(title_tag, 'text') else title_tag).strip()

                    album_tag = tags.get('TALB') or tags.get('album') or tags.get('ALBUM')
                    if album_tag:
                        metadata['album'] = str(album_tag.text[0] if hasattr(album_tag, 'text') else album_tag).strip()

    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Error parsing metadata for {file_path}: {e}")

    return metadata


class CamelotMatcher:
    """
    Intelligent Harmonic Key, BPM, and Vibe Matcher using Camelot Wheel Rules.
    """
    CAMELOT_WHEEL = [
        '1A', '1B', '2A', '2B', '3A', '3B', '4A', '4B',
        '5A', '5B', '6A', '6B', '7A', '7B', '8A', '8B',
        '9A', '9B', '10A', '10B', '11A', '11B', '12A', '12B'
    ]

    @staticmethod
    def parse_key(key_str: str) -> tuple:
        """Parses key string into (num: int, letter: str) e.g. '8A' -> (8, 'A')"""
        if not key_str:
            return None, None
        key_str = key_str.strip().upper()
        if len(key_str) >= 2 and key_str[:-1].isdigit() and key_str[-1] in ('A', 'B'):
            return int(key_str[:-1]), key_str[-1]
        return None, None

    @classmethod
    def calculate_key_match(cls, key1: str, key2: str) -> tuple:
        """
        Returns (score: float, match_type: str).
        Score range: 0.0 to 1.0.
        """
        n1, l1 = cls.parse_key(key1)
        n2, l2 = cls.parse_key(key2)

        if not n1 or not n2:
            return 0.5, "Unknown Key"

        if n1 == n2 and l1 == l2:
            return 1.0, "Exact Key Match"

        if n1 == n2 and l1 != l2:
            return 0.95, "Relative Major/Minor"

        # Adjacent wheel steps (+1 / -1)
        diff = abs(n1 - n2)
        if diff == 1 or diff == 11:
            if l1 == l2:
                return 0.90, "Harmonic Shift (+/- 1)"
            else:
                return 0.85, "Diagonal Energy Shift"

        # Energy Boost Jumps (+5 or +7 steps)
        step_diff = (n2 - n1) % 12
        if step_diff in (5, 7) and l1 == l2:
            return 0.85, "Energy Boost Jump"

        if diff == 2 or diff == 10:
            return 0.70, "2-Step Key Shift"

        return 0.40, "Key Distance"

    @staticmethod
    def calculate_bpm_match(bpm1: float, bpm2: float) -> tuple:
        """
        Returns (score: float, match_label: str).
        Score range: 0.0 to 1.0.
        Handles direct matches and half-time / double-time tempos.
        """
        if bpm1 <= 0 or bpm2 <= 0:
            return 0.5, "BPM Unknown"

        # Direct ratio
        ratio = bpm2 / bpm1
        
        # Check half-time / double-time
        best_diff = abs(1.0 - ratio)
        best_label = f"{round(bpm2)} BPM"

        if abs(0.5 - ratio) < best_diff:
            best_diff = abs(0.5 - ratio)
            best_label = f"{round(bpm2)} BPM (Half-time)"
        elif abs(2.0 - ratio) < best_diff:
            best_diff = abs(2.0 - ratio)
            best_label = f"{round(bpm2)} BPM (Double-time)"

        pct_diff = best_diff * 100.0

        if pct_diff <= 2.0:
            return 1.0, f"Perfect Tempo ({best_label})"
        elif pct_diff <= 5.0:
            return 0.90, f"Tight Tempo ({best_label})"
        elif pct_diff <= 8.0:
            return 0.75, f"Compatible Tempo ({best_label})"
        elif pct_diff <= 12.0:
            return 0.50, f"Tempo Stretch ({best_label})"
        else:
            return 0.20, f"Tempo Discrepancy ({best_label})"

    @classmethod
    def calculate_track_match(cls, source_track: dict, target_track: dict) -> dict:
        """
        Calculates overall match score (0 to 100%) between source and target track.
        Returns a rich result dict with score, labels, BPM values, and quality tier.
        """
        if source_track.get('path') == target_track.get('path'):
            return {'score': 0, 'label': 'Same Track', 'quality': '', 'key_label': '', 'bpm_label': '',
                    'source_key': '', 'target_key': '', 'source_bpm': '', 'target_bpm': '', 'is_harmonic': False}

        k1 = source_track.get('key', '')
        k2 = target_track.get('key', '')
        key_score, key_label = cls.calculate_key_match(k1, k2)

        b1 = float(source_track.get('bpm', 0)) if str(source_track.get('bpm', '')).isdigit() else 0.0
        b2 = float(target_track.get('bpm', 0)) if str(target_track.get('bpm', '')).isdigit() else 0.0
        bpm_score, bpm_label = cls.calculate_bpm_match(b1, b2)

        # Rating vibe bonus
        rating = target_track.get('rating', 0)
        rating_bonus = 0.05 if rating == 4 else (0.10 if rating == 5 else 0.0)

        # Final weighted score
        total_score = (key_score * 0.50) + (bpm_score * 0.40) + rating_bonus
        final_pct = min(100, int(total_score * 100))

        # Quality tier label
        is_harmonic = key_score >= 0.85 and bpm_score >= 0.75
        if final_pct >= 85:
            quality = "Perfect Mix"
        elif final_pct >= 70:
            quality = "Good Transition"
        elif final_pct >= 55:
            quality = "Workable"
        else:
            quality = "Risky"

        return {
            'score': final_pct,
            'quality': quality,
            'key_label': key_label,
            'bpm_label': bpm_label,
            'source_key': k1,
            'target_key': k2,
            'source_bpm': str(int(b1)) if b1 > 0 else '',
            'target_bpm': str(int(b2)) if b2 > 0 else '',
            'is_harmonic': is_harmonic
        }
