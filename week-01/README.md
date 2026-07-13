# Week 01 — When one-shot automation fails silently

*Published: July 13, 2026*

Four backlog items went to four one-shot cloud routines.

Three came back as PRs: #22, #23, and #24. The fourth produced nothing. I ran it again. Nothing again: no branch, no PR, and no failure record I could act on.

So I built the last item locally. It became PR #25: two reusable routines, `sprint-close` and `arch-decision`. Their source files added 227 lines; the full change added 484 lines across source and harness mirrors. After one fix pass, it merged on July 13.

## What I learned

Parallel dispatch made throughput look like the problem. It wasn't. The bottleneck was a failure that left nothing another worker could pick up.

A cloud routine needs to leave one of three receipts: a branch, a PR, or a failure record. "Session started" is not evidence of work.

After the second silent failure, retrying the same black box was no longer persistence. Building it locally and closing the item was the smaller move.

The useful metric was not four routines launched. It was four artifacts landed.
