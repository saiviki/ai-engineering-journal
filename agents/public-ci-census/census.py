#!/usr/bin/env python3
"""Public CI census for the AI engineering journal (PER-58).

Samples public GitHub repositories and classifies each active workflow lane
on the default branch: is it green at HEAD, or is it dark, never green,
stale, cancelled, skipped, neutral, or something else?

Unauthenticated by design: no Authorization header is ever sent and no
token environment variable is ever read. Standard library only.

Exit codes:
  0  every classified lane is OK (or nothing was classified before a stop)
  1  at least one classified lane is not OK (a successful experiment)
  2  HTTP 401/403 or a connection error (a failed run)
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

API_BASE = "https://api.github.com"
WINDOW = 30
USER_AGENT = "personal-labs-research"
ACCEPT = "application/vnd.github+json"


class RateLimitStop(Exception):
    """Raised when X-RateLimit-Remaining drops below 2."""


class ApiError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def api_get(path, query=""):
    """GET one API path. Raises RateLimitStop below 2 remaining calls."""
    global RATE_LIMIT_REMAINING
    if RATE_LIMIT_REMAINING < 2:
        raise RateLimitStop()
    url = f"{API_BASE}{path}" + (f"?{query}" if query else "")
    request = urllib.request.Request(
        url, headers={"Accept": ACCEPT, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            for name in ("X-RateLimit-Remaining", "x-ratelimit-remaining"):
                value = response.headers.get(name)
                if value is not None and value.isdigit():
                    RATE_LIMIT_REMAINING = int(value)
                    break
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise ApiError(f"http {error.code}") from None
    except (urllib.error.URLError, OSError) as error:
        raise ApiError(f"connection error: {error}") from None


RATE_LIMIT_REMAINING = 5000


def classify_lane(head_sha, runs, window):
    """Apply the PER-58 verdict table strictly in order.

    Returns (verdict, detail, completed_count). The latest completed run in
    the window decides the lane; in-progress runs never do. NEVER_GREEN is
    checked before the conclusion rules, so CANCELLED/SKIPPED/NEUTRAL and
    the upper-case "other" verdicts are reachable only when at least one
    completed success exists in the window.
    """
    completed = [r for r in runs
                 if r.get("status") == "completed" and r.get("conclusion")]
    count = len(completed)
    never_green = ("NEVER_GREEN",
                   f"no completed success in {window}-run window", count)
    if not runs:
        return "DARK", "no runs on default branch", 0
    if not any(r.get("conclusion") == "success" for r in completed):
        return never_green
    latest = completed[0]  # API returns newest first; keep the first completed
    conclusion = latest.get("conclusion")
    if conclusion == "cancelled":
        return "CANCELLED", "latest completed cancelled", count
    if conclusion == "skipped":
        return "SKIPPED", "latest completed skipped", count
    if conclusion == "neutral":
        return "NEUTRAL", "latest completed neutral", count
    if conclusion == "success":
        if latest.get("head_sha") == head_sha:
            return "OK", f"green at HEAD ({count}/{window} in window)", count
        return "STALE", "green but not at default-branch head", count
    return conclusion.upper(), f"latest completed {conclusion}", count


def select_active(workflows, cap):
    """Keep state=active only; first `cap` in API order; flag truncation."""
    active = [w for w in workflows if w.get("state") == "active"]
    return active[:cap], len(active) > cap


def print_lane(repo, head_sha, branch, truncated, lanes):
    print(f"{repo} @ {head_sha[:7]} ({branch}) truncated="
          f"{'true' if truncated else 'false'}")
    for name, verdict, detail in lanes:
        print(f"  {verdict:<9} {name}: {detail}")


def main(argv=None):
    global API_BASE, RATE_LIMIT_REMAINING
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos", nargs="+", required=True,
                        help="owner/repo list, sampled in order")
    parser.add_argument("--max-workflows", type=int, default=15)
    parser.add_argument("--window", type=int, default=WINDOW)
    parser.add_argument("--api-base", default=API_BASE,
                        help="override for tests (local fake server)")
    args = parser.parse_args(argv)

    API_BASE = args.api_base.rstrip("/")
    RATE_LIMIT_REMAINING = 5000

    print("auth=none")
    counts = {"OK": 0, "CANCELLED": 0, "SKIPPED": 0, "NEUTRAL": 0,
              "STALE": 0, "NEVER_GREEN": 0, "DARK": 0}
    other_not_ok = 0
    lanes = 0
    all_ok = True
    stopped = "none"
    header_done = False
    try:
        for repo in args.repos:
            info = api_get(f"/repos/{repo}")
            if not header_done:
                # rate_limit_remaining is the observed X-RateLimit-Remaining
                # from the first response.
                print(f"rate_limit_remaining={RATE_LIMIT_REMAINING}")
                print(f"window={args.window}")
                print(f"max_workflows={args.max_workflows}")
                header_done = True
            branch = info.get("default_branch") or ""
            head = api_get(f"/repos/{repo}/commits/{branch}")
            head_sha = head.get("sha") or ""
            listing = api_get(f"/repos/{repo}/actions/workflows",
                              query="per_page=100")
            kept, truncated = select_active(
                listing.get("workflows") or [], args.max_workflows)
            repo_lanes = []
            for workflow in kept:
                runs = api_get(
                    f"/repos/{repo}/actions/workflows/{workflow['id']}/runs",
                    query=f"branch={quote(branch)}&per_page={args.window}")
                verdict, detail, _ = classify_lane(
                    head_sha, runs.get("workflow_runs") or [], args.window)
                lanes += 1
                if verdict in counts:
                    counts[verdict] += 1
                else:
                    other_not_ok += 1
                if verdict != "OK":
                    all_ok = False
                repo_lanes.append((workflow.get("name") or "workflow",
                                   verdict, detail))
            print_lane(repo, head_sha, branch, truncated, repo_lanes)
    except RateLimitStop:
        stopped = "rate_limit"
    except ApiError as error:
        print(f"error={error.message}")
        return 2

    print(f"summary lanes={lanes} ok={counts['OK']}"
          f" cancelled={counts['CANCELLED']} skipped={counts['SKIPPED']}"
          f" neutral={counts['NEUTRAL']} stale={counts['STALE']}"
          f" never_green={counts['NEVER_GREEN']} dark={counts['DARK']}"
          f" other_not_ok={other_not_ok} stopped={stopped}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
