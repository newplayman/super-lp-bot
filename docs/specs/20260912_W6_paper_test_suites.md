# W6 Spec: B/C/D/E/F end-to-end paper test suites

## GOAL
Five additional end-to-end test suites — B, C, D, E, F — that exercise the full `_run_episode_persisted` production entry (same as A in `tests/test_paper_a_no_grant.py`). Each suite locks down one specific risk axis identified during R3 整改 and the Owner-supplied paper-readiness gate list. Together with W1's A and W2's G, these produce the 6 paper-readiness gates that require new tests.

## CONTEXT
- Pattern precedent: `tests/test_paper_a_no_grant.py` and `tests/test_lp_rh_shadow_daemon_v1_readonly.py:717-836` already import `_run_episode_persisted` and call it with synthetic sample lists.
- `run_episode(...)` lives at `scripts/lp_rh_shadow_runner_v1_readonly.py:800`; `compute_full_cost_nav` at `scripts/lp_rh_pnl_v1_readonly.py:142`; `compute_liquidation_nav` at `:170`.
- W1 wired `TxIntentWriter` into daemon (PROPOSED); W2 wires the whitelist gate. B-F must work with W1+W2 in place — B/C/E/F should still see their expected `rh_tx_intents` rows; D does not depend on tx-intents.
- Owner explicitly listed six end-to-end test suites (A-F) as required for paper readiness; only A exists today.
- `compute_liquidation_nav` was hardened in R3 Package E to fail-close (`LIQUIDATION_NAV_INPUT_MISSING`); D re-asserts this in matrix form.

## TARGET FILES

