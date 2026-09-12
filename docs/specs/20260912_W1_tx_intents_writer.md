# W1 Spec: rh_tx_intents writer + A-no-grant test

## GOAL
Build a Python writer for the `rh_tx_intents` SQLite table that defaults to dry-run, wires into the daemon's `_run_episode_persisted` entry point, and ships an end-to-end no-grant test that verifies dry-run invariants from the real production entry.

## CONTEXT
- `rh_tx_intents` schema already exists at `scripts/lp_rh_store_v1_readonly.py:121`. Columns: `request_id, idempotency_key, chain_id, wallet_id, position_id, nonce, state, calldata_hash, policy_hash, expires_at, created_at`.
- `_ensure_columns` + `EXTRA_COLUMNS` pattern at `:247` and `:207` is the established idempotent ALTER TABLE pattern. Use it for new columns.
- The canonical real production entry is `scripts/lp_rh_shadow_daemon_v1_readonly.py::_run_episode_persisted`. Existing tests at `tests/test_rh07_0_copy_new_rows_state_merge.py:9` and `tests/test_rh07_0_release_no_independent_commit.py:9` already import this and call it.
- A test pattern exists at `tests/test_lp_rh_shadow_daemon_v1_readonly.py:717-836` for invoking `_run_episode_persisted` with synthetic sample lists.
- Non-live build broadcaster already panics on `Send` (`adapters/broadcast/disabled/broadcaster.go:45-49`), so signer/broadcaster wiring for dry-run is unnecessary; we record only the intent row.

## TARGET FILES

### NEW: `scripts/lp_rh_tx_intents_writer_v1.py`
- `class TxIntentWriter` accepting `(conn: sqlite3.Connection, dry_run: bool = True)`
- `class DryRunViolation(Exception)`
- Constants:
  - `STATE_PROPOSED = "PROPOSED"`
  - `STATE_SIMULATED_OK = "SIMULATED_OK"`
  - `STATE_WHITELIST_REJECTED = "WHITELIST_REJECTED"`
  - `STATE_DECODER_REJECTED = "DECODER_REJECTED"`
  - `STATE_SIMULATED_FAIL = "SIMULATED_FAIL"`
  - `STATE_SUBMITTED = "SUBMITTED"`
  - `STATE_CONFIRMED = "CONFIRMED"`
  - `DRY_RUN_BLOCKED_STATES = frozenset({STATE_SUBMITTED, STATE_CONFIRMED})`
- `def is_dry_run() -> bool` reads env `LPBOT_TX_DRY_RUN`, default `"true"`. Returns False only if env == `"false"` (literal).
- Methods on writer:
  - `write_intent(*, request_id, idempotency_key, chain_id, wallet_id=None, position_id=None, intent_type, target_address, recipient_address, selector, calldata_hash, value_wei="0", policy_hash, expires_at) -> dict` returns `{request_id, idempotent_hit: bool}`. If `idempotency_key` already exists, returns existing row without writing a new one (idempotent_hit=True). Otherwise inserts row with state=PROPOSED, created_at=now UTC RFC3339.
  - `update_state(request_id, new_state, *, reject_reason=None, tx_hash=None, submitted_at=None, confirmed_at=None, broadcaster_signature=None, simulated_at=None, live_block_number=None) -> None`. Refuses to set `new_state in DRY_RUN_BLOCKED_STATES` unless `self.dry_run is False` AND `is_dry_run()` returns False. Raises `DryRunViolation` otherwise. If reject_reason is set, persists it. If tx_hash is set, persists it. Caller must pre-validate target/selector whitelist OR pass through the wrapper in W2.
  - `get_intent(request_id) -> dict | None`. Returns full row including all 16 columns after migrate.
- Schema additions (idempotent via `EXTRA_COLUMNS`):
  - Add to `rh_tx_intents` table: `intent_type TEXT`, `target_address TEXT`, `recipient_address TEXT`, `selector TEXT`, `value_wei TEXT DEFAULT '0'`, `reject_reason TEXT`, `tx_hash TEXT`, `submitted_at TEXT`, `confirmed_at TEXT`, `broadcaster_signature TEXT`, `simulated_at TEXT`, `live_block_number INTEGER`. All nullable / default values; do NOT mark NOT NULL on existing columns.
  - Register these new columns in `TIME_COLUMNS["rh_tx_intents"]` so UTC validators treat them correctly.
