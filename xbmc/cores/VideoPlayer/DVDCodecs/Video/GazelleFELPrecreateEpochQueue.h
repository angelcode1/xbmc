// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// OFFLINE MODEL ONLY: Kodi-like priority flush/seek ordering around the
// ORIGINAL shared packet message owner. This is NOT CDVDMessageQueue.
// A real integration must stamp packets AT PRODUCER ENQUEUE under a common
// serialization boundary with seek/flush, not at worker dequeue.
// No production Kodi TU includes this header; no decoder selection.

#include "GazelleFELPrecreateOwners.h"

#include <cstdint>
#include <deque>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <utility>

namespace GazelleFELPrecreate
{
enum class EpochEventType : std::uint8_t
{
  Packet,
  FlushBarrier,
  ResetBarrier
};

template <class Message>
struct EpochEvent
{
  EpochEventType type{EpochEventType::Packet};
  std::uint64_t epoch{0};
  std::shared_ptr<Message> original{};
};

// This is deliberately a small modeled queue, rather than an alternate
// implementation of Kodi's player queue. Its mutex makes the producer
// enqueue/stamp and control-event epoch transition indivisible.
// Kodi's priority queue can process a barrier before earlier normal packets;
// those packets must carry their OLD epoch and fail closed when read later.
template <class Message>
class EpochIngressModel
{
public:
  using Owner = std::shared_ptr<Message>;
  using Event = EpochEvent<Message>;

  explicit EpochIngressModel(std::uint64_t initialEpoch = 1)
    : m_epoch(initialEpoch)
  {
  }

  EpochIngressModel(const EpochIngressModel&) = delete;
  EpochIngressModel& operator=(const EpochIngressModel&) = delete;

  bool Enqueue(Owner original)
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    if (!m_open || !original)
      return false;
    m_normal.push_back({EpochEventType::Packet, m_epoch, std::move(original)});
    return true;
  }

  bool Control(EpochEventType type)
  {
    if (type != EpochEventType::FlushBarrier &&
        type != EpochEventType::ResetBarrier)
      return false;
    std::lock_guard<std::mutex> guard(m_mutex);
    if (!m_open || m_epoch == std::numeric_limits<std::uint64_t>::max())
      return false;
    const auto next = m_epoch + 1u;
    // Preserve epoch if the queue allocation throws: the new producer epoch
    // becomes visible only after its control message was enqueued.
    m_priority.push_back({type, next, {}});
    m_epoch = next;
    return true;
  }

  std::optional<Event> Pop()
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    auto& from = m_priority.empty() ? m_normal : m_priority;
    if (from.empty())
      return std::nullopt;
    auto result = std::move(from.front());
    from.pop_front();
    return result;
  }

  // Kodi's GENERAL_FLUSH handler calls FlushMessages(), which can purge
  // both pre- and post-flush queued ordinary packets. It may discard valid
  // newer data but must never duplicate or replay stale original owners.
  void PurgePackets()
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    m_normal.clear();
  }

  void Close()
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    m_open = false;
    m_priority.clear();
    m_normal.clear();
  }

  std::uint64_t ProducerEpoch() const
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    return m_epoch;
  }

private:
  mutable std::mutex m_mutex;
  std::uint64_t m_epoch;
  bool m_open{true};
  std::deque<Event> m_priority;
  std::deque<Event> m_normal;
};

enum class WorkerOutcome : std::uint8_t
{
  BarrierApplied,
  Held,
  MetadataPairOnly,
  StockFallback,
  StaleDropped,
  FutureDropped,
  InvalidDropped,
  ControlRefused
};

template <class Message>
class EpochWorkerModel
{
public:
  using Event = EpochEvent<Message>;
  using Owner = std::shared_ptr<Message>;
  struct Result
  {
    WorkerOutcome outcome{WorkerOutcome::InvalidDropped};
    Owner first{};
    Owner second{};
  };

  explicit EpochWorkerModel(double invalidTimestamp, std::uint64_t startEpoch = 1)
    : m_pair(invalidTimestamp, startEpoch)
  {
  }

  Result Accept(Event event, LayerInfo info = {})
  {
    if (event.type != EpochEventType::Packet)
    {
      // A misplaced, duplicated or backwards control cannot roll the worker
      // epoch back or release a newer currently pending original.
      return {m_pair.AdvanceEpoch(event.epoch)
                  ? WorkerOutcome::BarrierApplied : WorkerOutcome::ControlRefused,
              {}, {}};
    }
    if (event.epoch < m_pair.Epoch())
      return {WorkerOutcome::StaleDropped, {}, {}};
    if (event.epoch > m_pair.Epoch())
      return {WorkerOutcome::FutureDropped, {}, {}};
    // Use the producer-stamped envelope, NEVER "current worker epoch" to
    // invent the packet's provenance after a priority seek/flush.
    info.epoch = event.epoch;
    auto out = m_pair.Observe(std::move(event.original), info);
    switch (out.disposition)
    {
      case Disposition::Held:
        return {WorkerOutcome::Held, {}, {}};
      case Disposition::PairMetadataOnly:
        return {WorkerOutcome::MetadataPairOnly, std::move(out.first), std::move(out.second)};
      case Disposition::StockFallback:
        return {WorkerOutcome::StockFallback, std::move(out.first), std::move(out.second)};
      case Disposition::StaleDropped:
        return {WorkerOutcome::StaleDropped, {}, {}};
      case Disposition::InvalidDropped:
        return {WorkerOutcome::InvalidDropped, {}, {}};
    }
    return {};
  }

  Owner TakeForStock(std::uint64_t epoch)
  {
    return m_pair.TakeForStock(epoch);
  }

  bool HasPending() const noexcept { return m_pair.HasPending(); }
  std::uint64_t Epoch() const noexcept { return m_pair.Epoch(); }
  void Close() noexcept { m_pair.Close(); }

private:
  PairOwners<Message> m_pair;
};
} // namespace GazelleFELPrecreate
