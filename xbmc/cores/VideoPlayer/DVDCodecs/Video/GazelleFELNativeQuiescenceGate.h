// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// NON-DEPLOYABLE / OFFLINE host witness model for Android MediaCodec reset.
//
// Kodi MediaCodec::AddData may return after queueInputBuffer, while output
// frame buffers and renderer references can outlive the submitted input.
// Real Reset() calls MediaCodec.flush() and logs JNI errors, but presently
// does not establish this complete witness for our research worker.
// Therefore neither "lease Finished" nor "m_state == FLUSHED" authorizes a
// research seek barrier. No actual JNI, codec, renderer, or device is called.
//
// Witnesses here are SYNTHETIC HOST INPUTS. A real implementation must
// independently prove: (a) input lease ended, (b) native flush returned
// without JNI exception, (c) all tracked output buffer references were
// released, and (d) renderer/buffer-pool retirement explicitly succeeded.
// A fake witness must NEVER be wired into Kodi.
#include <cstddef>
#include <cstdint>
#include <limits>

namespace GazelleFELPrecreate
{
enum class QuiescenceStep : std::uint8_t
{
  Refused,
  Recorded,
  Failed
};

class NativeQuiescenceGate
{
public:
  // Mark when a modeled original input starts: this creates a native-proof
  // debt, even if the caller later releases its packet message reference.
  bool InputStarted(std::uint64_t inputEpoch) noexcept
  {
    if (m_closed || inputEpoch == 0 || m_unsettledInput ||
        m_pendingEvidenceEpoch != 0)
      return false;
    m_inputEpoch = inputEpoch;
    m_unsettledInput = true;
    m_nativeDebt = true;
    return true;
  }

  bool InputReturned(std::uint64_t inputEpoch) noexcept
  {
    if (m_closed || !m_unsettledInput || m_inputEpoch != inputEpoch)
      return false;
    m_unsettledInput = false;
    return true;
  }

  // The pending flush's epoch MUST be the next generation after the
  // submitted input. A newer seek can supersede the old proof; reset is
  // explicit and fail-closed, never evidence of hardware quiescence.
  bool BeginFlushProof(std::uint64_t targetEpoch) noexcept
  {
    if (m_closed || !m_nativeDebt || m_unsettledInput ||
        m_inputEpoch == std::numeric_limits<std::uint64_t>::max() ||
        targetEpoch != m_inputEpoch + 1 ||
        m_pendingEvidenceEpoch != 0)
      return false;
    m_pendingEvidenceEpoch = targetEpoch;
    m_flushOkay = false;
    m_poolOkay = false;
    m_trackedOutputs = 0;
    m_outputObserved = false;
    m_failed = false;
    return true;
  }

  QuiescenceStep TrackOutputAcquire(std::uint64_t targetEpoch) noexcept
  {
    if (!Valid(targetEpoch) || m_outputObserved ||
        m_trackedOutputs == std::numeric_limits<std::size_t>::max())
      return QuiescenceStep::Refused;
    ++m_trackedOutputs;
    return QuiescenceStep::Recorded;
  }

  QuiescenceStep TrackOutputRelease(std::uint64_t targetEpoch) noexcept
  {
    if (!Valid(targetEpoch) || m_outputObserved || m_trackedOutputs == 0)
      return QuiescenceStep::Refused;
    --m_trackedOutputs;
    return QuiescenceStep::Recorded;
  }

  // JNI success must be separately checked by a trustworthy adapter.
  // Passing "true" unconditionally after current Kodi Reset() is INVALID.
  QuiescenceStep ReportNativeFlush(std::uint64_t targetEpoch,
                                   bool callReturned,
                                   bool jniExceptionFree) noexcept
  {
    if (!Valid(targetEpoch) || m_flushOkay)
      return QuiescenceStep::Refused;
    if (!callReturned || !jniExceptionFree)
    {
      m_failed = true;
      return QuiescenceStep::Failed;
    }
    m_flushOkay = true;
    return QuiescenceStep::Recorded;
  }

  // Reports an audited snapshot of Kodi output-buffer AND renderer lifetime.
  // Existing source does not expose a complete production witness.
  QuiescenceStep ReportOutputRetired(std::uint64_t targetEpoch,
                                    bool poolDetached,
                                    bool rendererReferencesReleased) noexcept
  {
    if (!Valid(targetEpoch) || !m_flushOkay || m_outputObserved ||
        m_trackedOutputs != 0)
      return QuiescenceStep::Refused;
    if (!poolDetached || !rendererReferencesReleased)
    {
      m_failed = true;
      return QuiescenceStep::Failed;
    }
    m_poolOkay = true;
    m_outputObserved = true;
    return QuiescenceStep::Recorded;
  }

  bool Ready(std::uint64_t targetEpoch) const noexcept
  {
    return !m_closed && !m_failed && !m_unsettledInput &&
           m_pendingEvidenceEpoch == targetEpoch && targetEpoch != 0 &&
           m_flushOkay && m_poolOkay && m_outputObserved &&
           m_trackedOutputs == 0;
  }

  // This only discharges MODELED input debt for the exact target epoch;
  // there is no actual Android quiescence proof here.
  bool Consume(std::uint64_t targetEpoch) noexcept
  {
    if (!Ready(targetEpoch))
      return false;
    m_nativeDebt = false;
    m_inputEpoch = 0;
    m_pendingEvidenceEpoch = 0;
    m_flushOkay = false;
    m_poolOkay = false;
    m_outputObserved = false;
    return true;
  }

  bool NeedsNativeProof() const noexcept { return m_nativeDebt; }
  void Close() noexcept
  {
    m_closed = true;
    m_failed = true;
  }

private:
  bool Valid(std::uint64_t targetEpoch) const noexcept
  {
    return !m_closed && !m_failed && m_nativeDebt &&
           m_pendingEvidenceEpoch != 0 &&
           m_pendingEvidenceEpoch == targetEpoch;
  }

  std::uint64_t m_inputEpoch{0};
  std::uint64_t m_pendingEvidenceEpoch{0};
  std::size_t m_trackedOutputs{0};
  bool m_unsettledInput{false};
  bool m_nativeDebt{false};
  bool m_flushOkay{false};
  bool m_poolOkay{false};
  bool m_outputObserved{false};
  bool m_failed{false};
  bool m_closed{false};
};
} // namespace GazelleFELPrecreate
