from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path("/Users/bendu/lp-bot/v3/scripts/lp_quote_depth_curve_v1_readonly.py")
spec = importlib.util.spec_from_file_location("lp_quote_depth_curve_v1_readonly", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_notionals_list_complete():
    assert mod.TESTED_NOTIONALS == [20, 100, 500, 1000, 2000]


def test_no_wallet_or_private_key_runtime_symbols():
    src = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    banned = [
        "private_key",
        "mnemonic",
        "sendtransaction",
        "send_transaction",
        "eth_sendrawtransaction",
        "sign_transaction",
        "web3.eth.account",
    ]
    for token in banned:
        assert token not in src


def test_invalid_candidate_produces_reject_reason():
    rows = mod.select_candidate_pools(
        [
            {
                "pool_id": "bad",
                "token_pair": "X/Y",
                "inferred_tier": "B",
                "has_entry_safe_snapshot": "no",
                "chain": "1",
                "protocol": "unknown",
                "liquidity": "0",
                "tvl_usd": "0",
                "vol_24h": "0",
                "fee_bps": "",
                "tick": "",
                "sample_count": "",
                "exit_depth_20_med": "",
                "slippage_20_med": "",
                "fee_velocity_med": "",
            }
        ]
    )
    assert rows[0]["selected_for_quote_depth"] == "no"
    assert rows[0]["reject_reason"] != ""


def test_slippage_monotonic_sanity():
    base = 0.01
    alpha = mod.protocol_alpha("concentrated_liquidity")
    vals = [mod.slippage_for_notional(20.0, base, n, alpha, 1.0) for n in mod.TESTED_NOTIONALS]
    assert vals == sorted(vals)


def test_output_schema_required_fields():
    fields = {
        "pool_id",
        "token_pair",
        "pool_type",
        "virtual_notional_usd",
        "quote_source",
        "estimated_slippage_pct",
        "estimated_price_impact_pct",
        "exit_depth_available",
        "exit_depth_usd",
        "capacity_pass",
        "capacity_limit_usd",
        "confidence",
        "invalid_reason",
    }
    row = mod.build_quote_results(
        [
            {
                "pool_id": "p1",
                "token_pair": "A/B",
                "selected_for_quote_depth": "yes",
                "pool_type": "concentrated_liquidity",
                "chain_name": "base",
                "slippage_20_med": "0.01",
                "tvl_usd": "1000000",
                "vol_24h": "500000",
            }
        ]
    )[0]
    assert fields.issubset(row.keys())


def test_secret_redaction():
    text = "DATABASE_URL=postgres://u:p@host/db"
    redacted = mod.redact_secretish(text)
    assert "postgres://" not in redacted
    assert "<redacted" in redacted
