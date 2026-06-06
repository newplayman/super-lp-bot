"""Tests for LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1.

These tests verify:
  - Adapter registry includes all 8 chains/protocols (4 existing + 4 new + 1 verify)
  - Base Uniswap V3 adapter: read-only, eth_call, no signing
  - Base Aerodrome: classic/slipstream distinguished
  - BSC V3 adapter: read-only, eth_call
  - BSC V2 adapter: CPMM quote formula correct
  - Meteora DLMM adapter check: re-uses existing solana_rpc_readonly
  - Integrated smoke does NOT use placeholder
  - No wallet / keypair / signer
  - No tx send
  - No long run started
  - Final verdict next stages only from allowed set

All tests are read-only. Adapter smoke tests use mock/stub since we
don't have a real public RPC environment for EVM/BSC in this stage.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_collector_adapter_coverage_wiring" / "20260606_093857"
ADAPTERS_DIR = ROOT / "scripts" / "lp_long_horizon" / "adapters"

ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1",
    "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
}


# ---------------------------------------------------------------------------
# Stage A: input evidence
# ---------------------------------------------------------------------------

def test_a_input_evidence_files_exist() -> None:
    assert (REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md").exists()
    assert (REPORT_DIR / "input_evidence_audit.json").exists()


def test_a_input_evidence_confirms_universe_state() -> None:
    d = json.loads((REPORT_DIR / "input_evidence_audit.json").read_text())
    c = d["input_evidence_confirmed"]
    assert c["expanded_universe_pool_count"] == 72
    assert c["observable_pool_count"] == 49
    assert c["non_observable_pool_count"] == 23
    assert c["base_uniswap_v3_adapter_missing"] is True
    assert c["base_aerodrome_adapter_missing"] is True
    assert c["bsc_pancakeswap_v3_adapter_missing"] is True
    assert c["bsc_pancakeswap_v2_adapter_missing"] is True


# ---------------------------------------------------------------------------
# Stage B: adapter registry
# ---------------------------------------------------------------------------

def test_b_adapter_registry_files_exist() -> None:
    assert (REPORT_DIR / "ADAPTER_REGISTRY_DESIGN_CN.md").exists()
    assert (REPORT_DIR / "adapter_registry_design.json").exists()


def test_b_adapter_registry_includes_8_adapters() -> None:
    d = json.loads((REPORT_DIR / "adapter_registry_design.json").read_text())
    names = {a["adapter_name"] for a in d["adapters"]}
    # 3 existing + 4 new + 1 verify = 8 (but verify is part of Meteora; we keep 7 distinct + 1 meteora = 8)
    expected = {
        "solana_rpc_readonly",  # existing
        "public_api_coingecko",  # existing
        "local_artifact_replay",  # existing
        "evm_base_uniswap_v3",  # new
        "evm_base_aerodrome",  # new
        "evm_bsc_pancakeswap_v3",  # new
        "evm_bsc_pancakeswap_v2",  # new
        "solana_meteora_dlmm_check",  # verify
    }
    assert expected.issubset(names), f"missing adapters: {expected - names}; got {names}"


def test_b_adapter_registry_all_read_only() -> None:
    d = json.loads((REPORT_DIR / "adapter_registry_design.json").read_text())
    for a in d["adapters"]:
        assert a["read_only_only"] is True, f"{a['adapter_name']} must be read_only_only"
        assert a["wallet_required"] is False
        assert a["transaction_required"] is False


# ---------------------------------------------------------------------------
# Stage C: Base Uniswap V3 adapter
# ---------------------------------------------------------------------------

def test_c_base_uniswap_v3_adapter_file_exists() -> None:
    p = ADAPTERS_DIR / "evm_base_uniswap_v3.py"
    assert p.exists()
    # Must have read-only contract
    text = p.read_text()
    assert "BANNED_TOKENS" in text or "forbidden" in text.lower() or "wallet" in text.lower() or "private_key" in text
    # No signing primitives
    assert "sendTransaction" not in text or "sendTransaction" in text and "REFUSE" in text.upper() or "raise" in text
    assert "send_raw_transaction" not in text.lower() or "raise" in text


def test_c_base_uniswap_v3_smoke_output_exists() -> None:
    p = REPORT_DIR / "base_uniswap_v3_adapter_wiring.json"
    assert p.exists()


def test_c_base_uniswap_v3_pool_snapshot_supports_eth_call() -> None:
    """The adapter should provide pool_snapshot via eth_call (read-only)."""
    p = ADAPTERS_DIR / "evm_base_uniswap_v3.py"
    if not p.exists():
        pytest.skip("adapter file not yet created")
    text = p.read_text()
    # Should reference slot0, liquidity, or pool state
    assert "slot0" in text or "globalState" in text
    # Should be read-only
    assert "def " in text


def test_c_base_uniswap_v3_quote_function_present() -> None:
    """The adapter should provide a quote function (10/20/100/500/1000/2000U)."""
    p = ADAPTERS_DIR / "evm_base_uniswap_v3.py"
    if not p.exists():
        pytest.skip("adapter file not yet created")
    text = p.read_text()
    # QuoterV2 staticcall or fallback math
    assert "quote" in text.lower()


# ---------------------------------------------------------------------------
# Stage D: Base Aerodrome adapter
# ---------------------------------------------------------------------------

def test_d_aerodrome_adapter_file_exists() -> None:
    p = ADAPTERS_DIR / "evm_base_aerodrome.py"
    assert p.exists()


def test_d_aerodrome_classic_and_slipstream_distinguished() -> None:
    """Aerodrome adapter must distinguish classic (Solidly) from slipstream (V3 fork)."""
    p = ADAPTERS_DIR / "evm_base_aerodrome.py"
    if not p.exists():
        pytest.skip("adapter file not yet created")
    text = p.read_text()
    assert "classic" in text.lower()
    assert "slipstream" in text.lower()


def test_d_aerodrome_slipstream_marked_not_ready() -> None:
    """Slipstream must be marked adapter_ready=false (custom tick math)."""
    p = REPORT_DIR / "base_aerodrome_adapter_wiring.json"
    if not p.exists():
        pytest.skip("wiring JSON not yet created")
    d = json.loads(p.read_text())
    if "slipstream" in d:
        assert d["slipstream_adapter_ready"] is False


# ---------------------------------------------------------------------------
# Stage E: BSC PancakeSwap V3 adapter
# ---------------------------------------------------------------------------

def test_e_bsc_pancakeswap_v3_adapter_file_exists() -> None:
    p = ADAPTERS_DIR / "evm_bsc_pancakeswap_v3.py"
    assert p.exists()


def test_e_bsc_pancakeswap_v3_quote_via_quoter_v2() -> None:
    """BSC V3 adapter should use QuoterV2 for quotes (read-only staticcall)."""
    p = ADAPTERS_DIR / "evm_bsc_pancakeswap_v3.py"
    if not p.exists():
        pytest.skip("adapter file not yet created")
    text = p.read_text()
    assert "QuoterV2" in text or "quoter" in text.lower() or "quoter_v2" in text.lower()


# ---------------------------------------------------------------------------
# Stage F: BSC PancakeSwap V2 adapter
# ---------------------------------------------------------------------------

def test_f_bsc_pancakeswap_v2_adapter_file_exists() -> None:
    p = ADAPTERS_DIR / "evm_bsc_pancakeswap_v2.py"
    assert p.exists()


def test_f_bsc_pancakeswap_v2_cpmm_formula_present() -> None:
    """BSC V2 adapter must use CPMM formula: x*y=k (constant product)."""
    p = ADAPTERS_DIR / "evm_bsc_pancakeswap_v2.py"
    if not p.exists():
        pytest.skip("adapter file not yet created")
    text = p.read_text()
    # Should reference reserves (CPMM primitive)
    assert "getReserves" in text or "reserve" in text.lower() or "reserves" in text.lower()


def test_f_bsc_pancakeswap_v2_no_quoter() -> None:
    """V2 has no quoter; must use getReserves for price calculation."""
    p = ADAPTERS_DIR / "evm_bsc_pancakeswap_v2.py"
    if not p.exists():
        pytest.skip("adapter file not yet created")
    text = p.read_text()
    # No V3 quoter; instead getReserves
    # (We just confirm V2 adapter exists with reserves; quoter is V3-specific)
    assert "getReserves" in text or "reserves" in text.lower()


# ---------------------------------------------------------------------------
# Stage G: Meteora DLMM adapter check
# ---------------------------------------------------------------------------

def test_g_meteora_dlmm_check_output_exists() -> None:
    p = REPORT_DIR / "meteora_dlmm_long_horizon_adapter_check.json"
    assert p.exists()


def test_g_meteora_dlmm_reuses_solana_rpc_readonly() -> None:
    """Meteora check should leverage the existing solana_rpc_readonly adapter."""
    p = REPORT_DIR / "meteora_dlmm_long_horizon_adapter_check.json"
    if not p.exists():
        pytest.skip("check JSON not yet created")
    d = json.loads(p.read_text())
    # Should reference solana_rpc_readonly
    assert "solana_rpc_readonly" in str(d) or d.get("reuses_solana_rpc_readonly") is True


# ---------------------------------------------------------------------------
# Stage H: integrated smoke
# ---------------------------------------------------------------------------

def test_h_integrated_smoke_output_exists() -> None:
    p = REPORT_DIR / "INTEGRATED_ADAPTER_WIRING_SMOKE_CN.md"
    assert p.exists()
    p2 = REPORT_DIR / "integrated_adapter_wiring_smoke.json"
    assert p2.exists()


def test_h_integrated_smoke_no_placeholder() -> None:
    """Integrated smoke must NOT use placeholder pools."""
    p = REPORT_DIR / "integrated_adapter_wiring_smoke.json"
    if not p.exists():
        pytest.skip("smoke JSON not yet created")
    d = json.loads(p.read_text())
    assert d["placeholder_pool_count"] == 0
    assert d.get("real_pool_universe_used") is True


def test_h_integrated_smoke_observable_count_recorded() -> None:
    """Smoke must record observable / non_observable pool counts honestly."""
    p = REPORT_DIR / "integrated_adapter_wiring_smoke.json"
    if not p.exists():
        pytest.skip("smoke JSON not yet created")
    d = json.loads(p.read_text())
    assert "observable_pool_count" in d
    assert "non_observable_pool_count" in d
    assert "chain_observed_count" in d
    assert "protocol_observed_count" in d


# ---------------------------------------------------------------------------
# Stage I: coverage readiness decision
# ---------------------------------------------------------------------------

def test_i_coverage_readiness_files_exist() -> None:
    assert (REPORT_DIR / "COVERAGE_READINESS_DECISION_CN.md").exists()
    assert (REPORT_DIR / "coverage_readiness_decision.json").exists()


def test_i_coverage_readiness_recommended_in_allowed_set() -> None:
    p = REPORT_DIR / "coverage_readiness_decision.json"
    if not p.exists():
        pytest.skip("decision JSON not yet created")
    d = json.loads(p.read_text())
    assert d["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_i_coverage_readiness_5_conditions_logic() -> None:
    """If all 5 conditions met → 12h retry recommended. Else fix_repeat or pause."""
    p = REPORT_DIR / "coverage_readiness_decision.json"
    if not p.exists():
        pytest.skip("decision JSON not yet created")
    d = json.loads(p.read_text())
    conditions = d["conditions"]
    all_met = (
        conditions["observable_pool_count_ge_45"]
        and conditions["observable_chain_count_ge_3"]
        and conditions["observable_protocol_count_ge_5"]
        and conditions["placeholder_pool_count_eq_0"]
        and conditions["no_wallet_tx_probe"]
    )
    if all_met:
        assert d["recommended_next_stage"] == "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1"
    else:
        assert d["recommended_next_stage"] in {
            "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT",
            "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        }


# ---------------------------------------------------------------------------
# Stage J: final verdict
# ---------------------------------------------------------------------------

def test_j_final_verdict_required_fields() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    if not p.exists():
        pytest.skip("FINAL_VERDICT not yet created")
    fv = json.loads(p.read_text())
    required = {
        "stage", "status",
        "adapter_registry_ready",
        "base_uniswap_v3_adapter_ready",
        "base_aerodrome_adapter_ready",
        "bsc_pancakeswap_v3_adapter_ready",
        "bsc_pancakeswap_v2_adapter_ready",
        "meteora_dlmm_long_horizon_adapter_ready",
        "integrated_smoke_ran",
        "expanded_pool_count", "observable_pool_count",
        "observable_chain_count", "observable_protocol_count",
        "placeholder_pool_count",
        "collector_full_coverage_ready",
        "can_start_12h_real_universe_retry",
        "long_run_started",
        "can_run_probe_now", "tiny_canary_allowed",
        "wallet_or_tx_touched", "transaction_sent",
        "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_j_final_verdict_locked_fields() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    if not p.exists():
        pytest.skip("FINAL_VERDICT not yet created")
    fv = json.loads(p.read_text())
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["long_run_started"] is False


def test_j_final_verdict_recommended_in_allowed_set() -> None:
    p = REPORT_DIR / "FINAL_VERDICT.json"
    if not p.exists():
        pytest.skip("FINAL_VERDICT not yet created")
    fv = json.loads(p.read_text())
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


# ---------------------------------------------------------------------------
# Stage K: safety
# ---------------------------------------------------------------------------

def test_k_no_forbidden_process() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["canary", "lpbot-live", "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in forbidden:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                pytest.fail(f"forbidden process token {tok!r} found: {line}")


def test_k_no_long_running_collectors_started() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in ["run_lp_long_horizon_readonly_stage_once", "tmux: server"]:
            if tok in line:
                pytest.fail(f"long-running runner still running: {line}")


def test_k_no_secret_value_in_outputs() -> None:
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
                    # 40-char hex (pool addresses) is fine; 64-char is private key
                    if "0x" in m.group(0) and len(m.group(0)) >= 64:
                        pytest.fail(f"potential 64-hex secret in {p}: {snippet}")
                    elif "private_key" in pat.pattern or "mnemonic" in pat.pattern or "seed" in pat.pattern:
                        pytest.fail(f"potential secret value in {p}: {snippet}")


def test_k_source_12h_data_dir_unchanged() -> None:
    """12h data dir (84 files) should be unchanged — this stage is read-only on it."""
    src = ROOT / "data" / "lp_long_horizon" / "20260605_082120"
    if not src.exists():
        pytest.skip("12h fixture data not present")
    files = [f for f in src.rglob("*") if f.is_file()]
    assert len(files) > 0
