#!/usr/bin/env python3
"""Stage source-local Gazelle kernel UDF files into Kodi/Android asset trees."""
import argparse
from pathlib import Path
from shutil import copyfile
from xml.etree import ElementTree

ADDON = "plugin.video.gazelle.kerneludf"
FILES = ("addon.xml", "default.py")


def copy_addon(root, target):
    source = Path(root).resolve() / "addons" / ADDON
    metadata = ElementTree.parse(source / "addon.xml").getroot()
    if metadata.tag != "addon" or metadata.get("id") != ADDON:
        raise ValueError("Unexpected kernel UDF addon identity")
    target.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        src = source / name
        if not src.is_file() or src.is_symlink():
            raise ValueError("Missing or symlinked addon file: " + str(src))
        copyfile(src, target / name)
        if (target / name).read_bytes() != src.read_bytes():
            raise ValueError("Addon copy mismatch: " + name)


def register_manifest(manifest):
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("Android addon manifest missing: " + str(manifest))
    tree = ElementTree.parse(manifest)
    root = tree.getroot()
    if root.tag != "addons":
        raise ValueError("Unexpected Kodi system addon manifest")
    matches = [x for x in root.findall("addon") if (x.text or "").strip() == ADDON]
    if len(matches) > 1:
        raise ValueError("Duplicate Gazelle kernel addon entry")
    if not matches:
        ElementTree.SubElement(root, "addon", {"optional": "true"}).text = ADDON
    elif matches[0].get("optional") != "true":
        raise ValueError("Gazelle addon must be optional")
    ElementTree.indent(tree, space="  ")
    tree.write(manifest, encoding="utf-8", xml_declaration=True)


def main(root, prefix=None, assets=None):
    if (prefix is None) == (assets is None):
        raise ValueError("Use exactly one of --depends-prefix or --assets")
    if prefix is not None:
        target = Path(prefix).resolve() / "share/kodi/addons" / ADDON
        copy_addon(root, target)
        print("GAZELLE_KERNEL_UDF_ADDON_DEPENDS_STAGED_PASS")
    else:
        assets_dir = Path(assets).resolve()
        copy_addon(root, assets_dir / "addons" / ADDON)
        register_manifest(assets_dir / "system/addon-manifest.xml")
        print("GAZELLE_KERNEL_UDF_ANDROID_ASSETS_PASS manifest=1 files=2")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--depends-prefix")
    group.add_argument("--assets")
    args = parser.parse_args()
    main(args.root, args.depends_prefix, args.assets)
