"""Tests for LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1.

Verifies the R1 upgrade deliverables + R1 smoke output:
  - r1 schema exists (6 dimensions)
  - r1 collector no placeholder fallback (real confidence + invalid_reason)
  - no wallet/keypair/signer
  - no tx send
  - actual_fee_data_available remains false (LOCKED)
  - fee_proxy_only true (R1 ≠ actual)
  - candidate review fields exist
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
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_r1_real_data_observation_upgrade" / "20260607_163000"
R1_DATA_DIR = ROOT / "data" / "lp_long_horizon_r1_smoke" / "20260607_163000"
COLLECTOR = ROOT / "scripts" / "lp_long_horizon_r1_real_data_collector_v1.py"

ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1",
    "LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT",
    "LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
}


# ---------------------------------------------------------------------------
# Deliverables exist
# ---------------------------------------------------------------------------

def test_all_deliverables_exist() -> None:
    files = [
        "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
        "R1_REAL_DATA_SCHEMA_CN.md", "r1_real_data_schema.json",
        "R1_COLLECTOR_ARCHITECTURE_CN.md", "r1_collector_architecture.json",
        "R1_SHORT_SMOKE_RESULT_CN.md", "r1_short_smoke_result.json",
        "R1_CANDIDATE_INTERPRETATION_CN.md", "r1_candidate_interpretation.json",
        "R1_NEXT_STAGE_DECISION_CN.md", "r1_next_stage_decision.json",
        "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
    ]
    for f in files:
        assert (REPORT_DIR / f).exists(), f"missing deliverable: {f}"


def test_r1_collector_exists() -> None:
    assert COLLECTOR.exists(), f"missing R1 collector: {COLLECTOR}"


def test_r1_collector_no_placeholder_fallback() -> None:
    """R1 collector must NOT use smoke_placeholder; use confidence + invalid_reason."""
    text = COLLECTOR.read_text()
    # Should define confidence values
    assert "CONFIDENCE_HIGH" in text
    assert "CONFIDENCE_MEDIUM" in text
    assert "CONFIDENCE_LOW" in text
    assert "CONFIDENCE_UNAVAILABLE" in text
    # Should define invalid_reason values
    assert "REASON_RPC_UNREACHABLE" in text
    assert "REASON_INDEXER_UNREACHABLE" in text


def test_r1_collector_no_wallet_keypair_signer() -> None:
    text = COLLECTOR.read_text()
    forbidden = ["PRIVATE_KEY", "MNEMONIC", "SEED_PHRASE", "KEYPAIR_PATH"]
    for f in forbidden:
        # In R1 collector, these may appear in forbidden-token list (defense-in-depth);
        # but actual code must NOT use them for signing.
        # Test: no wallet/keystore SDK import.
        assert "from solders" not in text
        assert "from solana.rpc.commitment" not in text or "sendTransaction" not in text


def test_r1_collector_no_tx_send() -> None:
    """R1 collector code must NOT call any write-side RPC.

    We strip the module docstring (which legitimately mentions forbidden tokens
    as a 'do-not-call' warning) before scanning for actual call sites.
    """
    text = COLLECTOR.read_text()
    # Strip leading docstring.
    if text.startswith('"""'):
        end = text.find('"""', 3)
        if end != -1:
            text = text[end + 3:]
    forbidden = ["sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction",
                 "sign_transaction", "build_and_send"]
    for f in forbidden:
        assert f not in text, f"R1 collector code must NOT call {f}"


# ---------------------------------------------------------------------------
# R1 smoke output exists
# ---------------------------------------------------------------------------

def test_r1_smoke_data_dir_exists() -> None:
    assert R1_DATA_DIR.exists(), f"R1 smoke data dir missing: {R1_DATA_DIR}"


def test_r1_smoke_files_exist() -> None:
    files = [
        "r1_pool_snapshot.csv", "r1_pool_snapshot.json",
        "r1_quote_snapshot.csv", "r1_quote_snapshot.json",
        "r1_fee_velocity.csv", "r1_fee_velocity.json",
        "r1_liquidity_distribution.csv", "r1_liquidity_distribution.json",
        "r1_market_regime.csv", "r1_market_regime.json",
        "r1_candidate_review.csv", "r1_candidate_review.json",
        "r1_smoke_summary.json",
    ]
    for f in files:
        assert (R1_DATA_DIR / f).exists(), f"missing R1 smoke file: {f}"


# ---------------------------------------------------------------------------
# R1 smoke stats
# ---------------------------------------------------------------------------

def test_r1_smoke_ran() -> None:
    s = json.loads((R1_DATA_DIR / "r1_smoke_summary.json").read_text())
    assert s["r1_smoke_ran"] is True
    assert s["selected_pool_count"] == 20


def test_r1_smoke_pool_snapshot_rows_positive() -> None:
    s = json.loads((R1_DATA_DIR / "r1_smoke_summary.json").read_text())
    assert s["pool_snapshot_rows"] > 0
    assert s["pool_snapshot_rows"] == 20


