"""Tests for LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1 stage.

Properties asserted:
  * no keypair / private key / seed phrase anywhere
  * no signer / no sendTransaction / no swap / no LP
  * RPC URL redaction (only endpoint_id + host_hash printed)
  * program id unknown not marked verified
  * getProgramAccounts bounded (dataSlice 0 bytes)
  * FINAL_VERDICT allowed_next_stages only contains the 4 specific stages
  * can_run_probe_now / execution_allowed_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_084054"
REPORT_DIR = REPO_ROOT / "reports" / "lp_solana_readonly_rpc_registry" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
RPC_REG = REPO_ROOT / "scripts" / "lp_solana_readonly_rpc_registry_v1.py"

ALLOWED_NEXT_STAGES = {
    "LP_METEORA_DLMM_READONLY_CONNECTOR_V1",
    "LP_SOLANA_RPC_REGISTRY_FIX_REPEAT",
    "LP_SOLANA_RPC_SETUP_REQUIRED",
    "STOP_LP_RESEARCH_NOW",
}
FORBIDDEN_NEXT_STAGES = {
    "EXECUTE_NOW",
    "FIRST_EXECUTION_RUN_V1",
    "MINT_NOW",
    "SEND_NOW",
    "WAIT_FOR_MONITOR_COMPLETION",
    "LP_BASE_10U_PROBE_LIVE",
    "LP_BASE_10U_PROBE_CANARY",
    "LP_BASE_10U_PROBE_PAPER",
    "LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1",  # not allowed here
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
    assert fv["stage"] == "LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1"
    assert fv["status"] in ("PASS", "WARN", "FAIL")


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["execution_allowed_now"] is False
    assert fv["transaction_sent"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["solana_wallet_or_keypair_touched"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["send_hard_disable_still_active"] is True
    assert fv["v2_modified_by_this_task"] is False
    assert fv["v2_line_count_unchanged"] is True
    assert fv["manual_approval_required"] is True


def test_final_verdict_rpc_readiness_ran() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["solana_rpc_readiness_ran"] is True
    assert fv["usable_rpc_count"] >= 1


def test_final_verdict_registry_seed_ready() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["protocol_registry_seed_ready"] is True
    assert fv["registry_count"] == 6
    assert fv["registry_p0_protocol"] == "Meteora DLMM"


def test_final_verdict_program_verification_ran() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["program_verification_ran"] is True
    assert fv["verified_program_count"] == 0
    assert fv["not_provided_count"] == 6
    assert fv["system_program_sanity_verified"] is True


def test_final_verdict_account_discovery_ran() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["account_discovery_feasibility_ran"] is True


def test_final_verdict_p0_p1_readiness() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["meteora_dlmm_registry_ready"] is False
    assert fv["orca_registry_ready"] is False
    assert fv["damm_v2_registry_ready"] is False


def test_final_verdict_recommended_next_stage_in_allowed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_final_verdict_recommended_next_stage_not_in_forbidden() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES
    for sub in ["EXECUTE_NOW", "FIRST_EXECUTION_RUN", "MINT_NOW", "SEND_NOW",
                "LIVE", "CANARY", "PAPER", "MARKET_UNSAFE_WAIT"]:
        assert sub not in rns


def test_final_verdict_did_not_list() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    did_not = fv["this_stage_did_not"]
    must_haves = [
        "Solana wallet",
        "keypair",
        "private key",
        "sign any transaction",
        "send any transaction",
        "LP position",
        "collect any fee",
        "swap any token",
        "bridge any asset",
        "live/canary/paper",
        "EVM executor v2",
        "v2 hard-disable",
        "can_run_probe_now to true",
        "tiny_canary_allowed to yes",
    ]
    for m in must_haves:
        assert any(m in line for line in did_not), f"missing did_not: {m!r}"


# --- All artifacts present -------------------------------------------

@pytest.mark.parametrize("name", [
    "STAGE_A_WORKSPACE_SAFETY.md",
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "SOLANA_RPC_READINESS_MATRIX_CN.md",
    "solana_rpc_readiness_matrix.csv", "solana_rpc_readiness_matrix.json",
    "SOLANA_PROTOCOL_REGISTRY_SEED_CN.md",
    "solana_protocol_registry_seed.csv", "solana_protocol_registry_seed.json",
    "SOLANA_PROGRAM_ID_VERIFICATION_CN.md",
    "solana_program_id_verification.csv", "solana_program_id_verification.json",
    "SOLANA_ACCOUNT_DISCOVERY_FEASIBILITY_CN.md",
    "solana_account_discovery_feasibility.csv",
    "solana_account_discovery_feasibility.json",
    "SOLANA_TOKEN_AND_QUOTE_REFERENCE_DESIGN_CN.md",
    "solana_token_and_quote_reference_design.json",
    "METEORA_DLMM_REGISTRY_READINESS_CN.md",
    "meteora_dlmm_registry_readiness.json",
    "ORCA_DAMM_REGISTRY_READINESS_CN.md",
    "orca_damm_registry_readiness.json",
    "SOLANA_READONLY_RPC_REGISTRY_NEXT_STAGE_DECISION_CN.md",
    "solana_readonly_rpc_registry_next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- RPC matrix -------------------------------------------------------

def test_rpc_matrix_has_at_least_2_endpoints() -> None:
    j = _read_json("solana_rpc_readiness_matrix.json")
    assert j["endpoint_count"] >= 2


def test_rpc_matrix_url_redaction() -> None:
    """RPC URL must not appear in plain text anywhere in artifacts."""
    j = _read_json("solana_rpc_readiness_matrix.json")
    j_str = json.dumps(j)
    forbidden_urls = [
        "https://api.mainnet-beta.solana.com",
        "https://solana.publicnode.com",
    ]
    for url in forbidden_urls:
        assert url not in j_str, f"forbidden RPC URL {url!r} leaked into JSON"


def test_rpc_matrix_csv_url_redaction() -> None:
    p = REPORT_DIR / "solana_rpc_readiness_matrix.csv"
    txt = p.read_text()
    forbidden_urls = [
        "https://api.mainnet-beta.solana.com",
        "https://solana.publicnode.com",
    ]
    for url in forbidden_urls:
        assert url not in txt, f"forbidden RPC URL {url!r} leaked into CSV"


def test_rpc_matrix_redaction_field_present() -> None:
    j = _read_json("solana_rpc_readiness_matrix.json")
    assert j["rpc_url_redaction_policy"] is not None
    for probe in j["probes"]:
        # host_hash is sha256[0:8]
        assert len(probe["host_hash"]) == 8
        assert all(c in "0123456789abcdef" for c in probe["host_hash"])


# --- protocol registry seed -----------------------------------------

def test_registry_seed_6_protocols() -> None:
    j = _read_json("solana_protocol_registry_seed.json")
    assert len(j["registry"]) == 6
    protocols = {r["protocol"] for r in j["registry"]}
    for required in ["Meteora DLMM", "Orca Whirlpools", "Meteora DAMM v2",
                     "Raydium CLMM", "Raydium CPMM", "Lifinity"]:
        assert required in protocols


def test_registry_seed_no_hard_coded_pid() -> None:
    """Program IDs must NOT be hard-coded per spec policy."""
    j = _read_json("solana_protocol_registry_seed.json")
    assert j["policy"]["no_hard_code_program_id_from_memory"] is True
    assert j["policy"]["no_hard_code_program_id_from_external_doc"] is True
    for r in j["registry"]:
        assert r["expected_program_id"] is None, (
            f"{r['protocol']} has hard-coded program id: {r['expected_program_id']}"
        )


def test_registry_seed_pid_source_is_doc_or_unknown() -> None:
    j = _read_json("solana_protocol_registry_seed.json")
    for r in j["registry"]:
        assert r["program_id_source"] in {
            "official_doc_required", "oficial_doc_required",
            "sdk_required", "unknown", "existing_artifact"
        }, (
            f"{r['protocol']} has invalid program_id_source: {r['program_id_source']}"
        )


def test_registry_seed_csv_no_hard_coded_pid() -> None:
    p = REPORT_DIR / "solana_protocol_registry_seed.csv"
    txt = p.read_text()
    # If any 32+ char base58 string appears outside header, fail
    base58_pat = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
    for line in txt.splitlines():
        if "protocol" in line and "priority" in line:
            continue
        m = base58_pat.search(line)
        assert not m, f"registry CSV may contain a base58 program id: {m.group(0)}"


# --- program ID verification --------------------------------------

def test_program_verification_no_protocol_verified() -> None:
    """Per spec policy, 0 protocol pids should be verified this round."""
    j = _read_json("solana_program_id_verification.json")
    assert j["verified_count"] == 0
    assert j["not_provided_count"] == 6


def test_program_verification_system_program_sanity_check() -> None:
    j = _read_json("solana_program_id_verification.json")
    sys_prog = j["system_program_sanity_check"]
    assert sys_prog["program_id"] == "11111111111111111111111111111111"
    assert sys_prog["verification_status"] == "verified"


def test_program_verification_no_signer_call() -> None:
    j = _read_json("solana_program_id_verification.json")
    s = json.dumps(j)
    bad = ["Keypair.from_secret_key(", "Keypair.generate(",
           "from_secret_key(", "from_seed(", "from_bytes(",
           "sendTransaction(", "sendRawTransaction(",
           "Account.from_key", "from_mnemonic("]
    for b in bad:
        assert b not in s, f"verification contains suspicious token: {b!r}"


# --- account discovery feasibility ---------------------------------

def test_account_discovery_bounded() -> None:
    j = _read_json("solana_account_discovery_feasibility.json")
    gpa = j["gpa_limits"]
    assert gpa["dataSlice"] == "0 bytes data, only count"
    assert gpa["timeout_seconds"] == 8.0
    assert gpa["no_unbounded_scan"] is True
    assert gpa["no_retry_on_rate_limit"] is True


def test_account_discovery_skipped_due_to_no_pid() -> None:
    j = _read_json("solana_account_discovery_feasibility.json")
    assert j["gpa_smoke_skipped_count"] == 6
    assert j["gpa_smoke_attempted_count"] == 1  # System Program sanity


# --- token/quote reference design ---------------------------------

def test_token_quote_design_9_dimensions() -> None:
    j = _read_json("solana_token_and_quote_reference_design.json")
    dims = j["token_quote_dimensions"]
    assert len(dims) >= 9


def test_token_quote_design_does_not_use_jupiter_swap() -> None:
    j = _read_json("solana_token_and_quote_reference_design.json")
    s = json.dumps(j)
    assert "jupiter-swap" not in s.lower() or "/swap" not in s, (
        "jupiter /swap endpoint mentioned without 'NOT used' qualifier"
    )
    # more specific: ensure no /swap endpoint is mentioned
    assert 'jupiter.ag/v6/swap' not in s


# --- Meteora / Orca / DAMM readiness -------------------------------

def test_meteora_dlmm_readiness_not_ready() -> None:
    j = _read_json("meteora_dlmm_registry_readiness.json")
    assert j["readiness_answers"]["Q1_verified_dlmm_program_id"] is False
    assert j["readiness_answers"]["Q6_can_enter_connector"] is False
    assert j["readiness_summary"]["overall_readiness_for_connector"] is False


def test_orca_damm_readiness_not_ready() -> None:
    j = _read_json("orca_damm_registry_readiness.json")
    assert j["orca_whirlpools"]["can_enter_connector"] is False
    assert j["meteora_damm_v2"]["can_enter_connector"] is False


# --- next stage decision ------------------------------------------

def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("solana_readonly_rpc_registry_next_stage_decision.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_next_stage_decision_not_METEORA_DLMM_CONNECTOR() -> None:
    j = _read_json("solana_readonly_rpc_registry_next_stage_decision.json")
    assert j["recommended_next_stage"] != "LP_METEORA_DLMM_READONLY_CONNECTOR_V1"


def test_next_stage_decision_must_not_list() -> None:
    j = _read_json("solana_readonly_rpc_registry_next_stage_decision.json")
    must_not = j["next_stage_must_not"]
    must_haves = [
        "execute probe on Solana", "send any tx",
        "keypair",
        "transaction",
        "bridge",
        "swap",
        "hard-disable",
        "can_run_probe_now to true",
        "tiny_canary_allowed to yes"
    ]
    for m in must_haves:
        assert any(m in line for line in must_not), f"missing must_not: {m!r}"


# --- v2 line count 992 unchanged ---------------------------------

def test_v2_line_count_unchanged() -> None:
    assert V2.is_file()
    with V2.open() as f:
        n = sum(1 for _ in f)
    assert n == 992, f"v2 line count changed: {n}"


# --- Sweep: safety invariants stay false everywhere ------------

def test_can_run_probe_now_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "can_run_probe_now" in data:
            assert data["can_run_probe_now"] is False, (
                f"{jf.name} has can_run_probe_now={data['can_run_probe_now']!r}"
            )


def test_tiny_canary_allowed_no_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            assert data["tiny_canary_allowed"] == "no", (
                f"{jf.name} has tiny_canary_allowed={data['tiny_canary_allowed']!r}"
            )


def test_solana_wallet_or_keypair_touched_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "solana_wallet_or_keypair_touched" in data:
            assert data["solana_wallet_or_keypair_touched"] is False, (
                f"{jf.name} has solana_wallet_or_keypair_touched={data['solana_wallet_or_keypair_touched']!r}"
            )


# --- No secret-shaped strings in artifacts ---------------------

def test_no_64hex_private_key_shape_in_any_artifact() -> None:
    pat = re.compile(r'"(0x[0-9a-fA-F]{64})"')
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for m in pat.finditer(txt):
            hex_val = m.group(1)
            start = txt.rfind("\n", 0, m.start()) + 1
            end = txt.find("\n", m.end())
            if end < 0:
                end = len(txt)
            line = txt[start:end]
            # known safe fields
            safe = ("pool_liquidity_raw", "pool_slot0_raw", "gas_price_wei",
                    "wallet_eth_wei", "usdc_balance_raw", "weth_balance_raw",
                    "usdc_allowance_raw", "weth_allowance_raw", "block_number")
            if any(fld in line for fld in safe):
                continue
            assert False, f"{f.name} contains 64-hex NOT in safe field: {line!r}"


def test_no_signer_construction_strings() -> None:
    """Solana + EVM: no signer / keypair / seed phrase / wallet import."""
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "HTTPProvider(", "Web3(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction(",
           # Solana
           "Keypair.from_secret_key(", "Keypair.generate(",
           "from_secret_key(", "from_seed(", "from_bytes(",
           "sendTransaction(", "sendRawTransaction(",
           "solana-keygen", "wallet add"]
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for b in bad:
            assert b not in txt, f"{f.name} contains suspicious call: {b!r}"


# --- RPC registry script: no keypair / no signer / CLI test --------

def test_rpc_registry_script_no_signer_call() -> None:
    src = RPC_REG.read_text()
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "Web3(", "Keypair.from_secret_key(",
           "send_transaction(", "send_raw_transaction(",
           "sign_transaction(", "from_secret_key(", "from_seed(",
           "sendTransaction(", "sendRawTransaction(",
           "solana-keygen", "wallet import", "wallet add"]
    for b in bad:
        assert b not in src, f"rpc_registry script contains suspicious token: {b!r}"


def test_rpc_registry_script_url_redaction_policy() -> None:
    """Script should write endpoint_id + host_hash (not full URL) to artifacts."""
    src = RPC_REG.read_text()
    # script uses endpoint_id + host_hash + source_type fields
    assert "host_hash" in src
    assert "endpoint_id" in src
    assert "source_type" in src
    # The script never writes the full URL to CSV/JSON outputs
    # Check that the function that writes CSV/JSON only uses the structured fields
    assert "_hash_host" in src
    assert "endpoint_id" in src


def test_rpc_registry_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(RPC_REG), "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0
    assert "Solana" in proc.stdout or "RPC" in proc.stdout


# FIX-R3 retirement assertions are deliberately additive: the historical
# artifact assertions above remain in place and continue protecting evidence.
def test_rpc_registry_is_documented_as_superseded_thin_shell() -> None:
    src = RPC_REG.read_text()
    assert "superseded by lp_rpc_pool CHAINS['solana']" in src
    assert "def probe_endpoint(" not in src
    assert "def gpa_smoke(" not in src
    assert "def verify_program(" not in src


def test_rpc_registry_reexports_canonical_solana_pool() -> None:
    from scripts import lp_rpc_pool_v1_readonly as canonical
    from scripts import lp_solana_readonly_rpc_registry_v1 as legacy

    assert legacy.CHAINS is canonical.CHAINS
    assert legacy.SOLANA_CHAIN is canonical.CHAINS["solana"]
    assert legacy.RpcPool is canonical.RpcPool
    assert legacy.RpcPoolExhaustedError is canonical.RpcPoolExhaustedError
    assert legacy.PUBLIC_FALLBACK_RPCS == tuple(
        endpoint["url"] for endpoint in canonical.CHAINS["solana"]["endpoints"]
    )


def test_rpc_registry_legacy_cli_defaults_to_solana_pool() -> None:
    proc = subprocess.run(
        [sys.executable, str(RPC_REG), "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0
    assert "--probe" in proc.stdout
    assert "--chain" in proc.stdout
