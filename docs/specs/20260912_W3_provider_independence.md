# W3 Spec: Second provider independence + report

## GOAL
Provide concrete evidence that the two RPC providers are actually independent (not the same backend under different domain names), wire `live_gate_status` to read from `rh_rpc_health` instead of a hardcoded string, and produce a JSON + Markdown evidence report.

## CONTEXT
- Round-robin RPC adapter already exists at `internal/adapters/rpc/roundrobin.go:114` with primary/fallback selection.
- `rh_rpc_health` table exists (migrate list — search for it in `scripts/lp_rh_store_v1_readonly.py` `_TABLES`); its columns include `provider`, `sample_time`, `success_count`, `fail_count`, `last_good_block`, `last_good_at`. Latency fields may not exist yet — check `EXTRA_COLUMNS["rh_rpc_health"]`.
- `live_gate_status` lives at `scripts/lp_rh_readiness_v1_readonly.py:505-530`. Its `SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE` blocker is currently a string literal computed in `live_gate_status` itself; tests at `tests/test_lp_rh_readiness_v1_readonly.py:408,448,1204` pass it directly.
- 6 quote providers already wired: dexscreener, defillama, subgraph, birdeye, geckoterminal, solana.
- Independence check precedent: `scripts/lp_rh_provider_pool_v1_readonly.py` already has a `SINGLE_PROVIDER` check at line 230 (different constant name).

## TARGET FILES

### NEW: `scripts/lp_rh_provider_independence_v1.py`
- `def check_independence(provider_a: str, provider_b: str, *, timeout_secs: float = 10.0) -> dict`:
  - DNS-resolves both hostnames (use `socket.getaddrinfo` with timeout).
  - Computes IP set intersection; if non-empty, mark potentially-shared-backend.
  - Sends 5 parallel HTTPS GET to `<provider>/<chain_id_probe_path>` (use `requests` lib with `timeout=timeout_secs`); collect latency_ms + status_code + chain_id response fingerprint.
  - Computes median latency per provider; if median_latency_a and median_latency_b differ by less than 30%, flag as possibly same-backend (latency cluster too tight).
  - TLS cert chain: peek `requests` response `.raw.connection.getpeercert()` for issuer + SAN. If both providers' certs share the same issuer CN, note it (informational; same CDN is not unusual).
  - Returns `{"independent": bool, "reason": str, "evidence": {"dns": {...}, "latency_ms": {...}, "certs": {...}, "chain_id_responses": {...}}}`.
- `def render_report(independence_result: dict, *, providers: list[str], out_path: Path) -> None` writes a Markdown report to `out_path`.
- CLI: `python -m scripts.lp_rh_provider_independence_v1 --provider-a URL --provider-b URL --out PATH [--probe-path PATH]`.

