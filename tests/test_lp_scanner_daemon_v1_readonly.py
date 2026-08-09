from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.lp_scanner_daemon_v1_readonly import (
    DEFAULT_COARSE_INTERVAL_SECS,
    DEFAULT_TOP_INTERVAL_SECS,
    DefaultStages,
    MARKET_SESSION_COLUMNS,
    OPPORTUNITY_SCORE_COLUMNS,
    POOL_SNAPSHOT_COLUMNS,
    CycleResult,
    FunnelOrchestrator,
    ScannerDaemon,
    ScannerStore,
    ScreenBatch,
    export_latest_vetted_menu,
    main,
    _score_row,
)
from scripts.lp_tg_alerter_v1_readonly import ScannerAlertBridge


AS_OF = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


class FakeStages:
    def __init__(self):
        self.calls = []

    def screen(self):
        self.calls.append("screen")
        records = [
            {
                "chain": "Base",
                "project": "aerodrome-slipstream",
                "symbol": "WETH-USDC",
                "llama_pool_id": "llama-1",
                "resolved_pool": "0x1111111111111111111111111111111111111111",
                "tvlUsd": 2_000_000,
                "volumeUsd1d": 400_000,
                "apyBase": 18.0,
                "apyReward": 2.0,
                "price": 3_200.0,
                "liquidity": 900_000.0,
                "active_liquidity": 500_000.0,
                "range_pct": 8.0,
                "reference_price": 3_198.0,
                "basis_bps": 6.25,
                "market_session": "PRIMARY_CLOSED",
                "instrument_id": "AAPLX-USD",
                "source_timestamp": "2026-08-08T11:59:00+00:00",
                "redemption_status": "OPEN",
            }
        ]
        return ScreenBatch(all_records=records, candidates=records)

    def resolve(self, candidates):
        self.calls.append("resolve")
        return [dict(candidates[0], resolve_status="OK", status="OK")]

    def multiwindow(self, resolved):
        self.calls.append("multiwindow")
        return [
            {
                "pool": resolved[0]["resolved_pool"],
                "fee_cover_stability": {"stable": True, "enter_frac": 1.0},
            }
        ]

    def funnel(self, resolved, stability):
        self.calls.append("funnel_vet")
        return [dict(resolved[0], vetted=True, stable=True, rejection_reason=None)]

    def netcover(self, vetted):
        self.calls.append("netcover")
        return [
            dict(
                vetted[0],
                fee_ev_usd=5.0,
                reward_ev_usd=1.0,
                il_ev_usd=-1.5,
                lvr_ev_usd=-0.25,
                risk_usd=-0.5,
                expected_net_yield_usd=2.75,
                expected_net_yield_pct=0.275,
                netcover_ratio=1.8,
                netcover_pass=True,
            )
        ]


def _table_columns(db: Path, table: str):
    with sqlite3.connect(db) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_default_scanner_cadence_matches_task_package():
    assert DEFAULT_COARSE_INTERVAL_SECS == 15 * 60
    assert DEFAULT_TOP_INTERVAL_SECS == 60


def test_gate_db_failure_does_not_turn_completed_scanner_cycle_fatal(capsys):
    class Hook:
        def __init__(self):
            self.results = []

        def after_cycle(self, result):
            self.results.append(result)

    hook = Hook()
    daemon = ScannerDaemon(
        lambda refresh: None,
        event_hook=hook,
        rpc_health_recorder=lambda health: (_ for _ in ()).throw(sqlite3.OperationalError("locked")),
    )

    daemon._notify_cycle({"rpc_health": "NORMAL"})

    assert hook.results == [{"rpc_health": "NORMAL"}]
    assert "gate evidence write failed: OperationalError" in capsys.readouterr().err


