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
        "dolby_vision_parameter_writer": (0x18fdc, 0x19006),
        "amlogic_profile_log": (0x1a160, 0x1a186),
        "dolby_component_constructor": (0x164b6, 0x164f8),
        "peer_owner_binding": (0x1db68, 0x1db72),
        "frame_flags_constructor": (0x163d0, 0x163dc),
        "dv_frame_property_to_owner": (0x16630, 0x16656),
        "multi_dec_mode_constructor": (0x16568, 0x1657c),
        "stream_mode_constructor": (0x16830, 0x1688c),
    },
    "libOmxVideo.so": {
        "legacy_duallayer_gate": (0x21a62, 0x21b04),
        "dolby_wrapper_routes": (0x308ac, 0x309d6),
        "codec_dv_hevc_device_selection": (0x590c8, 0x590e8),
        "codec_dv_frame_stream_switch": (0x58cbe, 0x58cf6),
        "dolby_vision_owner_reader": (0x1eb54, 0x1eb76),
        "dolby_vision_profile_compare": (0x1ee5c, 0x1ee6c),
        "dvhe_hevc_profile_bypass": (0x1eda8, 0x1edd0),
        "awesome_format_gate": (0x3b682, 0x3b7d0),
        "dolby_decoder_spec": (0x30948, 0x30990),
        "dolby_decoder_es": (0x309a0, 0x309e0),
        "dolby2_decoder_spec": (0x43000, 0x43043),
        "per_instance_meta_ioctl_wrapper": (0x5a1a0, 0x5a1c8),
        "decoder_mode_property_selection": (0x1ef78, 0x1efd6),
        "awesome_owner_flag_transfer": (0x26128, 0x26142),
        "awesome_frame_mode_handoff": (0x263f8, 0x26416),
    },
}


