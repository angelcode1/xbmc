#!/usr/bin/env python3
"""Fast offline ELF32 ARM guard for the bundled Gazelle MMBD APK payload.

This test never invokes an NDK compiler, Android device, network, or MakeMKV.
It catches accidental double-escaping of ELF e_ident magic/class/endian bytes
before the expensive full Kodi build starts.
"""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stage_mmbd_apk import LIB, LIB_SHA, arm_elf, verified_bytes  # noqa: E402


def sample(*, file_class=1, endian=1, version=1, kind=3, arch=40):
    data = bytearray(52)
    data[:4] = b"\x7fELF"
    data[4:7] = bytes((file_class, endian, version))
    struct.pack_into("<HH", data, 16, kind, arch)
    return bytes(data)


def rejects(description, data):
    try:
        arm_elf(data)
    except ValueError:
        return
    raise AssertionError(description + " incorrectly accepted")


def main():
    assert arm_elf(sample()) is True
    rejects("missing ELF header", bytes(52))
    rejects("truncated ELF", sample()[:51])
    rejects("ELF64", sample(file_class=2))
    rejects("big-endian", sample(endian=2))
    rejects("invalid ELF version", sample(version=0))
    rejects("non-ARM", sample(arch=183))
    rejects("non-ET_DYN", sample(kind=2))
    verified = verified_bytes(HERE / "native" / LIB, LIB_SHA)
    assert arm_elf(verified)
    print("GAZELLE_MMBD_ELF32_ARM_EARLY_PREFLIGHT_PASS")


if __name__ == "__main__":
    main()
