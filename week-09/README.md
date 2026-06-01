# Week 09 — Lessons from shipping an Agent Cost Calculator

**Phase 3 · Tools, APIs & Multi-Agent** · *Shipped: [agent-cost-calc](https://github.com/saiviki/agent-cost-calc) → Vercel*

## What I shipped

This week I shipped the **Agent Cost Calculator** to Vercel — Layer 1 of my engineering portfolio. It models the financial reality of running stateful agentic loops in production: not the sticker price of a single call, but what an agent actually costs once it loops.

## The token-cost formula

Every provider bills the same way per request — input and output tokens priced separately, output far more expensive:

$$\text{Cost} = \frac{T_{\text{in}}}{10^6}\cdot P_{\text{in}} \;+\; \frac{T_{\text{out}}}{10^6}\cdot P_{\text{out}}$$

where $T_{\text{in}}, T_{\text{out}}$ are the input/output token counts and $P_{\text{in}}, P_{\text{out}}$ are the per-million-token prices. Output tokens dominate the bill because decode is sequential and memory-bandwidth-bound, while input (prefill) parallelizes cheaply on tensor cores.

## What surprised me — quadratic intermediate-step amplification

The big surprise was how severe **intermediate-step amplification** is. In a naive agent loop, history accumulates across iterations. Because completion APIs are stateless, the provider re-bills the *entire* conversation payload on every call. So a 10-step run is **not** 10× a single call — the accumulation follows a quadratic curve governed by the $\frac{N(N+1)}{2}$ triangular series:

$$\text{input}_{\text{total}} \;=\; N\cdot S \;+\; (u+o)\cdot\frac{N(N+1)}{2}$$

- $N$ — number of sequential steps
- $S$ — fixed system-prompt length
- $u$ — new input tokens per iteration (user message / tool output)
- $o$ — output tokens generated per turn

Run a 20-step loop at ~1,000 tokens/turn and cumulative **input** consumption exceeds **210,000 tokens** — versus the **20,000** a linear per-step estimate predicts. A **10×** miss in your infra budget.

Concrete numbers for a file-reading agent over 10 iterations on Claude Sonnet 4.6 pricing ($3.00 / 1M input, $15.00 / 1M output):

| Architecture | Cumulative input tokens | Cumulative cost | Multiplier |
|---|--:|--:|--:|
| Single-pass baseline | 9,000 | $0.03 | 1.0× |
| Constrained window | 260,000 | $0.86 | ~28.6× |
| Naive accumulation (10-step) | 472,500 | $1.49 | ~49.6× |

And caching doesn't save you here: prompt caching knocks ~90% off the static system prompt $S$, but it can't touch the dynamic $\frac{N(N+1)}{2}$ accumulation of reasoning traces and tool outputs — which is exactly the term that explodes.

## What I'd do differently

Before scaling this further, the state-management layer needs a structural refactor. The naive approach lets uncontrolled context bloat the serialization window. The fix is strict scope-limiting via **isolated subagents** plus **external state persistence**: rather than appending reasoning traces back into the prompt forever, the orchestrator offloads completed nodes to a durable PostgreSQL store and injects only the final computed variables into the next step.

## What's next

Layer 2 of the portfolio, then validation testing for Phonics Buddy. The Cost Calculator gives me a deterministic baseline for these assumptions — the floor I need before evaluating dynamic model-routing.
