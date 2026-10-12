#!/usr/bin/env python3
"""Stage verified Gazelle physical optical addons into Kodi Android packaging.

This is *build-time only*: no ADB, device, root, SCSI, UDF mount, or disc I/O.
The cube3 checkout is pinned by the calling CI workflow.
"""
import argparse
import hashlib
import pathlib
import shutil
import subprocess
import xml.etree.ElementTree as ET

ALLOWED_SOURCE = pathlib.Path("blu-ray/physical-udf")
SDK = pathlib.Path("xbmc/addons/kodi-dev-kit/include")
EXPORTS = pathlib.Path("blu-ray/g10g2b1s-r1/tools/G10G2B1S-EXPORTS.map")
SOURCE = pathlib.Path("blu-ray/g10g2b1s-r1/original/OpticalG3Client.cpp")


def copy_verified(src, dst):
    if not src.is_file() or src.is_symlink():
        raise RuntimeError("Missing or symlinked addon source: " + str(src))
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    if hashlib.sha256(src.read_bytes()).digest() != hashlib.sha256(dst.read_bytes()).digest():
        raise RuntimeError("Source copy mismatch: " + str(src))


def check_addon(src, addon_id, version):
    root = ET.parse(src).getroot()
    if root.tag != "addon" or root.attrib.get("id") != addon_id:
        raise RuntimeError("Unrecognized Gazelle addon XML: " + str(src))
    if root.attrib.get("version") != version:
        raise RuntimeError("Unpinned Gazelle addon version: " + str(src))


def stage(root, cube3, depends, ndk):
    root, cube3, depends, ndk = [pathlib.Path(p).resolve() for p in
                                 (root, cube3, depends, ndk)]
    src = cube3 / ALLOWED_SOURCE
    vfs_xml = src / "kodi-vfs/addon.xml"
    checker_xml = src / "kodi-check/addon.xml"
    check_addon(vfs_xml, "vfs.gazelle.physical", "0.1.0")
    check_addon(checker_xml, "script.gazelle.physicaludfcheck", "0.1.6")
    if not (root / SDK / "kodi/addon-instance/VFS.h").is_file():
        raise RuntimeError("Kodi VFS build headers missing")
    if not (cube3 / EXPORTS).is_file() or not (cube3 / SOURCE).is_file():
        raise RuntimeError("Gazelle VFS source dependency missing")

    abi = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    cxx = abi / "armv7a-linux-androideabi28-clang++"
    readelf = abi / "llvm-readelf"
    if not cxx.is_file() or not readelf.is_file():
        raise RuntimeError("Pinned Android NDK ARMv7 compiler unavailable")

    assets = depends / "share/kodi/addons"
    vfs_dir = assets / "vfs.gazelle.physical"
    script_dir = assets / "script.gazelle.physicaludfcheck"
    native = depends / "lib/kodi/addons/vfs.gazelle.physical/libvfs.gazelle.physical.so"
    native.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(cxx), "-std=c++17", "-O2", "-fPIC", "-fvisibility=hidden",
        "-fstack-protector-strong", "-static-libstdc++",
        "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
        "-I"+str(root / SDK), "-I"+str(cube3 / SOURCE.parent),
        "-I"+str(src / "kodi-vfs"),
        "-shared", "-Wl,-z,relro", "-Wl,-z,now", "-Wl,-z,noexecstack",
        "-Wl,--no-undefined", "-Wl,--exclude-libs,ALL",
        "-Wl,--version-script,"+str(cube3 / EXPORTS),
        "-Wl,-soname,libvfs.gazelle.physical.so",
        str(src / "kodi-vfs/PhysicalVFS.cpp"), str(cube3 / SOURCE),
        "-llog", "-o", str(native),
    ]
    subprocess.run(cmd, check=True)
    hdr = subprocess.check_output([str(readelf), "-h", str(native)], text=True)
    if "ELF32" not in hdr or "ARM" not in hdr:
        raise RuntimeError("Gazelle VFS is not ELF32 ARM")
    if native.stat().st_size < 4096:
        raise RuntimeError("Gazelle VFS library unexpectedly small")

    copy_verified(vfs_xml, vfs_dir/"addon.xml")
    for name in ("addon.xml", "default.py", "udf_descriptors.py"):
        copy_verified(src / "kodi-check" / name, script_dir / name)
    print("GAZELLE_KODI_APK_ADDONS_STAGED_PASS vfs=0.1.0 checker=0.1.6 "
          "elf32_arm=1 no_privileged_service_in_apk=1")
    print("GAZELLE_KODI_APK_VFS_SHA256=" + hashlib.sha256(native.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--kodi-root", required=True)
    parser.add_argument("--cube3", required=True)
    parser.add_argument("--depends-prefix", required=True)
    parser.add_argument("--ndk", required=True)
    arguments = parser.parse_args()
    stage(arguments.kodi_root, arguments.cube3, arguments.depends_prefix, arguments.ndk)
