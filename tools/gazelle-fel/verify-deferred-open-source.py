#!/usr/bin/env python3
"""Source regression gate for the OFF-by-default Kodi video worker FEL scaffold.

Does NOT compile Kodi, load libdovi, access a Cube, or prove thread correctness.
Read-only check of two pinned source files in this exact checkout.
"""
from __future__ import annotations

import argparse
from pathlib import Path

CPP = Path("xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp")
HEADER = Path("xbmc/cores/VideoPlayer/VideoPlayerVideo.h")


def check(cpp: str, header: str) -> None:
    markers = {
        "feature_explicitly_off":
            "constexpr bool kGazelleDeferredStockResearchEnabled = false;" in cpp and
            "constexpr bool kGazelleDeferredStockResearchEnabled = true;" not in cpp,
        "candidate_requires_clear_p7":
            "hint.dovi.dv_profile == 7 && hint.dovi.el_present_flag" in cpp and
            "!hint.cryptoSession && !hint.dvd && !hint.stills" in cpp,
        "existing_initial_factory":
            "std::unique_ptr<CDVDVideoCodec> codec = CDVDFactoryCodec::CreateVideoCodec(hint, m_processInfo);" in cpp,
        "stock_only_factory":
            "m_pVideoCodec = CDVDFactoryCodec::CreateVideoCodec(hint, m_processInfo);" in cpp,
        "stock_after_timeout":
            "std::chrono::steady_clock::now() - m_gazelleDeferredSince < 500ms" in cpp,
        "own_worker_state":
            "bool m_gazelleDeferredStockOpen{false};" in header,
        "safe_packet_gate":
            "if (m_gazelleDeferredStockOpen && !GazelleEnsureDeferredStockCodec())" in cpp and
            cpp.index("if (m_gazelleDeferredStockOpen && !GazelleEnsureDeferredStockCodec())\n        continue;\n      DemuxPacket* pPacket =") <
            cpp.index("m_pVideoCodec->SetCodecControl(codecControl);"),
        "timeout_before_output_deref":
            cpp.index("if (m_gazelleDeferredStockOpen)\n      {") <
            cpp.index("if (m_outputSate == OUTPUT_AGAIN &&"),
        "flush_guard":
            "if (m_gazelleDeferredStockOpen && !GazelleEnsureDeferredStockCodec())\n        continue;\n      bool sync =" in cpp,
        "reset_guard":
            "if (m_gazelleDeferredStockOpen && !GazelleEnsureDeferredStockCodec())\n        continue;\n      if(m_pVideoCodec)" in cpp,
        "no_alias_routing":
            "OMX.gazelle.research" not in cpp and
            "GAZELLE_FEL_ENABLE" not in cpp,
        "one_codec_worker_event":
            "OpenStream(msg->m_hints, std::move(msg->m_codec), msg->m_gazelleDeferred);" in cpp,
    }
    failed = [key for key, ok in markers.items() if not ok]
    if failed:
        raise AssertionError("REFUSED_SOURCE_CONTRACT:" + ",".join(failed))


def selftest(cpp: str, h: str) -> None:
    check(cpp, h)
    mutated = [
        (cpp.replace("kGazelleDeferredStockResearchEnabled = false",
                     "kGazelleDeferredStockResearchEnabled = true"), h),
        (cpp.replace("m_pVideoCodec = CDVDFactoryCodec::CreateVideoCodec(hint, m_processInfo);",
                     "m_pVideoCodec.reset();"), h),
        (cpp.replace("m_gazelleDeferredSince < 500ms", "m_gazelleDeferredSince < 5s"), h),
        (cpp.replace("OMX.gazelle.research", "ignored") + "\n// OMX.gazelle.research", h),
        (cpp, h.replace("bool m_gazelleDeferredStockOpen{false};", "")),
    ]
    for badcpp, badh in mutated:
        try:
            check(badcpp, badh)
        except (AssertionError, ValueError):
            continue
        raise AssertionError("NEGATIVE_MUTATION_ACCEPTED")
    print("GAZELLE_KODI_DEFERRED_OPEN_SOURCE_SELFTEST_PASS negative=5")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[2]
    cpp = (root / CPP).read_text(encoding="utf-8")
    h = (root / HEADER).read_text(encoding="utf-8")
    if args.selftest:
        selftest(cpp, h)
    else:
        check(cpp, h)
        print("GAZELLE_KODI_DEFERRED_OPEN_SOURCE_AUDIT_PASS "
              "feature_enabled=false stock_only=true "
              "first_au_parser=NOT_CONNECTED target_compile=NOT_TESTED "
              "on_device=NOT_TESTED")
if __name__ == "__main__":
    main()
