// SPDX-License-Identifier: GPL-2.0-or-later
// This is the exact header consumed by VideoPlayerVideo.cpp, not a copy.
#include "../xbmc/cores/VideoPlayer/GazelleDeferredOpenPolicy.h"

#include <cassert>
#include <iostream>

using KODI::VIDEO::GAZELLE::DeferredStockInputs;
using KODI::VIDEO::GAZELLE::EligibleForDeferredStock;
using KODI::VIDEO::GAZELLE::UseDeferredStock;

int main()
{
  constexpr DeferredStockInputs eligible{true,true,true,true,false,false,false,true};
  static_assert(EligibleForDeferredStock(eligible), "Candidate should be recognized");
  static_assert(!UseDeferredStock(eligible), "Disabled feature must remain off");

  assert(EligibleForDeferredStock(eligible));
  assert(!UseDeferredStock(eligible));
  for (unsigned i=0;i<8;i++)
  {
    auto input=eligible;
    switch(i)
    {
      case 0: input.hevc=false;break;
      case 1: input.dolbyVision=false;break;
      case 2: input.profile7=false;break;
      case 3: input.enhancementPresent=false;break;
      case 4: input.protectedContent=true;break;
      case 5: input.dvd=true;break;
      case 6: input.stills=true;break;
      case 7: input.alreadyRunningWorker=false;break;
    }
    assert(!EligibleForDeferredStock(input));
    assert(!UseDeferredStock(input));
  }
  // A P7 enhancement-present flag makes *only a candidate*. Neither the
  // header nor the worker treats it as verified FEL-vs-MEL identity.
  std::cout << "GAZELLE_KODI_DEFERRED_POLICY_HOST_PASS disabled=true "
               "rejected=8 candidate_only=true live_codec=false no_device=true\n";
}
