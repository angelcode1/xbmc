// SPDX-License-Identifier: GPL-2.0-or-later
// Compiles/links the exact production read-only scanner against genuine
// libdovi 3.3.2 system headers + library, never the fake test stub.
// This is NOT a genuine FEL fixture and can only establish real FFI safety.
#define HAVE_LIBDOVI 1
#include "../xbmc/utils/GazelleFELPrecreateProbe.h"

#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>

int main()
{
  using GazelleFEL::InspectFirstAU;
  using GazelleFEL::InspectRpu;
  using GazelleFEL::PrecreateRpuType;

  assert(InspectRpu(nullptr, 0) == PrecreateRpuType::Unknown);
  const std::array<std::uint8_t, 2> truncatedRpu{{0x7c, 0x01}};
  assert(InspectRpu(truncatedRpu.data(), truncatedRpu.size()) == PrecreateRpuType::Unknown);
  // Valid HEVC NAL-62 header, but deliberately NOT valid Dolby RPU metadata.
  const std::array<std::uint8_t, 4> invalidRpu{{0x7c, 0x01, 0x00, 0x00}};
  assert(InspectRpu(invalidRpu.data(), invalidRpu.size()) == PrecreateRpuType::Unknown);
  assert(InspectRpu(invalidRpu.data(), GazelleFEL::kMaxPrecreateRpu + 1) ==
         PrecreateRpuType::Unknown); // size checked before any access

  const std::vector<std::uint8_t> au{
      0, 0, 0, 3, 0x26, 0x01, 0x11, // VCL / BL
      0, 0, 0, 4, 0x7c, 0x01, 0, 0, // structurally RPU, malformed Dolby payload
      0, 0, 0, 3, 0x7e, 0x01, 0x21  // EL type 63
  };
  std::array<std::uint8_t, 23> hvcc{};
  hvcc[0] = 1;
  hvcc[21] = 3;
  auto parsed = InspectFirstAU(au.data(), au.size(), hvcc.data(), hvcc.size(), false);
  assert(parsed.framingValid && parsed.bl && parsed.el && parsed.rpu);
  assert(parsed.type == PrecreateRpuType::Unknown);
  parsed = InspectFirstAU(au.data(), au.size(), hvcc.data(), hvcc.size(), true);
  assert(parsed.type == PrecreateRpuType::Unknown);

  std::cout << "GAZELLE_FEL_REAL_LIBDOVI_ABI_PASS version=3.3.2 "
               "linked_real_library=true invalid_input_unknown=true "
               "no_authenticated_FEL_fixture=true kodi_android_build=false "
               "no_device=true\n";
}
