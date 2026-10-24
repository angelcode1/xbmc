// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// OFFLINE, HOST-ONLY MODEL. NEVER include in the live Kodi worker or decoder.
//
// MediaCodec.flush() invalidates earlier dequeued buffer indices, but Kodi
// renderer-held CMediaCodecVideoBuffers can outlive that call. Model the
// *separate* output-index, renderer-reference, and JNI-operation lifetimes.
// A modeled acknowledgment is NOT proof of Android/OMX native quiescence.
// External JNI work MUST take place after these short locked transitions.
// Fail closed: no permit for a stale index, no flush while a release is in
// flight, no barrier with held frames or missing explicit retirement proof.
// All reported JNI/renderer completions in this header are SYNTHETIC inputs.

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <mutex>
#include <optional>

namespace GazelleFELPrecreate
{
class OutputGenerationFence
{
public:
  static constexpr std::size_t kMaxOutstanding = 64;
  enum class Phase : std::uint8_t
  {
    Unopened, Running, FlushPending, FlushInFlight,
    AwaitRetirement, Closed, Faulted
  };
  enum class Decision : std::uint8_t
  {
    Granted, Stale, Busy, Invalid, Full, Refused
  };
  struct Ticket
  {
    std::uint64_t decoder{0};
    std::uint64_t generation{0};
    std::uint64_t serial{0};
    int index{-1};
  };
  struct ReleasePermit
  {
    Ticket ticket{};
    std::uint64_t operation{0};
  };
  struct ReleaseResult
  {
    Decision decision{Decision::Refused};
    std::optional<ReleasePermit> permit{};
  };
  struct FlushPermit
  {
    std::uint64_t decoder{0};
    std::uint64_t generation{0};
    std::uint64_t seekEpoch{0};
    std::uint64_t operation{0};
  };

  // Constructor seeds are for host wrap tests. Not a native runtime API.
  explicit OutputGenerationFence(std::uint64_t nextTicket = 1,
                                 std::uint64_t nextOperation = 1,
                                 std::uint64_t nextDecoder = 1,
                                 std::uint64_t nextGeneration = 1) noexcept
    : m_nextTicket(nextTicket), m_nextOperation(nextOperation),
      m_nextDecoder(nextDecoder), m_nextGeneration(nextGeneration)
  {
  }

  bool OpenFirst() noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    if (m_phase != Phase::Unopened || !AdvanceIdentity())
      return false;
    m_phase = Phase::Running;
    return true;
  }