def test_latest_vetted_menu_exports_only_live_accepted_records_and_fails_closed(tmp_path):
    db = tmp_path / "scanner.db"
    store = ScannerStore(db)
    store.write_cycle(
        AS_OF,
        pool_snapshots=[],
        opportunity_scores=[
            {
                "pool": "0x1",
                "source": "live",
                "accepted": True,
                "score_json": json.dumps({
                    "pool": "0x1", "vetted": True, "netcover_pass": True,
                    "tvlUsd": 1_000_000, "active_liquidity_notional_usd": 50_000,
                }),
            },
            {
                "pool": "0x2", "source": "live", "accepted": False,
                "score_json": json.dumps({"pool": "0x2", "vetted": False}),
            },
            {"pool": "0x3", "source": "live", "accepted": True, "score_json": "not-json"},
        ],
        market_sessions=[],
    )
    out = tmp_path / "vetted_menu.json"

    result = export_latest_vetted_menu(db, out)

    assert result["as_of"] == AS_OF.isoformat()
    assert result["accepted_rows"] == 2
    assert result["exported_records"] == 1
    assert result["invalid_records"] == 1
    assert json.loads(out.read_text())[0]["pool"] == "0x1"


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ("pool_snapshots", POOL_SNAPSHOT_COLUMNS),
        ("opportunity_scores", OPPORTUNITY_SCORE_COLUMNS),
        ("market_sessions", MARKET_SESSION_COLUMNS),
    ],
)
def test_sqlite_schema_contains_prd_v1_section_30_fields_plus_as_of(tmp_path, table, expected):
    db = tmp_path / "scanner.db"
    ScannerStore(db).initialize_schema()
    assert set(expected) <= _table_columns(db, table)
    assert "as_of" in _table_columns(db, table)


def test_once_executes_every_funnel_stage_and_persists_all_three_tables(tmp_path):
    db = tmp_path / "scanner.db"
    stages = FakeStages()

    rc = main(["--once", "--db", str(db)], stages=stages, now=lambda: AS_OF)

    assert rc == 0
    assert stages.calls == ["screen", "resolve", "multiwindow", "funnel_vet", "netcover"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM pool_snapshots").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM opportunity_scores").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM market_sessions").fetchone()[0] == 1
        accepted, reason = conn.execute(
            "SELECT accepted, rejection_reason FROM opportunity_scores"
        ).fetchone()
        assert accepted == 1
        assert reason is None
        session = conn.execute("SELECT market_session FROM market_sessions").fetchone()[0]
        assert session == "PRIMARY_CLOSED"


def test_coarse_screen_is_cached_between_top_candidate_cycles(tmp_path):
    stages = FakeStages()
    orchestrator = FunnelOrchestrator(stages, ScannerStore(tmp_path / "scanner.db"))

    orchestrator.run_once(refresh_coarse=True, as_of=AS_OF)
    orchestrator.run_once(refresh_coarse=False, as_of=AS_OF.replace(minute=1))

    assert stages.calls.count("screen") == 1
    assert stages.calls.count("resolve") == 2


def test_netcover_unavailable_is_fail_closed_and_explained(tmp_path):
    stages = FakeStages()

    def unavailable(records):
        return [dict(records[0], netcover_pass=False, rejection_reason="netcover unavailable")]

    stages.netcover = unavailable
    db = tmp_path / "scanner.db"
    FunnelOrchestrator(stages, ScannerStore(db)).run_once(refresh_coarse=True, as_of=AS_OF)

    with sqlite3.connect(db) as conn:
        accepted, reason = conn.execute(
            "SELECT accepted, rejection_reason FROM opportunity_scores"
        ).fetchone()
    assert accepted == 0
    assert reason == "netcover unavailable"