- Module-level CLI (for offline use, optional): `python -m scripts.lp_rh_tx_intents_writer_v1 --print-schema`.

### NEW: `tests/test_paper_a_no_grant.py`
- Imports: `pytest`, `Decimal`, `sqlite3`, `scripts.lp_rh_shadow_daemon_v1_readonly._run_episode_persisted`, `scripts.lp_rh_store_v1_readonly.open_store, migrate`, `scripts.lp_rh_tx_intents_writer_v1.TxIntentWriter`.
- Test fixture: a `tmp_path` based SQLite ledger + live DB.
- Build a sample list of 3 samples, each with `position_open=False` (every step rejected), price=2000.
- Build a `cfg` dict matching existing test pattern at `tests/test_rh07_0_copy_new_rows_state_merge.py:107-118`.
- Call `_run_episode_persisted(ledger, cfg=cfg, episode_id=ep_id, sample_list=..., now_fn=lambda: NOW)` (this is the real production entry point).
- Assert:
  - `rh_tx_intents` table has **zero rows** for this episode (no grant → no intent to propose).
  - `rh_position_marks` has no virtual LP row.
  - `rh_journal` has no fee-event row.
  - `rh_bucket_reservations` count for this episode == 0 (no leak).
  - `ledger.execute("SELECT COUNT(*) FROM rh_journal")` returns 0.
- After the run, manually instantiate `TxIntentWriter(ledger, dry_run=True)`. Call `update_state("nonexistent_id", "SUBMITTED")` and assert `DryRunViolation` is raised.

### NEW: `tests/test_lp_rh_tx_intents_writer_v1.py` (unit tests)
- `test_dry_run_default_blocks_submitted_state`: env unset → writer dry_run=True → update_state(SUBMITTED) raises DryRunViolation.
- `test_dry_run_default_blocks_confirmed_state`: same.
- `test_dry_run_env_false_allows_submitted`: env `LPBOT_TX_DRY_RUN=false` → writer dry_run=False → update_state(SUBMITTED) succeeds.
- `test_idempotent_write_returns_existing`: write same `idempotency_key` twice → second call returns `idempotent_hit=True`, row count remains 1.
- `test_state_machine_proposed_to_simulated_ok`: write_intent returns row, update_state(SIMULATED_OK) succeeds, get_intent reflects state.
- `test_state_machine_to_whitelist_rejected`: write_intent returns row, update_state(WHITELIST_REJECTED, reject_reason="target 0xdeadbeef not in whitelist") succeeds, get_intent shows reject_reason.
- `test_dry_run_does_not_set_tx_hash_columns`: after PROPOSED + SIMULATED_OK under default dry_run, `get_intent` shows `tx_hash, submitted_at, confirmed_at, broadcaster_signature` all None.
- `test_schema_columns_present`: PRAGMA table_info(rh_tx_intents) includes all 12 new column names.
- `test_value_wei_default_zero`: write_intent without value_wei → row shows `value_wei='0'`.

## CWD
`/opt/lpbot/lp-bot-v3-origin-check`

## CONSTRAINTS
- READ-ONLY on existing files except: `scripts/lp_rh_store_v1_readonly.py` (add to EXTRA_COLUMNS + TIME_COLUMNS), `scripts/lp_rh_shadow_daemon_v1_readonly.py` (add TxIntentWriter call inside `_run_episode_persisted` only — preserve all existing behavior).
- Do NOT modify: `scripts/lp_rh_shadow_runner_v1_readonly.py`, `scripts/lp_rh_calldata_decoder_v1_readonly.py`, any test file outside the new test paths, any existing source from previous R3 REWORK commits (607071a, 52b934b, c0600dd).
- Do NOT touch `internal/` (Go) — this is Python-side only.
- Do NOT touch configs/, deploy/, scripts/lp_*_v1_readonly.py files outside the target list.
- No daemon, no signer, no broadcaster, no key. Dry-run only by default.
- All hex addresses must be lowercased before persist to avoid case-mismatch duplicates.
- Use `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` for UTC RFC3339 timestamps (matches existing `_time` convention in `MONEY_COLUMNS`/`TIME_COLUMNS`).
- Use `sqlite3.Row` or explicit column names; no tuple unpacking on row data.
- Single Write/Edit ≤150 lines or 6000 characters; larger files write in multiple passes.

