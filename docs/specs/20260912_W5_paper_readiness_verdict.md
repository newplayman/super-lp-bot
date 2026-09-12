# W5 Spec: Paper readiness verdict (16 gates + report + unit tests)

## GOAL
Provide `compute_paper_readiness()` that aggregates 16 concrete Paper-technical gates, each backed by either (a) a pytest collection, (b) a SQLite/file inspection, (c) a process-counter read, or (d) a CLI invocation. Output a JSON verdict + Markdown report. Every gate is a **pure function** (no hidden state) so it can be unit-tested independently.

## CONTEXT
- R3 baseline: 52 fail / 4948 pass / 14 skip on `tests/` (after W1/W3/W4 commit f94abc9 it became 53 fail / 4949 pass; one extra fail is pre-existing flaky in `test_rh02by_journal_entries_pass_stage_b_balance_audit`).
- W1 wired `TxIntentWriter` into `_run_episode_persisted`; W2 will wire the whitelist gate after that.
- W3 wired `live_gate_status` to read `usable_providers_from_db` from `rh_rpc_health`; the readiness module already exposes `live_gate_status` with a `SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE` blocker derived from count.
- W4 wrote systemd units but **timer is not enabled** (BLOCKED_BY_OWNER_FREEZE).
- B/C/D/E/F test suites (W6) produce 5 of the 16 gates' evidence (g5/g6/g7/g8/g9).
- Owner forbids: starting paper/live/canary, creating keys, signing, broadcasting, setting `live_allowed=true`/`tiny_live_authorized=true`, modifying main, bypassing CLAUDE.md freeze.
- Owner permits: any read-only inspection, audit, doc writing, dry-run code, plus the explicit W1-W6 engineering items.

## TARGET FILES

### NEW: `scripts/lp_rh_paper_readiness_v1.py`
- 16 pure-function gates, each returning `{"pass": bool, "evidence": dict, "reason": str | None}`:
  1. `g1_all_pytest_pass` — call `pytest tests/ -q --tb=no -p no:cacheprovider` (subprocess, capture last line), parse `N passed / M failed`; pass iff `failed == 0`.
  2. `g2_audit_regression_pass` — call `python3 tools/audit_repro/audit_repro.py --repo . --allow-other-head --json-out /tmp/audit_w5.json`; pass iff `counts.PROBE_ERROR == 0` AND `counts.DEFECT_REPRODUCED == 0`.
  3. `g3_entry_integration_tests_pass` — pytest collection of `tests/test_rh07_fix_c_r2_*.py` + `tests/test_lp_rh_shadow_daemon_v1_readonly.py` + `tests/test_lp_rh_shadow_runner_v1_readonly.py`; pass iff all collected items pass.
  4. `g4_full_cost_nav_wired` — AST inspect `scripts/lp_rh_shadow_runner_v1_readonly.py`: find a `SHADOW_SCENARIO` (or `DEFAULT_SCENARIO` / `DEFAULT_CFG`) reference and assert that the call to the runner passes through `compute_full_cost_nav` OR the runner's output struct contains a `full_cost_nav` key (AST: `ast.Attribute(value=..., attr="full_cost_nav")`).
  5. `g5_liquidation_unit_matrix` — pytest `tests/test_paper_d_liquidation_matrix.py` (W6 produces); pass iff collected items pass.
  6. `g6_no_grant_no_virtual_position` — pytest `tests/test_paper_a_no_grant.py` (W1); pass iff pass.
  7. `g7_grant_baseline_sync` — pytest `tests/test_paper_b_delayed_grant.py` (W6); pass iff pass.
  8. `g8_pool_state_excludes_invalid` — pytest `tests/test_paper_e_pool_state.py` (W6); pass iff pass.
  9. `g9_reconciliation_binding_failclose` — pytest `tests/test_lp_rh_graduation_reconciliation_v1_readonly.py::test_*_fail_close` (already exists); pass iff pass.
  10. `g10_coverage_denominator_consistent` — pytest `tests/test_lp_rh_readiness_v1_readonly.py::test_*coverage_denom*` (already exists); pass iff pass.
  11. `g11_two_providers_usable` — read `rh_rpc_health` from a writable DB; pass iff `usable_providers_from_db` returns `count >= 2`. Provide a `LPBOT_RPC_HEALTH_DB` env var override; when unset, this gate is reported as `INCONCLUSIVE` (not FAIL) and reason `"DB_PATH_NOT_SET"`. Owner can wire it before running the verdict.
  12. `g12_live_allowed_false` — read `configs/config.shadow.toml` (path passed in via env or arg); pass iff no `live_allowed = true` line.
  13. `g13_tiny_live_authorized_false` — same; pass iff no `tiny_live_authorized = true` line.
  14. `g14_keys_created_zero` — read `reports/paper_runtime_counters.json` if exists, default `{"keys_created": 0, "signatures": 0, "broadcasts": 0}`. Pass iff `keys_created == 0`.
  15. `g15_signatures_zero` — same source; pass iff `signatures == 0`.
  16. `g16_broadcasts_zero` — same source; pass iff `broadcasts == 0`.
- Top-level aggregator:
  - `def compute_paper_readiness(*, db_path: str | None = None, config_path: str | None = None, runtime_counters_path: str | None = None) -> dict`:
    - Iterates `g1..g16`. For each: capture `(pass, evidence, reason)`.
    - Returns `{"verdict": "PASS" | "FAIL", "gates": {name: {...}}, "summary": {"passed": N, "failed": M, "inconclusive": K}}`.
    - `verdict == "PASS"` iff every gate is `pass == True`. Inconclusive gates DO NOT auto-fail; they appear under `summary.inconclusive` and the verdict PASSes if all concrete gates pass.
  - `def render_report(verdict_dict: dict, *, out_path: Path) -> None` — write Markdown.