def test_m0f_permanent_reason_forces_rejection_and_survives_score_json():
    source = {
        "pool": "0x1",
        "symbol": "WETH-USDC",
        "vetted": True,
        "gates": {"quality": True, "yield_cover": True, "stable": True},
        "permanent_fail_closed_reason": "observed_range_gte_100",
        "permanent_fail_closed_r1a_classification": "OBSERVED_RANGE_EXCEEDS_MATH_DOMAIN",
        "measured_sigma_daily": 0.5,
        "measured_horizon_days": 14.0,
        "measured_range_pct": 224.5,
        "measured_entry_price_token1_per_token0": 2_000.0,
        "measured_lower_bound_token1_per_token0": -2_490.0,
    }
    malicious = dict(source, netcover=99.0, netcover_ratio=99.0, netcover_pass=True)

    final = DefaultStages._enforce_fifth_gate([source], [malicious])[0]
    row = _score_row(final)
    persisted = json.loads(row["score_json"])

    assert final["netcover_pass"] is False
    assert final["vetted"] is False
    assert final["netcover_ratio"] is None
    assert final["netcover_gate_status"] == "PERMANENT_FAIL_CLOSED"
    assert row["accepted"] is False
    assert row["netcover_ratio"] is None
    assert persisted["permanent_fail_closed_reason"] == "observed_range_gte_100"
    assert persisted["measured_range_pct"] == 224.5


def test_m0f_zero_liquidity_anchor_makes_cross_pool_evidence_incomplete(monkeypatch):
    class TipOnlyPool:
        def call(self, method, params, timeout=20):
            assert method == "eth_blockNumber"
            return "0x64"

        def health_snapshot(self):
            return {"state": "NORMAL"}

    stages = DefaultStages(rpc_pool=TipOnlyPool())
    monkeypatch.setattr(
        stages,
        "_measure_preregistered_slipstream_route",
        lambda spec, observed_block: {
            "route_id": spec["route_id"],
            "executable": False,
            "observed_block": observed_block,
        },
    )
    measured = stages._read_base_cross_pool_measurements()
    assert measured["complete"] is False
    assert measured["anchors"] == []
    assert "anchor route not executable" in measured["errors"][0]
    record_evidence = stages._scanner_cross_pool_evidence({
        "token0": "0x4200000000000000000000000000000000000006",
        "token1": "0x" + "22" * 20,
        "last_swap_price_token1_per_token0": 2.0,
    })
    assert record_evidence["complete"] is False
    assert "token1_usd" not in record_evidence


def test_m0f_watched_zero_liquidity_route_becoming_executable_requires_review(monkeypatch):
    class TipOnlyPool:
        def call(self, method, params, timeout=20):
            assert method == "eth_blockNumber"
            return "0x65"

        def health_snapshot(self):
            return {"state": "NORMAL"}

    stages = DefaultStages(rpc_pool=TipOnlyPool())
    monkeypatch.setattr(
        stages,
        "_measure_preregistered_slipstream_route",
        lambda spec, observed_block: {
            "route_id": spec["route_id"],
            "executable": True,
            "observed_block": observed_block,
        },
    )
    measured = stages._read_base_cross_pool_measurements()
    assert measured["complete"] is False
    assert measured["permanent_fail_closed_reason"] == (
        "preregistered_watchlist_became_executable"
    )
    assert "watched route became executable" in measured["errors"][0]
    assert "allowlist review required" in measured["errors"][0]


