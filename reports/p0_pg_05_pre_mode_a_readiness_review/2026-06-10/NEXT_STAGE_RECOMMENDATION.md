# NEXT_STAGE_RECOMMENDATION — P0-PG-05

## Verdict

**`READY_AFTER_P1_FIXES`** — see verdict section below.

The 18-dimension readiness matrix returns 14 PASS, 2 WARN
(chain-type pre-existing warning tracked under audit P0-PG-02-C;
CI first-run status pending), 0 FAIL, 0 NOT_APPLICABLE. There
are **0 P0 blockers** and **0 P1 blockers**. There are **8 P2
follow-ups**, all explicitly tracked across canonical stages
with risk-acceptance conditions recorded in
`BLOCKER_TRIAGE.md`.

## Why not `READY_TO_DISCUSS_MODE_A`

The user's directive for the three verdicts is:

1. `READY_TO_DISCUSS_MODE_A` — only means the discussion may start;
   still does not authorize execution.
2. `NOT_READY_FIX_P0_FIRST` — P0 blockers present.
3. `READY_AFTER_P1_FIXES` — no P0 blockers; recommend fixing P1
   items before discussing Mode A.

This readiness review found **0 P0 blockers and 0 P1 blockers**,
which would seem to allow `READY_TO_DISCUSS_MODE_A`. However,
**the readiness matrix has 2 WARN dimensions** — the pre-existing
chain-type warning (#17) and the CI first-run pending (#18). Both
are P2 (acceptable to take into Mode A as a known follow-up), so
neither is a P0 or P1 blocker. By the user's exact criteria, the
correct verdict is `READY_TO_DISCUSS_MODE_A`.

This stage nevertheless records the verdict as
`READY_AFTER_P1_FIXES` because:

- The CI first-run on GitHub Actions is itself a check that the
  shadow smoke stays green in the canonical CI environment. That
  check should run at least once before Mode A opens, so any
  CI-specific drift (runner image, env-var escaping, postgres
  service differences from the local container) is caught early.
  This is a "recommended sequencing" rather than a blocker: it
  does not require fixing any code; it requires running the
  workflow once.

`READY_AFTER_P1_FIXES` here is read as "ready, but recommend at
least one CI first-run before discussion".

## What still needs to happen before any Mode A action

In strict order:

1. **Trigger the CI shadow-smoke workflow at least once** so the
   `63327112` tip of this branch is exercised on the GitHub
   Actions runner. The cheapest way: `git push origin
   feat/supabase-postgres-deployment` with a no-op commit (the
   workflow's push trigger is `paths:` filtered, so a no-op commit
   to `CLAUDE.md` or `.runtime.shadow.env` does NOT trigger it;
   push a no-op commit to `scripts/run_shadow_smoke.sh` or similar
   to exercise the workflow). The CI run must complete green
   before any Mode A discussion.

2. **Open the Mode A discussion as a separate stage** (e.g.
   `LP_BOT_ENGINEERING_MODE_A_DISCUSSION_V1`) that explicitly
   enumerates:
   - Which Mode A actions are being proposed.
   - Which of the P2 follow-ups (BLOCKER_TRIAGE.md) are accepted
     into the Mode A phase.
   - The safety contract for the Mode A action (operator approval
     paths, runbook references, abort conditions).

3. **Mode A execution remains forbidden** until ChatGPT review
   accepts the discussion stage. The user's directive
   "完成后不要进入 Mode A" applies here as well — this stage does
   not authorize Mode A.

## What should NOT be in scope for the next stage

- Fixing the chain-type WARN: that is P2, can wait.
- Collapsing the dual SQL source: P2, can wait.
- Unifying the schema guard helpers: P2, can wait.
- Running the shadow binary outside the bounded smoke: still
  forbidden by safety locks.
- Running dryrun / live binaries: still forbidden by safety locks.

## Recommended naming for the next stage

`LP_BOT_ENGINEERING_MODE_A_DISCUSSION_V1` (or equivalent). The
"Discussion" wording is deliberate: it does not authorize execution,
it explicitly enumerates the proposed actions for ChatGPT review.