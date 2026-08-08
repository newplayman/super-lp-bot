"""Seven-scenario PRD v2.1 section 12.2 defensive-exit replay."""

import json

from scripts.lp_defensive_exit_replay_v1_readonly import (
    SCENARIO_NAMES,
    run_scenarios,
    write_report,
)


def test_replay_runs_exactly_seven_machine_asserted_paper_scenarios():
    results = run_scenarios()
    assert tuple(result["scenario"] for result in results) == SCENARIO_NAMES
    assert len(results) == 7
    assert all(result["passed"] for result in results)
    assert all(result["paper_only"] for result in results)
    assert all(result["assertions"] and all(result["assertions"].values()) for result in results)


def test_lower_eighty_percent_risky_remove_only_is_not_risk_off_complete():
    result = {row["scenario"]: row for row in run_scenarios()}["lower_breach_80pct_risky"]
    assert result["observed"]["post_trade_risky_inventory_ratio"] >= 0.80
    assert result["observed"]["risk_off_complete"] is False
    assert result["observed"]["next_state"] == "EXITING"


def test_remove_only_and_remove_to_stable_are_distinct():
    rows = {row["scenario"]: row for row in run_scenarios()}
    remove_only = rows["remove_only"]
    assert remove_only["observed"]["mode"] == "REMOVE_ONLY"
    assert remove_only["observed"]["swap_requested"] is False
    to_stable = rows["remove_to_stable"]
    assert to_stable["observed"]["mode"] == "REMOVE_TO_STABLE"
    assert to_stable["observed"]["quote_required"] is True
    assert to_stable["observed"]["swap_allowed"] is True


def test_quote_and_slippage_failures_are_staged_and_alerted():
    rows = {row["scenario"]: row for row in run_scenarios()}
    for name, reason in (("quote_failure", "quote_failed"), ("slippage_limit", "slippage_limit")):
        observed = rows[name]["observed"]
        assert observed["swap_allowed"] is False
        assert observed["substate"] == "staged/limit_exit"
        assert observed["alert"] is True
        assert observed["block_reason"] == reason


def test_rpc_degraded_and_exit_only_allowlists_are_machine_asserted():
    rows = {row["scenario"]: row for row in run_scenarios()}
    degraded = rows["rpc_degraded"]["observed"]
    assert degraded["open_allowed"] is False
    assert degraded["add_allowed"] is False
    assert degraded["monitor_allowed"] is True
    assert degraded["remove_allowed"] is True
    exit_only = rows["rpc_exit_only"]["observed"]
    assert exit_only["remove_allowed"] is True
    assert exit_only["collect_allowed"] is True
    assert exit_only["swap_to_usdc_allowed"] is True
    assert exit_only["add_allowed"] is False
    assert exit_only["rebalance_allowed"] is False
    assert exit_only["approve_allowed"] is False


def test_report_contains_machine_json_and_human_summary(tmp_path):
    report_dir = write_report(out_root=tmp_path, stamp="20260808_120000")
    payload = json.loads((report_dir / "results.json").read_text())
    summary = (report_dir / "SUMMARY.md").read_text()
    assert payload["schema_version"] == "lp_defensive_exit_replay_v1"
    assert payload["paper_only"] is True
    assert payload["passed"] is True
    assert payload["passed_scenarios"] == 7
    assert payload["total_scenarios"] == 7
    assert "7/7 PASS" in summary
    assert "no signing, approval, or broadcast" in summary
