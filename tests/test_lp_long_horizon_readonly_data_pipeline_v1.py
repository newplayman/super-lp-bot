"""Tests for LP Long Horizon Read-only Data Pipeline (LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1).

These tests verify:
1. The collector script is read-only and free of wallet / signer / tx / mutation / bridge tokens
2. The script defaults to design mode and rejects daemon / 30d / loop / cron / live / canary / paper / probe
3. The script's safety self-check passes (no banned tokens in real code)
4. The script's CLI rejects non-design/smoke modes and non-whitelisted write paths
5. The FINAL_VERDICT.json fields are locked
6. The 6 deliverables (CN + json) exist with correct structure
7. Long-running phases (R0 long run, R1 actual fee, R2 regime split, R3 candidate review,
   R4 probe preflight, R5 manual probe) are out of scope
8. The 7 regime classifier spec, the actual fee accrual schema, and the safety audit
   cover all required dimensions
9. The 6 model limitations from the prior scope_audit are addressed by the data
   requirements (HIGH-impact gaps have a corresponding design)
10. Locked conclusions from prior scope_audit (can_run_probe_now=false, tiny_canary_allowed=no,
    edge_proven=no, global_lp_rejected=false) are preserved
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
REPORT_DIR = REPO_ROOT / "reports" / "lp_long_horizon_readonly_data_pipeline" / "20260604_062324"
SCRIPT_PATH = REPO_ROOT / "scripts" / "lp_long_horizon_readonly_collector_v1.py"
FINAL_VERDICT = REPORT_DIR / "FINAL_VERDICT.json"  # will be created in Stage K
INPUT_EVIDENCE = REPORT_DIR / "input_evidence_audit.json"
REQUIREMENTS_JSON = REPORT_DIR / "long_horizon_data_requirements.json"
ARCHITECTURE_JSON = REPORT_DIR / "readonly_collector_architecture.json"
SCHEMA_JSON = REPORT_DIR / "research_only_schema.json"
REGIME_JSON = REPORT_DIR / "market_regime_classifier_spec.json"
ACTUAL_FEE_JSON = REPORT_DIR / "actual_fee_accrual_schema.json"
SAFETY_JSON = REPORT_DIR / "collector_safety_audit.json"
ONEPAGE_CN = REPORT_DIR / "ONEPAGE_CN.md"
ARTIFACT_INDEX = REPORT_DIR / "ARTIFACT_INDEX.md"

CN_DOCS = [
    REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
    REPORT_DIR / "LONG_HORIZON_DATA_REQUIREMENTS_CN.md",
    REPORT_DIR / "READONLY_COLLECTOR_ARCHITECTURE_CN.md",
    REPORT_DIR / "RESEARCH_ONLY_SCHEMA_CN.md",
    REPORT_DIR / "MARKET_REGIME_CLASSIFIER_SPEC_CN.md",
    REPORT_DIR / "ACTUAL_FEE_ACCRUAL_SCHEMA_CN.md",
    REPORT_DIR / "COLLECTOR_SAFETY_AUDIT_CN.md",
]


# ---------------------------------------------------------------------------
# 1. safety / wallet / keypair / signer / tx
# ---------------------------------------------------------------------------

BANNED_TOKENS = [
    "private_key", "mnemonic", "seed_phrase", "seed_words",
    "Keypair.from_secret_key", "fromSecretKey", "SecretKey",
    "keystore.json", "encrypted_json",
    "new Signer(", "new Wallet(",
    "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction",
    "signTransaction(", "signAndSendTransaction(",
    "add_liquidity(", "remove_liquidity(", "collect_fee(", "collect(",
    "mint(", "approve(", "burn(", "transfer(",
    "wormhole.core", "wormhole.bridge", "mayan.forward", "portal.bridge",
]


def _strip_docstrings_and_comments(text: str) -> str:
    """Return the source with comments and string literals (including docstrings) blanked.

    Used to ensure the safety check examines real code only, not documentation.
    """
    import ast
    import io as _io
    import tokenize

    try:
        ast.parse(text)  # ensure the file is syntactically valid before tokenizing
    except SyntaxError:
        return text  # let the safety self-check fail loudly in the script

    lines = text.splitlines(keepends=True)
    try:
        tokens = list(tokenize.generate_tokens(_io.StringIO(text).readline))
    except tokenize.TokenizeError:
        return text
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            start_row, start_col = tok.start
            end_row, end_col = tok.end
            if start_row - 1 >= len(lines):
                continue
            if end_row - 1 >= len(lines):
                end_row = len(lines)
            if start_row == end_row:
                line = lines[start_row - 1]
                lines[start_row - 1] = line[:start_col] + " " * (end_col - start_col) + line[end_col:]
            else:
                first = lines[start_row - 1]
                lines[start_row - 1] = first[:start_col]
                for mid in range(start_row, end_row - 1):
                    lines[mid] = " " * len(lines[mid])
                last = lines[end_row - 1]
                lines[end_row - 1] = " " * end_col + last[end_col:]
    return "".join(lines)


def test_script_no_banned_token_in_real_code():
    assert SCRIPT_PATH.exists(), f"missing {SCRIPT_PATH}"
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    scannable = _strip_docstrings_and_comments(text)
    # The BANNED_TOKENS_IN_CODE tuple itself is metadata, not real code; strip it.
    m = re.search(r"BANNED_TOKENS_IN_CODE\s*=\s*\(", text)
    if m is not None:
        # blank out the entire tuple
        import ast
        try:
            tree = ast.parse(text)
        except SyntaxError:
            pass
        else:
            target = None
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name) and tgt.id == "BANNED_TOKENS_IN_CODE":
                            target = node
                            break
                    if target is not None:
                        break
            if target is not None:
                lines = scannable.splitlines(keepends=True)
                start_line, start_col = target.lineno - 1, target.col_offset
                end_line, end_col = target.end_lineno - 1, target.end_col_offset
                if end_line >= len(lines):
                    end_line = len(lines) - 1
                    end_col = len(lines[end_line])
                pre = "".join(lines[:start_line]) + lines[start_line][:start_col]
                post = lines[end_line][end_col:] + "".join(lines[end_line + 1:])
                blanked = " " * (len(scannable) - len(pre) - len(post))
                scannable = pre + blanked + post
    for token in BANNED_TOKENS:
        assert token not in scannable, f"banned token {token!r} found in {SCRIPT_PATH.name}"


def test_script_self_check_passes():
    """Run the script in design mode and confirm the safety self-check passes."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"design mode failed: rc={result.returncode}\nstderr={result.stderr}"
    assert "SAFETY GUARD" not in result.stderr
    assert "[design mode]" in result.stdout


