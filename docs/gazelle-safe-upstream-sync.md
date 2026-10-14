# Safe syncing angelcode1/xbmc with xbmc/xbmc

Last set up: 2026-10-14. GitHub upstream is `xbmc/xbmc:master` (not `main`).
This fork uses four roles:

| Ref | Role |
| --- | --- |
| `xbmc/xbmc:master` | Unmodified external upstream |
| `angelcode1/xbmc:master` | Upstream tracking / fork default, keeping original fork history |
| `angelcode1/xbmc:android-firetv-unified` | Canonical **combined Fire TV build** with AACS/MakeMKV, physical Blu-ray/VFS, and Dolby Vision P7 FEL |
| `android-firetv-bluray`, `android-firetv-fel` | Issue work branches, fast-forwarded from unified if they have no divergent work |

## Automated **proposals**, not automated overwrites

1. **Upstream -> fork master:** [Gazelle safe upstream sync](../.github/workflows/gazelle-safe-upstream-sync.yml) is manually dispatchable and checks weekly, Monday at 03:17 UTC. If upstream is not already an ancestor of fork master, it merges upstream into a *new staging branch* with a normal two-parent merge commit, and opens a PR targeting fork `master`. It does **not** push to or overwrite `master`, use `reset`, rebase, squash, or force push. If source conflicts exist it fails with a list of conflicting files and leaves remote branches unchanged. **Review the PR and use 'Create a merge commit', not 'Squash and merge'.**
2. **Fork master -> unified:** [Gazelle forward sync](../.github/workflows/gazelle-forward-sync.yml) is manually dispatchable and runs on pushes to `master`. It prepares a fresh staging branch from `android-firetv-unified`, merges `master`, checks that the Gazelle AACS and FEL source still exists and creates a PR **into the unified branch**. Conflicts fail closed: no remote ref changes. Manual resolution must preserve both upstream and the custom Fire TV changes.
3. **Preservation gate:** [Gazelle preserve features](../.github/workflows/gazelle-preserve-features.yml) runs on PRs into, and direct pushes to, `android-firetv-unified`. It rejects disappearance of AACS phase-marker instrumentation, LibMMBD Android loader patch, optical/UDF paths, Dolby capability and MediaFormat logs, or the routing-core-only packaging contract. This is a **source-preservation gate**, not a complete Android compile, a passing AACS decrypt test or a FEL pixel-reconstruction test.
4. **Unified -> issue refs:** [Gazelle issue ref fast-forward](../.github/workflows/gazelle-fast-forward-issue-branches.yml) checks `android-firetv-bluray` and `android-firetv-fel` after each push to the unified branch. It updates each only by **plain fast-forward**, never force. If either has independent commits not yet in unified, it refuses to overwrite and reports the divergent branch. Merge that work into unified first.

**Important:** GitHub Actions' ability to create PRs may require repository Settings -> Actions -> General -> Workflow permissions, with pull-request creation enabled. If the staging push passes but PR creation is denied, open a PR manually from the new `sync/` branch; the code was not lost. Existing branch protection rules, if any, still apply. GitHub Actions pushes made with `GITHUB_TOKEN` generally do not trigger another GitHub Actions workflow, so use **Run workflow** manually when needed to finish the next stage.

## Review before accepting an upstream update

- Check the merge has *both parent histories* and use a **merge commit**, never a force-push or reset to upstream.
- Ensure physical Blu-ray libbluray, AACS, UDF, MakeMKV helper, Kodi VFS changes and DV P7 / FEL code remain. Do not automatically choose `--theirs` on conflicts.
- Require the Gazelle preservation gate and a fresh full ARMv7 **routing core** build from the merged `android-firetv-unified` commit before private `cube3` optical/MMBD packaging.
- Only install the signed **private integrated APK**, not the public routing-core diagnostic artifact, and verify its signer matches the installed Kodi signer before `adb install -r`. The external root broker and optical daemon are not bundled in the APK.
- Keep existing working P8 Dolby Vision output and the audio/HDMI passthrough setup unchanged. Neither source merge nor a successful CI build proves P7 FEL reconstruction or protected AACS playback.

## Manual conflict resolution (no force-push)

```bash
git clone --filter=blob:none https://github.com/angelcode1/xbmc.git
cd xbmc
git remote add kodi-upstream https://github.com/xbmc/xbmc.git
git fetch origin master android-firetv-unified
git fetch kodi-upstream master

# First, if needed, merge upstream into fork master via a review branch.
git switch -c sync/manual-kodi-upstream origin/master
git merge --no-ff kodi-upstream/master
# Resolve conflicts deliberately; do not choose theirs for all files.
git status
git push -u origin sync/manual-kodi-upstream
# Open PR into master; merge after review.

# After the PR to master has merged, update local refs:
git fetch origin master android-firetv-unified
git switch -c sync/manual-to-unified origin/android-firetv-unified
git merge --no-ff origin/master
# Resolve custom vs upstream changes, then inspect and run checks.
git status
git push -u origin sync/manual-to-unified
# Open PR into android-firetv-unified; merge after review.
```

Branch names in the examples should be made unique for each sync attempt. Neither operation modifies existing live refs until its PR is deliberately merged. If the merge conflicts, Git will stop before the push; resolve only the affected files while keeping both the upstream and Gazelle changes.

## Historical safety snapshots

`backup/master-pre-upstream-sync-20261014`,
`backup/blu-ray-pre-unify-20261014`, and `backup/fel-pre-unify-20261014`
are preserved; do not delete these to 'clean up' syncs. The 2026-10-14 unified-source merge `e7c93d107835ffb94a9e899ba0e3eb580a10be4c` includes the old FEL source and AACS diagnostic histories as separate parents. Normal merges preserve these commits.
