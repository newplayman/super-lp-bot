from __future__ import annotations

import json
import sys

sys.path.insert(0, "/opt/lpbot/lp-bot-v3-origin-check")

import pytest

from scripts.lp_rh_funnel_autopsy_v1_readonly import (
    STATUS_ORDER,
    autopsy,
    main,
    mutation_harness,
    producer_map_check,
    zero_candidate_explanation,
)
from scripts.lp_rh_terminal_gate_v1_readonly import CONJUNCT_ORDER


NOW = "2026-09-08T00:00:00Z"


def _record(name="pool", **updates):
    record = {
        "candidate_key": name,
        "legacy_required_conjunction": True,
        "identity_verified": True,
        "protocol_capabilities_sufficient": True,
        "data_complete_and_fresh": True,
        "profile_policy_pass": True,
        "market_and_chain_risk_pass": True,
        "netcover_pass": True,
        "absolute_profit_pass": True,
        "position_and_exit_depth_pass": True,
        "capital_policy_pass": True,
        "missing_inputs": [],
        "fee_ev_usd": 1.0,
        "reward_ev_usd": 1.0,
        "il_ev_usd": 1.0,
        "entry_cost_usd": 1.0,
        "exit_cost_usd": 1.0,
        "gas_usd": 1.0,
        "slippage_usd": 1.0,
        "reward_conversion_cost_usd": 1.0,
        "exit_latency_loss_usd": 1.0,
    }
    record.update(updates)
    return record


def _summary_for_statuses(records):
    return autopsy(records, target_mode="LIVE_READINESS", now=NOW)


def test_status_order_contains_the_five_primary_states():
    assert set(STATUS_ORDER) == {
        "COMPUTED_PASS", "COMPUTED_FAIL", "INPUTS_UNAVAILABLE",
        "UNSUPPORTED", "POLICY_BLOCKED",
    }


def test_autopsy_counts_total_and_statuses():
    records = [
        _record("pass"),
        _record("fail", netcover_pass=False, netcover=0.5),
        _record("missing", legacy_required_conjunction=None),
    ]
    summary = _summary_for_statuses(records)
    assert summary["total"] == 3
    assert summary["by_primary_status"]["COMPUTED_PASS"] == 1
    assert summary["by_primary_status"]["COMPUTED_FAIL"] == 1
    assert summary["by_primary_status"]["INPUTS_UNAVAILABLE"] == 1


def test_autopsy_counts_dominant_blocker_in_priority_order():
    summary = _summary_for_statuses([_record("x", identity_verified=False)])
    assert summary["by_dominant_blocker"]["identity_verified"] == 1
    assert summary["by_dominant_blocker"]["legacy_required_conjunction"] == 0


def test_decay_is_monotonic_and_ends_at_computed_pass_count():
    records = [
        _record("pass"),
        _record("legacy", legacy_required_conjunction=False),
        _record("identity", identity_verified=False),
        _record("risk", market_and_chain_risk_pass=False),
        _record("capital", capital_policy_pass=False),
    ]
    summary = _summary_for_statuses(records)
    survivors = [row["survivors"] for row in summary["decay"]]
    assert survivors == sorted(survivors, reverse=True)
    assert survivors[-1] == summary["by_primary_status"]["COMPUTED_PASS"]


def test_decay_keeps_gate_order():
    summary = _summary_for_statuses([_record()])
    assert [row["gate"] for row in summary["decay"]] == list(CONJUNCT_ORDER)


def test_closest_to_pass_only_contains_exactly_one_missing_gate():
    records = [
        _record("one", netcover_pass=False),
        _record("two", netcover_pass=False, identity_verified=False),
        _record("three"),
    ]
    closest = _summary_for_statuses(records)["closest_to_pass"]
    assert [row["candidate_key"] for row in closest] == ["one"]
    assert closest[0]["missing_gate"] == "netcover_pass"


def test_closest_to_pass_is_limited_to_three():
    records = [_record(str(index), netcover_pass=False) for index in range(5)]
    assert len(_summary_for_statuses(records)["closest_to_pass"]) == 3