### NEW: `tests/test_paper_b_delayed_grant.py`
- Same fixture pattern as `tests/test_paper_a_no_grant.py` (`tmp_path`, `_fresh_store`, `_run_episode_persisted`).
- Build a 3-sample list where samples[0] and samples[1] are REJECTED (`position_open=False`, `reference_mid=2000`), and samples[2] is GRANTED (`position_open=True`, `reference_mid=2200`).
- Assert after `_run_episode_persisted`:
  - `rh_position_marks[grant_step].entry_price == 2200` (not 2000; fee-growth baseline must lock at the GRANT step's price).
  - `tick_lower / tick_upper` of the resulting virtual LP position is computed from the 2200 range, not 2000.
  - `fee_growth_global_0 / fee_growth_global_1` recorded at the grant step equals `samples[2].fee_growth_global_*`.
  - `inventory.liquidity_raw` corresponds to the 2200 grant step's price, not the rejected step's cached value.

### NEW: `tests/test_paper_c_full_cost_flat.py`
- Build a flat-price 5-sample list (price=2000 throughout, `fee_apr_pct=0`, rewards=0), `position_open=True` from sample 0 onward.
- Inject round-trip costs via the cfg that flows into the daemon: `entry_cost_usd=5`, `exit_cost_usd=3`, `gas_usd=2`. (These fields must already be honored by `_run_episode_persisted`'s downstream NAV computation; if not, this test is BLOCKED and must FAIL — not skip — so the owner sees the gap.)
- Assert:
  - `episode_summary.net_pnl ≈ -(5 + 3 + 2) = -10` (relative error ≤ 1e-12).
  - `episode_summary.nav_start == 1000` (the seed capital), NOT the first mark's NAV.
  - `steps[0].nav == 990` (the cost is recognized at the open step, not deferred).
  - `compute_full_cost_nav(wallet=..., lp_principal=..., accrued_fees=0, entry_cost_usd=5, exit_cost_usd=3, gas_usd=2, slippage_usd=0, verified_rewards=0, liabilities=0)` equals the same value as the episode-level NAV (cross-check).

### NEW: `tests/test_paper_d_liquidation_matrix.py`
- Parametrize matrix: `(principal ∈ {1, 10, 50, 1000}) × (dec0, dec1) ∈ {(18,6), (6,18), (18,18)} × range_pct ∈ {5, 10, 50, 90}` (36 combinations).
- For each combination, build a minimal virtual LP position (l_pos = principal * 10^dec1 / price), then compute:
  - `compute_liquidation_nav(...)` (production function from `lp_rh_pnl_v1_readonly.py`).
  - Analytic reference: `inventory_for_position(...).liquidity_raw * price / 10^dec` (closed-form liquidity-as-cash).
- Assert relative error ≤ 1e-10.
- AST check (test-time): load `scripts/lp_rh_pnl_v1_readonly.py`, parse with `ast`, walk to `compute_liquidation_nav` FunctionDef body, assert NO `if/elif` branch on numeric thresholds (per R3 Package E — fail-close only, no silent-success thresholds).

### NEW: `tests/test_paper_e_pool_state.py`
- Three scenarios; each runs `_run_episode_persisted` with one sample whose `pool_state` field is set differently:
  - `pool_state='STALE'` (timestamp > `reference_age_secs` cap).
  - `pool_state='FUTURE'` (timestamp > now).
  - `pool_state='UNKNOWN'` (None or empty).
- The daemon's existing fail-close logic (R3 Package D) must mark each as `terminal_eligible=False`.
- Assert (via inspecting the `rh_position_marks` table after migration):
  - All three scenarios produce a row with `invalid_for_paper_evaluation=1` (or `True`). The schema migration for this column MUST be added to `scripts/lp_rh_store_v1_readonly.py` `_ensure_columns` + `EXTRA_COLUMNS["rh_position_marks"]` if not already present (≤5 line diff).
  - `rh_journal` count for the episode == 0 (no fee event written when pool state is invalid).
  - `rh_bucket_reservations` for the episode == 0 (no bucket leaked).
- If the column does not exist or migration is missing, the test must FAIL with a clear message — not skip.

### NEW: `tests/test_paper_f_crash_recovery.py`
- Three sub-tests, each driven by `tmp_path` SQLite:
  1. **Crash mid-episode**: run `_run_episode_persisted` to step 2/4, monkeypatch `_copy_new_rows` to raise `sqlite3.IntegrityError("UNIQUE constraint failed: rh_journal.event_id")`. Assert the daemon returns a partial result; `rh_journal` has no duplicate `event_id`.
  2. **Duplicate episode replay**: run the same `episode_id` twice. Assert second run is idempotent at the table level: `rh_journal` row count stays the same; `rh_bucket_reservations` for the episode stays singular; `rh_position_marks` (episode_id, step_idx) UNIQUE constraint holds.
  3. **Reservation recovery after crash**: simulate a half-applied reservation (insert `rh_bucket_reservations` row with status='PENDING' and no matching `rh_journal` credit), then call the existing reconciliation helper if any (`scripts/lp_rh_*_reconciliation_v1_readonly.py`). Assert PENDING reservation is either resolved or explicitly released — never silently leaked.

## CWD
`/opt/lpbot/lp-bot-v3-origin-check`

## CONSTRAINTS
- READ-ONLY on existing files except:
  - `scripts/lp_rh_store_v1_readonly.py` (allowed ONLY for adding `invalid_for_paper_evaluation` column to `rh_position_marks` via the existing `EXTRA_COLUMNS` pattern).
- Do NOT modify `scripts/lp_rh_shadow_runner_v1_readonly.py`, `scripts/lp_rh_shadow_daemon_v1_readonly.py`, `internal/`, `configs/`.
- No daemon, no signer, no broadcaster, no key. All tests are pure pytest.
- Tests must be order-independent (no shared state). Each must use `tmp_path`.
- All hex addresses lowercased before persist or compare.
- AST checks must use `ast.parse` only — no execution of the source.
- Single Write/Edit ≤150 lines or 6000 characters.

## DELIVERABLES
- `tests/test_paper_b_delayed_grant.py` (≤200 lines)
- `tests/test_paper_c_full_cost_flat.py` (≤200 lines)
- `tests/test_paper_d_liquidation_matrix.py` (≤250 lines; matrix can be split across two files if needed)
- `tests/test_paper_e_pool_state.py` (≤200 lines)
- `tests/test_paper_f_crash_recovery.py` (≤300 lines)
- `scripts/lp_rh_store_v1_readonly.py` patch (≤10 line diff for `invalid_for_paper_evaluation` column)
- `git status --short` and `git diff --stat` at end.

## VALIDATION
```bash
# 1. New tests pass
python3 -m pytest tests/test_paper_b_delayed_grant.py \
                  tests/test_paper_c_full_cost_flat.py \
                  tests/test_paper_d_liquidation_matrix.py \
                  tests/test_paper_e_pool_state.py \
                  tests/test_paper_f_crash_recovery.py -v

# 2. A-F combined (A from W1, B-F new, G from W2)
python3 -m pytest tests/test_paper_a_no_grant.py \
                  tests/test_paper_b_delayed_grant.py \
                  tests/test_paper_c_full_cost_flat.py \
                  tests/test_paper_d_liquidation_matrix.py \
                  tests/test_paper_e_pool_state.py \
                  tests/test_paper_f_crash_recovery.py \
                  tests/test_paper_g_whitelist_gate.py -v

# 3. Daemon entry test (R3 baseline) — no regression
python3 -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py tests/test_rh07_0_*.py tests/test_rh07_fix_c_*.py -q --tb=short -p no:cacheprovider

# 4. Schema migration idempotency check (new column)
python3 -c "
from scripts.lp_rh_store_v1_readonly import open_store, migrate
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    c = open_store(os.path.join(d, 's.db'))
    migrate(c); migrate(c)
    cols = [r[1] for r in c.execute(\"PRAGMA table_info(rh_position_marks)\").fetchall()]
    assert 'invalid_for_paper_evaluation' in cols, cols
    print('schema OK; invalid_for_paper_evaluation present')
    c.close()
"

# 5. Sanity: D matrix has 36 combinations
python3 -c "
combos = [(p, d0, d1, r) for p in [1, 10, 50, 1000] for d0, d1 in [(18,6), (6,18), (18,18)] for r in [5, 10, 50, 90]]
print('D matrix size:', len(combos))
"

# 6. Full pytest — count pass/fail
python3 -m pytest tests/ -q --tb=line -p no:cacheprovider 2>&1 | tail -3
```

## UNRESOLVED (mark in report if hit)
- `compute_liquidation_nav` cannot be called with synthetic `(l_pos, price, range, fee_growth_*, decimals)` without importing the full shadow stack → BLOCKED.
- `rh_position_marks.invalid_for_paper_evaluation` column already added by R3 in another path → no-op; verify with PRAGMA before adding.
- Test C requires the daemon to honor `entry_cost_usd / exit_cost_usd / gas_usd` cfg fields. If today the daemon ignores them, C must FAIL — do not silently pass by skipping these costs.

## FAILURE HANDLING
If any validation step fails, return the original error + which test failed + last 30 lines of pytest output. Do NOT modify the spec. Do NOT skip tests. Do NOT silence errors with try/except.