## DELIVERABLES
- `scripts/lp_rh_tx_intents_writer_v1.py` (≤300 lines total)
- `tests/test_paper_a_no_grant.py` (≤150 lines)
- `tests/test_lp_rh_tx_intents_writer_v1.py` (≤200 lines)
- `scripts/lp_rh_shadow_daemon_v1_readonly.py` patched to invoke `TxIntentWriter` once per "PROPOSED" intent at the gate-decision point inside `_run_episode_persisted`. The call must be wrapped in `try/except` so a writer failure does NOT break the existing daemon path; log to stderr with prefix `[tx_intents_writer]` and continue.
- `scripts/lp_rh_store_v1_readonly.py` patched: add `EXTRA_COLUMNS["rh_tx_intents"]` tuple + extend `TIME_COLUMNS["rh_tx_intents"]` with `simulated_at, submitted_at, confirmed_at`.
- `git status --short` and `git diff --stat` at end.

## VALIDATION
```bash
# 1. New unit tests pass
python3 -m pytest tests/test_lp_rh_tx_intents_writer_v1.py -v

# 2. New no-grant test passes
python3 -m pytest tests/test_paper_a_no_grant.py -v

# 3. Existing daemon / R2 tests still pass (no regression)
python3 -m pytest tests/test_rh07_fix_c_*.py tests/test_rh07_0_*.py tests/test_lp_rh_shadow_daemon_v1_readonly.py -q --tb=short -p no:cacheprovider

# 4. Full pytest — count pass/fail deltas vs. baseline (4930 pass / 52 fail)
python3 -m pytest tests/ -q --tb=line -p no:cacheprovider 2>&1 | tail -3

# 5. Verify schema migration is idempotent (run migrate twice on a fresh DB)
python3 -c "
from scripts.lp_rh_store_v1_readonly import open_store, migrate
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    c = open_store(os.path.join(d, 's.db'))
    v1 = migrate(c); v2 = migrate(c)
    print('migrate_versions:', v1, v2, '(should differ only if schema changed)')
    cols = [r[1] for r in c.execute(\"PRAGMA table_info(rh_tx_intents)\").fetchall()]
    expected = ['request_id','idempotency_key','chain_id','wallet_id','position_id','nonce','state',
                'calldata_hash','policy_hash','expires_at','created_at',
                'intent_type','target_address','recipient_address','selector','value_wei',
                'reject_reason','tx_hash','submitted_at','confirmed_at','broadcaster_signature',
                'simulated_at','live_block_number']
    missing = [c2 for c2 in expected if c2 not in cols]
    print('missing:', missing, '(should be empty)')
    c.close()
"

# 6. Dry-run env wiring sanity check
python3 -c "
import os
os.environ.pop('LPBOT_TX_DRY_RUN', None)
from scripts.lp_rh_tx_intents_writer_v1 import is_dry_run, TxIntentWriter
print('default dry_run:', is_dry_run())
os.environ['LPBOT_TX_DRY_RUN'] = 'false'
import importlib, scripts.lp_rh_tx_intents_writer_v1 as m
importlib.reload(m)
print('env=false dry_run:', m.is_dry_run())
"
```

## UNRESOLVED (mark in report if hit)
- Anything requiring touching `lp_rh_shadow_runner_v1_readonly.py` (forbidden).
- Anything requiring touching `internal/` Go files (forbidden).
- Anything where the test requires running the daemon as a real process.

## FAILURE HANDLING
If any validation step fails, return the original error + which test failed + last 30 lines of pytest output. Do NOT modify the spec. Do NOT skip tests. Do NOT silence errors with try/except.