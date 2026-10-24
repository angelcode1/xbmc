#!/usr/bin/env python3
"""Non-deployable Kodi owner-bridge producer stamp source safety checks.

Actual Android ABI compilation is a separate gate. This prevents a future
worker-dequeue epoch parameter or bypass of stock fallback being reintroduced.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MESSAGE = ROOT / "xbmc/cores/VideoPlayer/DVDMessage.h"
BRIDGE = ROOT / "xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELPrecreateKodiBridge.h"
PRODUCER = ROOT / "xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELProducerEpoch.h"
ADAPTER = ROOT / "xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELPrecreateKodiProducerEpoch.h"
POLICY = ROOT / "xbmc/cores/VideoPlayer/GazelleDeferredOpenPolicy.h"

def verify(message: str, bridge: str, producer: str, adapter: str, policy: str) -> None:
    checks = {
        "switch_hard_off": "constexpr bool kDeferredStockResearchEnabled = false;" in policy
                           and "static_assert(!KODI::VIDEO::GAZELLE::kDeferredStockResearchEnabled" in adapter,
        "one_time_nonzero_packet_tag":
            "std::uint64_t m_gazelleResearchEpoch{0};" in message
            and "epoch == 0 || m_gazelleResearchEpoch != 0" in message
            and "m_gazelleResearchEpoch = epoch;" in message,
        "trusted_original_message_stamp":
            "info.epoch = original->GetGazelleResearchEpoch();" in bridge
            and "std::uint64_t seekEpoch" not in bridge
            and "GetGazelleResearchEpoch()" in message,
        "reject_untagged_and_release_prior":
            "if (info.epoch == 0)" in bridge
            and "gate.TakeForStock(gate.Epoch()), std::move(original)" in bridge,
        "producer_tag_before_queue_put":
            "original->TrySetGazelleResearchEpoch(m_epoch)" in producer
            and producer.find("original->TrySetGazelleResearchEpoch(m_epoch)")
                < producer.find("m_queue.Put(original, 0)"),
        "barrier_queue_before_epoch_publish":
            "m_queue.Put(barrier, 1)" in producer
            and producer.find("m_queue.Put(barrier, 1)")
                < producer.find("m_epoch = newEpoch"),
        "real_kodi_adapter_still_unwired":
            "class ResearchProducerIngress final" in adapter
            and '#include "cores/VideoPlayer/DVDMessageQueue.h"' in adapter,
    }
    failed = [name for name, okay in checks.items() if not okay]
    if failed:
        raise AssertionError("GAZELLE_KODI_PRODUCER_SOURCE_REFUSED " + ",".join(failed))

def main() -> None:
    args = [p.read_text(encoding="utf8") for p in
            (MESSAGE, BRIDGE, PRODUCER, ADAPTER, POLICY)]
    verify(*args)
    message, bridge, producer, adapter, policy = args
    mutations = [
        (message, bridge.replace("original->GetGazelleResearchEpoch()", "1"),
         producer, adapter, policy),
        (message, bridge.replace("if (info.epoch == 0)", "if (false)"),
         producer, adapter, policy),
        (message, bridge.replace("gate.TakeForStock(gate.Epoch()), std::move(original)",
                                 "{}, std::move(original)"),
         producer, adapter, policy),
        (message.replace("epoch == 0 || m_gazelleResearchEpoch != 0", "false"),
         bridge, producer, adapter, policy),
        (message, bridge, producer.replace("m_queue.Put(original, 0)", "m_queue.Put(original, 1)"),
         adapter, policy),
        (message, bridge, producer.replace("m_epoch = newEpoch", "m_epoch = m_epoch"),
         adapter, policy),
    ]
    for mutant in mutations:
        try:
            verify(*mutant)
        except AssertionError:
            continue
        raise AssertionError("GAZELLE_KODI_PRODUCER_MUTATION_ACCEPTED")
    print("GAZELLE_KODI_PRODUCER_STAMP_SOURCE_PASS negatives=6 "
          "original_message_epoch_only=true untagged_stock_fallback=true "
          "original_held_owner_released=true no_device=true live_queue=false")

if __name__ == "__main__":
    main()