def test_wp04_adapter_is_the_strict_fifth_gate_not_only_a_diagnostic():
    complete = {
        "pool": "0x1",
        "vetted": True,
        "gates": {"quality": True, "yield_cover": True, "stable": True, "status_ok": True},
        "chain": "Base",
        "project": "uniswap-v3",
        "profile": "PASSIVE_CL",
        "holding_horizon_days": 14,
        "is_new_pool": False,
        "fee_apr_24h": 1_000.0,
        "fee_apr_7d": 1_000.0,
        "reward_apr": 0.0,
        "il_apr": 1.0,
        "sigma_pair": 0.01,
        "l_active_raw": 10**30,
        "price_usd": 1.0,
        "last_swap_price_token1_per_token0": 1.0,
        "last_swap_liquidity_raw": 10**30,
        "last_swap_cost_state_source": "measured:latest_decoded_swap_event",
        "token0": "0x4200000000000000000000000000000000000006",
        "token1": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "fee_tier": 0.0001,
        "dec0": 18,
        "dec1": 6,
    }
    missing = {
        "pool": "0x2",
        "chain": "Base",
        "vetted": True,
        "gates": {"quality": True},
        **{field: 0.0 for field in (
            "fee_ev_usd", "reward_ev_usd", "il_ev_usd", "entry_cost_usd",
            "exit_cost_usd", "gas_usd", "slippage_usd",
            "reward_conversion_cost_usd", "exit_latency_loss_usd",
        )},
    }

    passed, rejected = DefaultStages().netcover([complete, missing])

    assert passed["netcover_pass"] is True
    assert passed["gates"]["netcover_shadow"] is True
    assert passed["vetted"] is True
    assert rejected["netcover_pass"] is False
    assert rejected["gates"]["netcover_shadow"] is False
    assert rejected["netcover_gate_status"] == "MISSING_FAIL_CLOSED"
    assert rejected["vetted"] is False
    assert rejected["rejection_reason"].startswith("NETCOVER_INPUT_MISSING:")


def test_scanner_marks_prefifth_funnel_as_explicit_intermediate(monkeypatch):
    import scripts.lp_funnel_vet_v1_readonly as funnel

    observed = {}

    def intermediate(bridge, stability, **kwargs):
        observed.update(kwargs)
        return [dict(bridge[0], vetted=True)]

    monkeypatch.setattr(funnel, "funnel_vet", intermediate)
    out = DefaultStages().funnel([{"pool": "0x1"}], [])

    assert out[0]["vetted"] is True
    assert observed["allow_legacy_without_netcover"] is True


def test_w6_scanner_carries_er_horizon_and_reads_depth_before_assembly(monkeypatch):
    import scripts.lp_funnel_vet_v1_readonly as funnel

    class ReadOnlyPool:
        def __init__(self):
            self.calls = []

        def call(self, method, params, timeout=20):
            assert method == "eth_call"
            selector = params[0]["data"]
            self.calls.append(selector)
            value = 2**96 if selector == "0x3850c7bd" else 10**24
            return "0x" + f"{value:064x}"

        def health_snapshot(self):
            return {"state": "NORMAL"}

    monkeypatch.setattr(
        funnel,
        "funnel_vet",
        lambda bridge, stability, **kwargs: [dict(bridge[0], vetted=True)],
    )
    rpc_pool = ReadOnlyPool()
    stages = DefaultStages(rpc_pool=rpc_pool)
    resolved = [{
        "pool": "0x1111111111111111111111111111111111111111",
        "chain": "Base",
        "project": "uniswap-v3",
        "tier": "A",
        "fee_tier": 0.0001,
    }]
    stability = [{
        "pool": resolved[0]["pool"],
        "windows": [{"sigma_daily": 0.02, "er": 0.3}],
    }]
    carried = stages.funnel(resolved, stability)[0]
    assert carried["holding_horizon_days"] == 14
    assert carried["sigma_pair"] == 0.02
    assert carried["holding_horizon_source"] == "ER_policy"
    assert carried["high_drag_flag"] is False

    enriched = stages._attach_live_pool_state(carried)
    assert enriched["sqrt_price_x96"] == 2**96
    assert enriched["l_active_raw"] == 10**24
    assert enriched["sqrt_price_x96_source"].startswith("measured:")

    already_measured = stages._attach_live_pool_state({
        "pool": resolved[0]["pool"],
        "last_swap_price_token1_per_token0": 1.5,
        "last_swap_liquidity_raw": 999,
        "last_swap_cost_state_source": "measured:latest_decoded_swap_event",
    })
    assert already_measured["last_swap_liquidity_raw"] == 999
    assert rpc_pool.calls == ["0x3850c7bd", "0x1a686502"]


