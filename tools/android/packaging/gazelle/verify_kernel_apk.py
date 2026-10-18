#!/usr/bin/env python3
"""Check that a Kodi APK includes kernel-UDF navigation without old VFS addons."""
import argparse
import zipfile
from xml.etree import ElementTree

PREFIX = "assets/addons/plugin.video.gazelle.kerneludf/"


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        if archive.testzip() is not None:
            raise ValueError("APK ZIP corruption")
        files = set(archive.namelist())
        if not {PREFIX+"addon.xml", PREFIX+"default.py"} <= files:
            raise ValueError("Missing kernel UDF addon files")
        addon = ElementTree.fromstring(archive.read(PREFIX + "addon.xml"))
        if addon.tag != "addon" or addon.get("id") != "plugin.video.gazelle.kerneludf":
            raise ValueError("Incorrect addon identity")
        obsolete = ("vfs.gazelle.physical", "script.gazelle.physicaludfcheck",
                    "libvfs.gazelle.physical.so")
        if any(any(part in path for part in obsolete) for path in files):
            raise ValueError("Userspace optical addon in APK")
    print("GAZELLE_KERNEL_UDF_APK_PASS userspace_vfs=0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("apk")
    verify(parser.parse_args().apk)
