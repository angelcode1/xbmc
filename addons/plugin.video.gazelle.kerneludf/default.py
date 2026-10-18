# -*- coding: utf-8 -*-
"""Expose a verified kernel UDF mount; no raw-sector or privileged access."""
import os
import sys

import xbmcgui
import xbmcplugin

MOUNTS = ("/data/user/0/org.xbmc.kodi/files/gazelle-kernel-udf",
          "/data/data/org.xbmc.kodi/files/gazelle-kernel-udf")


def get_readonly_mount():
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as info:
            for row in info:
                left, sep, right = row.rstrip("\n").partition(" - ")
                if not sep:
                    continue
                fields, source = left.split(), right.split()
                if len(fields) < 6 or len(source) < 3:
                    continue
                path = fields[4].replace(r"\040", " ")
                if (path in MOUNTS and source[:2] == ["udf", "/dev/block/sr0"]
                        and "ro" in fields[5].split(",") and os.path.isdir(path)):
                    return path
    except OSError:
        pass
    return None


def main():
    handle = int(sys.argv[1])
    mount = get_readonly_mount()
    if mount is None:
        xbmcgui.Dialog().notification("Kernel UDF Optical Disc",
                                      "No read-only UDF disc mounted",
                                      xbmcgui.NOTIFICATION_WARNING, 5000)
        xbmcplugin.endOfDirectory(handle)
        return
    bluray = os.path.join(mount, "BDMV", "index.bdmv")
    if os.path.isfile(bluray):
        item = xbmcgui.ListItem(label="Play Blu-ray Disc", path=bluray)
        item.setProperty("IsPlayable", "true")
        xbmcplugin.addDirectoryItem(handle, bluray, item, isFolder=False)
    item = xbmcgui.ListItem(label="Browse Disc Files", path=mount)
    xbmcplugin.addDirectoryItem(handle, mount + "/", item, isFolder=True)
    xbmcplugin.endOfDirectory(handle)


if __name__ == "__main__":
    main()
