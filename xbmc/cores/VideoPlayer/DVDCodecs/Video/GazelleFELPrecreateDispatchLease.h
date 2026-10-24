// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// OFFLINE ONLY. Cancellable, bounded original-message lease state machine.
//
// A seek can revoke *prepared* original packet owners without any codec
// work. A packet already handed to a potentially blocking decoder is NOT
// safely cancellable merely by invalidating its generation: the owner must
// finish, and the real decoder must be quiesced before a flush may apply.
// This class models that crucial distinction; it DOES NOT perform decode,
// block, flush Kodi, or prove Android decoder cancellation.
//
// NOT thread-safe by itself: the experimental SeekFence serializes all
// operations under the SAME host mutex as producer seek publication.
// Zero payload copy, no PutBack, no raw DemuxPacket rewrapping, no device.
#include "GazelleFELPairing.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <utility>

namespace GazelleFELPrecreate
{
constexpr std::size_t kDispatchSlots = 2;
constexpr std::size_t kDispatchMaxDeclaredBytes =
    kDispatchSlots * GazelleFELPairing::kMaxLayerPacketBytes;

enum class LeasePrepare : std::uint8_t
{
  Prepared, CallerRetains, Invalid, Closed
};

template <class Message>
class DispatchLease
{
public:
  using Owner = std::shared_ptr<Message>;
  struct Started
  {
    std::uint64_t token{0};
    std::uint64_t epoch{0};
    Owner original{};
    explicit operator bool() const noexcept { return token != 0 && !!original; }
  };

  DispatchLease() = default;
  DispatchLease(const DispatchLease&) = delete;
  DispatchLease& operator=(const DispatchLease&) = delete;

  LeasePrepare Prepare(Owner& original, std::uint64_t epoch,
                       std::size_t bytes) noexcept
  {
    if (m_closed)
      return LeasePrepare::Closed;
    if (!original || epoch == 0 || bytes == 0 ||
        bytes > GazelleFELPairing::kMaxLayerPacketBytes)
      return LeasePrepare::Invalid;
    if (m_size >= kDispatchSlots || bytes > kDispatchMaxDeclaredBytes - m_bytes)
      return LeasePrepare::CallerRetains;
    if (auto active = m_activeOwner.lock(); active && active == original)
      return LeasePrepare::CallerRetains;
    for (std::size_t i = 0; i < m_size; ++i)
    {
      if (m_pending[i] == original || m_epochs[i] != epoch)
        return LeasePrepare::CallerRetains;
    }
    m_pending[m_size] = std::move(original);
    m_sizes[m_size] = bytes;
    m_epochs[m_size] = epoch;
    ++m_size;
    m_bytes += bytes;
    return LeasePrepare::Prepared;
  }

  Started Begin(std::uint64_t epoch) noexcept
  {
    if (m_closed || m_activeToken != 0 || m_size == 0 ||
        m_epochs[0] != epoch || m_nextToken == 0)
      return {};
    Started started{};
    started.token = m_nextToken++;
    started.epoch = m_epochs[0];
    started.original = std::move(m_pending[0]);
    m_bytes -= m_sizes[0];
    --m_size;
    if (m_size)
    {
      m_pending[0] = std::move(m_pending[1]);
      m_sizes[0] = m_sizes[1];
      m_epochs[0] = m_epochs[1];
    }
    m_pending[m_size].reset();
    m_sizes[m_size] = 0;
    m_epochs[m_size] = 0;
    m_activeToken = started.token;
    m_activeEpoch = started.epoch;
    m_activeOwner = started.original; // weak identity only, never a new owner
    return started;
  }

  // New seek cancels all NOT-YET-BEGUN originals without handing them to
  // stock. An in-flight original remains with its caller until Finish;
  // the worker's flush/barrier must NOT apply while one remains in flight.
  void RevokePrepared() noexcept
  {
    for (auto& owner : m_pending)
      owner.reset();
    m_sizes = {};
    m_epochs = {};
    m_size = 0;
    m_bytes = 0;
  }

  bool Finish(std::uint64_t token) noexcept
  {
    if (token == 0 || token != m_activeToken)
      return false;
    m_activeToken = 0;
    m_activeEpoch = 0;
    m_activeOwner.reset();
    return true;
  }

  void Close() noexcept
  {
    m_closed = true;
    RevokePrepared();
    // Never delete / steal an in-flight decoder input: the lease caller
    // still owns its original shared packet and MUST call Finish later.
  }

  bool InFlight() const noexcept { return m_activeToken != 0; }
  std::uint64_t InFlightEpoch() const noexcept { return m_activeEpoch; }
  std::size_t Queued() const noexcept { return m_size; }
  std::size_t DeclaredBytes() const noexcept { return m_bytes; }
  bool Closed() const noexcept { return m_closed; }

private:
  std::array<Owner, kDispatchSlots> m_pending{};
  std::array<std::size_t, kDispatchSlots> m_sizes{};
  std::array<std::uint64_t, kDispatchSlots> m_epochs{};
  std::weak_ptr<Message> m_activeOwner{};
  std::uint64_t m_activeToken{0};
  std::uint64_t m_activeEpoch{0};
  std::uint64_t m_nextToken{1};
  std::size_t m_size{0};
  std::size_t m_bytes{0};
  bool m_closed{false};
};

static_assert(kDispatchSlots == 2, "Original BL/EL dispatch holds at most two");
static_assert(kDispatchMaxDeclaredBytes <= GazelleFELPairing::kMaxPendingBytes,
              "Research dispatch must respect existing BL/EL byte budget");
} // namespace GazelleFELPrecreate
