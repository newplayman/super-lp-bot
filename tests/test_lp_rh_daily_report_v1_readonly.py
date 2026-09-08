#!/usr/bin/env python3
"""Tests for the RH daily decision report generator (offline/read-only)."""
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_daily_report_v1_readonly import (  # noqa: E402
    SEVEN_SECTIONS,
    answer_six_questions,
    assert_not_bare_accepted_zero,
    build_report,
    evidence_freshness_table,
    forbid_paper_pnl,
    main,
)


def valid_state():
    return {
        "run_id": "rh-2026-09-08",
        "as_of": "2026-09-08T00:00:00Z",
        "autopsy_summary": {
            "closest_to_pass": [
                {"candidate_key": "pool_a", "missing_gate": "netcover_pass"},
            ],
            "by_primary_status": {
                "COMPUTED_PASS": 0,
                "COMPUTED_FAIL": 3,
                "INPUTS_UNAVAILABLE": 1,
                "UNSUPPORTED": 2,
                "POLICY_BLOCKED": 1,
            },
        },
        "coverage": {
            "COMPUTED_PASS": 0,
            "COMPUTED_FAIL": 3,
            "INPUTS_UNAVAILABLE": 1,
            "UNSUPPORTED": 2,
            "POLICY_BLOCKED": 1,
        },
        "capital_policy": {"lp_deploy_u": 100, "wallet_risk_u": 50},
        "cost_breakdown": {"dominant_cost": "rebalance", "ev_hold": 0.1},
        "infra_gaps": ["no exit simulator"],
        "evidence_freshness": [
            {
                "source": "scanner",
                "fetched_at": "2026-09-08T00:00:00Z",
                "source_event_time": "2026-09-08T00:00:00Z",
                "age_secs": 0,
                "quality": "ok",
            },
        ],
    }


@pytest.mark.parametrize(
    "name,mutate",
    [
        ("证据日期与完整性", lambda s: s.update(evidence_freshness=[])),
        ("已算与未算", lambda s: s.update(coverage={})),
        ("最接近通过的三个候选", lambda s: s["autopsy_summary"].pop("closest_to_pass")),
        ("100U 政策下可行性", lambda s: s.update(capital_policy={})),
        ("全部费用与风险成本", lambda s: s.update(cost_breakdown=None)),
        ("无交易是否合理", lambda s: s["autopsy_summary"].pop("by_primary_status")),
        ("基础设施缺口", lambda s: s.update(infra_gaps=None)),
    ],
)
def test_missing_section_raises(name, mutate):
    state = valid_state()
    mutate(state)
    with pytest.raises(ValueError) as exc:
        build_report(**state)
    assert f"MISSING_SECTION:{name}" in str(exc.value)


def test_bare_accepted_zero_raises():
    with pytest.raises(ValueError) as exc:
        assert_not_bare_accepted_zero("accepted=0, tests green",
                                      {"by_primary_status": {"COMPUTED_PASS": 0}})
    assert "BARE_ACCEPTED_ZERO" in str(exc.value)


def test_bare_accepted_zero_passes_with_split():
    report = "COMPUTED_FAIL: 3 INPUTS_UNAVAILABLE: 1 UNSUPPORTED: 2 POLICY_BLOCKED: 1"
    assert_not_bare_accepted_zero(report, {"by_primary_status": {"COMPUTED_PASS": 0}})


def test_real_report_passes_bare_zero_check():
    state = valid_state()
    report = build_report(**state)
    assert_not_bare_accepted_zero(report, state["autopsy_summary"])


def test_paper_pnl_raises():
    with pytest.raises(ValueError) as exc:
        forbid_paper_pnl("paper runner 净值 $1,769")
    assert "PAPER_PNL_CITED_FOR_RH" in str(exc.value)


def test_paper_pnl_passes_without_amount():
    forbid_paper_pnl("the paper runner is deprecated")


def test_six_questions_no_evidence_not_measured():
    answers = answer_six_questions({})
    assert len(answers) == 6
    for entry in answers.values():
        assert "NOT_MEASURED" in entry["answer"]
        assert not re.search(r"\d", entry["answer"])


def test_six_questions_with_evidence():
    answers = answer_six_questions({"q1_mode": "SHADOW_SCENARIO only"})
    assert answers["q1_mode"]["answer"] == "SHADOW_SCENARIO only"
    assert "NOT_MEASURED" in answers["q2_budgets"]["answer"]


def test_freshness_table_server_time_unknown():
    table = evidence_freshness_table([
        {"source": "scanner", "fetched_at": "2026-09-08T00:00:00Z",
         "source_event_time": None, "age_secs": 0, "quality": "ok"},
    ])
    assert "SERVER_TIME_UNKNOWN" in table


def test_freshness_table_with_event_time():
    table = evidence_freshness_table([
        {"source": "scanner", "fetched_at": "2026-09-08T00:00:00Z",
         "source_event_time": "2026-09-08T00:00:00Z", "age_secs": 0, "quality": "ok"},
    ])
    assert "SERVER_TIME_UNKNOWN" not in table
    assert "2026-09-08T00:00:00Z" in table


def test_report_contains_all_seven_sections():
    report = build_report(**valid_state())
    assert report
    for name in SEVEN_SECTIONS:
        assert f"## {name}" in report


def test_main_writes_report(tmp_path):
    state_json = tmp_path / "state.json"
    state_json.write_text(json.dumps(valid_state()), encoding="utf-8")
    out = tmp_path / "DAILY_DECISION.md"
    main(["--state-json", str(state_json), "--out", str(out)])
    text = out.read_text(encoding="utf-8")
    for name in SEVEN_SECTIONS:
        assert f"## {name}" in text
