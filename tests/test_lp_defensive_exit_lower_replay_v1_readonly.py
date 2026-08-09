"""C3 real-swap lower-breach replay acceptance tests."""

import json

from scripts.lp_defensive_exit_lower_replay_v1_readonly import (
    DEFAULT_SWAP_SOURCE,
    run_replay,
    write_report,
)


def test_c3_uses_three_real_streams_and_includes_gap_through():
    payload = run_replay()
    assert payload["source"]["real_historical_swap_rows"] == 3000
    assert payload["scenario_count"] == 3
    assert payload["gap_through_count"] >= 1
    assert payload["passed"] is True
    assert DEFAULT_SWAP_SOURCE.is_file()


def test_c3_lower_breaches_record_five_fields_and_remove_to_stable():
    for row in run_replay()["results"]:
        assert row["breach"]["breach_price"] < row["breach"]["lower_bound"]
        assert row["five_mandatory_fields"].keys() == {
            "breach_direction",
            "post_remove_inventory_ratio",
            "post_remove_delta_usd",
            "recommended_exit_mode",
            "expected_swap_cost",
        }
        assert row["five_mandatory_fields"]["breach_direction"] == "LOWER"
        assert row["five_mandatory_fields"]["post_remove_inventory_ratio"] >= 0.80
        assert row["five_mandatory_fields"]["recommended_exit_mode"] == "REMOVE_TO_STABLE"


def test_c3_success_and_unacceptable_quote_paths_enforce_inventory_invariants():
    rows = run_replay()["results"]
    successful = [row for row in rows if row["paper_plan"]["swap_allowed"]]
    staged = [row for row in rows if not row["paper_plan"]["swap_allowed"]]
    assert len(successful) == 2
    assert len(staged) == 1
    for row in successful:
        plan = row["paper_plan"]
        assert plan["paper_actions"] == ("simulate_remove", "simulate_swap_to_stable")
        assert plan["post_trade_risky_inventory_ratio"] <= 0.25
        assert plan["risk_off_complete"] is True
    plan = staged[0]["paper_plan"]
    assert plan["quote_succeeded"] is True
    assert plan["expected_slippage_bps"] > 75.0
    assert plan["swap_allowed"] is False
    assert plan["substate"] == "staged/limit_exit"
    assert plan["alert"] is True
    assert plan["block_reason"] == "slippage_limit"
    assert plan["risk_off_complete"] is False


def test_c3_cost_comparison_is_real_and_deviation_is_not_hidden():
    deviations = []
    for row in run_replay()["results"]:
        cost = row["cost_comparison"]
        assert cost["actual_notional_usd"] >= 100.0
        assert cost["replay_actual_cost_usd"] > 0.0
        assert cost["model_cost_usd"] > 0.0
        deviations.append(cost["absolute_deviation_pct"])
    assert max(deviations) > 20.0


def test_c3_report_is_reproducible_and_paper_only(tmp_path):
    out = tmp_path / "report"
    write_report(out)
    payload = json.loads((out / "results.json").read_text())
    summary = (out / "SUMMARY.md").read_text()
    assert payload["passed"] is True
    assert payload["safety"] == {
        "broadcast": False,
        "signing": False,
        "threshold_changes": False,
        "wallet": False,
    }
    assert "3 lower breaches" in summary
    assert "calibration warning" in summary
