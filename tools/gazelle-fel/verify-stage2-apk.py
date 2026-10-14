#!/usr/bin/env python3
"""Fail closed if an Android Kodi APK does not contain Gazelle Stage 2 markers.

Uses only Python's standard library; inspects packaged native binaries without
installing or modifying the APK. Code-marker presence is necessary evidence of
the diagnostic build, but not proof of successful execution or ELF provenance.
"""
import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

MARKERS = (
    b"GAZELLE_DOVI_CODEC_SELECTED",
    b"GAZELLE_DOVI_MEDIAFORMAT",
    b"GAZELLE_P7_INPUT_COPY",
)
CHUNK_SIZE = 1024 * 1024


def find_markers(apk: Path):
    found = {}
    with zipfile.ZipFile(apk) as z:
        entries = [
            e for e in z.infolist()
            if not e.is_dir()
            and (e.filename.endswith((".so", ".bin")) or "/lib/" in e.filename)
        ]
        if not entries:
            print("WARNING: no packaged native library entries found", file=sys.stderr)
        for entry in entries:
            if len(found) == len(MARKERS):
                break
            with z.open(entry) as f:
                prior = b""
                while True:
                    data = f.read(CHUNK_SIZE)
                    if not data:
                        break
                    combined = prior + data
                    for marker in MARKERS:
                        if marker not in found and marker in combined:
                            found[marker] = entry.filename
                    prior = combined[-max(map(len, MARKERS)):]
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    args = parser.parse_args()
    if not args.apk.is_file():
        parser.error(f"File not found: {args.apk}")
    digest = hashlib.sha256()
    with args.apk.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK_SIZE), b""):
            digest.update(block)
    print(f"APK={args.apk}")
    print(f"APK_SHA256={digest.hexdigest()}")
    try:
        located = find_markers(args.apk)
    except (zipfile.BadZipFile, OSError, RuntimeError) as e:
        print(f"APK_CHECK_FAILED: {e}", file=sys.stderr)
        return 2
    for marker in MARKERS:
        if marker in located:
            print(f"PRESENT {marker.decode()} in {located[marker]}")
        else:
            print(f"MISSING {marker.decode()}")
    if len(located) != len(MARKERS):
        print("STAGE2_MISSING_MARKERS: DO NOT INSTALL AS THE STAGE 2 TEST APK")
        return 1
    print("STAGE2_MARKERS_PASS: all expected diagnostic strings embedded in APK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
