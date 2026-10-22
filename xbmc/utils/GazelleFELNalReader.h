// SPDX-License-Identifier: MIT
// Bounded NAL length-prefix reader for Kodi's Profile-7 BL+EL converter.
#pragma once
#include <cstddef>
#include <cstdint>

namespace GazelleFEL
{
struct NalSpan
{
  uint8_t* data{nullptr};
  uint32_t bytes{0};
  uint8_t type{0};
};

class LengthPrefixedReader
{
public:
  LengthPrefixedReader(uint8_t* data, std::size_t bytes, unsigned prefixBytes) noexcept
    : m_data(data), m_size(bytes), m_prefixBytes(prefixBytes)
  {
    if (!data || !bytes || prefixBytes < 1 || prefixBytes > 4)
      m_failed = true;
  }

  bool Next(NalSpan& nal) noexcept
  {
    if (m_failed || m_pos == m_size)
      return false;
    const std::size_t remaining = m_size - m_pos;
    if (remaining < m_prefixBytes)
    {
      m_failed = true;
      return false;
    }
    uint32_t length = 0;
    for (unsigned i = 0; i < m_prefixBytes; ++i)
      length = (length << 8) | m_data[m_pos + i];
    m_pos += m_prefixBytes;
    if (length < 2 || length > m_size - m_pos)
    {
      m_failed = true;
      return false;
    }
    nal.data = m_data + m_pos;
    nal.bytes = length;
    nal.type = static_cast<uint8_t>((nal.data[0] >> 1) & 0x3f);
    m_pos += length;
    ++m_count;
    return true;
  }

  // A malformed trailing prefix cannot be accepted after earlier valid NALs.
  bool Complete() const noexcept
  {
    return !m_failed && m_count != 0 && m_pos == m_size;
  }

private:
  uint8_t* m_data;
  std::size_t m_size;
  unsigned m_prefixBytes;
  std::size_t m_pos{0};
  std::size_t m_count{0};
  bool m_failed{false};
};
} // namespace GazelleFEL
