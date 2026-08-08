from pathlib import Path
import csv
import json
import re
import importlib.util
import sys

SCRIPT_PATH = Path("/Users/bendu/lp-bot/v3/scripts/lp_universe_scope_audit_v1_readonly.py")
REPORT_ROOT = Path("/Users/bendu/lp-bot/v3/reports/lp_universe_scope_audit")

def _latest_report_dir() -> Path:
    if not REPORT_ROOT.exists():
        return Path()
    dirs = sorted([p for p in REPORT_ROOT.iterdir() if p.is_dir() and re.fullmatch(r"\d{8}_\d{6}", p.name)])
    if not dirs:
        return Path()
    return dirs[-1]


def _load_module():
    spec = importlib.util.spec_from_file_location("lp_universe_scope_audit_v1_readonly", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_no_wallet_tx_signature_symbols_in_script():
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    banned = [
        "eth_sendrawtransaction",
        "sendtransaction(",
        "signtransaction(",
        "create_order",
        "wallet",
        "broadcast",
        "tx_hash",
    ]
    # This is a research-only script; allow only neutral words in comments/metadata as a strict check
    for token in banned:
        assert token not in text


def test_required_input_schema_fields_declared():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    required = [
        "unique_pool_count",
        "chain_count",
        "protocol_count",
        "recommended_next_stage",
        "universe_likely_too_narrow",
    ]
    for field in required:
        assert f'"{field}"' in text


def test_output_artifacts_exist_and_have_min_fields():
    report_dir = _latest_report_dir()
    assert report_dir and report_dir.exists()

    must_have_files = [
        "input_evidence_audit.json",
        "universe_extraction_raw.json",
        "vps_pool_universe_db_audit.json",
        "lp_universe_normalized_pool_list.csv",
        "lp_universe_stage_coverage_matrix.csv",
        "chain_protocol_coverage.csv",
        "current_screened_pool_summary.json",
        "universe_gap_analysis.json",
        "pool_universe_expansion_plan.json",
        "lp_universe_scope_next_stage_decision.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
        "ARTIFACT_INDEX.md",
    ]
    for name in must_have_files:
        assert (report_dir / name).exists(), f"missing {name}"

    # headers sanity
    with (report_dir / "lp_universe_normalized_pool_list.csv").open(encoding="utf-8") as f:
        fields = next(csv.reader(f))
        for key in ["pool_id", "chain", "protocol", "token_pair", "fee_tier", "pool_type", "latest_seen_stage"]:
            assert key in fields

    with (report_dir / "lp_universe_stage_coverage_matrix.csv").open(encoding="utf-8") as f:
        fields = next(csv.reader(f))
        for key in ["stage", "pool_count", "chain_count", "protocol_count", "label", "notes"]:
            assert key in fields

    with (report_dir / "chain_protocol_coverage.csv").open(encoding="utf-8") as f:
        fields = next(csv.reader(f))
        for key in ["type", "name", "covered", "pool_count", "priority_to_add"]:
            assert key in fields


def test_final_verdict_structure_and_rules():
    report_dir = _latest_report_dir()
    assert report_dir
    verdict_path = report_dir / "FINAL_VERDICT.json"
    payload = json.loads(verdict_path.read_text(encoding="utf-8"))

    for k in [
        "status",
        "stage",
        "unique_pool_count",
        "chain_count",
        "protocol_count",
        "recommended_next_stage",
        "solana_pool_count",
    ]:
        assert k in payload

    assert payload["stage"] == "LP_UNIVERSE_SCOPE_AUDIT_V1"
    assert payload["status"] in {"PASS", "WARN", "FAIL"}
    allowed_next = {
        "LP_EVM_UNIVERSE_EXPANSION_DESIGN_V1",
        "LP_AERODROME_SLIPSTREAM_PARSER_DESIGN_V1",
        "LP_SOLANA_LP_UNIVERSE_DESIGN_V1",
        "LP_UNIVERSE_SCOPE_AUDIT_FIX_REPEAT",
        "STOP_LP_RESEARCH_NOW",
    }
    assert payload["recommended_next_stage"] in allowed_next
    assert payload["unique_pool_count"] > 0


def test_chain_protocol_coverage_consistency():
    report_dir = _latest_report_dir()
    summary = json.loads((report_dir / "chain_protocol_coverage.json").read_text(encoding="utf-8"))
    assert summary["rows"]
    assert "summary" in summary

    # required summary keys exist
    for key in ["solana_covered", "base_uniswap_v3_covered", "base_pancakeswap_v3_covered", "aerodrome_covered"]:
        assert key in summary["summary"]


def test_stage_coverage_and_transition_consistent():
    module = _load_module()
    # ensure helper functions are callable and safe when invoked directly
    assert callable(module.normalize_chain)
    assert module.normalize_chain("base") == "base"
    assert module.normalize_chain("") == "unknown"
    assert module.normalize_protocol("uniswap v3") == "Uniswap V3"
    assert module.normalize_protocol("aerodrome") == "Aerodrome Slipstream"


def test_artifact_index_tracks_core_outputs():
    report_dir = _latest_report_dir()
    artifact = (report_dir / "ARTIFACT_INDEX.md").read_text(encoding="utf-8")
    required_lines = [
        "INPUT_EVIDENCE_AUDIT_CN.md",
        "universe_extraction_raw.csv",
        "lp_universe_normalized_pool_list.csv",
        "LP_UNIVERSE_SCOPE_NEXT_STAGE_DECISION_CN.md",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
    ]
    for line in required_lines:
        assert f"- {line}" in artifact

