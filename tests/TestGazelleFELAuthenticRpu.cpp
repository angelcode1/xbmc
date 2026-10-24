// SPDX-License-Identifier: GPL-2.0-or-later
// Runs the production P7 probe with real libdovi and pinned *upstream* test
// RPUs. Synthetic BL/EL NALs are only transport wrappers, NOT FEL playback.
#define HAVE_LIBDOVI 1
#include "../xbmc/utils/GazelleFELPrecreateProbe.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>

using GazelleFEL::PrecreateRpuType;

static std::vector<std::uint8_t> ReadRpu(const char* filename)
{
  std::ifstream file(filename, std::ios::binary);
  if (!file)
    throw std::runtime_error("UPSTREAM_FIXTURE_MISSING");
  std::vector<std::uint8_t> bytes(std::istreambuf_iterator<char>{file}, {});
  if (bytes.size() < 8 || bytes.size() > GazelleFEL::kMaxPrecreateRpu + 4)
    throw std::runtime_error("UPSTREAM_FIXTURE_SIZE_INVALID");
  // Upstream dovi_tool .bin RPU files have a 4-byte Annex B start code.
  if (bytes[0] != 0 || bytes[1] != 0 || bytes[2] != 0 || bytes[3] != 1)
    throw std::runtime_error("UPSTREAM_FIXTURE_NOT_ANNEXB");
  return bytes;
}
static void Append(std::vector<std::uint8_t>& dst,
                   const std::uint8_t* nal, std::size_t size)
{
  if (size > 65536)
    throw std::runtime_error("NAL_TOO_LARGE");
  const auto u = static_cast<std::uint32_t>(size);
  dst.push_back(static_cast<std::uint8_t>(u >> 24u));
  dst.push_back(static_cast<std::uint8_t>(u >> 16u));
  dst.push_back(static_cast<std::uint8_t>(u >> 8u));
  dst.push_back(static_cast<std::uint8_t>(u));
  dst.insert(dst.end(), nal, nal + size);
}
static void AppendAnnexB(std::vector<std::uint8_t>& dst,
                         const std::uint8_t* nal, std::size_t size,
                         bool fourBytePrefix)
{
  if (size > GazelleFEL::kMaxPrecreateRpu)
    throw std::runtime_error("ANNEXB_NAL_TOO_LARGE");
  if (fourBytePrefix)
    dst.push_back(0);
  dst.insert(dst.end(), {0, 0, 1});
  dst.insert(dst.end(), nal, nal + size);
}
static void Check(const char* path, PrecreateRpuType expected)
{
  const auto bytes = ReadRpu(path);
  // Upstream test .bin stores raw RPU after the Annex B start code. Its
  // first payload byte is 0x19, NOT the HEVC NAL-62 header. Wrap it with
  // 0x7c01 exactly as Kodi's in-band HEVC packet contains it.
  std::vector<std::uint8_t> nal{0x7c, 0x01};
  nal.insert(nal.end(), bytes.begin() + 4, bytes.end());
  const auto* rpu = nal.data();
  const std::size_t size = nal.size();
  assert(GazelleFEL::InspectRpu(rpu, size) == expected);
  const std::array<std::uint8_t, 3> bl{{0x26, 0x01, 0x12}};
  const std::array<std::uint8_t, 3> el{{0x7e, 0x01, 0x24}};
  std::vector<std::uint8_t> au;
  Append(au, bl.data(), bl.size());
  Append(au, rpu, size);
  Append(au, el.data(), el.size());
  std::array<std::uint8_t, 23> hvcc{};
  hvcc[0] = 1;
  hvcc[21] = 3; // four-byte NAL length prefix
  const auto out = GazelleFEL::InspectFirstAU(
      au.data(), au.size(), hvcc.data(), hvcc.size(), false);
  assert(out.framingValid && out.bl && out.el && out.rpu);
  assert(out.type == expected);
  // Blu-ray/MPEG-TS can deliver Annex B rather than hvcC length-prefixed
  // packets. This is the SAME genuine upstream RPU metadata, never a disc.
  std::vector<std::uint8_t> annex;
  AppendAnnexB(annex, bl.data(), bl.size(), true);
  AppendAnnexB(annex, rpu, size, false);
  AppendAnnexB(annex, el.data(), el.size(), true);
  const auto annexOut=GazelleFEL::InspectFirstAU(
      annex.data(), annex.size(), nullptr, 0, false);
  assert(annexOut.framingValid && annexOut.bl && annexOut.el && annexOut.rpu);
  assert(annexOut.type == expected);
  assert(GazelleFEL::InspectFirstAU(
      annex.data(), annex.size(), nullptr, 0, true).type ==
         PrecreateRpuType::Unknown);
  AppendAnnexB(annex, rpu, size, true);
  assert(GazelleFEL::InspectFirstAU(
      annex.data(), annex.size(), nullptr, 0, false).type ==
         PrecreateRpuType::Unknown);
  // Never inspect encrypted first packets.
  assert(GazelleFEL::InspectFirstAU(
      au.data(), au.size(), hvcc.data(), hvcc.size(), true).type ==
         PrecreateRpuType::Unknown);
  // Two RPUs in one AU are ambiguous.
  Append(au, rpu, size);
  assert(GazelleFEL::InspectFirstAU(
      au.data(), au.size(), hvcc.data(), hvcc.size(), false).type ==
         PrecreateRpuType::Unknown);
}
int main(int argc, char** argv)
{
  if (argc != 3)
    throw std::runtime_error("EXPECTED_PINNED_FEL_AND_MEL_FIXTURE_PATHS");
  Check(argv[1], PrecreateRpuType::FEL);
  Check(argv[2], PrecreateRpuType::MEL);
  std::cout << "GAZELLE_REAL_FEL_MEL_RPU_CLASSIFICATION_PASS "
               "libdovi=3.3.2 authentic_upstream_metadata=true "
               "synthetic_bl_el_transport=true annexb_and_hvcc=true codec_selection=disabled "
               "actual_fel_decode=false android_kodi_compile=false "
               "no_device=true\n";
}
