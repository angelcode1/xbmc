// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// Kodi-specific, compile-only adapter for the UNWIRED first-AU owner gate.
// It borrows actual DemuxPacket metadata through the ORIGINAL message owner;
// it never clones, rewrites, releases, enqueues or decodes a Kodi packet.
// Nothing in this header is invoked by VideoPlayerVideo's runtime path.
#include "GazelleFELPrecreateOwners.h"

#include "cores/VideoPlayer/DVDMessage.h"
#include "cores/VideoPlayer/Interface/DemuxPacket.h"
#include "cores/VideoPlayer/GazelleDeferredOpenPolicy.h"

#include <cstdint>
#include <memory>
#include <type_traits>
#include <utility>

namespace GazelleFELPrecreateKodi
{
using Owner = std::shared_ptr<CDVDMsgDemuxerPacket>;
using Gate = GazelleFELPrecreate::PairOwners<CDVDMsgDemuxerPacket>;

static_assert(std::is_base_of<CDVDMsg, CDVDMsgDemuxerPacket>::value,
              "Kodi's packet message must retain its normal destructor");
static_assert(!KODI::VIDEO::GAZELLE::kDeferredStockResearchEnabled,
              "This message adapter must remain non-deployable");

// The owning Kodi CDVDMsgDemuxerPacket's destructor frees its DemuxPacket.
// Do not construct another message around that same raw pointer: ownership
// belongs exclusively to the ORIGINAL shared message object.
inline GazelleFELPrecreate::LayerInfo BorrowInfo(
    const Owner& original, bool streamProtected) noexcept
{
  GazelleFELPrecreate::LayerInfo info{};
  if (!original)
    return info;
  // Source-issued, single-assignment original-message generation ONLY.
  // Worker-dequeue-time stamping is unsafe because priority flush can
  // overtake already enqueued BL/EL packets. Untagged stock messages have
  // generation 0 and must never be accepted as pre-create pair owners.
  info.epoch = original->GetGazelleResearchEpoch();
  const DemuxPacket* const packet = original->GetPacket();
  if (!packet)
    return info;
  info.demuxerId = packet->demuxerId;
  info.streamId = packet->iStreamId;
  info.isDualStream = packet->isDualStream;
  info.isEL = packet->isELPackage;
  info.protectedContent = streamProtected || packet->cryptoInfo != nullptr;
  info.dropRequested = original->GetPacketDrop();
  // Reject empty, negative, null-buffer and oversized lengths in the gate.
  // No access to pData, PTS/DTS mutation, or side-data normalization.
  if (packet->iSize > 0 && packet->pData != nullptr)
    info.bytes = static_cast<std::size_t>(packet->iSize);
  info.dts = packet->dts;
  info.pts = packet->pts;
  return info;
}

// Deliberately unused by live playback. This is the exact typed seam that
// a future video-worker implementation would call AFTER it demonstrates
// genuine queue/flush epoch provenance and exactly-once stock re-delivery.
// PairMetadataOnly is NEVER a FEL decoder selection decision.
inline Gate::Result ObserveOriginal(
    Gate& gate, Owner original, bool streamProtected) noexcept
{
  const auto info = BorrowInfo(original, streamProtected);
  // A 0-generation owner came from ordinary stock Kodi; it cannot
  // authenticate a seek-epoch BL/EL pair. Fail closed, releasing any held
  // same-epoch message for stock FIRST. An untagged message must not leave a
  // previous layer held to be paired with some later, unrelated packet.
  if (info.epoch == 0)
    return {GazelleFELPrecreate::Disposition::StockFallback,
            gate.TakeForStock(gate.Epoch()), std::move(original)};
  return gate.Observe(std::move(original), info);
}
} // namespace GazelleFELPrecreateKodi
