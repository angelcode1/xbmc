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
#include "GazelleFELPrecreateDispatchLease.h"
#include "GazelleFELNativeQuiescenceGate.h"

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
  LeasePrepared,       // Original staged, not yet given to any decoder
  InFlight,            // Original lease begun; must finish before flush
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
  using Dispatch = DispatchLease<Message>;

  explicit SeekFence(Queue& queue, std::uint64_t maxWaitTicks,
                     std::uint64_t initialEpoch = 1)
      : m_queue(queue), m_holder(maxWaitTicks), m_published(initialEpoch),
        m_applied(initialEpoch), m_closed(initialEpoch == 0)
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
    // Revoke all PREPARED codec dispatches atomically with publication.
    // An in-flight decoder original remains externally owned until finish.
    m_dispatch.RevokePrepared();
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
    if (m_closed || m_dispatch.InFlight() || epoch == 0 ||
        m_applied == std::numeric_limits<std::uint64_t>::max() ||
        epoch != m_applied + 1 || epoch > m_published)
      return FenceDecision::Refused;
    // A lease's ordinary C++ return does not prove JNI flush or renderer
    // buffer quiescence. This extra witness is SYNTHETIC and UNWIRED;
    // real Kodi currently supplies none of its three required signals.
    if (m_native.NeedsNativeProof() && !m_native.Ready(epoch))
      return FenceDecision::Refused;
    if (m_native.NeedsNativeProof() && !m_native.Consume(epoch))
      return FenceDecision::Refused;
    m_applied = epoch;
    m_holder.DropSuperseded(m_published, m_applied, nowTicks);
    return FenceDecision::Applied;
  }

  // OFFLINE retry ingress: Kodi's VC_FLUSHED and VC_REOPEN normally use
  // SendMessage(original, 10), which can starve a priority-1 seek flush.
  // Reject old original owners AFTER new seek publication and retain new
  // owners for caller backpressure UNTIL their actual flush is applied.
  // Only a same-epoch, already-applied retry can enter the priority-10
  // queue. This only protects retry calls that use THIS SAME ingress.
  // Existing Kodi calls bypass it, and previously queued priority-10
  // packets can still starve a barrier; not a live fairness solution.
  FenceDecision TryEnqueueDecoderRetry(Owner& original)
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    if (m_closed || !original)
      return FenceDecision::Refused;
    const auto admission = ClassifyEpoch(
        original->GetGazelleResearchEpoch(), m_published, m_applied);
    if (admission == Admission::StaleReject)
    {
      original.reset();
      return FenceDecision::StaleDropped;
    }
    if (admission == Admission::UntaggedStock)
      return FenceDecision::UntaggedStockOnly;
    if (admission == Admission::AwaitBarrier)
      return FenceDecision::Backpressure; // caller retains original
    if (admission != Admission::MetadataOnly)
      return FenceDecision::Refused;
    // Kodi queue Put only takes a shared original owner on successful
    // submission; failure leaves it with the caller. Never PutBack.
    if (static_cast<int>(m_queue.Put(original, 10)) != 1)
      return FenceDecision::Backpressure;
    original.reset();
    return FenceDecision::Submitted;
  }

  // A TWO-PHASE lease model for original Kodi packet owners already
  // dequeued from CDVDMessageQueue. Stage is under the seek publication lock,
  // but Begin returns the original shared message for work OUTSIDE that lock.
  // Never feed a decoder directly in one of these locked methods. Cancellation
  // before Begin destroys staged originals; a running lease cannot be
  // revoked, so BarrierApplied refuses to flush until Finish.
  FenceDecision PrepareOriginalLease(Owner& original, std::size_t bytes)
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    if (m_closed || !original)
      return FenceDecision::Refused;
    const auto stamp = original->GetGazelleResearchEpoch();
    const auto admission = ClassifyEpoch(stamp, m_published, m_applied);
    if (admission == Admission::StaleReject)
    {
      original.reset();
      return FenceDecision::StaleDropped;
    }
    if (admission != Admission::MetadataOnly)
      return admission == Admission::AwaitBarrier
                 ? FenceDecision::Backpressure : FenceDecision::Refused;
    const auto result = m_dispatch.Prepare(original, stamp, bytes);
    if (result == LeasePrepare::Prepared)
      return FenceDecision::LeasePrepared;
    return result == LeasePrepare::CallerRetains
               ? FenceDecision::Backpressure : FenceDecision::Refused;
  }

  typename Dispatch::Started BeginOriginalLease() noexcept
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    if (m_closed || m_published != m_applied ||
        m_native.NeedsNativeProof())
      return {};
    auto started = m_dispatch.Begin(m_published);
    if (started && !m_native.InputStarted(started.epoch))
    {
      // The host model must not silently misrepresent a begun decoder
      // operation as cancellable if the native witness refuses it.
      m_dispatch.Finish(started.token);
      return {};
    }
    return started;
  }

  // Release the modeled in-flight lease marker after the external caller
  // reports decoder work complete. Must be called even if the external
  // operation failed. This does NOT cancel native codec work or prove it
  // has stopped; that promise belongs to future real Kodi integration.
  bool FinishOriginalLease(std::uint64_t token) noexcept
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    const auto epoch = m_dispatch.InFlightEpoch();
    if (!m_dispatch.Finish(token))
      return false;
    return m_native.InputReturned(epoch);
  }

  // No JNI call is made here. These methods record simulated independent
  // witnesses under the same publication fence; real Kodi cannot use them
  // until the MediaCodec and renderer lifetimes are separately instrumented.
  bool BeginNativeFlushProof(std::uint64_t targetEpoch) noexcept
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    if (m_closed || m_dispatch.InFlight() || targetEpoch != m_applied + 1 ||
        targetEpoch > m_published)
      return false;
    return m_native.BeginFlushProof(targetEpoch);
  }

  QuiescenceStep ReportNativeFlush(std::uint64_t epoch,
                                   bool callReturned,
                                   bool jniExceptionFree) noexcept
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    return m_native.ReportNativeFlush(epoch, callReturned, jniExceptionFree);
  }

  QuiescenceStep ReportRetiredOutputs(std::uint64_t epoch,
                                      bool poolDetached,
                                      bool rendererReferencesReleased) noexcept
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    return m_native.ReportOutputRetired(
        epoch, poolDetached, rendererReferencesReleased);
  }

  bool InFlightForAuditOnly() const
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    return m_dispatch.InFlight();
  }

  std::size_t PreparedForAuditOnly() const
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    return m_dispatch.Queued();
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
    m_dispatch.Close();
    m_native.Close();
  }

private:
  Queue& m_queue;
  mutable std::mutex m_mutex;
  Hold m_holder;
  Dispatch m_dispatch;
  NativeQuiescenceGate m_native;
  std::uint64_t m_published;
  std::uint64_t m_applied;
  bool m_closed{false};
};
} // namespace GazelleFELPrecreate
