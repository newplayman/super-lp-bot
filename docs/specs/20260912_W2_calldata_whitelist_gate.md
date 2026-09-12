# W2 Spec: calldata whitelist gate wired into the daemon

## GOAL
Wire the existing `scripts/lp_rh_calldata_decoder_v1_readonly.py::verify_intent` (currently only called from the file's CLI `main()`) into the daemon's real production entry point so that every `rh_tx_intents` row is gated through the whitelist. Whitelist rejection must set `state='WHITELIST_REJECTED'` + persist a `reject_reason`, must NOT trigger any signer/broadcaster, and must be observable in the SQLite row.

## CONTEXT
- `verify_intent(intent)` at `scripts/lp_rh_calldata_decoder_v1_readonly.py:242` already implements `check_targets:152`, `check_amount_protection:175`, `check_deadline:200`, `check_approval:213`.
- The wrapper must be added at `scripts/lp_rh_shadow_daemon_v1_readonly.py::_run_episode_persisted` AFTER `TxIntentWriter.write_intent(state='PROPOSED')` is called (W1 produces that call). On reject, call `TxIntentWriter.update_state('WHITELIST_REJECTED', reject_reason=...)` and **do not** propagate to any signer or broadcaster.
- W1 already wires `TxIntentWriter` invocation. The exact insertion point is the gate-decision step in `_run_episode_persisted` where each "ready-to-broadcast" intent is produced.
- Non-live broadcaster already panics on `Send` (`adapters/broadcast/disabled/broadcaster.go:45-49`); the gate's purpose is to provide an observable, dry-run-friendly fail-close boundary before any signature or broadcast could ever be reached.

## TARGET FILES

### NEW: `scripts/lp_rh_calldata_whitelist_gate_v1_readonly.py`
- Constants:
  - `WHITELIST_TARGETS = frozenset({...})` — load from `internal/adapters/pool/aerodrome/adapter.go`:
    - Router `0xF87912FeFD79b1dEe6561C3d38e9EB4F3F77D7e2`
    - Factory `0x420DD7b1D89364d57d6EEA33300755E7d0fF6794`
  - `WHITELIST_SELECTORS = frozenset({...})` — load from `aerodrome/adapter.go` `buildAddLiquidityCalldata:195` and `buildRemoveLiquidityCalldata:212` etc:
    - `0xb95cac29` (addLiquidity)
    - `0x02751cec` (removeLiquidity / decreaseLiquidity on Uniswap V3 style)
    - collect / burn / swap selectors per adapter
  - `WHITELIST_RECIPIENTS = frozenset({...})` — at minimum include `0x0000000000000000000000000000000000000000` (zero address = burn) and the project's controlled addresses. Add placeholder for project-controlled wallet (use `0x000000000000000000000000000000000000dEaD` as documented placeholder, with a comment that it must be replaced before any LIVE mode).
- `def verify_intent_or_reject(intent: dict) -> tuple[bool, str | None]`:
  - Lowercase all hex addresses before comparison.
  - Call `verify_intent(intent)` if available; if `verify_intent` is missing or raises, fall back to in-process whitelist check (target + selector only; do NOT reimplement amount/deadline/approval logic in this layer — that is `verify_intent`'s job).
  - Returns `(True, None)` on pass, `(False, "whitelist_reject:<reason>")` on fail.
- `def load_whitelist() -> dict` returns the constants above (so tests can inspect without hardcoding duplicates).

### MODIFY: `scripts/lp_rh_shadow_daemon_v1_readonly.py`
- Inside `_run_episode_persisted`, locate the spot where W1 inserts a `TxIntentWriter.write_intent(state='PROPOSED')` call.
- After the `write_intent` call, build a minimal `intent` dict with `target_address`, `selector`, `recipient_address`, `value_wei`, `deadline`, and `calldata_hash` (all from the gate-decision context).
- Call `verify_intent_or_reject(intent)`.
- If `False`, call `tx_writer.update_state(request_id, 'WHITELIST_REJECTED', reject_reason=reason)` and **skip** any downstream signer/broadcast invocation. Continue with the next episode step.
- If `True`, call `tx_writer.update_state(request_id, 'SIMULATED_OK')` (note: `SIMULATED_OK` is dry-run's "we verified intent and it would pass through").
- Wrap the entire gate section in `try/except` so a failure inside verify_intent_or_reject does NOT break the daemon; log prefix `[whitelist_gate]` to stderr and `update_state('WHITELIST_REJECTED', reject_reason='whitelist_gate_exception:...')`.

### NEW: `tests/test_paper_g_whitelist_gate.py`
- `test_legal_target_passes`: target = router address (lowercase), selector = addLiquidity → returns `(True, None)`.
- `test_evil_target_rejected`: target = `0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef` → returns `(False, reason)`; reason startswith `"whitelist_reject:"` or `"whitelist_gate_exception:"`.
- `test_evil_selector_rejected`: target = legal, selector = `0xdeadbeef` → returns `(False, reason)`.
- `test_case_insensitive_target`: target = `0xF879...` uppercase → still passes after lowercasing.
- `test_whitelist_constant_non_empty`: `load_whitelist()["targets"]` len > 3.

### NEW: `tests/test_lp_rh_calldata_whitelist_gate_v1_readonly.py`
- E2E via `_run_episode_persisted` (real production entry). Build cfg with sample list that reaches the gate-decision step. Use `tmp_path` SQLite.
- Case 1: legal `target_address` in sample → assert `rh_tx_intents.state == 'SIMULATED_OK'` after run.
- Case 2: evil `target_address` injected via sample → assert `rh_tx_intents.state == 'WHITELIST_REJECTED'` + `reject_reason` non-empty + `rh_journal` count == 0 + `rh_bucket_reservations` count == 0.
- Case 3: empty `target_address` (None) → must produce `state='WHITELIST_REJECTED'` with reason containing "target".

## CWD
`/opt/lpbot/lp-bot-v3-origin-check`

## CONSTRAINTS
- READ-ONLY on existing files except:
  - `scripts/lp_rh_shadow_daemon_v1_readonly.py` (add gate call after TxIntentWriter.write_intent)
  - `scripts/lp_rh_calldata_decoder_v1_readonly.py` (READ-ONLY — do not modify)
- Do NOT modify `scripts/lp_rh_shadow_runner_v1_readonly.py`, `internal/`, configs/.
- No daemon, no signer, no broadcaster.
- Whitelist constants MUST be derived from the existing Go adapter (`internal/adapters/pool/aerodrome/adapter.go`); copy the values but keep a code comment with the source file:line.
- The wrapper must call `verify_intent` if importable; otherwise fall back. NEVER reimplement verify_intent's internal checks (amount_protection, deadline, approval) here.
- Lowercase all hex addresses before persist or compare.
- Single Write/Edit ≤150 lines or 6000 characters.

## DELIVERABLES
- `scripts/lp_rh_calldata_whitelist_gate_v1_readonly.py` (≤200 lines)
- `tests/test_paper_g_whitelist_gate.py` (≤150 lines)
- `tests/test_lp_rh_calldata_whitelist_gate_v1_readonly.py` (≤200 lines)
- `scripts/lp_rh_shadow_daemon_v1_readonly.py` patch (≤60 line diff): gate insertion in `_run_episode_persisted`.
- `git status --short` and `git diff --stat` at end.

## VALIDATION
```bash
# 1. Unit tests for the gate itself
python3 -m pytest tests/test_paper_g_whitelist_gate.py -v

# 2. E2E test for the daemon integration
python3 -m pytest tests/test_lp_rh_calldata_whitelist_gate_v1_readonly.py -v

# 3. Daemon entry test (R3 baseline) — no regression
python3 -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py tests/test_rh07_0_*.py tests/test_rh07_fix_c_*.py -q --tb=short -p no:cacheprovider

# 4. Tx-intent unit tests (W1) still pass — no regression
python3 -m pytest tests/test_lp_rh_tx_intents_writer_v1.py tests/test_paper_a_no_grant.py -v

# 5. Sanity: gate rejects evil target even outside daemon context
python3 -c "
from scripts.lp_rh_calldata_whitelist_gate_v1_readonly import verify_intent_or_reject, load_whitelist
print('whitelist targets:', sorted(list(load_whitelist()['targets']))[:3], '...')
ok, reason = verify_intent_or_reject({'target_address': '0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef', 'selector': '0xb95cac29', 'recipient_address': '0x0'})
assert not ok and reason, f'expected reject, got ok={ok} reason={reason}'
print('evil target rejected:', reason)
ok, reason = verify_intent_or_reject({'target_address': load_whitelist()['targets'].copy().pop(), 'selector': '0xb95cac29', 'recipient_address': '0x0'})
print('legal target result:', ok, reason)
"

# 6. Full pytest
python3 -m pytest tests/ -q --tb=line -p no:cacheprovider 2>&1 | tail -3
```

## UNRESOLVED (mark in report if hit)
- `verify_intent` raises or is unimportable in test environment → fail the test, do not silently skip.
- Need to modify `scripts/lp_rh_calldata_decoder_v1_readonly.py` for any reason → BLOCKED.
- Whitelist constants cannot be derived from the Go adapter (file structure changed) → BLOCKED.

## FAILURE HANDLING
If any validation step fails, return the original error + which test failed + last 30 lines of pytest output. Do NOT modify the spec. Do NOT skip tests. Do NOT silence errors with try/except.