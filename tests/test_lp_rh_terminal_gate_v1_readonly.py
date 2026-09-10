"""Contracts for the RH terminal gate (ten-way conjunction + mutation witness).

Mirrors the INV-GATE-02 paradigm: an AST source-shape assertion pins exactly
which names participate in the terminal ``and``; a per-gate rejection sweep
proves each gate blocks; a mutation witness proves that restoring one false
bit to True (i.e. omitting a gate) makes the sweep fail.
"""
from __future__ import annotations

import ast
import inspect
import json
import textwrap
from pathlib import Path

import pytest

from scripts import lp_rh_terminal_gate_v1_readonly as tg

NOW = "2026-09-08T00:00:00Z"


def _bool_conjunct_names(source: str, *, assignment_target: str) -> frozenset[str]:
    """Return local names used by one terminal ``and`` assignment."""
    tree = ast.parse(textwrap.dedent(source))
    candidates: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == assignment_target
                for target in node.targets
            ):
                candidates.append(node.value)
    assert len(candidates) == 1, (
        f"expected one {assignment_target} assignment, found {len(candidates)}"
    )
    value = candidates[0]
    assert isinstance(value, ast.BoolOp) and isinstance(value.op, ast.And), (
        f"{assignment_target} must remain an explicit conjunction"
    )
    return frozenset(
        child.id for child in ast.walk(value) if isinstance(child, ast.Name)
    )


def _all_true_record(**updates):
    """A candidate that passes every gate and the economic classifier."""
    rec = {
        "candidate_key": "pool-test",
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
        "fee_ev_usd": 1.0, "reward_ev_usd": 1.0, "il_ev_usd": 1.0,
        "entry_cost_usd": 1.0, "exit_cost_usd": 1.0, "gas_usd": 1.0,
        "slippage_usd": 1.0, "reward_conversion_cost_usd": 1.0,
        "exit_latency_loss_usd": 1.0,
        "source_snapshot_ids": ["snap-test"],
    }
    rec.update(updates)
    return rec


def test_terminal_conjunction_source_shape_is_complete():
    """A removed or newly added conjunct forces an explicit invariant update."""
    assert _bool_conjunct_names(
        inspect.getsource(tg.evaluate_terminal_gate),
        assignment_target="terminal_eligible",
    ) == tg.TERMINAL_CONJUNCTS


@pytest.mark.parametrize("gate", tg.CONJUNCT_ORDER)
def test_rejects_each_false_gate(gate):
    rec = _all_true_record()
    rec[gate] = False
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.terminal_eligible is False
    assert d.dominant_blocker == gate


def _assert_all_false_gate_mutations_reject(decide):
    """Sweep: with each gate forced False, the decision must reject."""
    for gate in tg.CONJUNCT_ORDER:
        rec = _all_true_record()
        rec[gate] = False
        assert decide(rec) is False, f"omitted terminal gate: {gate}"


@pytest.mark.parametrize("omitted_gate", tg.CONJUNCT_ORDER)
def test_mutation_witness_detects_each_omitted_gate(omitted_gate):
    """A mutant that restores one false bit to True must fail the sweep."""
    def decide(rec):
        return tg.mutation_witness_removed_gate(
            rec, removed=omitted_gate, target_mode="LIVE_READINESS", now=NOW)
    with pytest.raises(AssertionError, match=f"omitted terminal gate: {omitted_gate}"):
        _assert_all_false_gate_mutations_reject(decide)


def test_t25_live_readiness_policy_conflict_blocks():
    rec = _all_true_record(capital_policy_conflict={"conflict": True, "code": "CAPITAL_POLICY_CONFLICT"})
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.terminal_eligible is False
    assert d.primary_status == "POLICY_BLOCKED"
    assert d.dominant_blocker == "capital_policy_pass"


def test_t25_shadow_scenario_policy_conflict_simulated():
    rec = _all_true_record(capital_policy_conflict={"conflict": True, "code": "CAPITAL_POLICY_CONFLICT"})
    d = tg.evaluate_terminal_gate(rec, target_mode="SHADOW_SCENARIO", now=NOW)
    assert d.terminal_eligible is True
    assert d.simulated_policy_only is True
    assert d.primary_status != "POLICY_BLOCKED"


def test_t25_modes_differ_on_conflict():
    rec = _all_true_record(capital_policy_conflict={"conflict": True})
    live = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    shadow = tg.evaluate_terminal_gate(rec, target_mode="SHADOW_SCENARIO", now=NOW)
    assert live.terminal_eligible is not shadow.terminal_eligible


def test_t59_missing_producer_not_computed_fail():
    rec = _all_true_record()
    del rec["legacy_required_conjunction"]
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.terminal_bits["legacy_required_conjunction"] is False
    assert "LEGACY_CONJUNCTION_NO_PRODUCER" in d.reasons
    assert d.terminal_eligible is False
    assert d.primary_status != "COMPUTED_FAIL"


def test_t60_all_true_eligible_no_blocker():
    rec = _all_true_record()
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.terminal_eligible is True
    assert d.dominant_blocker is None


