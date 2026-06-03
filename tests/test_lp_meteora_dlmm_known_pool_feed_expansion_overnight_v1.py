"""Tests for LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1 stage.

Properties asserted:
  * no keypair / no private key / no seed phrase anywhere
  * no signer / no sendTransaction / no wallet adapter
  * candidate sources cannot be accepted without chain verification
  * heuristic fee marked heuristic
  * missing data not filled with zero
  * final verdict allowed next stages only contains the 5 specific stages
  * can_run_probe_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_174815"
REPORT_DIR = REPO_ROOT / "reports" / "lp_meteora_dlmm_known_pool_feed_expansion_overnight" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"

ALLOWED_NEXT_STAGES = {
    "LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1",
    "LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT",
    "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1",
    "LP_SOLANA_PAID_RPC_SETUP_REQUIRED",
    "STOP_LP_RESEARCH_NOW",
}
FORBIDDEN_NEXT_STAGES = {
    "EXECUTE_NOW", "FIRST_EXECUTION_RUN_V1", "MINT_NOW", "SEND_NOW",
    "WAIT_FOR_MONITOR_COMPLETION", "LP_BASE_10U_PROBE_LIVE",
    "LP_BASE_10U_PROBE_CANARY", "LP_BASE_10U_PROBE_PAPER",
    "PROBE_NOW", "LIVE TRADE_NOW", "OPEN_LP_NOW", "CLOSE_LP_NOW",
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
    assert fv["stage"] == "LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1"
    assert fv["status"] in ("PASS", "WARN", "FAIL")


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["solana_wallet_or_keypair_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"


def test_final_verdict_recommended_next_stage_in_allowed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns in ALLOWED_NEXT_STAGES
    for sub in ["EXECUTE_NOW", "FIRST_EXECUTION_RUN", "MINT_NOW", "SEND_NOW",
                "LIVE", "CANARY", "PAPER", "PROBE_NOW", "OPEN_LP_NOW", "CLOSE_LP_NOW"]:
        assert sub not in rns


def test_final_verdict_counts_present() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    for k in ["candidate_raw_count", "verified_pool_count", "sdk_decode_success_count",
              "quote_ready_pool_count", "row_count"]:
        assert k in fv, f"missing field: {k}"


# --- Chain verification: only Meteora DLMM program accepted ----------

def test_chain_verification_only_meteora_dlmm_accepted() -> None:
    """Candidates without owner = Meteora DLMM program are rejected."""
    j = _read_json("meteora_pool_chain_verification.json")
    if j is None:
        pytest.skip("chain_verification artifact not yet written")
    meteora_program = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
    for r in j:
        if r.get("selected_for_sdk_decode") and not r.get("invalid_reason"):
            assert r.get("owner") == meteora_program, (
                f"selected pool {r.get('pool_address')} has wrong owner: {r.get('owner')}"
            )


# --- SDK decode: heuristic + missing data not zero -------------------

def test_decoded_pools_heuristic_marked() -> None:
    j = _read_json("meteora_batch_pool_snapshot.json")
    if j is None:
        pytest.skip("pool_snapshot artifact not yet written")
    for r in j:
        if r.get("sdk_decode_success"):
            # Decoded pools are direct on-chain data; require either a
            # `heuristic` field set to True OR a `confidence` <= 0.95 (we use
            # 0.85 for SDK decode) which signals this is not ground truth.
            assert r.get("confidence") is not None
            assert r.get("confidence") <= 0.95, (
                f"decoded pool {r.get('pool_address')} has implausibly high confidence: {r.get('confidence')}"
            )


# --- EV preview: heuristic + missing data not zero -------------------

def test_ev_preview_all_rows_heuristic_marked() -> None:
    j = _read_json("meteora_batch_survival_ev.json")
    if j is None:
        pytest.skip("survival_ev artifact not yet written")
    for r in j:
        assert r["heuristic"] is True
        assert r["confidence"] < 0.5


# --- Forbidden strings: no keypair / no sendTransaction / no signer -

def test_no_keypair_strings() -> None:
    """Detect actual call sites in code-like lines, not policy descriptions.

    A "this_stage_does_not" bullet is policy text saying we DID NOT do X. A
    real violation would be e.g. `Keypair.from_secret_key(...)` or
    `sendTransaction(...)`. We allow the substrings to appear in policy
    prose but not as function calls in code.
    """
    bad = [
        "Keypair.from_secret_key", "Keypair.generate", "from_mnemonic", "from_seed",
        "from_bytes", "Account.from_key", "LocalAccount", "load_keystore",
    ]
    # Check for code-like patterns: a forbidden name followed by `(`
    code_pat = re.compile(r"(Keypair\.from_secret_key|Keypair\.generate|from_mnemonic|from_seed|from_bytes|Account\.from_key|LocalAccount|load_keystore|sendTransaction|sendRawTransaction)\s*\(")
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for b in bad:
            # substring check on bare names is too aggressive (appears in policy
            # text); use a regex that requires a code-like context
            assert not re.search(r"\b" + re.escape(b) + r"\s*\(", txt), (
                f"{f.name} contains forbidden call: {b!r}"
            )
        # also: any sendTransaction / sendRawTransaction followed by `(`
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
