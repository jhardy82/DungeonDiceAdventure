"""What phase 0 has to know about a built APK (docs/android/PLAN.md, the go or no-go checks).

Reads the APK with the standard library only: its size, the processor types it carries, and whether every
native library is laid out for memory pages of 16 KB, which Android asks of new apps. Prints one line per
finding and a last line that starts with ``APK CHECK``. It measures; it does not fail a build.

Usage: python android/tools/check_apk.py path/to/app.apk
"""

from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path

PAGE_16K = 16384
PT_LOAD = 1


def load_alignments(data: bytes) -> list[int]:
    """The alignment of every loadable part of an ELF library (32 or 64 bit, little endian)."""
    if data[:4] != b"\x7fELF" or data[5] != 1:
        return []
    wide = data[4] == 2
    if wide:
        offset, size, count = struct.unpack_from("<Q", data, 0x20)[0], *struct.unpack_from("<HH", data, 0x36)
    else:
        offset, size, count = struct.unpack_from("<I", data, 0x1C)[0], *struct.unpack_from("<HH", data, 0x2A)
    found = []
    for index in range(count):
        start = offset + index * size
        if struct.unpack_from("<I", data, start)[0] != PT_LOAD:
            continue
        found.append(struct.unpack_from("<Q", data, start + 0x30)[0] if wide else struct.unpack_from("<I", data, start + 0x1C)[0])
    return found


def check(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as apk:
        libraries = [name for name in apk.namelist() if name.startswith("lib/") and name.endswith(".so")]
        small = []
        for name in libraries:
            alignments = load_alignments(apk.read(name))
            if not alignments or min(alignments) < PAGE_16K:
                small.append(f"{name} ({min(alignments) if alignments else 'not an ELF library'})")
        stored_unaligned = [name for name in libraries
                            if apk.getinfo(name).compress_type == zipfile.ZIP_STORED and _data_offset(apk, name) % PAGE_16K]
    return {"megabytes": round(path.stat().st_size / 1_000_000, 1), "abis": sorted({name.split("/")[1] for name in libraries}),
            "libraries": len(libraries), "not_16k_inside": small, "not_16k_in_the_apk": stored_unaligned}


def _data_offset(apk: zipfile.ZipFile, name: str) -> int:
    """Where a stored file's bytes begin in the APK: an uncompressed library is mapped from there."""
    info = apk.getinfo(name)
    assert apk.fp is not None
    apk.fp.seek(info.header_offset + 26)
    name_length, extra_length = struct.unpack("<HH", apk.fp.read(4))
    return info.header_offset + 30 + name_length + extra_length


def main(arguments: list[str]) -> int:
    if len(arguments) != 1:
        print(__doc__)
        return 2
    found = check(Path(arguments[0]))
    for key, value in found.items():
        print(f"{key}: {value}")
    aligned = not found["not_16k_inside"] and not found["not_16k_in_the_apk"]
    print(f"APK CHECK: size={found['megabytes']}MB abis={','.join(found['abis'])} libraries={found['libraries']} pages_16k={'yes' if aligned else 'NO'}")  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
