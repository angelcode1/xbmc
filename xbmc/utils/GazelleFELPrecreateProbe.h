// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// Bounded, read-only Dolby Profile 7 first access-unit classification.
// SOURCE-ONLY. No codec selection, no residual decoder, no packet rewriting.
// Never infer FEL from dv_profile==7 or el_present_flag alone.
#include <cstddef>
#include <cstdint>
#include <cstring>

#ifdef HAVE_LIBDOVI
extern "C"
{
#include <libdovi/rpu_parser.h>
}
#endif

namespace GazelleFEL
{
enum class PrecreateRpuType : uint8_t
{
  Unknown,
  MEL,
  FEL
};
struct PrecreateResult
{
  PrecreateRpuType type{PrecreateRpuType::Unknown};
  bool framingValid{false};
  bool bl{false};
  bool el{false};
  bool rpu{false};
};
constexpr std::size_t kMaxPrecreateAU = 16u * 1024u * 1024u;
constexpr std::size_t kMaxPrecreateNals = 512u;
constexpr std::size_t kMaxPrecreateRpu = 65536u;

// The existing converter's libdovi API accepts the *entire* HEVC NAL-62,
// including its two-byte HEVC header. Parsing must not mutate the source.
inline PrecreateRpuType InspectRpu(const uint8_t* nal, std::size_t size) noexcept
{
  if (!nal || size < 3u || size > kMaxPrecreateRpu)
    return PrecreateRpuType::Unknown;
  if ((nal[0] & 0x80u) || ((nal[0] >> 1u) & 63u) != 62u || (nal[1] & 7u) == 0u)
    return PrecreateRpuType::Unknown;
#ifdef HAVE_LIBDOVI
  auto* const rpu = dovi_parse_unspec62_nalu(nal, size);
  if (!rpu)
    return PrecreateRpuType::Unknown;
  // Header is separately heap allocated by libdovi, not owned by RpuOpaque.
  const auto* const header = dovi_rpu_get_header(rpu);
  PrecreateRpuType answer = PrecreateRpuType::Unknown;
  if (header && header->guessed_profile == 7 && header->el_type)
  {
    if (std::strcmp(header->el_type, "FEL") == 0)
      answer = PrecreateRpuType::FEL;
    else if (std::strcmp(header->el_type, "MEL") == 0)
      answer = PrecreateRpuType::MEL;
  }
  if (header)
    dovi_rpu_free_header(header);
  dovi_rpu_free(rpu);
  return answer;
#else
  return PrecreateRpuType::Unknown;
#endif
}

// Immutable in-band HEVC AU. Transport can carry 3/4-byte Annex B start
// codes (notably MPEG-TS/Blu-ray) OR hvcC length-prefixed NALs. The two
// framing modes are disjoint: a legal length-prefixed NAL cannot have the
// first NAL size 1 as implied by a leading Annex B prefix. Never heuristically
// accept a non-Annex-B packet without trusted hvcC length-width metadata.
//
// This does not decode HEVC, authorize FEL playback, own the packet, or prove
// the AU reached Kodi before its initial stock decoder open. Fail closed on
// malformed framing, duplicated RPU, protection, or missing BL/EL.
inline PrecreateResult InspectFirstAU(const uint8_t* data, std::size_t bytes,
                                     const uint8_t* hvcc, std::size_t hvccBytes,
                                     bool protectedContent) noexcept
{
  PrecreateResult result{};
  if (protectedContent || !data || !bytes || bytes > kMaxPrecreateAU)
    return result;

  std::size_t count = 0;
  const uint8_t* soleRpu = nullptr;
  std::size_t soleRpuBytes = 0;
  unsigned rpuCount = 0;
  const auto acceptNal = [&](const uint8_t* nal, std::size_t length) -> bool {
    if (++count > kMaxPrecreateNals || length < 2u ||
        (nal[0] & 0x80u) || (nal[1] & 7u) == 0u)
      return false;
    const unsigned type = static_cast<unsigned>((nal[0] >> 1u) & 63u);
    if (type <= 31u)
      result.bl = true;
    if (type == 63u)
      result.el = true;
    if (type == 62u)
    {
      if (++rpuCount != 1u || length > kMaxPrecreateRpu)
        return false;
      soleRpu = nal;
      soleRpuBytes = length;
      result.rpu = true;
    }
    return true;
  };

  const auto startCodeWidth = [&](std::size_t at) -> unsigned {
    if (at >= bytes || bytes - at < 3u || data[at] != 0u ||
        data[at + 1u] != 0u)
      return 0u;
    if (data[at + 2u] == 1u)
      return 3u;
    if (bytes - at >= 4u && data[at + 2u] == 0u &&
        data[at + 3u] == 1u)
      return 4u;
    return 0u;
  };

  const bool annexB = startCodeWidth(0u) != 0u;
  std::size_t pos = 0;
  if (annexB)
  {
    // Read-only bounded scan; no copy, no NAL rewrite and no unchecked
    // arithmetic. Strip transport trailing_zero_8bits only, not RPU bytes.
    while (pos < bytes)
    {
      const unsigned prefix = startCodeWidth(pos);
      if (!prefix)
        return {};
      pos += prefix;
      std::size_t end = pos;
      while (end < bytes && !startCodeWidth(end))
        ++end;
      std::size_t nalEnd = end;
      while (nalEnd > pos && data[nalEnd - 1u] == 0u)
        --nalEnd;
      if (!acceptNal(data + pos, nalEnd - pos))
        return {};
      pos = end;
    }
  }
  else
  {
    if (!hvcc || hvccBytes < 23u || hvcc[0] != 1u)
      return {};
    const unsigned width = static_cast<unsigned>(hvcc[21] & 3u) + 1u;
    if (width == 3u) // reserved length-prefix width
      return {};
    while (pos < bytes)
    {
      if (bytes - pos < width)
        return {};
      uint32_t length = 0;
      for (unsigned i = 0; i < width; ++i)
        length = (length << 8u) | data[pos++];
      if (length < 2u || static_cast<std::size_t>(length) > bytes - pos ||
          !acceptNal(data + pos, length))
        return {};
      pos += length;
    }
  }

  result.framingValid = count != 0u && pos == bytes;
  if (!result.framingValid || !result.bl || !result.el || rpuCount != 1u)
    return result;
  result.type = InspectRpu(soleRpu, soleRpuBytes);
  return result;
}
} // namespace GazelleFEL