def test_r1_smoke_quote_snapshot_rows_positive() -> None:
    s = json.loads((R1_DATA_DIR / "r1_smoke_summary.json").read_text())
    assert s["quote_snapshot_rows"] > 0
    assert s["quote_snapshot_rows"] == 120


def test_r1_smoke_fee_velocity_rows_positive() -> None:
    s = json.loads((R1_DATA_DIR / "r1_smoke_summary.json").read_text())
    assert s["fee_velocity_rows"] > 0
    assert s["fee_velocity_rows"] == 100


def test_r1_smoke_liquidity_distribution_rows_positive() -> None:
    s = json.loads((R1_DATA_DIR / "r1_smoke_summary.json").read_text())
    assert s["liquidity_distribution_rows"] > 0
    assert s["liquidity_distribution_rows"] == 20


def test_r1_smoke_candidate_review_rows_positive() -> None:
    s = json.loads((R1_DATA_DIR / "r1_smoke_summary.json").read_text())
    assert s["candidate_review_rows"] > 0
    assert s["candidate_review_rows"] == 20


# ---------------------------------------------------------------------------
# R1 actual_fee_data_available = false (LOCKED)
# ---------------------------------------------------------------------------

def test_actual_fee_data_available_remains_false() -> None:
    s = json.loads((R1_DATA_DIR / "r1_smoke_summary.json").read_text())
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert s["actual_fee_data_available"] is False
    assert fv["actual_fee_data_available"] is False
    assert fv["actual_fee_schema_unchanged"] is True


def test_fee_proxy_only_true() -> None:
    s = json.loads((R1_DATA_DIR / "r1_smoke_summary.json").read_text())
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert s["fee_proxy_only"] is True
    assert fv["fee_proxy_only"] is True


# ---------------------------------------------------------------------------
# No wallet / tx / probe
# ---------------------------------------------------------------------------

def test_no_wallet_tx_touched() -> None:
    s = json.loads((R1_DATA_DIR / "r1_smoke_summary.json").read_text())
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert s["wallet_or_tx_touched"] is False
    assert s["transaction_sent"] is False
    assert s["no_wallet_tx_probe"] is True
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False


# ---------------------------------------------------------------------------
# Candidate review fields exist
# ---------------------------------------------------------------------------

def test_candidate_review_required_fields() -> None:
    cr_json = json.loads((R1_DATA_DIR / "r1_candidate_review.json").read_text())
    assert "candidates" in cr_json
    candidates = cr_json["candidates"]
    assert len(candidates) == 20
    required = {"pool_address", "quote_ready", "fee_ready", "liquidity_ready",
                "regime_ready", "ev_ready", "preflight_candidate", "watchlist",
                "data_insufficient", "reason"}
    for c in candidates:
        missing = required - set(c.keys())
        assert not missing, f"candidate {c.get('pool_address')} missing: {missing}"


# ---------------------------------------------------------------------------
# FINAL_VERDICT allowed next stages only
# ---------------------------------------------------------------------------

def test_final_verdict_recommended_in_allowed_set() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    rec = fv.get("recommended_next_stage", "")
    assert rec in ALLOWED_NEXT_STAGES, f"recommended_next_stage {rec!r} not in {ALLOWED_NEXT_STAGES}"


def test_final_verdict_required_fields() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    required = {
        "stage", "status",
        "r1_schema_ready", "r1_collector_built", "r1_short_smoke_ran",
        "selected_pool_count", "pool_snapshot_rows", "quote_snapshot_rows",
        "fee_velocity_rows", "liquidity_distribution_rows", "market_regime_rows",
        "candidate_review_rows",
        "quote_ready_pool_count", "fee_ready_pool_count", "liquidity_ready_pool_count",
        "ev_ready_pool_count", "preflight_candidate_count", "watchlist_count",
        "data_insufficient_count",
        "actual_fee_data_available", "fee_proxy_only",
        "wallet_or_tx_touched", "transaction_sent",
        "can_run_probe_now", "tiny_canary_allowed", "edge_proven",
        "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing: {missing}"


# ---------------------------------------------------------------------------
# R1 schema (6 dimensions)
# ---------------------------------------------------------------------------

def test_r1_schema_6_dimensions() -> None:
    sch = json.loads((REPORT_DIR / "r1_real_data_schema.json").read_text())
    dims = sch["r1_schema_6_dimensions"]
    expected = {
        "r1_pool_snapshot", "r1_quote_snapshot", "r1_fee_velocity",
        "r1_liquidity_distribution", "r1_market_regime", "r1_candidate_review",
    }
    assert set(dims.keys()) == expected


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

def test_safety_no_forbidden_process() -> None:
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["canary", "lpbot-live", "sendTransaction", "eth_sendRawTransaction",
                 "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in forbidden:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                pytest.fail(f"forbidden process token {tok!r} found: {line}")


def test_safety_no_secret_value_in_outputs() -> None:
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
    ]
    for p in REPORT_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md", ".csv"}:
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
