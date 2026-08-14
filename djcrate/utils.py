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

    @classmethod
    def calculate_transition_analysis(cls, track1: dict, track2: dict) -> dict:
        """
        Deep transition analysis between an outgoing track (track1) and incoming track (track2).
        Calculates exact pitch adjustments on both decks, semitone transposition,
        Camelot wheel relationship, clash detection, and recommended mixing technique.
        """
        k1 = track1.get('key', '')
        k2 = track2.get('key', '')
        key_score, key_label = cls.calculate_key_match(k1, k2)

        try:
            bpm1 = float(track1.get('bpm', 0)) if track1.get('bpm') and str(track1.get('bpm')).replace('.', '', 1).isdigit() else 0.0
        except (ValueError, TypeError):
            bpm1 = 0.0

        try:
            bpm2 = float(track2.get('bpm', 0)) if track2.get('bpm') and str(track2.get('bpm')).replace('.', '', 1).isdigit() else 0.0
        except (ValueError, TypeError):
            bpm2 = 0.0

        bpm_score, bpm_label = cls.calculate_bpm_match(bpm1, bpm2)

        pitch_delta_pct = 0.0
        deck_a_pitch_pct = 0.0
        deck_b_pitch_pct = 0.0
        semitones_shift = 0.0
        transposed_key = k1
        tempo_status = "BPM Unknown"

        if bpm1 > 0 and bpm2 > 0:
            pitch_delta_pct = round(((bpm2 - bpm1) / bpm1) * 100.0, 2)
            deck_a_pitch_pct = pitch_delta_pct
            deck_b_pitch_pct = round(((bpm1 - bpm2) / bpm2) * 100.0, 2)

            rate = bpm2 / bpm1
            if rate > 0:
                semitones_shift = round(12.0 * math.log2(rate), 2)
                shifted_state = cls.calculate_pitch_shifted_state(bpm1, k1, pitch_delta_pct)
                transposed_key = shifted_state.get('transposed_key', k1)

            abs_pitch = abs(pitch_delta_pct)
            if abs_pitch <= 2.0:
                tempo_status = "Tight (≤2%)"
            elif abs_pitch <= 5.0:
                tempo_status = "Compatible (≤5%)"
            elif abs_pitch <= 8.0:
                tempo_status = "Tempo Stretch (≤8%)"
            else:
                tempo_status = "⚠️ Wide Tempo Gap (>8%)"

        # Key clash identification (incompatible keys)
        has_keys = bool(k1 and k2 and cls.parse_key(k1)[0] and cls.parse_key(k2)[0])
        is_clash = has_keys and (key_score < 0.65)

        # Transition strategy recommendation
        abs_pitch = abs(pitch_delta_pct)
        if key_score >= 0.95 and abs_pitch <= 3.0:
            technique = "Long Blend / Harmonic EQ Swap"
        elif key_score >= 0.85 and abs_pitch <= 5.0:
            technique = "Bass Swap & Filter Transition"
        elif "Energy Boost" in key_label or "Shift" in key_label:
            technique = "Drop Cut / Breakdown Jump"
        elif is_clash:
            technique = "Echo Out / Reverb Wash / Tone Play"
        elif abs_pitch > 6.0:
            technique = "Tempo Ramp / Cut On The One"
        else:
            technique = "Standard Crossfade & Low-End Cut"

        # Overall transition score (0-100%)
        overall_score = min(100, int((key_score * 0.55 + bpm_score * 0.45) * 100))

        if is_clash:
            quality = "⚠️ Key Clash Alert"
            badge_color = "#FF4D4D"
        elif overall_score >= 85:
            quality = "Harmonic Match"
            badge_color = "#00E676"
        elif overall_score >= 70:
            quality = "Good Blend"
            badge_color = "#FFD600"
        elif overall_score >= 50:
            quality = "Creative Shift"
            badge_color = "#FF9100"
        else:
            quality = "Risky Transition"
            badge_color = "#FF5252"

        return {
            'track1': track1,
            'track2': track2,
            'k1': k1,
            'k2': k2,
            'bpm1': bpm1,
            'bpm2': bpm2,
            'key_score': key_score,
            'bpm_score': bpm_score,
            'key_label': key_label,
            'bpm_label': bpm_label,
            'is_clash': is_clash,
            'pitch_delta_pct': pitch_delta_pct,
            'deck_a_pitch_pct': deck_a_pitch_pct,
            'deck_b_pitch_pct': deck_b_pitch_pct,
            'semitones_shift': semitones_shift,
            'transposed_key': transposed_key,
            'tempo_status': tempo_status,
            'technique': technique,
            'overall_score': overall_score,
            'quality': quality,
            'badge_color': badge_color
        }

    @classmethod
    def calculate_setlist_flow(cls, tracks: list) -> dict:
        """
        Calculates cumulative statistics, transitions, cumulative start times,
        harmonic flow health score, and dynamic energy curve across an ordered setlist.
        """
        if not tracks:
            return {
                'track_count': 0,
                'total_duration_secs': 0,
                'total_duration_str': "00:00",
                'cumulative_start_times': [],
                'formatted_start_times': [],
                'transitions': [],
                'clash_count': 0,
                'avg_bpm': 0.0,
                'min_bpm': 0.0,
                'max_bpm': 0.0,
                'harmonic_flow_score': 100,
                'energy_curve': []
            }

        total_secs = 0
        cumulative_times = []
        formatted_times = []
        bpms = []
        energy_curve = []

        for i, t in enumerate(tracks):
            dur = t.get('duration', 0) or 0
            try:
                dur = int(dur)
            except (ValueError, TypeError):
                dur = 0

            cumulative_times.append(total_secs)
            m = total_secs // 60
            s = total_secs % 60
            h = m // 60
            if h > 0:
                formatted_times.append(f"{h}:{m % 60:02d}:{s:02d}")
            else:
                formatted_times.append(f"{m:02d}:{s:02d}")

            total_secs += dur

            b = float(t.get('bpm', 0)) if t.get('bpm') and str(t.get('bpm')).replace('.', '', 1).isdigit() else 0.0
            if b > 0:
                bpms.append(b)

            # Energy score derivation (1.0 to 10.0 scale)
            k = t.get('key', '')
            n, mode = cls.parse_key(k)
            # Base energy from tempo (e.g. 120 -> 5.0, 130 -> 7.0, 140 -> 9.0)
            base_energy = 5.0
            if b > 0:
                base_energy = max(1.0, min(10.0, 5.0 + (b - 124.0) * 0.25))
            
            # Major key lift (+0.4) vs minor mood
            if mode == 'B':
                base_energy += 0.4

            # Rating boost
            rating = t.get('rating', 0) or 0
            if rating >= 4:
                base_energy += 0.5

            energy_val = round(max(1.0, min(10.0, base_energy)), 1)
            energy_curve.append({
                'index': i,
                'track': t,
                'energy': energy_val,
                'bpm': b,
                'key': k,
                'start_time_secs': cumulative_times[-1],
                'start_time_str': formatted_times[-1]
            })

        # Calculate transitions
        transitions = []
        clash_count = 0
        score_sum = 0

        for i in range(len(tracks) - 1):
            analysis = cls.calculate_transition_analysis(tracks[i], tracks[i + 1])
            transitions.append(analysis)
            if analysis['is_clash']:
                clash_count += 1
            score_sum += analysis['overall_score']

        harmonic_flow = int(score_sum / len(transitions)) if transitions else 100

        # Total duration string
        tot_m = total_secs // 60
        tot_s = total_secs % 60
        tot_h = tot_m // 60
        if tot_h > 0:
            total_duration_str = f"{tot_h}h {tot_m % 60:02d}m {tot_s:02d}s"
        else:
            total_duration_str = f"{tot_m}m {tot_s:02d}s"

        avg_bpm = round(sum(bpms) / len(bpms), 1) if bpms else 0.0
        min_bpm = min(bpms) if bpms else 0.0
        max_bpm = max(bpms) if bpms else 0.0

        return {
            'track_count': len(tracks),
            'total_duration_secs': total_secs,
            'total_duration_str': total_duration_str,
            'cumulative_start_times': cumulative_times,
            'formatted_start_times': formatted_times,
            'transitions': transitions,
            'clash_count': clash_count,
            'avg_bpm': avg_bpm,
            'min_bpm': min_bpm,
            'max_bpm': max_bpm,
            'harmonic_flow_score': harmonic_flow,
            'energy_curve': energy_curve
        }

    @classmethod
    def auto_harmonize_track_order(cls, tracks: list) -> list:
        """
        Greedy nearest-harmonic-neighbor algorithm to reorder a collection of tracks
        into an optimal Camelot wheel harmonic progression with minimal key/tempo clashes.
        """
        if not tracks or len(tracks) <= 2:
            return list(tracks)

        remaining = list(tracks)
        # Start with the first track as anchor (or track with lowest BPM / highest rating)
        ordered = [remaining.pop(0)]

        while remaining:
            curr = ordered[-1]
            best_idx = 0
            best_score = -1

            for idx, candidate in enumerate(remaining):
                analysis = cls.calculate_transition_analysis(curr, candidate)
                score = analysis['overall_score']
                # Extra penalty if clash
                if analysis['is_clash']:
                    score -= 30
                if score > best_score:
                    best_score = score
                    best_idx = idx

            ordered.append(remaining.pop(best_idx))

        return ordered


