from __future__ import annotations

import pytest

from scripts.lp_universe_second_opinion_v1_readonly import analyze, il_tolerance_apr


def _raw(identity="one", **changes):
    row = {
        "chain": "Base",
        "project": "aerodrome-slipstream",
        "symbol": "WETH-USDC",
        "tvlUsd": 2_000_000.0,
        "apyBase": 20.0,
        "apyReward": 0.0,
        "apy": 20.0,
        "apyMean30d": 20.0,
        "volumeUsd1d": 500_000.0,
        "sigma": 1.0,
        "ilRisk": "yes",
        "stablecoin": False,
        "poolMeta": "CL50 - 0.05%",
        "pool": identity,
        "rewardTokens": None,
    }
    row.update(changes)
    return row


def test_reuses_terminal_shaped_proxy_and_reports_il_tolerance():
    report = analyze([_raw()], top_n=50)
    row = report["top_50"][0]
    assert report["model"]["implementation"].endswith("proxy_netcover")
    assert row["proxy_status"] == "CALCULABLE"
    assert row["proxy_netcover"] > 0
    assert row["proxy_il_tolerance_apr_pct"] == pytest.approx(
        (row["proxy_income_apr_pct"] - 3.1511666666666667) / 1.5
    )
    assert report["model"]["proxy_is_entry_gate"] is False


def test_reports_coarse_failures_instead_of_hiding_leads():
    report = analyze([_raw(volumeUsd1d=1.0, apyBase=100.0)], top_n=50)
    row = report["top_50"][0]
    assert row["stage1_gate_ok"] is False
    assert "vol1d" in row["stage1_gate_reason"]
    assert row["proxy_netcover"] is not None


def test_scope_is_independent_and_zero_rpc():
    report = analyze([
        _raw("base"),
        _raw("other-project", project="aerodrome-v1"),
        _raw("other-chain", chain="Solana", project="orca-dex"),
    ])
    assert report["scope"]["scoped_pools"] == 1
    assert report["scope"]["network"].endswith("zero RPC")
    assert [row["llama_pool_id"] for row in report["top_50"]] == ["base"]


def test_missing_proxy_input_is_ranked_after_calculable_and_reasoned():
    report = analyze([_raw("missing", sigma=None), _raw("good")])
    assert [row["llama_pool_id"] for row in report["top_50"]] == ["good", "missing"]
    assert report["top_50"][1]["proxy_reason"] == "sigma_unavailable"
    assert report["proxy_unavailable_reasons"] == {"sigma_unavailable": 1}


def test_il_tolerance_missing_inputs_fails_closed():
    assert il_tolerance_apr({}) is None
