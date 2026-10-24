// SPDX-License-Identifier: GPL-2.0-or-later
// Host-only Kodi-like Put(priority) contract, NOT a real CDVDMessageQueue run.
// Tests producer-time single-assignment stamp and serialized priority barrier.
#include "../xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELProducerEpoch.h"

#include <atomic>
#include <cassert>
#include <cstdint>
#include <deque>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

namespace
{
struct Base
{
  enum class Type { Packet, Flush, Reset };
  explicit Base(Type type) : kind(type) {}
  virtual ~Base() = default;
  Type kind;
  virtual std::uint64_t Epoch() const noexcept = 0;
};
struct Original final : Base
{
  Original(int id, std::atomic<int>& deaths)
    : Base(Type::Packet), id(id), deaths(deaths)
  {
  }
  ~Original() override { ++deaths; }
  bool TrySetGazelleResearchEpoch(std::uint64_t e) noexcept
  {
    if (e == 0 || epoch != 0)
      return false;
    epoch = e;
    return true;
  }
  std::uint64_t Epoch() const noexcept override { return epoch; }
  int id;
  std::atomic<int>& deaths;
  std::uint64_t epoch{0};
};
struct Barrier final : Base
{
  Barrier(Type type, std::uint64_t epoch) : Base(type), epoch(epoch) {}
  std::uint64_t Epoch() const noexcept override { return epoch; }
  std::uint64_t epoch;
};

class Queue
{
public:
  // Same method shape/return convention as actual Kodi CDVDMessageQueue::Put,
  // but no claim that this stand-in covers real Kodi queue implementation.
  int Put(const std::shared_ptr<Base>& message, int priority)
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    if (rejectNext)
    {
      rejectNext = false;
      return -2;
    }
    if (!message || (priority != 0 && priority != 1))
      return -3;
    if (priority)
      m_priority.push_back(message);
    else
      m_normal.push_back(message);
    return 1; // Kodi MSGQ_OK
  }

  std::shared_ptr<Base> Pop()
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    auto& which = m_priority.empty() ? m_normal : m_priority;
    if (which.empty())
      return {};
    auto msg = std::move(which.front());
    which.pop_front();
    return msg;
  }

  void RejectNext()
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    rejectNext = true;
  }
  void Purge()
  {
    std::lock_guard<std::mutex> guard(m_mutex);
    m_normal.clear();
    m_priority.clear();
  }

private:
  std::mutex m_mutex;
  bool rejectNext{false};
  std::deque<std::shared_ptr<Base>> m_normal;
  std::deque<std::shared_ptr<Base>> m_priority;
};
using Ingress = GazelleFELPrecreate::ProducerEpoch<Original, Queue>;
std::shared_ptr<Original> Make(int id, std::atomic<int>& deaths)
{
  return std::make_shared<Original>(id, deaths);
}
bool Flush(Ingress& ingress, Base::Type type = Base::Type::Flush)
{
  return ingress.PutBarrier([type](std::uint64_t epoch) {
    return std::make_shared<Barrier>(type, epoch);
  });
}
} // namespace

