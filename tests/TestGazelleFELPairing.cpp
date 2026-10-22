// SPDX-License-Identifier: MIT
#include "../xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELPairing.h"
#include <cassert>
#include <cstdint>
#include <deque>
#include <limits>
#include <vector>

struct Packet
{
  bool isEL;
  double dts;
  double pts;
  std::vector<std::uint8_t> data;
};
int main()
{
  constexpr double no = -4503599627370496.0;
  using namespace GazelleFELPairing;
  assert(SameAccessUnit(1000000, 1100000, 1000050, 1200000, no));
  assert(!SameAccessUnit(1000000, 1100000, 1040000, 1100000, no));
  assert(!SameAccessUnit(1000000, 1100000, 1000101, 1100000, no));
  assert(SameAccessUnit(no, 1000000, no, 1000050, no));
  assert(SameAccessUnit(no, 1000000, 100000, 1000050, no));
  assert(!SameAccessUnit(no, no, no, no, no));
  assert(!SameAccessUnit(std::numeric_limits<double>::quiet_NaN(), no, no, no, no));
  std::deque<Packet> q{
    {false, 2000000, 2100000, {1}},
    {false, 2040000, 2140000, {2}},
    {true, 2080000, 2180000, {3}},
  };
  auto i = FindMate(q, true, 2040000, 999, no);
  assert(i != q.end() && i->data[0] == 2);
  assert(FindMate(q, true, 2120000, 2100000, no) == q.end());
  assert(FindMate(q, false, 2080000, 777, no) == q.begin()+2);
  assert(CanBuffer(q, 100));
  assert(!CanBuffer(q, 0));
  assert(!CanBuffer(q, kMaxLayerPacketBytes+1));
  q[0].data.resize(kMaxLayerPacketBytes);
  assert(!CanBuffer(q, kMaxPendingBytes));
  for (unsigned n=0; n<6; ++n) q.push_back({false, 0, 0, {0}});
  assert(!CanBuffer(q, 1)); // bounded queue, no silent eviction
  assert(q.size() == 9);
  return 0;
}
