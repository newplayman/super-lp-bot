# LP panel hardening attack smoke

- UTC: `2026-08-09T10:27:07Z`
- baseline: `a5c26b5`
- bind: `127.0.0.1:18991`
- mode: `PAPER / READ-ONLY`
- configured bounds: `request_queue_size=16`, `max_threads=16`

## Real-process results

| Check | Expected | Observed | Verdict |
|---|---:|---:|---|
| GET `/api/state.json` without token | 401 | 401 | PASS |
| GET with correct `X-Panel-Token` | 200 | 200 | PASS |
| POST `/api/state.json` | 405 | 405 | PASS |
| `--path-as-is /../../etc/passwd` | 404 | 404 | PASS |
| startup with `"a" * 32` | non-zero exit | exit 1 | PASS |
| weak-token error generation hint | `openssl rand -hex 32` | present | PASS |

The authenticated server was stopped with SIGINT and exited `0`. A post-smoke
`pgrep -af '[l]p_panel_server_v1_readonly.py'` returned no process. No daemon was
left running.

## Deterministic connection-exhaustion regression

The targeted pytest opens a deliberately incomplete HTTP request with
`max_threads=1`, waits until the active worker count is exactly one, and verifies
that a second request receives `503` immediately. It then closes the slow socket,
waits for the worker count to return to zero, and verifies that a subsequent
request succeeds with `200`. This exercises both overload rejection and the
`finally`-based slot release.

## Read-only/redline check

The smoke used GET requests plus a rejected POST. The panel has no write endpoint,
wallet, signing, broadcast, transaction, or daemon-control path. The access log
was written only to `/tmp/lpbot_m0f_p2_attack_access.log`.