@pytest.mark.parametrize("bad_mode", [
    "daemon", "30d", "long", "loop", "cron", "continuous",
    "live", "canary", "paper", "probe", "auto", "scheduled",
])
def test_script_rejects_long_running_mode(bad_mode: str):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--mode", bad_mode],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0, f"mode {bad_mode!r} unexpectedly accepted"
    assert "REFUSED" in result.stderr or "REFUSED" in result.stdout


def test_script_rejects_non_whitelisted_output_path():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--mode", "smoke", "--out", "/tmp/evil"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "REFUSED" in result.stderr or "data/lp_long_horizon" in result.stderr


def test_script_smoke_mode_writes_only_in_whitelisted_dir(tmp_path: Path):
    # Use a relative path starting with data/lp_long_horizon to satisfy the script's
    # write-path guard (which checks for the literal prefix "data/lp_long_horizon").
    out_rel = "data/lp_long_horizon/smoke_test"
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--mode", "smoke", "--out", out_rel],
        capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"smoke failed: rc={result.returncode}\nstderr={result.stderr}"
    out = (REPO_ROOT / out_rel).resolve()
    assert out.exists()
    files = sorted(p.name for p in out.iterdir())
    assert "pool_snapshots.jsonl" in files
    assert "quote_snapshots.jsonl" in files
    assert "fee_velocity.jsonl" in files
    assert "liquidity_distribution.jsonl" in files
    assert "market_regime.jsonl" in files
    assert "actual_fee_accrual_placeholder.json" in files
    assert "smoke_summary.json" in files
    summary = json.loads((out / "smoke_summary.json").read_text(encoding="utf-8"))
    assert summary["wallet_or_tx_touched"] is False
    assert summary["transaction_sent"] is False
    assert summary["send_hard_disable_still_active"] is True
    assert summary["stage"] == "LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1"
    # cleanup
    import shutil
    shutil.rmtree(out, ignore_errors=True)


