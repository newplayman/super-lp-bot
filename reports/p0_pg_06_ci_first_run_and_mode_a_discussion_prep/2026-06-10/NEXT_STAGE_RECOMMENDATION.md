# NEXT_STAGE_RECOMMENDATION — P0-PG-06

## What this stage did

- Triggered the canonical GitHub Actions workflow
  `shadow-smoke-gate.yml` for the first time via a no-op comment
  commit to `scripts/run_shadow_smoke.sh` (because `gh` is not
  authenticated on this host; `gh workflow run` is not available).
- Authored `MODE_A_DISCUSSION_DRAFT.md` enumerating Mode A's
  boundary, three candidate options (A1 / A2 / A3), the P2 risk
  acceptance matrix, the proposed safety contract, and the
  three-stage gating (discussion → plan → execute) that any
  future Mode A execution must satisfy.
- Documented the trigger and the inability to read the CI result
  in `CI_FIRST_RUN_TRIGGER_REPORT.md` and
  `CI_FIRST_RUN_RESULT.md`.

## What this stage did NOT do

- Did not run Mode A.
- Did not run Mode B.
- Did not execute any canary / live / paper / probe path.
- Did not sign or broadcast any transaction.
- Did not read CI run results (auth absent; recorded honestly as
  `ci_result_verified = false`).
- Did not poll for the CI run to complete.
- Did not commit the r1 modified file.
- Did not modify R1 reports / data dirs.

## What the next stage should be

The single recommended next stage, per the user's directive and the
MODE_A_DISCUSSION_DRAFT.md gating:

### Option 1 (preferred): manual CI observation + small follow-up

A reviewer with `gh` authenticated against the repo observes the
workflow run that was triggered by this stage's commit. The
reviewer records the `run id`, `html_url`, `status`, `conclusion`,
and the per-step results. If the conclusion is `success`, the
canonical CI path is exercised and the readiness matrix's
dimension #18 closes. If `failure`, the reviewer captures the
failing step and opens a follow-up stage.

This is not a Claude stage — it is a manual observation step. The
reviewer writes the observed values into the existing
`CI_FIRST_RUN_RESULT.md` (or a follow-up commit) so that future
reviewers have a known-good CI baseline.

### Option 2: plan stage

If ChatGPT accepts this draft and the manual CI observation is
green (or ChatGPT explicitly accepts a Plan stage without
requiring the manual observation first), the next stage is:

```
LP_BOT_ENGINEERING_MODE_A1_SHADOW_CONTINUITY_SOAK_PLAN_V1
```

(or `_MODE_A2_*_PLAN_V1` or `_MODE_A3_*_PLAN_V1` — one of the
three options in the draft).

The plan stage must:

- Pick exactly one of A1 / A2 / A3.
- Carry the relevant subset of the P2 risk acceptance matrix into
  its own `P2_RISK_ACCEPTANCE_MATRIX.md`.
- Specify exact duration, exact log / report output paths, exact
  abort conditions, exact success/fail criteria.
- NOT execute the plan. Plans are non-executing documents.

The plan stage lands on `origin/feat/supabase-postgres-deployment`
and is reviewed by ChatGPT. Only after ChatGPT accepts the plan
stage can an `EXECUTE` stage be authored.

### Option 3 (not recommended in this draft)

If ChatGPT decides any of the three Mode A options is unsafe or
premature, the next stage is to address one of the P2 items (e.g.
land the chain-type fix at `cmd/lpbot/position_mark.go:220`),
re-derive the readiness verdict, and re-open the discussion. This
draft does not recommend Option 3 because all eight P2 items are
either sequencing-only (CI first-run), log noise (chain-type
WARN), or already explicitly tracked in canonical SAFETY_LOCKS_RECHECK.json
files.

## Strict non-goal

This stage does **not** authorize any Mode A action. The user's
directive "完成后不要进入 Mode A" applies to this stage's
completion. Any subsequent stage that wants to authorize Mode A
must explicitly name the action, name the option (A1 / A2 / A3),
include the word `EXECUTE` in its name, and go through the
three-stage gating described in
`MODE_A_DISCUSSION_DRAFT.md` §5.