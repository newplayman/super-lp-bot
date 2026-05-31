#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


RUN_ID = "20260531_124000"
REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
REPORT_DIR = REPO_ROOT / "reports" / "final_freeze" / RUN_ID


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


INPUTS = {
    "final_p2_verdict": REPO_ROOT / "reports/fee_velocity_rule_fix/20260531_122413/FINAL_VERDICT.json",
    "final_p2_stop": REPO_ROOT / "reports/fee_velocity_rule_fix/20260531_122413/FEE_RULE_FIX_STOP_OR_CONTINUE_CN.md",
    "final_p2_best": REPO_ROOT / "reports/fee_velocity_rule_fix/20260531_122413/FEE_RULE_BEST_PRACTICAL_VARIANT_CN.md",
    "final_p2_gate": REPO_ROOT / "reports/fee_velocity_rule_fix/20260531_122413/FEE_RULE_PRACTICALITY_GATE_CN.md",
    "p2_v1_verdict": REPO_ROOT / "reports/fee_velocity_exit_depth/20260531_115101/FINAL_VERDICT.json",
    "regime_rule_fix_verdict": REPO_ROOT / "reports/pool_regime_rule_fix/20260531_113056/FINAL_VERDICT.json",
    "regime_review_verdict": REPO_ROOT / "reports/pool_regime_aware_review/20260531_110005/FINAL_VERDICT.json",
    "regime_review_leakage": REPO_ROOT / "reports/pool_regime_aware_review/20260531_110005/LOOKAHEAD_LEAKAGE_AUDIT_CN.md",
    "regime_counterfactual_verdict": REPO_ROOT / "reports/pool_regime_aware_short_hold/20260531_095237/FINAL_VERDICT.json",
    "regime_classifier_verdict": REPO_ROOT / "reports/pool_regime_classifier/20260531_092109/FINAL_VERDICT.json",
    "risk_signal_verdict": REPO_ROOT / "reports/risk_signal_definition_fix/20260531_080614/FINAL_VERDICT.json",
    "risk_aware_verdict": REPO_ROOT / "reports/risk_aware_short_hold/20260531_073906/FINAL_VERDICT.json",
    "new_hypothesis_verdict": REPO_ROOT / "reports/new_strategy_hypothesis/20260531_071724/FINAL_VERDICT.json",
    "new_hypothesis_priority": REPO_ROOT / "reports/new_strategy_hypothesis/20260531_071724/NEW_STRATEGY_PRIORITY_RANKING_CN.md",
    "intent_dedup_verdict": REPO_ROOT / "reports/intent_lifecycle_dedup/20260531_061138/FINAL_VERDICT.json",
    "intent_dq_verdict": REPO_ROOT / "reports/intent_lifecycle_dq/20260531_055521/FINAL_VERDICT.json",
    "position_reuse_verdict": REPO_ROOT / "reports/position_reuse_review/20260531_050614/FINAL_VERDICT.json",
    "materializer_verdict": REPO_ROOT / "reports/materializer_classification/20260531_044242/FINAL_VERDICT.json",
    "fixed_horizon_verdict": REPO_ROOT / "reports/fixed_horizon_policy/20260530_145208/FINAL_VERDICT.json",
    "tierb_data_fix_verdict": REPO_ROOT / "reports/tierb_data_fix/20260530_125453/FINAL_VERDICT.json",
    "tierb_diagnosis_verdict": REPO_ROOT / "reports/tierb_diagnosis/20260530_103214/FINAL_VERDICT.json",
    "tierc_freeze_verdict": REPO_ROOT / "reports/tierc_shadow/20260529_155854/TIER_C_BATCH_FINAL_FREEZE_VERDICT.json",
    "portfolio_verdict": REPO_ROOT / "reports/portfolio_status/20260529_160811/FINAL_VERDICT.json",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_input_audit() -> dict[str, Any]:
    rows = [{"input_name": k, "path": str(v), "exists": v.exists()} for k, v in INPUTS.items()]
    missing = [r["path"] for r in rows if not r["exists"]]
    latest_available = {
        "final_p2": str(INPUTS["final_p2_verdict"]) if INPUTS["final_p2_verdict"].exists() else "",
        "pool_regime": str(INPUTS["regime_rule_fix_verdict"]) if INPUTS["regime_rule_fix_verdict"].exists() else "",
        "risk_aware_short_hold": str(INPUTS["risk_aware_verdict"]) if INPUTS["risk_aware_verdict"].exists() else "",
        "intent_lifecycle": str(INPUTS["intent_dedup_verdict"]) if INPUTS["intent_dedup_verdict"].exists() else "",
        "tier_c": str(INPUTS["tierc_freeze_verdict"]) if INPUTS["tierc_freeze_verdict"].exists() else "",
    }
    audit = {
        "inputs": rows,
        "missing_input_list": missing,
        "latest_available_report_per_strategy_line": latest_available,
        "enough_evidence_to_freeze_research": len(missing) == 0,
        "must_not_add_new_strategy_conclusion": True,
    }
    md = ["# 输入证据审计", "", "| input | exists |", "|---|---|"]
    for row in rows:
        md.append(f"| `{row['path']}` | {fmt(row['exists'])} |")
    md.extend(
        [
            "",
            f"- missing input list: `{', '.join(missing) if missing else 'none'}`",
            f"- enough evidence to freeze research: `{fmt(audit['enough_evidence_to_freeze_research'])}`",
            "- 本轮不新增策略结论，只基于已有报告做收口。",
        ]
    )
    write_text(REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md", "\n".join(md) + "\n")
    write_json(REPORT_DIR / "input_evidence_audit.json", audit)
    return audit


def build_strategy_freeze_matrix() -> list[dict[str, Any]]:
    fee_fix = load_json(INPUTS["final_p2_verdict"])
    fee_v1 = load_json(INPUTS["p2_v1_verdict"])
    regime_fix = load_json(INPUTS["regime_rule_fix_verdict"])
    regime_review = load_json(INPUTS["regime_review_verdict"])
    regime_classifier = load_json(INPUTS["regime_classifier_verdict"])
    risk_signal = load_json(INPUTS["risk_signal_verdict"])
    risk_aware = load_json(INPUTS["risk_aware_verdict"])
    intent_dedup = load_json(INPUTS["intent_dedup_verdict"])
    intent_dq = load_json(INPUTS["intent_dq_verdict"])
    position_reuse = load_json(INPUTS["position_reuse_verdict"])
    fixed_horizon = load_json(INPUTS["fixed_horizon_verdict"])
    tierb_data = load_json(INPUTS["tierb_data_fix_verdict"])
    tierc = load_json(INPUTS["tierc_freeze_verdict"])
    portfolio = load_json(INPUTS["portfolio_verdict"])

    rows = [
        {
            "strategy_line": "current_full_strategy",
            "latest_stage": "portfolio_freeze",
            "latest_report_path": str(INPUTS["portfolio_verdict"]),
            "status": "FAIL",
            "core_reason": "position_lifecycle primary proof 下 tail 不可接受",
            "key_metrics": "current_full_strategy=FAIL, tiny_canary_allowed=no",
            "can_continue_same_line": "no",
            "canary_allowed": "no",
            "required_condition_to_reopen": "new proof unit or new data/strategy assumption",
        },
        {
            "strategy_line": "fixed_horizon_position_lifecycle",
            "latest_stage": fixed_horizon["stage"],
            "latest_report_path": str(INPUTS["fixed_horizon_verdict"]),
            "status": "STOP",
            "core_reason": "12h fail, 24h insufficient, position reuse dominant",
            "key_metrics": f"recommended_next_stage={fixed_horizon.get('recommended_next_stage')}",
            "can_continue_same_line": "no",
            "canary_allowed": "no",
            "required_condition_to_reopen": "new sample source not blocked by reuse",
        },
        {
            "strategy_line": "intent_lifecycle",
            "latest_stage": intent_dedup["stage"],
            "latest_report_path": str(INPUTS["intent_dedup_verdict"]),
            "status": "STOP",
            "core_reason": "DQ 修正后无 stable review-ready signal",
            "key_metrics": f"signal_status={intent_dedup.get('intent_lifecycle_signal_status')}",
            "can_continue_same_line": "no",
            "canary_allowed": "no",
            "required_condition_to_reopen": "new intent proof design + better entry notional lineage",
        },
        {
            "strategy_line": "Tier B discovery/data-fix",
            "latest_stage": tierb_data["stage"],
            "latest_report_path": str(INPUTS["tierb_data_fix_verdict"]),
            "status": "PAUSE",
            "core_reason": "no research candidate with enough data quality",
            "key_metrics": f"recommended_next_stage={tierb_data.get('recommended_next_stage')}",
            "can_continue_same_line": "no",
            "canary_allowed": "no",
            "required_condition_to_reopen": "stronger data source and new candidate set",
        },
        {
            "strategy_line": "Tier C batch",
            "latest_stage": tierc["stage"],
            "latest_report_path": str(INPUTS["tierc_freeze_verdict"]),
            "status": "REJECTED",
            "core_reason": "holder/trader concentration extreme, batch frozen",
            "key_metrics": f"batch_status={tierc.get('batch_status')}, reject_locked_count={tierc.get('reject_locked_count')}",
            "can_continue_same_line": "no",
            "canary_allowed": "no",
            "required_condition_to_reopen": "new market change and rediscovery only",
        },
        {
            "strategy_line": "Risk-Aware Short-Hold exit",
            "latest_stage": risk_signal["stage"],
            "latest_report_path": str(INPUTS["risk_signal_verdict"]),
            "status": "STOP",
            "core_reason": "risk_exit not helpful, quarantine only helpful",
            "key_metrics": f"risk_exit_helpful_after_fix={risk_signal.get('risk_exit_helpful_after_fix')}",
            "can_continue_same_line": "no",
            "canary_allowed": "no",
            "required_condition_to_reopen": "new risk signal family with practical retention",
        },
        {
            "strategy_line": "Pool Regime Classifier",
            "latest_stage": regime_classifier["stage"],
            "latest_report_path": str(INPUTS["regime_classifier_verdict"]),
            "status": "PAUSE",
            "core_reason": "有尾部解释力，但只能做过滤解释，不足以独立成策略",
            "key_metrics": f"review_ready={regime_classifier.get('review_ready')}",
            "can_continue_same_line": "no",
            "canary_allowed": "no",
            "required_condition_to_reopen": "serve as feature only under new strategy frame",
        },
        {
            "strategy_line": "Pool Regime Aware Short-Hold",
            "latest_stage": regime_review["stage"],
            "latest_report_path": str(INPUTS["regime_review_verdict"]),
            "status": "STOP",
            "core_reason": "leakage fixed 后 retention 太低，误杀太高",
            "key_metrics": f"review_v2_status={regime_review.get('review_v2_status')}, recommended_next_stage={regime_fix.get('recommended_next_stage')}",
            "can_continue_same_line": "no",
            "canary_allowed": "no",
            "required_condition_to_reopen": "new practical gate pass with non-overfiltering behavior",
        },
        {
            "strategy_line": "Fee Velocity / Exit Depth",
            "latest_stage": fee_fix["stage"],
            "latest_report_path": str(INPUTS["final_p2_verdict"]),
            "status": "STOP",
            "core_reason": "no practical variant passed, fee-cost still negative or retention too low",
            "key_metrics": f"tested_rule_fix_variant_count={fee_fix.get('tested_rule_fix_variant_count')}, practical_gate_pass={fee_fix.get('practical_gate_pass')}",
            "can_continue_same_line": "no",
            "canary_allowed": "no",
            "required_condition_to_reopen": "new fee/depth data pipeline and strategy redesign",
        },
        {
            "strategy_line": "Overall LP research line",
            "latest_stage": "final_freeze",
            "latest_report_path": str(REPORT_DIR / "FINAL_VERDICT.json"),
            "status": "STOP",
            "core_reason": "P0/P1/P2 全部未形成可实用研究候选",
            "key_metrics": f"portfolio_next={portfolio.get('recommended_primary_next_stage')}, p2_next={fee_fix.get('recommended_next_stage')}",
            "can_continue_same_line": "no",
            "canary_allowed": "no",
            "required_condition_to_reopen": "new data source first or full hypothesis redesign",
        },
    ]
    write_csv(REPORT_DIR / "strategy_line_freeze_matrix.csv", rows, list(rows[0].keys()))
    md = ["# 策略线冻结矩阵", ""]
    for row in rows:
        md.append(
            f"- `{row['strategy_line']}`: `{row['status']}` | reason: {row['core_reason']} | reopen: {row['required_condition_to_reopen']}"
        )
    write_text(REPORT_DIR / "STRATEGY_LINE_FREEZE_MATRIX_CN.md", "\n".join(md) + "\n")
    return rows


def build_key_evidence_chain() -> list[dict[str, Any]]:
    items = [
        {
            "finding": "terminal tail / proof surface 问题",
            "evidence_report": str(INPUTS["portfolio_verdict"]),
            "implication": "主策略 proof surface 需要收敛到可信单位",
            "decision": "放弃 decision_trace 作为 primary proof",
        },
        {
            "finding": "decision_trace 重复计数污染",
            "evidence_report": str(INPUTS["portfolio_verdict"]),
            "implication": "旧 edge 判断不可信",
            "decision": "position_lifecycle 成为 primary proof",
        },
        {
            "finding": "position reuse dominant 导致 position-level OOS 不可行",
            "evidence_report": str(INPUTS["position_reuse_verdict"]),
            "implication": "继续等待 position lifecycle 新样本效率极低",
            "decision": "fixed horizon 主线暂停/停止",
        },
        {
            "finding": "intent lifecycle DQ 修正，hardcoded 10 USD 伪信号被消除",
            "evidence_report": str(INPUTS["intent_dq_verdict"]),
            "implication": "先前 intent positive signal 有伪信号成分",
            "decision": "intent lifecycle 不进入 review",
        },
        {
            "finding": "dedup 修复后仍无法进入 review",
            "evidence_report": str(INPUTS["intent_dedup_verdict"]),
            "implication": "intent line 没有稳定实用 edge",
            "decision": "暂停 intent line",
        },
        {
            "finding": "risk-aware exit 不 helpful",
            "evidence_report": str(INPUTS["risk_aware_verdict"]),
            "implication": "靠 exit timing 修不出可用 LP edge",
            "decision": "转向 quarantine / regime filtering",
        },
        {
            "finding": "quarantine 有帮助",
            "evidence_report": str(INPUTS["risk_signal_verdict"]),
            "implication": "尾部风险有可过滤结构",
            "decision": "进入 regime classifier 研究",
        },
        {
            "finding": "pool regime classifier 有尾部解释力",
            "evidence_report": str(INPUTS["regime_classifier_verdict"]),
            "implication": "数据 stale / incomplete 对 tail 有显著影响",
            "decision": "尝试 regime-aware short-hold",
        },
        {
            "finding": "temporal leakage 被发现并修正",
            "evidence_report": str(INPUTS["regime_review_leakage"]),
            "implication": "same-bucket/post-entry feature 使用会制造伪改善",
            "decision": "entry-safe previous closed bucket rule 固化",
        },
        {
            "finding": "entry-safe regime 仍机会保留率太低、误杀太高",
            "evidence_report": str(INPUTS["regime_rule_fix_verdict"]),
            "implication": "虽然 tail improved，但不可实用",
            "decision": "不继续 regime-aware 主线",
        },
        {
            "finding": "fee velocity / exit depth rule fix 无 practical variant",
            "evidence_report": str(INPUTS["final_p2_verdict"]),
            "implication": "P2 也只是过滤器，不是可继续 review 的策略候选",
            "decision": "STOP_RESEARCH",
        },
        {
            "finding": "最终 STOP_RESEARCH",
            "evidence_report": str(INPUTS["final_p2_verdict"]),
            "implication": "当前 LP 研究线不应继续小修参数",
            "decision": "收口并 handoff",
        },
    ]
    write_json(REPORT_DIR / "key_evidence_chain.json", items)
    md = ["# 关键证据链总结", ""]
    for item in items:
        md.append(f"- finding: {item['finding']}")
        md.append(f"  - evidence_report: `{item['evidence_report']}`")
        md.append(f"  - implication: {item['implication']}")
        md.append(f"  - decision: {item['decision']}")
    write_text(REPORT_DIR / "KEY_EVIDENCE_CHAIN_CN.md", "\n".join(md) + "\n")
    return items


def build_bug_fix_list() -> list[dict[str, Any]]:
    rows = [
        {
            "issue": "terminal_exit_mark / pool_mark_only 误读",
            "root_cause": "terminal / future mark 语义未分清",
            "fixed": "yes",
            "fix_location_or_report": str(INPUTS["materializer_verdict"]),
            "residual_risk": "low",
            "lessons_learned": "terminal 和 no_future_mark 必须分开统计",
        },
        {
            "issue": "decision_trace_id join 到 trace_id 而不是 id",
            "root_cause": "连接键理解偏差",
            "fixed": "yes",
            "fix_location_or_report": str(INPUTS["portfolio_verdict"]),
            "residual_risk": "medium",
            "lessons_learned": "trace surfaces 要先验 schema semantics",
        },
        {
            "issue": "decision_trace 重复计数污染",
            "root_cause": "把 trace 当独立 proof unit",
            "fixed": "yes",
            "fix_location_or_report": str(INPUTS["portfolio_verdict"]),
            "residual_risk": "low",
            "lessons_learned": "proof unit 必须先冻结",
        },
        {
            "issue": "terminal_before_target 被归入 no_future_mark",
            "root_cause": "invalid_reason 分类顺序错误",
            "fixed": "yes",
            "fix_location_or_report": str(INPUTS["materializer_verdict"]),
            "residual_risk": "low",
            "lessons_learned": "invalid_reason 是研究结论的一部分，不只是标签",
        },
        {
            "issue": "hardcoded 10 USD entry notional 伪信号",
            "root_cause": "missing intended_notional 被默认值掩盖",
            "fixed": "yes",
            "fix_location_or_report": str(INPUTS["intent_dq_verdict"]),
            "residual_risk": "low",
            "lessons_learned": "缺失值不能用乐观默认值补",
        },
        {
            "issue": "pool regime temporal leakage",
            "root_cause": "同 bucket post-entry feature 混入 classifier",
            "fixed": "yes",
            "fix_location_or_report": str(INPUTS["regime_review_leakage"]),
            "residual_risk": "medium",
            "lessons_learned": "entry-safe cutoff 要显式定义",
        },
        {
            "issue": "retained_sample_count / quarantine 0.0 混入口径",
            "root_cause": "filtered summary 混了 quarantine sentinel",
            "fixed": "yes",
            "fix_location_or_report": str(INPUTS["regime_review_verdict"]),
            "residual_risk": "low",
            "lessons_learned": "summary 之前先分开 retained 与 quarantine",
        },
        {
            "issue": "VPS runtime env / DB DSN 加载问题",
            "root_cause": "runtime env 路径和 workspace 依赖不稳定",
            "fixed": "yes",
            "fix_location_or_report": str(INPUTS["portfolio_verdict"]),
            "residual_risk": "medium",
            "lessons_learned": "DB readiness 检查必须前置",
        },
        {
            "issue": "Git sync / artifact publish workflow 改进",
            "root_cause": "本地/VPS 研究产物不同步",
            "fixed": "yes",
            "fix_location_or_report": str(INPUTS["portfolio_verdict"]),
            "residual_risk": "low",
            "lessons_learned": "report-first git flow 要标准化",
        },
    ]
    write_csv(REPORT_DIR / "bugs_and_semantic_fixes.csv", rows, list(rows[0].keys()))
    md = ["# 已修复的 bug / 口径问题清单", ""]
    for row in rows:
        md.append(f"- `{row['issue']}` | fixed=`{row['fixed']}` | residual_risk=`{row['residual_risk']}`")
    write_text(REPORT_DIR / "BUGS_AND_SEMANTIC_FIXES_CN.md", "\n".join(md) + "\n")
    return rows


def build_no_canary() -> dict[str, Any]:
    data = {
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "reasons": [
            "没有通过任何完整 proof gate",
            "没有可用 practical variant",
            "fee_minus_exit_cost 不能覆盖成本",
            "opportunity retention 太低",
            "false filter / missed profit 太高",
            "仍有 overfit / data quality / leakage 修复历史",
            "tail risk 虽可被过滤，但过滤后策略不可实用",
            "live/canary 会把研究伪信号变成真实损失",
        ],
    }
    md = ["# 为什么不能 Canary", ""]
    for k in ["edge_proven", "tiny_canary_candidate", "tiny_canary_allowed"]:
        md.append(f"- {k}: `{data[k]}`")
    md.append("")
    for r in data["reasons"]:
        md.append(f"- {r}")
    write_text(REPORT_DIR / "WHY_NO_CANARY_CN.md", "\n".join(md) + "\n")
    write_json(REPORT_DIR / "why_no_canary.json", data)
    return data


def build_reopen_conditions() -> dict[str, Any]:
    data = {
        "new_data_source_conditions": [
            "更可信的 fee APR / LP fee accrual 数据",
            "更精确的 exit depth / quote route simulation",
            "完整 holder / trader concentration",
            "更高频且 entry-safe 的 pool snapshots",
            "可证明无 lookahead 的 feature pipeline",
        ],
        "new_strategy_conditions": [
            "不再从 fixed-horizon / simple short-hold 出发",
            "必须先定义容量、退出路径、fee-cost 覆盖",
            "必须先设 tail gate，再看 median",
            "必须支持小资金实际容量",
        ],
        "proof_conditions": [
            "sample_count >= 300",
            "p10 / p5 / p1 不危险",
            "opportunity retention 不低",
            "false filter / missed profit 可接受",
            "fee_minus_exit_cost p10 不明显负",
            "worst pool/event 不集中",
            "无 lookahead",
            "go/no-go gate 清晰",
        ],
    }
    md = ["# 未来重启条件", ""]
    for title, items in data.items():
        md.append(f"## {title}")
        for item in items:
            md.append(f"- {item}")
        md.append("")
    write_text(REPORT_DIR / "REOPEN_CONDITIONS_CN.md", "\n".join(md) + "\n")
    write_json(REPORT_DIR / "reopen_conditions.json", data)
    return data


def build_next_project_options() -> dict[str, Any]:
    options = [
        {"option": "STOP_LP_RESEARCH_NOW", "reason": "P0/P1/P2 都没有 practical candidate"},
        {"option": "NEW_DATA_PIPELINE_FIRST", "reason": "先补 fee/depth/holder/trader/entry-safe 高频数据"},
        {"option": "NEW_STRATEGY_HYPOTHESIS_DESIGN_REPEAT", "reason": "完全重开题，避开已有失败路径"},
        {"option": "NON_LP_STRATEGY_RESEARCH", "reason": "转向非 LP 方向，例如纯扫描/异常检测"},
        {"option": "PRODUCTION_INFRA_CLEANUP_ONLY", "reason": "不继续研究，只做工程清理"},
    ]
    result = {
        "options": options,
        "primary_next_option": "STOP_LP_RESEARCH_NOW",
        "secondary_next_option": "NEW_DATA_PIPELINE_FIRST",
        "why_not_continue_same_line": "当前所有 LP 研究分支都只证明了过滤价值，没有形成 practical variant",
    }
    md = ["# 下一阶段选择", "", f"- primary: `{result['primary_next_option']}`", f"- secondary: `{result['secondary_next_option']}`", ""]
    for row in options:
        md.append(f"- `{row['option']}`: {row['reason']}")
    write_text(REPORT_DIR / "NEXT_PROJECT_OPTIONS_CN.md", "\n".join(md) + "\n")
    write_json(REPORT_DIR / "next_project_options.json", result)
    return result


def build_final_onepage() -> None:
    md = [
        "# LPBOT 最终一页总结",
        "",
        "最终结论：当前 LP 研究线应停止，不做 canary，不做 micro-live。",
        "",
        "为什么停：",
        "- 主策略 current_full_strategy 失败。",
        "- fixed horizon 和 intent lifecycle 都没形成可实用 proof。",
        "- Tier B 没有可推进候选，Tier C 批次已 reject。",
        "- Risk-Aware Short-Hold 证明 quarantine 有帮助，但 risk-exit 本身没用。",
        "- Pool Regime 方向修掉 leakage 之后，tail 虽改善，但机会保留率太低。",
        "- Fee Velocity / Exit Depth 最终也没有任何 practical variant 通过 gate。",
        "",
        "已经试过什么：",
        "- position lifecycle proof",
        "- fixed horizon / intent lifecycle",
        "- regime-aware short-hold",
        "- fee / depth / slippage / small-cap variants",
        "",
        "最大教训：",
        "- 先冻结 proof unit，再跑研究。",
        "- 先防 lookahead 和重复计数，再谈 edge。",
        "- 只会压 tail 但不能保留机会的过滤器，不等于策略。",
        "",
        "未来怎么重启：",
        "- 先补新数据源，尤其是 fee accrual、exit depth、holder/trader、高频 entry-safe snapshots。",
        "- 然后重新开题，不要继续同一批参数搜索。",
        "",
        "当前是否能 canary：不能。",
    ]
    write_text(REPORT_DIR / "LPBOT_FINAL_ONEPAGE_CN.md", "\n".join(md) + "\n")


def build_final_verdict(next_options: dict[str, Any]) -> dict[str, Any]:
    verdict = {
        "status": "PASS",
        "stage": "LPBOT_RESEARCH_FINAL_FREEZE_AND_HANDOFF_V1",
        "research_freeze_complete": True,
        "current_full_strategy": "FAIL",
        "fixed_horizon_position_lifecycle": "STOP",
        "intent_lifecycle": "STOP",
        "tier_b": "PAUSE",
        "tier_c": "BATCH_REJECTED",
        "risk_aware_short_hold": "STOP",
        "pool_regime_aware_short_hold": "STOP",
        "fee_velocity_exit_depth": "STOP",
        "overall_recommendation": "stop current LP strategy research and hand off findings",
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_options["primary_next_option"],
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
    md = [
        "# Onepage",
        "",
        f"- research_freeze_complete: `{fmt(verdict['research_freeze_complete'])}`",
        f"- overall_recommendation: `{verdict['overall_recommendation']}`",
        f"- recommended_next_stage: `{verdict['recommended_next_stage']}`",
        f"- edge_proven: `{verdict['edge_proven']}`",
        f"- tiny_canary_allowed: `{verdict['tiny_canary_allowed']}`",
    ]
    write_text(REPORT_DIR / "ONEPAGE_CN.md", "\n".join(md) + "\n")
    return verdict


def write_artifact_index() -> None:
    names = [
        "INPUT_EVIDENCE_AUDIT_CN.md",
        "input_evidence_audit.json",
        "STRATEGY_LINE_FREEZE_MATRIX_CN.md",
        "strategy_line_freeze_matrix.csv",
        "KEY_EVIDENCE_CHAIN_CN.md",
        "key_evidence_chain.json",
        "BUGS_AND_SEMANTIC_FIXES_CN.md",
        "bugs_and_semantic_fixes.csv",
        "WHY_NO_CANARY_CN.md",
        "why_no_canary.json",
        "REOPEN_CONDITIONS_CN.md",
        "reopen_conditions.json",
        "NEXT_PROJECT_OPTIONS_CN.md",
        "next_project_options.json",
        "LPBOT_FINAL_ONEPAGE_CN.md",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
    ]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "# Artifact Index\n\n" + "\n".join(f"- `{n}`" for n in names) + "\n")


def main() -> None:
    ensure_dir(REPORT_DIR)
    build_input_audit()
    build_strategy_freeze_matrix()
    build_key_evidence_chain()
    build_bug_fix_list()
    build_no_canary()
    build_reopen_conditions()
    next_options = build_next_project_options()
    build_final_onepage()
    build_final_verdict(next_options)
    write_artifact_index()


if __name__ == "__main__":
    main()