# ---------------------------------------------------------------------------
# 2. locked conclusions preserved
# ---------------------------------------------------------------------------

def test_final_verdict_fields_locked():
    assert FINAL_VERDICT.exists(), f"missing {FINAL_VERDICT}"
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    assert v["stage"] == "LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1"
    assert v["status"] in {"PASS", "WARN", "FAIL"}
    assert v["global_lp_rejected"] is False
    assert v["current_probe_allowed"] is False
    assert v["can_run_probe_now"] is False
    assert v["tiny_canary_allowed"] == "no"
    assert v["edge_proven"] == "no"
    assert v["wallet_or_tx_touched"] is False
    assert v["transaction_sent"] is False
    assert v["send_hard_disable_still_active"] is True
    # long_horizon_pipeline_ready / collector_script_built /
    # market_regime_classifier_spec_ready / actual_fee_accrual_schema_ready
    # are all true after Stage K's FINAL_VERDICT.json is written.
    assert v["long_horizon_pipeline_ready"] is True
    assert v["collector_script_built"] is True
    assert v["market_regime_classifier_spec_ready"] is True
    assert v["actual_fee_accrual_schema_ready"] is True


def test_final_verdict_recommended_next_stage_allowed():
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    allowed = {
        "LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1",
        "LP_LONG_HORIZON_READONLY_PIPELINE_FIX_REPEAT",
        "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA",
        "STOP_LP_RESEARCH_NOW",
    }
    assert v["recommended_next_stage"] in allowed, (
        f"recommended_next_stage={v['recommended_next_stage']!r} "
        f"not in allowed set {sorted(allowed)}"
    )


def test_input_evidence_audit_locked_fields():
    audit = json.loads(INPUT_EVIDENCE.read_text(encoding="utf-8"))
    locked = audit["locked_boundary_fields"]
    assert locked["can_run_probe_now"] is False
    assert locked["tiny_canary_allowed"] == "no"
    assert locked["edge_proven"] == "no"
    assert locked["send_hard_disable_still_active"] is True
    assert locked["global_lp_rejected"] is False
    assert locked["current_probe_allowed"] is False
    assert locked["long_term_lp_value_judged"] is False
    assert locked["conclusion_scope"] == "current_data_current_model_short_window"


def test_input_evidence_audit_build_target_fields():
    audit = json.loads(INPUT_EVIDENCE.read_text(encoding="utf-8"))
    target = audit["build_target_fields"]
    assert target["needs_longer_horizon_validation"] is True
    assert target["needs_actual_fee_accrual"] is True
    assert target["needs_market_regime_split"] is True
    assert target["long_horizon_pipeline_ready"] is False  # flipped to true at Stage K
    assert target["collector_script_built"] is False  # flipped to true at Stage K
    assert target["market_regime_classifier_spec_ready"] is False
    assert target["actual_fee_accrual_schema_ready"] is False


# ---------------------------------------------------------------------------
# 3. data requirements cover 6 categories
# ---------------------------------------------------------------------------

def test_requirements_cover_six_categories():
    req = json.loads(REQUIREMENTS_JSON.read_text(encoding="utf-8"))
    names = {c["name"] for c in req["data_categories"]}
    expected = {
        "pool_snapshot", "quote_snapshot", "fee_velocity",
        "liquidity_distribution", "market_regime", "future_actual_fee_accrual",
    }
    assert expected.issubset(names)
    for cat in req["data_categories"]:
        assert "fields" in cat
        assert len(cat["fields"]) > 0


def test_requirements_address_high_impact_limitations():
    req = json.loads(REQUIREMENTS_JSON.read_text(encoding="utf-8"))
    addressed = req["addressed_model_limitations"]
    for dim in ["data_window", "fee_data", "il_lvr", "pool_selection"]:
        assert dim in addressed, f"missing {dim} in addressed_model_limitations"
        assert addressed[dim]  # non-empty string


