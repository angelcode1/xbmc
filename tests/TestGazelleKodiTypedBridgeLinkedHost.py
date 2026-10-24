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
#include "GazelleFELPrecreateAdmission.h"
#include "GazelleFELAwaitBarrierOwners.h"
#include "GazelleFELPrecreateSeekFence.h"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <thread>

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

  // CRITICAL: Kodi's actual ProcessDecoderOutput() VC_FLUSHED/VC_REOPEN
  // paths SendMessage(msg, 10). Priority 10 beats priority-1 GENERAL_FLUSH,
  // including when the flush was already queued. A worker whose epoch is
  // advanced ONLY on dequeuing that flush could wrongly admit an old packet
  // first. The test demonstrates this ordering HAZARD; it does not claim
  // that the current unwired owner gate handles it.
  {
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-priority-10-hazard");
    queue.Init(); queue.SetMaxDataSize(10000);
    Ingress ingress(queue);
    auto old=Original(60,false,&freed);
    auto* oldId=old.get();
    assert(ingress.PutOriginal(old) && old->GetGazelleResearchEpoch()==1);
    old.reset();
    auto dequeued=NextPacket(queue); // normal input leaves accounting zero
    assert(dequeued.get()==oldId && queue.GetDataSize()==0);
    // Existing Kodi worker has now obtained this original message and may
    // requeue it through the decoder-output retry path.
    assert(ingress.PutBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    }));
    assert(ingress.ProducerEpochForAuditOnly()==2);
    assert(queue.Put(dequeued,10)==MSGQ_OK);
    dequeued.reset();
    std::shared_ptr<CDVDMsg> next;
    int priority=0;
    assert(queue.Get(next,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==10 && next.get()==oldId);
    auto oldAgain=std::static_pointer_cast<CDVDMsgDemuxerPacket>(next);
    assert(oldAgain->GetGazelleResearchEpoch()==1);
    // A producer-published seek watermark must win even if the worker has
    // not processed the priority-1 flush. THIS IS NOT WIRED TO LIVE KODI.
    assert(GazelleFELPrecreate::ClassifyEpoch(
        oldAgain->GetGazelleResearchEpoch(),
        ingress.ProducerEpochForAuditOnly(), 1) ==
        GazelleFELPrecreate::Admission::StaleReject);
    assert(!GazelleFELPrecreate::MayDirectStockReplay(
        oldAgain->GetGazelleResearchEpoch(),
        ingress.ProducerEpochForAuditOnly(), 1));
    assert(GazelleFELPrecreate::ClassifyEpoch(2,2,1) ==
           GazelleFELPrecreate::Admission::AwaitBarrier);
    // Producer knows epoch 2 already, but worker's PairOwners would still
    // be at epoch 1 until the priority-1 control was processed. DO NOT pair.
    next.reset();
    assert(freed==0); // oldAgain still holds the original owner
    oldAgain.reset();
    assert(freed==1); // same original freed once; no fabricated raw owner
    priority=0; // Kodi Get uses priority as minimum requested priority
    assert(queue.Get(next,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==1 && next->IsType(CDVDMsg::GENERAL_FLUSH));
    next.reset();
    assert(GazelleFELPrecreate::ClassifyEpoch(2,2,2) ==
           GazelleFELPrecreate::Admission::MetadataOnly);
    assert(GazelleFELPrecreate::MayDirectStockReplay(2,2,2));
    assert(freed==1);
    assert(queue.GetDataSize()==0); // priority-10 retry is not ordinary bytes
    queue.End();
    assert(freed==1);
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

  // AwaitBarrier holding integrated with actual Kodi-linked queue and typed
  // ORIGINAL packet owners. A synthetic high-priority new-epoch delivery is
  // injected to exercise the inversion; real producer/worker ingress remains
  // UNWIRED and caller backpressure is NOT implemented in live Kodi.
  {
    using Hold = GazelleFELPrecreate::AwaitBarrierOwners<CDVDMsgDemuxerPacket>;
    using HoldCode = GazelleFELPrecreate::AwaitHoldResult;
    using HoldState = GazelleFELPrecreate::AwaitState;
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-await-barrier");
    queue.Init(); queue.SetMaxDataSize(10000);
    Ingress sender(queue);
    Hold hold(50);
    assert(sender.PutBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    }));
    assert(sender.ProducerEpochForAuditOnly()==2);
    // Synthetic queue injection at priority 10 to force delivery before the
    // priority-1 flush. No real Kodi producer path generates such an initial
    // high-priority message; safety gate must still refuse early stock feed.
    for (int id=70; id<73; ++id) {
      auto original=Original(id, id==71, &freed);
      assert(original->TrySetGazelleResearchEpoch(2));
      assert(queue.Put(original,10)==MSGQ_OK);
      original.reset();
    }
    std::shared_ptr<CDVDMsgDemuxerPacket> thirdCallerRetains;
    for (int i=0;i<3;++i) {
      std::shared_ptr<CDVDMsg> next;
      int priority=0;
      assert(queue.Get(next,std::chrono::milliseconds(0),priority)==MSGQ_OK);
      assert(priority==10);
      auto original=std::static_pointer_cast<CDVDMsgDemuxerPacket>(std::move(next));
      assert(GazelleFELPrecreate::ClassifyEpoch(
          original->GetGazelleResearchEpoch(),2,1)==
          GazelleFELPrecreate::Admission::AwaitBarrier);
      const auto result=hold.TryHold(original,2,2,1,
                                     static_cast<std::size_t>(original->GetPacket()->iSize),
                                     static_cast<std::uint64_t>(i));
      if (i<2) {
        assert(result==HoldCode::HeldOriginal && !original);
      } else {
        assert(result==HoldCode::CallerMustRetain && original);
        thirdCallerRetains=std::move(original);
      }
    }
    assert(hold.Size()==2 && hold.Bytes()==40 && freed==0);
    assert(hold.Inspect(2,1,60)==HoldState::DeadlineNeedsControlRecovery);
    assert(hold.TakeAfterBarrier(2,1,60).count==0);
    assert(hold.Size()==2 && freed==0);
    std::shared_ptr<CDVDMsg> flush;
    int priority=0;
    assert(queue.Get(flush,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==1 && flush->IsType(CDVDMsg::GENERAL_FLUSH));
    flush.reset();
    auto ready=hold.TakeAfterBarrier(2,2,60);
    assert(ready.count==2 && ready.original[0]->GetPacket()->iStreamId==70 &&
           ready.original[1]->GetPacket()->iStreamId==71);
    assert(!hold.Size() && thirdCallerRetains->GetPacket()->iStreamId==72);
    ready.original[0].reset();
    ready.original[1].reset();
    assert(freed==2);
    thirdCallerRetains.reset(); // caller, not hold, still owned overflow
    assert(freed==3 && queue.GetDataSize()==0);
    queue.End();
  }

  // Source-linked unchanged Kodi queue + actual packet message types:
  // one producer/worker fence serializes packet stamping, seek publication,
  // worker applied-barrier reports, and immediate synthetic commit.
  {
    using Fence = GazelleFELPrecreate::SeekFence<CDVDMsgDemuxerPacket,
                                                  CDVDMessageQueue>;
    using Decision = GazelleFELPrecreate::FenceDecision;
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-serialized-epoch-fence");
    queue.Init(); queue.SetMaxDataSize(10000);
    Fence fence(queue, 50);
    auto old = Original(80,false,&freed);
    assert(fence.EnqueueOriginal(old)==Decision::Submitted);
    old.reset();
    assert(fence.PublishBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    },10)==Decision::Submitted);
    assert(fence.PublishedForAuditOnly()==2 &&
           fence.AppliedForAuditOnly()==1);
    auto fresh = Original(81,false,&freed);
    assert(fence.EnqueueOriginal(fresh)==Decision::Submitted);
    fresh.reset();
    std::shared_ptr<CDVDMsg> flush;
    int priority=0;
    assert(queue.Get(flush,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(flush->IsType(CDVDMsg::GENERAL_FLUSH) && priority==1);
    flush.reset();
    auto stale=NextPacket(queue);
    assert(stale->GetGazelleResearchEpoch()==1);
    assert(fence.HoldOrRefuse(stale,20,11)==Decision::StaleDropped);
    assert(!stale && freed==1);
    auto epochTwo=NextPacket(queue);
    assert(epochTwo->GetGazelleResearchEpoch()==2);
    assert(fence.HoldOrRefuse(epochTwo,20,12)==Decision::AwaitHeld);
    assert(!epochTwo && fence.PendingForAuditOnly()==1 && freed==1);
    assert(fence.CommitReady(13,[](const auto&,std::size_t) noexcept -> bool {
      return true; // must not be invoked before applied barrier
    })==0);
    // "BarrierApplied" must follow actual worker flush. This synthetic
    // harness models that action; it does NOT run VideoPlayerVideo::Flush.
    assert(fence.BarrierApplied(2,14)==Decision::Applied);
    assert(fence.CommitReady(15,[](const auto&,std::size_t) noexcept -> bool {
      return false; // simulated downstream refusal; zero originals lost
    })==0);
    assert(fence.PendingForAuditOnly()==1 && freed==1);
    std::shared_ptr<CDVDMsgDemuxerPacket> acceptedOriginal;
    assert(fence.CommitReady(16,[&](const auto& msgs,std::size_t count) noexcept -> bool {
      assert(count==1 && msgs[0] && msgs[0]->GetPacket()->iStreamId==81);
      acceptedOriginal=msgs[0]; // retain original shared owner, no data copy
      return true;
    })==1);
    assert(fence.PendingForAuditOnly()==0 && freed==1);
    acceptedOriginal.reset();
    assert(freed==2);
    fence.Close(); fence.Close();
    queue.End();
  }
  // Failed synthetic stock handoff retains caller owner; successful callback
  // commits once under the same lock as publication. Demonstrate linearizable
  // ordering under a deterministic producer/worker concurrency interleave.
  {
    using Fence = GazelleFELPrecreate::SeekFence<CDVDMsgDemuxerPacket,
                                                  CDVDMessageQueue>;
    using Decision = GazelleFELPrecreate::FenceDecision;
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-fence-concurrent");
    queue.Init(); queue.SetMaxDataSize(10000);
    Fence fence(queue, 50);
    auto caller=Original(90,false,&freed);
    assert(fence.EnqueueOriginal(caller)==Decision::Submitted);
    caller.reset();
    auto original=NextPacket(queue);
    assert(fence.CommitOriginal(original,[](const auto&) noexcept -> bool {
      return false;
    })==Decision::Backpressure);
    assert(original && freed==0);

    std::mutex signalMutex;
    std::condition_variable signal;
    bool entered=false, allowCommit=false, producerStarted=false;
    std::atomic<bool> publishReturned{false};
    std::atomic<bool> commitSucceeded{false};
    std::thread worker([&] {
      const auto result=fence.CommitOriginal(original,[&](const auto& msg) noexcept -> bool {
        assert(msg && msg->GetPacket()->iStreamId==90);
        {
          std::lock_guard<std::mutex> guard(signalMutex);
          entered=true;
        }
        signal.notify_all();
        {
          std::unique_lock<std::mutex> lock(signalMutex);
          signal.wait(lock,[&]{return allowCommit;});
        }
        return true;
      });
      commitSucceeded.store(result==Decision::Committed);
    });
    {
      std::unique_lock<std::mutex> guard(signalMutex);
      assert(signal.wait_for(guard,std::chrono::seconds(5),[&]{return entered;}));
    }
    std::thread producer([&] {
      {
        std::lock_guard<std::mutex> guard(signalMutex);
        producerStarted=true;
      }
      signal.notify_all();
      const auto outcome=fence.PublishBarrier([](std::uint64_t) {
        return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
      },100);
      assert(outcome==Decision::Submitted);
      publishReturned.store(true);
    });
    {
      std::unique_lock<std::mutex> guard(signalMutex);
      assert(signal.wait_for(guard,std::chrono::seconds(5),[&]{return producerStarted;}));
      // Producer publication cannot cross a callback holding the fence.
      assert(!publishReturned.load());
      allowCommit=true;
    }
    signal.notify_all();
    worker.join(); producer.join();
    assert(commitSucceeded.load() && publishReturned.load() &&
           fence.PublishedForAuditOnly()==2 && freed==1 && !original);
    // Control still pending in unchanged Kodi queue, not worker-applied.
    assert(fence.AppliedForAuditOnly()==1);
    std::shared_ptr<CDVDMsg> flush;
    int priority=0;
    assert(queue.Get(flush,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(flush->IsType(CDVDMsg::GENERAL_FLUSH));
    flush.reset();
    assert(fence.BarrierApplied(2,101)==Decision::Applied);
    fence.Close(); queue.End();
  }

  // Epoch zero is uninitialized and epoch UINT64_MAX cannot wrap: even
  // intentionally malformed control messages cannot reopen a closed fence.
  {
    using Fence = GazelleFELPrecreate::SeekFence<CDVDMsgDemuxerPacket,
                                                  CDVDMessageQueue>;
    using Decision = GazelleFELPrecreate::FenceDecision;
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-epoch-wrap");
    queue.Init(); queue.SetMaxDataSize(10000);
    Fence zero(queue,10,0);
    auto packet=Original(95,false,&freed);
    assert(zero.EnqueueOriginal(packet)==Decision::Refused);
    assert(zero.PublishBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    },0)==Decision::Refused);
    packet.reset();
    assert(freed==1);
    Fence maxed(queue,10,~std::uint64_t{0});
    assert(maxed.PublishBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    },1)==Decision::Refused);
    assert(maxed.BarrierApplied(0,2)==Decision::Refused);
    assert(!queue.GetDataSize());
    zero.Close(); maxed.Close(); queue.End();
  }

  // Retry admitted AFTER seek publication: old original epoch is revoked,
  // not inserted at priority 10 in front of the priority-1 seek flush.
  {
    using Fence = GazelleFELPrecreate::SeekFence<CDVDMsgDemuxerPacket,
                                                  CDVDMessageQueue>;
    using Decision = GazelleFELPrecreate::FenceDecision;
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-retry-gate");
    queue.Init(); queue.SetMaxDataSize(10000);
    Fence fence(queue,50);
    auto old=Original(110,false,&freed);
    auto* oldId=old.get();
    assert(fence.EnqueueOriginal(old)==Decision::Submitted);
    old.reset();
    auto retry=NextPacket(queue);
    assert(retry.get()==oldId && queue.GetDataSize()==0);
    assert(fence.PublishBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    },1)==Decision::Submitted);
    assert(fence.TryEnqueueDecoderRetry(retry)==Decision::StaleDropped);
    assert(!retry && freed==1);
    std::shared_ptr<CDVDMsg> barrier; int priority=0;
    assert(queue.Get(barrier,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==1 && barrier->IsType(CDVDMsg::GENERAL_FLUSH));
    barrier.reset();

    // A newly tagged epoch-2 original may NOT retry ahead of this unapplied
    // barrier. No owner transfer; the caller must exert actual backpressure.
    auto newEpoch=Original(111,false,&freed);
    auto* newId=newEpoch.get();
    assert(newEpoch->TrySetGazelleResearchEpoch(2));
    assert(fence.TryEnqueueDecoderRetry(newEpoch)==Decision::Backpressure);
    assert(newEpoch.get()==newId && freed==1 && !queue.GetDataSize());
    assert(fence.BarrierApplied(2,2)==Decision::Applied);
    assert(fence.TryEnqueueDecoderRetry(newEpoch)==Decision::Submitted);
    assert(!newEpoch);
    std::shared_ptr<CDVDMsg> ready; priority=0;
    assert(queue.Get(ready,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==10 && ready.get()==newId);
    assert(std::static_pointer_cast<CDVDMsgDemuxerPacket>(ready)
               ->GetGazelleResearchEpoch()==2);
    ready.reset();
    assert(freed==2 && !queue.GetDataSize());
    fence.Close(); queue.End();
  }

  // PRIORITY 10 packets that were already enqueued BEFORE a new seek can
  // still overtake its later priority-1 flush. Ingress validation alone
  // cannot solve this: worker must revalidate the producer epoch at actual
  // consumption, before any blocking decoder input. Remains live NO-GO.
  {
    using Fence = GazelleFELPrecreate::SeekFence<CDVDMsgDemuxerPacket,
                                                  CDVDMessageQueue>;
    using Decision = GazelleFELPrecreate::FenceDecision;
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-existing-retry");
    queue.Init(); queue.SetMaxDataSize(10000);
    Fence fence(queue,50);
    auto original=Original(112,false,&freed);
    assert(fence.EnqueueOriginal(original)==Decision::Submitted);
    original.reset();
    auto retried=NextPacket(queue);
    assert(fence.TryEnqueueDecoderRetry(retried)==Decision::Submitted);
    assert(!retried);
    assert(fence.PublishBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    },3)==Decision::Submitted);
    std::shared_ptr<CDVDMsg> popped;int priority=0;
    assert(queue.Get(popped,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==10 && popped->IsType(CDVDMsg::DEMUXER_PACKET));
    auto oldAgain=std::static_pointer_cast<CDVDMsgDemuxerPacket>(popped);
    assert(GazelleFELPrecreate::ClassifyEpoch(
        oldAgain->GetGazelleResearchEpoch(),
        fence.PublishedForAuditOnly(),fence.AppliedForAuditOnly())==
        GazelleFELPrecreate::Admission::StaleReject);
    oldAgain.reset(); popped.reset();
    assert(freed==1);
    priority=0;
    assert(queue.Get(popped,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==1 && popped->IsType(CDVDMsg::GENERAL_FLUSH));
    popped.reset();
    assert(fence.BarrierApplied(2,4)==Decision::Applied);
    fence.Close(); queue.End();
  }

  // A finite synthetic burst of stale originals offered for priority-10
  // retry AFTER seek publication cannot keep the queued priority-1 control
  // from being the next message. This proves only cooperative callers;
  // already enqueued old priority-10 messages can still starve the control.
  {
    using Fence = GazelleFELPrecreate::SeekFence<CDVDMsgDemuxerPacket,
                                                  CDVDMessageQueue>;
    using Decision = GazelleFELPrecreate::FenceDecision;
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-postseek-retry-flood");
    queue.Init(); queue.SetMaxDataSize(10000);
    Fence fence(queue,50);
    assert(fence.PublishBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    },1)==Decision::Submitted);
    constexpr int burst=64;
    for (int i=0; i<burst; ++i) {
      // Model already held/in-flight packet-message owners from epoch 1.
      auto original=Original(200+i,false,&freed);
      assert(original->TrySetGazelleResearchEpoch(1));
      assert(fence.TryEnqueueDecoderRetry(original)==Decision::StaleDropped);
      assert(!original && freed==static_cast<unsigned>(i+1));
    }
    std::shared_ptr<CDVDMsg> flush;
    int priority=0;
    assert(queue.Get(flush,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==1 && flush->IsType(CDVDMsg::GENERAL_FLUSH));
    flush.reset();
    assert(fence.BarrierApplied(2,2)==Decision::Applied);
    assert(freed==burst && queue.GetDataSize()==0);
    fence.Close(); queue.End();
  }

  // New two-phase lease: a prepared original can be canceled at seek
  // publication before ANY decoder work. The already dequeued Kodi queue
  // packet isn't PutBack'd and its destructor runs exactly once.
  {
    using Fence = GazelleFELPrecreate::SeekFence<CDVDMsgDemuxerPacket,
                                                  CDVDMessageQueue>;
    using Decision = GazelleFELPrecreate::FenceDecision;
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-lease-revocation");
    queue.Init(); queue.SetMaxDataSize(10000);
    Fence fence(queue,50);
    for (int id=300; id<302; ++id) {
      auto original=Original(id,false,&freed);
      assert(fence.EnqueueOriginal(original)==Decision::Submitted);
      original.reset();
      auto queued=NextPacket(queue);
      assert(fence.PrepareOriginalLease(queued,20)==Decision::LeasePrepared);
      assert(!queued);
    }
    assert(fence.PreparedForAuditOnly()==2 && freed==0);
    assert(fence.PublishBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    },1)==Decision::Submitted);
    assert(fence.PreparedForAuditOnly()==0 && freed==2);
    assert(!fence.BeginOriginalLease());
    std::shared_ptr<CDVDMsg> flush; int priority=0;
    assert(queue.Get(flush,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==1 && flush->IsType(CDVDMsg::GENERAL_FLUSH));
    flush.reset();
    assert(fence.BarrierApplied(2,2)==Decision::Applied);
    assert(queue.GetDataSize()==0);
    fence.Close(); queue.End();
  }

  // Deterministic interleaving of external potentially BLOCKING operation
  // versus new seek. Lease.Begin exits fence lock BEFORE worker blocks;
  // publication can proceed and cancel another PREPARED packet immediately,
  // but applied flush must REFUSE while old original is in-flight. No
  // attempt to abort the native operation or steal its shared packet.
  {
    using Fence = GazelleFELPrecreate::SeekFence<CDVDMsgDemuxerPacket,
                                                  CDVDMessageQueue>;
    using Decision = GazelleFELPrecreate::FenceDecision;
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-inflight-decoder-lease");
    queue.Init(); queue.SetMaxDataSize(10000);
    Fence fence(queue,50);
    for (int id=310; id<312; ++id) {
      auto original=Original(id,false,&freed);
      assert(fence.EnqueueOriginal(original)==Decision::Submitted);
      original.reset();
      auto dequeued=NextPacket(queue);
      assert(fence.PrepareOriginalLease(dequeued,20)==Decision::LeasePrepared);
    }
    auto started=fence.BeginOriginalLease();
    assert(started && started.original->GetPacket()->iStreamId==310);
    assert(fence.InFlightForAuditOnly() && fence.PreparedForAuditOnly()==1);
    std::mutex signalMutex;
    std::condition_variable signal;
    bool workerBegan=false, finishExternal=false;
    std::atomic<bool> finished{false};
    std::thread worker([&] {
      {
        std::lock_guard<std::mutex> guard(signalMutex);
        workerBegan=true;
      }
      signal.notify_all();
      {
        std::unique_lock<std::mutex> guard(signalMutex);
        signal.wait(guard,[&] {return finishExternal;});
      }
      // Simulated external native work has completed. Do not hold the
      // producer seek lock across any portion of that blocking wait.
      started.original.reset();
      assert(fence.FinishOriginalLease(started.token));
      finished.store(true);
    });
    {
      std::unique_lock<std::mutex> guard(signalMutex);
      assert(signal.wait_for(guard,std::chrono::seconds(5),
                             [&] {return workerBegan;}));
    }
    assert(fence.PublishBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    },10)==Decision::Submitted);
    // Queued original #311 is revoked, but in-flight #310 is still live.
    assert(fence.PreparedForAuditOnly()==0 && fence.InFlightForAuditOnly());
    assert(freed==1);
    assert(fence.BarrierApplied(2,11)==Decision::Refused);
    std::shared_ptr<CDVDMsg> flush; int priority=0;
    assert(queue.Get(flush,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(flush->IsType(CDVDMsg::GENERAL_FLUSH));
    flush.reset();
    {
      std::lock_guard<std::mutex> guard(signalMutex);
      finishExternal=true;
    }
    signal.notify_all();
    worker.join();
    assert(finished.load() && freed==2 && !fence.InFlightForAuditOnly());
    // Native input-return is NOT enough: neither Kodi Reset() JNI flush nor
    // renderer/output-pool retirement is proved by the packet lease token.
    assert(fence.BarrierApplied(2,12)==Decision::Refused);
    assert(fence.BeginNativeFlushProof(2));
    assert(fence.BarrierApplied(2,12)==Decision::Refused);
    assert(fence.ReportNativeFlush(2,true,true)==
           GazelleFELPrecreate::QuiescenceStep::Recorded);
    assert(fence.BarrierApplied(2,12)==Decision::Refused);
    assert(fence.ReportRetiredOutputs(2,true,true)==
           GazelleFELPrecreate::QuiescenceStep::Recorded);
    assert(fence.BarrierApplied(2,12)==Decision::Applied);
    assert(queue.GetDataSize()==0);
    fence.Close(); queue.End();
  }

  // Even an original priority-10 retry accepted BEFORE publication is
  // rejected at the worker's modeled consumption boundary, rather than
  // forwarded to an unsafe decoder. The unchanged Kodi queue really
  // delivers it before the lower-priority GENERAL_FLUSH.
  {
    using Fence = GazelleFELPrecreate::SeekFence<CDVDMsgDemuxerPacket,
                                                  CDVDMessageQueue>;
    using Decision = GazelleFELPrecreate::FenceDecision;
    unsigned freed=0;
    CDVDMessageQueue queue("gazelle-linked-priority10-consume-fence");
    queue.Init(); queue.SetMaxDataSize(10000);
    Fence fence(queue,50);
    auto first=Original(320,false,&freed);
    assert(fence.EnqueueOriginal(first)==Decision::Submitted);
    first.reset();
    auto originallyDequeued=NextPacket(queue);
    assert(fence.TryEnqueueDecoderRetry(originallyDequeued)==Decision::Submitted);
    assert(!originallyDequeued);
    assert(fence.PublishBarrier([](std::uint64_t) {
      return std::make_shared<CDVDMsg>(CDVDMsg::GENERAL_FLUSH);
    },10)==Decision::Submitted);
    int priority=0;
    std::shared_ptr<CDVDMsg> current;
    assert(queue.Get(current,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==10 && current->IsType(CDVDMsg::DEMUXER_PACKET));
    auto retry=std::static_pointer_cast<CDVDMsgDemuxerPacket>(current);
    current.reset(); // C++17 static_pointer_cast cannot consume base owner
    assert(retry->GetGazelleResearchEpoch()==1);
    assert(fence.PrepareOriginalLease(retry,20)==Decision::StaleDropped);
    assert(!retry && freed==1 && !fence.PreparedForAuditOnly());
    priority=0;
    assert(queue.Get(current,std::chrono::milliseconds(0),priority)==MSGQ_OK);
    assert(priority==1 && current->IsType(CDVDMsg::GENERAL_FLUSH));
    current.reset();
    assert(fence.BarrierApplied(2,11)==Decision::Applied);
    assert(freed==1 && !queue.GetDataSize());
    fence.Close(); queue.End();
  }

  std::puts("GAZELLE_KODI_TYPED_BRIDGE_LINK_HOST_PASS "
            "original_kodi_queue_and_messages=true "
            "borrow_epoch_from_original=true priority_flush_overtake=true "
            "stale_bl_released=true pair_original_owners=true "
            "untagged_returns_held_and_incoming_stock=true "
            "protection_drop_veto=true direct_stock_once=true "
            "queue_accounting_preserved=true retry_priority_10_overtakes_flush_1=true "
            "retry_before_barrier_requires_external_epoch_watermark=true "
            "dual_epoch_admission_rejects_stale_and_premature_new=true "
            "bounded_await_barrier_originals=2 preflush_no_stock=true "
            "overflow_caller_retains=true expired_hold_requires_barrier=true "
            "serialized_epoch_fence_with_real_queue=true "
            "concurrent_commit_precedes_seek_publication=true "
            "rejected_barrier_handoff_retains_original=true "
            "zero_and_wrapped_epoch_refused=true "
            "postseek_retry_admission_blocks_priority10=true "
            "prequeued_retry_still_requires_worker_fence=true "
            "postseek_stale_retry_burst_64_does_not_starve_flush=true "
            "prepared_originals_revoked_on_seek=true "
            "inflight_lease_blocks_barrier_until_finish=true "
            "blocking_external_work_outside_fence_lock=true "
            "prequeued_priority10_retry_rejected_at_consume_fence=true "
            "lease_finish_not_native_quiescence=true "
            "native_jni_flush_and_renderer_witness_required=true "
            "external_platform_demux_shims=true "
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
