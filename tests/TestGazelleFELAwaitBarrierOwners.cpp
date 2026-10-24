// SPDX-License-Identifier: GPL-2.0-or-later
// Host-only original-message await-flush boundary. Synthetic owners only.
// DOES NOT run the real Kodi worker nor claim safe producer lock integration.
#include "../xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELAwaitBarrierOwners.h"

#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <utility>

namespace
{
struct Original
{
  Original(int id, int& frees) : id(id), frees(frees) {}
  ~Original() { ++frees; }
  int id;
  int& frees;
};
using Hold = GazelleFELPrecreate::AwaitBarrierOwners<Original>;
using Result = GazelleFELPrecreate::AwaitHoldResult;
using State = GazelleFELPrecreate::AwaitState;

std::shared_ptr<Original> Make(int id, int& freed)
{
  return std::make_shared<Original>(id, freed);
}
} // namespace

int main()
{
  constexpr std::size_t m = GazelleFELPairing::kMaxLayerPacketBytes;
  // Two ORIGINAL shared message owners from new epoch, priority 10 before
  // priority 1 flush; neither may be inspected or stock-fed pre-flush.
  {
    int freed = 0;
    Hold hold(500);
    auto bl = Make(1, freed), el = Make(2, freed);
    const auto* blId = bl.get();
    const auto* elId = el.get();
    assert(hold.TryHold(bl, 2, 2, 1, m, 10) == Result::HeldOriginal);
    assert(!bl && !freed && hold.Size() == 1);
    assert(hold.TryHold(el, 2, 2, 1, m, 11) == Result::HeldOriginal);
    assert(!el && hold.Size() == 2 && hold.Bytes() == 2*m);
    assert(hold.Inspect(2, 1, 12) == State::WaitingForBarrier);
    auto blocked = hold.TakeAfterBarrier(2, 1, 12);
    assert(blocked.count == 0 && hold.Size() == 2 && freed == 0);
    assert(hold.Inspect(2, 2, 13) == State::ReadyAfterBarrier);
    auto ready = hold.TakeAfterBarrier(2, 2, 13);
    assert(ready.count == 2 && hold.Size() == 0);
    assert(ready.original[0].get() == blId && ready.original[1].get() == elId);
    assert(hold.TakeAfterBarrier(2, 2, 14).count == 0);
    ready.original[0].reset();
    assert(freed == 1);
    ready.original[1].reset();
    assert(freed == 2);
  }
  // Capacity exhaustion must NEVER consume or destroy an incoming Kodi owner:
  // the caller retains it and is required to exert backpressure itself.
  {
    int freed = 0;
    Hold hold(500);
    auto first = Make(3, freed), second = Make(4, freed), overflow = Make(5, freed);
    const auto* original = overflow.get();
    assert(hold.TryHold(first, 2, 2, 1, m, 100) == Result::HeldOriginal);
    assert(hold.TryHold(second, 2, 2, 1, m, 101) == Result::HeldOriginal);
    assert(hold.TryHold(overflow, 2, 2, 1, 1, 102) == Result::CallerMustRetain);
    assert(overflow && overflow.get() == original && freed == 0);
    assert(hold.Size() == 2 && hold.Bytes() == 2*m);
    overflow.reset();
    assert(freed == 1);
    hold.Close();
    assert(freed == 3 && hold.Size() == 0);
  }
  // No implicit packet drop or stock replay upon expiration, even when an
  // old decoder retry overtakes the CONTROL at priority 10.
  {
    int freed = 0;
    Hold hold(20);
    auto first = Make(6, freed);
    assert(hold.TryHold(first, 4, 4, 3, 200, 100) == Result::HeldOriginal);
    assert(hold.Inspect(4, 3, 120) == State::DeadlineNeedsControlRecovery);
    assert(hold.TakeAfterBarrier(4, 3, 120).count == 0);
    auto other = Make(7, freed);
    assert(hold.TryHold(other, 4, 4, 3, 200, 121) == Result::CallerMustRetain);
    assert(other && freed == 0);
    // Applying the actual flush can make originals ready even after timeout.
    auto ready = hold.TakeAfterBarrier(4, 4, 123);
    assert(ready.count == 1 && ready.original[0]->id == 6);
    assert(other && hold.Size() == 0 && freed == 0);
    ready.original[0].reset();
    other.reset();
    assert(freed == 2);
  }
  // A newer producer seek revokes all retained old/new messages without
  // stock delivery, even before the queued priority-1 flush runs.
  {
    int freed = 0;
    Hold hold(300);
    auto prior = Make(8, freed);
    assert(hold.TryHold(prior, 2, 2, 1, 50, 2) == Result::HeldOriginal);
    assert(hold.Inspect(3, 1, 3) == State::SupersededBySeek);
    assert(!hold.TakeAfterBarrier(3, 1, 3).count);
    assert(hold.DropSuperseded(3, 1, 3));
    assert(freed == 1 && !hold.Size());
    assert(!hold.DropSuperseded(3, 1, 4));
  }
  // Null, invalid, stale, untagged and already-applied arrivals stay with
  // caller; no spurious release of other owners or fabricated epoch.
  {
    int freed = 0;
    Hold hold(50);
    std::shared_ptr<Original> null{};
    assert(hold.TryHold(null, 2, 2, 1, 5, 1) == Result::InvalidOriginal);
    auto invalid = Make(9, freed);
    assert(hold.TryHold(invalid, 2, 2, 1, 0, 1) == Result::InvalidOriginal);
    assert(hold.TryHold(invalid, 2, 2, 1, m+1, 1) == Result::InvalidOriginal);
    assert(hold.TryHold(invalid, 0, 2, 1, 5, 1) == Result::NotAwaitingBarrier);
    assert(hold.TryHold(invalid, 1, 2, 1, 5, 1) == Result::NotAwaitingBarrier);
    assert(hold.TryHold(invalid, 2, 2, 2, 5, 1) == Result::NotAwaitingBarrier);
    assert(invalid && hold.Size() == 0);
    invalid.reset();
    assert(freed == 1);
  }
  // Different pending future epoch, invalid snapshots and backwards tick
  // cannot silently evict prior valid original owner.
  {
    int freed = 0;
    Hold hold(10);
    auto bl = Make(10, freed), incoming = Make(11, freed);
    assert(hold.TryHold(bl, 2, 2, 1, 15, 100) == Result::HeldOriginal);
    assert(hold.TryHold(incoming, 3, 3, 1, 15, 101) == Result::CallerMustRetain);
    assert(hold.TryHold(incoming, 2, 2, 1, 15, 99) == Result::CallerMustRetain);
    assert(hold.Inspect(0, 0, 105) == State::InconsistentEpochs);
    assert(hold.Inspect(2, 3, 105) == State::InconsistentEpochs);
    assert(hold.Inspect(2, 1, 99) == State::InconsistentEpochs);
    assert(hold.TakeAfterBarrier(2, 3, 105).count == 0);
    assert(hold.Size() == 1 && incoming && freed == 0);
    hold.Close();
    incoming.reset();
    assert(freed == 2);
  }
  // Closing without ever applying flush destructs retained owners exactly
  // once, and a second Close does not produce a duplicated free.
  {
    int freed = 0;
    {
      Hold hold(0);
      auto owner = Make(12, freed);
      assert(hold.TryHold(owner, 2, 2, 1, 1, 0) == Result::HeldOriginal);
      assert(hold.Inspect(2, 1, 0) == State::DeadlineNeedsControlRecovery);
      hold.Close();
      hold.Close();
      assert(freed == 1);
      auto afterClose = Make(13, freed);
      assert(hold.TryHold(afterClose, 3, 3, 2, 1, 1) ==
             Result::CallerMustRetain);
      assert(afterClose && !hold.Size());
      afterClose.reset();
      assert(freed == 2);
    }
    assert(freed == 2);
  }
  std::cout << "GAZELLE_AWAIT_BARRIER_OWNERS_HOST_PASS "
               "capacity=2 declared_bytes_limit=33554432 "
               "preflush_no_stock=true caller_retains_on_backpressure=true "
               "deadline_retains_originals=true applied_flush_releases_once=true "
               "superseded_seek_drops_stale_once=true bad_epochs_refused=true "
               "close_cannot_reopen=true "
               "no_live_worker=true no_device=true fel_disabled=true\n";
}
