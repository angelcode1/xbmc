// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// Compile-only research producer stamp contract. NOT in Kodi playback.
// This wrapper is specifically modeled on CDVDMessageQueue::Put(original,
// priority). Both packet Put and high-priority seek barrier Put run under
// ONE producer lock, and no source may bypass this wrapper when enabled.
// The packet itself receives its immutable generation BEFORE Put wakes the
// worker; a dequeue-time stamp is incorrect when GENERAL_FLUSH overtakes BL.
//
// A success result means accepted by queue, NOT decoded. Failure after a tag
// is fail-closed: a failed owner may not be re-stamped or retried in a new
// generation. No packet data, raw pointer, NAL or decoder is accessed here.
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <utility>

namespace GazelleFELPrecreate
{
template <class OriginalMessage, class KodiLikeQueue>
class ProducerEpoch
{
public:
  using Owner = std::shared_ptr<OriginalMessage>;
  explicit ProducerEpoch(KodiLikeQueue& queue, std::uint64_t initialEpoch = 1)
    : m_queue(queue), m_epoch(initialEpoch)
  {
  }

  ProducerEpoch(const ProducerEpoch&) = delete;
  ProducerEpoch& operator=(const ProducerEpoch&) = delete;

  bool PutOriginal(const Owner& original)
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_open || m_epoch == 0 || !original ||
        !original->TrySetGazelleResearchEpoch(m_epoch))
      return false;
    // Kodi's documented MSGQ_OK is +1. A failed Put retains the one-time
    // stamp, so a caller must fail closed instead of reusing a later epoch.
    return static_cast<int>(m_queue.Put(original, 0)) == 1;
  }

  // Factory is called with the NEW epoch while the producer lock is held,
  // and must return the actual priority control message carrying that epoch.
  // Kodi's normal GENERAL_FLUSH handler has other responsibilities (including
  // m_bAbortOutput) and must NOT be replaced by this unwired contract.
  template <class BarrierFactory>
  bool PutBarrier(BarrierFactory makeBarrier)
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_open || m_epoch == std::numeric_limits<std::uint64_t>::max())
      return false;
    const auto newEpoch = m_epoch + 1u;
    const auto barrier = makeBarrier(newEpoch);
    if (!barrier || static_cast<int>(m_queue.Put(barrier, 1)) != 1)
      return false;
    m_epoch = newEpoch;
    return true;
  }

  void Close() noexcept
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_open = false;
  }

  std::uint64_t ProducerEpochForAuditOnly() const noexcept
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_epoch;
  }

private:
  KodiLikeQueue& m_queue;
  mutable std::mutex m_mutex;
  std::uint64_t m_epoch;
  bool m_open{true};
};
} // namespace GazelleFELPrecreate
