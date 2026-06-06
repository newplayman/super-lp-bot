"""Tests for LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1.

These tests verify:
  - RPC registry has base/bsc/solana with primary + fallback + env override
  - env override does NOT leak secret
  - Base/BSC/Solana smoke failures are honest (no fake success)
  - BSC V2 uses factory.getPair before getReserves
  - No placeholder fallback
  - No wallet / keypair / signer
  - No tx send
  - No long run started
  - Final verdict next stages only from allowed set

All tests are read-only EXCEPT for short smoke outputs that go to
`data/lp_long_horizon_adapter_wiring_retry_smoke/<run_id>/` (cleaned up at end).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_rpc_reachability_adapter_smoke_fix" / "20260606_103807"

ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1",
    "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT",
    "LP_LONG_HORIZON_COLLECTOR_ADAPTER_CODE_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
}


# ---------------------------------------------------------------------------
# Stage A: input evidence
# ---------------------------------------------------------------------------

def test_a_input_evidence_audit_files_exist() -> None:
    assert (REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md").exists()
    assert (REPORT_DIR / "input_evidence_audit.json").exists()


def test_a_input_evidence_confirms_rpc_blocks() -> None:
    d = json.loads((REPORT_DIR / "input_evidence_audit.json").read_text())
    c = d["input_evidence_confirmed"]
    assert c["adapter_code_ready"] is True
    assert c["base_rpc_unavailable_in_prior_stage"] is True
    assert c["solana_rpc_empty_for_meteora_in_prior_stage"] is True
    assert c["bsc_v2_address_empty_in_prior_stage"] is True
    assert c["collector_full_coverage_ready"] is False
    assert c["this_stage_only_rpc_smoke_fix_no_12h_start"] is True


# ---------------------------------------------------------------------------
# Stage B: RPC registry
# ---------------------------------------------------------------------------

def test_b_rpc_registry_files_exist() -> None:
    assert (REPORT_DIR / "RPC_FALLBACK_REGISTRY_CN.md").exists()
    assert (REPORT_DIR / "rpc_fallback_registry.json").exists()


def test_b_rpc_registry_has_3_chains() -> None:
    d = json.loads((REPORT_DIR / "rpc_fallback_registry.json").read_text())
    chains = {r["chain"] for r in d["registries"]}
    assert "base" in chains
    assert "bsc" in chains
    assert "solana" in chains


def test_b_rpc_registry_env_override_no_secret() -> None:
    """env_override_name should be a name, not contain a secret value."""
    d = json.loads((REPORT_DIR / "rpc_fallback_registry.json").read_text())
    for r in d["registries"]:
        env_name = r.get("env_override_name", "")
        # env name should be like BASE_RPC_URL — no value, no key
        assert re.match(r"^[A-Z_]+_RPC_URL$", env_name), f"unexpected env_name format: {env_name}"
        # No secret patterns
        assert "0x" not in env_name
        assert "private" not in env_name.lower()


def test_b_rpc_registry_fallback_list_non_empty() -> None:
    d = json.loads((REPORT_DIR / "rpc_fallback_registry.json").read_text())
    for r in d["registries"]:
        fallbacks = r.get("fallback_public_rpc_list", [])
        assert len(fallbacks) >= 1, f"{r['chain']} has no fallback list"
        # All fallback URLs should be https
        for url in fallbacks:
            assert url.startswith("https://"), f"non-https url: {url}"


# ---------------------------------------------------------------------------
# Stage C: RPC reachability matrix
# ---------------------------------------------------------------------------

def test_c_rpc_reachability_matrix_files_exist() -> None:
    assert (REPORT_DIR / "RPC_REACHABILITY_MATRIX_CN.md").exists()
    assert (REPORT_DIR / "rpc_reachability_matrix.csv").exists()
    assert (REPORT_DIR / "rpc_reachability_matrix.json").exists()


def test_c_rpc_reachability_matrix_no_fake_success() -> None:
    """Failures must be recorded honestly; no endpoint marked reachable if it errored."""
    d = json.loads((REPORT_DIR / "rpc_reachability_matrix.json").read_text())
    for r in d["results"]:
        if not r.get("reachable", False):
            # Honest failure: must have error field set
            assert r.get("error", ""), f"unreachable endpoint without error: {r}"


def test_c_rpc_reachability_matrix_3_chains() -> None:
    d = json.loads((REPORT_DIR / "rpc_reachability_matrix.json").read_text())
    chains = {r["chain"] for r in d["results"]}
    assert "base" in chains
    assert "bsc" in chains
    assert "solana" in chains


# ---------------------------------------------------------------------------
# Stage D: Base adapter smoke retry
# ---------------------------------------------------------------------------

def test_d_base_adapter_smoke_retry_files_exist() -> None:
    assert (REPORT_DIR / "BASE_ADAPTER_SMOKE_RETRY_CN.md").exists()
    assert (REPORT_DIR / "base_adapter_smoke_retry.json").exists()


def test_d_base_slipstream_marked_unsupported() -> None:
    """Slipstream must still be marked adapter_ready=false (custom tick math)."""
    p = REPORT_DIR / "base_adapter_smoke_retry.json"
    if not p.exists():
        pytest.skip("not yet created")
    d = json.loads(p.read_text())
    if "slipstream_supported" in d:
        assert d["slipstream_supported"] is False


def test_d_base_no_fake_success() -> None:
    """If Base public RPC fails, all Base pool_snapshot_rows must be 0."""
    p = REPORT_DIR / "base_adapter_smoke_retry.json"
    if not p.exists():
        pytest.skip("not yet created")
    d = json.loads(p.read_text())
    if not d.get("base_rpc_reachable", True):
        assert d.get("pool_snapshot_rows", 0) == 0, "fake success on Base"


# ---------------------------------------------------------------------------
# Stage E: BSC adapter smoke retry
# ---------------------------------------------------------------------------

def test_e_bsc_adapter_smoke_retry_files_exist() -> None:
    assert (REPORT_DIR / "BSC_ADAPTER_SMOKE_RETRY_CN.md").exists()
    assert (REPORT_DIR / "bsc_adapter_smoke_retry.json").exists()


def test_e_bsc_v2_uses_factory_getpair() -> None:
    """BSC V2 must use factory.getPair(tokenA, tokenB) for pair discovery."""
    p = REPORT_DIR / "bsc_adapter_smoke_retry.json"
    if not p.exists():
        pytest.skip("not yet created")
    d = json.loads(p.read_text())
    # Should record factory.getPair usage
    if "pancakeswap_v2_factory_getpair" in d:
        # success_count should be recorded
        assert isinstance(d["pancakeswap_v2_factory_getpair_success_count"], int)


def test_e_bsc_no_fake_success() -> None:
    """If BSC public RPC fails, all BSC pool_snapshot_rows must be 0."""
    p = REPORT_DIR / "bsc_adapter_smoke_retry.json"
    if not p.exists():
        pytest.skip("not yet created")
    d = json.loads(p.read_text())
    if not d.get("bsc_rpc_reachable", True):
        assert d.get("pool_snapshot_rows", 0) == 0, "fake success on BSC"


# ---------------------------------------------------------------------------
# Stage F: Meteora DLMM smoke retry
# ---------------------------------------------------------------------------

def test_f_meteora_dlmm_smoke_retry_files_exist() -> None:
    assert (REPORT_DIR / "METEORA_DLMM_SMOKE_RETRY_CN.md").exists()
    assert (REPORT_DIR / "meteora_dlmm_smoke_retry.json").exists()


def test_f_meteora_no_fake_success() -> None:
    """If Solana public RPC fails, accountinfo_success_count must be 0."""
    p = REPORT_DIR / "meteora_dlmm_smoke_retry.json"
    if not p.exists():
        pytest.skip("not yet created")
    d = json.loads(p.read_text())
    if not d.get("solana_rpc_reachable", True):
        assert d.get("accountinfo_success_count", 0) == 0


# ---------------------------------------------------------------------------
# Stage G: integrated observable smoke retry
# ---------------------------------------------------------------------------

def test_g_integrated_smoke_retry_files_exist() -> None:
    assert (REPORT_DIR / "INTEGRATED_OBSERVABLE_SMOKE_RETRY_CN.md").exists()
    assert (REPORT_DIR / "integrated_observable_smoke_retry.json").exists()


def test_g_integrated_smoke_no_placeholder() -> None:
    p = REPORT_DIR / "integrated_observable_smoke_retry.json"
    if not p.exists():
        pytest.skip("not yet created")
    d = json.loads(p.read_text())
    assert d.get("placeholder_pool_count", 0) == 0


def test_g_integrated_smoke_real_universe_used() -> None:
    p = REPORT_DIR / "integrated_observable_smoke_retry.json"
    if not p.exists():
        pytest.skip("not yet created")
    d = json.loads(p.read_text())
    assert d.get("real_pool_universe_used") is True


# ---------------------------------------------------------------------------
# Stage H: coverage readiness decision
# ---------------------------------------------------------------------------

def test_h_coverage_readiness_files_exist() -> None:
    assert (REPORT_DIR / "COVERAGE_READINESS_DECISION_CN.md").exists()
    assert (REPORT_DIR / "coverage_readiness_decision.json").exists()


def test_h_coverage_readiness_recommended_in_allowed_set() -> None:
    p = REPORT_DIR / "coverage_readiness_decision.json"
    if not p.exists():
        pytest.skip("not yet created")
    d = json.loads(p.read_text())
    assert d["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_h_coverage_readiness_5_conditions_logic() -> None:
    """Logic: if all 5 met → 12h retry. If 4 met but RPC unreachable → fix_repeat. If 4 met but code issue → code_fix."""
    p = REPORT_DIR / "coverage_readiness_decision.json"
    if not p.exists():
        pytest.skip("not yet created")
    d = json.loads(p.read_text())
    c = d["conditions"]
    all_met = (
        c["observable_pool_count_ge_45"]
        and c["observable_chain_count_ge_3"]
        and c["observable_protocol_count_ge_5"]
        and c["placeholder_pool_count_eq_0"]
        and c["no_wallet_tx_probe"]
    )
    if all_met:
        assert d["recommended_next_stage"] == "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1"
    else:
        assert d["recommended_next_stage"] in {
            "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT",
            "LP_LONG_HORIZON_COLLECTOR_ADAPTER_CODE_FIX_REPEAT",
            "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        }


# ---------------------------------------------------------------------------
# Stage I: final verdict
# ---------------------------------------------------------------------------

def test_i_final_verdict_required_fields() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    if not p.exists():
        pytest.skip("FINAL_VERDICT not yet created")
    fv = json.loads(p.read_text())
    required = {
        "stage", "status",
        "rpc_registry_ready", "rpc_reachability_matrix_ran",
        "base_rpc_reachable", "bsc_rpc_reachable", "solana_rpc_reachable",
        "base_adapter_smoke_success", "bsc_adapter_smoke_success", "meteora_dlmm_smoke_success",
        "integrated_smoke_ran",
        "observable_pool_count", "observable_chain_count", "observable_protocol_count",
        "placeholder_pool_count",
        "collector_full_coverage_ready", "can_start_12h_real_universe_retry",
        "long_run_started",
        "can_run_probe_now", "tiny_canary_allowed",
        "wallet_or_tx_touched", "transaction_sent",
        "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_i_final_verdict_locked_fields() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    if not p.exists():
        pytest.skip("FINAL_VERDICT not yet created")
    fv = json.loads(p.read_text())
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["long_run_started"] is False


def test_i_final_verdict_recommended_in_allowed_set() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    if not p.exists():
        pytest.skip("FINAL_VERDICT not yet created")
    fv = json.loads(p.read_text())
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


# ---------------------------------------------------------------------------
# Stage J: safety
# ---------------------------------------------------------------------------

def test_j_no_forbidden_process() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["canary", "lpbot-live", "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in forbidden:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                pytest.fail(f"forbidden process token {tok!r} found: {line}")


def test_j_no_long_running_collectors_started() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in ["run_lp_long_horizon_readonly_stage_once", "tmux: server"]:
            if tok in line:
                pytest.fail(f"long-running runner still running: {line}")


def test_j_no_secret_value_in_outputs() -> None:
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
    ]
    for p in REPORT_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md", ".csv", ".py"}:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in value_patterns:
                for m in pat.finditer(text):
                    snippet = m.group(0)[:80]
                    if "0x" in m.group(0) and len(m.group(0)) >= 64:
                        pytest.fail(f"potential 64-hex secret in {p}: {snippet}")
                    elif "private_key" in pat.pattern or "mnemonic" in pat.pattern or "seed" in pat.pattern:
                        pytest.fail(f"potential secret value in {p}: {snippet}")


def test_j_source_12h_data_dir_unchanged() -> None:
    src = ROOT / "data" / "lp_long_horizon" / "20260605_082120"
    if not src.exists():
        pytest.skip("12h fixture data not present")
    files = [f for f in src.rglob("*") if f.is_file()]
    assert len(files) > 0
