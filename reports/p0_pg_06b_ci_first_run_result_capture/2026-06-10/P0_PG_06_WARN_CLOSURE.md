# P0_PG_06_WARN_CLOSURE — P0-PG-06B

## Status of the P0-PG-06 WARN

`p0_pg_06_warn_closed_by_06b = false`.

The WARN recorded in
`reports/p0_pg_06_ci_first_run_and_mode_a_discussion_prep/2026-06-10/FINAL_VERDICT.json`
(`ci_result_verified = false`, `ci_workflow_run_id = (pending)`,
`ci_workflow_status = (pending)`, `ci_workflow_conclusion = (pending)`)
**remains open** as of this stage.

## What this stage tried

1. `git fetch origin` — got remote HEAD `f5da80c` (same as local).
2. `gh auth status` — confirmed unauthenticated.
3. `gh run list --workflow shadow-smoke-gate.yml --branch feat/supabase-postgres-deployment --limit 10` — refused, exits with the auth-required message.
4. Probed for `GH_TOKEN` and `GITHUB_TOKEN` env vars — neither is set.

## Why the WARN cannot be closed by this stage

Per the user's directive, this stage must not fabricate CI
results. `gh` is not authenticated on this host and no GitHub
authentication material is in scope for this stage to use.

The trigger commit (`ea3bf446cec178ce650f87cc68dd311f96e489f3`,
P0-PG-06) is on `origin/feat/supabase-postgres-deployment`. The
workflow should have triggered on push and run within ~5 minutes.
The result is on GitHub; this host just cannot read it.

## What is required to close the WARN

Exactly one of the following (in order of preference):

1. **Browser-based manual observation** (lowest friction).
   A reviewer with web access opens
   `https://github.com/newplayman/super-lp-bot/actions/workflows/shadow-smoke-gate.yml`
   in a browser. They look for the run with the commit message
   "prepare mode a discussion and trigger smoke ci" or the
   `ea3bf44` SHA. They confirm `conclusion = success` (green) or
   `failure` (red). They feed the run id / status / conclusion /
   any failing step's log back to the project (a comment on the
   PR, a follow-up commit updating `CI_FIRST_RUN_RESULT.md`,
   or a follow-up stage).

2. **Authenticated `gh` read**. A reviewer with `gh` authenticated
   runs:

   ```bash
   gh auth login
   gh run list --workflow shadow-smoke-gate.yml \
       --branch feat/supabase-postgres-deployment --limit 5
   gh run view <RUN_ID> --log
   ```

   and feeds the values back the same way.

3. **A follow-up stage** that reads the run output through a
   different mechanism (e.g. via a GitHub webhook into a known
   sink). Heavier; only justified if manual observation is not
   acceptable for the project.

Once the real values are recorded into
`reports/p0_pg_06_ci_first_run_and_mode_a_discussion_prep/2026-06-10/CI_FIRST_RUN_RESULT.md`
(an update commit, not a new stage), the WARN is closed. The
P0-PG-05 readiness matrix's dimension #18 closes as well.

## What is NOT required to close the WARN

- Re-running this stage. This stage's job was to *attempt* the
  closure; if the attempt fails due to auth, re-running without
  changing anything will not help.
- Re-triggering the workflow. The trigger commit is already on
  remote; re-triggering without reading the result is noise.
- Modifying the workflow file. The workflow is statically
  safety-checked; nothing in this stage changes it.
- Modifying the trigger script. Same — `scripts/run_shadow_smoke.sh`
  is unchanged.

## What changes in this stage if a follow-up commit lands the run id

If a follow-up commit amends
`reports/p0_pg_06_ci_first_run_and_mode_a_discussion_prep/2026-06-10/FINAL_VERDICT.json`
with real run id / status / conclusion values, this stage's
`p0_pg_06_warn_closed_by_06b` becomes true. This stage's
`status` would also become PASS (assuming the run was green). No
new stage is required to make that update.

## What does NOT close the WARN

A WARN closure based on this stage's `WARN` status is not the
same as closing the P0-PG-06 WARN. This stage's own
`status = WARN` is honest for THIS stage; it does not promote
P0-PG-06. The closure is recorded in P0-PG-06's report dir, not
here.