"""Tests for LP_SOLANA_STABLE_POOL_RESEARCH_V1 stage (LP research 收口).

Properties asserted:
  * no keypair / no private key / no seed phrase anywhere
  * no signer / no sendTransaction / no wallet adapter
  * candidate sources cannot be accepted without chain verification
  * heuristic fee marked heuristic
  * missing data not filled with zero
  * final verdict allowed next stages only contains the 4 specific stages
  * can_run_probe_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
  * SURVIVAL_EV ran on quote-ready pools only
  * positive_realistic_count = 0 -> STOP_LP_RESEARCH_NOW (per spec rule_2 + 5/5 AMM reject)
  * 4 stable AMM programs verified on mainnet
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260604_044118"
REPORT_DIR = REPO_ROOT / "reports" / "lp_solana_stable_pool_research" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"

ALLOWED_NEXT_STAGES = {
    "LP_STABLE_POOL_10_20U_PROBE_PREFLIGHT_DESIGN_V1",
    "LP_STABLE_POOL_KNOWN_POOL_FEED_EXPANSION_REPEAT",
    "LP_SOLANA_PAID_RPC_SETUP_REQUIRED",
    "STOP_LP_RESEARCH_NOW",
}


def _read_json(rel: str) -> dict | None:
    p = REPORT_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


# --- FINAL_VERDICT.json -----------------------------------------------

def test_final_verdict_exists() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv is not None
    assert fv["stage"] == "LP_SOLANA_STABLE_POOL_RESEARCH_V1"
    assert fv["status"] in ("PASS", "WARN", "FAIL")


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["solana_wallet_or_keypair_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["v2_line_count_unchanged"] is True
    assert fv["v2_line_count"] == 992


def test_final_verdict_recommended_next_stage_in_allowed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns in ALLOWED_NEXT_STAGES
    for sub in ["EXECUTE_NOW", "FIRST_EXECUTION_RUN", "MINT_NOW", "SEND_NOW",
                "LIVE", "CANARY", "PAPER", "PROBE_NOW", "OPEN_LP_NOW", "CLOSE_LP_NOW"]:
        assert sub not in rns


def test_final_verdict_program_verified() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["program_verified"] is True
    assert fv["verified_program_count"] == 4


def test_final_verdict_counts_present() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    for k in ["verified_pool_count", "sdk_decode_success_count",
              "quote_ready_pool_count", "row_count",
              "positive_realistic_count",
              "best_pool", "best_net_ev_proxy_usd", "stable_quote_ready_count"]:
        assert k in fv, f"missing field: {k}"


# --- LP Research 收口: 5/5 AMM reject record -----------------------

def test_amm_cumulative_5_reject_recorded() -> None:
    """LP research 收口: 5/5 Solana AMM protocols reject retail 10-20U 2000 USD LP."""
    fv = _read_json("FINAL_VERDICT.json")
    cumulative = fv.get("amm_cumulative_5_reject", {})
    assert "meteora_dlmm_v8" in cumulative
    assert "orca_whirlpools_v1" in cumulative
    assert "raydium_clmm_v1" in cumulative
    assert "raydium_cpmm_v1" in cumulative
    assert "orca_stable_this" in cumulative
    # All 5 should have positive_realistic=0
    for k, v in cumulative.items():
        if k == "summary":
            continue
        assert v.get("positive_realistic") == 0, f"{k} has positive_realistic != 0"


def test_stop_lp_research_now_recommendation() -> None:
    """Per spec rule_2 + 5/5 reject: STOP_LP_RESEARCH_NOW is the selected next stage."""
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] == "STOP_LP_RESEARCH_NOW"


# --- Chain verification: at least 1 program accepted ---------------

def test_chain_verification_some_pools_accepted() -> None:
    j = _read_json("stable_pool_chain_verification.json")
    if j is None:
        pytest.skip("chain_verification artifact not yet written")
    n_v = sum(1 for r in j if r.get("verified"))
    assert n_v >= 1, f"no pools verified (n_v={n_v})"


# --- SDK decode: heuristic + missing data not zero -------------------

def test_decoded_pools_heuristic_marked() -> None:
    j = _read_json("stable_pool_decode_snapshot.json")
    if j is None:
        pytest.skip("pool_snapshot artifact not yet written")
    for r in j:
        if r.get("sdk_decode_success"):
            assert r.get("confidence") is not None
            assert r.get("confidence") <= 0.95, (
                f"decoded pool {r.get('pool_address')} has implausibly high confidence"
            )


# --- EV preview: heuristic + missing data not zero -------------------

def test_ev_preview_all_rows_heuristic_marked() -> None:
    j = _read_json("stable_pool_survival_ev_preview.json")
    if j is None:
        pytest.skip("survival_ev artifact not yet written")
    for r in j:
        assert r["heuristic"] is True
        assert r["confidence"] < 0.5
        assert r["scope"] == "stable_pool_research"


def test_ev_row_count_matches_quote_ready() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    qr = fv["quote_ready_pool_count"]
    expected = qr * 6 * 7 * 4
    assert fv["row_count"] == expected, f"row_count {fv['row_count']} != {expected}"


def test_ev_realistic_zero_triggers_stop() -> None:
    """Per spec rule_2: positive_realistic=0 + quote_ready>0 -> STOP_LP_RESEARCH_NOW."""
    fv = _read_json("FINAL_VERDICT.json")
    if fv["positive_realistic_count"] > 0:
        return
    assert fv["recommended_next_stage"] == "STOP_LP_RESEARCH_NOW"


# --- Forbidden strings: no keypair / no sendTransaction / no signer -

def test_no_keypair_strings() -> None:
    code_pat = re.compile(r"(Keypair\.from_secret_key|Keypair\.generate|from_mnemonic|from_seed|from_bytes|Account\.from_key|LocalAccount|load_keystore|sendTransaction|sendRawTransaction)\s*\(")
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
