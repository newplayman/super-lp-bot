import pytest

from scripts.lp_tier_b_level2_replay_v1_readonly import replay as replay_func

import scripts.lp_tier_b_level2_replay_v1_readonly as replay_mod


def _swaps(prices):
    return [{"block": i + 1, "price": p, "liquidity": 10_000_000, "amount1": 10**18} for i, p in enumerate(prices)]


def test_replay_round_trip_passive():
    swaps = _swaps([1.0, 1.05, 1.0])
    out = replay_func(swaps, range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="passive")

    assert out["mode"] == "passive"
    assert out["n_swaps"] == 3
    assert out["net_pct"] is not None and out["net_pct"] > 0
    assert out["fees_quote"] > 0
    assert abs(out["il_quote"]) < 1e-9


def test_replay_trend_passive_vs_active():
    swaps = _swaps([1.0, 1.12, 1.2, 1.0])
    passive = replay_func(swaps, range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="passive", gas_pct=0.001, swap_cost_bps=5)
    active = replay_func(swaps, range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="active", gas_pct=0.001, swap_cost_bps=5)

    assert passive["mode"] == "passive"
    assert active["mode"] == "active"
    assert passive["rebalances"] == 0
    assert active["rebalances"] >= 1
    assert passive["fees_quote"] > 0
    assert active["fees_quote"] > 0
    assert active["rebal_cost_quote"] > 0
    assert passive["net_pct"] is not None
    assert active["net_pct"] is not None


def test_replay_in_range_fee_only_passive(monkeypatch):
    calls = []

    def fake_fee_for_swap_usd(position_liq_raw, active_liq, amount1, fee_tier, dec1):
        calls.append((position_liq_raw, active_liq, amount1, fee_tier, dec1))
        return 1.0

    monkeypatch.setattr(replay_mod, "fee_for_swap_usd", fake_fee_for_swap_usd)

    swaps = _swaps([1.0, 1.5])
    out = replay_func(swaps, range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="passive")

    assert out["n_swaps"] == 2
    assert abs(out["frac_swaps_in_range"] - 0.5) < 1e-12
    assert out["fees_quote"] == pytest.approx(1.0)
    assert len(calls) == 1


def test_replay_no_data():
    out = replay_func([], range_pct=10, fee_tier=0.003, dec0=18, dec1=18, mode="passive")

    assert out["net_pct"] is None
    assert out["verdict"] == "NO_DATA"
    assert out["fees_quote"] is None
    assert out["rebalances"] is None
    assert out["n_swaps"] == 0
