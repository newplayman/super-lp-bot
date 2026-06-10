# CI_RUN_OBSERVATION — P0-PG-06B

## Goal

Close `shadow-smoke-gate.yml`'s GitHub Actions first-run observation
left open by P0-PG-06. Either record the real run id / status /
conclusion (PASS path) or record the inability to read it honestly
(WARN path).

## Probes performed

```bash
$ gh auth status
You are not logged into any GitHub hosts. To log in, run: gh auth login
Alternatively, populate the GH_TOKEN environment variable with a
GitHub API authentication token.

$ gh run list --workflow shadow-smoke-gate.yml \
    --branch feat/supabase-postgres-deployment --limit 10
To get started with GitHub CLI, please run: gh auth login
Alternatively, populate the GH_TOKEN environment variable with a
GitHub API authentication token.

$ env | grep -E "^(GH_TOKEN|GITHUB_TOKEN)="
(no output)

$ env | grep -E "TOKEN|GH_|GITHUB" | head -10
(no relevant tokens)
```

`gh` 2.45.0 is installed at `/usr/bin/gh`. The command exits 0
(`exit: 0` shown above) but reports "not logged in" and refuses
to read run data. No `GH_TOKEN`, no `GITHUB_TOKEN`, no other
GitHub authentication material is present in the environment.

## Result

`ci_result_observed = false`.

`unable_to_read_reason = "gh unauthenticated; no GH_TOKEN or
GITHUB_TOKEN in env"`.

## What is NOT done (per the user's "不要伪造 CI 结果" directive)

- No run id is invented. `ci_workflow_run_id` is recorded as
  `(unread)`.
- No conclusion is invented. `ci_conclusion` is recorded as
  `(unread)`.
- No status is invented. `ci_status` is recorded as `(unread)`.
- No html_url is invented. `ci_workflow_url` is recorded as
  `(unread)` plus the canonical
  `https://github.com/newplayman/super-lp-bot/actions/workflows/shadow-smoke-gate.yml`
  URL that any reviewer with browser access can visit.
- No workflow log is faked. `CI_RUN_LOG_EXCERPT.txt` is empty,
  with an explicit `(no log available; gh unauthenticated)` marker
  at the top.
- No retry of the trigger is performed. The P0-PG-06 trigger
  commit (`ea3bf446cec178ce650f87cc68dd311f96e489f3`) is on
  `origin/feat/supabase-postgres-deployment`; the workflow will
  have run by now on GitHub Actions. This stage did not re-trigger
  because re-triggering without reading the result would be
  noise.

## Honest status

This stage's `status = WARN`. P0-PG-06's WARN is **NOT** closed by
this stage (`p0_pg_06_warn_closed_by_06b = false`). The WARN
remains open and is recorded as a blocker in `remaining_blockers`.

## P0-PG-06 trigger confirmation

`git log -1 --format=%H` for `scripts/run_shadow_smoke.sh` on
remote is `ea3bf446cec178ce650f87cc68dd311f96e489f3`. The
P0-PG-06 commit message was `docs: prepare mode a discussion and
trigger smoke ci`. That commit's diff against its parent
(`102cbe36c51a8d056a5c5cbc0b67f6ca35b92d32`) is exactly +2 lines
of pure comments in `scripts/run_shadow_smoke.sh`. That diff is in
the workflow's `paths:` list, so the workflow should have triggered.

This stage cannot independently confirm that the workflow did
trigger (no GitHub API access). A reviewer with browser access
or authenticated `gh` should look at the `actions` tab of the repo
and look for a run titled with the `ea3bf44` SHA or the message
"prepare mode a discussion and trigger smoke ci".

## What is required to close the WARN

Exactly one of:

1. **Manual observation**: a reviewer opens
   `https://github.com/newplayman/super-lp-bot/actions/workflows/shadow-smoke-gate.yml`
   in a browser and records the run id / status / conclusion.
   They update `CI_FIRST_RUN_RESULT.md` (P0-PG-06) with the real
   values. The P0-PG-06 stage is then re-promoted to PASS.
2. **Authenticated CI read**: a reviewer runs `gh auth login`,
   then runs `gh run list ...` and `gh run view <RUN_ID> --log`,
   and feeds the values back into this stage's
   `CI_RUN_OBSERVATION.md` and `CI_RUN_LOG_EXCERPT.txt`. This
   stage can then be promoted to PASS.
3. **A follow-up stage** with explicit CI observability (e.g. a
   stage that captures the run output via a different mechanism,
   like a CI-side webhook). This is a much heavier path and is
   not recommended; option 1 is preferred.

No automatic re-trigger is appropriate here because (a) the
trigger commit is already on remote and (b) without a way to read
the result, a re-trigger is just adding more unread output.