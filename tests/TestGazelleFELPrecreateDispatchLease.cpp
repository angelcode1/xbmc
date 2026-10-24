// SPDX-License-Identifier: GPL-2.0-or-later
// Host-only lease lifetime proof. NO decoder, Kodi worker or Android runtime.
#include "../xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELPrecreateDispatchLease.h"

#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <utility>

namespace
{
struct Message
{
  Message(int id, int& freed) : id(id), freed(freed) {}
  ~Message() { ++freed; }
  int id;
  int& freed;
};
using Lease = GazelleFELPrecreate::DispatchLease<Message>;
using Result = GazelleFELPrecreate::LeasePrepare;
std::shared_ptr<Message> Make(int id, int& freed)
{
  return std::make_shared<Message>(id, freed);
}
} // namespace

int main()
{
  // Prepare at most two original shared owners, never duplicate the same
  // original; a third stays with caller as a backpressure obligation.
  {
    int freed = 0;
    Lease lease;
    auto first = Make(1, freed), second = Make(2, freed), third = Make(3, freed);
    auto firstAlias = first;
    auto* firstId = first.get();
    assert(lease.Prepare(first, 1, 100) == Result::Prepared && !first);
    assert(lease.Prepare(firstAlias, 1, 100) == Result::CallerRetains);
    assert(firstAlias && firstAlias.get() == firstId);
    assert(lease.Prepare(second, 1, 200) == Result::Prepared && !second);
    assert(lease.Prepare(third, 1, 100) == Result::CallerRetains && third);
    assert(lease.Queued() == 2 && lease.DeclaredBytes() == 300);
    firstAlias.reset();
    auto running = lease.Begin(1);
    assert(running && running.original.get() == firstId &&
           running.token != 0 && running.epoch == 1);
    assert(lease.InFlight() && lease.InFlightEpoch() == 1);
    assert(!lease.Begin(1));
    assert(lease.Queued() == 1 && lease.DeclaredBytes() == 200);
    // A seek may cancel only NOT-YET-BEGUN data; the active original
    // survives with its external caller until explicit Finish.
    lease.RevokePrepared();
    assert(freed == 1 && !lease.Queued() && running.original->id == 1);
    assert(!lease.Finish(running.token + 1) && lease.InFlight());
    running.original.reset();
    assert(freed == 2);
    assert(lease.Finish(running.token) && !lease.InFlight());
    assert(!lease.Finish(running.token));
    third.reset();
    assert(freed == 3);
    lease.Close();
  }
  // Invalid size, zero stamp, wrong generation and closing never steal an
  // owner's reference. Closing cannot reopen a previously canceled holder.
  {
    int freed = 0;
    Lease lease;
    auto original = Make(4, freed);
    assert(lease.Prepare(original, 0, 1) == Result::Invalid);
    assert(lease.Prepare(original, 1, 0) == Result::Invalid);
    assert(lease.Prepare(original, 1,
           GazelleFELPairing::kMaxLayerPacketBytes + 1) == Result::Invalid);
    assert(original && lease.Queued() == 0);
    assert(lease.Prepare(original, 2, 20) == Result::Prepared && !original);
    assert(!lease.Begin(1));
    lease.Close();
    lease.Close();
    assert(freed == 1);
    auto newOwner = Make(5, freed);
    assert(lease.Prepare(newOwner, 2, 20) == Result::Closed && newOwner);
    newOwner.reset();
    assert(freed == 2);
  }
  // A second generation cannot enter a pending lease batch and cannot
  // reorder an already-prepared message. Revoke clears pending exactly once.
  {
    int freed = 0;
    Lease lease;
    auto e1 = Make(6, freed), e2 = Make(7, freed);
    assert(lease.Prepare(e1, 5, 30) == Result::Prepared);
    assert(lease.Prepare(e2, 6, 30) == Result::CallerRetains && e2);
    lease.RevokePrepared();
    lease.RevokePrepared();
    assert(freed == 1);
    assert(lease.Prepare(e2, 6, 30) == Result::Prepared && !e2);
    auto running = lease.Begin(6);
    assert(running && running.original->id == 7);
    lease.Close(); // never steals active original
    assert(lease.InFlight() && freed == 1);
    assert(lease.Finish(running.token) && !lease.InFlight());
    running.original.reset();
    assert(freed == 2);
  }
  std::cout << "GAZELLE_DISPATCH_LEASE_HOST_PASS "
               "two_originals_bounded=true duplicate_refused=true "
               "caller_backpressure=true prepared_canceled_at_seek=true "
               "inflight_not_cancelled=true flush_waits_for_finish_model=true "
               "close_retains_inflight_owner=true destructor_once=true "
               "no_real_decoder=true no_device=true fel_off=true\n";
}
