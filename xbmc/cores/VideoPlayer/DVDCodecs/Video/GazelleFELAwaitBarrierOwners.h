// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// OFFLINE, UNWIRED original-message owner contract for an UNAPPLIED seek/flush.
//
// Real Kodi priority-10 decoder retries can overtake priority-1 GENERAL_FLUSH,
// while the opposite inversion exists for ordinary priority-0 demux messages.
// Therefore the immutable producer generation and actual worker-applied flush
// generation BOTH matter. New-generation messages that arrive before their
// flush must NOT be sent to stock, examined as FEL or silently discarded.
//
// This research model retains at most TWO original shared message owners and
// 2*16MiB of declared payload bytes; capacity/deadline failures leave the
// incoming ORIGINAL owned by the caller and require upstream backpressure.
// That vital caller contract is NOT implemented by the live Kodi worker.
// A timeout NEVER releases media for pre-flush decode. No packet cloning,
// Kodi queue PutBack, native decoder, live media data, or device actions.

#include "GazelleFELPrecreateAdmission.h"
#include "GazelleFELPairing.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <utility>

namespace GazelleFELPrecreate
{
constexpr std::size_t kMaxAwaitBarrierOwners = 2;
constexpr std::size_t kMaxAwaitBarrierBytes =
    kMaxAwaitBarrierOwners * GazelleFELPairing::kMaxLayerPacketBytes;

enum class AwaitHoldResult : std::uint8_t
{
  HeldOriginal,
  CallerMustRetain,   // Cap reached; no owner has been taken or destroyed
  NotAwaitingBarrier, // Any other admission; caller retains owner unchanged
  InvalidOriginal     // Null/zero/oversized input; caller retains owner
};

enum class AwaitState : std::uint8_t
{
  Empty,
  WaitingForBarrier,
  DeadlineNeedsControlRecovery, // still owns originals; NEVER stock replay
  ReadyAfterBarrier,
  SupersededBySeek, // explicit drop required, NEVER direct stock replay
  InconsistentEpochs
};

template <class Message>
class AwaitBarrierOwners
{
public:
  using Owner = std::shared_ptr<Message>;

  struct Release
  {
    std::array<Owner, kMaxAwaitBarrierOwners> original{};
    std::size_t count{0};
    // Consumers must deliver each original DIRECTLY to stock exactly once
    // AFTER applying the barrier and revalidating producer generation.
    // Never requeue via PutBack or interpret as FEL.
  };

  explicit AwaitBarrierOwners(std::uint64_t maxWaitTicks) noexcept
      : m_maxWaitTicks(maxWaitTicks)
  {
  }

  AwaitBarrierOwners(const AwaitBarrierOwners&) = delete;
  AwaitBarrierOwners& operator=(const AwaitBarrierOwners&) = delete;

  std::size_t Size() const noexcept { return m_size; }
  std::size_t Bytes() const noexcept { return m_bytes; }
  std::uint64_t Epoch() const noexcept { return m_epoch; }

  AwaitHoldResult TryHold(Owner& original,
                          std::uint64_t packetEpoch,
                          std::uint64_t publishedEpoch,
                          std::uint64_t appliedEpoch,
                          std::size_t bytes,
                          std::uint64_t nowTicks) noexcept
  {
    if (!original || bytes == 0 || bytes > GazelleFELPairing::kMaxLayerPacketBytes)
      return AwaitHoldResult::InvalidOriginal;
    if (ClassifyEpoch(packetEpoch, publishedEpoch, appliedEpoch) != Admission::AwaitBarrier)
      return AwaitHoldResult::NotAwaitingBarrier;
    if (m_size != 0 && m_epoch != packetEpoch)
      return AwaitHoldResult::CallerMustRetain;
    if (m_size >= kMaxAwaitBarrierOwners ||
        bytes > kMaxAwaitBarrierBytes - m_bytes)
      return AwaitHoldResult::CallerMustRetain;
    // On deadline expiration no additional owners are accepted until the
    // caller applies/recovers its barrier. No implicit release to stock.
    if (m_size != 0 && (nowTicks < m_firstTicks ||
        nowTicks - m_firstTicks >= m_maxWaitTicks))
      return AwaitHoldResult::CallerMustRetain;
    if (m_size == 0)
    {
      m_epoch = packetEpoch;
      m_firstTicks = nowTicks;
    }
    m_original[m_size++] = std::move(original);
    m_bytes += bytes;
    return AwaitHoldResult::HeldOriginal;
  }

  AwaitState Inspect(std::uint64_t publishedEpoch,
                     std::uint64_t appliedEpoch,
                     std::uint64_t nowTicks) const noexcept
  {
    if (!m_size)
      return AwaitState::Empty;
    if (publishedEpoch == 0 || appliedEpoch == 0 ||
        appliedEpoch > publishedEpoch || m_epoch > publishedEpoch ||
        nowTicks < m_firstTicks)
      return AwaitState::InconsistentEpochs;
    if (m_epoch < publishedEpoch)
      return AwaitState::SupersededBySeek;
    if (m_epoch <= appliedEpoch)
      return m_epoch == appliedEpoch ? AwaitState::ReadyAfterBarrier
                                     : AwaitState::SupersededBySeek;
    if (nowTicks - m_firstTicks >= m_maxWaitTicks)
      return AwaitState::DeadlineNeedsControlRecovery;
    return AwaitState::WaitingForBarrier;
  }

  // Caller must atomically validate (published,applied) under the same
  // authoritative queue/seek control before consuming this Release. A
  // concurrent producer seek AFTER this check would otherwise invalidate it.
  Release TakeAfterBarrier(std::uint64_t publishedEpoch,
                           std::uint64_t appliedEpoch,
                           std::uint64_t nowTicks) noexcept
  {
    if (Inspect(publishedEpoch, appliedEpoch, nowTicks) !=
        AwaitState::ReadyAfterBarrier)
      return {};
    Release ready{};
    ready.count = m_size;
    for (std::size_t i = 0; i < m_size; ++i)
      ready.original[i] = std::move(m_original[i]);
    ClearMetadata();
    return ready;
  }

  // Explicit seek/close revocation; destroys only previously RETAINED owner
  // references. A blocked incoming owner remains with its external caller.
  // No stale old BL is handed to stock after a new producer seek.
  bool DropSuperseded(std::uint64_t publishedEpoch,
                      std::uint64_t appliedEpoch,
                      std::uint64_t nowTicks) noexcept
  {
    if (Inspect(publishedEpoch, appliedEpoch, nowTicks) !=
        AwaitState::SupersededBySeek)
      return false;
    Close();
    return true;
  }

  void Close() noexcept
  {
    for (auto& original : m_original)
      original.reset();
    ClearMetadata();
  }

private:
  void ClearMetadata() noexcept
  {
    m_size = 0;
    m_bytes = 0;
    m_epoch = 0;
    m_firstTicks = 0;
  }

  std::array<Owner, kMaxAwaitBarrierOwners> m_original{};
  const std::uint64_t m_maxWaitTicks;
  std::uint64_t m_epoch{0};
  std::uint64_t m_firstTicks{0};
  std::size_t m_size{0};
  std::size_t m_bytes{0};
};

static_assert(kMaxAwaitBarrierOwners == 2, "At most one BL+EL original pair");
static_assert(kMaxAwaitBarrierBytes <= GazelleFELPairing::kMaxPendingBytes,
              "Research deferred barrier is bounded by pairing budget");
} // namespace GazelleFELPrecreate
