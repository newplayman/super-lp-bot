"""Tests for LP_RESEARCH_FINAL_FREEZE_AND_HANDOFF_V1 stage.

Properties asserted:
  * final verdict has STOP_LP_RESEARCH_NOW
  * can_run_probe_now false
  * tiny_canary_allowed no
  * edge_proven no
  * docs updated (LPBOT_RESEARCH_STATUS_CN.md, ARTIFACT_INDEX_CN.md, README.md all contain 2026-06-04 final freeze reference)
  * reopen conditions present
  * no private key / keypair / signer / sendTransaction
  * no wallet / tx path touched
  * 5/5 AMM reject cumulative documented
  * 12 reusable modules listed
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260604_051254"
REPORT_DIR = REPO_ROOT / "reports" / "lp_research_final_freeze" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
DOCS = REPO_ROOT / "docs"


def _read_json(rel: str) -> dict | None:
    p = REPORT_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


# --- FINAL_VERDICT.json -----------------------------------------------

def test_final_verdict_exists() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv is not None
    assert fv["stage"] == "LP_RESEARCH_FINAL_FREEZE_AND_HANDOFF_V1"
    assert fv["status"] in ("PASS", "WARN", "FAIL")


def test_final_verdict_stop_recommendation() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["overall_recommendation"] == "STOP_LP_RESEARCH_NOW"
    assert fv["recommended_next_stage"] == "STOP_LP_RESEARCH_NOW"


def test_final_verdict_safety_locks() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["solana_wallet_or_keypair_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["v2_line_count_unchanged"] is True
    assert fv["v2_line_count"] == 992
    assert fv["send_hard_disable_still_active"] is True


def test_final_verdict_cumulative_5_reject() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    protocols = fv.get("protocols_frozen", [])
    assert len(protocols) == 5, f"expected 5 protocols_frozen, got {len(protocols)}"
    expected_stages = [
        "LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1",
        "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1",
        "LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1",
        "LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1",
        "LP_SOLANA_STABLE_POOL_RESEARCH_V1",
    ]
    actual_stages = [p["stage"] for p in protocols]
    for expected in expected_stages:
        assert expected in actual_stages, f"missing {expected} in protocols_frozen"

    # All should be REJECT
    for p in protocols:
        assert p["verdict"] == "REJECT", f"{p['stage']} verdict != REJECT"

    # All best_scenario should be zero_il_lvr
    for p in protocols:
        assert p["best_scenario"] == "zero_il_lvr"


def test_final_verdict_cumulative_summary() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    summary = fv.get("cumulative_summary", {})
    cs = summary.get("cumulative_5_stages", {})
    assert cs.get("total_positive_realistic") == 0
    assert cs.get("total_positive_optimistic") == 0
    assert cs.get("total_positive_conservative") == 0
    assert cs.get("total_positive_zero_il_lvr", 0) > 0
    assert cs.get("total_cells", 0) > 0


def test_final_verdict_reopen_documented() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["reopen_conditions_documented"] is True
    assert fv["docs_updated"] is True
    assert len(fv["reopen_conditions_summary"]) == 7


# --- Reopen conditions file -----------------------------------------

def test_reopen_conditions_file_present() -> None:
    f = _read_json("lp_research_reopen_conditions.json")
    assert f is not None
    assert len(f.get("conditions", [])) == 7
    assert len(f.get("reopen_flow_mandatory", [])) == 7
    assert len(f.get("checklist_11_items", [])) == 11


# --- Why stop file --------------------------------------------------

def test_why_stop_file_present() -> None:
    f = _read_json("why_stop_lp_research_now.json")
    assert f is not None
    assert len(f.get("reasons", [])) == 9
    assert f.get("decision") == "STOP_LP_RESEARCH_NOW"


# --- What this does NOT mean file ----------------------------------

def test_not_meant_file_present() -> None:
    f = _read_json("what_this_does_not_mean.json")
    assert f is not None
    assert len(f.get("six_common_misreadings", [])) == 6


# --- Reusable modules file -----------------------------------------

def test_reusable_modules_file_present() -> None:
    f = _read_json("reusable_artifacts_and_modules.json")
    assert f is not None
    assert len(f.get("reusable_modules", [])) == 12
    assert len(f.get("do_not_delete", [])) > 0


# --- Final freeze matrix file --------------------------------------

def test_final_freeze_matrix_file_present() -> None:
    f = _read_json("lp_research_final_freeze_matrix.json")
    assert f is not None
    assert f.get("overall_recommendation") == "STOP_LP_RESEARCH_NOW"
    assert f.get("matrix_version") == "v1"
    assert len(f.get("research_lines", [])) == 7


# --- Next project direction file -----------------------------------

def test_next_project_direction_file_present() -> None:
    f = _read_json("next_project_direction.json")
    assert f is not None
    assert len(f.get("four_directions", [])) == 4
    primary = f.get("recommendations", {}).get("if_active_development", {}).get("primary", "")
    assert "A" in primary or "B" in primary


# --- Docs updated ---------------------------------------------------

def test_lpbot_research_status_doc_updated() -> None:
    f = DOCS / "LPBOT_RESEARCH_STATUS_CN.md"
    assert f.is_file()
    txt = f.read_text()
    assert "STOP_LP_RESEARCH_NOW" in txt
    assert "20260604_051254" in txt or "2026-06-04" in txt
    assert "5/5" in txt or "5 个" in txt or "5 个 Solana" in txt


def test_artifact_index_doc_updated() -> None:
    f = DOCS / "LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md"
    assert f.is_file()
    txt = f.read_text()
    assert "lp_research_final_freeze" in txt
    assert "20260604_051254" in txt


def test_readme_updated() -> None:
    f = REPO_ROOT / "README.md"
    assert f.is_file()
    txt = f.read_text()
    assert "STOP_LP_RESEARCH_NOW" in txt
    assert "2026-06-04" in txt
    assert "5/5" in txt


# --- Forbidden strings: no keypair / no sendTransaction / no signer -

def test_no_keypair_strings() -> None:
    code_pat = re.compile(r"(Keypair\.from_secret_key|Keypair\.generate|from_mnemonic|from_seed|from_bytes|Account\.from_key|LocalAccount|load_keystore|sendTransaction|sendRawTransaction|eth_sendRawTransaction|eth_sendTransaction)\s*\(")
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        assert not code_pat.search(txt), f"{f.name} contains forbidden call site"


# --- No 64-hex private keys ------------------------------------------

def test_no_64hex_private_key() -> None:
    pat = re.compile(r'"(0x[0-9a-fA-F]{64})"')
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for m in pat.finditer(txt):
            pytest.fail(f"{f.name} contains 64-hex private key shape: {m.group(1)!r}")


# --- v2 line count 992 unchanged -------------------------------------

def test_v2_line_count_unchanged() -> None:
    assert V2.is_file()
    with V2.open() as f:
        n = sum(1 for _ in f)
    assert n == 992, f"v2 line count changed: {n}"


# --- Repo root not polluted ------------------------------------------

def test_repo_node_modules_not_created() -> None:
    nm = REPO_ROOT / "node_modules"
    assert not nm.is_dir(), f"repo node_modules was created: {nm}"


# --- Sweep: safety invariants stay false everywhere -----------------

def test_can_run_probe_now_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "can_run_probe_now" in data:
            val = data["can_run_probe_now"]
            assert val is False, f"{jf.name} has can_run_probe_now={val!r}"


def test_solana_wallet_or_keypair_touched_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "solana_wallet_or_keypair_touched" in data:
            val = data["solana_wallet_or_keypair_touched"]
            assert val is False, f"{jf.name} has solana_wallet_or_keypair_touched={val!r}"


def test_tiny_canary_allowed_no_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            val = data["tiny_canary_allowed"]
            assert val == "no" or val is False, f"{jf.name} has tiny_canary_allowed={val!r}"
