#!/usr/bin/env python3
"""Fail-closed source audit of Kodi MediaCodec reset/output lifetime.

This does NOT assert that Android JNI flush quiesces a real decoder. It
ensures the opposite: Kodi's actual source exhibits multiple independently
managed input/flush/output paths, and experimental host witness models
remain outside the live worker/MediaCodec implementation.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT / "xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp"
WORKER = ROOT / "xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp"
MODEL = ROOT / "xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELNativeQuiescenceGate.h"


def verify(codec: str, worker: str, model: str) -> None:
    reset_start = codec.find("void CDVDVideoCodecAndroidMediaCodec::Reset()")
    reset_end = codec.find("CDVDVideoCodec::VCReturn CDVDVideoCodecAndroidMediaCodec::GetPicture(")
    dispose_start = codec.find("void CDVDVideoCodecAndroidMediaCodec::Dispose()")
    add_start = codec.find("bool CDVDVideoCodecAndroidMediaCodec::AddData(")
    if min(reset_start, reset_end, dispose_start, add_start) < 0:
        raise AssertionError("GAZELLE_CODEC_SOURCE_METHODS_MISSING")
    reset = codec[reset_start:reset_end]
    dispose = codec[dispose_start:reset_start]
    add = codec[add_start:reset_start]
    checks = {
        "native_input_submit_separate":
            "m_codec->queueInputBuffer(" in add
            and "m_codec->queueSecureInputBuffer(" in add,
        "jni_flush_checked_not_enough":
            "m_codec->flush();" in reset
            and "xbmc_jnienv()->ExceptionCheck()" in reset
            and reset.find("m_codec->flush();") <
            reset.find("xbmc_jnienv()->ExceptionCheck()") <
            reset.find("m_state = MEDIACODEC_STATE_FLUSHED;"),
        "state_flushed_even_after_error_branch":
            "flush failed" in reset
            and "m_state = MEDIACODEC_STATE_FLUSHED;" in reset
            and reset.find("flush failed") <
            reset.find("m_state = MEDIACODEC_STATE_FLUSHED;"),
        "output_pool_separate_from_reset":
            "m_videoBufferPool->ResetMediaCodec();" in dispose
            and "m_videoBufferPool->ResetMediaCodec();" not in reset,
        "output_buffers_not_input_lease":
            "m_videoBufferPool->Get()" in codec
            and "m_videoBufferPool->ReleaseMediaCodecBuffers();" in codec
            and "releaseOutputBuffer(" in codec
            and "m_videoBuffers[bufferIdx]->Acquire(shared_from_this())" in codec,
        "witness_model_requires_both":
            "bool jniExceptionFree" in model
            and "bool rendererReferencesReleased" in model
            and "m_flushOkay && m_poolOkay && m_outputObserved" in model,
        "native_proof_unwired":
            "GazelleFELNativeQuiescenceGate.h" not in worker
            and "GazelleFELNativeQuiescenceGate.h" not in codec
            and "BeginNativeFlushProof(" not in worker
            and "ReportRetiredOutputs(" not in worker,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise AssertionError("GAZELLE_CODEC_QUIESCENCE_SOURCE_REFUSED " +
                             ",".join(failed))


def main() -> None:
    codec, worker, model = (
        CODEC.read_text(encoding="utf8"),
        WORKER.read_text(encoding="utf8"),
        MODEL.read_text(encoding="utf8"),
    )
    verify(codec, worker, model)
    mutations = [
        (codec.replace("m_codec->flush();", "m_codec->start();"), worker, model),
        (codec.replace("m_codec->queueInputBuffer(", "m_codec->queueInputX("),
         worker, model),
        (codec.replace("m_videoBufferPool->ResetMediaCodec();",
                       "m_videoBufferPool->CloseUntracked();"), worker, model),
        (codec.replace("m_videoBufferPool->Get()", "m_videoBufferPool->Fake()"),
         worker, model),
        (codec, worker + '\n#include "GazelleFELNativeQuiescenceGate.h"\n',
         model),
        (codec, worker, model.replace("bool jniExceptionFree",
                                     "bool ignoreExceptions")),
        (codec, worker, model.replace("bool rendererReferencesReleased",
                                     "bool ignoreRenderer")),
    ]
    for mutant in mutations:
        try:
            verify(*mutant)
        except AssertionError:
            continue
        raise AssertionError("GAZELLE_CODEC_QUIESCENCE_MUTATION_ACCEPTED")
    print("GAZELLE_MEDIACODEC_QUIESCENCE_SOURCE_PASS negative=7 "
          "jni_flush_not_native_idle=true output_pool_separate=true "
          "no_real_Android_quiescence_witness=true live_worker_unwired=true")


if __name__ == "__main__":
    main()
