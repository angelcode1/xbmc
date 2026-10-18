#!/usr/bin/env python3
"""Verify the APK's Gazelle kernel-UDF addon files and system registration."""
import argparse
import hashlib
import re
import struct
import zipfile
from xml.etree import ElementTree

ADDON = "plugin.video.gazelle.kerneludf"
PREFIX = "assets/addons/" + ADDON + "/"
MANIFEST = "assets/system/addon-manifest.xml"


def verify(apk, *, kernel_only=False):
    with zipfile.ZipFile(apk) as archive:
        if archive.testzip() is not None:
            raise ValueError("APK ZIP corruption")
        paths = set(archive.namelist())
        missing = sorted({PREFIX + "addon.xml", PREFIX + "default.py", MANIFEST} - paths)
        if missing:
            related = sorted(p for p in paths if "gazelle" in p.lower() or
                             "addon-manifest.xml" in p)
            raise ValueError("Missing kernel UDF APK assets: {} (related: {})".
                             format(missing, related[:40]))
        metadata = ElementTree.fromstring(archive.read(PREFIX + "addon.xml"))
        if metadata.tag != "addon" or metadata.get("id") != ADDON:
            raise ValueError("Incorrect Gazelle kernel UDF addon identity")
        manifest = ElementTree.fromstring(archive.read(MANIFEST))
        registered = [node for node in manifest.findall("addon")
                      if (node.text or "").strip() == ADDON]
        if len(registered) != 1 or registered[0].get("optional") != "true":
            raise ValueError("Kernel UDF addon missing from optional system manifest")
        obsolete = ("vfs.gazelle.physical", "script.gazelle.physicaludfcheck",
                    "libvfs.gazelle.physical.so")
        if any(any(name in p for name in obsolete) for p in paths):
            raise ValueError("Legacy userspace optical addon still bundled")
        if kernel_only:
            print('GAZELLE_KERNEL_UDF_APK_SOURCE_PASS')
            return
        mm_service = "service.gazelle.mmbd"
        mm_prefix = "assets/addons/" + mm_service + "/"
        native_prefix = "lib/armeabi-v7a/"
        extra = {mm_prefix+"addon.xml", mm_prefix+"service.py",
                 native_prefix+"libmmbd.so", native_prefix+"libgazelle_mmbd_v2.so",
                 "assets/licenses/gazelle-libmmbd-LGPL-2.1.txt",
                 "assets/licenses/gazelle-libmmbd-source.txt"}
        missing = sorted(extra - paths)
        if missing:
            raise ValueError("Missing standalone MMBD APK payload: " + str(missing))
        service = archive.read(mm_prefix+"service.py").decode("utf-8")
        def pin(name):
            found = re.search(r"^" + name + r" = '([0-9a-f]{64})'$",
                              service, flags=re.MULTILINE)
            if not found:
                raise ValueError("Missing MMBD " + name + " digest")
            return found.group(1)
        lib = archive.read(native_prefix+"libmmbd.so")
        helper = archive.read(native_prefix+"libgazelle_mmbd_v2.so")
        for filename, data in (("libmmbd", lib), ("MMBD helper", helper)):
            if (len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01"
                    or struct.unpack_from("<HH", data, 16) != (3, 40)):
                raise ValueError(filename + " is not ARMv7 ELF32 ET_DYN")
        if hashlib.sha256(lib).hexdigest() != pin("LIB_SHA"):
            raise ValueError("MMBD native library mismatch")
        if hashlib.sha256(helper).hexdigest() != pin("HELPER_SHA"):
            raise ValueError("MMBD native helper mismatch")
        if hashlib.sha256(lib).hexdigest() != "826b5e6dfebfd628c1a6f851a22cb583fa831978600f4ddc2663af46794a8d0b":
            raise ValueError("Incorrect pinned ARMv7 libmmbd")
        registered = [node for node in manifest.findall("addon")
                      if (node.text or "").strip() == mm_service]
        if len(registered) != 1 or registered[0].get("optional") != "true":
            raise ValueError("MMBD startup service not registered as optional")
    print("GAZELLE_KERNEL_UDF_APK_PASS manifest=1 userspace_vfs=0")
    print("GAZELLE_MMBD_APK_PASS native=2 service=1 matching_pins=1")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("apk")
    parser.add_argument("--kernel-only", action="store_true")
    args = parser.parse_args()
    verify(args.apk, kernel_only=args.kernel_only)
