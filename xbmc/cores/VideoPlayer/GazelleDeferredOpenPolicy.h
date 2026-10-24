// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

// Gazelle source-only, fail-closed decoder allocation policy.
// The production switch is permanently false in this research checkpoint.
// This header does not parse RPUs, authorize FEL, change OMX or touch media.
namespace KODI::VIDEO::GAZELLE
{
constexpr bool kDeferredStockResearchEnabled = false;

struct DeferredStockInputs
{
  bool hevc{false};
  bool dolbyVision{false};
  bool profile7{false};
  bool enhancementPresent{false};
  bool protectedContent{false};
  bool dvd{false};
  bool stills{false};
  bool alreadyRunningWorker{false};
};

// This is a scheduling *candidate*, not FEL-vs-MEL evidence.
// Never promote EL presence or Dolby stream hints to "FEL verified".
constexpr bool EligibleForDeferredStock(const DeferredStockInputs& v) noexcept
{
  return v.hevc && v.dolbyVision && v.profile7 && v.enhancementPresent &&
         !v.protectedContent && !v.dvd && !v.stills &&
         v.alreadyRunningWorker;
}

constexpr bool UseDeferredStock(const DeferredStockInputs& v) noexcept
{
  return kDeferredStockResearchEnabled && EligibleForDeferredStock(v);
}

// Initial OpenStream has not created its video worker yet, unlike a
// GENERAL_STREAMCHANGE. Scheduling eligibility is distinct, and neither
// eligibility test authenticates an FEL RPU or authorizes a non-stock codec.
constexpr bool EligibleForDeferredInitialStock(const DeferredStockInputs& v) noexcept
{
  return v.hevc && v.dolbyVision && v.profile7 && v.enhancementPresent &&
         !v.protectedContent && !v.dvd && !v.stills &&
         !v.alreadyRunningWorker;
}

constexpr bool UseDeferredInitialStock(const DeferredStockInputs& v) noexcept
{
  return kDeferredStockResearchEnabled && EligibleForDeferredInitialStock(v);
}

static_assert(!kDeferredStockResearchEnabled, "No live deferred Kodi source activation");
static_assert(!UseDeferredInitialStock({true, true, true, true, false, false, false, false}),
              "Initial-open stock deferral remains compile-time disabled");
} // namespace KODI::VIDEO::GAZELLE
