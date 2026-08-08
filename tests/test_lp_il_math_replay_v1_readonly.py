"""Independent math replay and report contracts for WP-02."""

import json
from pathlib import Path

from scripts.lp_il_math_replay_v1_readonly import (
    DEFAULT_REAL_SWAP_SOURCE,
    SCENARIO_TYPES,
    build_trajectories,
    load_real_swap_prices,
    run_replay,
)


def test_tracked_real_swap_artifact_decodes_to_prices_without_network():
    source = Path(DEFAULT_REAL_SWAP_SOURCE)
    assert source.is_file()
    prices = load_real_swap_prices(source, limit=64)
    assert len(prices) == 64
    assert all(p > 0 for p in prices)
    assert len(set(prices)) > 1


def test_trajectory_suite_has_real_provenance_and_six_required_shapes():
    trajectories = build_trajectories(load_real_swap_prices(DEFAULT_REAL_SWAP_SOURCE, limit=128))
    assert len(trajectories) >= 50
    assert set(t.scenario_type for t in trajectories) == set(SCENARIO_TYPES)
    assert any(t.provenance == "real_historical_swap" for t in trajectories)
    assert any(t.provenance == "synthetic" for t in trajectories)


def test_replay_writes_machine_readable_details_and_hard_threshold_summary(tmp_path):
    result = run_replay(
        real_source=DEFAULT_REAL_SWAP_SOURCE,
        output_root=tmp_path,
        clock=lambda: "20260808_123456",
    )
    run_dir = tmp_path / "20260808_123456"
    summary = json.loads((run_dir / "summary.json").read_text())
    details = [json.loads(line) for line in (run_dir / "details.jsonl").read_text().splitlines()]
    assert result == summary
    assert summary["status"] == "PASS"
    assert summary["trajectory_count"] >= 50
    assert summary["real_trajectory_count"] > 0
    assert summary["synthetic_trajectory_count"] > 0
    assert set(summary["scenario_distribution"]) == set(SCENARIO_TYPES)
    assert summary["max_inventory_error_pct"] <= 0.1
    assert summary["max_il_error_bps_of_nav"] <= 5.0
    assert summary["real_source"] == str(Path(DEFAULT_REAL_SWAP_SOURCE))
    assert len(details) == summary["trajectory_count"]
    assert all(row["passed"] for row in details)
