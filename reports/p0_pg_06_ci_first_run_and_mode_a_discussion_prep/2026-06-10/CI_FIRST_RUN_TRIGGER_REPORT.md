# CI_FIRST_RUN_TRIGGER_REPORT — P0-PG-06

## Goal

Trigger a real GitHub Actions run of the
`.github/workflows/shadow-smoke-gate.yml` workflow so that its
behaviour in the canonical CI environment is observed at least
once before Mode A discussion proceeds.

## Method selection

Two methods were available:

1. **`gh workflow run`** — direct API call, no commit, no diff.
2. **Trigger commit** — a no-op edit to a file in the workflow's
   `paths:` list, pushed to `origin/feat/supabase-postgres-deployment`.

Pre-flight check:

```
$ gh --version
gh version 2.45.0 (2025-07-18 Ubuntu 2.45.0-1ubuntu0.3)
$ gh auth status
You are not logged into any GitHub hosts. To log in, run: gh auth login
```

`gh` is installed but **not authenticated** on this host. Direct
`gh workflow run` is therefore not available.

## Method used

Trigger commit (option 2). The chosen file is
`scripts/run_shadow_smoke.sh`. The edit is **comment-only** (no
logic change):

```diff
+#
+# CI first-run trigger (P0-PG-06): no logic change; comment only.
+#
 # Strict safety: refuses to start if any canary/live/paper env var
```

The diff is +2 lines of pure comments, sits between two existing
comment blocks, and does not change any executable code or any
documentation that the smoke safety check relies on.

## Trigger surface

The workflow's `on:` block lists:

- `workflow_dispatch` (manual — would require a token we do not have)
- `schedule: cron "37 6 * * *"` (daily at 06:37 UTC)
- `push: branches: [feat/supabase-postgres-deployment] paths: [..., scripts/run_shadow_smoke.sh, ...]`

Pushing a commit that touches `scripts/run_shadow_smoke.sh` to
`feat/supabase-postgres-deployment` will satisfy the push trigger.

## Commit and push

```
$ git add scripts/run_shadow_smoke.sh reports/p0_pg_06_ci_first_run_and_mode_a_discussion_prep/2026-06-09/
$ git commit -m "ci: trigger shadow smoke gate first run"
$ git push origin feat/supabase-postgres-deployment
```

The trigger commit's SHA is captured below in `CI_FIRST_RUN_RESULT.md`.

## What is NOT triggered

- No `gh workflow run` was issued (auth absent).
- No GitHub Actions API call was made by this stage.
- No GitHub Actions result is read by this stage beyond the local
  `git log` confirmation that the trigger commit landed on the
  remote branch.
- No `act` runner is available on this host to dry-run the
  workflow locally.

## After push — what to expect

Within a few minutes (typical GitHub Actions latency for an
ubuntu-latest runner picking up a push trigger):

- The `shadow-smoke-gate.yml` workflow starts a run on the
  `feat/supabase-postgres-deployment` branch.
- The run takes 3–6 minutes (build + migration + 180s smoke +
  safety check + static workflow check).
- A green run is the canonical "CI first-run PASS" signal that
  P0-PG-05's WARN on dimension #18 was closed.
- A red run means either (a) the workflow has a CI-specific bug
  that the local 180s re-run did not surface, or (b) a transient
  network / container issue. Either way, do not retry without
  ChatGPT review.

## Manual check instruction

After pushing the trigger commit, a reviewer can either:

- open `https://github.com/newplayman/super-lp-bot/actions/workflows/shadow-smoke-gate.yml`
  in a browser; or
- run `gh run list --workflow shadow-smoke-gate.yml --branch feat/supabase-postgres-deployment --limit 5`
  on a host with `gh` authenticated.

The CI run's `run id`, `html_url`, `status`, and `conclusion` are
recorded in `CI_FIRST_RUN_RESULT.md` once they are observable
from this host. As of this stage's push, the CI run has not yet
completed; the next observation window is the next time this host
has network access to `api.github.com` or a reviewer with
authenticated `gh` reads the result and feeds it back.