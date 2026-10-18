#!/usr/bin/env python3
"""Verify the APK's Gazelle kernel-UDF addon files and system registration."""
import argparse
import zipfile
from xml.etree import ElementTree

ADDON = "plugin.video.gazelle.kerneludf"
PREFIX = "assets/addons/" + ADDON + "/"
MANIFEST = "assets/system/addon-manifest.xml"


def verify(apk):
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
    print("GAZELLE_KERNEL_UDF_APK_PASS manifest=1 userspace_vfs=0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("apk")
    verify(parser.parse_args().apk)
