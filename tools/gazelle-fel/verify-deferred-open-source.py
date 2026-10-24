#!/usr/bin/env python3
"""Fail-closed source checks for the NON-DEPLOYABLE Kodi deferred-open scaffold.

Checks the actual VideoPlayerVideo.cpp plus the compiled shared header.
Not an Android build, libdovi integration, or Kodi lifecycle proof.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CPP = Path("xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp")
HEADER = Path("xbmc/cores/VideoPlayer/VideoPlayerVideo.h")
POLICY = Path("xbmc/cores/VideoPlayer/GazelleDeferredOpenPolicy.h")


def check(cpp: str, h: str, policy: str) -> None:
    guards = {
        "disabled_shared_policy":
            "constexpr bool kDeferredStockResearchEnabled = false;" in policy
            and "constexpr bool kDeferredStockResearchEnabled = true;" not in policy,
        "compile_time_assert_disabled":
            'static_assert(!kDeferredStockResearchEnabled' in policy,
        "worker_imports_compiled_policy":
            '#include "GazelleDeferredOpenPolicy.h"' in cpp
            and "KODI::VIDEO::GAZELLE::UseDeferredStock(inputs)" in cpp,
        "candidate_without_implicit_fel":
            "hint.dovi.dv_profile == 7" in cpp
            and "hint.dovi.el_present_flag != 0" in cpp
            and "hint.cryptoSession" in cpp
            and "hint.dvd" in cpp
            and "hint.stills" in cpp,
        "initial_stream_factory_preserved":
            "std::unique_ptr<CDVDVideoCodec> codec = CDVDFactoryCodec::CreateVideoCodec(hint, m_processInfo);" in cpp,
        "stock_only_worker_factory":
            "m_pVideoCodec = CDVDFactoryCodec::CreateVideoCodec(hint, m_processInfo);" in cpp,
        "worker_state_declared":
            "bool m_gazelleDeferredStockOpen{false};" in h,
        "timeout_deadline":
            "m_gazelleDeferredSince < 500ms" in cpp,
        "packet_guard_before_codec_call":
            "if (m_gazelleDeferredStockOpen && !GazelleEnsureDeferredStockCodec())" in cpp
            and "DemuxPacket* pPacket =" in cpp,
        "flush_guard":
            "if (m_gazelleDeferredStockOpen && !GazelleEnsureDeferredStockCodec())" in cpp
            and "CDVDMsg::GENERAL_FLUSH" in cpp,
        "reset_guard":
            "CDVDMsg::GENERAL_RESET" in cpp,
        "stock_only_no_alias":
            "OMX.gazelle.research" not in cpp
            and "GAZELLE_FEL_ENABLE" not in cpp,
        "worker_message_passes_defer_flag":
            "OpenStream(msg->m_hints, std::move(msg->m_codec), msg->m_gazelleDeferred);" in cpp,
    }
    packet_gate = (
        "if (m_gazelleDeferredStockOpen && !GazelleEnsureDeferredStockCodec())\n"
        "        continue;\n"
        "      DemuxPacket* pPacket ="
    )
    if packet_gate in cpp and "m_pVideoCodec->SetCodecControl(codecControl);" in cpp:
        guards["packet_guard_before_codec_call"] &= (
            cpp.index(packet_gate) < cpp.index("m_pVideoCodec->SetCodecControl(codecControl);")
        )
    else:
        guards["packet_guard_before_codec_call"] = False
    timeout_gate = "if (m_gazelleDeferredStockOpen)\n      {"
    output_check = "if (m_outputSate == OUTPUT_AGAIN &&"
    guards["timeout_before_output"] = (
        timeout_gate in cpp and output_check in cpp
        and cpp.index(timeout_gate) < cpp.index(output_check)
    )
    helper_start = cpp.find("bool CVideoPlayerVideo::GazelleEnsureDeferredStockCodec()")
    helper_end = cpp.find("void CVideoPlayerVideo::CloseStream(", helper_start)
    helper = cpp[helper_start:helper_end] if helper_start >= 0 and helper_end > helper_start else ""
    guards["helper_never_joins_own_worker"] = (
        bool(helper) and "m_bStop = true;" in helper
        and "StopThread();" not in helper
    )
    failed = [key for key, ok in guards.items() if not ok]
    if failed:
        raise AssertionError("GAZELLE_SOURCE_GATE_REFUSED " + ",".join(failed))


def selftest(cpp: str, h: str, policy: str) -> None:
    check(cpp, h, policy)
    variants = [
        (cpp, h, policy.replace("kDeferredStockResearchEnabled = false",
                                "kDeferredStockResearchEnabled = true")),
        (cpp, h, policy.replace("static_assert(!kDeferredStockResearchEnabled",
                                "static_assert(kDeferredStockResearchEnabled")),
        (cpp.replace("KODI::VIDEO::GAZELLE::UseDeferredStock(inputs)", "false"), h, policy),
        (cpp.replace("m_pVideoCodec = CDVDFactoryCodec::CreateVideoCodec(hint, m_processInfo);",
                     "m_pVideoCodec.reset();"), h, policy),
        (cpp.replace("m_gazelleDeferredSince < 500ms", "m_gazelleDeferredSince < 5s"), h, policy),
        (cpp.replace("GazelleDeferredOpenPolicy.h", "GazelleDeferredOpenPolicyMissing.h"), h, policy),
        (cpp, h.replace("bool m_gazelleDeferredStockOpen{false};", ""), policy),
        (cpp + "\n// OMX.gazelle.research\n", h, policy),
        (cpp.replace("m_bStop = true;\n  return false;", "StopThread();\n  return false;"),
         h, policy),
    ]
    for a, b, c in variants:
        try:
            check(a, b, c)
        except AssertionError:
            continue
        raise AssertionError("NEGATIVE_MUTATION_ACCEPTED")
    print("GAZELLE_KODI_DEFERRED_OPEN_SOURCE_SELFTEST_PASS negative=9 no_device=true")


def main() -> None:
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("--selftest", action="store_true")
    args = arg.parse_args()
    cpp = (ROOT / CPP).read_text(encoding="utf-8")
    h = (ROOT / HEADER).read_text(encoding="utf-8")
    policy = (ROOT / POLICY).read_text(encoding="utf-8")
    if args.selftest:
        selftest(cpp, h, policy)
    else:
        check(cpp, h, policy)
        print("GAZELLE_KODI_DEFERRED_OPEN_SOURCE_AUDIT_PASS "
              "feature_enabled=false stock_only=true first_au_parser=NOT_CONNECTED "
              "full_kodi_build=NOT_TESTED on_device=NOT_TESTED")


if __name__ == "__main__":
    main()