def test_requirements_notional_levels():
    req = json.loads(REQUIREMENTS_JSON.read_text(encoding="utf-8"))
    for cat in req["data_categories"]:
        if cat["name"] == "quote_snapshot":
            assert cat["notional_levels_usd"] == [10, 20, 100, 500, 1000, 2000]


# ---------------------------------------------------------------------------
# 4. collector architecture: design + smoke, daemon / 30d rejected
# ---------------------------------------------------------------------------

def test_architecture_default_mode_design():
    arch = json.loads(ARCHITECTURE_JSON.read_text(encoding="utf-8"))
    assert arch["default_mode"] == "design"
    assert set(arch["allowed_modes"]) == {"design", "smoke"}
    rejected = set(arch["hard_rejected_modes"])
    for bad in ["daemon", "30d", "long", "loop", "cron", "live", "canary", "paper", "probe"]:
        assert bad in rejected, f"{bad!r} not in hard_rejected_modes"


def test_architecture_storage_root_whitelisted():
    arch = json.loads(ARCHITECTURE_JSON.read_text(encoding="utf-8"))
    assert arch["storage"]["root"].startswith("data/lp_long_horizon/")
    # The architecture JSON does not enumerate forbidden write paths; those live in
    # the safety_audit JSON. The architecture does enumerate hard_rejected_modes which
    # should cover daemon / cron / continuous / live / canary / paper / probe.
    rejected = set(arch["hard_rejected_modes"])
    for bad in ["daemon", "30d", "long", "loop", "cron", "live", "canary", "paper", "probe"]:
        assert bad in rejected, f"{bad!r} not in architecture.hard_rejected_modes"
    # Cross-check: safety audit JSON enumerates the forbidden write paths.
    safety = json.loads(SAFETY_JSON.read_text(encoding="utf-8"))
    forbidden_write = set(safety["forbidden_write_paths"])
    for path in ["data/dryrun*", "data/shadow*", "data/live*", "migrations/", "cmd/", "internal/"]:
        assert path in forbidden_write, f"{path!r} not in safety.forbidden_write_paths"


def test_architecture_safety_guard_invariants():
    arch = json.loads(ARCHITECTURE_JSON.read_text(encoding="utf-8"))
    invariants = arch["safety_guard_invariants"]
    joined = " ".join(invariants).lower()
    assert "private_key" in joined or "keypair" in joined
    assert "sendtransaction" in joined
    assert "swap" in joined or "liquidity" in joined
    assert "data/lp_long_horizon" in joined


# ---------------------------------------------------------------------------
# 5. research-only schema
# ---------------------------------------------------------------------------

def test_schema_tables_complete():
    schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    table_names = {t["name"] for t in schema["tables"]}
    expected = {
        "pool_snapshots", "quote_snapshots", "fee_velocity",
        "liquidity_distribution", "market_regime", "future_actual_fee_accrual",
    }
    assert expected.issubset(table_names)


def test_schema_write_path_constraint():
    schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    assert schema["storage_root"].startswith("data/lp_long_horizon/")
    # Schema JSON does not enumerate forbidden paths; cross-check via safety_audit.
    safety = json.loads(SAFETY_JSON.read_text(encoding="utf-8"))
    forbidden = set(safety["forbidden_write_paths"])
    for path in ["migrations/", "cmd/", "internal/", "data/dryrun*", "data/shadow*", "data/live*"]:
        assert path in forbidden, f"{path!r} not in safety.forbidden_write_paths"


def test_schema_actual_fee_r0_no_records():
    schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    actual = [t for t in schema["tables"] if t["name"] == "future_actual_fee_accrual"]
    assert actual
    assert "schema only" in actual[0]["r0_phase_status"] or "no records" in actual[0]["r0_phase_status"]


# ---------------------------------------------------------------------------
# 6. regime classifier spec
# ---------------------------------------------------------------------------

