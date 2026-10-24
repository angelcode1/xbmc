#!/usr/bin/env python3
"""Host-linked Kodi original queue/header/packet methods + REAL typed owner bridge.

Original DVDMessageQueue.cpp/.h and DVDMessage.h are copied byte-for-byte.
CDVDMsgDemuxerPacket constructor/destructor/GetPacketSize methods are copied
verbatim from DVDMessage.cpp. Actual GazelleFELPrecreateKodiBridge.h,
GazelleFELProducerEpoch.h and PairOwners header are compiled and executed.
External platform, complete DemuxPacket layout and packet allocator are host
shims. No actual Kodi worker, no libdovi FEL decode, and no device.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import tempfile

from TestGazelleKodiQueueObjectLink import FAKES, QUEUE, POLICY
from TestGazelleKodiQueueRealMessageHeaders import packet_message_methods

BRIDGE_TEST = r"""
#include "DVDMessageQueue.h"
#include "cores/VideoPlayer/Interface/DemuxPacket.h"
#include "GazelleFELPrecreateKodiBridge.h"
#include "GazelleFELProducerEpoch.h"

#include <cassert>
#include <cstdio>
#include <memory>
#include <utility>

using Ingress = GazelleFELPrecreate::ProducerEpoch<CDVDMsgDemuxerPacket,
                                                    CDVDMessageQueue>;
