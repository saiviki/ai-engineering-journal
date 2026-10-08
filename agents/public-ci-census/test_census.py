"""Offline tests for agents/public-ci-census/census.py.

Stdlib only. A local fake GitHub API server backs the end-to-end tests;
census.py is pointed at it with the --api-base test seam. No real network,
no credentials: the fake server rejects any request carrying an
Authorization header, and the subprocess runs with sentinel GH_TOKEN /
GITHUB_TOKEN values that must never be read or sent.

Run: python3 agents/public-ci-census/test_census.py
"""
import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import census  # noqa: E402

HEAD = "3d7f2ab1c4e5f60718293a4b5c6d7e8f90123456"
UA = "personal-labs-research"
ACCEPT = "application/vnd.github+json"


def wf(wid, name, state="active"):
    return {"id": wid, "name": name, "state": state,
            "path": f".github/workflows/{name.lower()}.yml"}


def runrow(conclusion, sha=HEAD, rid=1, name="WF", status="completed"):
    return {"id": rid, "name": name, "head_branch": "develop", "head_sha": sha,
            "status": status, "conclusion": conclusion}


class FakeGitHub:
    """Minimal fake of the endpoints census.py hits. Records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.requests.append((self.path, dict(self.headers)))
                if "Authorization" in self.headers:
                    self._send(500, {"message": "census must never authenticate"})
                    return
                path = self.path.split("?", 1)[0]
                entry = outer.routes.get(path)
                if entry is None:
                    self._send(404, {"message": "not found"})
                    return
                status, payload = entry[0], entry[1]
                extra = entry[2] if len(entry) > 2 else {}
                self._send(status, payload,
                           {"X-RateLimit-Remaining": str(extra.get("remaining", 4990))})

            def _send(self, status, payload, headers=None):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def paths(self):
        return [p.split("?", 1)[0] for p, _ in self.requests]

    def queries(self, path):
        return [p.split("?", 1)[1] for p, _ in self.requests
                if p.split("?", 1)[0] == path]


def run_census(base, *cli):
    env = dict(os.environ)
    env["GH_TOKEN"] = "sentinel-never-read"
    env["GITHUB_TOKEN"] = "sentinel-never-read"
    return subprocess.run(
        [sys.executable, str(HERE / "census.py"), "--api-base", base, *cli],
        capture_output=True, text=True, env=env, timeout=120)


def ok_repo_routes(repo="octo/hello", branch="develop"):
    r = f"/repos/{repo}"
    return {
        r: (200, {"full_name": repo, "default_branch": branch}),
        f"{r}/commits/{branch}": (200, {"sha": HEAD}),
        f"{r}/actions/workflows": (200, {"total_count": 3, "workflows": [
            wf(11, "Tests"), wf(12, "Lint"), wf(13, "Deploy", state="inactive")]}),
        f"{r}/actions/workflows/11/runs": (200, {"total_count": 1,
            "workflow_runs": [runrow("success", rid=901, name="Tests")]}),
        f"{r}/actions/workflows/12/runs": (200, {"total_count": 1,
            "workflow_runs": [runrow("success", rid=902, name="Lint")]}),
    }


class VerdictOrder(unittest.TestCase):
    """Verdicts apply in order; in-progress runs never decide a lane."""

    def test_dark_when_no_runs(self):
        self.assertEqual(census.classify_lane(HEAD, [], 30),
                         ("DARK", "no runs on default branch", 0))

    def test_never_green_with_completed_failures(self):
        verdict, detail, done = census.classify_lane(
            HEAD, [runrow("failure")], 30)
        self.assertEqual(verdict, "NEVER_GREEN")
        self.assertEqual(done, 1)
        self.assertIn("no completed success", detail)

    def test_never_green_when_only_in_progress(self):
        self.assertEqual(
            census.classify_lane(
                HEAD, [runrow(None, status="in_progress")], 30)[0],
            "NEVER_GREEN")

    def test_cancelled_beats_older_success(self):
        self.assertEqual(
            census.classify_lane(
                HEAD, [runrow("cancelled", rid=2), runrow("success", rid=1)], 30)[0],
            "CANCELLED")

    def test_skipped(self):
        # A completed success elsewhere in the window lets SKIPPED surface.
        self.assertEqual(
            census.classify_lane(
                HEAD, [runrow("skipped", rid=2), runrow("success", rid=1)], 30)[0],
            "SKIPPED")

    def test_skipped_alone_is_never_green(self):
        # Spec order: NEVER_GREEN precedes the conclusion rules, so a window
        # with no completed success at all cannot be SKIPPED.
        self.assertEqual(
            census.classify_lane(HEAD, [runrow("skipped")], 30)[0],
            "NEVER_GREEN")

    def test_neutral(self):
        self.assertEqual(
            census.classify_lane(
                HEAD, [runrow("neutral", rid=2), runrow("success", rid=1)], 30)[0],
            "NEUTRAL")

    def test_stale_when_success_not_at_head(self):
        self.assertEqual(
            census.classify_lane(HEAD, [runrow("success", sha="a" * 40)], 30)[0],
            "STALE")

    def test_ok(self):
        self.assertEqual(
            census.classify_lane(
                HEAD, [runrow("success", rid=2), runrow("failure", rid=1)], 30),
            ("OK", "green at HEAD (2/30 in window)", 2))

    def test_in_progress_latest_does_not_decide(self):
        self.assertEqual(
            census.classify_lane(
                HEAD,
                [runrow(None, status="in_progress", rid=2),
                 runrow("success", rid=1)], 30)[0],
            "OK")

    def test_other_conclusions_print_upper(self):
        self.assertEqual(
            census.classify_lane(
                HEAD, [runrow("timed_out", rid=2), runrow("success", rid=1)],
                30)[0],
            "TIMED_OUT")
        self.assertEqual(
            census.classify_lane(
                HEAD, [runrow("action_required", rid=2), runrow("success", rid=1)],
                30)[0],
            "ACTION_REQUIRED")

    def test_timed_out_alone_is_never_green(self):
        self.assertEqual(
            census.classify_lane(HEAD, [runrow("timed_out")], 30)[0],
            "NEVER_GREEN")


class SelectActive(unittest.TestCase):
    def test_under_cap(self):
        kept, truncated = census.select_active(
            [wf(i, f"W{i}") for i in range(15)], 15)
        self.assertEqual(len(kept), 15)
        self.assertFalse(truncated)

    def test_over_cap_takes_first_in_api_order(self):
        kept, truncated = census.select_active(
            [wf(i, f"W{i}") for i in range(17)], 15)
        self.assertEqual([w["id"] for w in kept], list(range(15)))
        self.assertTrue(truncated)

    def test_inactive_filtered_before_cap(self):
        kept, truncated = census.select_active(
            [wf(i, f"W{i}", state="inactive") for i in range(5)]
            + [wf(100 + i, f"A{i}") for i in range(10)], 15)
        self.assertEqual(len(kept), 10)
        self.assertFalse(truncated)


class SourceHygiene(unittest.TestCase):
    def test_no_token_env_or_auth_header_in_source(self):
        source = (HERE / "census.py").read_text()
        self.assertNotIn("GH_TOKEN", source)
        self.assertNotIn("GITHUB_TOKEN", source)
        # The word may appear in prose; it must never be set as a header.
        self.assertNotRegex(source, r"""["']Authorization["']\s*[:=]""")
        self.assertIn("urllib.request", source)


class EndToEnd(unittest.TestCase):
    def assert_common_headers(self, fake):
        for _, headers in fake.requests:
            self.assertNotIn("Authorization", headers)
            self.assertEqual(headers.get("User-Agent"), UA)
            self.assertEqual(headers.get("Accept"), ACCEPT)

    def test_all_ok_exit_0_and_exact_stdout(self):
        fake = FakeGitHub(ok_repo_routes())
        try:
            proc = run_census(fake.base, "--repos", "octo/hello",
                              "--max-workflows", "15")
        finally:
            fake.stop()
        expected = [
            "auth=none",
            "rate_limit_remaining=4990",
            "window=30",
            "max_workflows=15",
            f"octo/hello @ {HEAD[:7]} (develop) truncated=false",
            "  OK        Tests: green at HEAD (1/30 in window)",
            "  OK        Lint: green at HEAD (1/30 in window)",
            "summary lanes=2 ok=2 cancelled=0 skipped=0 neutral=0 stale=0"
            " never_green=0 dark=0 other_not_ok=0 stopped=none",
        ]
        self.assertEqual(proc.stdout.splitlines(), expected)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(sorted(set(fake.paths())), sorted([
            "/repos/octo/hello",
            "/repos/octo/hello/commits/develop",
            "/repos/octo/hello/actions/workflows",
            "/repos/octo/hello/actions/workflows/11/runs",
            "/repos/octo/hello/actions/workflows/12/runs",
        ]))
        self.assertEqual(fake.queries("/repos/octo/hello/actions/workflows"),
                         ["per_page=100"])
        self.assertEqual(
            fake.queries("/repos/octo/hello/actions/workflows/11/runs"),
            ["branch=develop&per_page=30"])
        self.assert_common_headers(fake)

    def test_not_ok_lane_exits_1(self):
        routes = ok_repo_routes()
        routes["/repos/octo/hello/actions/workflows/11/runs"] = (
            200, {"total_count": 2,
                  "workflow_runs": [runrow("failure", rid=901, name="Tests"),
                                    runrow("success", rid=900, name="Tests")]})
        fake = FakeGitHub(routes)
        try:
            proc = run_census(fake.base, "--repos", "octo/hello",
                              "--max-workflows", "15")
        finally:
            fake.stop()
        self.assertIn("  FAILURE   Tests: latest completed failure",
                      proc.stdout.splitlines())
        self.assertIn(
            "summary lanes=2 ok=1 cancelled=0 skipped=0 neutral=0 stale=0"
            " never_green=0 dark=0 other_not_ok=1 stopped=none",
            proc.stdout.splitlines())
        self.assertEqual(proc.returncode, 1)

    def test_rate_limit_below_2_stops_before_next_request(self):
        routes = {"/repos/octo/hello":
                  (200, {"full_name": "octo/hello",
                         "default_branch": "develop"}, {"remaining": 1})}
        fake = FakeGitHub(routes)
        try:
            proc = run_census(fake.base, "--repos", "octo/hello",
                              "--max-workflows", "15")
        finally:
            fake.stop()
        self.assertEqual(len(fake.paths()), 1)
        self.assertEqual(proc.stdout.splitlines(), [
            "auth=none",
            "rate_limit_remaining=1",
            "window=30",
            "max_workflows=15",
            "summary lanes=0 ok=0 cancelled=0 skipped=0 neutral=0 stale=0"
            " never_green=0 dark=0 other_not_ok=0 stopped=rate_limit",
        ])
        self.assertEqual(proc.returncode, 0)

    def test_truncation_marks_repo_and_caps_runs(self):
        r = "/repos/octo/hello"
        routes = ok_repo_routes()
        routes[f"{r}/actions/workflows"] = (200, {"total_count": 17,
            "workflows": [wf(i, f"W{i}") for i in range(17)]})
        for i in range(17):
            routes[f"{r}/actions/workflows/{i}/runs"] = (
                200, {"total_count": 1,
                      "workflow_runs": [runrow("success", rid=i, name=f"W{i}")]})
        fake = FakeGitHub(routes)
        try:
            proc = run_census(fake.base, "--repos", "octo/hello",
                              "--max-workflows", "15")
        finally:
            fake.stop()
        self.assertIn(f"octo/hello @ {HEAD[:7]} (develop) truncated=true",
                      proc.stdout.splitlines())
        run_paths = [p for p in fake.paths() if p.endswith("/runs")]
        self.assertEqual(len(run_paths), 15)
        self.assertEqual(
            [int(p.rsplit("/", 2)[-2]) for p in run_paths], list(range(15)))
        self.assertIn(
            "summary lanes=15 ok=15 cancelled=0 skipped=0 neutral=0 stale=0"
            " never_green=0 dark=0 other_not_ok=0 stopped=none",
            proc.stdout.splitlines())
        self.assertEqual(proc.returncode, 0)

    def test_no_active_workflows_still_a_receipt(self):
        routes = ok_repo_routes()
        routes["/repos/octo/hello/actions/workflows"] = (
            200, {"total_count": 1,
                  "workflows": [wf(13, "Deploy", state="inactive")]})
        fake = FakeGitHub(routes)
        try:
            proc = run_census(fake.base, "--repos", "octo/hello",
                              "--max-workflows", "15")
        finally:
            fake.stop()
        self.assertIn(
            "summary lanes=0 ok=0 cancelled=0 skipped=0 neutral=0 stale=0"
            " never_green=0 dark=0 other_not_ok=0 stopped=none",
            proc.stdout.splitlines())
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("/runs", " ".join(fake.paths()))

    def test_http_403_exits_2(self):
        fake = FakeGitHub({"/repos/octo/hello": (403, {"message": "forbidden"})})
        try:
            proc = run_census(fake.base, "--repos", "octo/hello",
                              "--max-workflows", "15")
        finally:
            fake.stop()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout.splitlines()[0], "auth=none")
        self.assertEqual(proc.stdout.splitlines()[-1], "error=http 403")

    def test_connection_error_exits_2(self):
        proc = run_census("http://127.0.0.1:9", "--repos", "octo/hello",
                          "--max-workflows", "15")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout.splitlines()[0], "auth=none")
        self.assertTrue(proc.stdout.splitlines()[-1].startswith("error="))


if __name__ == "__main__":
    unittest.main(verbosity=2)