def test_add1_funnel_er_missing_clears_all_candidate_prefilled_horizon_and_drag(monkeypatch):
    import scripts.lp_funnel_vet_v1_readonly as funnel

    malicious = {
        "pool": "0x1111111111111111111111111111111111111111",
        "chain": "Base",
        "project": "uniswap-v3",
        "profile": "PASSIVE_CL",
        "holding_horizon_hours": 720.0,
        "holding_horizon_days": 30.0,
        "holding_horizon_source": "drag_adjusted(from=168)",
        "profile_horizon_hours": 720.0,
        "profile_horizon_days": 30.0,
        "er_horizon_hours": 720.0,
        "er_horizon_days": 30.0,
        "drag_apr_pct": 0.0,
        "drag_apr_max_pct": 15.0,
        "high_drag_flag": False,
    }
    monkeypatch.setattr(
        funnel,
        "funnel_vet",
        lambda bridge, stability, **kwargs: [dict(malicious, vetted=True)],
    )

    carried = DefaultStages().funnel([malicious], stability=[])[0]

    for key in (
        "holding_horizon_hours", "holding_horizon_days", "holding_horizon_source",
        "profile_horizon_hours", "profile_horizon_days", "er_horizon_hours",
        "er_horizon_days", "drag_apr_pct", "drag_apr_max_pct", "high_drag_flag",
    ):
        assert carried.get(key) is None


def test_add1_scanner_moves_to_smallest_legal_h_for_fixed_drag(monkeypatch):
    import scripts.lp_funnel_vet_v1_readonly as funnel

    monkeypatch.setattr(
        funnel,
        "funnel_vet",
        lambda bridge, stability, **kwargs: [dict(bridge[0], vetted=True)],
    )
    resolved = [{
        "pool": "0x1111111111111111111111111111111111111111",
        "chain": "Base",
        "project": "uniswap-v3",
        "tier": "A",
        "fee_tier": 0.003,
    }]
    stability = [{
        "pool": resolved[0]["pool"],
        "windows": [{"sigma_daily": 0.02, "er": 0.3}],
    }]

    carried = DefaultStages().funnel(resolved, stability)[0]

    assert carried["holding_horizon_er_policy_hours"] == 336.0
    assert carried["holding_horizon_hours"] == 720.0
    assert carried["holding_horizon_days"] == 30.0
    assert carried["holding_horizon_source"] == "drag_adjusted(from=336)"
    assert carried["drag_apr_pct"] <= 15.0
    assert carried["high_drag_flag"] is False


@pytest.mark.parametrize(
    ("er", "expected_hours"),
    [
        (0.10, 6.0),   # range-bound
        (0.35, 24.0),  # neutral
        (0.80, 72.0),  # trending
    ],
)
def test_r6_tactical_er_regime_selects_profile_legal_horizon(
    monkeypatch, er, expected_hours
):
    import scripts.lp_funnel_vet_v1_readonly as funnel

    monkeypatch.setattr(
        funnel,
        "funnel_vet",
        lambda bridge, stability, **kwargs: [dict(bridge[0], vetted=True)],
    )
    resolved = [{
        "pool": "0x1111111111111111111111111111111111111111",
        "chain": "Unknown",  # no gas evidence: preserve the measured-ER candidate
        "project": "uniswap-v3",
        "profile": "TACTICAL",
        "tier": "A",
        "fee_tier": 0.0001,
        # A candidate-prefilled PASSIVE H must never cross the profile boundary.
        "holding_horizon_hours": 168.0,
        "holding_horizon_source": "candidate_prefill",
    }]
    stability = [{
        "pool": resolved[0]["pool"],
        "windows": [{"sigma_daily": 0.02, "er": er}],
    }]

    carried = DefaultStages().funnel(resolved, stability)[0]

    assert carried["holding_horizon_er_policy_hours"] == expected_hours
    assert carried["holding_horizon_hours"] == expected_hours
    assert carried["holding_horizon_source"] == "ER_policy"
    assert carried["holding_horizon_hours"] in {6.0, 12.0, 24.0, 72.0}


