"""INV-GATE-02: every terminal gate bit participates in acceptance.

The two stage-specific registries below are deliberately explicit.  Adding a
new terminal gate requires extending the appropriate registry and its
production conjunction; otherwise this meta-test's source-shape or behavioral
enumeration fails instead of silently accepting an incomplete terminal gate.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from scripts.lp_scanner_daemon_v1_readonly import DefaultStages, _score_row


SCORE_ROW_GATE_FIELDS = (
    "vetted", "netcover_pass", "entry_eligible", "position_cap_pass",
)
ENFORCE_GATE_FIELDS = (
    "vetted", "netcover_pass", "entry_eligible", "position_cap_pass",
)

SCORE_ROW_CONJUNCTS = frozenset({
    "vetted", "netcover_pass", "entry_allowed", "position_cap_allowed",
})
ENFORCE_CONJUNCTS = frozenset({"prior_vetted", "passed", "entry_eligible"})
ENFORCE_PASSED_CONJUNCTS = frozenset({
    "netcover_passed", "position_cap_passed",
})


def _source() -> dict[str, Any]:
    return {
        "pool": "0x1",
        "symbol": "INV-GATE-02",
        "vetted": True,
        "entry_eligible": True,
        "entry_block_reasons": [],
        "gates": {
            "quality": True,
            "yield_cover": True,
            "stable": True,
            "status_ok": True,
        },
    }


def _assessed() -> dict[str, Any]:
    return {
        "pool": "0x1",
        "netcover_pass": True,
        "position_cap_pass": True,
        "netcover": 2.0,
        "netcover_ratio": 2.0,
        "rejection_reason": None,
    }


def _accepted_after_enforce(
    source: Mapping[str, Any], assessed: Mapping[str, Any]
) -> bool:
    final = DefaultStages._enforce_fifth_gate([source], [assessed])[0]
    return bool(_score_row(final)["accepted"])


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
            if assignment_target == 'rec["vetted"]' and any(
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "rec"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "vetted"
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
        child.id
        for child in ast.walk(value)
        if isinstance(child, ast.Name)
    )


def test_inv_gate_02_terminal_conjunction_source_shape_is_complete():
    """A removed or newly added conjunct forces an explicit invariant update."""
    assert _bool_conjunct_names(
        inspect.getsource(_score_row), assignment_target="accepted"
    ) == SCORE_ROW_CONJUNCTS
    assert _bool_conjunct_names(
        inspect.getsource(DefaultStages._enforce_fifth_gate),
        assignment_target='rec["vetted"]',
    ) == ENFORCE_CONJUNCTS
    assert _bool_conjunct_names(
        inspect.getsource(DefaultStages._enforce_fifth_gate),
        assignment_target="passed",
    ) == ENFORCE_PASSED_CONJUNCTS


@pytest.mark.parametrize("field", SCORE_ROW_GATE_FIELDS)
def test_inv_gate_02_score_row_rejects_each_false_gate(field):
    record = {**_source(), **_assessed()}
    record[field] = False
    assert _score_row(record)["accepted"] is False


@pytest.mark.parametrize("field", ENFORCE_GATE_FIELDS)
def test_inv_gate_02_enforce_rejects_each_false_gate(field):
    source = _source()
    assessed = _assessed()
    target = assessed if field in {"netcover_pass", "position_cap_pass"} else source
    target[field] = False
    assert _accepted_after_enforce(source, assessed) is False


def _assert_all_false_gate_mutations_reject(
    decision: Callable[[dict[str, Any], dict[str, Any]], bool]
) -> None:
    for field in ENFORCE_GATE_FIELDS:
        source = _source()
        assessed = _assessed()
        target = (
            assessed
            if field in {"netcover_pass", "position_cap_pass"}
            else source
        )
        target[field] = False
        assert decision(source, assessed) is False, f"omitted terminal gate: {field}"


@pytest.mark.parametrize("omitted_gate", ENFORCE_GATE_FIELDS)
def test_inv_gate_02_mutation_witness_detects_each_deliberately_omitted_gate(
    omitted_gate,
):
    """A mutant that restores one false bit to True must fail the meta-check."""
    def mutant(source, assessed):
        source = dict(source)
        assessed = dict(assessed)
        target = (
            assessed
            if omitted_gate in {"netcover_pass", "position_cap_pass"}
            else source
        )
        target[omitted_gate] = True
        return _accepted_after_enforce(source, assessed)

    with pytest.raises(AssertionError, match=f"omitted terminal gate: {omitted_gate}"):
        _assert_all_false_gate_mutations_reject(mutant)
