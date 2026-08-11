import os
import struct
from djcrate.logger import logger

class SeratoCrateWriter:
    """
    Encoder for writing native Serato DJ ScratchLive binary .crate files.
    Serato crates are big-endian tagged binary structures stored in _Serato_/Subcrates/.
    """
    @staticmethod
    def get_serato_subcrates_dir(music_path=None):
        search_dirs = []
        if music_path:
            search_dirs.append(os.path.join(music_path, "_Serato_", "Subcrates"))
        
        home = os.path.expanduser("~")
        search_dirs.append(os.path.join(home, "Music", "_Serato_", "Subcrates"))
        search_dirs.append(os.path.join(home, "_Serato_", "Subcrates"))

        for d in search_dirs:
            if os.path.exists(os.path.dirname(d)):
                os.makedirs(d, exist_ok=True)
                return d

        default_dir = os.path.join(home, "Music", "_Serato_", "Subcrates")
        os.makedirs(default_dir, exist_ok=True)
        return default_dir

    @staticmethod
    def _encode_tag(tag: str, payload: bytes) -> bytes:
        tag_bytes = tag.encode('ascii')
        length_bytes = struct.pack('>I', len(payload))
        return tag_bytes + length_bytes + payload

    @classmethod
    def write_crate(cls, crate_name: str, file_paths: list, output_dir: str = None) -> str:
        """
        Writes a native Serato .crate file for the given list of audio file paths.
        Returns the path to the written .crate file.
        """
        if not output_dir:
            output_dir = cls.get_serato_subcrates_dir()

        os.makedirs(output_dir, exist_ok=True)
        crate_filename = f"{crate_name}.crate"
        crate_path = os.path.join(output_dir, crate_filename)

        # Header: vrsn tag with "8v8.00/Serato ScratchLive Crate" in UTF-16BE
        version_str = "8v8.00/Serato ScratchLive Crate"
        version_payload = version_str.encode('utf-16be')
        data = cls._encode_tag("vrsn", version_payload)

        # Track entries
        for path in file_paths:
            if not path:
                continue
            norm_path = os.path.normpath(path)
            ptrk_payload = norm_path.encode('utf-16be')
            ptrk_block = cls._encode_tag("ptrk", ptrk_payload)
            otrk_block = cls._encode_tag("otrk", ptrk_block)
            data += otrk_block

        with open(crate_path, 'wb') as f:
            f.write(data)

        logger.info(f"Successfully wrote native Serato crate: {crate_path} with {len(file_paths)} tracks")
        return crate_path