using Bridge = GazelleFELPrecreateKodi::Gate;
using GazelleFELPrecreateKodi::ObserveOriginal;
using Disposition = GazelleFELPrecreate::Disposition;
static unsigned char mediaPlaceholder[] = {0x02};
static std::shared_ptr<CDVDMsgDemuxerPacket>
Original(int id, bool el, unsigned* freed, bool protectedMedia=false, bool drop=false) {
  auto* packet = new DemuxPacket;
  packet->iSize = 20;
  packet->dts = 1000000;
  packet->pts = 1100000;
  packet->iStreamId = id;
  packet->demuxerId = 77;
  packet->isDualStream = true;
  packet->isELPackage = el;
  packet->cryptoInfo = protectedMedia ? packet : nullptr;
  packet->pData = mediaPlaceholder;
  packet->destroyed = freed;
  return std::make_shared<CDVDMsgDemuxerPacket>(packet, drop);
}
static std::shared_ptr<CDVDMsgDemuxerPacket>
NextPacket(CDVDMessageQueue& queue) {
  std::shared_ptr<CDVDMsg> next;
  int priority=0;
  assert(queue.Get(next, std::chrono::milliseconds(0), priority)==MSGQ_OK);
  assert(next->IsType(CDVDMsg::DEMUXER_PACKET) && priority==0);
  return std::static_pointer_cast<CDVDMsgDemuxerPacket>(std::move(next));
}
int main() {
  // PRIORITY FLUSH CAN OVERTAKE OLD BL IN ACTUAL UNMODIFIED KODI QUEUE,
  // but actual Kodi-typed BorrowInfo reads the original PRODUCER STAMP.
  {
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-typed");
    queue.Init(); queue.SetMaxDataSize(10000);
    Ingress ingress(queue);
    Bridge gate(DVD_NOPTS_VALUE,1);
    auto old=Original(11,false,&freed);
    const auto* oldIdentity=old.get();
    assert(ingress.PutOriginal(old));
    old.reset();
    assert(ingress.PutBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    }));
    auto freshBl=Original(11,false,&freed);
    auto freshEl=Original(12,true,&freed);
    const auto* firstIdentity=freshBl.get();
    const auto* secondIdentity=freshEl.get();
    assert(ingress.PutOriginal(freshBl) && ingress.PutOriginal(freshEl));
    freshBl.reset(); freshEl.reset();
    std::shared_ptr<CDVDMsg> flush;
    int priority=0;
    assert(queue.Get(flush,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(flush->IsType(CDVDMsg::GENERAL_FLUSH) && priority==1);
    flush.reset();
    assert(gate.AdvanceEpoch(2));
    auto stale=NextPacket(queue);
    assert(stale.get()==oldIdentity);
    assert(stale->GetGazelleResearchEpoch()==1);
    auto dropped=ObserveOriginal(gate,std::move(stale),false);
    assert(dropped.disposition==Disposition::StaleDropped);
    dropped={};
    assert(freed==1 && !gate.HasPending());
    auto bl=NextPacket(queue);
    assert(bl.get()==firstIdentity && bl->GetGazelleResearchEpoch()==2);
    auto held=ObserveOriginal(gate,std::move(bl),false);
    assert(held.disposition==Disposition::Held && gate.HasPending());
    auto el=NextPacket(queue);
    assert(el.get()==secondIdentity && el->GetGazelleResearchEpoch()==2);
    auto pair=ObserveOriginal(gate,std::move(el),false);
    assert(pair.disposition==Disposition::PairMetadataOnly &&
           pair.first.get()==firstIdentity && pair.second.get()==secondIdentity);
    assert(!gate.HasPending());
    pair={};
    assert(freed==3 && queue.GetDataSize()==0);
    queue.End();
  }

  // UNTAGGED stock owner cannot borrow the current worker's epoch.
  // It must return any pending original first and itself second for stock,
  // while preserving their PTS/DTS, raw identity and exactly-once lifetime.
  {
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-untagged");
    queue.Init(); queue.SetMaxDataSize(10000);
    Ingress ingress(queue);
    Bridge gate(DVD_NOPTS_VALUE,1);
    auto candidate=Original(30,false,&freed);
    auto* originalFirst=candidate.get();
    assert(ingress.PutOriginal(candidate));
    candidate.reset();
    auto bl=NextPacket(queue);
    auto retained=ObserveOriginal(gate,std::move(bl),false);
    assert(retained.disposition==Disposition::Held);
    auto stock=Original(31,true,&freed);  // original normal Kodi, tag 0
    auto* originalSecond=stock.get();
    assert(stock->GetGazelleResearchEpoch()==0);
    assert(queue.Put(stock,0)==MSGQ_OK);
    stock.reset();
    auto out=ObserveOriginal(gate,NextPacket(queue),false);
    assert(out.disposition==Disposition::StockFallback);
    assert(out.first.get()==originalFirst && out.second.get()==originalSecond);
    assert(!gate.HasPending() && freed==0);
    out={};
    assert(freed==2);
    queue.End();
  }

  // A protected original packet is returned as STOCK fallback, never held.
  // The real Kodi packet drop bit vetoes the same path.
  {
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-protected");
    queue.Init(); queue.SetMaxDataSize(10000);
    Ingress ingress(queue);
    Bridge gate(DVD_NOPTS_VALUE,1);
    auto protectedOriginal=Original(40,false,&freed,true,false);
    assert(ingress.PutOriginal(protectedOriginal));
    protectedOriginal.reset();
    auto result=ObserveOriginal(gate,NextPacket(queue),false);
    assert(result.disposition==Disposition::StockFallback &&
           !result.first && result.second && !gate.HasPending());
    result={};
    assert(freed==1);
    auto dropOriginal=Original(41,false,&freed,false,true);
    assert(ingress.PutOriginal(dropOriginal));
    dropOriginal.reset();
    auto dropped=ObserveOriginal(gate,NextPacket(queue),false);
    assert(dropped.disposition==Disposition::StockFallback && dropped.second);
    dropped={};
    assert(freed==2);
    queue.End();
  }

  // In a real queue, a timed-out one-original hold leaves the queue's data
  // accounting at zero because its Get already subtracted the payload.
  // Re-adding through PutBack would increase byte count AGAIN and jump order.
  // Therefore a future worker must feed TakeForStock directly to stock once,
  // without modifying/duplicating the queue-owned original message.
  {
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-timeout");
    queue.Init(); queue.SetMaxDataSize(10000);
    Ingress ingress(queue);
    Bridge gate(DVD_NOPTS_VALUE,1);
    auto original=Original(50,false,&freed);
    assert(ingress.PutOriginal(original));
    original.reset();
    assert(queue.GetDataSize()==20);
    auto held=ObserveOriginal(gate,NextPacket(queue),false);
    assert(held.disposition==Disposition::Held && queue.GetDataSize()==0);
    auto forStock=gate.TakeForStock(1);
    assert(forStock && forStock->GetPacket()->iStreamId==50);
    assert(!gate.TakeForStock(1));
    forStock.reset();
    assert(freed==1 && queue.GetDataSize()==0);
    queue.End();
  }

  std::puts("GAZELLE_KODI_TYPED_BRIDGE_LINK_HOST_PASS "
            "original_kodi_queue_and_messages=true "
            "borrow_epoch_from_original=true priority_flush_overtake=true "
            "stale_bl_released=true pair_original_owners=true "
            "untagged_returns_held_and_incoming_stock=true "
            "protection_drop_veto=true direct_stock_once=true "
            "queue_accounting_preserved=true external_platform_demux_shims=true "
            "no_real_worker=true no_device=true fel_switch_off=true");
}
"""

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ubsan",action="store_true")
    opt=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="gazelle-kodi-typed-bridge-") as td:
        dest=pathlib.Path(td)
        for filename in ("DVDMessageQueue.cpp","DVDMessageQueue.h","DVDMessage.h"):
            source=QUEUE / filename
            output=dest / filename
            shutil.copyfile(source,output)
            assert hashlib.sha256(source.read_bytes()).digest()== \
                   hashlib.sha256(output.read_bytes()).digest()
        # The REAL bridge spells this include using Kodi's repo-root path.
        # Publish the very same unchanged message header at that path.
        real_message_header=QUEUE/"DVDMessage.h"
        bridge_message_header=dest/"cores/VideoPlayer/DVDMessage.h"
        bridge_message_header.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(real_message_header,bridge_message_header)
        assert hashlib.sha256(real_message_header.read_bytes()).digest()== \
               hashlib.sha256(bridge_message_header.read_bytes()).digest()
        for name,code in FAKES.items():
            if name == "DVDMessage.h":
                continue
            if name == "cores/VideoPlayer/Interface/DemuxPacket.h":
                code=r"""
