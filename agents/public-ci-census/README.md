# Public CI census

A content experiment for the AI engineering journal (issue PER-58). It
samples public GitHub repositories and classifies every active workflow
lane on the default branch: is CI green at HEAD, or is it dark, never
green, stale, cancelled, skipped, neutral, or something else?

Unauthenticated by design. The process never sends an `Authorization`
header, never reads `GH_TOKEN` or `GITHUB_TOKEN`, and never authenticates
to raise the rate limit. Python 3 standard library only
(`urllib.request`).

## Command

From the repository root, on the `per-53-public-ci-census` branch:

```bash
env -u GH_TOKEN -u GITHUB_TOKEN python3 agents/public-ci-census/census.py \
  --repos pallets/click BurntSushi/ripgrep actions/checkout \
  --max-workflows 15 \
  | tee agents/public-ci-census/receipt.txt
sha256sum agents/public-ci-census/receipt.txt
```

Exit `0` when every classified lane is `OK`; exit `1` when at least one
lane is not `OK` (that is a successful experiment, not a failure); exit
`2` on HTTP 401/403 or a connection error.

## Receipt (2026-10-08)

Run of the command above. `rate_limit_remaining=59` is the observed
`X-RateLimit-Remaining` from the first response — the unauthenticated
60-per-hour quota, which is itself evidence the run sent no token.
`sha256(receipt.txt) =
dcc297c5e1ab6f4f43afda6575da49dde6b1239a96dfe6e95cd14c8319e5267d`.

```text
auth=none
rate_limit_remaining=59
window=30
max_workflows=15
pallets/click @ 2247b35 (main) truncated=false
  OK        Lock inactive closed issues: green at HEAD (30/30 in window)
  OK        Nightly tests: green at HEAD (30/30 in window)
  OK        pre-commit: green at HEAD (30/30 in window)
  DARK      Publish: no runs on default branch
  NEVER_GREEN QualityRisk Bootstrap (Tests + Sonar): no completed success in 30-run window
  OK        Tests: green at HEAD (30/30 in window)
  STALE     GitHub Actions security analysis with zizmor: green but not at default-branch head
  STALE     Copilot: green but not at default-branch head
  DARK      Copilot code review: no runs on default branch
  STALE     Dependency Graph: green but not at default-branch head
BurntSushi/ripgrep @ 3fce3b5 (master) truncated=false
  DARK      ci: no runs on default branch
  OK        ci: green at HEAD (30/30 in window)
  DARK      Test: no runs on default branch
  DARK      plumber: no runs on default branch
  DARK      release: no runs on default branch
  STALE     Copilot: green but not at default-branch head
  DARK      Copilot code review: no runs on default branch
actions/checkout @ f548e57 (main) truncated=false
  ACTION_REQUIRED Build and Test: latest completed action_required
  ACTION_REQUIRED Licensed: latest completed action_required
  ACTION_REQUIRED Check dist: latest completed action_required
  OK        CodeQL: green at HEAD (30/30 in window)
  DARK      Update Main Version: no runs on default branch
  NEVER_GREEN NodeJS with Webpack: no completed success in 30-run window
  DARK      Publish test-ubuntu-git Container: no runs on default branch
  OK        Dependabot Updates: green at HEAD (30/30 in window)
  NEVER_GREEN CodeQL Advanced: no completed success in 30-run window
  NEVER_GREEN .github/workflows/generator-generic-ossf-slsa3-publish.yml: no completed success in 30-run window
  DARK      Copilot code review: no runs on default branch
  DARK      Copilot cloud agent: no runs on default branch
  OK        Copilot: green at HEAD (7/30 in window)
summary lanes=30 ok=8 cancelled=0 skipped=0 neutral=0 stale=4 never_green=4 dark=11 other_not_ok=3 stopped=none
```

A zero cancelled count is still a receipt: on this day, none of the 30
sampled lanes had a cancelled run as its latest completed run.

## Reading the verdicts

- `OK` — latest completed run on the default branch is a success whose
  commit is the branch head.
- `DARK` — the workflow is active but has never run on the default branch.
- `STALE` — green, but the green run predates the current head.
- `NEVER_GREEN` — no completed success anywhere in the 30-run window.
- `SKIPPED` and `NEUTRAL` count as success for dependent GitHub checks,
  but the census keeps them visible instead of calling them `OK`.
- Other conclusions (`FAILURE`, `TIMED_OUT`, `ACTION_REQUIRED`, …) are
  printed in upper case.

## Bounds

The sample is three third-party public repositories, fetched once,
read-only. The census does not scan this repository's own account and
collects no credentials. This is a content experiment, not a product:
no merge, deploy, publish, or scheduling comes from it.
