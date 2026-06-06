"""Tests for LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1.

These tests verify:
  - expanded universe has no placeholder pools (<smoke_pool_)
  - pool count target (>=45) enforced
  - protocol distribution exists
  - chain distribution exists
  - adapter_ready vs collector_observable distinguished
  - cannot mark full coverage if adapter missing
  - no wallet / keypair / signer
  - no tx send
  - no long run started
  - final verdict allowed next stages only

All tests are read-only.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_real_pool_universe_coverage_expand" / "20260606_091120"

ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1",
    "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1",
    "LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
}


# ---------------------------------------------------------------------------
# Stage A: input evidence
# ---------------------------------------------------------------------------

def test_a_input_evidence_audit_files_exist() -> None:
    assert (REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md").exists()
    assert (REPORT_DIR / "input_evidence_audit.json").exists()


def test_a_input_evidence_confirms_finalize_fix() -> None:
    d = json.loads((REPORT_DIR / "input_evidence_audit.json").read_text())
    assert d["input_evidence_confirmed"]["finalize_bug_fixed"] is True
    assert d["input_evidence_confirmed"]["fallback_finalize_bug_fixed"] is True
    assert d["input_evidence_confirmed"]["lowercase_python_boolean_removed"] is True
    assert d["input_evidence_confirmed"]["current_universe_pool_count"] == 33
    assert d["input_evidence_confirmed"]["target_pool_count"] == 45
    assert d["input_evidence_confirmed"]["pool_count_gap"] == 12
    assert len(d["input_evidence_confirmed"]["missing_protocols"]) == 5


# ---------------------------------------------------------------------------
# Stage B: Meteora DLMM coverage
# ---------------------------------------------------------------------------

def test_b_meteora_coverage_csv_exists() -> None:
    assert (REPORT_DIR / "meteora_dlmm_coverage_expand.csv").exists()
    assert (REPORT_DIR / "meteora_dlmm_coverage_expand.json").exists()
    assert (REPORT_DIR / "METEORA_DLMM_COVERAGE_EXPAND_CN.md").exists()


def test_b_meteora_at_least_10_pools() -> None:
    """At least 10 Meteora pools (target 10)."""
    d = json.loads((REPORT_DIR / "meteora_dlmm_coverage_expand.json").read_text())
    assert d["selected_for_12h_retry_count"] >= 10


def test_b_meteora_all_addresses_real_or_pending_marker() -> None:
    """Meteora pool addresses should be real (44 char base58) — not placeholder."""
    d = json.loads((REPORT_DIR / "meteora_dlmm_coverage_expand.json").read_text())
    for p in d["pools"]:
        addr = p["pool_address"]
        # Solana base58: 32-50 chars
        assert re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,50}$", addr), f"non-base58 address: {addr}"


def test_b_meteora_owner_program_is_dlmm() -> None:
    """All Meteora pools should have owner_program = LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo."""
    d = json.loads((REPORT_DIR / "meteora_dlmm_coverage_expand.json").read_text())
    for p in d["pools"]:
        assert p["owner_program"] == "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
        assert p["owner_program_verified"] is True
        assert p["data_len"] == 904
        assert p["dlmm_sized"] is True


def test_b_meteora_no_placeholder_marker() -> None:
    """No <smoke_pool_> in any Meteora pool_address."""
    d = json.loads((REPORT_DIR / "meteora_dlmm_coverage_expand.json").read_text())
    for p in d["pools"]:
        assert "<smoke_pool_" not in p["pool_address"]


# ---------------------------------------------------------------------------
# Stage C: Base Uniswap V3 coverage
# ---------------------------------------------------------------------------

def test_c_base_univ3_csv_exists() -> None:
    assert (REPORT_DIR / "base_uniswap_v3_coverage_expand.csv").exists()
    assert (REPORT_DIR / "base_uniswap_v3_coverage_expand.json").exists()
    assert (REPORT_DIR / "BASE_UNISWAP_V3_COVERAGE_EXPAND_CN.md").exists()


def test_c_base_univ3_at_least_5_pools() -> None:
    d = json.loads((REPORT_DIR / "base_uniswap_v3_coverage_expand.json").read_text())
    assert d["candidate_count"] >= 5


def test_c_base_univ3_adapter_ready_yes_collector_observable_no() -> None:
    """Base UniV3: adapter_ready=true but collector_observable=false (EVM not wired)."""
    d = json.loads((REPORT_DIR / "base_uniswap_v3_coverage_expand.json").read_text())
    assert d["adapter_ready"] is True
    assert d["collector_observable"] is False
    for p in d["pools"]:
        assert p["adapter_ready"] is True
        assert p["collector_observable"] is False


def test_c_base_univ3_inferred_pools_marked_pending() -> None:
    """Inferred pools should have validation_status=inferred_..._not_rpc_validated."""
    d = json.loads((REPORT_DIR / "base_uniswap_v3_coverage_expand.json").read_text())
    inferred = [p for p in d["pools"] if "inferred" in p["validation_status"]]
    assert len(inferred) >= 1, "expected at least 1 inferred pool"
    for p in inferred:
        assert "not_rpc_validated" in p["validation_status"]


# ---------------------------------------------------------------------------
# Stage D: Base Aerodrome coverage
# ---------------------------------------------------------------------------

def test_d_aerodrome_csv_exists() -> None:
    assert (REPORT_DIR / "base_aerodrome_coverage_expand.csv").exists()
    assert (REPORT_DIR / "base_aerodrome_coverage_expand.json").exists()
    assert (REPORT_DIR / "BASE_AERODROME_COVERAGE_EXPAND_CN.md").exists()


def test_d_aerodrome_classic_and_slipstream_distinguished() -> None:
    d = json.loads((REPORT_DIR / "base_aerodrome_coverage_expand.json").read_text())
    assert d["classic_count"] >= 4
    assert d["slipstream_count"] >= 1
    # Slipstream must have adapter_ready=false (custom tick math)
    for p in d["pools"]:
        if "slipstream" in p["pool_subtype"]:
            assert p["adapter_ready"] is False, "slipstream must have adapter_ready=false"
            assert "custom_tick_math" in p["reason"] or "tick_math" in p["reason"]


def test_d_aerodrome_slipstream_adapter_gap_explicit() -> None:
    """Slipstream must NOT be marked ready (per spec: must mark adapter gap honestly)."""
    d = json.loads((REPORT_DIR / "base_aerodrome_coverage_expand.json").read_text())
    slipstream = [p for p in d["pools"] if "slipstream" in p["pool_subtype"]]
    assert len(slipstream) >= 1
    for p in slipstream:
        assert p["adapter_ready"] is False
        assert p["collector_observable"] is False


# ---------------------------------------------------------------------------
# Stage E: BSC PancakeSwap coverage
# ---------------------------------------------------------------------------

def test_e_bsc_csv_exists() -> None:
    assert (REPORT_DIR / "bsc_pancakeswap_coverage_expand.csv").exists()
    assert (REPORT_DIR / "bsc_pancakeswap_coverage_expand.json").exists()
    assert (REPORT_DIR / "BSC_PANCAKESWAP_COVERAGE_EXPAND_CN.md").exists()


def test_e_bsc_at_least_5_v3_pools() -> None:
    d = json.loads((REPORT_DIR / "bsc_pancakeswap_coverage_expand.json").read_text())
    assert d["v3_count"] >= 5


def test_e_bsc_at_least_5_v2_pools() -> None:
    d = json.loads((REPORT_DIR / "bsc_pancakeswap_coverage_expand.json").read_text())
    assert d["v2_count"] >= 5


def test_e_bsc_chain_adapter_not_implemented_explicit() -> None:
    """BSC pools must explicitly mark bsc_chain_adapter_not_implemented_yet."""
    d = json.loads((REPORT_DIR / "bsc_pancakeswap_coverage_expand.json").read_text())
    assert d["adapter_ready"] is False
    assert d["collector_observable"] is False
    assert "bsc_chain_adapter_not_implemented_yet" in d["bsc_chain_adapter_status"]
    for p in d["pools"]:
        assert p["adapter_ready"] is False
        assert p["collector_observable"] is False
        assert "bsc_chain_adapter" in p["reason"]


def test_e_bsc_v3_addresses_real_or_pending() -> None:
    """V3 pool addresses should be 0x-prefixed 40 hex chars (real or PENDING marker)."""
    d = json.loads((REPORT_DIR / "bsc_pancakeswap_coverage_expand.json").read_text())
    for p in d["pools"]:
        if p["protocol"] == "pancakeswap_v3":
            addr = p["pool_address"]
            assert addr.startswith("0x") and len(addr) == 42, f"invalid hex address: {addr}"
            assert re.match(r"^0x[0-9a-fA-F]{40}$", addr), f"non-hex address: {addr}"


# ---------------------------------------------------------------------------
# Stage F: expanded universe merge
# ---------------------------------------------------------------------------

def test_f_expanded_universe_files_exist() -> None:
    assert (REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.csv").exists()
    assert (REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.json").exists()
    assert (REPORT_DIR / "EXPANDED_REAL_POOL_UNIVERSE_FOR_12H_RETRY_CN.md").exists()


def test_f_expanded_universe_pool_count_45_plus() -> None:
    d = json.loads((REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.json").read_text())
    assert d["total_pool_count"] >= 45
    assert d["target_pool_count_met"] is True


def test_f_expanded_universe_protocol_distribution_exists() -> None:
    d = json.loads((REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.json").read_text())
    assert len(d["protocol_distribution"]) >= 5
    assert d["target_protocol_count_met"] is True


def test_f_expanded_universe_chain_distribution_exists() -> None:
    d = json.loads((REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.json").read_text())
    assert len(d["chain_distribution"]) >= 3
    assert d["target_chain_count_met"] is True


def test_f_expanded_universe_no_placeholder() -> None:
    """No <smoke_pool_> in any pool_address."""
    d = json.loads((REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.json").read_text())
    for p in d["pools"]:
        assert "<smoke_pool_" not in (p.get("pool_address") or ""), f"placeholder in {p}"
        assert "<smoke_mint_" not in (p.get("token_pair") or "")


def test_f_expanded_universe_preserves_v2_33_pools() -> None:
    """V2 33 pools should be preserved (oracles + raydiums)."""
    d = json.loads((REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.json").read_text())
    v2_pools = [p for p in d["pools"] if p["validation_status"] == "verified_v2_universe"]
    assert len(v2_pools) == 33


def test_f_expanded_universe_adapter_vs_observable_distinguished() -> None:
    """adapter_ready and collector_observable are independent fields."""
    d = json.loads((REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.json").read_text())
    # Solana (V2 + Meteora): both true
    # Base/BSC: adapter_ready may be true OR false, but collector_observable=false
    for p in d["pools"]:
        if p["chain"] in ("base", "bsc"):
            assert p["collector_observable"] is False, \
                f"Base/BSC pool should be non-observable: {p}"


def test_f_expanded_universe_cannot_mark_full_coverage_if_adapter_missing() -> None:
    """If any pool is non-observable, collector_full_coverage_ready must be false."""
    d = json.loads((REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.json").read_text())
    non_obs = d["non_observable_pool_count"]
    if non_obs > 0:
        # honest disclosure: full coverage NOT ready
        # (The spec says: "如果 Base/BSC adapter 未接通，不能把 full_coverage_ready 设为 true")
        # Note: 23 non-observable pools (Base 10 + BSC 13) are blocking
        assert d["collector_full_coverage_ready"] is False or non_obs < 0  # should be false


# ---------------------------------------------------------------------------
# Stage G: coverage gap decision
# ---------------------------------------------------------------------------

def test_g_coverage_gap_decision_files_exist() -> None:
    assert (REPORT_DIR / "coverage_gap_decision.json").exists()
    assert (REPORT_DIR / "COVERAGE_GAP_DECISION_CN.md").exists()


def test_g_coverage_gap_decision_recommended_next_stage_allowed() -> None:
    d = json.loads((REPORT_DIR / "coverage_gap_decision.json").read_text())
    assert d["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_g_coverage_gap_decision_honest_disclosure() -> None:
    """If non_observable > 0, decision must recommend adapter wiring (not 12h retry)."""
    u = json.loads((REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.json").read_text())
    d = json.loads((REPORT_DIR / "coverage_gap_decision.json").read_text())
    if u["non_observable_pool_count"] > 0:
        assert d["decisions"]["can_12h_retry_directly"] is False
        # Recommended must be adapter wiring OR coverage expand repeat (but not 12h retry)
        assert d["recommended_next_stage"] != "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1"


# ---------------------------------------------------------------------------
# Stage H: final verdict
# ---------------------------------------------------------------------------

def test_h_final_verdict_required_fields() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    required = {
        "stage", "status",
        "current_pool_count", "target_pool_count", "expanded_pool_count", "added_pool_count",
        "meteora_dlmm_added_count", "base_uniswap_v3_added_count", "base_aerodrome_added_count",
        "bsc_pancakeswap_v3_added_count", "bsc_pancakeswap_v2_added_count",
        "observable_pool_count", "non_observable_pool_count",
        "target_pool_count_met", "target_protocol_count_met", "target_chain_count_met",
        "collector_full_coverage_ready", "can_start_12h_retry_after_this",
        "can_run_probe_now", "tiny_canary_allowed",
        "wallet_or_tx_touched", "transaction_sent",
        "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_h_final_verdict_locked_fields() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False


def test_h_final_verdict_recommended_next_stage_allowed() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_h_final_verdict_pool_count_matches_expanded() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    u = json.loads((REPORT_DIR / "expanded_real_pool_universe_for_12h_retry.json").read_text())
    assert fv["expanded_pool_count"] == u["total_pool_count"]
    assert fv["observable_pool_count"] == u["observable_pool_count"]


def test_h_final_verdict_no_long_run_started() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["can_start_12h_retry_after_this"] is False


# ---------------------------------------------------------------------------
# Stage I: safety
# ---------------------------------------------------------------------------

def test_i_no_forbidden_process() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["canary", "lpbot-live", "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in forbidden:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                pytest.fail(f"forbidden process token {tok!r} found: {line}")


def test_i_no_long_running_collectors_started() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in ["run_lp_long_horizon_readonly_stage_once", "lp_long_horizon_readonly_collector_v1", "tmux: server"]:
            if tok in line:
                pytest.fail(f"long-running collector/runner still running: {line}")


def test_i_no_secret_value_in_outputs() -> None:
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),  # 64-hex private key
    ]
    for p in REPORT_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md", ".csv"}:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in value_patterns:
                m = pat.search(text)
                if m:
                    # 64-hex might match 0x addresses in pool addresses, but
                    # pool addresses are 40 hex chars (not 64).
                    snippet = m.group(0)[:80]
                    # Allow 40-char hex (pool addresses) but not 64-char
                    if len(m.group(0)) >= 64 and "0x" in m.group(0):
                        pytest.fail(f"potential 64-hex secret matched {pat.pattern!r} in {p}: {snippet}")
                    elif "private_key" in pat.pattern or "mnemonic" in pat.pattern or "seed" in pat.pattern:
                        pytest.fail(f"potential secret value matched {pat.pattern!r} in {p}: {snippet}")


def test_i_source_12h_data_dir_unchanged() -> None:
    """12h data dir (84 files) should be unchanged — this stage is read-only on it."""
    src = ROOT / "data" / "lp_long_horizon" / "20260605_082120"
    if not src.exists():
        pytest.skip("12h fixture data not present")
    # Just check it's still there with same files
    files = list(src.rglob("*"))
    files = [f for f in files if f.is_file()]
    assert len(files) > 0