def test_r6_tactical_drag_moves_only_upward_through_profile_legal_set(monkeypatch):
    import scripts.lp_funnel_vet_v1_readonly as funnel
    import scripts.lp_netcover_inputs_v1_readonly as inputs

    monkeypatch.setattr(
        funnel,
        "funnel_vet",
        lambda bridge, stability, **kwargs: [dict(bridge[0], vetted=True)],
    )
    # At M1_MIN_POSITION_USD this measured gas makes 6h exceed the drag model
    # while 12h is the first legal tactical horizon at/below it.
    monkeypatch.setitem(inputs.HISTORICAL_GAS_USD, "base", 0.0075)
    resolved = [{
        "pool": "0x1111111111111111111111111111111111111111",
        "chain": "Base",
        "project": "uniswap-v3",
        "profile": "TACTICAL",
        "tier": "A",
        "fee_tier": 0.0,
    }]
    stability = [{
        "pool": resolved[0]["pool"],
        "windows": [{"sigma_daily": 0.02, "er": 0.10}],
    }]

    carried = DefaultStages().funnel(resolved, stability)[0]

    assert carried["holding_horizon_er_policy_hours"] == 6.0
    assert carried["holding_horizon_hours"] == 12.0
    assert carried["holding_horizon_source"] == "drag_adjusted(from=6)"
    assert carried["holding_horizon_hours"] in {6.0, 12.0, 24.0, 72.0}
    assert carried["drag_apr_pct"] <= carried["drag_apr_max_pct"]
    assert carried["high_drag_flag"] is False


def test_r6_unknown_profile_with_measured_er_drops_prefilled_horizon(monkeypatch):
    import scripts.lp_funnel_vet_v1_readonly as funnel

    monkeypatch.setattr(
        funnel,
        "funnel_vet",
        lambda bridge, stability, **kwargs: [dict(bridge[0], vetted=True)],
    )
    resolved = [{
        "pool": "0x1111111111111111111111111111111111111111",
        "chain": "Base",
        "project": "unknown-project",
        "profile": "UNKNOWN",
        "fee_tier": 0.0001,
        "holding_horizon_hours": 168.0,
        "holding_horizon_source": "candidate_prefill",
        "drag_apr_pct": 0.0,
    }]
    stability = [{
        "pool": resolved[0]["pool"],
        "windows": [{"sigma_daily": 0.02, "er": 0.10}],
    }]

    carried = DefaultStages().funnel(resolved, stability)[0]

    assert carried["sigma_pair"] == 0.02
    assert carried["er"] == 0.10
    for key in (
        "holding_horizon_er_policy_hours",
        "holding_horizon_hours",
        "holding_horizon_days",
        "holding_horizon_source",
        "drag_apr_pct",
        "drag_apr_max_pct",
        "high_drag_flag",
    ):
        assert key not in carried


def test_default_live_stages_inject_rotating_rpc_pool_into_calls_and_logs(monkeypatch):
    import scripts.lp_multiwindow_stability_v1_readonly as stability
    import scripts.lp_pool_resolve_and_rank_v1_readonly as bridge
    import scripts.lp_rpc_pool_v1_readonly as rpc_module

    calls = []

    class FakeRpcPool:
        def __init__(self, chain):
            assert chain == "base"

        def call(self, method, params, timeout=20):
            calls.append((method, params, timeout))
            return "0x64" if method == "eth_blockNumber" else []

    def raw_fetch(pool, lo, hi, dec0, dec1, rpc_call=None):
        assert rpc_call is not None
        rpc_call("eth_getLogs", [{"address": pool}])
        return []

    live = {"_rpc_with_retry": lambda *_: pytest.fail("legacy RPC used"), "fetch_pool_swaps": raw_fetch}
    monkeypatch.setattr(rpc_module, "RpcPool", FakeRpcPool)
    monkeypatch.setattr(bridge, "_load_live_helpers", lambda: dict(live))
    monkeypatch.setattr(bridge, "_eth_block_number", lambda rpc: int(rpc("eth_blockNumber", []), 16))

    def process(candidate, window_blocks, current_block, caches, injected):
        assert current_block == 100
        injected["fetch_pool_swaps"]("0x1", 1, 2, 18, 6)
        return dict(candidate, status="OK")

    monkeypatch.setattr(bridge, "process_candidate", process)
    monkeypatch.setattr(stability, "_live", lambda: dict(live))
    monkeypatch.setattr(
        stability,
        "assess_pool",
        lambda injected, cfg, *_: (
            injected["fetch_pool_swaps"]("0x1", 1, 2, 18, 6) or {"pool": cfg["pool"]}
        ),
    )
    monkeypatch.setattr(
        bridge,
        "build_policy_config",
        lambda records: [{"pool": "0x1", "dec0": 18, "dec1": 6, "fee_tier": 0.0005}],
    )

    stages = DefaultStages(chain="Base")
    assert stages.resolve([{"pool": "0x1"}])[0]["status"] == "OK"
    assert stages.multiwindow([{"pool": "0x1"}]) == [{"pool": "0x1"}]
    assert [method for method, _, _ in calls] == [
        "eth_blockNumber",
        "eth_getLogs",
        "eth_blockNumber",
        "eth_getLogs",
    ]


