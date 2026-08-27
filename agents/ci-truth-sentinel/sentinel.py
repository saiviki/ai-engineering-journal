#!/usr/bin/env python3
"""ci-truth-sentinel: find CI lanes that look green because nobody looked.

A dashboard that only counts red misses three ways a lane can lie:
  - CANCELLED renders as not-red (so does "no run at all")
  - the latest success can be commits behind HEAD
  - a lane can have NEVER been green since creation (0/N = unimplemented, not flaky)

Usage: python3 sentinel.py OWNER/REPO [OWNER/REPO ...] [--json]
Needs: gh CLI, authenticated. Read-only. Exit 1 if any lane is not OK.
"""
import json, subprocess, sys

def gh(path):
    return json.loads(subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=True).stdout)

def audit(repo):
    branch = gh(f"repos/{repo}")["default_branch"]
    head = gh(f"repos/{repo}/commits/{branch}")["sha"]
    lanes = []
    for wf in gh(f"repos/{repo}/actions/workflows?per_page=100")["workflows"]:
        if wf["state"] != "active":
            continue
        runs = gh(f"repos/{repo}/actions/workflows/{wf['id']}/runs"
                  f"?branch={branch}&per_page=50")["workflow_runs"]
        done = [r for r in runs if r["status"] == "completed"]
        greens = [r for r in done if r["conclusion"] == "success"]
        if not runs:
            verdict, detail = "DARK", "no runs on default branch"
        elif not greens:
            # ponytail: per_page=50 window, not full history; a lane green >50 runs ago still shows NEVER_GREEN
            verdict, detail = "NEVER_GREEN", f"0/{len(done)} completed runs green (last 50)"
        elif done and done[0]["conclusion"] == "cancelled":
            n = next((i for i, r in enumerate(done) if r["conclusion"] != "cancelled"), len(done))
            verdict, detail = "CANCELLED", f"latest {n} run(s) cancelled; last real verdict: {done[n]['conclusion'] if n < len(done) else 'none in window'}"
        elif greens[0]["head_sha"] != head:
            verdict, detail = "STALE", f"last success at {greens[0]['head_sha'][:7]}, HEAD is {head[:7]}"
        elif done[0]["conclusion"] != "success":
            verdict, detail = done[0]["conclusion"].upper(), f"latest completed run {done[0]['conclusion']}"
        else:
            verdict, detail = "OK", f"green at HEAD ({len(greens)}/{len(done)} green in window)"
        lanes.append({"workflow": wf["name"], "verdict": verdict, "detail": detail})
    return {"repo": repo, "branch": branch, "head": head[:7], "lanes": lanes}

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    reports, bad = [audit(r) for r in args], 0
    if "--json" in sys.argv:
        print(json.dumps(reports, indent=2))
    for rep in reports:
        if "--json" not in sys.argv:
            print(f"\n{rep['repo']} @ {rep['head']} ({rep['branch']})")
            for l in rep["lanes"]:
                flag = "  " if l["verdict"] == "OK" else "⚠️ "
                print(f"  {flag}{l['verdict']:<12} {l['workflow']}: {l['detail']}")
        bad += sum(1 for l in rep["lanes"] if l["verdict"] != "OK")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
