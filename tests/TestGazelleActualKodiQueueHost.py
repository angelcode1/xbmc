#!/usr/bin/env python3
"""Execute actual checked-in Kodi CDVDMessageQueue methods with host platform shims.

This is source-backed, not a full Kodi link: original DVDMessageQueue.h's class
and DVDMessageQueue.cpp's function implementations are copied verbatim from the
current checkout into a temporary TU; only external platform/message
dependencies are stubbed. Re-tests exact source behaviour, not a rewritten
queue model. No vendor/device/APK actions or MediaCodec.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADER = ROOT / "xbmc/cores/VideoPlayer/DVDMessageQueue.h"
CPP = ROOT / "xbmc/cores/VideoPlayer/DVDMessageQueue.cpp"

PRELUDE = r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <list>
#include <memory>
#include <mutex>
#include <string>
#include <utility>

using namespace std::chrono_literals;
constexpr double DVD_NOPTS_VALUE = -4503599627370496.0;
constexpr double DVD_TIME_BASE = 1000000.0;
constexpr int LOGDEBUG=0, LOGWARNING=1, LOGFATAL=2, LOGINFO=3;
struct CLog {
  template<class... Args> static void Log(int, const char*, Args&&...) {}
};
using CCriticalSection = std::recursive_mutex;
class CEvent {
public:
  explicit CEvent(bool set = false) : m_set(set) {}
  void Set() { std::lock_guard<std::mutex> l(m_lock); m_set = true; m_cv.notify_all(); }
  void Reset() { std::lock_guard<std::mutex> l(m_lock); m_set = false; }
  bool Wait(std::chrono::milliseconds duration) {
    std::unique_lock<std::mutex> l(m_lock);
    return m_cv.wait_for(l, duration, [&] { return m_set; });
  }
private:
  std::mutex m_lock;
  std::condition_variable m_cv;
  bool m_set;
};
struct DemuxPacket {
  int iSize{};
  double dts{DVD_NOPTS_VALUE};
  double pts{DVD_NOPTS_VALUE};
  int* destroyed{};
};
struct CDVDMsg {
  enum Message {
    NONE=1000, GENERAL_FLUSH, GENERAL_RESET, GENERAL_SYNCHRONIZE,
    DEMUXER_PACKET
  };
  explicit CDVDMsg(Message t): m_type(t) {}
  virtual ~CDVDMsg() = default;
  bool IsType(Message t) const { return m_type == t; }
  Message m_type;
};
struct CDVDMsgDemuxerPacket final : CDVDMsg {
  explicit CDVDMsgDemuxerPacket(DemuxPacket* p)
    : CDVDMsg(DEMUXER_PACKET), m_packet(p) {}
  ~CDVDMsgDemuxerPacket() override {
    if (m_packet && m_packet->destroyed)
      ++*m_packet->destroyed;
    delete m_packet;
  }
  DemuxPacket* GetPacket() { return m_packet; }
  DemuxPacket* m_packet{};
};
struct CDVDMsgGeneralSynchronize final : CDVDMsg {
  CDVDMsgGeneralSynchronize(std::chrono::milliseconds, unsigned)
    : CDVDMsg(GENERAL_SYNCHRONIZE) {}
  void Wait(std::atomic<bool>&, unsigned) {}
};
"""

