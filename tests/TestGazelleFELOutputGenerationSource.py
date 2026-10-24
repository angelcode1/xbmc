#!/usr/bin/env python3
"""Fail-closed source audit of a deliberately UNWIRED output-generation model.

Checks are structural only. They do NOT attest to real JNI quiescence,
codec callbacks, kernel/firmware work completion or renderer retirement.
Pass --header-only to run in the downloadable self-contained package.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELOutputGenerationFence.h"
WORKER = ROOT / "xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp"
CODEC = ROOT / "xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp"


def check(model: str, worker: str | None = None, codec: str | None = None) -> None:
    gates = {
        "nondeployable_banner": "OFFLINE, HOST-ONLY MODEL" in model,
        "buffer_incarnation": "ticket.decoder != m_decoder" in model,
        "buffer_generation": "ticket.generation != m_generation" in model,
        "unique_ticket_serial": "lhs.serial == rhs.serial" in model,
        "operation_token": "slot->operation != permit.operation" in model,
        "freeze_release_at_seek": "m_phase = Phase::FlushPending;" in model,
        "flush_waits_for_native_releases":
            "m_phase != Phase::FlushPending || OperationsInFlightLocked()" in model,
        "seek_only_after_jni": "m_phase = Phase::AwaitRetirement;" in model,
        "held_renderer_owner_gate": "OutstandingLocked() != 0" in model,
        "full_barrier_gate": "m_rendererVerified && !OperationsInFlightLocked() &&" in model
                             and "OutstandingLocked() == 0" in model,
        "closed_inflight_poison": "if (OperationsInFlightLocked())\n      m_poisoned = true;" in model,
        "jni_error_poison": "if (!jniSucceeded)" in model
                            and "m_phase = Phase::Faulted;" in model,
        "no_output_counter_reset": "m_slots = {}" not in model,
        "native_work_outside_mutex": "BeginRelease(const Ticket& ticket)" in model
                                    and "FinishRelease(const ReleasePermit& permit" in model
                                    and "BeginNativeFlush()" in model
                                    and "FinishNativeFlush(const FlushPermit& permit" in model,
        "no_real_jni": "#include <jni" not in model and "xbmc_jnienv()" not in model,
    }
    if worker is not None and codec is not None:
        gates.update({
            "unwired_worker": "GazelleFELOutputGenerationFence.h" not in worker
                              and "OutputGenerationFence" not in worker,
            "unwired_codec": "GazelleFELOutputGenerationFence.h" not in codec
                             and "OutputGenerationFence" not in codec,
            "existing_kodi_reset": "m_codec->flush();" in codec,
            "existing_renderer_pool": "CMediaCodecVideoBufferPool::Return" in codec,
        })
    failed = [k for k, v in gates.items() if not v]
    if failed:
        raise AssertionError("GAZELLE_OUTPUT_GENERATION_SOURCE_REFUSED " + ",".join(failed))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--header-only", action="store_true")
    args = ap.parse_args()
    model = HEADER.read_text()
    worker = None if args.header_only else WORKER.read_text()
    codec = None if args.header_only else CODEC.read_text()
    check(model, worker, codec)
    mutations = [
        model.replace("ticket.decoder != m_decoder", "false"),
        model.replace("ticket.generation != m_generation", "false"),
        model.replace("lhs.serial == rhs.serial", "true"),
        model.replace("slot->operation != permit.operation", "false"),
        model.replace("m_phase = Phase::FlushPending;", "m_phase = Phase::Running;"),
        model.replace("m_phase != Phase::FlushPending || OperationsInFlightLocked()",
                      "m_phase != Phase::FlushPending"),
        model.replace("m_phase = Phase::AwaitRetirement;", "m_phase = Phase::Running;"),
        model.replace("OutstandingLocked() != 0", "false"),
        model.replace("m_rendererVerified && !OperationsInFlightLocked() &&",
                      "true && !OperationsInFlightLocked() &&"),
        model.replace("if (OperationsInFlightLocked())\n      m_poisoned = true;",
                      "if (false)\n      m_poisoned = true;"),
        model.replace("if (!jniSucceeded)", "if (false)"),
        model.replace("OFFLINE, HOST-ONLY MODEL", "PRODUCTION READY"),
    ]
    assert len(mutations) == 12
    for n, mutant in enumerate(mutations):
        if mutant == model:
            raise AssertionError(f"GAZELLE_MUTATION_NOOP {n}")
        try:
            check(mutant, worker, codec)
        except AssertionError:
            continue
        raise AssertionError(f"GAZELLE_OUTPUT_MUTATION_ACCEPTED {n}")
    if worker is not None and codec is not None:
        for changed_worker, changed_codec in (
            (worker + '\n#include "GazelleFELOutputGenerationFence.h"\n', codec),
            (worker, codec + '\n#include "GazelleFELOutputGenerationFence.h"\n'),
        ):
            try:
                check(model, changed_worker, changed_codec)
            except AssertionError:
                continue
            raise AssertionError("GAZELLE_LIVE_WIRING_MUTATION_ACCEPTED")
    print("GAZELLE_OUTPUT_GENERATION_SOURCE_PASS "
          f"negative={14 if worker is not None else 12} "
          "output_model_unwired=true native_quiescence_unproven=true fel_off=true")

if __name__ == "__main__":
    main()