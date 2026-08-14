import os
import sys
import math
import subprocess
from typing import Any, Optional, Dict, Tuple, List
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


def get_track_artwork(file_path: str):
    """
    Extracts the embedded cover art from an audio file.
    Returns bytes of the image, or None if no artwork exists.
    """
    if not os.path.exists(file_path):
        return None
    try:
        import mutagen
        audio = mutagen.File(file_path)
        if audio is None:
            return None
        
        # ID3 (MP3)
        if hasattr(audio, 'tags') and audio.tags:
            for tag in audio.tags.values():
                if tag.__class__.__name__ == 'APIC':
                    return tag.data
        
        # FLAC
        if hasattr(audio, 'pictures') and audio.pictures:
            return audio.pictures[0].data
            
    except Exception as e:
        logger.debug(f"Error extracting artwork for {file_path}: {e}")
    return None


class CamelotMatcher:
    """
    Intelligent Harmonic Key, BPM, and Vibe Matcher using the Camelot Wheel system.

    The Camelot Wheel maps musical keys to numbers (1–12) and letters (A=minor, B=major).
    Compatible keys are adjacent on the wheel (+/−1 step) or share the same number
    (relative major/minor). BPM matching allows for direct, half-time, and double-time
    relationships.

    Public API
    ----------
    calculate_match_score(key1, bpm1, key2, bpm2) -> (score, key_quality, bpm_quality)
        Compact entry point used by GigMatcherWidget and any consumer needing a flat score.

    calculate_track_match(source_track, target_track) -> dict
        Rich result dict used by LibraryTrackRow match badges and filter_library sorting.

    get_compatible_keys(key_str) -> dict
        Dictionary of harmonically compatible keys mapped by relationship.

    calculate_pitch_shifted_state(bpm, key_str, pitch_pct) -> dict
        Calculates real-time effective tempo and transposed Camelot key under pitch adjustment.

    get_camelot_color(key_str) -> str
        Returns UI accent hex color code according to Camelot harmonic wheel position.
    """
    CAMELOT_WHEEL = [
        '1A', '1B', '2A', '2B', '3A', '3B', '4A', '4B',
        '5A', '5B', '6A', '6B', '7A', '7B', '8A', '8B',
        '9A', '9B', '10A', '10B', '11A', '11B', '12A', '12B'
    ]

    CAMELOT_COLORS = {
        1: '#00E5FF',   # 1A/1B (Aqua Cyan)
        2: '#00B0FF',   # 2A/2B (Sky Blue)
        3: '#2979FF',   # 3A/3B (Royal Blue)
        4: '#651FFF',   # 4A/4B (Deep Purple)
        5: '#AA00FF',   # 5A/5B (Purple)
        6: '#F50057',   # 6A/6B (Magenta)
        7: '#FF1744',   # 7A/7B (Red)
        8: '#FF5252',   # 8A/8B (Coral Red)
        9: '#FF9100',   # 9A/9B (Warm Orange)
        10: '#FFD600',  # 10A/10B (Gold)
        11: '#AEEA00',  # 11A/11B (Lime)
        12: '#00E676',  # 12A/12B (Emerald Green)
    }

    @staticmethod
    def parse_key(key_str: str) -> tuple:
        """Parses key string into (num: int, letter: str) e.g. '8A' -> (8, 'A')"""
        if not key_str:
            return None, None
        key_str = str(key_str).strip().upper()
        if len(key_str) >= 2 and key_str[:-1].isdigit() and key_str[-1] in ('A', 'B'):
            num = int(key_str[:-1])
            if 1 <= num <= 12:
                return num, key_str[-1]
        return None, None

    @classmethod
    def get_camelot_color(cls, key_str: str) -> str:
        """Returns standard hex color code for a Camelot key."""
        n, _ = cls.parse_key(key_str)
        if n and n in cls.CAMELOT_COLORS:
            return cls.CAMELOT_COLORS[n]
        return '#8A8580'

    @classmethod
    def get_compatible_keys(cls, key_str: str) -> dict:
        """
        Returns a dictionary of harmonic keys compatible with ``key_str``:
        - exact: Same key (100%)
        - relative: Relative major/minor (95%)
        - energy_plus: +1 Camelot step (90%)
        - energy_minus: -1 Camelot step (90%)
        - energy_boost_plus: +7 steps (85%)
        - energy_boost_minus: +5 steps (85%)
        - diagonal_plus: +1 step opposite letter (85%)
        - diagonal_minus: -1 step opposite letter (85%)
        - all_keys: full list of compatible Camelot keys
        """
        n, l = cls.parse_key(key_str)
        if not n or not l:
            return {'all_keys': []}

        opp_l = 'B' if l == 'A' else 'A'
        plus_1 = 1 if n == 12 else n + 1
        minus_1 = 12 if n == 1 else n - 1
        boost_plus = ((n - 1 + 7) % 12) + 1
        boost_minus = ((n - 1 + 5) % 12) + 1

        res = {
            'exact': f"{n}{l}",
            'relative': f"{n}{opp_l}",
            'energy_plus': f"{plus_1}{l}",
            'energy_minus': f"{minus_1}{l}",
            'energy_boost_plus': f"{boost_plus}{l}",
            'energy_boost_minus': f"{boost_minus}{l}",
            'diagonal_plus': f"{plus_1}{opp_l}",
            'diagonal_minus': f"{minus_1}{opp_l}",
        }
        res['all_keys'] = [
            res['exact'], res['relative'], res['energy_plus'], res['energy_minus'],
            res['energy_boost_plus'], res['energy_boost_minus'],
            res['diagonal_plus'], res['diagonal_minus']
        ]
        return res

    @classmethod
    def calculate_pitch_shifted_state(cls, bpm: Any, key_str: str, pitch_pct: float) -> dict:
        """
        Calculates live effective BPM and musical semitone key transposition
        when adjusting the DJ pitch slider (-20% to +20%).
        """
        try:
            b = float(bpm) if bpm and str(bpm).replace('.', '', 1).isdigit() else 0.0
        except (ValueError, TypeError):
            b = 0.0

        rate = 1.0 + (pitch_pct / 100.0)
        rate = max(0.01, rate)
        
        effective_bpm = round(b * rate, 1) if b > 0 else 0.0
        bpm_diff = round(effective_bpm - b, 1) if b > 0 else 0.0

        # Semitone shift = 12 * log2(rate)
        semitones = 12.0 * math.log2(rate)
        semitones_rounded = int(round(semitones))

        n, l = cls.parse_key(key_str)
        transposed_key = key_str
        if n and l and semitones_rounded != 0:
            # Shift by semitones: Each semitone = +7 Camelot steps (Circle of Fifths)
            new_n = ((n - 1 + semitones_rounded * 7) % 12) + 1
            transposed_key = f"{new_n}{l}"

        sign = "+" if pitch_pct > 0 else ""
        bpm_sign = "+" if bpm_diff > 0 else ""
        
        return {
            'rate': rate,
            'pitch_pct': pitch_pct,
            'pitch_str': f"{sign}{pitch_pct:.1f}%",
            'original_bpm': b,
            'effective_bpm': effective_bpm,
            'bpm_diff': bpm_diff,
            'bpm_str': f"{effective_bpm:.1f} BPM" if effective_bpm > 0 else "",
            'original_key': key_str,
            'transposed_key': transposed_key,
            'semitones': round(semitones, 2),
            'semitones_rounded': semitones_rounded,
            'is_transposed': (transposed_key != key_str and bool(key_str)),
            'display_text': f"{effective_bpm:.1f} BPM ({bpm_sign}{bpm_diff:.1f})" if effective_bpm > 0 else f"{sign}{pitch_pct:.1f}%"
        }

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

        # Rating vibe bonus: 4-star adds 5% to score, 5-star adds 10%.
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

    @classmethod
    def calculate_match_score(cls, key1: str, bpm1: str, key2: str, bpm2: str) -> tuple:
        """
        Compact entry point returning ``(score: int, key_quality: str, bpm_quality: str)``.
        """
        key_score, key_quality = cls.calculate_key_match(key1, key2)

        try:
            b1 = float(bpm1) if bpm1 and str(bpm1).replace('.', '', 1).isdigit() else 0.0
            b2 = float(bpm2) if bpm2 and str(bpm2).replace('.', '', 1).isdigit() else 0.0
        except (ValueError, TypeError):
            b1, b2 = 0.0, 0.0

        bpm_score, bpm_quality = cls.calculate_bpm_match(b1, b2)

        total = min(100, int((key_score * 0.50 + bpm_score * 0.40) * 100))
        return total, key_quality, bpm_quality
