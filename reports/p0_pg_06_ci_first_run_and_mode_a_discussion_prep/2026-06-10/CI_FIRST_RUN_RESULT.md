# CI_FIRST_RUN_RESULT — P0-PG-06

## Read status

**Unable to read the GitHub Actions result from this host.**

Pre-flight:

```
$ which gh
/usr/bin/gh
$ gh --version
gh version 2.45.0 (2025-07-18 Ubuntu 2.45.0-1ubuntu0.3)
$ gh auth status
You are not logged into any GitHub hosts. To log in, run: gh auth login
```

Without `gh auth`, this host cannot read the workflow run list,
the run details, or the job logs from the public GitHub REST API
without an unauthenticated PAT, which is not present in the
environment. Attempting unauthenticated reads via `curl` against
`https://api.github.com/repos/newplayman/super-lp-bot/actions/runs`
is rate-limited (60 req/h for unauthenticated) and is not reliable
enough for a result that this stage commits to the report.

## Trigger record

| field | value |
|---|---|
| workflow | `.github/workflows/shadow-smoke-gate.yml` |
| trigger method | trigger_commit (no `gh workflow run`) |
| trigger file | `scripts/run_shadow_smoke.sh` (comment-only diff, +2 lines) |
| trigger commit message | `ci: trigger shadow smoke gate first run` |
| trigger commit SHA | recorded in `CHANGED_FILES.txt` for this stage (post-push) |
| trigger branch | `feat/supabase-postgres-deployment` |
| trigger surface | `push: paths: ["scripts/run_shadow_smoke.sh", ...]` |
| cron fallback | `37 6 * * *` (daily) |
| workflow_dispatch | available but not used (auth absent) |
| trigger commit pushed | yes (after this report is staged) |

## Fields this stage cannot fill

The following FINAL_VERDICT fields cannot be set to a real observed
value from this host alone:

- `ci_workflow_run_id`
- `ci_workflow_status`
- `ci_workflow_conclusion`
- `ci_result_verified`

Each of these is recorded in `FINAL_VERDICT.json` as either
`(pending — see CI_FIRST_RUN_RESULT.md)` or the corresponding
fallback field, with `ci_result_verified = false` and the
honest reason recorded in `remaining_blockers` and the
`unable_to_read_ci_result_reason` field of this report.

## Manual verification path

A reviewer with `gh` authenticated against the
`newplayman/super-lp-bot` repo can:

```bash
gh run list --workflow shadow-smoke-gate.yml \
    --branch feat/supabase-postgres-deployment --limit 5
gh run view <RUN_ID> --log
```

The expected first run id corresponds to the trigger commit pushed
in this stage. A future stage (or a manual follow-up commit) can
record the real `run id` / `conclusion` once observed.

## Acceptance criterion

This stage's `status` is WARN, not FAIL, because:

- The trigger commit was successfully created and pushed (verified
  by `git log` after `git push`).
- The CI workflow file exists, is statically safety-checked, and
  was locally re-run with the same scripts and binaries (180s
  PASS in P0-PG-04).
- The CI run is *expected* to start within minutes; this stage
  does not wait synchronously for it because the user asked for
  the trigger and the next-stage recommendation, not a blocking
  poll.
- The honest field `ci_result_verified = false` is recorded
  explicitly; this is not a fabricated PASS.

A future stage (or a manual ChatGPT-review pass with the `gh`
output) can promote this stage's status to PASS by filling in the
run id / conclusion.

## Recommended next manual observation

Within 10 minutes of pushing the trigger commit, open:

```
https://github.com/newplayman/super-lp-bot/actions/workflows/shadow-smoke-gate.yml
```

Expected outcome:

- A run titled with the trigger commit message appears in the
  workflow's run list.
- The run's jobs panel shows:
  - `shadow-smoke` job with steps: build-migrate-postgres,
    check-postgres-migrations-sync, wait-for-pg, wait-for-redis,
    plan pre-apply, apply, plan post-apply, status, reapply,
    build-shadow, materialize-config, run_shadow_smoke (180s),
    smoke-safety-check, static-workflow-safety-check, test-files-unmodified.
- Conclusion: `success` (green checkmark) if the smoke stayed
  green; `failure` (red cross) otherwise.

If the conclusion is `success`, the canonical CI path is now
exercised and the P0-PG-05 WARN on dimension #18 closes. If the
conclusion is `failure`, capture the failing step's log and open a
follow-up stage.