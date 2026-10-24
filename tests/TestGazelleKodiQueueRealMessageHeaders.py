#!/usr/bin/env python3
"""Offline link Kodi's ORIGINAL queue and message headers with real packet-message methods.

The actual DVDMessageQueue.cpp, DVDMessageQueue.h and DVDMessage.h are copied
byte-for-byte from current Kodi source. The real DVDMessage.cpp definitions
of CDVDMsgDemuxerPacket ctor/dtor/GetPacketSize are extracted WITHOUT editing
and compiled as a separate object. Only FileItem/IPlayer, platform primitives,
demux-packet allocation/free and synchronization primitives are host shims.
This is NOT a complete DVDMessage.cpp build, Kodi runtime or native FEL test.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import tempfile

from TestGazelleKodiQueueObjectLink import FAKES, TEST, QUEUE, POLICY

ROOT = pathlib.Path(__file__).resolve().parents[1]

def packet_message_methods() -> str:
    source = (QUEUE / "DVDMessage.cpp").read_text(encoding="utf8")
    begin = source.find("CDVDMsgDemuxerPacket::CDVDMsgDemuxerPacket(")
    function = source.find("unsigned int CDVDMsgDemuxerPacket::GetPacketSize()", begin)
    last = source.find("\n}\n", function)
    if min(begin, function, last) < 0:
        raise AssertionError("GAZELLE_ACTUAL_KODI_PACKET_MESSAGE_METHODS_MISSING")
    return source[begin:last + 3]

def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--ubsan", action="store_true")
    options = args.parse_args()
    with tempfile.TemporaryDirectory(prefix="gazelle-real-kodi-messages-") as td:
        root = pathlib.Path(td)
        for name in ("DVDMessageQueue.cpp", "DVDMessageQueue.h", "DVDMessage.h"):
            original = QUEUE / name
            output = root / name
            shutil.copyfile(original, output)
            if hashlib.sha256(output.read_bytes()).digest() != \
               hashlib.sha256(original.read_bytes()).digest():
                raise AssertionError("GAZELLE_ORIGINAL_KODI_HEADERS_MODIFIED")
        for name, code in FAKES.items():
            if name == "DVDMessage.h":
                continue
            dst = root / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(code, encoding="utf8")

        other = {
            "FileItem.h": r"""
#pragma once
// External FileItem dependency only, not the Kodi message definitions.
#include <chrono>
#include <memory>
class CFileItem {
public:
  CFileItem() = default;
};
""",
            "cores/IPlayer.h": r"""
#pragma once
struct CPlayerOptions {};
""",
            "DVDDemuxers/DVDDemuxUtils.h": r"""
#pragma once
#include "cores/VideoPlayer/Interface/DemuxPacket.h"
// Only the platform demux packet allocator/freeer is substituted.
// CDVDMsgDemuxerPacket's REAL destructor invokes this function unchanged.
struct CDVDDemuxUtils {
  static void FreeDemuxPacket(DemuxPacket* packet) {
    if (packet && packet->destroyed)
      ++*packet->destroyed;
    delete packet;
  }
};
""",
        }
        for name, code in other.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code, encoding="utf8")

        real_message_impl = (
            '#include "DVDMessage.h"\n'
            '#include "cores/VideoPlayer/Interface/DemuxPacket.h"\n'
            '#include "DVDDemuxers/DVDDemuxUtils.h"\n\n'
            + packet_message_methods() + '\n'
            + r"""
// Synchronize-message implementation is an external host shim. Its actual
// Kodi implementation depends on threading/ConditionVariable/EndTime.
CDVDMsgGeneralSynchronize::CDVDMsgGeneralSynchronize(
    std::chrono::milliseconds, unsigned)
    : CDVDMsg(GENERAL_SYNCHRONIZE), m_p(nullptr) {}
CDVDMsgGeneralSynchronize::~CDVDMsgGeneralSynchronize() = default;
bool CDVDMsgGeneralSynchronize::Wait(std::chrono::milliseconds, unsigned) {
  return true;
}
void CDVDMsgGeneralSynchronize::Wait(std::atomic<bool>&, unsigned) {}
"""
        )
        (root / "packet_message_real_methods.cpp").write_text(real_message_impl, encoding="utf8")
        (root / "queue_and_messages.cpp").write_text(TEST.replace(
            "GAZELLE_KODI_UNMODIFIED_QUEUE_OBJECT_LINK_PASS",
            "GAZELLE_KODI_REAL_MESSAGE_HEADER_AND_QUEUE_LINK_PASS").replace(
            "actual_kodi_message_header=false", "actual_kodi_message_header=true"
        ).replace(
            "external_platform_message_shims=true",
            "real_packet_msg_ctor_dtor=true platform_shims=true"
        ), encoding="utf8")

        cmd = ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
               "-pedantic", "-pthread", "-O1" if options.ubsan else "-O2"]
        if options.ubsan:
            cmd += ["-g", "-fsanitize=undefined", "-fno-sanitize-recover=all"]
        cmd += ["-I", str(root), "-I", str(POLICY.parent),
                str(root / "DVDMessageQueue.cpp"),
                str(root / "packet_message_real_methods.cpp"),
                str(root / "queue_and_messages.cpp"),
                "-o", str(root / "real_kodi_message_queue")]
        subprocess.run(cmd, check=True, timeout=45)
        subprocess.run([str(root / "real_kodi_message_queue")], check=True, timeout=20)

if __name__ == "__main__":
    main()
