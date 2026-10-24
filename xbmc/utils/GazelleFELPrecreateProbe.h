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

// Immutable length-prefixed AU (existing in-band BL+EL+RPU layout).
// This does not decode HEVC, validate RPU authenticity beyond libdovi,
// own a packet, or prove the first AU was obtained before codec allocation.
// Requires one VCL NAL, one EL type-63 NAL and exactly one RPU type-62 NAL.
// Unknown results must only fall through to the stock decoder.
inline PrecreateResult InspectFirstAU(const uint8_t* data, std::size_t bytes,
                                     const uint8_t* hvcc, std::size_t hvccBytes,
                                     bool protectedContent) noexcept
{
  PrecreateResult result{};
  if (protectedContent || !data || !bytes || bytes > kMaxPrecreateAU ||
      !hvcc || hvccBytes < 23u || hvcc[0] != 1u)
    return result;
  const unsigned width = static_cast<unsigned>(hvcc[21] & 3u) + 1u;
  if (width == 3u) // reserved length-prefix width
    return result;
  std::size_t pos = 0;
  std::size_t count = 0;
  const uint8_t* soleRpu = nullptr;
  std::size_t soleRpuBytes = 0;
  unsigned rpuCount = 0;
  while (pos < bytes)
  {
    if (++count > kMaxPrecreateNals || bytes - pos < width)
      return {};
    uint32_t length = 0;
    for (unsigned i = 0; i < width; ++i)
      length = (length << 8u) | data[pos++];
    if (length < 2u || static_cast<std::size_t>(length) > bytes - pos)
      return {};
    const uint8_t* const nal = data + pos;
    if ((nal[0] & 0x80u) || (nal[1] & 7u) == 0u)
      return {};
    const unsigned type = static_cast<unsigned>((nal[0] >> 1u) & 63u);
    if (type <= 31u)
      result.bl = true;
    if (type == 63u)
      result.el = true;
    if (type == 62u)
    {
      if (++rpuCount != 1u || length > kMaxPrecreateRpu)
        return {};
      soleRpu = nal;
      soleRpuBytes = length;
      result.rpu = true;
    }
    pos += length;
  }
  result.framingValid = pos == bytes && count != 0u;
  if (!result.framingValid || !result.bl || !result.el || rpuCount != 1u)
    return result;
  result.type = InspectRpu(soleRpu, soleRpuBytes);
  return result;
}
} // namespace GazelleFEL
