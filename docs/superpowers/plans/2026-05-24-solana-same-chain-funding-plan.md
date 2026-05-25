# Solana Same-Chain Funding Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Solana same-chain funding planner and make swap readiness use it before assuming the wallet already holds the exact input mint.

**Architecture:** Keep the implementation in `cmd/lpbot` beside existing Solana readiness helpers. Introduce a new read-only funding planner file, then route CLI flags from `main.go` and call the planner from existing swap readiness handlers.

**Tech Stack:** Go, existing Jupiter quote/build helpers, existing Solana RPC wallet snapshot helper

---

### Task 1: Add planner entrypoints

**Files:**
- Create: `/Users/bendu/lp-bot/v3/cmd/lpbot/solana_funding_plan.go`
- Modify: `/Users/bendu/lp-bot/v3/cmd/lpbot/main.go`

- [ ] Add `--solana-funding-plan` and related funding flags in `main.go`.
- [ ] Route the new flag to a new `runSolanaFundingPlan(...)` function.
- [ ] Keep all behavior read-only.

### Task 2: Implement same-chain funding planner

**Files:**
- Create: `/Users/bendu/lp-bot/v3/cmd/lpbot/solana_funding_plan.go`

- [ ] Resolve the Solana wallet public key from CLI/env.
- [ ] Read same-chain balances only from the existing Solana wallet snapshot helper.
- [ ] Estimate same-chain SOL value in USDC using Jupiter quotes.
- [ ] Detect whether the target mint is already sufficiently funded.
- [ ] If not, compute a pre-fund swap plan using the opposite same-chain asset.
- [ ] Surface estimated swap loss, gas, and max slippage.

### Task 3: Harden swap readiness with funding planning

**Files:**
- Modify: `/Users/bendu/lp-bot/v3/cmd/lpbot/solana_readiness.go`

- [ ] Run the funding planner before current build/sign readiness logic.
- [ ] If direct balance is enough, keep the current behavior.
- [ ] If a pre-fund swap is required, print the plan and block direct target-swap readiness from being reported as ready from current balances.

### Task 4: Document the same-chain constraint

**Files:**
- Create: `/Users/bendu/lp-bot/v3/docs/superpowers/specs/2026-05-24-solana-same-chain-funding-design.md`
- Create: `/Users/bendu/lp-bot/v3/docs/superpowers/plans/2026-05-24-solana-same-chain-funding-plan.md`

- [ ] Document that funding valuation is strictly same-chain only.
- [ ] Document that this first implementation only supports current Solana wallet assets `SOL` and `USDC`.