- Module CLI:
  - `python -m scripts.lp_rh_paper_readiness_v1 --json-out /tmp/w5.json --md-out reports/paper_readiness_20260912_CN.md [--db-path PATH] [--config-path PATH] [--runtime-counters PATH]`.
  - Exits `0` iff `verdict == "PASS"`, else `1`.

### NEW: `tests/test_lp_rh_paper_readiness_v1.py`
- Unit tests (mock subprocess + DB):
  - `test_compute_paper_readiness_all_pass`: monkeypatch each of 16 gate functions to return `{"pass": True, "evidence": {}, "reason": None}`; expect `verdict == "PASS"` and `summary.passed == 16`.
  - `test_compute_paper_readiness_one_fail`: mock `g6_no_grant_no_virtual_position` to `pass: False`; expect `verdict == "FAIL"` and `gates["g6_..."]["pass"] == False`.
  - `test_compute_paper_readiness_inconclusive_does_not_fail`: mock `g11_two_providers_usable` to `{"pass": False, "evidence": {}, "reason": "DB_PATH_NOT_SET"}`; assert verdict logic still considers it inconclusive (a separate `summary.inconclusive` counter increments) and `verdict == "PASS"` iff every other gate passes. The module-level constant `INCONCLUSIVE_REASONS = {"DB_PATH_NOT_SET"}` decides this.
  - `test_render_report_writes_markdown`: feed a synthetic `verdict_dict`, write to tmp_path, assert file exists and contains "PASS"/"FAIL" + every gate name.
  - `test_compute_paper_readiness_invokes_subprocess_for_pytest` (pytest-mock): assert `subprocess.run(["pytest", ...])` is called for `g1` and `g3`.
  - `test_g14_g15_g16_read_counters_file`: write a `runtime_counters.json` with `keys_created=0, signatures=0, broadcasts=0`; assert all three gates pass; with `keys_created=1` assert `g14` fails.
  - `test_g12_g13_read_config_toml`: write a tmp config.toml without `live_allowed` and `tiny_live_authorized`; assert g12/g13 pass; write one with `live_allowed = true`; assert g12 fails.

## CWD
`/opt/lpbot/lp-bot-v3-origin-check`

## CONSTRAINTS
- READ-ONLY on existing files except: nothing — this is a NEW script.
- Do NOT modify `scripts/lp_rh_readiness_v1_readonly.py`, `scripts/lp_rh_shadow_runner_v1_readonly.py`, `scripts/lp_rh_shadow_daemon_v1_readonly.py`, `internal/`, `configs/`.
- No daemon, no signer, no broadcaster, no key.
- `subprocess.run` calls MUST have `timeout` (≤120s each); if it exceeds, mark gate as INCONCLUSIVE with reason `SUBPROCESS_TIMEOUT`.
- g1/g2/g3 must NOT pull the entire network or filesystem into the test; in tests, monkeypatch them with a stub returning a synthetic verdict dict.
- Single Write/Edit ≤150 lines or 6000 characters.

## DELIVERABLES
- `scripts/lp_rh_paper_readiness_v1.py` (≤350 lines)
- `tests/test_lp_rh_paper_readiness_v1.py` (≤250 lines)
- `reports/paper_readiness_20260912_CN.md` (generated by CLI run)
- `git status --short` and `git diff --stat` at end.

## VALIDATION
```bash
# 1. Unit tests pass
python3 -m pytest tests/test_lp_rh_paper_readiness_v1.py -v

# 2. CLI runs end-to-end (g1 + g3 + g5 + g6 + g7 + g8 may FAIL today — that's fine,
# verdict will be FAIL but the report must render cleanly)
python3 -m scripts.lp_rh_paper_readiness_v1 \
  --json-out /tmp/w5_paper_readiness.json \
  --md-out reports/paper_readiness_20260912_CN.md

# 3. JSON inspection
python3 -c "
import json
d = json.load(open('/tmp/w5_paper_readiness.json'))
print('verdict:', d['verdict'])
print('passed:', d['summary']['passed'], 'failed:', d['summary']['failed'], 'inconclusive:', d['summary']['inconclusive'])
for name, g in d['gates'].items():
    print(f'  {name}: pass={g[\"pass\"]} reason={g[\"reason\"]}')
"

# 4. CI YAML still parses (regression)
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK ci.yml')"
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/audit-regression.yml')); print('OK audit-regression.yml')"

# 5. Full pytest — no regression
python3 -m pytest tests/ -q --tb=line -p no:cacheprovider 2>&1 | tail -3
```

## UNRESOLVED (mark in report if hit)
- Subprocess timeout → gate marked INCONCLUSIVE (does not fail verdict).
- `rh_rpc_health` DB path not set → g11 INCONCLUSIVE.
- W6 tests missing for g5/g7/g8 → those gates will FAIL until W6 lands; that's expected and reflected in `PAPER_READY_APPLICATION_CN.md` as `BLOCKED_BY_W6`.

## FAILURE HANDLING
If any validation step fails, return the original error + which test failed + last 30 lines of pytest output. Do NOT modify the spec. Do NOT skip tests. Do NOT silence errors with try/except.
