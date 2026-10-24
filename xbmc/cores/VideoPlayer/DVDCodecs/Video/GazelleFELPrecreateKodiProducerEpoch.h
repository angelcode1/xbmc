// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// Kodi-type checked but UNWIRED, hard-disabled producer-time stamp adapter.
// Does NOT replace Kodi's existing ProcessVideoData/ProcessPacket/Flush logic.
// Do not call unless caller, worker, all BL/EL sources and seek/close paths
// share this exact serialized ingress; production safety is NOT proven.
#include "GazelleFELProducerEpoch.h"

#include "cores/VideoPlayer/DVDMessage.h"
#include "cores/VideoPlayer/DVDMessageQueue.h"
#include "cores/VideoPlayer/GazelleDeferredOpenPolicy.h"

#include <cstdint>
#include <memory>
#include <type_traits>

namespace GazelleFELPrecreateKodi
{
// These inherit Kodi's EXISTING message type so its typed worker handler
// remains able to cast to CDVDMsgBool, retaining the normal flush payload.
class ResearchFlushBarrier final : public CDVDMsgBool
{
public:
  ResearchFlushBarrier(bool sync, std::uint64_t epoch) noexcept
    : CDVDMsgBool(CDVDMsg::GENERAL_FLUSH, sync), m_epoch(epoch)
  {
  }
  std::uint64_t Epoch() const noexcept { return m_epoch; }

private:
  const std::uint64_t m_epoch;
};

class ResearchResetBarrier final : public CDVDMsg
{
public:
  explicit ResearchResetBarrier(std::uint64_t epoch) noexcept
    : CDVDMsg(CDVDMsg::GENERAL_RESET), m_epoch(epoch)
  {
  }
  std::uint64_t Epoch() const noexcept { return m_epoch; }

private:
  const std::uint64_t m_epoch;
};

static_assert(!KODI::VIDEO::GAZELLE::kDeferredStockResearchEnabled,
              "Producer epoch adapter must remain disabled");
static_assert(std::is_base_of<CDVDMsgBool, ResearchFlushBarrier>::value,
              "Flush handler must retain the original Kodi bool payload");
static_assert(std::is_base_of<CDVDMsg, ResearchResetBarrier>::value,
              "Reset handler must retain the normal Kodi message type");

// Producer/stamp and queue.Put are serialized in the same research lock,
// BEFORE worker Get() can return the original message. ProducerEpoch does
// not take ownership of DemuxPacket; its ORIGINAL CDVDMsgDemuxerPacket does.
// No new CDVDMsgDemuxerPacket is created around an existing raw pointer.
class ResearchProducerIngress final
{
public:
  explicit ResearchProducerIngress(CDVDMessageQueue& queue)
    : m_ingress(queue)
  {
  }

  bool QueueOriginal(const std::shared_ptr<CDVDMsgDemuxerPacket>& original)
  {
    return m_ingress.PutOriginal(original);
  }

  bool QueueFlush(bool sync)
  {
    // Research-only envelope: this is NOT a drop-in replacement for Kodi's
    // CVideoPlayerVideo::Flush (which must also abort active rendering).
    return m_ingress.PutBarrier([sync](std::uint64_t epoch) {
      return std::make_shared<ResearchFlushBarrier>(sync, epoch);
    });
  }

  bool QueueReset()
  {
    return m_ingress.PutBarrier([](std::uint64_t epoch) {
      return std::make_shared<ResearchResetBarrier>(epoch);
    });
  }

  void Close() noexcept { m_ingress.Close(); }
  std::uint64_t EpochForAuditOnly() const noexcept
  {
    return m_ingress.ProducerEpochForAuditOnly();
  }

private:
  GazelleFELPrecreate::ProducerEpoch<CDVDMsgDemuxerPacket,
                                     CDVDMessageQueue> m_ingress;
};
} // namespace GazelleFELPrecreateKodi
