// SPDX-License-Identifier: GPL-2.0-or-later
// SYNTHETIC host witness state only. No Kodi JNI/MediaCodec/output renderer.
#include "../xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELNativeQuiescenceGate.h"

#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>

using GazelleFELPrecreate::NativeQuiescenceGate;
using GazelleFELPrecreate::QuiescenceStep;

int main()
{
  // A returned C++ input call alone NEVER proves MediaCodec quiescence.
  {
    NativeQuiescenceGate g;
    assert(g.InputStarted(1) && g.NeedsNativeProof());
    assert(!g.BeginFlushProof(2)); // input lease still active
    assert(!g.InputReturned(2));
    assert(g.InputReturned(1));
    assert(g.NeedsNativeProof() && !g.Ready(2) && !g.Consume(2));
    assert(g.BeginFlushProof(2));
    assert(!g.Ready(2));
    assert(g.ReportOutputRetired(2,true,true) == QuiescenceStep::Refused);
    assert(g.ReportNativeFlush(3,true,true) == QuiescenceStep::Refused);
    assert(g.ReportNativeFlush(2,true,true) == QuiescenceStep::Recorded);
    assert(!g.Ready(2)); // flush JNI return != output-pool retirement
    assert(g.TrackOutputAcquire(2) == QuiescenceStep::Recorded);
    assert(g.TrackOutputAcquire(2) == QuiescenceStep::Recorded);
    assert(g.ReportOutputRetired(2,true,true) == QuiescenceStep::Refused);
    assert(g.TrackOutputRelease(2) == QuiescenceStep::Recorded);
    assert(g.ReportOutputRetired(2,true,true) == QuiescenceStep::Refused);
    assert(g.TrackOutputRelease(2) == QuiescenceStep::Recorded);
    assert(g.TrackOutputRelease(2) == QuiescenceStep::Refused);
    assert(!g.Ready(2));
    assert(g.ReportOutputRetired(2,true,true) == QuiescenceStep::Recorded);
    assert(g.Ready(2) && !g.Ready(3));
    assert(g.Consume(2));
    assert(!g.NeedsNativeProof() && !g.Consume(2) && !g.Ready(2));
  }
  // JNI exceptions MUST latch failure, even if later Reset sets local
  // m_state to FLUSHED or someone reports clean output-buffer handles.
  {
    NativeQuiescenceGate g;
    assert(g.InputStarted(10));
    assert(g.InputReturned(10));
    assert(g.BeginFlushProof(11));
    assert(g.ReportNativeFlush(11,true,false) == QuiescenceStep::Failed);
    assert(g.ReportNativeFlush(11,true,true) == QuiescenceStep::Refused);
    assert(g.ReportOutputRetired(11,true,true) == QuiescenceStep::Refused);
    assert(!g.Ready(11) && !g.Consume(11) && g.NeedsNativeProof());
  }
  // Renderer references and pool-detachment evidence are independently
  // required and cannot be inferred from output buffer count reaching 0.
  {
    NativeQuiescenceGate g;
    assert(g.InputStarted(7) && g.InputReturned(7));
    assert(g.BeginFlushProof(8));
    assert(g.ReportNativeFlush(8,true,true) == QuiescenceStep::Recorded);
    assert(g.ReportOutputRetired(8,true,false) == QuiescenceStep::Failed);
    assert(!g.Ready(8));
  }
  {
    NativeQuiescenceGate g;
    assert(g.InputStarted(7) && g.InputReturned(7));
    assert(g.BeginFlushProof(8));
    assert(g.ReportNativeFlush(8,true,true) == QuiescenceStep::Recorded);
    assert(g.ReportOutputRetired(8,false,true) == QuiescenceStep::Failed);
    assert(!g.Ready(8));
  }
  // No epoch zero, cross-epoch, duplicate flush, or UINT64_MAX wrap.
  {
    NativeQuiescenceGate g;
    assert(!g.InputStarted(0));
    assert(g.InputStarted(std::numeric_limits<std::uint64_t>::max()));
    assert(g.InputReturned(std::numeric_limits<std::uint64_t>::max()));
    assert(!g.BeginFlushProof(0));
    assert(!g.BeginFlushProof(1));
    assert(!g.Ready(0));
    g.Close();
    assert(!g.InputStarted(1));
    assert(!g.InputReturned(1));
    assert(!g.BeginFlushProof(2));
  }
  // Host mock can acknowledge a single input and synthetic pool proof
  // before seek applies; the next input starts a new epoch after Consume.
  {
    NativeQuiescenceGate g;
    assert(g.InputStarted(1));
    assert(g.InputReturned(1));
    assert(g.BeginFlushProof(2));
    assert(!g.BeginFlushProof(2));
    assert(g.ReportNativeFlush(2,true,true) == QuiescenceStep::Recorded);
    assert(g.ReportOutputRetired(2,true,true) == QuiescenceStep::Recorded);
    assert(g.Consume(2));
    assert(g.InputStarted(2));
    assert(g.InputReturned(2));
    assert(!g.BeginFlushProof(2));
    assert(g.BeginFlushProof(3));
    assert(!g.Ready(3));
    g.Close();
    assert(!g.Ready(3));
  }
  std::cout << "GAZELLE_NATIVE_QUIESCENCE_HOST_PASS "
               "input_return_insufficient=true jni_flush_separate=true "
               "output_pool_and_renderer_required=true "
               "output_reference_counted=true jni_error_latched=true "
               "epoch_wrap_refused=true no_real_jni=true "
               "no_decoder_quiescence_proven=true fel_disabled=true\n";
}
