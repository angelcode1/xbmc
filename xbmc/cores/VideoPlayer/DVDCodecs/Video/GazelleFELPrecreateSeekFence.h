// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// OFFLINE ONLY: serialized seek-publication, barrier-application and
// original-message admission model. This is NOT called by Kodi's worker.
//
// A priority-10 decoder retry can overtake priority-1 GENERAL_FLUSH, while
// ordinary priority-0 video messages can lag behind that same flush.
// All admissions and *synchronous, noexcept* handoff callbacks use one
// mutex with producer packet Put/barrier Put and publication. No callback
// may block on Kodi's worker, call a decoder, or enter this fence recursively.
// Real Kodi worker/producer synchronization and backpressure are UNPROVEN.
// Do not use this class in real playback, decoder selection or APK builds.
#include "GazelleFELAwaitBarrierOwners.h"
#include "GazelleFELPrecreateAdmission.h"

#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <type_traits>
#include <utility>

namespace GazelleFELPrecreate
{
enum class FenceDecision : std::uint8_t
{
  Submitted,           // Producer queue accepted the original message
  Applied,             // Worker reported that its real flush ran
  Committed,           // Callback synchronously accepted original for stock
  AwaitHeld,           // Original held pending worker-applied flush
  Backpressure,        // Caller still owns original; must stop/wait/recover
  UntaggedStockOnly,   // Never qualify for precreate pairing
  StaleDropped,        // Old original owner released without stock replay
  Refused              // Invalid/closed/failed queue/barrier
};

template <class Message, class Queue>
class SeekFence
{
public:
  using Owner = std::shared_ptr<Message>;
  using Hold = AwaitBarrierOwners<Message>;

  explicit SeekFence(Queue& queue, std::uint64_t maxWaitTicks,
                     std::uint64_t initialEpoch = 1)
      : m_queue(queue), m_holder(maxWaitTicks), m_published(initialEpoch),
        m_applied(initialEpoch)
  {
  }

  SeekFence(const SeekFence&) = delete;
  SeekFence& operator=(const SeekFence&) = delete;

  FenceDecision EnqueueOriginal(const Owner& original)
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    if (m_closed || !original || m_published == 0 ||
        !original->TrySetGazelleResearchEpoch(m_published))
      return FenceDecision::Refused;
    return static_cast<int>(m_queue.Put(original, 0)) == 1
               ? FenceDecision::Submitted : FenceDecision::Refused;
  }

  template <class BarrierFactory>
  FenceDecision PublishBarrier(BarrierFactory&& makeBarrier,
                               std::uint64_t nowTicks)
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    if (m_closed || m_published == std::numeric_limits<std::uint64_t>::max())
      return FenceDecision::Refused;
    const auto next = m_published + 1;
    const auto barrier = std::forward<BarrierFactory>(makeBarrier)(next);
    if (!barrier || static_cast<int>(m_queue.Put(barrier, 1)) != 1)
      return FenceDecision::Refused;
    m_published = next;
    // Expire a prior-generation held owner without handing it to stock.
    m_holder.DropSuperseded(m_published, m_applied, nowTicks);
    return FenceDecision::Submitted;
  }

  // Called only AFTER the actual flush worker action has completed.
  // An out-of-order/missing control cannot skip directly to a future epoch.
  FenceDecision BarrierApplied(std::uint64_t epoch,
                               std::uint64_t nowTicks)
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    if (m_closed || epoch != m_applied + 1 || epoch > m_published)
      return FenceDecision::Refused;
    m_applied = epoch;
    m_holder.DropSuperseded(m_published, m_applied, nowTicks);
    return FenceDecision::Applied;
  }

  // The returned enum is NOT permission for caller to feed a decoder:
  // only CommitOriginal() can commit under the shared producer fence.
  FenceDecision HoldOrRefuse(Owner& original, std::size_t declaredBytes,
                             std::uint64_t nowTicks)
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    if (m_closed || !original)
      return FenceDecision::Refused;
    const auto packetEpoch = original->GetGazelleResearchEpoch();
    const auto a = ClassifyEpoch(packetEpoch, m_published, m_applied);
    if (a == Admission::UntaggedStock)
      return FenceDecision::UntaggedStockOnly;
    if (a == Admission::StaleReject)
    {
      original.reset();
      return FenceDecision::StaleDropped;
    }
    if (a != Admission::AwaitBarrier)
      return FenceDecision::Refused;
    const auto held = m_holder.TryHold(original, packetEpoch,
                                      m_published, m_applied,
                                      declaredBytes, nowTicks);
    return held == AwaitHoldResult::HeldOriginal
               ? FenceDecision::AwaitHeld : FenceDecision::Backpressure;
  }

  // Atomic check+commit point. callback must be nonthrowing, synchronous,
  // nonblocking and not call SeekFence/queue again. No real Kodi codec work
  // is allowed inside it. If callback fails, original stays with caller.
  // Production would need a proven equivalent at the real worker handoff.
  template <class Callback>
  FenceDecision CommitOriginal(Owner& original, Callback&& callback) noexcept
  {
    static_assert(std::is_nothrow_invocable_r_v<bool, Callback, const Owner&>,
                  "Commit callback must be bool noexcept(const Owner&)");
    std::lock_guard<std::mutex> guard(m_mutex);
    if (m_closed || !original)
      return FenceDecision::Refused;
    if (ClassifyEpoch(original->GetGazelleResearchEpoch(),
                      m_published, m_applied) != Admission::MetadataOnly)
      return FenceDecision::Refused;
    if (!std::forward<Callback>(callback)(original))
      return FenceDecision::Backpressure;
    original.reset();
    return FenceDecision::Committed;
  }

  // All-or-nothing acknowledgment under the SAME seek publication lock.
  // A rejecting downstream callback leaves BOTH original messages held,
  // without PutBack, duplicated queue bytes, or a fabricated raw packet.
  // Successful callback MUST retain original shared pointers or complete
  // synchronous handoff. This is never called by the real Kodi decoder.
  template <class Callback>
  std::size_t CommitReady(std::uint64_t nowTicks, Callback&& callback) noexcept
  {
    static_assert(std::is_nothrow_invocable_r_v<
                      bool, Callback,
                      const std::array<Owner, kMaxAwaitBarrierOwners>&,
                      std::size_t>,
                  "Ready callback must acknowledge bool noexcept");
    std::lock_guard<std::mutex> guard(m_mutex);
    if (m_closed)
      return 0;
    const auto count = m_holder.Size();
    const bool accepted = m_holder.AcceptAfterBarrier(
        m_published, m_applied, nowTicks, std::forward<Callback>(callback));
    return accepted ? count : 0;
  }

  // Deliberately an audit snapshot only: it is NOT an admission permit.
  std::uint64_t PublishedForAuditOnly() const
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    return m_published;
  }
  std::uint64_t AppliedForAuditOnly() const
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    return m_applied;
  }
  std::size_t PendingForAuditOnly() const
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    return m_holder.Size();
  }

  void Close() noexcept
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    m_closed = true;
    m_holder.Close();
  }

private:
  Queue& m_queue;
  mutable std::mutex m_mutex;
  Hold m_holder;
  std::uint64_t m_published;
  std::uint64_t m_applied;
  bool m_closed{false};
};
} // namespace GazelleFELPrecreate
