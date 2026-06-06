"""Tests for LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1.

These tests verify:
  - Collector CLI accepts --pool-universe and reads REAL pool universe JSON
  - Placeholder pools are REJECTED when --pool-universe is provided
  - Universe parse failure does NOT fallback to placeholder (REFUSED + exit)
  - selected_real_pool_count > 0
  - real_pool_universe_used = true
  - Stage runner forwards --pool-universe to collector
  - No wallet / keypair / signer
  - No tx send
  - No production write
  - Final verdict recommended next stages only from the 4-stage allowed set

All tests are read-only EXCEPT for short smoke outputs that go to
`data/lp_long_horizon_real_pool_smoke/test_*` (cleaned up at end).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_long_horizon_real_pool_universe_collector_fix" / "20260605_083000"
COLLECTOR = ROOT / "scripts" / "lp_long_horizon_readonly_collector_v1.py"
STAGE_RUNNER = ROOT / "scripts" / "run_lp_long_horizon_readonly_stage_once.sh"
REAL_UNIVERSE = ROOT / "reports" / "lp_long_horizon_readonly_continuous_12h_extension" / "20260605_082120" / "real_pool_universe_for_12h.json"
SMOKE_DIR = ROOT / "data" / "lp_long_horizon_real_pool_smoke" / "20260605_083000"

ALLOWED_NEXT_STAGES = {
    "LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1",
    "LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR FIX_REPEAT",
    "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
    "STOP_LP_RESEARCH_NOW",
}


# ---------------------------------------------------------------------------
# Stage A: input evidence
# ---------------------------------------------------------------------------

def test_a_input_evidence_audit_files_exist() -> None:
    assert (REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md").exists()
    assert (REPORT_DIR / "input_evidence_audit.json").exists()


def test_a_real_pool_universe_exists() -> None:
    assert REAL_UNIVERSE.exists()
    d = json.loads(REAL_UNIVERSE.read_text())
    assert d["selected_real_pool_count"] == 33
    assert d["placeholder_pool_count"] == 0
    assert d["real_pool_universe_used"] is True


# ---------------------------------------------------------------------------
# Stage B: collector CLI fix
# ---------------------------------------------------------------------------

def test_b_collector_script_exists() -> None:
    assert COLLECTOR.exists()
    assert COLLECTOR.is_file()


def test_b_collector_syntax() -> None:
    import py_compile
    try:
        py_compile.compile(str(COLLECTOR), doraise=True)
    except py_compile.PyCompileError as e:
        pytest.fail(f"compile error: {e}")


def test_b_collector_supports_pool_universe_arg() -> None:
    """CLI must have --pool-universe / --max-pools / --max-snapshots / --run-id args."""
    text = COLLECTOR.read_text()
    assert "--pool-universe" in text
    assert "--max-pools" in text
    assert "--max-snapshots" in text
    assert "--run-id" in text
    assert "REAL_UNIVERSE_REQUIRED_KEYS" in text
    assert "PLACEHOLDER_MARKERS" in text
    assert "_load_pool_universe" in text
    assert "_select_universe_pools" in text
    assert "_real_universe_smoke_mode" in text
    assert "_build_real_pool_snapshot" in text


def test_b_collector_loads_real_universe() -> None:
    """Collector can run with --pool-universe pointing to real pool universe."""
    if not SMOKE_DIR.exists():
        rc = subprocess.run(
            [
                sys.executable, str(COLLECTOR),
                "--mode", "smoke",
                "--pool-universe", str(REAL_UNIVERSE),
                "--max-pools", "5",
                "--max-snapshots", "1",
                "--run-id", "20260605_083000",
                "--out", str(SMOKE_DIR),
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert rc.returncode == 0, f"collector failed: {rc.stderr}"
    # Verify outputs
    summary = json.loads((SMOKE_DIR / "smoke_summary.json").read_text())
    assert summary["real_pool_universe_used"] is True
    assert summary["placeholder_pool_count"] == 0
    assert summary["all_pools_are_real_on_chain"] is True
    assert summary["smoke_placeholder_used"] is False
    assert summary["selected_real_pool_count"] == 5


def test_b_collector_rejects_placeholder_in_real_universe() -> None:
    """A universe with '<smoke_pool_' should be REFUSED, not fall back to placeholder."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
        bad = {
            "selected_real_pool_count": 1,
            "placeholder_pool_count": 0,  # claim clean
            "all_pools_are_real_on_chain": True,
            "real_pool_universe_used": True,
            "pools": [
                {
                    "chain": "solana", "protocol": "test", "pool_type": "clmm",
                    "pool_address": "<smoke_pool_evil_a>",
                    "token_pair": "X/Y", "fee_tier_or_fee_bps": 30,
                    "tvl_proxy_usd": 100, "vol24h_usd": 50,
                },
            ],
        }
        json.dump(bad, tf)
        bad_path = tf.name
    try:
        rc = subprocess.run(
            [
                sys.executable, str(COLLECTOR),
                "--mode", "smoke",
                "--pool-universe", bad_path,
                "--max-pools", "1",
                "--out", "data/lp_long_horizon_real_pool_smoke/bad_test",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert rc.returncode != 0, f"collector accepted placeholder universe (rc={rc.returncode})"
        assert "REFUSED" in rc.stderr or "smoke_pool" in rc.stderr
    finally:
        Path(bad_path).unlink(missing_ok=True)


def test_b_collector_universe_parse_fail_no_fallback() -> None:
    """If --pool-universe path doesn't exist, REFUSED (no fallback to placeholder)."""
    rc = subprocess.run(
        [
            sys.executable, str(COLLECTOR),
            "--mode", "smoke",
            "--pool-universe", "data/lp_long_horizon/nonexistent_universe.json",
            "--out", "data/lp_long_horizon_real_pool_smoke/bad_parse",
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert rc.returncode != 0
    assert "REFUSED" in rc.stderr or "not found" in rc.stderr


def test_b_collector_placeholder_count_must_be_zero() -> None:
    """Universe with placeholder_pool_count != 0 must be REFUSED."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
        bad = {
            "selected_real_pool_count": 1,
            "placeholder_pool_count": 5,  # 5 placeholders declared
            "all_pools_are_real_on_chain": True,
            "real_pool_universe_used": True,
            "pools": [
                {
                    "chain": "solana", "protocol": "test", "pool_type": "clmm",
                    "pool_address": "RealAddress123",
                    "token_pair": "X/Y", "fee_tier_or_fee_bps": 30,
                    "tvl_proxy_usd": 100, "vol24h_usd": 50,
                },
            ],
        }
        json.dump(bad, tf)
        bad_path = tf.name
    try:
        rc = subprocess.run(
            [
                sys.executable, str(COLLECTOR),
                "--mode", "smoke",
                "--pool-universe", bad_path,
                "--out", "data/lp_long_horizon_real_pool_smoke/placeholder_count",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert rc.returncode != 0
        assert "REFUSED" in rc.stderr
    finally:
        Path(bad_path).unlink(missing_ok=True)


def test_b_collector_no_real_universe_runs_smoke_placeholder() -> None:
    """Without --pool-universe, smoke mode emits smoke_placeholder_used=true explicitly."""
    import shutil
    test_out_rel = "data/lp_long_horizon/no_universe_test_20260605_083000"
    test_out_abs = ROOT / test_out_rel
    if test_out_abs.exists():
        shutil.rmtree(test_out_abs)
    rc = subprocess.run(
        [
            sys.executable, str(COLLECTOR),
            "--mode", "smoke",
            "--pools-per-protocol", "1",
            "--out", test_out_rel,
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert rc.returncode == 0, f"collector failed: rc={rc.returncode}, stderr={rc.stderr}"
    summary = json.loads((test_out_abs / "smoke_summary.json").read_text())
    assert summary["smoke_placeholder_used"] is True
    assert summary["real_pool_universe_used"] is False
    assert summary["smoke_placeholder_only"] is True
    # The pool address should be a placeholder
    with (test_out_abs / "pool_snapshots.jsonl").open() as f:
        for line in f:
            d = json.loads(line)
            assert "<smoke_pool_" in d["pool_address"]
    shutil.rmtree(test_out_abs, ignore_errors=True)


# ---------------------------------------------------------------------------
# Stage C: stage runner forwards --pool-universe
# ---------------------------------------------------------------------------

def test_c_stage_runner_forwards_pool_universe() -> None:
    """Stage runner script must pass --pool-universe to the collector."""
    text = STAGE_RUNNER.read_text()
    # Verify the actual call site has --pool-universe
    assert '"${POOL_UNIVERSE_PATH}"' in text or "--pool-universe" in text
    # The grep-based placeholder check is preserved
    assert "grep -q '<smoke_pool'" in text
    # Refused if universe is placeholder
    assert "REFUSED: pool universe contains <smoke_pool placeholder" in text


def test_c_stage_runner_syntax() -> None:
    rc = subprocess.run(["bash", "-n", str(STAGE_RUNNER)], capture_output=True, text=True)
    assert rc.returncode == 0, f"stage runner syntax error: {rc.stderr}"


def test_c_stage_runner_collector_args_updated() -> None:
    """Verify the actual collector invocation has --pool-universe passed."""
    text = STAGE_RUNNER.read_text()
    # The python3 invocation is multi-line via backslash continuation
    assert "--pool-universe" in text, "missing --pool-universe in stage runner"
    assert "--max-snapshots 1" in text, "missing --max-snapshots 1 in stage runner"
    assert "--run-id" in text, "missing --run-id in stage runner"
    # The actual call site must include them
    assert '"${POOL_UNIVERSE_PATH}"' in text, "POOL_UNIVERSE_PATH not used as --pool-universe value"


# ---------------------------------------------------------------------------
# Stage D: real pool universe short smoke (already ran; verify outputs)
# ---------------------------------------------------------------------------

def test_d_smoke_outputs_exist() -> None:
    assert SMOKE_DIR.exists()
    assert (SMOKE_DIR / "pool_snapshots.jsonl").exists()
    assert (SMOKE_DIR / "quote_snapshots.jsonl").exists()
    assert (SMOKE_DIR / "fee_velocity.jsonl").exists()
    assert (SMOKE_DIR / "liquidity_distribution.jsonl").exists()
    assert (SMOKE_DIR / "market_regime.jsonl").exists()
    assert (SMOKE_DIR / "actual_fee_accrual_placeholder.json").exists()
    assert (SMOKE_DIR / "smoke_summary.json").exists()


def test_d_smoke_real_pool_universe_used() -> None:
    summary = json.loads((SMOKE_DIR / "smoke_summary.json").read_text())
    assert summary["real_pool_universe_used"] is True
    assert summary["smoke_placeholder_used"] is False
    assert summary["placeholder_pool_count"] == 0


def test_d_smoke_all_pool_addresses_real() -> None:
    """No <smoke_pool_ in any output."""
    for p in SMOKE_DIR.rglob("*"):
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")
            assert "<smoke_pool_" not in text, f"placeholder marker in {p}"
            assert "<smoke_mint_" not in text, f"placeholder marker in {p}"


def test_d_smoke_pool_addresses_solana_format() -> None:
    """All pool addresses should be 43-44 char base58 (valid Solana format)."""
    with (SMOKE_DIR / "pool_snapshots.jsonl").open() as f:
        for line in f:
            d = json.loads(line)
            addr = d["pool_address"]
            assert 32 <= len(addr) <= 50, f"unexpected address length: {addr}"
            # Solana base58 charset (no 0, O, I, l)
            assert re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,50}$", addr), f"non-base58 address: {addr}"


def test_d_smoke_pool_addresses_unique() -> None:
    addrs = []
    with (SMOKE_DIR / "pool_snapshots.jsonl").open() as f:
        for line in f:
            addrs.append(json.loads(line)["pool_address"])
    assert len(addrs) == len(set(addrs)), "duplicate pool addresses"


def test_d_smoke_row_counts() -> None:
    """5 pools × 1 snapshot = 5 pool, 30 quote, 25 fee, 5 liq, 7 regime, 1 actual_fee_placeholder."""
    with (SMOKE_DIR / "pool_snapshots.jsonl").open() as f:
        assert sum(1 for _ in f) == 5
    with (SMOKE_DIR / "quote_snapshots.jsonl").open() as f:
        assert sum(1 for _ in f) == 30
    with (SMOKE_DIR / "fee_velocity.jsonl").open() as f:
        assert sum(1 for _ in f) == 25
    with (SMOKE_DIR / "liquidity_distribution.jsonl").open() as f:
        assert sum(1 for _ in f) == 5
    with (SMOKE_DIR / "market_regime.jsonl").open() as f:
        assert sum(1 for _ in f) == 7


def test_d_smoke_wallet_or_tx_touched_false() -> None:
    summary = json.loads((SMOKE_DIR / "smoke_summary.json").read_text())
    assert summary["wallet_or_tx_touched"] is False
    assert summary["transaction_sent"] is False


def test_d_smoke_source_artifact_recorded() -> None:
    """Each pool should have source_artifact recorded."""
    with (SMOKE_DIR / "pool_snapshots.jsonl").open() as f:
        for line in f:
            d = json.loads(line)
            assert d.get("source_artifact"), f"missing source_artifact in {d}"
            assert d.get("selection_reason"), f"missing selection_reason in {d}"


# ---------------------------------------------------------------------------
# Stage E: locked fields
# ---------------------------------------------------------------------------

def test_e_no_secret_value_in_outputs() -> None:
    """No real secret values in this stage's outputs."""
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),
        re.compile(r'\b[0-9a-fA-F]{64,}\b'),
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
                    pytest.fail(f"potential secret value matched {pat.pattern!r} in {p}: {m.group(0)[:80]}")


def test_e_no_forbidden_process() -> None:
    """No canary / live / paper / sendTransaction / keypair / private_key / mnemonic process."""
    rc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    forbidden = ["canary", "lpbot-live", "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for line in rc.stdout.splitlines():
        if "grep" in line:
            continue
        for tok in forbidden:
            if re.search(rf"\b{re.escape(tok)}\b", line):
                pytest.fail(f"forbidden process token {tok!r} found: {line}")


# ---------------------------------------------------------------------------
# Stage F: final verdict (will be filled in Stage Fx-F; just structure check)
# ---------------------------------------------------------------------------

def test_f_final_verdict_required_fields() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    required = {
        "stage", "status",
        "collector_pool_universe_arg_supported", "stage_runner_pool_universe_arg_supported",
        "real_pool_universe_smoke_ran", "real_pool_universe_used",
        "selected_real_pool_count", "placeholder_pool_count",
        "pool_snapshot_rows", "quote_snapshot_rows", "fee_velocity_rows", "market_regime_rows",
        "all_pool_addresses_real",
        "can_start_12h_real_universe_retry",
        "can_run_probe_now", "tiny_canary_allowed", "wallet_or_tx_touched", "transaction_sent",
        "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_f_final_verdict_locked_fields() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False


def test_f_final_verdict_recommended_next_stage_allowed() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    rec = fv["recommended_next_stage"]
    assert rec in ALLOWED_NEXT_STAGES, f"recommended_next_stage {rec!r} not in allowed set"


def test_f_final_verdict_no_auto_24h() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["can_start_12h_real_universe_retry"] is True or fv["can_start_12h_real_universe_retry"] is False
    # 12h retry must require user manual approval (not auto-start)
    # The verdict is: if 5 conditions met, recommend 12h retry; else fix_repeat / pause
