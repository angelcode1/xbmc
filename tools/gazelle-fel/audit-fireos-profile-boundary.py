#!/usr/bin/env python3
"""Read-only, fail-closed Fire OS OMX profile/dual-layer static contract report.

Use only on a private local directory containing the three original 32-bit
Gazelle vendor libraries. Prints *summary evidence*, never patches binaries,
attaches to a running decoder, invokes adb, or writes to Android.
This is not a test of active FEL residual reconstruction.
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

EXPECTED = {
    "libOmxVideo.so": "eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77",
    "libomx_framework_alt.so": "fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba",
    "libOmxBase.so": "7bbf3da721b69995add8a7cd6b5bd5fc0e6454c065c3d4690f81eebe2d69c7ee",
}
# AOSP OMX_VIDEO_DOLBYVISIONPROFILETYPE; not established to be the vendor owner field.
AOSP_PROFILES = {
    0x10: "DvheDtr / P4", 0x20: "DvheStn / P5",
    0x80: "DvheDtb / P7", 0x100: "DvheSt / P8",
    0x400: "Dvav110 / P10 AV1",
}
CONTEXTS = {
    "libomx_framework_alt.so": {
        "vendor_parameter_writer": (0x19488, 0x194c0),
        "dolby_component_constructor": (0x164b6, 0x164f8),
        "peer_owner_binding": (0x1db68, 0x1db72),
    },
    "libOmxVideo.so": {
        "legacy_duallayer_gate": (0x21a62, 0x21b04),
        "awesome_format_gate": (0x3b682, 0x3b7d0),
        "dolby_decoder_spec": (0x30948, 0x30990),
        "dolby_decoder_es": (0x309a0, 0x309e0),
        "dolby2_decoder_spec": (0x43000, 0x43043),
        "per_instance_meta_ioctl_wrapper": (0x5a1a0, 0x5a1c8),
    },
}

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as fd:
        for block in iter(lambda: fd.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def check_elf(path):
    with path.open("rb") as f:
        h = f.read(20)
    if len(h) < 20 or h[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Expected ARM little-endian ELF32: " + path.name)
    if int.from_bytes(h[18:20], "little") != 40:
        raise ValueError("Expected ARM e_machine=40: " + path.name)

def disasm(objdump, path, start, stop):
    return subprocess.run(
        [objdump, "-d", "--triple=thumbv7a-linux-android",
         f"--start-address=0x{start:x}", f"--stop-address=0x{stop:x}", str(path)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path, nargs="?", help="Private vendor ELF directory")
    p.add_argument("--selftest", action="store_true", help="Check profile mapping without any vendor binaries")
    args = p.parse_args()
    assert AOSP_PROFILES[0x80].endswith("P7")
    assert AOSP_PROFILES[0x100].endswith("P8")
    assert "AV1" in AOSP_PROFILES[0x400]
    if args.selftest:
        print("GAZELLE_PROFILE_ENUM_SELFTEST_PASS")
        return 0
    if args.directory is None:
        p.error("Provide a directory or --selftest")
    root = args.directory.expanduser().resolve()
    for name, expected in EXPECTED.items():
        f = root / name
        if not f.is_file() or f.is_symlink():
            print("UNSUPPORTED_BINARY missing/symlink " + name, file=sys.stderr)
            return 2
        try:
            check_elf(f)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        actual = digest(f)
        if actual != expected:
            print(f"UNSUPPORTED_BINARY {name}: sha256 {actual} (expected {expected})", file=sys.stderr)
            return 2
        print(f"PINNED_ELF_PASS {name} sha256={actual}")
    objdump = shutil.which("llvm-objdump")
    if not objdump:
        print("MISSING_TOOL llvm-objdump; install LLVM and add its bin directory to PATH", file=sys.stderr)
        return 2
    print("AOSP_PROFILE_ENUM (context only; NOT a vendor-memory decode):")
    for code, name in AOSP_PROFILES.items():
        print(f"  0x{code:x} => {name}")
    for name, windows in CONTEXTS.items():
        for label, (start, stop) in windows.items():
            try:
                output = disasm(objdump, root / name, start, stop)
            except subprocess.CalledProcessError as e:
                print(f"DISASSEMBLY_ERROR {name} {label}: {e.stderr[-200:]}", file=sys.stderr)
                return 2
            n = len(re.findall(r"(?m)^\s*[0-9a-f]+:\s", output))
            print(f"WINDOW {name} {label} 0x{start:x}-0x{stop:x} instruction_lines={n}")
            if n == 0:
                print(f"EMPTY_WINDOW {name} {label}: no analysis supported", file=sys.stderr)
                return 2
    video = root / "libOmxVideo.so"
    try:
        result = subprocess.run([objdump, "-d", "--triple=thumbv7a-linux-android", str(video)],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=True).stdout
    except subprocess.CalledProcessError as e:
        print("DISASSEMBLY_ERROR full video library " + e.stderr[-200:], file=sys.stderr)
        return 2
    # Direct-branch target check only; does NOT detect indirect calls or BLX register calls.
    direct_calls = [line.strip() for line in result.splitlines()
                    if re.search(r"\bbl(?:x)?\b.*(?:0x)?0*5a1a0\b", line, re.I)]
    print("DIRECT_STATIC_CALLS_TO_0x5a1a0=" + str(len(direct_calls)))
    for line in direct_calls[:8]:
        # Limited mnemonic/address only; proprietary ELF content is not embedded here.
        print("CALLSITE_CANDIDATE " + line[:180])
    print("OWNER_PLUS_0x20_RUNTIME_VALUE=UNKNOWN")
    print("VENDOR_INDEX_0x7f00010d_RUNTIME_CALLER=UNKNOWN")
    print("DECODER_META_IOCTL_0x179_RUNTIME=UNKNOWN")
    print("ACTIVE_EL_RECONSTRUCTION=NOT_ESTABLISHED")
    print("GAZELLE_FIREOS_PROFILE_STATIC_WINDOWS_PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