# Check actual instructions, not just whether disassembly windows are nonempty.
# Valid only after the full SHA-256 validation above has passed.
SEMANTIC_GATES = {
    ("libomx_framework_alt.so", "frame_flags_constructor"): {
        0x163d4: r"str\.w\s+r5,\s*\[r4,\s*#0x109\]",
    },
    ("libomx_framework_alt.so", "multi_dec_mode_constructor"): {
        0x16572: r"strb\.w\s+r0,\s*\[r4,\s*#0x109\]",
    },
    ("libomx_framework_alt.so", "dv_frame_property_to_owner"): {
        0x16632: r"ldr\.w\s+r0,\s*\[pc,",
        0x1663a: r"bl\s+0x246d0\b",
        0x16650: r"strb\.w\s+r0,\s*\[r4,\s*#0x10b\]",
    },
    ("libomx_framework_alt.so", "stream_mode_constructor"): {
        0x16832: r"movs\s+r0,\s*#0x1\b",
        0x16834: r"strb\.w\s+r0,\s*\[r4,\s*#0x10a\]",
        0x16842: r"ldr\.w\s+r0,\s*\[pc,",
        0x16888: r"strb\.w\s+r0,\s*\[r4,\s*#0x10a\]",
    },
    ("libOmxVideo.so", "decoder_mode_property_selection"): {
        0x1ef7a: r"ldrb\.w\s+r0,\s*\[r5,\s*#0xdc\]",
        0x1ef80: r"ldr\s+r0,\s*\[pc,",
        0x1ef8c: r"ldr\s+r0,\s*\[pc,",
        0x1ef9a: r"strb\.w\s+r0,\s*\[r5,\s*#0xdd\]",
        0x1efb6: r"ldrb\.w\s+r0,\s*\[r5,\s*#0xdd\]",
        0x1efc0: r"ldrb\.w\s+r3,\s*\[r5,\s*#0xdc\]",
        0x1efd2: r"str\s+r3,\s*\[r4,\s*r0\]",
    },
    ("libOmxVideo.so", "awesome_owner_flag_transfer"): {
        0x2612c: r"ldrb\.w\s+r1,\s*\[r0,\s*#0x109\]",
        0x26130: r"strb\.w\s+r1,\s*\[r4,\s*#0xdc\]",
        0x26134: r"ldrb\.w\s+r2,\s*\[r0,\s*#0x10a\]",
        0x26138: r"strb\.w\s+r2,\s*\[r4,\s*#0xdd\]",
    },
    ("libOmxVideo.so", "awesome_frame_mode_handoff"): {
        0x263f8: r"ldrb\.w\s+r0,\s*\[r4,\s*#0xdd\]",
        0x26402: r"strb\s+r0,\s*\[r1,\s*#0x18\]",
    },
    ("libomx_framework_alt.so", "dolby_component_constructor"): {
        0x164c8: r"movs\s+r0,\s*#0xb\b",
        0x164ca: r"str\.w\s+r0,\s*\[r4,\s*#0x3dc\]",
    },
    ("libOmxVideo.so", "dvhe_hevc_profile_bypass"): {
        0x1eda8: r"ldr\s+r0,\s*\[r5,\s*#0x4\]",
        0x1edaa: r"ldr\.w\s+r0,\s*\[r0,\s*#0x3dc\]",
        0x1edb2: r"cmp\s+r0,\s*#0xb\b",
        0x1edb4: r"bne\s+0x1ee5c\b",
        0x1edce: r"b\s+0x1ef1c\b",
    },
    ("libomx_framework_alt.so", "dolby_vision_parameter_writer"): {
        0x18fde: r"movt\s+r0,\s*#0x7f80\b",
        0x18fe2: r"cmp\s+r6,\s*r0\b",
        0x18ff2: r"str\.w\s+r0,\s*\[r4,\s*#0x36c\]",
        0x18ffc: r"str\.w\s+r0,\s*\[r4,\s*#0x370\]",
    },
    ("libomx_framework_alt.so", "amlogic_profile_log"): {
        0x1a164: r"ldrd\s+r0,\s*r1,\s*\[r4,\s*#32\]",
    },
    ("libOmxVideo.so", "dolby_vision_owner_reader"): {
        0x1eb6e: r"ldr\.w\s+r8,\s*\[r2,\s*#0x36c\]",
    },
    ("libOmxVideo.so", "dolby_vision_profile_compare"): {
        0x1ee5c: r"cmp\.w\s+r8,\s*#0x400\b",
    },
    ("libomx_framework_alt.so", "vendor_parameter_writer"): {
        0x194a4: r"str\s+r0,\s*\[r4,\s*#0x20\]",
        0x194a8: r"str\s+r1,\s*\[r4,\s*#0x24\]",
    },
    ("libomx_framework_alt.so", "peer_owner_binding"): {
        0x1db6e: r"str\s+r1,\s*\[r0,\s*#0x4\]",
    },
    ("libOmxVideo.so", "dolby_wrapper_routes"): {
        0x308b0: r"bl\s+0x66b24\b",
        0x3095a: r"cmp\.w\s+r2,\s*#0x400\b",
        0x3096c: r"bne\s+0x3098c\b",
        0x30986: r"bl\s+0x66b44\b",
        0x309a4: r"bl\s+0x66b54\b",
        0x309ce: r"b\.w\s+0x66b64\b",
        0x309d2: r"b\.w\s+0x66b74\b",
    },
    ("libOmxVideo.so", "codec_dv_frame_stream_switch"): {
        0x58ce6: r"cmp\s+r2,\s*#0x1\b",
        0x58cea: r"moveq\s+r0,\s*r3\b",
    },
    ("libOmxVideo.so", "codec_dv_hevc_device_selection"): {
        0x590d0: r"mov\.w\s+r0,\s*#0x10a0\b",
        0x590d8: r"ldr\.w\s+r2,\s*\[r8,\s*r0\]",
        0x590d4: r"ldr\.w\s+r3,\s*\[pc,",
        0x590dc: r"ldr\.w\s+r0,\s*\[pc,",
        0x590e4: r"b\s+0x58ce6\b",
    },
    ("libOmxVideo.so", "legacy_duallayer_gate"): {
        0x21a68: r"cmp\s+r1,\s*#0xb\b",
        0x21aca: r"cmp\s+r0,\s*#0x10\b",
        0x21ad4: r"ldr\.w\s+r2,\s*\[pc,",
    },
    ("libOmxVideo.so", "awesome_format_gate"): {
        0x3b69c: r"cmp\s+r0,\s*#0x10\b",
        0x3b746: r"movs\s+r6,\s*#0xb\b",
    },
    ("libOmxVideo.so", "dolby_decoder_spec"): {
        0x3095a: r"cmp\.w\s+r2,\s*#0x400\b",
    },
    ("libOmxVideo.so", "dolby2_decoder_spec"): {
        0x43014: r"cmp\.w\s+r2,\s*#0x400\b",
    },
    ("libOmxVideo.so", "per_instance_meta_ioctl_wrapper"): {
        0x5a1a6: r"movw\s+r2,\s*#0x179\b",
    },
}
INSTRUCTION_RE = re.compile(
    r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][a-z0-9.]*)\s*(.*)"
)

def parse_instructions(output):
    parsed = {}
    for line in output.splitlines():
        m = INSTRUCTION_RE.match(line)
        if m:
            parsed[int(m[1], 16)] = m[2] + " " + m[3]
    return parsed

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
            instructions = parse_instructions(output)
            for addr, pattern in SEMANTIC_GATES.get((name, label), {}).items():
                actual = instructions.get(addr, "")
                if not re.search(pattern, actual):
                    print(f"SEMANTIC_GATE_FAIL {name} {label} 0x{addr:x}: {actual!r}", file=sys.stderr)
                    return 1
            print(f"SEMANTIC_GATE_PASS {name} {label} checked={len(SEMANTIC_GATES.get((name, label), {}))}")
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
    print("DVHE_HEVC_BRANCH_MAY_BYPASS_DOLBY_PROFILE_COMPARE; RUNTIME_UNVERIFIED")
    print("FRAME_MODE_OWNER_FLAGS_0x109_0x10a_0x10b=STATIC_CHAIN_VERIFIED_RUNTIME_UNKNOWN")
    print("AMLOGIC_FRAME_STREAM_DECODER_MODE=CODE_PATH_VERIFIED_NO_DEVICE_TOGGLE")
    print("DV_HEVC_FRAME_STREAM_PATH=STAGE10_STATIC_GATE_PASS_ACTIVE_EL_UNPROVEN")
    print("ACTIVE_EL_RECONSTRUCTION=NOT_ESTABLISHED")
    print("GAZELLE_FIREOS_PROFILE_STATIC_WINDOWS_PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
