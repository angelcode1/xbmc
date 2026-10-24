#!/usr/bin/env python3
"""Compile and link UNMODIFIED Kodi CDVDMessageQueue .cpp/.h as distinct host TUs.

The two queue source files are copied byte-for-byte from this checkout;
only external Kodi platform/message dependencies are replaced by minimal host
headers. The queue's real Put/Get/PutBack/Flush/Abort/End bodies are linked,
not extracted, transformed, reimplemented or mocked. This is not a complete
Kodi build; packet message/demux allocation and mutex/event/log are shims.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
QUEUE = ROOT / "xbmc/cores/VideoPlayer"
POLICY = QUEUE / "DVDCodecs/Video/GazelleFELProducerEpoch.h"

FAKES = {
    "threads/CriticalSection.h": r"""
#pragma once
#include <mutex>
// Offline platform shim: actual Kodi uses CCriticalSection; recursive because
// CDVDMessageQueue::End nests a call to Flush under the same critical section.
using CCriticalSection = std::recursive_mutex;
""",
    "threads/Event.h": r"""
#pragma once
#include <chrono>
#include <condition_variable>
#include <mutex>
class CEvent {
public:
  explicit CEvent(bool initial=false) : m_signaled(initial) {}
  void Set() { std::lock_guard<std::mutex> g(m_mutex); m_signaled=true; m_cv.notify_all(); }
  void Reset() { std::lock_guard<std::mutex> g(m_mutex); m_signaled=false; }
  bool Wait(std::chrono::milliseconds d) {
    std::unique_lock<std::mutex> lock(m_mutex);
    return m_cv.wait_for(lock,d,[&]{return m_signaled;});
  }
private:
  std::mutex m_mutex;
  std::condition_variable m_cv;
  bool m_signaled;
};
""",
    "cores/VideoPlayer/Interface/TimingConstants.h": r"""
#pragma once
constexpr double DVD_NOPTS_VALUE = -4503599627370496.0;
constexpr double DVD_TIME_BASE = 1000000.0;
""",
    "cores/VideoPlayer/Interface/DemuxPacket.h": r"""
#pragma once
#include "cores/VideoPlayer/Interface/TimingConstants.h"
struct DemuxPacket {
  int iSize{0};
  double dts{DVD_NOPTS_VALUE};
  double pts{DVD_NOPTS_VALUE};
  unsigned* destroyed{nullptr};
};
""",
    "utils/log.h": r"""
#pragma once
constexpr int LOGDEBUG=0, LOGWARNING=1, LOGFATAL=2, LOGINFO=3;
struct CLog {
  template<class... T> static void Log(int, const char*, T&&...) {}
};
""",
    "DVDMessage.h": r"""
#pragma once
// Explicit host shim of only the message types the REAL Kodi queue calls.
// CDVDMessageQueue.h / CDVDMessageQueue.cpp are NOT shimmed or modified.
// The real CDVDMsgDemuxerPacket destructor normally invokes
// CDVDDemuxUtils::FreeDemuxPacket; here a host counter stands in for it.
#include "cores/VideoPlayer/Interface/DemuxPacket.h"
#include <atomic>
#include <chrono>
#include <cstdint>
#include <memory>
constexpr unsigned SYNCSOURCE_ANY = 0x08;
class CDVDMsg {
public:
  enum Message {NONE=1000, GENERAL_FLUSH, GENERAL_RESET, GENERAL_SYNCHRONIZE,
                DEMUXER_PACKET};
  explicit CDVDMsg(Message type) : m_type(type) {}
  virtual ~CDVDMsg() = default;
  bool IsType(Message type) const { return m_type == type; }
private:
  Message m_type;
};
class CDVDMsgDemuxerPacket : public CDVDMsg {
public:
  explicit CDVDMsgDemuxerPacket(DemuxPacket* packet)
    : CDVDMsg(DEMUXER_PACKET), m_packet(packet) {}
  ~CDVDMsgDemuxerPacket() override {
    if (m_packet && m_packet->destroyed)
      ++*m_packet->destroyed;
    delete m_packet;
  }
  DemuxPacket* GetPacket() { return m_packet; }
  bool TrySetGazelleResearchEpoch(std::uint64_t next) noexcept {
    if (next == 0 || m_researchEpoch != 0) return false;
    m_researchEpoch = next; return true;
  }
  std::uint64_t GetGazelleResearchEpoch() const noexcept { return m_researchEpoch; }
private:
  DemuxPacket* m_packet;
  std::uint64_t m_researchEpoch{0};
};
class CDVDMsgGeneralSynchronize : public CDVDMsg {
public:
  CDVDMsgGeneralSynchronize(std::chrono::milliseconds, unsigned)
    : CDVDMsg(GENERAL_SYNCHRONIZE) {}
  void Wait(std::atomic<bool>&, unsigned) {}
};
""",
}

TEST = r"""
#include "DVDMessageQueue.h"
#include "GazelleFELProducerEpoch.h"

