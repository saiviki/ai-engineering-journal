# ci-truth-sentinel — find CI lanes that are green because nobody looked

A ~90-line read-only auditor that answers one question per workflow lane: **is this actually verified at HEAD, or does it just render as not-red?**

## Why

In one week I hit the same defect four times, in four unrelated systems: a dashboard said "all green" while

- two lanes' latest runs were **CANCELLED** (renders exactly like a pass on anything that only counts red),
- one lane's last success was **five commits behind HEAD**,
- and one scheduled job had **never been green once** — not flaky, *never implemented as a working gate*.

The pattern: red is the only state dashboards treat as a signal, so every non-red failure mode is invisible. This tool makes the other three states first-class verdicts.

## Verdicts

| Verdict | Meaning | Why "not red" hides it |
|---|---|---|
| `OK` | latest completed run green **at HEAD** | — |
| `CANCELLED` | latest run(s) cancelled; reports the last real verdict | cancelled ≠ failed on most UIs |
| `STALE` | last success is behind HEAD (shows both SHAs) | old green reads as current green |
| `NEVER_GREEN` | 0/N completed runs green in window | 0-for-N is *unimplemented*, not unlucky |
| `DARK` | no runs at all on the default branch | absence renders as nothing |

Exit code `1` if any lane is not `OK` — drop it in cron or a meta-workflow.

## Run it

```bash
# needs: gh CLI, authenticated; python3; nothing else
python3 sentinel.py OWNER/REPO [OWNER/REPO ...] [--json]
```

## Real output (my own repos, first ever run)

```
saiviki/storyboard_generator @ e031c3f (main)
    OK           BMAD Story Dispatch: green at HEAD (18/50 green in window)
  ⚠️ DARK         Build Installers: no runs on default branch
    OK           CI: green at HEAD (19/50 green in window)
  ⚠️ NEVER_GREEN  Jules Resolver: 0/12 completed runs green (last 50)
  ⚠️ STALE        PR-Agent: last success at 9d894ba, HEAD is e031c3f
    OK           Security: green at HEAD (6/7 green in window)

saiviki/lifestyle-app @ 7f47c89 (main)
  ⚠️ NEVER_GREEN  CI: 0/8 completed runs green (last 50)
  ⚠️ STALE        Dependabot Updates: last success at 29ca040, HEAD is 7f47c89
```

I wrote this tool because of a client-side incident, then pointed it at my own side projects — and found a resolver workflow that has failed all 12 of its runs and a CI lane that has *never* passed. I would have told you both repos "have CI."

## How it works

Pure GitHub API via `gh api` (no tokens in the repo, your existing `gh auth` is the credential): list active workflows → last 50 default-branch runs per workflow → classify. No LLM in the loop on purpose — this is a *measurement* tool, and measurements should be deterministic. Pipe `--json` into your favourite model if you want a prose briefing.

## Limits (known, deliberate)

- 50-run window: a lane last green 51+ runs ago shows `NEVER_GREEN`. For a lane that runs nightly that's ~7 weeks of history — if it hasn't been green in 7 weeks, the verdict is morally correct anyway.
- Lane = workflow. Matrix jobs inside one workflow share a verdict.
- `gh` rate limits apply; ~2 + workflows API calls per repo.

## Going further

- Run it from a meta-workflow on a schedule; alert on exit 1.
- Track `green/total` over time — the derivative ("this gate is *decaying*") is the early warning.
- The strict rule that motivated it: **any 0/N gate blocks a release freeze** — a gate that has never fired is a decoration, not a control.