#pragma once
#include "cores/VideoPlayer/Interface/TimingConstants.h"
#include <cstdint>
struct DemuxPacket {
  int iSize{0};
  double dts{DVD_NOPTS_VALUE};
  double pts{DVD_NOPTS_VALUE};
  int iStreamId{-1};
  int demuxerId{-1};
  bool isDualStream{false};
  bool isELPackage{false};
  void* cryptoInfo{nullptr};
  std::uint8_t* pData{nullptr};
  unsigned* destroyed{nullptr};
};
"""
            path=dest/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(code,encoding="utf8")
        fakes={
            "FileItem.h":'#pragma once\n#include <chrono>\n#include <memory>\nstruct CFileItem {};\n',
            "cores/IPlayer.h":'#pragma once\nstruct CPlayerOptions {};\n',
            "DVDDemuxers/DVDDemuxUtils.h":r"""
#pragma once
#include "cores/VideoPlayer/Interface/DemuxPacket.h"
struct CDVDDemuxUtils {
  static void FreeDemuxPacket(DemuxPacket* packet) {
    if (packet && packet->destroyed) ++*packet->destroyed;
    delete packet;
  }
};
""",
        }
        for name,code in fakes.items():
            path=dest/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(code,encoding="utf8")
        policy_source=QUEUE/"GazelleDeferredOpenPolicy.h"
        policy_output=dest/"cores/VideoPlayer/GazelleDeferredOpenPolicy.h"
        policy_output.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(policy_source,policy_output)
        assert hashlib.sha256(policy_source.read_bytes()).digest()== \
               hashlib.sha256(policy_output.read_bytes()).digest()
        shim = (r"""
#include "DVDMessage.h"
#include "cores/VideoPlayer/Interface/DemuxPacket.h"
#include "DVDDemuxers/DVDDemuxUtils.h"
""" + packet_message_methods() + r"""
CDVDMsgGeneralSynchronize::CDVDMsgGeneralSynchronize(
    std::chrono::milliseconds,unsigned)
    : CDVDMsg(GENERAL_SYNCHRONIZE),m_p(nullptr) {}
CDVDMsgGeneralSynchronize::~CDVDMsgGeneralSynchronize()=default;
bool CDVDMsgGeneralSynchronize::Wait(std::chrono::milliseconds,unsigned) {return true;}
void CDVDMsgGeneralSynchronize::Wait(std::atomic<bool>&,unsigned) {}
""")
        (dest/"packet_methods.cpp").write_text(shim,encoding="utf8")
        (dest/"typed_bridge_tests.cpp").write_text(BRIDGE_TEST,encoding="utf8")
        cmd=["c++","-std=c++17","-O1" if opt.ubsan else "-O2",
             "-Wall","-Wextra","-Werror","-pedantic","-pthread"]
        if opt.ubsan:
            cmd+=["-g","-fsanitize=undefined","-fno-sanitize-recover=all"]
        cmd+=["-I",str(dest),"-I",str(POLICY.parent),
              str(dest/"DVDMessageQueue.cpp"),
              str(dest/"packet_methods.cpp"),
              str(dest/"typed_bridge_tests.cpp"),
              "-o",str(dest/"linked_typed_bridge")]
        subprocess.run(cmd,check=True,timeout=45)
        subprocess.run([str(dest/"linked_typed_bridge")],check=True,timeout=20)

if __name__=="__main__":
    main()
