// SPDX-License-Identifier: GPL-2.0-or-later
// Synthetic HOST test. No real JNI, MediaCodec, native quiescence or Cube.
#include "../xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELOutputGenerationFence.h"
#include <atomic>
#include <cassert>
#include <cstdint>
#include <future>
#include <iostream>
#include <limits>
#include <thread>
#include <vector>
using Fence = GazelleFELPrecreate::OutputGenerationFence;
using Decision = Fence::Decision;
using Phase = Fence::Phase;

int main()
{
  // Flush must not invalidate while JNI release operation is still active;
  // seek publication is nonblocking, JNI call runs outside fence mutex.
  {
    Fence f;
    assert(f.OpenFirst());
    auto held = f.Acquire(4); assert(held);
    auto begin = f.BeginRelease(*held);
    assert(begin.decision == Decision::Granted && begin.permit);
    std::promise<void> entered, release;
    auto releaseFuture = release.get_future().share();
    std::atomic<bool> finished{false};
    std::thread native([&] {
      entered.set_value();
      releaseFuture.wait(); // synthetic blocking external JNI call
      assert(f.FinishRelease(*begin.permit, true));
      finished = true;
    });
    entered.get_future().wait();
    assert(f.RequestFlush(2) && !finished);
    assert(f.CurrentPhase() == Phase::FlushPending);
    assert(!f.BeginNativeFlush());
    assert(f.BeginRelease(*held).decision == Decision::Busy);
    assert(!f.RequestFlush(3)); // second seek refused until resolved
    release.set_value(); native.join();
    assert(f.Outstanding() == 0);
    auto permit = f.BeginNativeFlush(); assert(permit);
    assert(!f.Ready(2));
    assert(f.FinishNativeFlush(*permit, true, true));
    assert(!f.Ready(2)); // JNI flush return != pool retirement
    assert(f.ReportRendererRetired(2, true, true));
    assert(f.Ready(2) && !f.Ready(3));
    assert(f.Acknowledge(2));
    assert(!f.Acknowledge(2));
    assert(f.Generation() == 2);
  }
  // Stale output handle MUST NOT release its recycled numeric buffer index.
  {
    Fence f; assert(f.OpenFirst());
    auto old = f.Acquire(7); assert(old);
    assert(f.RequestFlush(10));
    assert(f.BeginRelease(*old).decision == Decision::Stale);
    auto flushing = f.BeginNativeFlush(); assert(flushing);
    assert(f.RetireStaleWithoutJNI(*old) == Decision::Stale); // retirement can happen during native flush
    assert(!f.FinishNativeFlush(Fence::FlushPermit{99,99,99,99},true,true));
    assert(f.FinishNativeFlush(*flushing,true,true));
    assert(f.Outstanding() == 0);
    assert(f.ReportRendererRetired(10,true,true));
    assert(f.Acknowledge(10));
    auto newer = f.Acquire(7); assert(newer);
    assert(newer->index == old->index && newer->serial != old->serial &&
           newer->generation != old->generation);
    assert(f.BeginRelease(*old).decision == Decision::Invalid);
    assert(f.RetireStaleWithoutJNI(*old) == Decision::Invalid);
    assert(f.RetireStaleWithoutJNI(*newer) == Decision::Refused);
    auto release = f.BeginRelease(*newer); assert(release.permit);
    assert(!f.FinishRelease(Fence::ReleasePermit{*newer, 999},true));
    assert(f.FinishRelease(*release.permit,true));
    assert(!f.FinishRelease(*release.permit,true));
  }
  // A late renderer return may arrive after flush returned, not only before.
  {
    Fence f; assert(f.OpenFirst());
    auto old = f.Acquire(8); assert(old);
    assert(f.RequestFlush(5));
    auto flushing = f.BeginNativeFlush(); assert(flushing);
    assert(f.FinishNativeFlush(*flushing,true,true));
    assert(!f.Ready(5));
    assert(!f.ReportRendererRetired(5,true,true));
    assert(f.BeginRelease(*old).decision == Decision::Stale);
    assert(f.RetireStaleWithoutJNI(*old) == Decision::Stale);
    assert(f.RetireStaleWithoutJNI(*old) == Decision::Invalid);
    assert(f.ReportRendererRetired(5,true,true) && f.Acknowledge(5));
  }
  // Stop + recreation has a new decoder ID, even if the OEM recycles 7;
  // held frames of old instance cannot be released against new codec.
  {
    Fence f; assert(f.OpenFirst());
    auto old = f.Acquire(7); assert(old);
    f.Close(); assert(!f.ReopenAfterStop());
    assert(f.BeginRelease(*old).decision == Decision::Stale);
    assert(f.ReportStop(true,true)); assert(f.ReopenAfterStop());
    auto newer = f.Acquire(7); assert(newer);
    assert(newer->decoder != old->decoder);
    assert(f.BeginRelease(*old).decision == Decision::Stale);
    assert(f.RequestFlush(6));
    auto flushing = f.BeginNativeFlush(); assert(flushing);
    assert(f.FinishNativeFlush(*flushing,true,true));
    assert(!f.ReportRendererRetired(6,true,true)); // old + new holders
    assert(f.RetireStaleWithoutJNI(*old) == Decision::Stale);
    assert(f.RetireStaleWithoutJNI(*newer) == Decision::Stale);
    assert(f.ReportRendererRetired(6,true,true) && f.Ready(6));
    assert(f.Acknowledge(6));
  }
  // An unsafe close (native operation in flight) never yields a new
  // decoder incarnation on the same fence, even after op returns.
  {
    Fence f; assert(f.OpenFirst());
    auto old = f.Acquire(3); assert(old);
    auto permit = f.BeginRelease(*old); assert(permit.permit);
    f.Close();
    assert(!f.ReportStop(true,true));
    assert(f.FinishRelease(*permit.permit,true));
    assert(!f.ReportStop(true,true));
    assert(!f.ReopenAfterStop());
  }
  // Fail-closed error, incorrect witness, duplicate and epoch regressions.
  {
    Fence f; assert(f.OpenFirst());
    assert(!f.RequestFlush(0));
    assert(f.RequestFlush(2));
    assert(!f.RequestFlush(2));
    auto permit = f.BeginNativeFlush(); assert(permit);
    assert(f.FinishNativeFlush(*permit,false,true));
    assert(!f.Ready(2) && !f.Acknowledge(2));
    assert(!f.FinishNativeFlush(*permit,true,true));
    assert(!f.ReportRendererRetired(2,true,true));
    assert(!f.RequestFlush(3));
  }
  {
    Fence f; assert(f.OpenFirst());
    assert(f.RequestFlush(2));
    auto permit = f.BeginNativeFlush(); assert(permit);
    assert(f.FinishNativeFlush(*permit,true,true));
    assert(!f.ReportRendererRetired(2,false,true));
    assert(!f.Ready(2));
  }
  {
    Fence f; assert(f.OpenFirst());
    auto held = f.Acquire(3); assert(held);
    auto release = f.BeginRelease(*held); assert(release.permit);
    assert(!f.FinishRelease(Fence::ReleasePermit{*held,99},true));
    assert(f.FinishRelease(*release.permit,false));
    assert(!f.RequestFlush(1));
  }
  // Composite barrier is an AND of THREE independent duties; output
  // success cannot stand in for the original input lease or native proof.
  {
    Fence f; assert(f.OpenFirst());
    bool inputLeaseFinished = false;
    bool nativeDecoderWitness = false;
    assert(f.RequestFlush(44));
    auto flush = f.BeginNativeFlush(); assert(flush);
    assert(f.FinishNativeFlush(*flush,true,true));
    assert(f.ReportRendererRetired(44,true,true));
    const auto mayApply = [&] {
      return inputLeaseFinished && nativeDecoderWitness && f.Ready(44);
    };
    assert(!mayApply());
    inputLeaseFinished = true;
    assert(!mayApply());
    nativeDecoderWitness = true; // SYNTHETIC ONLY
    assert(mayApply() && f.Acknowledge(44));
  }
  // A close overlapping an unfinished MediaCodec.flush() is unresolved.
  {
    Fence f; assert(f.OpenFirst());
    assert(f.RequestFlush(1));
    auto flush=f.BeginNativeFlush(); assert(flush);
    f.Close();
    assert(!f.ReportStop(true,true) && !f.ReopenAfterStop());
    assert(!f.FinishNativeFlush(*flush,true,true));
    assert(!f.Ready(1));
  }
  // Capacity, duplicate index, generation/token/decoder wrap refusal.
  {
    Fence f; assert(f.OpenFirst());
    std::vector<Fence::Ticket> handles;
    for(int i=0;i<static_cast<int>(Fence::kMaxOutstanding);++i)
    {
      auto h=f.Acquire(i); assert(h); handles.push_back(*h);
    }
    assert(!f.Acquire(100)); assert(!f.Acquire(0));
    assert(f.RequestFlush(2));
    auto flush=f.BeginNativeFlush(); assert(flush);
    assert(f.FinishNativeFlush(*flush,true,true));
    for (const auto& h: handles)
      assert(f.RetireStaleWithoutJNI(h)==Decision::Stale);
    assert(f.ReportRendererRetired(2,true,true));
    assert(f.Acknowledge(2));
    assert(!f.RequestFlush(2));
  }
  {
    constexpr auto max = std::numeric_limits<std::uint64_t>::max();
    Fence tickets(max,1,1,1); assert(tickets.OpenFirst());
    assert(!tickets.Acquire(1));
    Fence operations(1,max,1,1); assert(operations.OpenFirst());
    auto h=operations.Acquire(1); assert(h);
    assert(operations.BeginRelease(*h).decision==Decision::Refused);
    assert(operations.RequestFlush(1));
    assert(!operations.BeginNativeFlush());
    Fence decoder(1,1,max,1); assert(!decoder.OpenFirst());
    Fence generation(1,1,1,max); assert(!generation.OpenFirst());
    Fence nearGen(1,1,1,max-1); assert(nearGen.OpenFirst());
    assert(nearGen.RequestFlush(1));
    auto fp=nearGen.BeginNativeFlush(); assert(fp);
    assert(nearGen.FinishNativeFlush(*fp,true,true));
    assert(nearGen.ReportRendererRetired(1,true,true));
    assert(!nearGen.Acknowledge(1)); // cannot wrap generation
  }
  std::cout << "GAZELLE_OUTPUT_GENERATION_HOST_PASS "
               "stale_index_never_released=true blocking_jni_outside_mutex=true "
               "held_renderer_ref_blocks_barrier=true reused_index_isolated=true "
               "decoder_recreation_isolated=true release_error_latched=true "
               "flush_error_latched=true strict_sequential_seeks=true "
               "wrap_refused=true output_capacity_bounded=true "
               "host_model_only=true no_device=true fel_off=true\n";
}