TESTS = r"""
static std::shared_ptr<CDVDMsgDemuxerPacket>
Packet(int bytes, double dts, int* freed) {
  auto* p = new DemuxPacket;
  p->iSize=bytes; p->dts=dts; p->pts=dts; p->destroyed=freed;
  return std::make_shared<CDVDMsgDemuxerPacket>(p);
}
int main() {
  // Actual Kodi queue Put/Get code: priority flush overtakes normal packets.
  {
    CDVDMessageQueue q("gazelle-source-backed");
    q.Init(); q.SetMaxDataSize(1000);
    int freed=0;
    auto a=Packet(10, 1000000, &freed);
    auto b=Packet(20, 2000000, &freed);
    const auto* aId=a.get();
    const auto* bId=b.get();
    assert(q.Put(a)==MSGQ_OK);
    assert(q.Put(b)==MSGQ_OK);
    a.reset(); b.reset();
    assert(q.GetDataSize()==30);
    auto flush=std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    assert(q.Put(flush,1)==MSGQ_OK);
    flush.reset();
    std::shared_ptr<CDVDMsg> first;
    int priority=0;
    assert(q.Get(first,0ms,priority)==MSGQ_OK);
    assert(first->IsType(CDVDMsg::GENERAL_FLUSH) && priority==1);
    first.reset();
    assert(q.GetDataSize()==30 && freed==0);

    priority=0;
    assert(q.Get(first,0ms,priority)==MSGQ_OK);
    assert(first.get()==aId && priority==0);
    assert(q.GetDataSize()==20);
    first.reset();
    assert(freed==1);
    priority=0;
    assert(q.Get(first,0ms,priority)==MSGQ_OK);
    assert(first.get()==bId && q.GetDataSize()==0);
    first.reset();
    assert(freed==2);
    priority=0;
    assert(q.Get(first,0ms,priority)==MSGQ_TIMEOUT);
    q.End();
  }
  // Kodi Flush(DEMuXER_PACKET) releases original shared message owners and
  // resets the real queue's byte accounting. No packet wrapper is recreated.
  {
    CDVDMessageQueue q("gazelle-source-backed");
    q.Init(); q.SetMaxDataSize(1000);
    int freed=0;
    assert(q.Put(Packet(5, 1000000, &freed))==MSGQ_OK);
    assert(q.Put(Packet(7, 2000000, &freed))==MSGQ_OK);
    assert(q.GetDataSize()==12 && freed==0);
    q.Flush(CDVDMsg::DEMUXER_PACKET);
    assert(q.GetDataSize()==0 && freed==2);
    q.Flush(CDVDMsg::DEMUXER_PACKET);
    assert(freed==2);
    q.End();
  }
  // PutBack with priority 0 deliberately reorders to the back (which Get
  // pops first); this cannot be assumed a safe post-seek replay operation.
  {
    CDVDMessageQueue q("gazelle-source-backed");
    q.Init(); q.SetMaxDataSize(1000);
    int freed=0;
    auto first=Packet(3, 1000000, &freed);
    auto replay=Packet(4, 2000000, &freed);
    const auto* replayId=replay.get();
    assert(q.Put(first,0)==MSGQ_OK);
    assert(q.PutBack(replay,0)==MSGQ_OK);
    first.reset(); replay.reset();
    std::shared_ptr<CDVDMsg> out; int priority=0;
    assert(q.Get(out,0ms,priority)==MSGQ_OK);
    assert(out.get()==replayId && q.GetDataSize()==3);
    out.reset();
    assert(q.Get(out,0ms,priority)==MSGQ_OK);
    out.reset();
    assert(freed==2);
    q.End();
  }
  // Normal Flush can purge post-control queue entries as well as old ones:
  // correctness requires reliable packet generations, not dequeue stamping.
  {
    CDVDMessageQueue q("gazelle-source-backed");
    q.Init(); q.SetMaxDataSize(1000);
    int freed=0;
    assert(q.Put(Packet(6, 1000000, &freed))==MSGQ_OK);
    assert(q.Put(std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH),1)==MSGQ_OK);
    assert(q.Put(Packet(8, 3000000, &freed))==MSGQ_OK);
    std::shared_ptr<CDVDMsg> barrier; int priority=0;
    assert(q.Get(barrier,0ms,priority)==MSGQ_OK && priority==1);
    barrier.reset();
    q.Flush(); // the actual Kodi handler invokes FlushMessages()
    assert(q.GetDataSize()==0 && freed==2);
    priority=0;
    assert(q.Get(barrier,0ms,priority)==MSGQ_TIMEOUT);
    q.End();
  }
  // Abort/End no double-release or queued playback after closing queue.
  {
    CDVDMessageQueue q("gazelle-source-backed");
    q.Init(); q.SetMaxDataSize(1000);
    int freed=0;
    assert(q.Put(Packet(10, 1000000, &freed))==MSGQ_OK);
    q.Abort();
    std::shared_ptr<CDVDMsg> out; int priority=0;
    assert(q.Get(out,0ms,priority)==MSGQ_ABORT);
    q.End();
    assert(freed==1);
    assert(q.Put(Packet(3, 1000000, &freed))==MSGQ_NOT_INITIALIZED);
    assert(freed==2);
  }
  std::puts("GAZELLE_KODI_REAL_QUEUE_BODY_HOST_PASS "
            "kodi_queue_methods=UNCHANGED priority_flush_overtake=true "
            "putback_order_measured=true byte_accounting=true "
            "flush_destructors_once=true abort_end=true "
            "actual_kodi_headers=false full_kodi_link=false no_device=true");
}
"""

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ubsan", action="store_true")
    opts = parser.parse_args()

    header = HEADER.read_text(encoding="utf8")
    cpp = CPP.read_text(encoding="utf8")
    start_h = "struct DVDMessageListItem"
    start_c = "using namespace std::chrono_literals;"
    if start_h not in header or start_c not in cpp:
        raise SystemExit("GAZELLE_QUEUE_SOURCE_REFUSED: missing actual Kodi queue method anchors")
    # The generated TU retains the checked-in Kodi class and method bodies,
    # changing only external-platform includes. No regex/body substitutions.
    source = (PRELUDE + "\n" + header[header.index(start_h):] + "\n"
              + cpp[cpp.index(start_c):] + "\n" + TESTS)

    with tempfile.TemporaryDirectory(prefix="gazelle-kodi-queue-") as temp:
        temp_path = pathlib.Path(temp)
        cpp_path = temp_path / "queue-test.cpp"
        exe_path = temp_path / "queue-test"
        cpp_path.write_text(source, encoding="utf8")
        cmd = ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
               "-pedantic", "-pthread", "-O1" if opts.ubsan else "-O2"]
        if opts.ubsan:
            cmd += ["-g", "-fsanitize=undefined", "-fno-sanitize-recover=all"]
        cmd += [str(cpp_path), "-o", str(exe_path)]
        subprocess.run(cmd, check=True, timeout=45)
        subprocess.run([str(exe_path)], check=True, timeout=20)

if __name__ == "__main__":
    main()
