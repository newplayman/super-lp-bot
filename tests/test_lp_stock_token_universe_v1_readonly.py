from __future__ import annotations

import json

import pytest

from scripts import lp_stock_token_universe_v1_readonly as universe


def pool(
    symbol, *, chain="Solana", project="raydium-amm", tvl=30_000, volume=15_000,
    underlying_tokens=None, pool_meta="Concentrated - 0.25%",
):
    return {
        "pool": f"pool-{symbol}-{project}",
        "chain": chain,
        "project": project,
        "symbol": symbol,
        "tvlUsd": tvl,
        "volumeUsd1d": volume,
        "apyBase": 20,
        "apyReward": 3,
        "apy": 23,
        "ilRisk": "yes",
        "exposure": "multi",
        "underlyingTokens": underlying_tokens,
        "poolMeta": pool_meta,
    }


def test_backed_and_wrapped_backed_identity_are_issuer_scoped():
    direct = universe.identify_stock_token("TSLAx", chain="Solana", project="raydium-amm")
    wrapped = universe.identify_stock_token("WTSLAX", chain="Ethereum", project="uniswap-v3")
    assert direct == {
        "instrument_id": "backed:TSLAX",
        "issuer": "Backed",
        "underlying_ticker": "TSLA",
        "price_semantics": "token",
        "pool_token_symbol": "TSLAX",
        "canonical_token_symbol": "TSLAX",
        "wrapped": False,
        "recognition_basis": "reviewed_backed_xstocks_catalogue",
    }
    assert wrapped["instrument_id"] == direct["instrument_id"]
    assert wrapped["wrapped"] is True


def test_ondo_robinhood_and_unknown_never_collapse_same_underlying():
    ondo = universe.identify_stock_token("TSLAON", chain="Ethereum", project="uniswap-v4")
    robinhood = universe.identify_stock_token("TSLA", chain="Robinhood Chain", project="ekubo")
    unknown = universe.identify_stock_token("TSLA", chain="Defichain", project="defichain-dex")
    assert [ondo["issuer"], robinhood["issuer"], unknown["issuer"]] == [
        "Ondo", "Robinhood", "unknown",
    ]
    assert len({ondo["instrument_id"], robinhood["instrument_id"], unknown["instrument_id"]}) == 3
    assert {ondo["underlying_ticker"], robinhood["underlying_ticker"], unknown["underlying_ticker"]} == {"TSLA"}


@pytest.mark.parametrize("token", ["FLUX", "GMX", "HDX", "RANDOMX", "MOONON", "STONK"])
def test_suffixes_are_not_guessed(token):
    assert universe.identify_stock_token(token, chain="Base", project="uniswap-v3") is None


@pytest.mark.parametrize(
    ("symbol", "project", "expected_tier", "expected_protocol"),
    [
        ("INTCX-USDC", "raydium-amm", "A", "clmm"),
        ("WSOL-MSTRX", "raydium-amm", "B", "clmm"),
        ("SPYX-SSX", "raydium-amm", "C", "clmm"),
        ("TQQQX-SPYX", "orca-dex", "stock_stock", "clmm"),
        ("NVDAX-USDC", "orca-dex", "A", "clmm"),
    ],
)
def test_pair_tier_and_protocol_dispatch(symbol, project, expected_tier, expected_protocol):
    row = universe.normalize_pool(pool(symbol, project=project))
    assert row["tier"] == expected_tier
    assert row["protocol_type"] == expected_protocol


def test_wash_suspect_threshold_is_strictly_greater_than_1_5():
    boundary = universe.normalize_pool(pool("SPYX-SSX", tvl=20_000, volume=30_000))
    above = universe.normalize_pool(pool("SPYX-STONK", tvl=20_000, volume=30_001))
    assert boundary["vol1d_tvl"] == 1.5
    assert boundary["wash_suspect"] is False
    assert above["wash_suspect"] is True
    assert above["tier"] == "C"


def test_non_dex_single_asset_and_low_tvl_are_excluded():
    single = pool("SPYX-USDC")
    single.update({"ilRisk": "no", "exposure": "single"})
    assert universe.normalize_pool(single) is None
    assert universe.normalize_pool(pool("SPYX-USDC", tvl=19_999)) is None


def test_unknown_protocol_is_explicit_and_fail_closed_for_downstream_dispatch():
    row = universe.normalize_pool(
        pool("AAPL-USDC", chain="Solana", project="gmtrade", pool_meta=None)
    )
    assert row["issuer"] == "unknown"
    assert row["protocol_type"] == "unknown"


@pytest.mark.parametrize("meta", ["Standard - 0.25%", "AMM - 0.25%", "CPMM - 0.25%", "constant product"])
def test_raydium_requires_explicit_constant_product_metadata(meta):
    row = universe.normalize_pool(pool("INTCX-USDC", pool_meta=meta))
    assert row["protocol_type"] == "amm_constant_product"


@pytest.mark.parametrize("meta", [None, "0.25%", "opaque"])
def test_raydium_ambiguous_metadata_fails_closed(meta):
    row = universe.normalize_pool(pool("INTCX-USDC", pool_meta=meta))
    assert row["protocol_type"] == "unknown"


def test_pool_meta_overrides_legacy_project_slug():
    row = universe.normalize_pool(pool("INTCX-USDC", pool_meta="Concentrated - 1%"))
    assert row["project"] == "raydium-amm"
    assert row["pool_meta"] == "Concentrated - 1%"
    assert row["protocol_type"] == "clmm"


@pytest.mark.parametrize("project", ["raydium-amm", "orca-dex"])
def test_solana_two_leg_underlying_addresses_are_preserved_exactly(project):
    token_addresses = [
        "XsTocK11111111111111111111111111111111111",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    ]
    row = universe.normalize_pool(
        pool("NVDAX-USDC", project=project, underlying_tokens=token_addresses)
    )
    assert row["underlying_tokens"] == token_addresses
    assert row["underlying_tokens"] is not token_addresses


@pytest.mark.parametrize(
    "bad_value",
    [None, [], ["valid", ""], ["valid", None], "not-a-list"],
)
def test_missing_or_malformed_underlying_addresses_are_not_guessed(bad_value):
    assert universe.preserve_underlying_tokens(bad_value) is None


def test_build_summary_and_outputs_preserve_unknown_count(tmp_path):
    rows = universe.build_universe([
        pool("INTCX-USDC"),
        pool("AAPL-DUSD", chain="Defichain", project="defichain-dex"),
        pool("USDT-SPYON", chain="BSC", project="uniswap-v3"),
        pool("WETH-FLUX", chain="Base", project="uniswap-v3"),
    ])
    summary = universe.write_outputs(
        rows, out_dir=tmp_path, as_of="2026-08-10T00:00:00+00:00", input_source="fixture.json",
    )
    assert summary["pool_count"] == 3
    assert summary["issuer_unknown_pool_count"] == 1
    assert summary["tier_counts"]["A"] == 3
    payload = json.loads((tmp_path / "stock_token_universe.json").read_text())
    assert payload["schema_version"] == "lp_stock_token_universe_v1"
    assert len(payload["rows"]) == 3
    assert "Stage-1 leads only" in (tmp_path / "SUMMARY.md").read_text()


def test_malformed_snapshot_fails_closed():
    with pytest.raises(universe.UniverseError):
        universe.build_universe({"data": {}})