def test_regime_seven_classes():
    spec = json.loads(REGIME_JSON.read_text(encoding="utf-8"))
    assert spec["regime_count"] == 7
    names = {r["name"] for r in spec["regimes"]}
    expected = {
        "uptrend", "downtrend", "sideways", "high_volume_sideways",
        "high_volatility_trend", "incentive_period", "low_volatility_stable",
    }
    assert expected == names


def test_regime_priority_order():
    spec = json.loads(REGIME_JSON.read_text(encoding="utf-8"))
    priority = spec["priority_order"]
    assert priority[0] == "low_volatility_stable"  # highest priority
    assert "incentive_period" in priority[:3]
    assert "high_volatility_trend" in priority[:4]
    assert priority[-1] == "sideways"  # lowest priority


def test_regime_locked_conclusions():
    spec = json.loads(REGIME_JSON.read_text(encoding="utf-8"))
    impl = spec["implementation_outline_only"]
    assert impl is True
    assert spec["manual_approval_required_for_r0_implementation"] is True


# ---------------------------------------------------------------------------
# 7. actual fee accrual schema
# ---------------------------------------------------------------------------

def test_actual_fee_schema_sections():
    schema = json.loads(ACTUAL_FEE_JSON.read_text(encoding="utf-8"))
    sections = {s["section"] for s in schema["schema_sections"]}
    expected = {"entry", "exit", "collect_fee", "tokens_owed", "derived"}
    assert expected.issubset(sections)


def test_actual_fee_r0_no_records_status():
    schema = json.loads(ACTUAL_FEE_JSON.read_text(encoding="utf-8"))
    for sec in schema["schema_sections"]:
        assert "schema only" in sec["r0_phase_status"] or "not applicable" in sec["r0_phase_status"], \
            f"section {sec['section']} r0_phase_status not locked: {sec['r0_phase_status']!r}"


def test_actual_fee_heuristic_vs_actual_mapping():
    schema = json.loads(ACTUAL_FEE_JSON.read_text(encoding="utf-8"))
    mapping = schema["heuristic_vs_actual_mapping"]
    for key in ["fee", "il", "net_ev", "holding_period"]:
        assert key in mapping, f"{key!r} missing in heuristic_vs_actual_mapping"


# ---------------------------------------------------------------------------
# 8. safety audit
# ---------------------------------------------------------------------------

def test_safety_audit_layers():
    audit = json.loads(SAFETY_JSON.read_text(encoding="utf-8"))
    layers = set(audit["audit_layers"])
    expected = {
        "architecture_design", "code_static_analysis", "data_source_call_safety",
        "write_path_constraint", "locked_field_preservation",
        "process_level_safety", "cross_stage_isolation",
    }
    assert expected.issubset(layers)


def test_safety_audit_forbidden_tokens_in_code():
    audit = json.loads(SAFETY_JSON.read_text(encoding="utf-8"))
    forbidden = audit["forbidden_tokens_in_code"]
    for tok in ["private_key", "sendTransaction", "add_liquidity(", "approve("]:
        assert tok in forbidden, f"{tok!r} missing in forbidden_tokens_in_code"


def test_safety_audit_locked_fields_preserved():
    audit = json.loads(SAFETY_JSON.read_text(encoding="utf-8"))
    locked = audit["locked_fields_preserved"]
    assert locked["can_run_probe_now"] is False
    assert locked["tiny_canary_allowed"] == "no"
    assert locked["edge_proven"] == "no"
    assert locked["global_lp_rejected"] is False
    assert locked["long_term_lp_value_judged"] is False


def test_safety_audit_out_of_scope():
    audit = json.loads(SAFETY_JSON.read_text(encoding="utf-8"))
    oos = " ".join(audit["out_of_scope_hard_prohibitions"]).lower()
    assert "paid" in oos
    assert "r1" in oos
    assert "r2" in oos
    assert "r3" in oos
    assert "r4" in oos
    assert "r5" in oos


# ---------------------------------------------------------------------------
# 9. CN docs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", CN_DOCS, ids=lambda p: p.name)
def test_cn_doc_exists_and_nonempty(path: Path):
    assert path.exists(), f"missing {path.name}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"empty {path.name}"
    assert "20260604_062324" in text, f"run_id missing in {path.name}"


