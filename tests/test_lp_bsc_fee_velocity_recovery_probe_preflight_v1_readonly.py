"""Tests for scripts/lp_bsc_*_v1_readonly.py — recovery+probe pipeline.

These tests are hermetic — no network calls. They exercise pure functions
and assert the read-only safety invariants.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_SCRIPT = REPO_ROOT / "scripts" / "lp_bsc_rpc_eth_getlogs_capability_matrix_v1_readonly.py"
SMOKE_SCRIPT  = REPO_ROOT / "scripts" / "lp_bsc_fee_velocity_smoke_v1_readonly.py"
BACKFILL_SCRIPT = REPO_ROOT / "scripts" / "lp_bsc_fee_velocity_short_backfill_v2_readonly.py"
ECON_SCRIPT  = REPO_ROOT / "scripts" / "lp_bsc_realdata_economics_with_recovered_fee_v1_readonly.py"
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "lp_bsc_10_20u_probe_preflight_design_v1_readonly.py"


def _load(path: Path, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _executable(path: Path) -> str:
    import re as _re
    raw = path.read_text()
    raw = _re.sub(r'"""[\s\S]*?"""', '', raw)
    raw = _re.sub(r"'''[\s\S]*?'''", '', raw)
    lines = []
    for ln in raw.splitlines():
        if ln.lstrip().startswith("#") and not ln.lstrip().startswith("#!"):
            continue
        if "#" in ln:
            ln = ln.split("#", 1)[0]
        lines.append(ln)
    return "\n".join(lines).lower()


# --- Safety / readonly invariants ----------------------------------------

@pytest.mark.parametrize("script", [MATRIX_SCRIPT, SMOKE_SCRIPT, BACKFILL_SCRIPT, ECON_SCRIPT, PREFLIGHT_SCRIPT])
def test_script_has_no_wallet_or_tx_symbols(script: Path) -> None:
    text = _executable(script)
    banned = [
        "eth_sendrawtransaction(",
        "eth_sendtransaction(",
        "signtransaction(",
        "createsigner",
        "wallet.load",
        "from_private_key",
        "private_key =",
        "mnemonic =",
        "load_keystore",
        # Pool-state-mutating method invocations
        ".swap(",
        ".mint(",
        ".burn(",
        ".collect(",
        ".increaseliquidity(",
        ".decreaseliquidity(",
        ".approve(",
    ]
    for b in banned:
        assert b not in text, f"banned token in {script.name}: {b!r}"


@pytest.mark.parametrize("script", [MATRIX_SCRIPT, SMOKE_SCRIPT, BACKFILL_SCRIPT, ECON_SCRIPT, PREFLIGHT_SCRIPT])
def test_script_filename_marked_readonly(script: Path) -> None:
    assert "_readonly" in script.name


# --- ABI decoder semantics ----------------------------------------------

def test_smoke_decoder_handles_signed_amount_and_correct_field_count() -> None:
    smoke = _load(SMOKE_SCRIPT, "smoke_under_test")
    # Build a synthetic Pancake V3 Swap log: 7 fields × 32 bytes each.
    amount0 = -2136139431140373138655   # USDT outflow (18 dec)
    amount1 = 3133934367807289222       # WBNB inflow  (18 dec)
    sqrt_p  = 0x9ce536e1cc3aac24cb65e63   # uint160-ish placeholder
    liq     = 0x31dd9ce39deb4cf44a8ec     # uint128
    tick    = -65488                       # int24 sign-extended into 32-byte slot
    pf0     = 0xc961d735d7                 # uint128
    pf1     = 0                            # uint128

    def slot(v: int, signed: bool, bits: int) -> str:
        # Produce the 32-byte ABI-encoded slot. Sign-extend for signed types.
        if signed and v < 0:
            v += 1 << 256
        return f"{v & ((1 << 256) - 1):064x}"

    data = "0x" + "".join([
        slot(amount0, True, 256),
        slot(amount1, True, 256),
        slot(sqrt_p,  False, 160),
        slot(liq,     False, 128),
        slot(tick,    True, 24),   # int24 sign-extended into 32 bytes
        slot(pf0,     False, 128),
        slot(pf1,     False, 128),
    ])
    fake_log = {
        "topics": [
            "0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83",
            "0x0000000000000000000000009999b0cdd35d7f3b281ba02efc0d228486940515",
            "0x0000000000000000000000009999b0cdd35d7f3b281ba02efc0d228486940515",
        ],
        "data": data,
    }
    d = smoke.decode_pancake_v3_swap(fake_log)
    assert d["amount0"] == amount0
    assert d["amount1"] == amount1
    assert d["sqrtPriceX96"] == sqrt_p
    assert d["liquidity"] == liq
    assert d["tick"] == tick
    assert d["protocolFeesToken0"] == pf0
    assert d["protocolFeesToken1"] == pf1


def test_smoke_decoder_rejects_wrong_length_data() -> None:
    smoke = _load(SMOKE_SCRIPT, "smoke_len_test")
    log = {"topics": ["0x19b4", "0x" + "0"*64, "0x" + "0"*64], "data": "0x" + "00" * 100}
    with pytest.raises(ValueError):
        smoke.decode_pancake_v3_swap(log)


# --- RPC matrix schema --------------------------------------------------

def test_matrix_topic_is_pancake_v3_not_uniswap() -> None:
    matrix = _load(MATRIX_SCRIPT, "matrix_topic_check")
    # PancakeSwap V3 Swap (with protocolFeesToken0/1) — different keccak from Uniswap V3.
    assert matrix.SWAP_TOPIC_V3 == "0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83"
    # And the script should NOT contain the Uniswap V3 hash as the operative topic.
    text = _executable(MATRIX_SCRIPT)
    assert "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67" not in text or \
        "uniswap v3 swap is" in MATRIX_SCRIPT.read_text().lower()


def test_matrix_host_hash_redacts_urls() -> None:
    matrix = _load(MATRIX_SCRIPT, "matrix_redact")
    h1 = matrix.host_hash("https://bsc-rpc.publicnode.com")
    h2 = matrix.host_hash("http://bsc-rpc.publicnode.com:443/foo")
    assert h1 == h2  # hostname only, ignoring scheme/path/port
    assert len(h1) == 8 and all(c in "0123456789abcdef" for c in h1)


def test_matrix_redact_error_does_not_leak_url() -> None:
    matrix = _load(MATRIX_SCRIPT, "matrix_redact2")
    msg = "RuntimeError at https://my-secret-rpc.example.com/api/v1 reading"
    r = matrix.redact_error(msg)
    assert "my-secret-rpc" not in r


# --- Backfill: chunk-split-retry behavior -------------------------------

def test_backfill_decoder_matches_smoke_decoder() -> None:
    smoke = _load(SMOKE_SCRIPT, "smoke_x")
    bf = _load(BACKFILL_SCRIPT, "bf_x")
    # Same synthetic log, both decoders must agree (one decodes via smoke,
    # other via bf; same ABI).
    data = "0x" + "0" * (7 * 64 - 2) + "01"
    log = {
        "topics": [
            "0x19b47279",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": data,
    }
    a = smoke.decode_pancake_v3_swap(log)
    b = bf.decode_swap(log)
    assert a["amount0"] == b["amount0"]
    assert a["amount1"] == b["amount1"]


# --- Economics preview schema -------------------------------------------

def test_economics_allowed_scenarios_and_notionals() -> None:
    econ = _load(ECON_SCRIPT, "econ_x")
    assert set(econ.IL_LVR_SCENARIOS.keys()) == {"zero_il_lvr", "optimistic", "realistic", "conservative"}
    assert econ.NOTIONALS_USD == [Decimal("20"), Decimal("100"), Decimal("500"), Decimal("1000"), Decimal("2000")]
    assert set(econ.HOLD_WINDOWS_SEC.keys()) == {"15m", "30m", "1h", "2h", "6h", "24h"}


def test_economics_runs_against_empty_backfill(tmp_path: Path) -> None:
    """If backfill is missing or has no rows, the script should still produce a row_count=0
    output, not crash."""
    econ = _load(ECON_SCRIPT, "econ_empty")
    backfill_json = tmp_path / "bsc_fee_velocity_short_backfill_results.json"
    backfill_json.write_text(json.dumps({"rows": []}))
    real_cost = tmp_path / "empty_real_cost.csv"
    real_cost.write_text("pool_id,scenario,notional_usd,total_fixed_cost_usd,proportional_slippage_cost_usd\n")
    rd = tmp_path / "report"
    rd.mkdir()
    rc = econ.main([
        "--report-dir", str(rd),
        "--run-id", "test_run",
        "--real-cost-csv", str(real_cost),
        "--short-backfill-json", str(backfill_json),
    ])
    assert rc == 0
    summary = json.loads((rd / "bsc_realdata_economics_with_recovered_fee.json").read_text())
    assert summary["row_count"] == 0
    # All probe gates remain locked even if backfill is empty.
    assert summary["can_run_probe_now"] is False
    assert summary["tiny_canary_allowed"] == "no"
    assert summary["edge_proven"] == "no"
    assert summary["actual_fee_ready"] is False
    assert summary["token_id_available"] is False


# --- Finalizer reused from prior phase: probe gates can't be flipped ----

def test_no_script_flips_can_run_probe_now() -> None:
    """Across all five scripts, no executable code path sets can_run_probe_now=True."""
    for script in [MATRIX_SCRIPT, SMOKE_SCRIPT, BACKFILL_SCRIPT, ECON_SCRIPT, PREFLIGHT_SCRIPT]:
        text = _executable(script)
        # Look for direct assignments that would unlock the gate.
        for bad in [
            "can_run_probe_now = true",
            'can_run_probe_now: true',
            'tiny_canary_allowed = "yes"',
            'tiny_canary_allowed: "yes"',
            "edge_proven = yes",
            'edge_proven: "yes"',
        ]:
            assert bad not in text, f"{script.name} contains forbidden assignment: {bad!r}"


# --- Probe preflight specific tests -------------------------------------

def test_preflight_with_no_candidate_emits_no_candidate_kind(tmp_path: Path) -> None:
    pre = _load(PREFLIGHT_SCRIPT, "preflight_no_cand")
    rd = tmp_path / "r"
    rd.mkdir()
    # No econ file present
    rc = pre.main(["--report-dir", str(rd), "--run-id", "T"])
    assert rc == 0
    out = json.loads((rd / "bsc_10_20u_probe_preflight_design.json").read_text())
    assert out["preflight_kind"] in {"no_candidate_blocked_on_economics_preview", "no_probe_candidate"}
    assert out["can_run_probe_now"] is False
    assert out["manual_approval_required_for_probe"] is True
    assert out["edge_proven"] == "no"
    assert out["tiny_canary_allowed"] == "no"
    assert out["wallet_or_tx_touched"] is False


def test_preflight_with_candidate_emits_design_only(tmp_path: Path) -> None:
    pre = _load(PREFLIGHT_SCRIPT, "preflight_cand")
    rd = tmp_path / "r"
    rd.mkdir()
    econ_payload = {
        "positive_proxy_count_realistic": 5,
        "near_break_even_count": 12,
        "best_pool": "0x172fcd41e0913e95784454622d1c3724f546f849",
        "best_pair": "USDT/WBNB",
        "best_fee_tier": 100,
        "best_hold_window": "1h",
        "best_notional": "20",
        "best_net_ev_proxy_usd": "0.04",
        "best_net_ev_proxy_pct": "0.20",
    }
    (rd / "bsc_realdata_economics_with_recovered_fee.json").write_text(json.dumps(econ_payload))
    rc = pre.main(["--report-dir", str(rd), "--run-id", "T"])
    assert rc == 0
    out = json.loads((rd / "bsc_10_20u_probe_preflight_design.json").read_text())
    assert out["preflight_kind"] == "candidate_present_design_only"
    # Even with a candidate, the gate is still off.
    assert out["can_run_probe_now"] is False
    assert out["manual_approval_required_for_probe"] is True
    assert out["edge_proven"] == "no"
    # All execution_constraints are False — no wallet/signer/tx allowed in this phase.
    for k, v in out["execution_constraints"].items():
        if k.endswith("_allowed_in_this_phase"):
            assert v is False, f"preflight unexpectedly allows {k}"
    # max_funds_usd capped at 20
    assert out["execution_constraints"]["max_funds_usd"] == 20
