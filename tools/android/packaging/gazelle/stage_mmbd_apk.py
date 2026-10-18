#!/usr/bin/env python3
"""Build and embed source-local Gazelle MMBD Android provider and service.

No network, private checkout, root execution or MakeMKV runtime download.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import struct
from xml.etree import ElementTree

ADDON = "service.gazelle.mmbd"
LIB_SHA = "826b5e6dfebfd628c1a6f851a22cb583fa831978600f4ddc2663af46794a8d0b"
SOURCE_HELPER_SHA = "c8005d1b168f42024f72de78ae64dcf66f4b142583d3afc92fd97ac72ce9172c"
LIB = "libmmbd.so"
HELPER = "libgazelle_mmbd_v2.so"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verified_bytes(path, sha):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("Missing/symlinked native payload: " + str(path))
    data = path.read_bytes()
    if sha256(data) != sha:
        raise ValueError("Pinned native payload checksum mismatch: " + str(path))
    return data


def arm_elf(data, *, pie=False):
    if len(data) < 52 or data[:4] != b"\x7fELF":
        raise ValueError("Missing ELF magic")
    if data[4:7] != b"\\x01\\x01\\x01":
        raise ValueError("Not little-endian ELF32")
    kind, arch = struct.unpack_from("<HH", data, 16)
    if arch != 40 or kind != 3:
        raise ValueError("Not an ELF32 ARM ET_DYN binary")
    # A PIE executable has ET_DYN just like an Android shared object.
    return True


def prepare(root, assets, build_dir, ndk):
    root = Path(root).resolve()
    assets = Path(assets).resolve()
    build_dir = Path(build_dir).resolve()
    ndk = Path(ndk).resolve()
    native_dir = root / "tools/android/packaging/gazelle/native"
    lib = verified_bytes(native_dir / LIB, LIB_SHA)
    arm_elf(lib)
    helpers = list(ndk.glob("toolchains/llvm/prebuilt/*/bin/armv7a-linux-androideabi28-clang"))
    if len(helpers) != 1:
        raise ValueError("One configured Android ARMv7 API28 compiler required: " + str(helpers))
    build_dir.mkdir(parents=True, exist_ok=True)
    executable = build_dir / HELPER
    src = native_dir / "gazelle_mmbd_helper_v2.c"
    if not src.is_file() or src.is_symlink():
        raise ValueError("Missing local source for MMBD helper")
    cmd = [str(helpers[0]), "-O2", "-fPIE", "-pie", "-fstack-protector-strong",
           "-Wl,-z,relro,-z,now", "-o", str(executable), str(src)]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    executable.chmod(0o755)
    helper_bytes = executable.read_bytes()
    arm_elf(helper_bytes, pie=True)
    helper_sha = sha256(helper_bytes)

    source = root / "addons" / ADDON
    xml = source / "addon.xml"
    if ElementTree.parse(xml).getroot().get("id") != ADDON:
        raise ValueError("Unexpected MMBD service ID")
    python_source = source / "service.py"
    text = python_source.read_text(encoding="utf-8")
    old = "HELPER_SHA = '" + SOURCE_HELPER_SHA + "'"
    if text.count(old) != 1 or text.count("LIB_SHA = '" + LIB_SHA + "'") != 1:
        raise ValueError("Unrecognized local MMBD service pin")
    updated = text.replace(old, "HELPER_SHA = '" + helper_sha + "'")
    target = assets / "addons" / ADDON
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(xml, target / "addon.xml")
    (target / "service.py").write_text(updated, encoding="utf-8")
    manifest_file = assets / "system/addon-manifest.xml"
    tree = ElementTree.parse(manifest_file)
    manifest = tree.getroot()
    if manifest.tag != "addons":
        raise ValueError("Missing Kodi system add-on manifest")
    existing = [x for x in manifest.findall("addon") if (x.text or "").strip() == ADDON]
    if len(existing) > 1:
        raise ValueError("Duplicate MMBD system addon")
    if existing:
        if existing[0].get("optional") != "true":
            raise ValueError("Service must remain optional")
    else:
        ElementTree.SubElement(manifest, "addon", {"optional": "true"}).text = ADDON
    ElementTree.indent(tree, space="  ")
    tree.write(manifest_file, encoding="utf-8", xml_declaration=True)
    (build_dir / "helper.sha256").write_text(helper_sha + "\n")
    print("GAZELLE_MMBD_LOCAL_COMPILE_PASS lib=" + LIB_SHA + " helper=" + helper_sha)


def native(root, native_dir, build_dir):
    root = Path(root).resolve()
    native_dir = Path(native_dir).resolve()
    build_dir = Path(build_dir).resolve()
    native_dir.mkdir(parents=True, exist_ok=True)
    lib = verified_bytes(root / "tools/android/packaging/gazelle/native" / LIB, LIB_SHA)
    helper_path = build_dir / HELPER
    if not helper_path.is_file() or helper_path.is_symlink():
        raise ValueError("Helper not compiled by local Kodi build")
    helper = helper_path.read_bytes()
    arm_elf(helper, pie=True)
    if sha256(helper) != (build_dir / "helper.sha256").read_text().strip():
        raise ValueError("Helper digest changed after staging")
    for name, data in ((LIB, lib), (HELPER, helper)):
        target = native_dir / name
        target.write_bytes(data)
        target.chmod(0o755)
        if target.read_bytes() != data:
            raise ValueError("Native copied with unexpected changes")
    print("GAZELLE_MMBD_NATIVE_COPY_PASS abi=armeabi-v7a no_private_sources=1")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--build-dir", required=True)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--assets")
    modes.add_argument("--native-dir")
    p.add_argument("--ndk")
    args = p.parse_args()
    if args.assets:
        if not args.ndk:
            p.error("--ndk required for --assets")
        prepare(args.root, args.assets, args.build_dir, args.ndk)
    else:
        native(args.root, args.native_dir, args.build_dir)