def test_input_evidence_audit_cn_contains_required():
    text = (REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md").read_text(encoding="utf-8")
    for phrase in [
        "LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1",
        "can_run_probe_now",
        "tiny_canary_allowed",
        "needs_longer_horizon_validation",
        "needs_actual_fee_accrual",
        "needs_market_regime_split",
        "market_downtrend_bias_acknowledged",
        "不创建 signer",
        "不发送 transaction",
    ]:
        assert phrase in text, f"missing phrase {phrase!r} in INPUT_EVIDENCE_AUDIT_CN.md"


def test_requirements_cn_contains_six_categories():
    text = (REPORT_DIR / "LONG_HORIZON_DATA_REQUIREMENTS_CN.md").read_text(encoding="utf-8")
    for cat in ["pool_snapshot", "quote_snapshot", "fee_velocity",
                "liquidity_distribution", "market_regime",
                "future_actual_fee_accrual"]:
        assert cat in text, f"missing {cat!r} in LONG_HORIZON_DATA_REQUIREMENTS_CN.md"


def test_architecture_cn_contains_design_and_smoke():
    text = (REPORT_DIR / "READONLY_COLLECTOR_ARCHITECTURE_CN.md").read_text(encoding="utf-8")
    for phrase in ["design mode", "smoke mode", "daemon", "30d", "data/lp_long_horizon", "safety guard"]:
        assert phrase in text, f"missing {phrase!r} in READONLY_COLLECTOR_ARCHITECTURE_CN.md"


def test_regime_cn_contains_seven_regimes():
    text = (REPORT_DIR / "MARKET_REGIME_CLASSIFIER_SPEC_CN.md").read_text(encoding="utf-8")
    for regime in ["uptrend", "downtrend", "sideways", "high_volume_sideways",
                   "high_volatility_trend", "incentive_period", "low_volatility_stable"]:
        assert regime in text, f"missing {regime!r} in MARKET_REGIME_CLASSIFIER_SPEC_CN.md"


def test_actual_fee_cn_contains_three_sections():
    text = (REPORT_DIR / "ACTUAL_FEE_ACCRUAL_SCHEMA_CN.md").read_text(encoding="utf-8")
    for sec in ["entry", "exit", "collect_fee", "tokens_owed", "derived"]:
        assert sec in text, f"missing {sec!r} in ACTUAL_FEE_ACCRUAL_SCHEMA_CN.md"


def test_safety_audit_cn_contains_layers():
    text = (REPORT_DIR / "COLLECTOR_SAFETY_AUDIT_CN.md").read_text(encoding="utf-8")
    for phrase in [
        "架构层", "代码层", "数据源", "写路径", "锁存字段",
        "进程级", "跨阶段", "长期运行",
    ]:
        assert phrase in text, f"missing {phrase!r} in COLLECTOR_SAFETY_AUDIT_CN.md"


# ---------------------------------------------------------------------------
# 10. run_id consistency
# ---------------------------------------------------------------------------

def test_run_id_consistent():
    expected = "20260604_062324"
    paths = [INPUT_EVIDENCE, REQUIREMENTS_JSON, ARCHITECTURE_JSON, SCHEMA_JSON,
             REGIME_JSON, ACTUAL_FEE_JSON, SAFETY_JSON] + CN_DOCS
    for p in paths:
        text = p.read_text(encoding="utf-8")
        assert expected in text, f"run_id {expected} missing in {p.name}"


# ---------------------------------------------------------------------------
# 11. process safety (live / canary / paper / keypair)
# ---------------------------------------------------------------------------

def test_no_canary_live_paper_keypair_process():
    result = subprocess.run(
        ["bash", "-c",
         "ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|"
         "eth_sendTransaction|keypair' | grep -v grep || true"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    # the matched output (if any) must not include our own process name
    # (since we ran ps + grep, our command line could match "live"; that's OK as long as
    # it isn't a real running process). Filter out the grep itself.
    matched = [
        line for line in result.stdout.splitlines()
        if "grep" not in line and line.strip()
    ]
    assert not matched, f"suspicious running process: {matched}"
