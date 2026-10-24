// SPDX-License-Identifier: GPL-2.0-or-later
// Host-only, no Kodi runtime: exact original-message shared_ptr lifetime,
// epoch revocation, and bounded metadata-only BL/EL pairing contract.
#include "../xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELPrecreateOwners.h"

#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
#include <memory>
#include <utility>

namespace
{
constexpr double kInvalid = -4503599627370496.0;
using Gate = GazelleFELPrecreate::PairOwners<struct Message>;
using Info = GazelleFELPrecreate::LayerInfo;
using Disposition = GazelleFELPrecreate::Disposition;

struct Message
{
  Message(int n, int* counter) : id(n), destroyed(counter) {}
  ~Message() { ++*destroyed; }
  int id;
  int* destroyed;
};

std::shared_ptr<Message> Original(int id, int& destroyed)
{
  return std::make_shared<Message>(id, &destroyed);
}

Info Bl(std::uint64_t epoch = 0)
{
  Info p{};
  p.epoch = epoch;
  p.demuxerId = 9;
  p.streamId = 101;
  p.isDualStream = true;
  p.isEL = false;
  p.protectedContent = false;
  p.dropRequested = false;
  p.bytes = 4096;
  p.dts = 1000000;
  p.pts = 1200000;
  return p;
}

Info El(std::uint64_t epoch = 0)
{
  auto p = Bl(epoch);
  p.streamId = 102;
  p.isEL = true;
  p.dts += 50;
  return p;
}
} // namespace

int main()
{
  // Preserve each exact message identity and arrival order (BL -> EL).
  // The only payload owner is Kodi's original shared packet-message owner.
  {
    int freed = 0;
    Gate gate(kInvalid);
    auto a = Original(1, freed);
    std::weak_ptr<Message> weak = a;
    auto first = gate.Observe(std::move(a), Bl());
    assert(!a && first.disposition == Disposition::Held);
    assert(!first.first && !first.second && gate.HasPending() && !weak.expired());
    auto b = Original(2, freed);
    auto result = gate.Observe(std::move(b), El());
    assert(!b && result.disposition == Disposition::PairMetadataOnly);
    assert(result.first && result.second && result.first->id == 1 && result.second->id == 2);
    assert(!gate.HasPending() && freed == 0);
    result.first.reset();
    assert(freed == 1 && weak.expired());
    result.second.reset();
    assert(freed == 2);
  }
  // EL may arrive before BL; preserve original input order, never reorder
  // message lifetime to look like media NAL decode order.
  {
    int freed = 0;
    Gate gate(kInvalid);
    assert(gate.Observe(Original(3, freed), El()).disposition == Disposition::Held);
    auto paired = gate.Observe(Original(4, freed), Bl());
    assert(paired.disposition == Disposition::PairMetadataOnly);
    assert(paired.first->id == 3 && paired.second->id == 4);
    paired = {};
    assert(freed == 2);
  }
  // Missing mate: stock fallback must receive the same original once.
  {
    int freed = 0;
    Gate gate(kInvalid, 4);
    assert(gate.Observe(Original(5, freed), Bl(4)).disposition == Disposition::Held);
    auto replay = gate.TakeForStock(4);
    assert(replay && replay->id == 5 && !gate.HasPending());
    assert(!gate.TakeForStock(4) && !gate.TakeForStock(3));
    replay.reset();
    assert(freed == 1);
  }
  // A seek revokes pending original ownership and forbids stale replay.
  {
    int freed = 0;
    Gate gate(kInvalid, 1);
    assert(gate.Observe(Original(6, freed), Bl(1)).disposition == Disposition::Held);
    assert(!gate.AdvanceEpoch(1) && !gate.AdvanceEpoch(0) && gate.HasPending());
    assert(gate.AdvanceEpoch(2) && freed == 1 && !gate.HasPending());
    assert(!gate.TakeForStock(1));
    const auto stale = gate.Observe(Original(7, freed), El(1));
    assert(stale.disposition == Disposition::StaleDropped);
    assert(freed == 2 && !gate.HasPending());
    assert(gate.Observe(Original(8, freed), Bl(2)).disposition == Disposition::Held);
    auto fresh = gate.Observe(Original(9, freed), El(2));
    assert(fresh.disposition == Disposition::PairMetadataOnly && freed == 2);
    fresh = {};
    assert(freed == 4);
  }
  // Timestamp mismatch MUST NOT be repaired with matching PTS when both DTS
  // are valid: reject pair, return both in arrival order for stock.
  {
    int freed = 0;
    Gate gate(kInvalid);
    assert(gate.Observe(Original(10, freed), Bl()).disposition == Disposition::Held);
    auto other = El();
    other.pts = Bl().pts;
    other.dts = 2000000;
    auto fail = gate.Observe(Original(11, freed), other);
    assert(fail.disposition == Disposition::StockFallback && fail.first->id == 10 &&
           fail.second->id == 11 && !gate.HasPending());
    fail = {};
    assert(freed == 2);
  }
  // Wrong stream identity, demuxer, layer, or bogus metadata: fail closed.
  for (int kind = 0; kind < 11; ++kind)
  {
    int freed = 0;
    Gate gate(kInvalid);
    auto first = Bl();
    auto second = El();
    if (kind == 0) second.demuxerId = 10;
    if (kind == 1) second.streamId = 101;
    if (kind == 2) second.isEL = false;
    if (kind == 3) second.protectedContent = true;
    if (kind == 4) second.dropRequested = true;
    if (kind == 5) second.isDualStream = false;
    if (kind == 6) second.bytes = 0;
    if (kind == 7) second.bytes = GazelleFELPairing::kMaxLayerPacketBytes + 1;
    if (kind == 8) second.dts = kInvalid, second.pts = kInvalid;
    if (kind == 9) second.dts = std::numeric_limits<double>::quiet_NaN(),
                   second.pts = kInvalid;
    if (kind == 10) second.streamId = -1;
    assert(gate.Observe(Original(20, freed), first).disposition == Disposition::Held);
    auto failed = gate.Observe(Original(21, freed), second);
    assert(failed.disposition == Disposition::StockFallback);
    assert(failed.first->id == 20 && failed.second->id == 21);
    assert(!gate.HasPending());
    failed = {};
    assert(freed == 2);
  }
  // Any invalid first layer goes straight back to stock (no owner retention).
  {
    int freed = 0;
    Gate gate(kInvalid);
    auto bad = Bl();
    bad.protectedContent = true;
    auto out = gate.Observe(Original(30, freed), bad);
    assert(out.disposition == Disposition::StockFallback && !out.first && out.second);
    out = {};
    assert(freed == 1 && !gate.HasPending());
    assert(gate.Observe({}, Bl()).disposition == Disposition::InvalidDropped);
  }
  // Close and destruction release pending without a second packet callback.
  {
    int freed = 0;
    {
      Gate gate(kInvalid);
      assert(gate.Observe(Original(31, freed), Bl()).disposition == Disposition::Held);
      gate.Close();
      gate.Close();
      assert(freed == 1 && !gate.HasPending());
      assert(gate.Observe(Original(32, freed), El()).disposition == Disposition::Held);
    }
    assert(freed == 2);
  }
  std::cout << "GAZELLE_PRECREATE_OWNER_HOST_PASS pair_orders=2 "
               "fallback_original_once=true seek_epoch_revocation=true "
               "stale_dropped=true protected_refused=true malformed=11 "
               "no_copy=true no_kodi_runtime=true codec_selection=disabled "
               "no_device=true\n";
}
