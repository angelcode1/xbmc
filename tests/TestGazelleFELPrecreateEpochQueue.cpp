// SPDX-License-Identifier: GPL-2.0-or-later
// OFFLINE stand-in, not actual Kodi playback. Tests priority control overtaking
// queued original messages, producer-stamped epochs, and owner destruction.
#include "../xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELPrecreateEpochQueue.h"

#include <atomic>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
#include <memory>
#include <thread>
#include <vector>

namespace
{
struct Message
{
  Message(int identity, std::atomic<int>& freed) : id(identity), deaths(freed) {}
  ~Message() { deaths.fetch_add(1, std::memory_order_relaxed); }
  int id;
  std::atomic<int>& deaths;
};
using Queue = GazelleFELPrecreate::EpochIngressModel<Message>;
using Worker = GazelleFELPrecreate::EpochWorkerModel<Message>;
using Type = GazelleFELPrecreate::EpochEventType;
using Outcome = GazelleFELPrecreate::WorkerOutcome;
using Info = GazelleFELPrecreate::LayerInfo;
constexpr double kInvalid = -4503599627370496.0;

std::shared_ptr<Message> Original(int id, std::atomic<int>& freed)
{
  return std::make_shared<Message>(id, freed);
}
Info Layer(bool el)
{
  Info info{};
  info.demuxerId = 5;
  info.streamId = el ? 12 : 11;
  info.isDualStream = true;
  info.isEL = el;
  info.protectedContent = false;
  info.dropRequested = false;
  info.bytes = 1024;
  info.dts = 1500000;
  info.pts = 1600000;
  return info;
}
} // namespace

