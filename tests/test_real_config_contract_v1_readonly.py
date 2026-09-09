"""Real-config contract tests for reports/lp_rh/pool_meta.json (RH-02ay).

RH-02ai shipped 6 green tests but its production path crashed on first call:
pool_meta.json stores input_price_usd as the string "2484.0" while every
fixture used the float 2484.0, so position_liquidity_raw's `entry_price <= 0`
raised TypeError.  Confirmed defect class #14 (fixture disagrees with the real
contract), recurred many times.  The lesson: a fixture that disagrees with the
real contract lets a must-crash production path land green.

This module pins the real contract instead of a fixture, in three ways:

  1. type-lock every key of the real pool_meta.json (a collector change that
     flips a key's type turns the matching test red immediately);
  2. drive each independently-callable consumer with the REAL pool_meta (not a
     fixture) and assert it does not raise and returns a non-None value;
  3. a general guard: every key that must be numeric is actually
     numeric-convertible (int/float/numeric-string pass; None/"N/A"/"" fail).

Read-only: it only reads local files and the local scanner.db.  No network, no
wallet, no broadcast.  If the real db is absent the db-driven test skips with a
reason rather than pretending to pass.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.lp_rh_exit_depth_v1_readonly import exit_depth_for_size
from scripts.lp_rh_shadow_runner_v1_readonly import (
    load_samples_from_db,
    run_episode,
)
from scripts.lp_rh_store_v1_readonly import migrate, open_store

REPO_ROOT = Path(__file__).resolve().parents[1]
POOL_META_PATH = REPO_ROOT / "reports" / "lp_rh" / "pool_meta.json"
LIVE_DB = REPO_ROOT / "reports" / "lp_rh" / "scanner.db"
DEFAULT_POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"

# Keys whose Python type we lock to the value the real collector currently
# emits.  A change to any of them (e.g. the collector now writing a float where
# it wrote a str) turns the matching test red instead of surfacing later as a
# production crash in some consumer.
EXPECTED_TYPES = {
    "input_price_usd": "str",
    "range_pct": "float",
    "dec0": "int",
    "dec1": "int",
    "gas_usd_estimate": "float",
    "tvl_usd": "float",
    "liquidity": "int",
    "sqrt_price_x96": "int",
    "current_tick": "int",
    "tick_spacing": "int",
    "fee_pips": "int",
    "attestation_status": "str",
    "protocol": "str",
    "tick_data": "list",
}

# Top-level keys that must be numeric in nature.  The check is deliberately
# loose (float(value) must not raise): an int, a float, or a numeric string all
# pass.  A value that is None / "N/A" / "" fails immediately.
NUMERIC_KEYS = (
    "input_price_usd",
    "range_pct",
    "dec0",
    "dec1",
    "gas_usd_estimate",
    "tvl_usd",
    "liquidity",
    "sqrt_price_x96",
    "current_tick",
    "tick_spacing",
    "fee_pips",
    "token0_decimals",
    "token1_decimals",
    "max_impact_bps",
    "fee",
    "liquidity_raw",
    "fee_apr_pct",
    "sigma_daily",
    "active_liquidity_notional_usd",
)


def _load_pool_meta() -> dict:
    with open(POOL_META_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def pool_meta() -> dict:
    return _load_pool_meta()


# ---------------------------------------------------------------------------
# 1. Type-lock every key of the real pool_meta.json.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,expected", sorted(EXPECTED_TYPES.items()))
def test_pool_meta_key_type(pool_meta, key, expected):
    assert key in pool_meta, f"pool_meta missing key {key!r}"
    actual = type(pool_meta[key]).__name__
    assert actual == expected, (
        f"pool_meta[{key!r}] type drifted: expected {expected}, got {actual} "
        f"(value={pool_meta[key]!r})")


# ---------------------------------------------------------------------------
# 2. Drive each independently-callable consumer with the REAL pool_meta.
# ---------------------------------------------------------------------------

def test_exit_depth_for_size_with_real_pool_meta(pool_meta):
    # pool_state is the whole pool_meta minus the three keys the caller passes
    # separately (attestation_status / protocol / max_impact_bps), exactly as
    # the shadow_runner's position_and_exit_depth_pass conjunct builds it.
    pool_state = {k: v for k, v in pool_meta.items()
                  if k not in ("attestation_status", "protocol", "max_impact_bps")}
    depth = exit_depth_for_size(
        position_value_usd=Decimal("1000"),
        max_impact_bps=Decimal(str(pool_meta.get("max_impact_bps", 50))),
        **pool_state)
    assert isinstance(depth, dict) and depth, "exit_depth_for_size returned no dict"
    assert depth.get("sufficient") is not None, "exit_depth_for_size missing 'sufficient'"


def test_run_episode_with_real_pool_meta(pool_meta, tmp_path):
    if not LIVE_DB.exists():
        pytest.skip(f"live scanner.db not present: {LIVE_DB}")
    live = open_store(LIVE_DB, read_only=True)
    try:
        samples, _skipped = load_samples_from_db(live, pool=DEFAULT_POOL, limit=20)
    finally:
        live.close()
    assert samples, "no real samples loaded from live scanner.db"
    conn = open_store(tmp_path / "scratch.db", read_only=False)
    try:
        migrate(conn)
        steps = run_episode(
            conn, strategy_episode="rh-contract", samples=samples,
            position_usd=Decimal("1000"), horizon_hours=24.0,
            capital_usd=Decimal("10000"), target_mode="SHADOW_SCENARIO",
            now_fn=lambda: "2026-01-01T00:00:00Z", pool_meta=pool_meta)
    finally:
        conn.close()
    assert isinstance(steps, list) and steps, "run_episode returned no steps"


# ---------------------------------------------------------------------------
# 3. General guard: numeric keys must be numeric-convertible.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", NUMERIC_KEYS)
def test_pool_meta_numeric_key_convertible(pool_meta, key):
    assert key in pool_meta, f"pool_meta missing numeric key {key!r}"
    value = pool_meta[key]
    try:
        float(value)
    except (TypeError, ValueError) as exc:
        pytest.fail(f"pool_meta[{key!r}] = {value!r} is not numeric-convertible: {exc}")