### MODIFY: `scripts/lp_rh_readiness_v1_readonly.py`
- Function `live_gate_status(*, usable_provider_count, ...)` at `:505`:
  - Replace `SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE` decision so it is **derived** from `usable_provider_count < 2` rather than a literal.
  - Add a new optional param `rh_rpc_health_db_path: str | None = None`. When provided, query `rh_rpc_health` directly: `SELECT provider, COUNT(*) AS n FROM rh_rpc_health WHERE success_count > fail_count AND sample_time > datetime('now', '-1 hour') GROUP BY provider`. Use the count of providers with n > 0 as `usable_provider_count`. If the table is missing or query fails, fall back to the `usable_provider_count` argument (don't break callers).
- Add a sibling function `usable_providers_from_db(db_path: str) -> dict` that returns `{count: int, providers: list[str], degraded_since: dict[str, str]}`. This is what `live_gate_status` calls when `rh_rpc_health_db_path` is provided.
- Add tests in the existing `tests/test_lp_rh_readiness_v1_readonly.py` covering the new behavior (use `tmp_path`).

### NEW: `tests/test_lp_rh_provider_independence_v1.py`
- `test_check_independence_two_distinct_endpoints` — uses `unittest.mock` to monkeypatch `socket.getaddrinfo` and `requests.get`. Two endpoints resolve to different IPs and respond with different latencies → returns `independent=True`.
- `test_check_independence_same_ip_fails` — both endpoints resolve to same IP → returns `independent=False`, reason contains "DNS".
- `test_check_independence_latency_too_close` — different IPs but identical 5-call latency sequence → flag latency cluster.
- `test_render_report_writes_markdown` — call render_report on a sample result, assert file exists and contains "Independent:" or "Not Independent:" + "DNS" + "latency" headers.

### NEW: `reports/provider_independence_20260912_CN.md` (generated, not hand-written)
- Run script against two distinct public RPC URLs (e.g., `https://mainnet.base.org` and `https://base.publicnode.com`). Capture the JSON output. Render the markdown report to this path.

## CWD
`/opt/lpbot/lp-bot-v3-origin-check`

## CONSTRAINTS
- READ-ONLY on existing files except: `scripts/lp_rh_readiness_v1_readonly.py` (modify `live_gate_status` and add helper), `scripts/lp_rh_store_v1_readonly.py` (only add columns to `EXTRA_COLUMNS["rh_rpc_health"]` IF needed: `latency_ms_p50 TEXT, latency_ms_p95 TEXT, latency_ms_p99 TEXT, degraded_since TEXT`).
- Do NOT touch `internal/` Go code. Round-robin is already implemented; we only need the *evidence* and the *gate wiring*.
- Do NOT call live RPC endpoints from inside test suite beyond what's strictly mocked. The `check_independence` function may be called against real URLs only when invoked from the CLI to produce the final report; tests mock the network.
- No daemon, no signer, no broadcaster.
- All network calls have explicit `timeout`. Do not block more than `timeout_secs`.
- Single Write/Edit ≤150 lines or 6000 characters.

## DELIVERABLES
- `scripts/lp_rh_provider_independence_v1.py` (≤250 lines)
- `scripts/lp_rh_readiness_v1_readonly.py` patch (≤80 line diff): live_gate_status derives SINGLE_PROVIDER from count, new helper `usable_providers_from_db`.
- `tests/test_lp_rh_provider_independence_v1.py` (≤150 lines)
- Updated tests in `tests/test_lp_rh_readiness_v1_readonly.py` (≤40 lines).
- `reports/provider_independence_20260912_CN.md` (generated by CLI run).
- `git status --short` and `git diff --stat` at end.

## VALIDATION
```bash
# 1. Unit tests pass
python3 -m pytest tests/test_lp_rh_provider_independence_v1.py tests/test_lp_rh_readiness_v1_readonly.py -v

# 2. CLI works on real distinct URLs
python3 -m scripts.lp_rh_provider_independence_v1 \
  --provider-a https://mainnet.base.org \
  --provider-b https://base.publicnode.com \
  --out reports/provider_independence_20260912_CN.md \
  --probe-path /

# 3. JSON inspect
python3 -m scripts.lp_rh_provider_independence_v1 \
  --provider-a https://mainnet.base.org \
  --provider-b https://base.publicnode.com \
  --probe-path / --out /tmp/probe-indep.json
python3 -c "import json; d=json.load(open('/tmp/probe-indep.json')); print('keys:', list(d.keys())); print('independent:', d['independent']); print('reason:', d['reason'])"

# 4. live_gate_status derives SINGLE_PROVIDER from count (regression)
python3 -c "
from scripts.lp_rh_readiness_v1_readonly import live_gate_status
g = live_gate_status(usable_provider_count=1, capital_policy_approved=False, signatures=0, broadcasts=0, keys_created=0)
print('blockers:', g['blockers'])
assert any('SINGLE_PROVIDER' in b for b in g['blockers']), 'expected SINGLE_PROVIDER blocker'
g2 = live_gate_status(usable_provider_count=2, capital_policy_approved=False, signatures=0, broadcasts=0, keys_created=0)
assert not any('SINGLE_PROVIDER' in b for b in g2['blockers']), 'should NOT emit SINGLE_PROVIDER when count>=2'
print('count=2 blockers:', g2['blockers'])
"

# 5. usable_providers_from_db helper (mocked)
python3 -c "
import tempfile, os
from scripts.lp_rh_store_v1_readonly import open_store, migrate
from scripts.lp_rh_readiness_v1_readonly import usable_providers_from_db
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, 'h.db')
    c = open_store(p); migrate(c)
    c.execute(\"INSERT INTO rh_rpc_health (provider, sample_time, success_count, fail_count, last_good_block, last_good_at) VALUES (?, ?, ?, ?, ?, ?)\",
              ('base-mainnet', '2026-09-12T17:00:00Z', 10, 1, 12345, '2026-09-12T17:00:00Z'))
    c.execute(\"INSERT INTO rh_rpc_health (provider, sample_time, success_count, fail_count, last_good_block, last_good_at) VALUES (?, ?, ?, ?, ?, ?)\",
              ('base-publicnode', '2026-09-12T17:00:00Z', 8, 2, 12340, '2026-09-12T17:00:00Z'))
    c.commit(); c.close()
    print(usable_providers_from_db(p))
"

# 6. Full pytest — no regression
python3 -m pytest tests/ -q --tb=line -p no:cacheprovider 2>&1 | tail -3
```

## UNRESOLVED (mark in report if hit)
- Two URLs cannot be resolved (DNS resolution failed for either) → mark as inconclusive, do NOT classify as independent.
- All 5 HTTPS probes timeout or error → independence = False, reason = "no_responses".
- Need to touch `internal/adapters/rpc/roundrobin.go` for any reason (forbidden).

## FAILURE HANDLING
If any validation step fails, return the original error + which test failed + last 30 lines of pytest output. Do NOT modify the spec. Do NOT skip tests. Do NOT silence errors with try/except.