def test_default_stages_reuses_one_rpc_pool_and_exports_real_health_snapshot():
    class PersistentPool:
        def __init__(self):
            self.state = "NORMAL"

        def call(self, method, params, timeout=20):
            return "0x64" if method == "eth_blockNumber" else []

        def health_snapshot(self):
            return {"state": self.state, "impaired_endpoints": int(self.state != "NORMAL")}

    pool = PersistentPool()
    stages = DefaultStages(chain="Base", rpc_pool=pool)
    raw = lambda *args, **kwargs: []

    first = stages._live_with_rotating_rpc({"fetch_pool_swaps": raw})
    second = stages._live_with_rotating_rpc({"fetch_pool_swaps": raw})

    assert first["_rpc_with_retry"].__self__ is pool
    assert second["_rpc_with_retry"].__self__ is pool
    assert stages.rpc_health == "NORMAL"
    pool.state = "DEGRADED"
    assert stages.rpc_health == "DEGRADED"


def test_real_pool_degradation_and_recovery_flow_through_daemon_alert_hook():
    from scripts.lp_rpc_pool_v1_readonly import CHAINS, RpcPool

    class Clock:
        def now(self):
            return 1000.0

        def sleep(self, secs):
            pass

    class RecordingAlerter:
        def __init__(self):
            self.events = []

        def send_event(self, event_type, message, **kwargs):
            self.events.append(event_type)

    pool = RpcPool("base", post=lambda *a, **k: {"result": "0x1"}, clock=Clock())
    impaired = CHAINS["base"]["endpoints"][0]["url"]
    stages = DefaultStages(chain="Base", rpc_pool=pool)
    alerter = RecordingAlerter()
    hook = ScannerAlertBridge(alerter, utc_now=lambda: AS_OF)

    def cycle(refresh_coarse):
        return CycleResult(AS_OF.isoformat(), 0, 0, 0, 0, 0, 0, stages.rpc_health)

    daemon = ScannerDaemon(cycle, event_hook=hook)
    pool._penalize(impaired)
    assert daemon.run(once=True) == 0
    pool._reset(impaired)
    assert daemon.run(once=True) == 0

    assert alerter.events == ["rpc_degraded", "rpc_normal"]


