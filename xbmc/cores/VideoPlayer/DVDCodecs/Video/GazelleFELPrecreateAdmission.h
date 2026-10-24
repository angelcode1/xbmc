// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

// UNWIRED, NO-DEVICE safety policy for Kodi's priority message queue.
// The queue can deliver a priority-10 decoder retry BEFORE an earlier
// priority-1 seek flush. A worker-local epoch is therefore insufficient:
// every proposed BL/EL pre-create pair and stock replay must check BOTH the
// latest producer-PUBLISHED epoch and the worker's APPLIED barrier epoch.
//
// Pure policy, no packet buffer access, no codec call, no queue rewrite.
// This deliberately cannot authorize FEL, an OMX alias or actual playback.
#include <cstdint>

namespace GazelleFELPrecreate
{
enum class Admission : std::uint8_t
{
  UntaggedStock,  // Normal Kodi message, not eligible for pre-create identity
  StaleReject,    // Old packet, including high-priority retry before a flush
  AwaitBarrier,   // Producer published seek but worker hasn't applied flush
  InvalidReject,  // Invalid/fabricated/wrapped generation
  MetadataOnly    // Safe for bounded owner-metadata comparison, NOT FEL
};

// Caller must sample publishedEpoch under the SAME producer serialization
// lock as packet enqueue and seek barrier Put, and must revalidate before
// handing an original packet to either a codec or libdovi. No such live
// worker/sender lock integration currently exists.
constexpr Admission ClassifyEpoch(std::uint64_t packetEpoch,
                                  std::uint64_t publishedEpoch,
                                  std::uint64_t appliedEpoch) noexcept
{
  if (packetEpoch == 0)
    return Admission::UntaggedStock;
  if (publishedEpoch == 0 || appliedEpoch == 0 ||
      appliedEpoch > publishedEpoch || packetEpoch > publishedEpoch)
    return Admission::InvalidReject;
  // A published seek supersedes previous BL/EL even if priority-10
  // requeue delivers that old message before priority-1 GENERAL_FLUSH.
  if (packetEpoch < publishedEpoch || packetEpoch < appliedEpoch)
    return Admission::StaleReject;
  // New-epoch packet must not be paired/decoded BEFORE its flush executes.
  // It requires a separately bounded pending-barrier ownership strategy;
  // dropping it or decoding it early would be incorrect.
  if (packetEpoch > appliedEpoch)
    return Admission::AwaitBarrier;
  return Admission::MetadataOnly;
}

// Timed-out single BL cannot be replayed into stock while ANY newer seek is
// published but still pending behind higher priority work.
constexpr bool MayDirectStockReplay(std::uint64_t originalEpoch,
                                    std::uint64_t publishedEpoch,
                                    std::uint64_t appliedEpoch) noexcept
{
  return ClassifyEpoch(originalEpoch, publishedEpoch, appliedEpoch) ==
         Admission::MetadataOnly;
}

static_assert(ClassifyEpoch(1, 2, 1) == Admission::StaleReject,
              "Priority-ten retry must not bypass published seek");
static_assert(ClassifyEpoch(2, 2, 1) == Admission::AwaitBarrier,
              "Fresh packet cannot bypass unapplied flush");
static_assert(ClassifyEpoch(2, 2, 2) == Admission::MetadataOnly,
              "Applied seek admits metadata-only work");
static_assert(ClassifyEpoch(0, 2, 2) == Admission::UntaggedStock,
              "Untagged Kodi packets remain stock-only");
static_assert(!MayDirectStockReplay(1, 2, 1),
              "Old owner must not be replayed after seek publication");
} // namespace GazelleFELPrecreate
