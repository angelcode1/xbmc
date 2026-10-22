// SPDX-License-Identifier: MIT
#include "../xbmc/utils/GazelleFELNalReader.h"
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
using GazelleFEL::LengthPrefixedReader;
using GazelleFEL::NalSpan;

static std::vector<uint8_t> TwoNal(unsigned width)
{
  std::vector<uint8_t> data;
  auto append = [&](uint8_t type, uint8_t payload)
  {
    for (unsigned i = width; i > 0; --i)
      data.push_back(static_cast<uint8_t>((3u >> (8u * (i - 1))) & 255));
    data.push_back(static_cast<uint8_t>(type << 1));
    data.push_back(1);
    data.push_back(payload);
  };
  append(1, 5);
  append(62, 6);
  return data;
}

static void Verify(unsigned width)
{
  auto data = TwoNal(width);
  LengthPrefixedReader r(data.data(), data.size(), width);
  NalSpan n;
  assert(r.Next(n) && n.bytes == 3 && n.type == 1 && n.data[2] == 5);
  assert(r.Next(n) && n.bytes == 3 && n.type == 62 && n.data[2] == 6);
  assert(!r.Next(n) && r.Complete());
  for (std::size_t i = 1; i <= width + 2; ++i)
  {
    LengthPrefixedReader truncated(data.data(), data.size() - i, width);
    while (truncated.Next(n)) {}
    assert(!truncated.Complete());
  }
  auto zero = data;
  for (unsigned i = 0; i < width; ++i)
    zero[i] = 0;
  LengthPrefixedReader badzero(zero.data(), zero.size(), width);
  assert(!badzero.Next(n) && !badzero.Complete());
  auto oversized = data;
  for (unsigned i = 0; i < width; ++i)
    oversized[i] = 0xff;
  LengthPrefixedReader badbig(oversized.data(), oversized.size(), width);
  assert(!badbig.Next(n) && !badbig.Complete());

  // RPU output is allowed to change size. The next source NAL must still be
  // found at its original input boundary (not the rewritten output length).
  auto rpuFirst = data;
  rpuFirst[width] = static_cast<uint8_t>(62 << 1);
  rpuFirst[width + 3 + width] = static_cast<uint8_t>(1 << 1);
  LengthPrefixedReader unchangedInput(rpuFirst.data(), rpuFirst.size(), width);
  assert(unchangedInput.Next(n) && n.type == 62);
  const unsigned rewrittenRpuOutputBytes = n.bytes + 20;
  assert(rewrittenRpuOutputBytes != n.bytes);
  assert(unchangedInput.Next(n) && n.type == 1 && n.bytes == 3);
  assert(!unchangedInput.Next(n) && unchangedInput.Complete());
}

int main()
{
  for (unsigned n = 1; n <= 4; ++n)
    Verify(n);
  NalSpan n;
  LengthPrefixedReader noData(nullptr, 0, 4);
  assert(!noData.Next(n) && !noData.Complete());
  uint8_t one[] = {0, 0, 0, 1, 2};
  LengthPrefixedReader tooShort(one, sizeof(one), 4);
  assert(!tooShort.Next(n) && !tooShort.Complete());
  LengthPrefixedReader wrongWidth(one, sizeof(one), 5);
  assert(!wrongWidth.Next(n) && !wrongWidth.Complete());
  return 0;
}
