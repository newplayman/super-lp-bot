from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_pool_resolve_and_rank_v1_readonly import (
    AERODROME_SLIPSTREAM_FACTORIES,
    AmbiguousMultiFactoryPoolError,
    ObservedRangeDomainError,
    PoolResolutionIncompleteError,
    SELECTOR_GET_POOL_AERODROME,
    SELECTOR_GET_POOL_UNISWAP,
    build_aerodrome_get_pool_calldata,
    build_uniswap_get_pool_calldata,
    composite_score,
    encode_address_word,
    encode_int_word,
    latest_swap_cost_state,
    _measure_range_and_replay,
    resolve_pool_with_provenance,
    reward_adjusted_cover,
)


def _address_word(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def test_m0f_aerodrome_registry_uses_only_unique_fully_validated_pool() -> None:
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    pool = "0x" + "aa" * 20
    gauges_v3 = AERODROME_SLIPSTREAM_FACTORIES[-1]

    def rpc(method, params):
        if method == "eth_getCode":
            return "0x6000"
        assert method == "eth_call"
        to = params[0]["to"].lower()
        data = params[0]["data"]
        if to == gauges_v3["factory"].lower() and data.startswith(SELECTOR_GET_POOL_AERODROME):
            return _address_word(pool)
        if to in {item["factory"].lower() for item in AERODROME_SLIPSTREAM_FACTORIES}:
            return _address_word("0x" + "00" * 20)
        if to == pool:
            if data == "0x0dfe1681":
                return _address_word(token_b)
            if data == "0xd21220a7":
                return _address_word(token_a)
            if data == "0xd0c93a7c":
                return "0x" + format(200, "064x")
        if data == "0x313ce567" and to in {token_a, token_b}:
            return "0x" + format(18, "064x")
        raise AssertionError((to, data))

    resolution = resolve_pool_with_provenance(
        rpc, "aerodrome-slipstream", token_a, token_b, 200, {}
    )

    assert resolution["pool"] == pool
    assert resolution["factory_label"] == "gauges_v3"
    assert resolution["factory"] == gauges_v3["factory"].lower()
    assert resolution["validated_token_set"] == sorted([token_a, token_b])
    assert resolution["validated_tick_spacing"] == 200
    assert resolution["factory_registry_source"].startswith("official:")


def test_m0f_aerodrome_registry_rejects_multiple_valid_addresses_without_ranking() -> None:
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    pools = {
        AERODROME_SLIPSTREAM_FACTORIES[1]["factory"].lower(): "0x" + "aa" * 20,
        AERODROME_SLIPSTREAM_FACTORIES[2]["factory"].lower(): "0x" + "bb" * 20,
    }

    def rpc(method, params):
        if method == "eth_getCode":
            return "0x6000"
        assert method == "eth_call"
        to = params[0]["to"].lower()
        data = params[0]["data"]
        if to in {item["factory"].lower() for item in AERODROME_SLIPSTREAM_FACTORIES}:
            return _address_word(pools.get(to, "0x" + "00" * 20))
        if to in pools.values():
            if data == "0x0dfe1681":
                return _address_word(token_a)
            if data == "0xd21220a7":
                return _address_word(token_b)
            if data == "0xd0c93a7c":
                return "0x" + format(200, "064x")
        if data == "0x313ce567" and to in {token_a, token_b}:
            return "0x" + format(18, "064x")
        raise AssertionError((to, data))

    with pytest.raises(AmbiguousMultiFactoryPoolError) as caught:
        resolve_pool_with_provenance(
            rpc, "aerodrome-slipstream", token_a, token_b, 200, {}
        )
    assert sorted(caught.value.valid_pool_addresses) == sorted(pools.values())
    assert caught.value.reason == "ambiguous_multi_factory_pool"


def test_m0f_factory_partial_rpc_failure_cannot_be_treated_as_unique() -> None:
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    pool = "0x" + "aa" * 20
    failed_factory = AERODROME_SLIPSTREAM_FACTORIES[0]["factory"].lower()
    good_factory = AERODROME_SLIPSTREAM_FACTORIES[2]["factory"].lower()

    def rpc(method, params):
        if method == "eth_getCode":
            return "0x6000"
        to = params[0]["to"].lower()
        data = params[0]["data"]
        if to == failed_factory:
            raise TimeoutError("factory unavailable")
        if to == good_factory and data.startswith(SELECTOR_GET_POOL_AERODROME):
            return _address_word(pool)
        if to in {item["factory"].lower() for item in AERODROME_SLIPSTREAM_FACTORIES}:
            return _address_word("0x" + "00" * 20)
        if to == pool and data == "0x0dfe1681":
            return _address_word(token_a)
        if to == pool and data == "0xd21220a7":
            return _address_word(token_b)
        if to == pool and data == "0xd0c93a7c":
            return "0x" + format(200, "064x")
        if to in {token_a, token_b} and data == "0x313ce567":
            return "0x" + format(18, "064x")
        raise AssertionError((method, to, data))

    with pytest.raises(PoolResolutionIncompleteError):
        resolve_pool_with_provenance(
            rpc, "aerodrome-slipstream", token_a, token_b, 200, {}
        )


def test_m0f_same_pool_across_factories_is_deduped_with_all_provenance() -> None:
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    pool = "0x" + "aa" * 20
    returning = {
        AERODROME_SLIPSTREAM_FACTORIES[1]["factory"].lower(),
        AERODROME_SLIPSTREAM_FACTORIES[2]["factory"].lower(),
    }

    def rpc(method, params):
        if method == "eth_getCode":
            return "0x6000"
        to = params[0]["to"].lower()
        data = params[0]["data"]
        if to in returning and data.startswith(SELECTOR_GET_POOL_AERODROME):
            return _address_word(pool)
        if to in {item["factory"].lower() for item in AERODROME_SLIPSTREAM_FACTORIES}:
            return _address_word("0x" + "00" * 20)
        if to == pool and data == "0x0dfe1681":
            return _address_word(token_a)
        if to == pool and data == "0xd21220a7":
            return _address_word(token_b)
        if to == pool and data == "0xd0c93a7c":
            return "0x" + format(200, "064x")
        if to in {token_a, token_b} and data == "0x313ce567":
            return "0x" + format(18, "064x")
        raise AssertionError((method, to, data))

    resolution = resolve_pool_with_provenance(
        rpc, "aerodrome-slipstream", token_a, token_b, 200, {}
    )
    assert resolution["pool"] == pool
    assert sorted(resolution["factory_labels"]) == ["gauge_caps", "gauges_v3"]


def test_m0f_observed_range_gte_100_is_rejected_before_replay_with_raw_evidence() -> None:
    called = {"replay": False}

    def forbidden_replay(*args, **kwargs):
        called["replay"] = True
        raise AssertionError("replay must not run outside its range domain")

    swaps = [
        {"block": 1, "price": 2_000.0},
        {"block": 2, "price": 2_100.0},
    ]
    live = {
        "hourly_closes": lambda rows: [(0, 2_000.0), (1, 2_100.0)],
        "daily_vol_from_closes": lambda closes: (0.50, 1),
        "recommend_range_pct": lambda sigma, horizon: 224.5,
        "replay": forbidden_replay,
    }

    with pytest.raises(ObservedRangeDomainError) as caught:
        _measure_range_and_replay(live, swaps, 0.0005, 18, 6)

    evidence = caught.value.evidence
    assert evidence == {
        "measured_sigma_daily": 0.50,
        "measured_horizon_days": 14.0,
        "measured_range_pct": 224.5,
        "measured_entry_price_token1_per_token0": 2_000.0,
        "measured_lower_bound_token1_per_token0": -2_490.0,
    }
    assert caught.value.reason == "observed_range_gte_100"
    assert called["replay"] is False


@pytest.mark.parametrize(
    ("observed_range", "reason"),
    [(100.0, "observed_range_gte_100"), (float("nan"), "observed_range_non_finite")],
)
def test_m0f_range_domain_boundary_and_nonfinite_never_reach_replay(
    observed_range, reason
) -> None:
    called = {"replay": 0}

    def forbidden(*args, **kwargs):
        called["replay"] += 1

    live = {
        "hourly_closes": lambda rows: [(0, 1.0), (1, 1.1)],
        "daily_vol_from_closes": lambda closes: (0.2, 1),
        "recommend_range_pct": lambda sigma, horizon: observed_range,
        "replay": forbidden,
    }
    with pytest.raises(ObservedRangeDomainError) as caught:
        _measure_range_and_replay(
            live,
            [{"block": 1, "price": 1.0}, {"block": 2, "price": 1.1}],
            0.0005,
            18,
            6,
        )
    assert caught.value.reason == reason
    assert called["replay"] == 0


def test_w6_latest_swap_price_and_raw_liquidity_are_carried_without_tvl_guess() -> None:
    out = latest_swap_cost_state([
        {"price": 2.5, "liquidity": 123, "block": 1},
        {"price": 2.75, "liquidity": 456, "block": 2},
    ])
    assert out == {
        "last_swap_price_token1_per_token0": 2.75,
        "last_swap_liquidity_raw": 456,
        "last_swap_cost_state_source": "measured:latest_decoded_swap_event",
    }
    assert latest_swap_cost_state([{"price": 2.0, "liquidity": 0}])[
        "last_swap_liquidity_raw"
    ] is None


def test_abi_encode_helpers_address_and_int24() -> None:
    address = "0x1234567890abcdef1234567890ABCDEF12345678"
    encoded_address = encode_address_word(address)
    assert encoded_address == "0x" + "0" * 24 + "1234567890abcdef1234567890abcdef12345678"

    encoded_positive = encode_int_word(60, bits=24)
    assert encoded_positive.startswith("0x")
    assert len(encoded_positive) == 66
    assert encoded_positive.endswith("3c".rjust(64, "0"))

    encoded_negative = encode_int_word(-1, bits=24)
    assert encoded_negative == "0x" + "f" * 58 + "ffffff"


def test_get_pool_calldata_builders_prefix_and_length() -> None:
    token_a = "0x00000000000000000000000000000000000000aa"
    token_b = "0x00000000000000000000000000000000000000bb"

    uni = build_uniswap_get_pool_calldata(token_a, token_b, 500)
    aero = build_aerodrome_get_pool_calldata(token_a, token_b, 60)

    assert uni.startswith(SELECTOR_GET_POOL_UNISWAP)
    assert aero.startswith(SELECTOR_GET_POOL_AERODROME)
    assert len(uni) == 2 + 8 + 64 * 3
    assert len(aero) == 2 + 8 + 64 * 3
    assert uni[10:] != ""
    assert aero[10:] != ""


def test_reward_adjusted_cover_math_and_zero_il() -> None:
    cover = reward_adjusted_cover(
        fees_quote=0.01,
        il_quote=-0.02,
        apy_reward=12.0,
        window_days=2.0,
    )
    assert cover["fee_apr"] > 0
    assert cover["reward_apr"] == 12.0
    assert cover["total_income_apr"] > cover["reward_apr"]
    assert cover["il_apr"] > 0
    assert cover["yield_cover"] > 0

    zero_il = reward_adjusted_cover(
        fees_quote=0.01,
        il_quote=0.0,
        apy_reward=0.0,
        window_days=1.0,
    )
    assert math.isinf(zero_il["yield_cover"])


def test_composite_score_penalties_and_clamp() -> None:
    clean = {
        "status": "OK",
        "resolve_status": "OK",
        "tier": "A",
        "suspect": [],
        "wash_flag": False,
        "total_income_apr": 90.0,
        "il_apr": 10.0,
        "yield_cover": 9.0,
    }
    suspect = dict(clean, suspect=["odd-metadata"])
    wash = dict(clean, wash_flag=True)
    weak_cover = dict(clean, total_income_apr=40.0, il_apr=80.0, yield_cover=0.5)
    extreme = dict(clean, total_income_apr=150000.0, il_apr=10.0, yield_cover=500.0)

    clean_score = composite_score(clean)
    suspect_score = composite_score(suspect)
    wash_score = composite_score(wash)
    weak_cover_score = composite_score(weak_cover)
    extreme_score = composite_score(extreme)

    assert clean_score > suspect_score
    assert wash_score == 0.0
    assert clean_score > weak_cover_score
    assert extreme_score <= clean_score
