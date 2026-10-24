// SPDX-License-Identifier: MIT
// HOST TEST SHIM ONLY. NOT the actual libdovi ABI header.
// The production probe uses the real #include <libdovi/rpu_parser.h>.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct DoviRpuOpaque DoviRpuOpaque;
typedef struct DoviRpuDataHeader {
  int guessed_profile;
  const char* el_type;
} DoviRpuDataHeader;
DoviRpuOpaque* dovi_parse_unspec62_nalu(const uint8_t* buf, size_t len);
const DoviRpuDataHeader* dovi_rpu_get_header(const DoviRpuOpaque* opaque);
void dovi_rpu_free_header(const DoviRpuDataHeader* header);
void dovi_rpu_free(DoviRpuOpaque* opaque);
#ifdef __cplusplus
}
#endif
