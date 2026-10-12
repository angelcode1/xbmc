#!/usr/bin/env python3
"""Fail closed unless the APK includes both verified Gazelle Kodi addons."""
import argparse
import pathlib
import zipfile
import xml.etree.ElementTree as ET

def run(apk):
    apk = pathlib.Path(apk)
    if not apk.is_file():
        raise RuntimeError("APK unavailable: " + str(apk))
    with zipfile.ZipFile(apk) as z:
        if z.testzip() is not None:
            raise RuntimeError("Corrupted APK archive")
        names = set(z.namelist())
        needed = {
            "assets/addons/vfs.gazelle.physical/addon.xml",
            "assets/addons/script.gazelle.physicaludfcheck/addon.xml",
            "assets/addons/script.gazelle.physicaludfcheck/default.py",
            "assets/addons/script.gazelle.physicaludfcheck/udf_descriptors.py",
        }
        missing = sorted(needed - names)
        if missing:
            raise RuntimeError("Gazelle APK addon files missing: " + repr(missing))
        files = [n for n in names if n.startswith("lib/") and
                 n.endswith("/libvfs.gazelle.physical.so")]
        if len(files) != 1:
            raise RuntimeError("Exactly one native Gazelle VFS library required")
        native = z.read(files[0])
        if native[:20] != b"\\x7fELF" + bytes([1,1,1]) + bytes(11) + bytes([40,0]):
            # Check ELF magic, class and e_machine separately, below.
            if not (native[:5] == b"\\x7fELF\\x01" and
                    int.from_bytes(native[18:20], "little") == 40):
                raise RuntimeError("Incorrect Gazelle VFS ELF architecture")
        for name, identity, version in (
            ("assets/addons/vfs.gazelle.physical/addon.xml", "vfs.gazelle.physical", "0.1.0"),
            ("assets/addons/script.gazelle.physicaludfcheck/addon.xml",
             "script.gazelle.physicaludfcheck", "0.1.6"),
        ):
            tag = ET.fromstring(z.read(name))
            if tag.attrib.get("id") != identity or tag.attrib.get("version") != version:
                raise RuntimeError("Incorrect Gazelle addon metadata " + name)
        if any(n.endswith("udf.ko") or "gazelle_optical_root_v1" in n for n in names):
            raise RuntimeError("Privileged driver/root service must not be inside APK")
    print("GAZELLE_KODI_APK_BUNDLED_ADDONS_PASS vfs=1 checker=1 "
          "elf32_arm=1 no_root_binary=1")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("apk")
    run(parser.parse_args().apk)