def test_all_endpoint_cycle_failure_alerts_exit_only_then_success_recovers_normal():
    from scripts.lp_rpc_pool_v1_readonly import CHAINS, RpcPool

    class Clock:
        def now(self):
            return 1000.0

        def sleep(self, secs):
            pass

    class RecordingAlerter:
        def __init__(self):
            self.events = []

        def send_event(self, event_type, message, **kwargs):
            self.events.append(event_type)

    failing = [True]

    def post(url, method, params, timeout=20):
        if failing[0]:
            raise OSError("public endpoint unavailable")
        return {"result": "0x1"}

    pool = RpcPool("base", post=post, clock=Clock())
    stages = DefaultStages(chain="Base", rpc_pool=pool)
    alerter = RecordingAlerter()
    hook = ScannerAlertBridge(alerter, utc_now=lambda: AS_OF)

    def cycle(refresh_coarse):
        pool.call("eth_blockNumber", [])
        return CycleResult(AS_OF.isoformat(), 0, 0, 0, 0, 0, 0, stages.rpc_health)

    daemon = ScannerDaemon(cycle, event_hook=hook)
    with pytest.raises(RuntimeError, match="failed on all"):
        daemon.run(once=True)

    failing[0] = False
    for endpoint in CHAINS["base"]["endpoints"]:
        pool._reset(endpoint["url"])
    assert daemon.run(once=True) == 0

    assert alerter.events == ["rpc_exit_only", "rpc_normal"]


def test_non_rpc_cycle_error_never_masquerades_as_exit_only():
    class RecordingAlerter:
        def __init__(self):
            self.events = []

        def send_event(self, event_type, message, **kwargs):
            self.events.append(event_type)

    alerter = RecordingAlerter()
    hook = ScannerAlertBridge(alerter, utc_now=lambda: AS_OF)

    def invalid_market_session(refresh_coarse):
        raise ValueError("invalid market_session")

    daemon = ScannerDaemon(invalid_market_session, event_hook=hook)

    with pytest.raises(ValueError, match="market_session"):
        daemon.run(once=True)

    assert alerter.events == ["scanner_cycle_error"]
    assert "rpc_exit_only" not in alerter.events


def test_store_rolls_back_the_whole_cycle_on_invalid_market_session(tmp_path):
    stages = FakeStages()
    original = stages.screen

    def bad_screen():
        batch = original()
        batch.all_records[0]["market_session"] = "MADE_UP"
        return batch

    stages.screen = bad_screen
    db = tmp_path / "scanner.db"

    with pytest.raises(ValueError, match="market_session"):
        FunnelOrchestrator(stages, ScannerStore(db)).run_once(refresh_coarse=True, as_of=AS_OF)

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM pool_snapshots").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM opportunity_scores").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM market_sessions").fetchone()[0] == 0


def test_sigterm_causes_graceful_shutdown_after_cycle(tmp_path):
    started = tmp_path / "started"
    stopped = tmp_path / "stopped"
    code = "\n".join(
        [
            "from pathlib import Path",
            "from scripts.lp_scanner_daemon_v1_readonly import ScannerDaemon",
            f"started = Path({str(started)!r})",
            f"stopped = Path({str(stopped)!r})",
            "def cycle(refresh_coarse):",
            "    started.write_text('started')",
            "daemon = ScannerDaemon(cycle, coarse_interval_secs=900, top_interval_secs=60,",
            "                       on_shutdown=lambda: stopped.write_text('flushed'))",
            "raise SystemExit(daemon.run())",
        ]
    )
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=Path(__file__).parents[1])
    deadline = time.time() + 10
    while time.time() < deadline and not started.exists():
        time.sleep(0.02)
    assert started.exists(), "daemon never completed its initial cycle"

    os.kill(proc.pid, signal.SIGTERM)
    assert proc.wait(timeout=10) == 0
    assert stopped.read_text() == "flushed"


def test_systemd_template_is_shadow_only_credential_free_and_preflighted():
    root = Path(__file__).parents[1]
    text = (root / "deploy/systemd/lpbot-scanner-shadow.service").read_text()
    lowered = text.lower()

    assert "lp_scanner_daemon_v1_readonly.py" in text
    assert "--db" in text
    assert "ExecStartPre=" in text
    assert "/opt/lpbot/lp-bot-v3-origin-check" in text
    assert "EnvironmentFile=" not in text
    assert "token" not in lowered
    assert "wallet" not in lowered
    assert "private_key" not in lowered
    assert "WantedBy=multi-user.target" in text
