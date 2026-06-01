from pathlib import Path
import importlib.util
import sys


SCRIPT_PATH = Path("/Users/bendu/lp-bot/v3/scripts/lp_quote_depth_curve_v2_readonly.py")
spec = importlib.util.spec_from_file_location("lp_quote_depth_curve_v2_readonly", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_tested_notionals_fixed():
    assert module.TESTED_NOTIONALS == [20, 100, 500, 1000, 2000]


def test_no_wallet_or_tx_symbols_in_script():
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    banned = ["eth_sendrawtransaction", "sendtransaction(", "signtransaction(", "private_key=", "mnemonic="]
    for token in banned:
        assert token not in text


def test_schema_required_fields_present():
    required = [
        "run_id",
        "pool_id",
        "token_pair",
        "inferred_tier",
        "chain",
        "pool_type",
        "method",
        "quote_side",
        "virtual_notional_usd",
        "quote_ts",
        "feature_cutoff_time",
        "entry_safe",
        "reserve_liquidity_usd",
        "tvl_proxy_usd",
        "estimated_output_usd",
        "estimated_slippage_pct",
        "estimated_price_impact_pct",
        "exit_depth_available",
        "exit_depth_usd",
        "capacity_pass",
        "capacity_limit_usd",
        "confidence",
        "confidence_reason",
        "invalid_reason",
        "monotonicity_check",
        "created_at",
    ]
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    for field in required:
        assert f'"{field}"' in text


def test_invalid_pool_reason_explicit():
    candidate = module.Candidate(
        pool_id="x",
        token_pair="FOO/BAR",
        inferred_tier="B",
        chain="unknown",
        protocol="",
        pool_type="unknown",
        fee_bps=None,
        tvl_usd=None,
        vol_24h=None,
        liquidity_raw=None,
        tick_raw=None,
        updated_at="",
        entry_safe_rows=0,
        healthy_rate=None,
        fee_sample_count=0,
        fee_ok_rate=None,
        fee_velocity_med=None,
        exit_depth_20_med=None,
        slippage_20_med=None,
        token_decimals_known=False,
        source_bucket="test",
        priority_score=0.0,
    )
    rows = module.materialize_rows([candidate])
    assert all(row["invalid_reason"] == "missing_tvl_or_non_base" for row in rows)


def test_monotonic_sanity_and_confidence():
    candidate = module.Candidate(
        pool_id="y",
        token_pair="WETH/USDC",
        inferred_tier="A",
        chain="base",
        protocol="uniswap-v3-base",
        pool_type="concentrated_liquidity",
        fee_bps=1,
        tvl_usd=10_000_000,
        vol_24h=20_000_000,
        liquidity_raw=1000,
        tick_raw=1,
        updated_at="1",
        entry_safe_rows=10,
        healthy_rate=1.0,
        fee_sample_count=10,
        fee_ok_rate=1.0,
        fee_velocity_med=1.0,
        exit_depth_20_med=2000,
        slippage_20_med=0.02,
        token_decimals_known=True,
        source_bucket="test",
        priority_score=10.0,
    )
    rows = module.materialize_rows([candidate])
    slips = [r["estimated_slippage_pct"] for r in rows]
    assert slips == sorted(slips)
    assert rows[0]["confidence"] in {"high", "medium"}


def test_expanded_pool_selection_handles_missing_metadata():
    rows = [
        {
            "pool_id": "1",
            "token_pair": "WETH/USDC",
            "chain": "1",
            "protocol": "uniswap-v3-base",
            "fee_bps": "1",
            "tier": "A",
            "liquidity": "",
            "tick": "",
            "tvl_usd": "1000000",
            "vol_24h": "2000000",
            "updated_at": "1",
            "source_bucket": "expanded",
            "fee_sample_count": "0",
            "fee_ok_rate": "",
            "fee_velocity_med": "",
            "exit_depth_20_med": "",
            "slippage_20_med": "",
            "entry_safe_rows": "0",
            "healthy_rate": "",
        }
    ]
    candidates = module.build_candidates(rows)
    assert len(candidates) == 1
    assert candidates[0].token_decimals_known is True


def test_secret_redaction():
    text = "POSTGRES_DSN=postgres://foo:bar@example.com/db DATABASE_URL=postgresql://abc"
    redacted = module.redact_secretish(text)
    assert "example.com" not in redacted
    assert "<redacted" in redacted
