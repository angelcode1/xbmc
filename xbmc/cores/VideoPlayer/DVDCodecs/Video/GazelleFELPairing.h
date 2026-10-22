// SPDX-License-Identifier: MIT
// Fail-closed timing and bounded pairing helpers for Kodi dual-track P7 packets.
// This file contains NO Dolby driver calls, kernel writes or codec initialization.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>

namespace GazelleFELPairing
{
constexpr std::size_t kMaxPendingPackets = 8;
constexpr std::size_t kMaxPendingBytes = 64u * 1024u * 1024u;
constexpr std::size_t kMaxLayerPacketBytes = 16u * 1024u * 1024u;
constexpr double kClockToleranceUs = 100.0;

inline bool ValidClock(double value, double invalid) noexcept
{
  return std::isfinite(value) && value != invalid;
}

// Same decoder access unit: prefer DTS when both demux tracks have it.
// If one/both DTS clocks are unavailable, PTS must exist on both sides.
// Never override a DTS disagreement with matching PTS: reordered video
// may have the same PTS but refer to a different decoder access unit.
inline bool SameAccessUnit(double leftDts, double leftPts,
                           double rightDts, double rightPts,
                           double invalid) noexcept
{
  if (ValidClock(leftDts, invalid) && ValidClock(rightDts, invalid))
    return std::fabs(leftDts - rightDts) <= kClockToleranceUs;
  if (ValidClock(leftPts, invalid) && ValidClock(rightPts, invalid))
    return std::fabs(leftPts - rightPts) <= kClockToleranceUs;
  return false;
}

template <class Queue>
inline typename Queue::iterator FindMate(Queue& queued,
                                          bool incomingIsEl,
                                          double dts, double pts,
                                          double invalid)
{
  return std::find_if(queued.begin(), queued.end(), [&](const auto& item) {
    return item.isEL != incomingIsEl &&
           SameAccessUnit(item.dts, item.pts, dts, pts, invalid);
  });
}

template <class Queue>
inline bool CanBuffer(const Queue& queued, std::size_t incomingBytes)
{
  if (!incomingBytes || incomingBytes > kMaxLayerPacketBytes ||
      queued.size() >= kMaxPendingPackets)
    return false;
  std::size_t remaining = kMaxPendingBytes;
  for (const auto& packet : queued)
  {
    if (packet.data.size() > remaining)
      return false;
    remaining -= packet.data.size();
  }
  return incomingBytes <= remaining;
}
} // namespace GazelleFELPairing