  // Close does NOT destroy records for frames still held by the renderer.
  // If an external native call is still running, recovery on this fence is
  // refused; destroying and recreating the object is NOT a runtime proof.
  void Close() noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    if (m_phase == Phase::Faulted)
      return;
    if (OperationsInFlightLocked())
      m_poisoned = true;
    m_phase = Phase::Closed;
    m_stopVerified = false;
  }

  bool ReportStop(bool returned, bool jniExceptionFree) noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    if (m_phase != Phase::Closed || m_poisoned || OperationsInFlightLocked())
      return false;
    if (!returned || !jniExceptionFree)
    {
      m_poisoned = true;
      return false;
    }
    // Only a successfully returned native stop invalidates old codec
    // output indices. Closing the model by itself is not such evidence.
    for (auto& slot : m_slots)
      if (slot.live && slot.ticket.decoder == m_decoder)
        slot.invalidated = true;
    m_stopVerified = true;
    return true;
  }

  // Reopening changes BOTH identity and generation. Preexisting tickets
  // remain stale, including if the OEM recycles their numeric buffer index.
  bool ReopenAfterStop() noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    if (m_phase != Phase::Closed || m_poisoned || !m_stopVerified ||
        OperationsInFlightLocked() || !AdvanceIdentity())
      return false;
    m_phase = Phase::Running;
    m_stopVerified = false;
    m_rendererVerified = false;
    m_seekEpoch = 0;
    return true;
  }

  std::optional<Ticket> Acquire(int index) noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    if (m_phase != Phase::Running || index < 0 || m_nextTicket == 0 ||
        m_nextTicket == std::numeric_limits<std::uint64_t>::max())
      return std::nullopt;
    Slot* empty = nullptr;
    for (auto& slot : m_slots)
    {
      if (!slot.live && !empty)
        empty = &slot;
      if (slot.live && slot.ticket.decoder == m_decoder &&
          slot.ticket.generation == m_generation &&
          slot.ticket.index == index)
        return std::nullopt; // same native output index still owned
    }
    if (!empty)
      return std::nullopt;
    const Ticket ticket{m_decoder, m_generation, m_nextTicket++, index};
    *empty = Slot{ticket, true, 0, false};
    return ticket;
  }

  // Caller MUST invoke MediaCodec.releaseOutputBuffer only with a Granted
  // permit and outside this fence's mutex, then FinishRelease once.
  ReleaseResult BeginRelease(const Ticket& ticket) noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    Slot* slot = Lookup(ticket);
    if (!slot)
      return {Decision::Invalid, std::nullopt};
    if (slot->operation)
      return {Decision::Busy, std::nullopt};
    if (m_phase != Phase::Running || slot->invalidated ||
        ticket.decoder != m_decoder || ticket.generation != m_generation)
      return {Decision::Stale, std::nullopt};
    if (!NewOperationAvailable())
      return {Decision::Refused, std::nullopt};
    slot->operation = m_nextOperation++;
    return {Decision::Granted, ReleasePermit{ticket, slot->operation}};
  }

  // An error is NOT equivalent to successful buffer retirement. Error is
  // latched and no flush/barrier may be acknowledged on this fence.
  bool FinishRelease(const ReleasePermit& permit, bool jniSucceeded) noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    Slot* slot = Lookup(permit.ticket);
    if (!slot || permit.operation == 0 ||
        slot->operation != permit.operation)
      return false;
    slot->operation = 0;
    slot->live = false;
    if (!jniSucceeded)
    {
      m_poisoned = true;
      m_phase = Phase::Faulted;
    }
    return true;
  }

  // Late renderer returns can retire indices WITHOUT JNI only AFTER native
  // flush returned without exception, or native stop was independently
  // acknowledged. Seek publication / BeginNativeFlush / Close alone cannot
  // invalidate an output: doing so before a native response could hide an
  // owner still belonging to the active codec. This operation models receipt
  // of the genuine final renderer-owner return, NOT cancellation of a live
  // renderer reference. No production renderer callback is wired here.
  Decision RetireStaleWithoutJNI(const Ticket& ticket) noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    Slot* slot = Lookup(ticket);
    if (!slot)
      return Decision::Invalid;
    if (slot->operation)
      return Decision::Busy;
    if (!slot->invalidated ||
        (m_phase == Phase::Running && ticket.decoder == m_decoder &&
         ticket.generation == m_generation))
      return Decision::Refused;
    slot->live = false;
    return Decision::Stale;
  }

  // First transition freezes new native-release admissions. Existing JNI
  // release calls finish outside the lock; the producer needn't await them.
  bool RequestFlush(std::uint64_t seekEpoch) noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    if (m_phase != Phase::Running || seekEpoch == 0 ||
        seekEpoch <= m_lastSeekEpoch || m_poisoned)
      return false;
    m_phase = Phase::FlushPending;
    m_seekEpoch = seekEpoch;
    m_rendererVerified = false;
    return true;
  }

  std::optional<FlushPermit> BeginNativeFlush() noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    if (m_phase != Phase::FlushPending || OperationsInFlightLocked() ||
        !NewOperationAvailable())
      return std::nullopt;
    m_flushOperation = m_nextOperation++;
    m_phase = Phase::FlushInFlight;
    return FlushPermit{m_decoder, m_generation, m_seekEpoch, m_flushOperation};
  }

  bool FinishNativeFlush(const FlushPermit& permit,
                         bool returned, bool jniExceptionFree) noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    if (m_phase != Phase::FlushInFlight || !m_flushOperation ||
        m_flushOperation != permit.operation ||
        permit.decoder != m_decoder || permit.generation != m_generation ||
        permit.seekEpoch != m_seekEpoch)
      return false;
    m_flushOperation = 0;
    if (!returned || !jniExceptionFree)
    {
      m_poisoned = true;
      m_phase = Phase::Faulted;
      return true; // recorded failure, NOT a success acknowledgment
    }
    // Android's documented MediaCodec.flush contract invalidates old
    // indices only upon successful return. Renderer references still exist;
    // invalidation is NOT owner retirement or hardware quiescence.
    for (auto& slot : m_slots)
      if (slot.live && slot.ticket.decoder == m_decoder &&
          slot.ticket.generation == m_generation)
        slot.invalidated = true;
    m_phase = Phase::AwaitRetirement;
    return true;
  }

  // Synthetic external proof: the renderer/pool is retired in addition to
  // all observed Ticket references being gone. Current Kodi cannot report
  // this complete witness. Call only after a successful flush return.
  bool ReportRendererRetired(std::uint64_t seekEpoch,
                             bool poolDetached,
                             bool rendererReferencesReleased) noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    if (m_phase != Phase::AwaitRetirement || seekEpoch != m_seekEpoch ||
        m_rendererVerified || OutstandingLocked() != 0)
      return false;
    if (!poolDetached || !rendererReferencesReleased)
    {
      m_poisoned = true;
      m_phase = Phase::Faulted;
      return false;
    }
    m_rendererVerified = true;
    return true;
  }

  bool Ready(std::uint64_t seekEpoch) const noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    return ReadyLocked(seekEpoch);
  }

  // Model only. Does not assert MediaCodec quiescence, successful rendering,
  // or that an actual Kodi GENERAL_FLUSH was run. Requires separate input
  // lease and native-quiescence witness from the existing host model.
  bool Acknowledge(std::uint64_t seekEpoch) noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    if (!ReadyLocked(seekEpoch) || m_nextGeneration == 0 ||
        m_nextGeneration == std::numeric_limits<std::uint64_t>::max())
      return false;
    m_lastSeekEpoch = seekEpoch;
    m_seekEpoch = 0;
    m_generation = m_nextGeneration++;
    m_rendererVerified = false;
    m_phase = Phase::Running;
    return true;
  }

  Phase CurrentPhase() const noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    return m_phase;
  }
  std::size_t Outstanding() const noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    return OutstandingLocked();
  }
  std::uint64_t Generation() const noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    return m_generation;
  }
  std::uint64_t Decoder() const noexcept
  {
    std::lock_guard<std::mutex> hold(m_mutex);
    return m_decoder;
  }

