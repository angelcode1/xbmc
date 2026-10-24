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
        "kodi_message_bridge_compiled_but_unwired":
            '#include "DVDCodecs/Video/GazelleFELPrecreateKodiBridge.h"' in cpp
            and "GazelleFELPrecreateKodi::ObserveOriginal(" not in cpp
            and "GazelleFELPrecreateKodi::BorrowInfo(" not in cpp,
        "candidate_without_implicit_fel":
            "hint.dovi.dv_profile == 7" in cpp
            and "hint.dovi.el_present_flag != 0" in cpp
            and "hint.cryptoSession" in cpp
            and "hint.dvd" in cpp
            and "hint.stills" in cpp,
        "initial_stream_factory_preserved": False,
        "initial_feature_hard_disabled":
            "constexpr bool kDeferredStockResearchEnabled = false;" in policy
            and "UseDeferredInitialStock(const DeferredStockInputs& v)" in policy
            and "static_assert(!UseDeferredInitialStock(" in policy,
        "stock_only_worker_factory":
            "m_pVideoCodec = CDVDFactoryCodec::CreateVideoCodec(hint, m_processInfo);" in cpp,
        "worker_state_declared":
            "bool m_gazelleDeferredStockOpen{false};" in h,
        "timeout_deadline":
            "m_gazelleDeferredSince < 500ms" in cpp,
        "packet_guard_before_codec_call":
            "if (m_gazelleDeferredStockOpen && !GazelleEnsureDeferredStockCodec())" in cpp
            and "DemuxPacket* pPacket =" in cpp,
        "flush_guard": False,
        "reset_guard": False,
        "stock_only_no_alias":
            "OMX.gazelle.research" not in cpp
            and "GAZELLE_FEL_ENABLE" not in cpp,
        "worker_message_passes_defer_flag":
            "OpenStream(msg->m_hints, std::move(msg->m_codec), msg->m_gazelleDeferred);" in cpp,
    }
    # Initial OpenStream must make a distinct source-verified, disabled
    # scheduling decision BEFORE the first stock factory and BEFORE Init/Create.
    # No decoder alias or prior packet ownership is authorized by this path.
    init_open = cpp.find("bool CVideoPlayerVideo::OpenStream(CDVDStreamInfo hint)")
    init_impl = cpp.find("void CVideoPlayerVideo::OpenStream(CDVDStreamInfo& hint,", init_open)
    initial_method = cpp[init_open:init_impl] if 0 <= init_open < init_impl else ""
    initial_else = initial_method.find("const bool gazelleDeferredInitial")
    guard_initial = initial_method.find("if (!gazelleDeferredInitial)")
    first_factory = initial_method.find("codec = CDVDFactoryCodec::CreateVideoCodec(hint, m_processInfo);", initial_else)
    handoff = initial_method.find("OpenStream(hint, std::move(codec), gazelleDeferredInitial);", initial_else)
    queue_init = initial_method.find("m_messageQueue.Init();", initial_else)
    worker_create = initial_method.find("Create();", initial_else)
    guards["initial_stream_factory_preserved"] = (
        "IsGazelleDeferredStockCandidate(hint, false)" in initial_method
        and "IsGazelleDeferredStockCandidate(hint, true)" in initial_method
        and min(initial_else, guard_initial, first_factory, handoff, queue_init, worker_create) >= 0
        and initial_else < guard_initial < first_factory < handoff < queue_init < worker_create
        and "if (!codec && !gazelleDeferredInitial)" in initial_method
    )
    # In the dormant worker, flush/reset must not create a decoder before
    # a fresh post-seek AU. Both paths can reset the timeout without any codec.
    reset_a = cpp.find("else if (pMsg->IsType(CDVDMsg::GENERAL_RESET))")
    flush_a = cpp.find("else if (pMsg->IsType(CDVDMsg::GENERAL_FLUSH))", reset_a)
    speed_a = cpp.find("else if (pMsg->IsType(CDVDMsg::PLAYER_SETSPEED))", flush_a)
    reset_body = cpp[reset_a:flush_a] if 0 <= reset_a < flush_a else ""
    flush_body = cpp[flush_a:speed_a] if 0 <= flush_a < speed_a else ""
    rearm = ("if (m_gazelleDeferredStockOpen)\n"
             "        m_gazelleDeferredSince = std::chrono::steady_clock::now();")
    guards["reset_guard"] = (
        rearm in reset_body
        and "GazelleEnsureDeferredStockCodec(" not in reset_body
        and "m_packets.clear();" in reset_body
    )
    guards["flush_guard"] = (
        rearm in flush_body
        and "GazelleEnsureDeferredStockCodec(" not in flush_body
        and "FlushMessages();" in flush_body
    )
    # Read-only RPU probe MUST happen before a STOCK factory can touch input.
    packet_begin = cpp.find("else if (pMsg->IsType(CDVDMsg::DEMUXER_PACKET))")
    packet_section = cpp[packet_begin:] if packet_begin >= 0 else ""
    probe_at = packet_section.find("GazelleFEL::InspectFirstAU(")
    stock_at = packet_section.find("if (!GazelleEnsureDeferredStockCodec())")
    original_at = packet_section.find("DemuxPacket* pPacket =")
    use_at = packet_section.find("m_pVideoCodec->SetCodecControl(codecControl);")
    guards["packet_guard_before_codec_call"] = (
        min(probe_at, stock_at, original_at, use_at) >= 0
        and probe_at < stock_at < original_at < use_at
    )
    guards["probe_in_real_worker_but_disabled"] = (
        '#include "utils/GazelleFELPrecreateProbe.h"' in cpp
        and 'm_hints.extradata.GetData()' in packet_section
        and 'original->cryptoInfo != nullptr' in packet_section
        and 'static_cast<bool>(m_hints.cryptoSession)' in packet_section
    )
    # Kodi's actual DVDDemuxFFmpeg marks BL and EL as separate messages
    # (isDualStream/isELPackage). MediaCodec pairs them only AFTER opening.
    # The dormant first-AU probe reads only one packet, so it MUST NOT
    # authenticate a split P7 pair or imply complete FEL pre-create.
    guards["split_layer_packets_refused_precreate"] = (
        "if (original && !pending->GetPacketDrop() && original->iSize > 0 &&\n"
        "            !original->isDualStream && !original->isELPackage)" in packet_section
        and "GazelleFEL::InspectFirstAU(" in packet_section
    )
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
        (cpp.replace("DVDCodecs/Video/GazelleFELPrecreateKodiBridge.h",
                     "DVDCodecs/Video/GazelleFELPrecreateMissing.h"), h, policy),
        (cpp + "\n// GazelleFELPrecreateKodi::ObserveOriginal(bridge, packet, epoch, protected);\n",
         h, policy),
        (cpp.replace("GazelleFEL::InspectFirstAU(", "GazelleFEL::InspectMissingAU("),
         h, policy),
        (cpp.replace("IsGazelleDeferredStockCandidate(hint, false)",
                     "IsGazelleDeferredStockCandidate(hint, true)"), h, policy),
        (cpp.replace("OpenStream(hint, std::move(codec), gazelleDeferredInitial);",
                     "OpenStream(hint, std::move(codec));"), h, policy),
        (cpp, h, policy.replace("UseDeferredInitialStock(const DeferredStockInputs& v)",
                                "UseDeferredInitialCodec(const DeferredStockInputs& v)")),
        (cpp.replace("!original->isDualStream && !original->isELPackage",
                     "true && !original->isELPackage"), h, policy),
        (cpp.replace("!original->isDualStream && !original->isELPackage",
                     "!original->isDualStream && true"), h, policy),
        (cpp.replace(
            "else if (pMsg->IsType(CDVDMsg::GENERAL_RESET))",
            "else if (pMsg->IsType(CDVDMsg::GENERAL_NEVER_RESET))"), h, policy),
        (cpp.replace(
            "else if (pMsg->IsType(CDVDMsg::GENERAL_FLUSH))",
            "else if (pMsg->IsType(CDVDMsg::GENERAL_NEVER_FLUSH))"), h, policy),
    ]
    for a, b, c in variants:
        try:
            check(a, b, c)
        except AssertionError:
            continue
        raise AssertionError("NEGATIVE_MUTATION_ACCEPTED")
    print("GAZELLE_KODI_DEFERRED_OPEN_SOURCE_SELFTEST_PASS negative=19 no_device=true")


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
              "feature_enabled=false stock_only=true first_au_parser=STAGED_DISABLED_REAL_RUNTIME_NOT_TESTED "
              "full_kodi_build=NOT_TESTED on_device=NOT_TESTED")


if __name__ == "__main__":
    main()