int main()
{
  // Priority flush overtakes an ordinary pre-seek original message but
  // MUST NOT retroactively relabel that original with the post-seek epoch.
  {
    std::atomic<int> freed{0};
    Queue queue;
    Ingress ingress(queue);
    auto old = Make(1, freed);
    assert(ingress.PutOriginal(old) && old->Epoch() == 1);
    assert(!ingress.PutOriginal(old)); // single-assignment, no duplicate Put
    old.reset();
    assert(Flush(ingress));
    auto fresh = Make(2, freed);
    assert(ingress.PutOriginal(fresh) && fresh->Epoch() == 2);
    fresh.reset();
    auto barrier = queue.Pop();
    assert(barrier && barrier->kind == Base::Type::Flush && barrier->Epoch() == 2);
    barrier.reset();
    auto stale = queue.Pop();
    assert(stale && stale->kind == Base::Type::Packet && stale->Epoch() == 1);
    stale.reset();
    auto postSeek = queue.Pop();
    assert(postSeek && postSeek->Epoch() == 2);
    postSeek.reset();
    assert(freed == 2 && !queue.Pop());
  }

  // A queue rejection preserves original caller ownership but a message
  // already stamped once must NEVER be silently retried at a new epoch.
  {
    std::atomic<int> freed{0};
    Queue queue;
    Ingress ingress(queue);
    auto rejected = Make(3, freed);
    queue.RejectNext();
    assert(!ingress.PutOriginal(rejected) && rejected->Epoch() == 1);
    assert(!ingress.PutOriginal(rejected));
    assert(!queue.Pop());
    rejected.reset();
    assert(freed == 1);
    queue.RejectNext();
    assert(!Flush(ingress));
    assert(ingress.ProducerEpochForAuditOnly() == 1);
    assert(Flush(ingress));
    assert(ingress.ProducerEpochForAuditOnly() == 2);
    queue.Purge();
  }

  // A failed barrier allocation (modeled by null factory) cannot publish a
  // new epoch. A closed or wrapping producer refuses further messages.
  {
    std::atomic<int> freed{0};
    Queue queue;
    Ingress ingress(queue);
    assert(!ingress.PutBarrier([](std::uint64_t) { return std::shared_ptr<Barrier>{}; }));
    assert(ingress.ProducerEpochForAuditOnly() == 1);
    ingress.Close();
    assert(!Flush(ingress));
    auto packet = Make(4, freed);
    assert(!ingress.PutOriginal(packet) && packet->Epoch() == 0);
    packet.reset();
    assert(freed == 1);

    Queue overflowQueue;
    Ingress overflow(overflowQueue, std::numeric_limits<std::uint64_t>::max());
    assert(!Flush(overflow));
    assert(!overflowQueue.Pop());
  }

  // Concurrent sender/seek races must stamp each packet under the SAME
  // lock used to insert controls. FIFO normal queue stamps are monotonic.
  // Processing controls first means any old packets are safely tagged old.
  {
    std::atomic<int> freed{0};
    std::atomic<int> nextId{0};
    Queue queue;
    Ingress ingress(queue);
    constexpr int producers = 4;
    constexpr int perProducer = 96;
    constexpr int flushes = 32;
    std::vector<std::thread> threads;
    for (int n = 0; n < producers; ++n)
    {
      threads.emplace_back([&]() {
        for (int i = 0; i < perProducer; ++i)
        {
          auto original = Make(nextId++, freed);
          assert(ingress.PutOriginal(original));
        }
      });
    }
    threads.emplace_back([&]() {
      for (int i = 0; i < flushes; ++i)
        assert(Flush(ingress, (i & 1) ? Base::Type::Reset : Base::Type::Flush));
    });
    for (auto& thread : threads)
      thread.join();
    assert(ingress.ProducerEpochForAuditOnly() == 1 + flushes);

    unsigned seenBarriers = 0;
    std::uint64_t last = 0;
    for (auto msg = queue.Pop(); msg; msg = queue.Pop())
    {
      if (msg->kind == Base::Type::Packet)
      {
        assert(msg->Epoch() >= last);
        last = msg->Epoch();
      }
      else
        ++seenBarriers;
    }
    assert(seenBarriers == flushes && freed == producers * perProducer);
    ingress.Close();
  }

  std::cout << "GAZELLE_PRECREATE_PRODUCER_STAMP_PASS "
               "priority_flush_overtake=true original_epoch_immutable=true "
               "duplicate_enqueue_refused=true failed_put_no_retry=true "
               "failed_barrier_no_epoch_bump=true lock_serialized=true "
               "concurrent_producers=4 epoch_overflow_refused=true "
               "actual_kodi_queue=false no_device=true research_off=true\n";
}