def test_zero_candidate_explanation_has_all_four_categories():
    records = [
        _record("fail", netcover_pass=False, netcover=0.1),
        _record("missing", legacy_required_conjunction=None),
        _record("unsupported", protocol_capabilities_sufficient=False),
        _record("policy", capital_policy_pass=False),
    ]
    summary = _summary_for_statuses(records)
    explanation = zero_candidate_explanation(summary)
    assert "已完成经济评估且不合格: 1" in explanation
    assert "尚未能评估: 1" in explanation
    assert "不支持: 1" in explanation
    assert "政策阻挡: 1" in explanation


def test_zero_candidate_explanation_avoids_forbidden_conclusion_words():
    summary = _summary_for_statuses([_record("fail", netcover_pass=False, netcover=0.1)])
    explanation = zero_candidate_explanation(summary).lower()
    assert "无机会" not in explanation
    assert "no opportunity" not in explanation


def test_zero_candidate_explanation_reports_pass_count_too():
    explanation = zero_candidate_explanation(_summary_for_statuses([_record()]))
    assert "COMPUTED_PASS: 1" in explanation


def test_mutation_harness_detects_single_gate_witnesses():
    records = [_record(gate, **{gate: False}) for gate in CONJUNCT_ORDER]
    result = mutation_harness(records, target_mode="LIVE_READINESS", now=NOW)
    assert any(detail["false_admits"] > 0 for detail in result.values())
    for detail in result.values():
        assert detail["witness_detected"] is (detail["false_admits"] > 0)


def test_mutation_harness_reports_every_gate():
    result = mutation_harness([_record("bad", netcover_pass=False, netcover=0.5)],
                              target_mode="LIVE_READINESS", now=NOW)
    assert list(result) == list(CONJUNCT_ORDER)


def test_mutation_harness_zero_witness_is_explicitly_false():
    record = _record("bad", identity_verified=False, netcover_pass=False, netcover=0.5)
    result = mutation_harness([record], target_mode="LIVE_READINESS", now=NOW)
    assert result["identity_verified"]["false_admits"] == 0
    assert result["identity_verified"]["witness_detected"] is False


def test_producer_map_marks_all_missing_as_no_producer():
    records = [{"candidate_key": "a"}, {"candidate_key": "b", "present": 1}]
    result = producer_map_check(records, ["legacy_required_conjunction", "present"])
    assert result["legacy_required_conjunction"] == {"missing": 2, "verdict": "NO_PRODUCER"}
    assert result["present"] == {"missing": 1, "verdict": "OK"}


def test_producer_map_treats_none_as_missing():
    result = producer_map_check([{"field": None}, {"field": True}], ["field"])
    assert result["field"]["missing"] == 1
    assert result["field"]["verdict"] == "OK"


def test_no_producer_is_input_unavailable_not_computed_fail():
    records = [_record("a", legacy_required_conjunction=None),
               _record("b", legacy_required_conjunction=None)]
    summary = _summary_for_statuses(records)
    assert summary["by_primary_status"]["INPUTS_UNAVAILABLE"] == 2
    assert summary["by_primary_status"]["COMPUTED_FAIL"] == 0


def test_shadow_mode_does_not_apply_live_capital_conflict():
    record = _record(capital_policy_conflict={"conflict": True})
    summary = autopsy([record], target_mode="SHADOW_SCENARIO", now=NOW)
    assert summary["by_primary_status"]["COMPUTED_PASS"] == 1


def test_invalid_target_mode_is_rejected():
    with pytest.raises(ValueError, match="UNKNOWN_TARGET_MODE"):
        autopsy([_record()], target_mode="BOGUS", now=NOW)


def test_cli_reads_records_and_writes_summary(tmp_path):
    records_path = tmp_path / "records.json"
    output_path = tmp_path / "out.json"
    records_path.write_text(json.dumps({"records": [_record("cli")] }), encoding="utf-8")
    assert main(["--records-json", str(records_path), "--target-mode", "LIVE_READINESS",
                 "--out", str(output_path)]) == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 1
    assert "mutation" in payload