def test_unknown_target_mode_raises():
    rec = _all_true_record()
    with pytest.raises(ValueError, match="UNKNOWN_TARGET_MODE"):
        tg.evaluate_terminal_gate(rec, target_mode="BOGUS", now=NOW)


def test_main_cli_synthetic_fixture(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "rh" / "synthetic" / "terminal_records.json"
    out = tmp_path / "out.json"
    rc = tg.main(["--record-json", str(fixture), "--target-mode", "LIVE_READINESS", "--out", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["count"] == 3


def test_status_policy_blocked_in_live():
    rec = _all_true_record(capital_policy_pass=False)
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.primary_status == "POLICY_BLOCKED"


def test_status_inputs_unavailable_when_no_producer():
    rec = _all_true_record()
    del rec["legacy_required_conjunction"]
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.primary_status == "INPUTS_UNAVAILABLE"


@pytest.mark.parametrize("gate", tg.CONJUNCT_ORDER)
def test_status_never_computed_pass_when_ineligible(gate):
    """Core regression: any single false gate must not read as COMPUTED_PASS."""
    rec = _all_true_record()
    rec[gate] = False
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.terminal_eligible is False
    assert d.primary_status != "COMPUTED_PASS"


def test_shadow_scenario_marks_simulated_only():
    rec = _all_true_record()
    shadow = tg.evaluate_terminal_gate(rec, target_mode="SHADOW_SCENARIO", now=NOW)
    live = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert shadow.simulated_policy_only is True
    assert live.simulated_policy_only is False


def test_same_record_differs_by_target_mode():
    rec = _all_true_record(capital_policy_conflict={"conflict": True})
    live = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    shadow = tg.evaluate_terminal_gate(rec, target_mode="SHADOW_SCENARIO", now=NOW)
    assert live.primary_status != shadow.primary_status


def test_decision_id_without_episode_is_byte_identical_to_legacy():
    """Regression guard: a record lacking ``strategy_episode`` must keep the
    exact legacy ``decision_id``.  Any drift here silently changes every
    existing ``rh_gate_decisions`` primary key and breaks the runner's
    duplicate-row detection (commit 330ab3e measured 199 dup rows on it)."""
    rec = _all_true_record()
    assert "strategy_episode" not in rec
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.decision_id == f"rh-terminal-{rec['candidate_key']}-LIVE_READINESS"


def test_decision_id_with_episode_is_prefixed_and_mode_suffixed():
    """Regression guard: with ``strategy_episode`` the id must embed the
    episode between the ``rh-terminal-`` prefix and the candidate_key, and
    still end with the target mode so downstream consumers that split on
    the trailing ``-<mode>`` keep working."""
    rec = _all_true_record(strategy_episode="ep-1")
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.decision_id.startswith("rh-terminal-ep-1-")
    assert d.decision_id.endswith("-LIVE_READINESS")


def test_same_candidate_key_different_episodes_disagree():
    """Purpose of this package: the daemon re-runs every 15 minutes over
    overlapping sample windows, so the same candidate_key recurs across
    rounds.  Distinct episodes must yield distinct decision_ids or the
    cross-round ``rh_gate_decisions`` primary-key collision (the 199-row
    duplicate ledger from commit 330ab3e) returns."""
    base = _all_true_record()
    a = tg.evaluate_terminal_gate(
        dict(base, strategy_episode="ep-1"), target_mode="LIVE_READINESS", now=NOW)
    b = tg.evaluate_terminal_gate(
        dict(base, strategy_episode="ep-2"), target_mode="LIVE_READINESS", now=NOW)
    assert a.decision_id != b.decision_id


def test_same_episode_same_candidate_key_is_idempotent():
    """Regression guard: within one round, re-evaluating the same record
    (same episode + candidate_key) must produce the same decision_id.
    Inserting the episode must not break the idempotency the runner relies
    on to treat a re-evaluation as an upsert, not a new row."""
    rec = _all_true_record(strategy_episode="ep-1")
    a = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    b = tg.evaluate_terminal_gate(dict(rec), target_mode="LIVE_READINESS", now=NOW)
    assert a.decision_id == b.decision_id


def test_empty_string_episode_falls_back_to_legacy_id():
    """Regression guard: an empty-string episode is 'absent', not a value.
    Without this, ``rh-terminal--<key>-<mode>`` (double dash) would become a
    new key shape and split the ledger between legacy and empty-episode
    rows for the same logical decision."""
    rec = _all_true_record(strategy_episode="")
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.decision_id == f"rh-terminal-{rec['candidate_key']}-LIVE_READINESS"


def test_none_episode_falls_back_to_legacy_id():
    """Regression guard: an explicit ``None`` episode must behave exactly
    like a missing key.  The runner may serialize records where the field
    exists but is null; treating that as an episode would mint ids of the
    form ``rh-terminal-None-...`` and collide with no legacy row."""
    rec = _all_true_record(strategy_episode=None)
    d = tg.evaluate_terminal_gate(rec, target_mode="LIVE_READINESS", now=NOW)
    assert d.decision_id == f"rh-terminal-{rec['candidate_key']}-LIVE_READINESS"