# --- Setlist Exporter Helper Functions ---

def export_setlist_to_m3u8(setlist_name: str, tracks: list, output_path: str) -> str:
    """Exports an ordered setlist to standard extended M3U8 format."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        f.write(f"#PLAYLIST:DJ Crate Set - {setlist_name}\n\n")
        for t in tracks:
            dur = t.get('duration', -1) or -1
            artist = t.get('artist', 'Unknown Artist')
            title = t.get('title', 'Unknown Title')
            f.write(f"#EXTINF:{dur},{artist} - {title}\n")
            f.write(f"{t.get('file_path', t.get('path', ''))}\n")
    return output_path

def export_setlist_to_csv(setlist_name: str, tracks: list, output_path: str) -> str:
    """Exports an ordered setlist to CSV format."""
    import csv
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["#", "Title", "Artist", "BPM", "Key", "Duration (s)", "Format", "Path", "Notes"])
        for i, t in enumerate(tracks, 1):
            writer.writerow([
                i,
                t.get('title', ''),
                t.get('artist', ''),
                t.get('bpm', ''),
                t.get('key', ''),
                t.get('duration', ''),
                t.get('genre', ''),
                t.get('file_path', t.get('path', '')),
                t.get('item_notes', t.get('notes', ''))
            ])
    return output_path

def export_setlist_to_tracklist_text(setlist_name: str, tracks: list) -> str:
    """
    Generates a clean timestamped text tracklist suitable for
    1001Tracklists, Mixcloud, SoundCloud, or YouTube descriptions.
    """
    flow = CamelotMatcher.calculate_setlist_flow(tracks)
    lines = [
        f"=== DJ SET: {setlist_name.upper()} ===",
        f"Total Duration: {flow['total_duration_str']} · Tracks: {flow['track_count']} · Avg BPM: {flow['avg_bpm']}",
        f"Harmonic Health: {flow['harmonic_flow_score']}% Flow ({flow['clash_count']} Key Clashes)",
        "--------------------------------------------------------------------------------",
        ""
    ]

    for i, t in enumerate(tracks):
        start_time = flow['formatted_start_times'][i] if i < len(flow['formatted_start_times']) else "00:00"
        artist = t.get('artist', 'Unknown Artist')
        title = t.get('title', 'Unknown Title')
        bpm_str = f"[{t.get('bpm')} BPM]" if t.get('bpm') else ""
        key_str = f"[{t.get('key')}]" if t.get('key') else ""
        
        line = f"[{start_time}] {i+1:02d}. {artist} - {title} {key_str} {bpm_str}".strip()
        lines.append(line)

        # Append transition note if available
        if i < len(flow['transitions']):
            tr = flow['transitions'][i]
            pitch_str = f"{tr['deck_a_pitch_pct']:+.1f}% pitch" if tr['bpm1'] > 0 and tr['bpm2'] > 0 else ""
            trans_note = f"      ↳ Transition: {tr['key_label']} · {pitch_str} · Strategy: {tr['technique']}"
            lines.append(trans_note)

    lines.append("")
    lines.append("Generated by DJ Crate — The Pro DJ Desktop Station")
    return "\n".join(lines)

def export_setlist_to_cheat_sheet_html(setlist_name: str, tracks: list, output_path: str) -> str:
    """
    Generates an ultra-sleek, print-ready or tablet-ready HTML DJ Transition Cheat Sheet
    with color-coded Camelot keys, exact pitch adjustments, and cue notes.
    """
    flow = CamelotMatcher.calculate_setlist_flow(tracks)
    
    rows_html = []
    for i, t in enumerate(tracks):
        start_time = flow['formatted_start_times'][i] if i < len(flow['formatted_start_times']) else "00:00"
        title = t.get('title', 'Unknown Title')
        artist = t.get('artist', 'Unknown Artist')
        bpm = t.get('bpm', '—')
        key = t.get('key', '—')
        key_color = CamelotMatcher.get_camelot_color(key)
        dur_secs = int(t.get('duration', 0) or 0)
        dur_str = f"{dur_secs // 60}:{dur_secs % 60:02d}"

        # Transition badge
        trans_cell = "—"
        if i < len(flow['transitions']):
            tr = flow['transitions'][i]
            clash_badge = '<span class="clash-badge">⚠️ CLASH</span>' if tr['is_clash'] else ''
            pitch_badge = f'<span class="pitch-badge">{tr["deck_a_pitch_pct"]:+.1f}%</span>' if tr['bpm1'] > 0 and tr['bpm2'] > 0 else ''
            trans_cell = f"""
                <div class="trans-box">
                    <div><b>{tr['key_label']}</b> {pitch_badge} {clash_badge}</div>
                    <div class="technique">{tr['technique']}</div>
                </div>
            """

        row = f"""
            <tr>
                <td class="pos-col">#{i+1:02d}</td>
                <td class="time-col">{start_time}</td>
                <td class="track-col">
                    <div class="track-title">{title}</div>
                    <div class="track-artist">{artist}</div>
                </td>
                <td class="key-col"><span class="key-pill" style="border-color: {key_color}; color: {key_color};">{key}</span></td>
                <td class="bpm-col">{bpm}</td>
                <td class="dur-col">{dur_str}</td>
                <td class="trans-col">{trans_cell}</td>
            </tr>
        """
        rows_html.append(row)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>DJ Crate — Setlist: {setlist_name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #0e0e12;
            color: #e2e2e8;
            margin: 0;
            padding: 24px;
        }}
        .header {{
            border-bottom: 2px solid #2a2a35;
            padding-bottom: 16px;
            margin-bottom: 20px;
        }}
        h1 {{
            margin: 0 0 8px 0;
            color: #ffffff;
            font-size: 26px;
            letter-spacing: 0.5px;
        }}
        .stats-bar {{
            display: flex;
            gap: 20px;
            font-size: 14px;
            color: #9c9ca8;
        }}
        .stat-item b {{ color: #00E676; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
        }}
        th {{
            text-align: left;
            padding: 10px 12px;
            background: #181820;
            color: #8a8a9a;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid #2a2a35;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #1e1e28;
            font-size: 14px;
            vertical-align: middle;
        }}
        tr:nth-child(even) {{ background: rgba(255, 255, 255, 0.02); }}
        .pos-col {{ font-weight: bold; color: #8a8a9a; width: 40px; }}
        .time-col {{ color: #00E5FF; font-family: monospace; font-size: 13px; width: 60px; }}
        .track-title {{ font-weight: 600; color: #ffffff; }}
        .track-artist {{ font-size: 12px; color: #8a8a9a; margin-top: 2px; }}
        .key-pill {{
            display: inline-block;
            padding: 2px 8px;
            border: 1px solid;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
            background: rgba(255, 255, 255, 0.05);
        }}
        .bpm-col {{ font-weight: 600; color: #ff9100; font-family: monospace; width: 60px; }}
        .dur-col {{ color: #8a8a9a; font-size: 12px; width: 50px; }}
        .trans-box {{
            background: #181820;
            border: 1px solid #282836;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
        }}
        .technique {{ color: #9c9ca8; font-size: 11px; margin-top: 3px; }}
        .pitch-badge {{
            background: rgba(0, 230, 118, 0.15);
            color: #00E676;
            border: 1px solid #00E676;
            border-radius: 3px;
            padding: 1px 4px;
            font-size: 10px;
            font-weight: bold;
            margin-left: 6px;
        }}
        .clash-badge {{
            background: rgba(255, 77, 77, 0.2);
            color: #FF4D4D;
            border: 1px solid #FF4D4D;
            border-radius: 3px;
            padding: 1px 4px;
            font-size: 10px;
            font-weight: bold;
            margin-left: 6px;
        }}
        @media print {{
            body {{ background: #ffffff; color: #111111; padding: 0; }}
            th {{ background: #f0f0f0; color: #333333; }}
            td {{ border-bottom: 1px solid #dddddd; color: #111111; }}
            .track-title {{ color: #000000; }}
            .trans-box {{ background: #f8f8f8; border-color: #cccccc; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎛️ DJ CRATE — SETLIST CHEAT SHEET</h1>
        <div class="stats-bar">
            <div>Set: <b style="color: #ffffff;">{setlist_name}</b></div>
            <div>Total Duration: <b>{flow['total_duration_str']}</b></div>
            <div>Tracks: <b>{flow['track_count']}</b></div>
            <div>Average BPM: <b>{flow['avg_bpm']} BPM</b></div>
            <div>Harmonic Health: <b>{flow['harmonic_flow_score']}% Flow</b></div>
            <div>Clashes: <b style="color: {'#FF4D4D' if flow['clash_count'] > 0 else '#00E676'};">{flow['clash_count']}</b></div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Time</th>
                <th>Track</th>
                <th>Key</th>
                <th>BPM</th>
                <th>Dur</th>
                <th>Next Transition & Strategy</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows_html)}
        </tbody>
    </table>
</body>
</html>
"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    return output_path