#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <utility>

using Ingress = GazelleFELPrecreate::ProducerEpoch<CDVDMsgDemuxerPacket,
                                                    CDVDMessageQueue>;
static std::shared_ptr<CDVDMsgDemuxerPacket>
Packet(int size, double ts, unsigned* freed) {
  auto* raw = new DemuxPacket;
  raw->iSize=size; raw->dts=ts; raw->pts=ts; raw->destroyed=freed;
  return std::make_shared<CDVDMsgDemuxerPacket>(raw);
}
static bool Barrier(Ingress& ingress) {
  return ingress.PutBarrier([](std::uint64_t) {
    return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
  });
}
static std::shared_ptr<CDVDMsg> Pop(CDVDMessageQueue& queue, int& prio) {
  std::shared_ptr<CDVDMsg> result;
  assert(queue.Get(result, std::chrono::milliseconds(0), prio)==MSGQ_OK);
  return result;
}
int main() {
  // Link and run the CHECKED-IN queue Put/Get + the research ProducerEpoch,
  // retaining each original shared owner, stamping before real queue.Put.
  {
    CDVDMessageQueue queue("gazelle-linked-original");
    queue.Init(); queue.SetMaxDataSize(1024);
    Ingress sender(queue);
    unsigned freed=0;
    auto old = Packet(17,1000000,&freed);
    auto* oldId=old.get();
    assert(sender.PutOriginal(old) && old->GetGazelleResearchEpoch()==1);
    assert(!sender.PutOriginal(old)); // same original cannot be put twice
    old.reset();
    assert(Barrier(sender)); // priority control after old ordinary packet
    assert(sender.ProducerEpochForAuditOnly()==2);
    auto current=Packet(29,2000000,&freed);
    auto* currentId=current.get();
    assert(sender.PutOriginal(current) && current->GetGazelleResearchEpoch()==2);
    current.reset();
    assert(queue.GetDataSize()==46 && freed==0);
    int priority=0;
    auto first=Pop(queue,priority);
    assert(first->IsType(CDVDMsg::GENERAL_FLUSH) && priority==1);
    first.reset();
    priority=0;
    auto stale=Pop(queue,priority);
    assert(stale.get()==oldId &&
      std::static_pointer_cast<CDVDMsgDemuxerPacket>(stale)->GetGazelleResearchEpoch()==1);
    assert(queue.GetDataSize()==29);
    stale.reset();
    assert(freed==1);
    priority=0;
    auto fresh=Pop(queue,priority);
    assert(fresh.get()==currentId &&
      std::static_pointer_cast<CDVDMsgDemuxerPacket>(fresh)->GetGazelleResearchEpoch()==2);
    fresh.reset();
    assert(queue.GetDataSize()==0 && freed==2);
    queue.End();
  }
  // Real queue PutBack(priority 0) reorders packets; replaying held owner
  // through it without designing priority semantics is NOT safe.
  {
    CDVDMessageQueue queue("gazelle-linked-putback");
    queue.Init(); queue.SetMaxDataSize(1024);
    unsigned freed=0;
    auto a=Packet(5,1000000,&freed);
    auto b=Packet(7,2000000,&freed);
    const auto* bId=b.get();
    assert(queue.Put(a,0)==MSGQ_OK && queue.PutBack(b,0)==MSGQ_OK);
    a.reset(); b.reset();
    assert(queue.GetDataSize()==12);
    int priority=0;
    auto first=Pop(queue,priority);
    assert(first.get()==bId && queue.GetDataSize()==5);
    first.reset();
    priority=0;
    auto second=Pop(queue,priority);
    assert(second && queue.GetDataSize()==0);
    second.reset();
    assert(freed==2);
    queue.End();
  }
  // Actual Flush implementation purges old AND post-barrier messages,
  // frees original owners exactly once and clears byte accounting.
  {
    CDVDMessageQueue queue("gazelle-linked-flush");
    queue.Init(); queue.SetMaxDataSize(1024);
    unsigned freed=0;
    auto old=Packet(11,1000000,&freed), fresh=Packet(13,2000000,&freed);
    assert(queue.Put(old,0)==MSGQ_OK);
    assert(queue.Put(std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH),1)==MSGQ_OK);
    assert(queue.Put(fresh,0)==MSGQ_OK);
    old.reset(); fresh.reset();
    int priority=0;
    auto control=Pop(queue,priority);
    assert(control->IsType(CDVDMsg::GENERAL_FLUSH));
    control.reset();
    queue.Flush();
    assert(queue.GetDataSize()==0 && freed==2);
    queue.Flush();
    assert(freed==2);
    queue.End();
  }
  // The real aborted queue rejects Get and End clears old owners; rejected
  // producer.Put must not mutate the queue/duplicate a packet owner.
  {
    CDVDMessageQueue queue("gazelle-linked-abort");
    queue.Init(); queue.SetMaxDataSize(1024);
    unsigned freed=0;
    assert(queue.Put(Packet(2,1000000,&freed))==MSGQ_OK);
    queue.Abort();
    std::shared_ptr<CDVDMsg> msg;
    int priority=0;
    assert(queue.Get(msg, std::chrono::milliseconds(0),priority)==MSGQ_ABORT);
    queue.End();
    assert(freed==1);
    Ingress sender(queue);
    auto rejected=Packet(3,2000000,&freed);
    assert(!sender.PutOriginal(rejected));
    assert(rejected->GetGazelleResearchEpoch()==1);
    assert(!sender.PutOriginal(rejected));
    rejected.reset();
    assert(freed==2);
  }
  std::puts("GAZELLE_KODI_UNMODIFIED_QUEUE_OBJECT_LINK_PASS "
            "real_kodi_queue_cpp=true real_kodi_queue_header=true "
            "producer_stamp_pre_put=true priority_flush_overtake=true "
            "putback_reorders=true flush_bytes_destructors_once=true "
            "abort_and_reject=true external_platform_message_shims=true "
            "actual_kodi_message_header=false full_kodi_link=false "
            "no_device=true fel_switch_off=true");
}
"""

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ubsan", action="store_true")
    options = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="gazelle-linked-real-queue-") as temp:
        root = pathlib.Path(temp)
        original_sources = (
            (QUEUE / "DVDMessageQueue.h", root / "DVDMessageQueue.h"),
            (QUEUE / "DVDMessageQueue.cpp", root / "DVDMessageQueue.cpp"),
        )
        for original, target in original_sources:
            shutil.copyfile(original, target)
            if hashlib.sha256(original.read_bytes()).digest() != \
               hashlib.sha256(target.read_bytes()).digest():
                raise AssertionError("GAZELLE_UNMODIFIED_QUEUE_SOURCE_REFUSED")

        for relative, code in FAKES.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code, encoding="utf8")
        (root / "queue_object_link_test.cpp").write_text(TEST, encoding="utf8")
        args = ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-pedantic", "-pthread", "-O1" if options.ubsan else "-O2"]
        if options.ubsan:
            args += ["-g", "-fsanitize=undefined", "-fno-sanitize-recover=all"]
        args += ["-I", str(root), "-I", str(POLICY.parent),
                 str(root / "DVDMessageQueue.cpp"),
                 str(root / "queue_object_link_test.cpp"), "-o", str(root / "queue_linked")]
        subprocess.run(args, check=True, timeout=50)
        subprocess.run([str(root / "queue_linked")], check=True, timeout=20)

if __name__ == "__main__":
    main()
