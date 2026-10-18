#!/usr/bin/env python3
"""Stage the local read-only UDF addon into Kodi's Android depends prefix."""
import argparse
from pathlib import Path
from shutil import copyfile
from xml.etree import ElementTree

ADDON = "plugin.video.gazelle.kerneludf"


def main(root, prefix):
    source = Path(root).resolve() / "addons" / ADDON
    target = Path(prefix).resolve() / "share/kodi/addons" / ADDON
    manifest = ElementTree.parse(source / "addon.xml").getroot()
    if manifest.tag != "addon" or manifest.get("id") != ADDON:
        raise ValueError("Unexpected kernel UDF addon identity")
    for name in ("addon.xml", "default.py"):
        src = source / name
        if not src.is_file() or src.is_symlink():
            raise ValueError("Missing or symlinked addon file: " + str(src))
        target.mkdir(parents=True, exist_ok=True)
        copyfile(src, target / name)
    print("GAZELLE_KERNEL_UDF_ADDON_STAGED_PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--depends-prefix", required=True)
    args = parser.parse_args()
    main(args.root, args.depends_prefix)