private:
  struct Slot
  {
    Ticket ticket{};
    bool live{false};
    std::uint64_t operation{0};
    bool invalidated{false};
  };
  static bool Same(const Ticket& lhs, const Ticket& rhs) noexcept
  {
    return lhs.decoder == rhs.decoder &&
           lhs.generation == rhs.generation &&
           lhs.serial == rhs.serial && lhs.index == rhs.index &&
           lhs.serial != 0;
  }
  Slot* Lookup(const Ticket& ticket) noexcept
  {
    for (auto& slot : m_slots)
      if (slot.live && Same(slot.ticket, ticket))
        return &slot;
    return nullptr;
  }
  bool AdvanceIdentity() noexcept
  {
    constexpr auto max = std::numeric_limits<std::uint64_t>::max();
    if (m_nextDecoder == 0 || m_nextDecoder == max ||
        m_nextGeneration == 0 || m_nextGeneration == max)
      return false;
    m_decoder = m_nextDecoder++;
    m_generation = m_nextGeneration++;
    return true;
  }
  bool NewOperationAvailable() const noexcept
  {
    return m_nextOperation != 0 &&
           m_nextOperation != std::numeric_limits<std::uint64_t>::max();
  }
  bool OperationsInFlightLocked() const noexcept
  {
    if (m_flushOperation)
      return true;
    for (const auto& slot : m_slots)
      if (slot.live && slot.operation)
        return true;
    return false;
  }
  std::size_t OutstandingLocked() const noexcept
  {
    std::size_t count = 0;
    for (const auto& slot : m_slots)
      if (slot.live)
        ++count;
    return count;
  }
  bool ReadyLocked(std::uint64_t seekEpoch) const noexcept
  {
    return !m_poisoned && m_phase == Phase::AwaitRetirement &&
           m_seekEpoch != 0 && seekEpoch == m_seekEpoch &&
           m_rendererVerified && !OperationsInFlightLocked() &&
           OutstandingLocked() == 0;
  }

  mutable std::mutex m_mutex{};
  std::array<Slot, kMaxOutstanding> m_slots{};
  std::uint64_t m_nextTicket{1};
  std::uint64_t m_nextOperation{1};
  std::uint64_t m_nextDecoder{1};
  std::uint64_t m_nextGeneration{1};
  std::uint64_t m_decoder{0};
  std::uint64_t m_generation{0};
  std::uint64_t m_seekEpoch{0};
  std::uint64_t m_lastSeekEpoch{0};
  std::uint64_t m_flushOperation{0};
  bool m_rendererVerified{false};
  bool m_stopVerified{false};
  bool m_poisoned{false};
  Phase m_phase{Phase::Unopened};
};
} // namespace GazelleFELPrecreate