// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// Non-deployable pre-decoder BL/EL *message ownership* research.
// Does not decode, copy or inspect media data, invoke Kodi or choose a codec.
// This header is intentionally NOT connected to VideoPlayerVideo.cpp.
// All live paths remain disabled by GazelleDeferredOpenPolicy.h.

#include "GazelleFELPairing.h"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <utility>

namespace GazelleFELPrecreate
{
enum class Disposition : std::uint8_t
{
  Held,                  // One original shared message owner retained
  PairMetadataOnly,      // Both original owners returned in arrival order
  StockFallback,         // Both (or sole) owners returned to caller for stock
  StaleDropped,          // Incoming prior-epoch owner released, not replayed
  InvalidDropped         // Null incoming owner; no media access or pairing
};

struct LayerInfo
{
  std::uint64_t epoch{0};
  std::int64_t demuxerId{-1};
  std::int64_t streamId{-1};
  bool isDualStream{false};
  bool isEL{false};
  bool protectedContent{true};
  bool dropRequested{true};
  std::size_t bytes{0};
  double dts{0.0};
  double pts{0.0};
};

// Owner must be the type of the *original* Kodi shared message (normally
// std::shared_ptr<CDVDMsgDemuxerPacket>), never a copied DemuxPacket.
// No codec or nal byte ownership is introduced by this contract.
template <class Message>
class PairOwners
{
public:
  using Owner = std::shared_ptr<Message>;

  struct Result
  {
    Disposition disposition{Disposition::InvalidDropped};
    Owner first{};
    Owner second{};
    // PairMetadataOnly NEVER means "FEL verified": genuine RPU validation,
    // BL/EL NAL parsing, and native residual decode are separate gates.
  };

  explicit PairOwners(double invalidClock, std::uint64_t epoch = 0) noexcept
    : m_invalidClock(invalidClock), m_epoch(epoch)
  {
  }

  PairOwners(const PairOwners&) = delete;
  PairOwners& operator=(const PairOwners&) = delete;

  std::uint64_t Epoch() const noexcept { return m_epoch; }
  bool HasPending() const noexcept { return static_cast<bool>(m_pending); }

  // A seek/flush revokes the previous epoch. Destruction of the last
  // shared_ptr to the old Kodi message frees its packet once by Kodi's normal
  // CDVDMsgDemuxerPacket destructor; stale media is NEVER replayed.
  // Reject non-increasing or wrapping epochs rather than silently reusing IDs.
  bool AdvanceEpoch(std::uint64_t next) noexcept
  {
    if (next <= m_epoch)
      return false;
    m_pending.reset();
    m_epoch = next;
    m_pendingInfo = {};
    return true;
  }

  void Close() noexcept
  {
    m_pending.reset();
    m_pendingInfo = {};
  }

  // Only a timed-out, same-epoch pending owner can be returned for STOCK
  // input replay. Caller must submit it exactly once through normal Kodi
  // AddData processing, not duplicate or prepend it to a different epoch.
  Owner TakeForStock(std::uint64_t epoch) noexcept
  {
    if (epoch != m_epoch)
      return {};
    m_pendingInfo = {};
    return std::move(m_pending);
  }

  Result Observe(Owner incoming, const LayerInfo& info) noexcept
  {
    if (!incoming)
      return {};
    if (info.epoch != m_epoch)
      return {Disposition::StaleDropped, {}, {}};
    if (!Eligible(info))
      return FallBack(std::move(incoming));
    if (!m_pending)
    {
      m_pendingInfo = info;
      m_pending = std::move(incoming);
      return {Disposition::Held, {}, {}};
    }
    if (m_pendingInfo.epoch == m_epoch &&
        m_pendingInfo.demuxerId == info.demuxerId &&
        m_pendingInfo.streamId != info.streamId &&
        m_pendingInfo.isEL != info.isEL &&
        GazelleFELPairing::SameAccessUnit(m_pendingInfo.dts, m_pendingInfo.pts,
                                          info.dts, info.pts, m_invalidClock) &&
        m_pendingInfo.bytes <=
            GazelleFELPairing::kMaxPendingBytes - info.bytes)
    {
      auto first = std::move(m_pending);
      m_pendingInfo = {};
      return {Disposition::PairMetadataOnly, std::move(first), std::move(incoming)};
    }
    return FallBack(std::move(incoming));
  }

private:
  bool Eligible(const LayerInfo& info) const noexcept
  {
    return info.isDualStream && !info.protectedContent && !info.dropRequested &&
           info.demuxerId >= 0 && info.streamId >= 0 &&
           info.bytes > 0 &&
           info.bytes <= GazelleFELPairing::kMaxLayerPacketBytes &&
           (GazelleFELPairing::ValidClock(info.dts, m_invalidClock) ||
            GazelleFELPairing::ValidClock(info.pts, m_invalidClock));
  }

  Result FallBack(Owner incoming) noexcept
  {
    auto prior = std::move(m_pending);
    m_pendingInfo = {};
    return {Disposition::StockFallback, std::move(prior), std::move(incoming)};
  }

  const double m_invalidClock;
  std::uint64_t m_epoch;
  Owner m_pending{};
  LayerInfo m_pendingInfo{};
};
} // namespace GazelleFELPrecreate