int main()
{
  // This reproduces Kodi's *priority control can overtake ordinary packets*
  // ordering, NOT Kodi's concrete CDVDMessageQueue itself. Old packet must
  // not be mislabeled with the current (post-flush) worker epoch.
  {
    std::atomic<int> freed{0};
    Queue ingress;
    Worker worker(kInvalid);
    assert(ingress.Enqueue(Original(1, freed))); // old BL, producer epoch 1
    assert(ingress.Control(Type::FlushBarrier));  // epoch 2 priority control
    assert(ingress.Enqueue(Original(2, freed))); // new BL, producer epoch 2
    assert(ingress.Enqueue(Original(3, freed))); // new EL, producer epoch 2

    auto barrier = ingress.Pop();
    assert(barrier && barrier->type == Type::FlushBarrier && barrier->epoch == 2);
    assert(worker.Accept(std::move(*barrier)).outcome == Outcome::BarrierApplied);
    auto oldPacket = ingress.Pop();
    assert(oldPacket && oldPacket->epoch == 1 && oldPacket->original->id == 1);
    assert(worker.Accept(std::move(*oldPacket), Layer(false)).outcome == Outcome::StaleDropped);
    assert(freed == 1 && !worker.HasPending());

    auto newBl = ingress.Pop();
    assert(newBl && newBl->epoch == 2);
    assert(worker.Accept(std::move(*newBl), Layer(false)).outcome == Outcome::Held);
    auto newEl = ingress.Pop();
    auto pair = worker.Accept(std::move(*newEl), Layer(true));
    assert(pair.outcome == Outcome::MetadataPairOnly);
    assert(pair.first->id == 2 && pair.second->id == 3);
    assert(freed == 1);
    pair = {};
    assert(freed == 3);
    assert(!ingress.Pop());
  }

  // A priority reset must revoke an already-dequeued pending original. It
  // cannot rescue the old opposite layer with a coincidentally equal DTS.
  {
    std::atomic<int> freed{0};
    Queue ingress;
    Worker worker(kInvalid);
    assert(ingress.Enqueue(Original(4, freed)));
    auto bl = ingress.Pop();
    assert(worker.Accept(std::move(*bl), Layer(false)).outcome == Outcome::Held);
    assert(ingress.Enqueue(Original(5, freed))); // EL queued before reset
    assert(ingress.Control(Type::ResetBarrier));
    auto control = ingress.Pop();
    assert(worker.Accept(std::move(*control)).outcome == Outcome::BarrierApplied);
    assert(freed == 1 && !worker.HasPending());
    auto lateEl = ingress.Pop();
    assert(worker.Accept(std::move(*lateEl), Layer(true)).outcome == Outcome::StaleDropped);
    assert(freed == 2);
    // A stale/duplicate barrier must not rewrite the worker's epoch.
    auto duplicate = GazelleFELPrecreate::EpochEvent<Message>{Type::ResetBarrier, 2, {}};
    assert(worker.Accept(std::move(duplicate)).outcome == Outcome::ControlRefused);
    assert(worker.Epoch() == 2);
  }

  // Explicitly fail closed if a future-tagged packet bypasses its priority
  // barrier: never silently stamp from the worker's current epoch.
  {
    std::atomic<int> freed{0};
    Worker worker(kInvalid);
    auto forged = GazelleFELPrecreate::EpochEvent<Message>{
        Type::Packet, 3, Original(6, freed)};
    assert(worker.Accept(std::move(forged), Layer(false)).outcome == Outcome::FutureDropped);
    assert(freed == 1 && !worker.HasPending());
  }

  // Current-epoch single owner can leave for stock exactly once; no copy or
  // replay of the same shared message. This is only a host-model handoff.
  {
    std::atomic<int> freed{0};
    Queue ingress;
    Worker worker(kInvalid);
    assert(ingress.Enqueue(Original(7, freed)));
    auto msg = ingress.Pop();
    assert(worker.Accept(std::move(*msg), Layer(false)).outcome == Outcome::Held);
    auto owner = worker.TakeForStock(1);
    assert(owner && owner->id == 7 && !worker.TakeForStock(1));
    owner.reset();
    assert(freed == 1);
  }

  // Kodi's FlushMessages may remove queued normal packets even if some were
  // enqueued just after the flush barrier. Purge never delivers a stale owner.
  {
    std::atomic<int> freed{0};
    Queue ingress;
    Worker worker(kInvalid);
    assert(ingress.Enqueue(Original(8, freed)));
    assert(ingress.Control(Type::FlushBarrier));
    assert(ingress.Enqueue(Original(9, freed)));
    auto barrier = ingress.Pop();
    assert(worker.Accept(std::move(*barrier)).outcome == Outcome::BarrierApplied);
    ingress.PurgePackets();
    assert(freed == 2 && !ingress.Pop());
  }

  // No wrap from UINT64_MAX to zero. No enqueue after Close. All outstanding
  // original owners are freed without a second callback or queue dispatch.
  {
    std::atomic<int> freed{0};
    Queue overflow(std::numeric_limits<std::uint64_t>::max());
    assert(!overflow.Control(Type::FlushBarrier));
    assert(overflow.ProducerEpoch() == std::numeric_limits<std::uint64_t>::max());
    assert(overflow.Enqueue(Original(10, freed)));
    assert(!overflow.Control(Type::Packet));
    overflow.Close();
    overflow.Close();
    assert(freed == 1);
    assert(!overflow.Enqueue(Original(11, freed)));
    assert(freed == 2);
  }

  // Producer sends and seek barriers may interleave on different threads.
  // Single ingress lock must assign monotonically nondecreasing stamps
  // in producer FIFO order regardless of scheduling; the priority worker
  // then drops all old epochs without retaining owners after Close.
  {
    constexpr int kWorkers = 3;
    constexpr int kEach = 60;
    constexpr int kBarriers = 18;
    std::atomic<int> freed{0};
    std::atomic<int> sequence{0};
    Queue ingress;
    std::vector<std::thread> threads;
    for (int worker = 0; worker < kWorkers; ++worker)
    {
      threads.emplace_back([&, worker]() {
        for (int i = 0; i < kEach; ++i)
        {
          const int id = sequence.fetch_add(1);
          assert(ingress.Enqueue(Original(worker * kEach + id + 100, freed)));
        }
      });
    }
    threads.emplace_back([&]() {
      for (int i = 0; i < kBarriers; ++i)
        assert(ingress.Control(Type::FlushBarrier));
    });
    for (auto& thread : threads)
      thread.join();
    assert(ingress.ProducerEpoch() == 1 + kBarriers);

    Worker consumer(kInvalid);
    std::uint64_t lastPacketEpoch = 0;
    int seenPackets = 0;
    int seenControls = 0;
    while (auto next = ingress.Pop())
    {
      if (next->type != Type::Packet)
      {
        ++seenControls;
        assert(consumer.Accept(std::move(*next)).outcome == Outcome::BarrierApplied);
      }
      else
      {
        assert(next->epoch >= lastPacketEpoch);
        lastPacketEpoch = next->epoch;
        ++seenPackets;
        const auto outcome = consumer.Accept(std::move(*next), Layer(false)).outcome;
        assert(outcome == Outcome::StaleDropped || outcome == Outcome::Held ||
               outcome == Outcome::StockFallback);
      }
    }
    assert(seenControls == kBarriers && seenPackets == kWorkers * kEach);
    consumer.Close();
    ingress.Close();
    assert(freed == kWorkers * kEach);
  }

  std::cout << "GAZELLE_PRECREATE_EPOCH_MODEL_PASS "
               "priority_flush_overtake=true producer_stamps=true "
               "seek_revoke=true stale_no_replay=true future_rejected=true "
               "stock_once=true purge_safe=true concurrent_producers=3 "
               "epoch_wrap_refused=true no_real_kodi_queue=true "
               "no_device=true codec_selection=disabled\n";
}
