#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import shlex
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
RUN_ID = "20260531_110005"
REPORT_DIR = REPO_ROOT / "reports" / "pool_regime_aware_review" / RUN_ID
PRIOR_DIR = REPO_ROOT / "reports" / "pool_regime_aware_short_hold" / "20260531_095237"
CLASSIFIER_DIR = REPO_ROOT / "reports" / "pool_regime_classifier" / "20260531_092109"
RISK_SIGNAL_DIR = REPO_ROOT / "reports" / "risk_signal_definition_fix" / "20260531_080614"
RISK_AWARE_DIR = REPO_ROOT / "reports" / "risk_aware_short_hold" / "20260531_073906"
NEW_STRATEGY_DIR = REPO_ROOT / "reports" / "new_strategy_hypothesis" / "20260531_071724"

TABLE_NAME = "pool_regime_aware_short_hold_counterfactual_v1"
EXPECTED_STAGE = "POOL_REGIME_AWARE_SHORT_HOLD_COUNTERFACTUAL_V1"
BEST_VARIANT = "regime_score_threshold_loose"
BEST_WINDOW = "recent_72h"
BEST_HORIZON = "2h"
BEST_PROOF = "pool_window"

WINDOWS = ["recent_24h", "recent_48h", "recent_72h", "recent_7d"]
HORIZONS = ["15m", "30m", "1h", "2h"]
BAD_REGIMES = {
    "TOXIC_FLOW",
    "EXIT_DEPTH_THIN",
    "VOLUME_COLLAPSE",
    "TVL_DROP",
    "PRICE_SPIKE_VOLATILE",
    "WHALE_OR_HOLDER_CONCENTRATED",
    "DATA_STALE_OR_INCOMPLETE",
    "UNKNOWN",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def bootstrap_env() -> None:
    for candidate in [REPO_ROOT / ".runtime.shadow.env", REPO_ROOT / ".env", REPO_ROOT / ".env.chain"]:
        if not candidate.exists():
            continue
        for raw in candidate.read_text(errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            try:
                parsed = shlex.split(line, posix=True)
            except Exception:
                parsed = [line]
            normalized = parsed[0] if parsed else line
            if "=" not in normalized:
                continue
            key, value = normalized.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def connect_db():
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("missing_postgres_dsn")
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    return conn


def parse_num(v: Any) -> float | None:
    if v in (None, "", "null", "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def percentile(values: list[float], p: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    idx = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * p))))
    return vals[idx]


def median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.10f}".rstrip("0").rstrip(".")
    return str(v)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def valid_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if row["data_quality_status"] != "ok":
            continue
        hold = parse_num(row["hold_to_horizon_pnl_pct"])
        filt = parse_num(row["regime_filtered_pnl_pct"])
        row = dict(row)
        row["hold_to_horizon_pnl_pct"] = hold
        row["regime_filtered_pnl_pct"] = filt
        row["loss_avoided"] = parse_num(row["loss_avoided"]) or 0.0
        row["missed_profit"] = parse_num(row["missed_profit"]) or 0.0
        out.append(row)
    return out


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = valid_rows(rows)
    retained = [r for r in rows if r["entry_allowed"]]
    quarantined = [r for r in rows if not r["entry_allowed"]]
    pos_rows = [r for r in rows if r["hold_to_horizon_pnl_pct"] is not None and r["hold_to_horizon_pnl_pct"] > 0]
    neg_rows = [r for r in rows if r["hold_to_horizon_pnl_pct"] is not None and r["hold_to_horizon_pnl_pct"] < 0]
    hold_values = [r["hold_to_horizon_pnl_pct"] for r in rows if r["hold_to_horizon_pnl_pct"] is not None]
    retained_values = [r["regime_filtered_pnl_pct"] for r in retained if r["regime_filtered_pnl_pct"] is not None]
    false_quarantine_rows = [r for r in rows if r["false_quarantine_flag"]]
    missed_profit_rows = [r for r in rows if (not r["entry_allowed"]) and (r["hold_to_horizon_pnl_pct"] or 0) > 0]
    loss_avoided_rows = [r for r in rows if (not r["entry_allowed"]) and (r["hold_to_horizon_pnl_pct"] or 0) < 0]

    total_retained_loss = sum(abs(r["hold_to_horizon_pnl_pct"]) for r in retained if (r["hold_to_horizon_pnl_pct"] or 0) < 0)
    pool_loss = Counter()
    regime_loss = Counter()
    for r in retained:
        hold = r["hold_to_horizon_pnl_pct"] or 0.0
        if hold < 0:
            pool_loss[r["pool_id"]] += abs(hold)
            regime_loss[r["regime_primary"]] += abs(hold)

    opportunity_retention_rate = None
    if pos_rows:
        opportunity_retention_rate = sum(1 for r in pos_rows if r["opportunity_retained"]) / len(pos_rows)

    false_quarantine_rate = len(false_quarantine_rows) / len(rows) if rows else None
    missed_profit_rate = (sum(r["missed_profit"] for r in rows) / len(pos_rows)) if pos_rows else None
    loss_avoidance_rate = len(loss_avoided_rows) / len(neg_rows) if neg_rows else None
    worst_pool_contribution = (max(pool_loss.values()) / total_retained_loss) if total_retained_loss and pool_loss else None
    worst_regime_contribution = (max(regime_loss.values()) / total_retained_loss) if total_retained_loss and regime_loss else None

    return {
        "sample_count": len(rows),
        "retained_sample_count": len(retained),
        "baseline_p10": percentile(hold_values, 0.10),
        "baseline_p5": percentile(hold_values, 0.05),
        "baseline_p1": percentile(hold_values, 0.01),
        "filtered_p10": percentile(retained_values, 0.10),
        "filtered_p5": percentile(retained_values, 0.05),
        "filtered_p1": percentile(retained_values, 0.01),
        "tail_improvement_p10": (percentile(retained_values, 0.10) - percentile(hold_values, 0.10)) if retained_values and hold_values else None,
        "tail_improvement_p5": (percentile(retained_values, 0.05) - percentile(hold_values, 0.05)) if retained_values and hold_values else None,
        "tail_improvement_p1": (percentile(retained_values, 0.01) - percentile(hold_values, 0.01)) if retained_values and hold_values else None,
        "opportunity_retention_rate": opportunity_retention_rate,
        "false_quarantine_rate": false_quarantine_rate,
        "missed_profit_rate": missed_profit_rate,
        "loss_avoidance_rate": loss_avoidance_rate,
        "worst_pool_contribution": worst_pool_contribution,
        "worst_regime_contribution": worst_regime_contribution,
        "data_quality_status": "sufficient" if len(rows) >= 300 else "thin",
        "missed_profit_count": len(missed_profit_rows),
        "false_quarantine_count": len(false_quarantine_rows),
        "loss_avoided_count": len(loss_avoided_rows),
        "missed_profit_values": [r["hold_to_horizon_pnl_pct"] for r in missed_profit_rows],
        "loss_avoided_values": [abs(r["hold_to_horizon_pnl_pct"]) for r in loss_avoided_rows],
        "quarantined_count": len(quarantined),
    }


def row_verdict(metrics: dict[str, Any]) -> str:
    if metrics["retained_sample_count"] < 100:
        return "INSUFFICIENT"
    improved = all((metrics[k] is not None and metrics[k] > 0) for k in ["tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1"])
    if not improved:
        return "FAIL"
    if (metrics["opportunity_retention_rate"] or 0) >= 0.7 and (metrics["false_quarantine_rate"] or 1) <= 0.2 and (metrics["missed_profit_rate"] or 1) <= 0.2:
        return "PASS"
    return "WARN"


def load_review_inputs() -> dict[str, Path]:
    return {
        "prior_final_verdict": PRIOR_DIR / "FINAL_VERDICT.json",
        "prior_counterfactual_md": PRIOR_DIR / "REGIME_AWARE_SHORT_HOLD_COUNTERFACTUAL_REPORT_CN.md",
        "prior_counterfactual_csv": PRIOR_DIR / "regime_aware_short_hold_counterfactual_report.csv",
        "prior_best_md": PRIOR_DIR / "REGIME_AWARE_BEST_VARIANT_SELECTION_CN.md",
        "prior_best_json": PRIOR_DIR / "regime_aware_best_variant_selection.json",
        "prior_robust_md": PRIOR_DIR / "REGIME_AWARE_ROBUSTNESS_AUDIT_CN.md",
        "prior_robust_csv": PRIOR_DIR / "regime_aware_robustness_audit.csv",
        "prior_next_md": PRIOR_DIR / "REGIME_AWARE_NEXT_STAGE_DECISION_CN.md",
        "prior_next_json": PRIOR_DIR / "regime_aware_next_stage_decision.json",
        "classifier_final": CLASSIFIER_DIR / "FINAL_VERDICT.json",
        "risk_signal_final": RISK_SIGNAL_DIR / "FINAL_VERDICT.json",
        "risk_aware_final": RISK_AWARE_DIR / "FINAL_VERDICT.json",
        "new_strategy_final": NEW_STRATEGY_DIR / "FINAL_VERDICT.json",
    }


def select_best_from_report(report_rows: list[dict[str, str]]) -> dict[str, Any] | None:
    candidates = []
    for row in report_rows:
        retained = int(row["retained_sample_count"])
        p10 = parse_num(row["tail_improvement_p10"])
        p5 = parse_num(row["tail_improvement_p5"])
        p1 = parse_num(row["tail_improvement_p1"])
        opp = parse_num(row["opportunity_retention_rate"])
        fq = parse_num(row["false_quarantine_rate"])
        mp = parse_num(row["missed_profit_rate"])
        worst = parse_num(row["worst_pool_contribution"])
        if retained < 100:
            continue
        if None in (p10, p5, p1):
            continue
        if p10 <= 0 or p5 <= 0 or p1 <= 0:
            continue
        if opp is not None and opp < 0.7:
            continue
        if fq is not None and fq > 0.5:
            continue
        if mp is not None and mp > 0.5:
            continue
        if worst is not None and worst > 0.6:
            continue
        candidates.append(row)
    candidates.sort(
        key=lambda r: (
            parse_num(r["tail_improvement_p10"]) or -999.0,
            parse_num(r["tail_improvement_p5"]) or -999.0,
            parse_num(r["tail_improvement_p1"]) or -999.0,
            parse_num(r["opportunity_retention_rate"]) or 0.0,
            -(parse_num(r["false_quarantine_rate"]) or 1.0),
        ),
        reverse=True,
    )
    return candidates[0] if candidates else None


def select_best_corrected(rows: list[dict[str, Any]], window: str, horizon: str, proof: str) -> dict[str, Any] | None:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["window"] != window or row["horizon"] != horizon or row["proof_unit_type"] != proof:
            continue
        by_variant[row["variant_name"]].append(row)
    candidates = []
    for variant_name, variant_rows in by_variant.items():
        metrics = compute_metrics(variant_rows)
        if metrics["retained_sample_count"] < 100:
            continue
        if None in (metrics["tail_improvement_p10"], metrics["tail_improvement_p5"], metrics["tail_improvement_p1"]):
            continue
        if metrics["tail_improvement_p10"] <= 0 or metrics["tail_improvement_p5"] <= 0 or metrics["tail_improvement_p1"] <= 0:
            continue
        if metrics["opportunity_retention_rate"] is not None and metrics["opportunity_retention_rate"] < 0.7:
            continue
        if metrics["false_quarantine_rate"] is not None and metrics["false_quarantine_rate"] > 0.5:
            continue
        if metrics["missed_profit_rate"] is not None and metrics["missed_profit_rate"] > 0.5:
            continue
        if metrics["worst_pool_contribution"] is not None and metrics["worst_pool_contribution"] > 0.6:
            continue
        candidates.append({"variant_name": variant_name, **metrics})
    candidates.sort(
        key=lambda r: (
            r["tail_improvement_p10"],
            r["tail_improvement_p5"],
            r["tail_improvement_p1"],
            r["opportunity_retention_rate"] or 0.0,
            -(r["false_quarantine_rate"] or 1.0),
        ),
        reverse=True,
    )
    return candidates[0] if candidates else None


def main() -> None:
    ensure_dir(REPORT_DIR)
    inputs = load_review_inputs()
    input_exists = {k: v.exists() for k, v in inputs.items()}

    prior_final = load_json(inputs["prior_final_verdict"])
    prior_best = load_json(inputs["prior_best_json"])
    prior_next = load_json(inputs["prior_next_json"])
    report_rows = load_csv(inputs["prior_counterfactual_csv"])

    enough_for_review = all(input_exists.values())
    input_audit = {
        **input_exists,
        "prior_stage_ok": prior_final.get("stage") == EXPECTED_STAGE,
        "best_variant_ok": prior_final.get("best_variant_name") == BEST_VARIANT,
        "review_ready_yes": bool(prior_final.get("review_ready")),
        "overfit_risk_high": prior_final.get("overfit_risk") == "HIGH",
        "enough_for_v2_review": enough_for_review and prior_final.get("stage") == EXPECTED_STAGE,
        "edge_proven": "no",
    }
    write_text(
        REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md",
        "\n".join(
            ["# Input Artifact Audit", ""]
            + [f"- {k}: {'yes' if v else 'no'}" for k, v in input_exists.items()]
            + [
                "",
                f"- prior_stage_ok: {'yes' if input_audit['prior_stage_ok'] else 'no'}",
                f"- best_variant_ok: {'yes' if input_audit['best_variant_ok'] else 'no'}",
                f"- review_ready_yes: {'yes' if input_audit['review_ready_yes'] else 'no'}",
                f"- overfit_risk_high: {'yes' if input_audit['overfit_risk_high'] else 'no'}",
                f"- enough_for_v2_review: {'yes' if input_audit['enough_for_v2_review'] else 'no'}",
                "- edge_proven: no",
            ]
        )
        + "\n",
    )
    write_json(REPORT_DIR / "input_artifact_audit.json", input_audit)

    if prior_final.get("stage") != EXPECTED_STAGE:
        write_text(
            REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md",
            "# Wrong Stage Blocker\n\n"
            f"- expected_stage: {EXPECTED_STAGE}\n"
            f"- actual_stage: {prior_final.get('stage')}\n",
        )
        return

    bootstrap_env()
    conn = connect_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("select current_database(), current_user")
        db_name, db_user = cur.fetchone().values()
        cur.execute(
            f"""
            select *
            from {TABLE_NAME}
            """,
        )
        all_rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    best_variant_rows = [r for r in all_rows if r["variant_name"] == BEST_VARIANT]

    write_text(
        REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md",
        "# VPS DB Quick Check\n\n"
        "- DSN_PRESENT: yes\n"
        "- DB_CONNECT: ok\n"
        f"- DB_NAME: {db_name}\n"
        f"- DB_USER: {db_user}\n",
    )

    best_tuple_rows = [
        r for r in best_variant_rows
        if r["window"] == BEST_WINDOW and r["horizon"] == BEST_HORIZON and r["proof_unit_type"] == BEST_PROOF
    ]
    recompute = compute_metrics(best_tuple_rows)
    prior_best_row = next(
        r for r in report_rows
        if r["variant_name"] == BEST_VARIANT and r["window"] == BEST_WINDOW and r["horizon"] == BEST_HORIZON and r["proof_unit_type"] == BEST_PROOF
    )
    recomputed_best = select_best_from_report(report_rows)

    recompute_rows = []
    for k, old_k in [
        ("sample_count", "sample_count"),
        ("retained_sample_count", "retained_sample_count"),
        ("baseline_p10", "hold_p10"),
        ("baseline_p5", "hold_p5"),
        ("baseline_p1", "hold_p1"),
        ("filtered_p10", "retained_p10"),
        ("filtered_p5", "retained_p5"),
        ("filtered_p1", "retained_p1"),
        ("tail_improvement_p10", "tail_improvement_p10"),
        ("tail_improvement_p5", "tail_improvement_p5"),
        ("tail_improvement_p1", "tail_improvement_p1"),
        ("opportunity_retention_rate", "opportunity_retention_rate"),
        ("false_quarantine_rate", "false_quarantine_rate"),
        ("missed_profit_rate", "missed_profit_rate"),
        ("worst_pool_contribution", "worst_pool_contribution"),
        ("worst_regime_contribution", "worst_regime_contribution"),
    ]:
        new_v = recompute.get(k)
        old_v = parse_num(prior_best_row.get(old_k)) if old_k != "sample_count" and old_k != "retained_sample_count" else int(prior_best_row.get(old_k) or 0)
        diff = None
        if isinstance(old_v, (int, float)) and isinstance(new_v, (int, float)):
            diff = float(new_v) - float(old_v)
        recompute_rows.append({"metric": k, "recomputed": new_v, "reported": old_v, "diff": diff})

    write_csv(REPORT_DIR / "best_variant_recompute.csv", recompute_rows, ["metric", "recomputed", "reported", "diff"])
    corrected_best = select_best_corrected(all_rows, BEST_WINDOW, BEST_HORIZON, BEST_PROOF)
    write_text(
        REPORT_DIR / "BEST_VARIANT_RECOMPUTE_CN.md",
        "\n".join(
            [
                "# Best Variant Recompute",
                "",
                f"- best_variant_reported: {prior_final['best_variant_name']}",
                f"- best_variant_recomputed_from_report_ranking: {recomputed_best['variant_name'] if recomputed_best else ''}",
                f"- best_variant_recomputed_corrected: {corrected_best['variant_name'] if corrected_best else ''}",
                f"- best_variant_still_same: {'yes' if recomputed_best and recomputed_best['variant_name'] == BEST_VARIANT else 'no'}",
                f"- best_variant_still_same_corrected: {'yes' if corrected_best and corrected_best['variant_name'] == BEST_VARIANT else 'no'}",
                f"- recompute_window: {BEST_WINDOW}",
                f"- recompute_horizon: {BEST_HORIZON}",
                f"- recompute_proof_unit: {BEST_PROOF}",
                f"- data_quality_status: {recompute['data_quality_status']}",
                f"- sample_count: {recompute['sample_count']}",
                f"- retained_sample_count: {recompute['retained_sample_count']}",
                f"- baseline_p10/p5/p1: {fmt(recompute['baseline_p10'])} / {fmt(recompute['baseline_p5'])} / {fmt(recompute['baseline_p1'])}",
                f"- filtered_p10/p5/p1: {fmt(recompute['filtered_p10'])} / {fmt(recompute['filtered_p5'])} / {fmt(recompute['filtered_p1'])}",
                f"- tail_improvement_p10/p5/p1: {fmt(recompute['tail_improvement_p10'])} / {fmt(recompute['tail_improvement_p5'])} / {fmt(recompute['tail_improvement_p1'])}",
                f"- opportunity_retention_rate: {fmt(recompute['opportunity_retention_rate'])}",
                f"- false_quarantine_rate: {fmt(recompute['false_quarantine_rate'])}",
                f"- missed_profit_rate: {fmt(recompute['missed_profit_rate'])}",
                f"- worst_pool_contribution: {fmt(recompute['worst_pool_contribution'])}",
                f"- worst_regime_contribution: {fmt(recompute['worst_regime_contribution'])}",
                f"- differences_explainable: {'yes' if all((abs((r['diff'] or 0.0)) < 1e-9) for r in recompute_rows if r['diff'] is not None) else 'no'}",
                "- recompute_note: prior V1 report mixed quarantine 0.0 into filtered distribution and used filtered_values length as retained_sample_count.",
            ]
        )
        + "\n",
    )

    time_rows = []
    window_verdicts = {}
    for window in WINDOWS:
        metrics = compute_metrics([r for r in best_variant_rows if r["window"] == window and r["horizon"] == BEST_HORIZON and r["proof_unit_type"] == BEST_PROOF])
        verdict = row_verdict(metrics)
        window_verdicts[window] = verdict
        time_rows.append({"window": window, **{k: metrics[k] for k in [
            "retained_sample_count", "baseline_p10", "baseline_p5", "baseline_p1",
            "filtered_p10", "filtered_p5", "filtered_p1", "tail_improvement_p10",
            "tail_improvement_p5", "tail_improvement_p1", "opportunity_retention_rate",
            "false_quarantine_rate", "missed_profit_rate"]}, "verdict": verdict})
    write_csv(REPORT_DIR / "time_window_robustness.csv", time_rows, [
        "window", "retained_sample_count", "baseline_p10", "baseline_p5", "baseline_p1",
        "filtered_p10", "filtered_p5", "filtered_p1", "tail_improvement_p10", "tail_improvement_p5",
        "tail_improvement_p1", "opportunity_retention_rate", "false_quarantine_rate",
        "missed_profit_rate", "verdict"
    ])
    if sum(1 for v in time_rows if (v["tail_improvement_p10"] or 0) > 0 and (v["tail_improvement_p5"] or 0) > 0 and (v["tail_improvement_p1"] or 0) > 0) == 1 and window_verdicts.get("recent_72h") in {"PASS", "WARN"}:
        time_window_robustness = "NARROW_72H_ONLY"
    elif all(v["verdict"] in {"PASS", "WARN"} for v in time_rows[1:]):
        time_window_robustness = "BROAD"
    else:
        time_window_robustness = "MIXED"
    write_text(
        REPORT_DIR / "TIME_WINDOW_ROBUSTNESS_CN.md",
        "# Time Window Robustness\n\n"
        + "\n".join(
            [
                f"- {r['window']}: retained={r['retained_sample_count']}, "
                f"tail_improvement_p10/p5/p1={fmt(r['tail_improvement_p10'])}/{fmt(r['tail_improvement_p5'])}/{fmt(r['tail_improvement_p1'])}, "
                f"opportunity_retention_rate={fmt(r['opportunity_retention_rate'])}, "
                f"false_quarantine_rate={fmt(r['false_quarantine_rate'])}, missed_profit_rate={fmt(r['missed_profit_rate'])}, verdict={r['verdict']}"
                for r in time_rows
            ]
        )
        + f"\n\n- time_window_robustness: {time_window_robustness}\n",
    )

    horizon_rows = []
    horizon_verdicts = {}
    for horizon in HORIZONS:
        metrics = compute_metrics([r for r in best_variant_rows if r["window"] == BEST_WINDOW and r["horizon"] == horizon and r["proof_unit_type"] == BEST_PROOF])
        verdict = row_verdict(metrics)
        horizon_verdicts[horizon] = verdict
        horizon_rows.append({"horizon": horizon, **{k: metrics[k] for k in [
            "retained_sample_count", "baseline_p10", "baseline_p5", "baseline_p1",
            "filtered_p10", "filtered_p5", "filtered_p1", "tail_improvement_p10",
            "tail_improvement_p5", "tail_improvement_p1", "opportunity_retention_rate",
            "false_quarantine_rate", "missed_profit_rate"]}, "verdict": verdict})
    write_csv(REPORT_DIR / "horizon_robustness.csv", horizon_rows, [
        "horizon", "retained_sample_count", "baseline_p10", "baseline_p5", "baseline_p1",
        "filtered_p10", "filtered_p5", "filtered_p1", "tail_improvement_p10", "tail_improvement_p5",
        "tail_improvement_p1", "opportunity_retention_rate", "false_quarantine_rate",
        "missed_profit_rate", "verdict"
    ])
    positive_horizons = sum(1 for r in horizon_rows if (r["tail_improvement_p10"] or 0) > 0 and (r["tail_improvement_p5"] or 0) > 0 and (r["tail_improvement_p1"] or 0) > 0)
    horizon_robustness = "2H_ONLY" if positive_horizons == 1 and horizon_verdicts.get("2h") in {"PASS", "WARN"} else ("BROAD" if positive_horizons >= 3 else "MIXED")
    write_text(
        REPORT_DIR / "HORIZON_ROBUSTNESS_CN.md",
        "# Horizon Robustness\n\n"
        + "\n".join(
            [
                f"- {r['horizon']}: retained={r['retained_sample_count']}, "
                f"tail_improvement_p10/p5/p1={fmt(r['tail_improvement_p10'])}/{fmt(r['tail_improvement_p5'])}/{fmt(r['tail_improvement_p1'])}, "
                f"opportunity_retention_rate={fmt(r['opportunity_retention_rate'])}, "
                f"false_quarantine_rate={fmt(r['false_quarantine_rate'])}, missed_profit_rate={fmt(r['missed_profit_rate'])}, verdict={r['verdict']}"
                for r in horizon_rows
            ]
        )
        + f"\n\n- horizon_robustness: {horizon_robustness}\n",
    )

    best_valid_rows = valid_rows(best_tuple_rows)
    retained_rows = [r for r in best_valid_rows if r["entry_allowed"]]
    filtered_rows = [r for r in best_valid_rows if not r["entry_allowed"]]
    total_loss_before = sum(abs(r["hold_to_horizon_pnl_pct"]) for r in best_valid_rows if (r["hold_to_horizon_pnl_pct"] or 0) < 0)
    total_loss_after = sum(abs(r["hold_to_horizon_pnl_pct"]) for r in retained_rows if (r["hold_to_horizon_pnl_pct"] or 0) < 0)
    before_pool = Counter()
    after_pool = Counter()
    before_regime = Counter()
    after_regime = Counter()
    filtered_negative_regime = Counter()
    for r in best_valid_rows:
        hold = r["hold_to_horizon_pnl_pct"] or 0.0
        if hold < 0:
            before_pool[r["pool_id"]] += abs(hold)
            before_regime[r["regime_primary"]] += abs(hold)
    for r in retained_rows:
        hold = r["hold_to_horizon_pnl_pct"] or 0.0
        if hold < 0:
            after_pool[r["pool_id"]] += abs(hold)
            after_regime[r["regime_primary"]] += abs(hold)
    for r in filtered_rows:
        hold = r["hold_to_horizon_pnl_pct"] or 0.0
        if hold < 0:
            filtered_negative_regime[r["regime_primary"]] += abs(hold)
    total_filtered_neg = sum(filtered_negative_regime.values())
    contribution_rows = [
        {
            "top_pool_before": before_pool.most_common(1)[0][0] if before_pool else "",
            "top_pool_before_share": (before_pool.most_common(1)[0][1] / total_loss_before) if before_pool and total_loss_before else None,
            "top_pool_after": after_pool.most_common(1)[0][0] if after_pool else "",
            "top_pool_after_share": (after_pool.most_common(1)[0][1] / total_loss_after) if after_pool and total_loss_after else None,
            "top_regime_before": before_regime.most_common(1)[0][0] if before_regime else "",
            "top_regime_before_share": (before_regime.most_common(1)[0][1] / total_loss_before) if before_regime and total_loss_before else None,
            "top_regime_after": after_regime.most_common(1)[0][0] if after_regime else "",
            "top_regime_after_share": (after_regime.most_common(1)[0][1] / total_loss_after) if after_regime and total_loss_after else None,
            "data_stale_filtered_loss_share": (filtered_negative_regime["DATA_STALE_OR_INCOMPLETE"] / total_filtered_neg) if total_filtered_neg else None,
            "healthy_short_hold_retained_share": sum(1 for r in retained_rows if r["regime_primary"] == "HEALTHY_SHORT_HOLD") / len(retained_rows) if retained_rows else None,
            "stable_fee_retained_share": sum(1 for r in retained_rows if r["regime_primary"] == "STABLE_FEE") / len(retained_rows) if retained_rows else None,
            "toxic_regimes_filtered_ratio": sum(1 for r in filtered_rows if r["regime_primary"] in BAD_REGIMES) / len([r for r in best_valid_rows if r["regime_primary"] in BAD_REGIMES]) if [r for r in best_valid_rows if r["regime_primary"] in BAD_REGIMES] else None,
            "filtered_out_loss_sample_share": sum(1 for r in filtered_rows if (r["hold_to_horizon_pnl_pct"] or 0) < 0) / len(filtered_rows) if filtered_rows else None,
            "filtered_out_profit_sample_share": sum(1 for r in filtered_rows if (r["hold_to_horizon_pnl_pct"] or 0) > 0) / len(filtered_rows) if filtered_rows else None,
        }
    ]
    write_csv(REPORT_DIR / "contribution_attribution.csv", contribution_rows, list(contribution_rows[0].keys()))
    data_stale_main = (contribution_rows[0]["data_stale_filtered_loss_share"] or 0) > 0.5
    few_pools_dominate = (contribution_rows[0]["top_pool_after_share"] or 0) > 0.5
    write_text(
        REPORT_DIR / "CONTRIBUTION_ATTRIBUTION_CN.md",
        "# Contribution Attribution\n\n"
        f"- top_pool_before_share: {fmt(contribution_rows[0]['top_pool_before_share'])}\n"
        f"- top_pool_after_share: {fmt(contribution_rows[0]['top_pool_after_share'])}\n"
        f"- top_regime_before_share: {fmt(contribution_rows[0]['top_regime_before_share'])}\n"
        f"- top_regime_after_share: {fmt(contribution_rows[0]['top_regime_after_share'])}\n"
        f"- DATA_STALE_OR_INCOMPLETE_filtered_loss_share: {fmt(contribution_rows[0]['data_stale_filtered_loss_share'])}\n"
        f"- HEALTHY_SHORT_HOLD_retained_share: {fmt(contribution_rows[0]['healthy_short_hold_retained_share'])}\n"
        f"- STABLE_FEE_retained_share: {fmt(contribution_rows[0]['stable_fee_retained_share'])}\n"
        f"- toxic_regimes_filtered_ratio: {fmt(contribution_rows[0]['toxic_regimes_filtered_ratio'])}\n"
        f"- filtered_out_loss_sample_share: {fmt(contribution_rows[0]['filtered_out_loss_sample_share'])}\n"
        f"- filtered_out_profit_sample_share: {fmt(contribution_rows[0]['filtered_out_profit_sample_share'])}\n"
        f"- tail_improvement_mainly_from_data_stale: {'yes' if data_stale_main else 'no'}\n"
        f"- few_pools_dominate_after_filter: {'yes' if few_pools_dominate else 'no'}\n"
        f"- data_freshness_fix_preferred_before_review: {'yes' if data_stale_main else 'no'}\n",
    )

    missed_profit_rows = [r for r in best_valid_rows if (not r["entry_allowed"]) and (r["hold_to_horizon_pnl_pct"] or 0) > 0]
    loss_avoided_rows = [r for r in best_valid_rows if (not r["entry_allowed"]) and (r["hold_to_horizon_pnl_pct"] or 0) < 0]
    missed_profit_values = [r["hold_to_horizon_pnl_pct"] for r in missed_profit_rows]
    loss_avoided_values = [abs(r["hold_to_horizon_pnl_pct"]) for r in loss_avoided_rows]
    missed_profit_count_rate = len(missed_profit_rows) / len([r for r in best_valid_rows if (r["hold_to_horizon_pnl_pct"] or 0) > 0]) if [r for r in best_valid_rows if (r["hold_to_horizon_pnl_pct"] or 0) > 0] else None
    false_quarantine_count_rate = len(missed_profit_rows) / len(best_valid_rows) if best_valid_rows else None
    net_tradeoff_score = sum(loss_avoided_values) - sum(missed_profit_values)
    acceptable = not ((recompute["missed_profit_rate"] or 0) > 0.2 or (recompute["false_quarantine_rate"] or 0) > 0.2)
    mp_rows = [{
        "missed_profit_count": len(missed_profit_rows),
        "missed_profit_rate": recompute["missed_profit_rate"],
        "missed_profit_count_rate": missed_profit_count_rate,
        "missed_profit_p50": median(missed_profit_values),
        "missed_profit_p90": percentile(missed_profit_values, 0.90),
        "missed_profit_p99": percentile(missed_profit_values, 0.99),
        "false_quarantine_count": len(missed_profit_rows),
        "false_quarantine_rate": recompute["false_quarantine_rate"],
        "false_quarantine_count_rate": false_quarantine_count_rate,
        "loss_avoided_count": len(loss_avoided_rows),
        "loss_avoidance_rate": recompute["loss_avoidance_rate"],
        "loss_avoided_p50": median(loss_avoided_values),
        "loss_avoided_p90": percentile(loss_avoided_values, 0.90),
        "loss_avoided_p99": percentile(loss_avoided_values, 0.99),
        "net_tradeoff_score": net_tradeoff_score,
        "acceptable": acceptable,
    }]
    write_csv(REPORT_DIR / "missed_profit_false_quarantine_audit.csv", mp_rows, list(mp_rows[0].keys()))
    write_text(
        REPORT_DIR / "MISSED_PROFIT_FALSE_QUARANTINE_AUDIT_CN.md",
        "# Missed Profit / False Quarantine Audit\n\n"
        f"- missed_profit_count: {len(missed_profit_rows)}\n"
        f"- missed_profit_rate: {fmt(recompute['missed_profit_rate'])}\n"
        f"- missed_profit_count_rate: {fmt(missed_profit_count_rate)}\n"
        f"- missed_profit_p50/p90/p99: {fmt(mp_rows[0]['missed_profit_p50'])} / {fmt(mp_rows[0]['missed_profit_p90'])} / {fmt(mp_rows[0]['missed_profit_p99'])}\n"
        f"- false_quarantine_count: {len(missed_profit_rows)}\n"
        f"- false_quarantine_rate: {fmt(recompute['false_quarantine_rate'])}\n"
        f"- false_quarantine_count_rate: {fmt(false_quarantine_count_rate)}\n"
        f"- loss_avoided_count: {len(loss_avoided_rows)}\n"
        f"- loss_avoidance_rate: {fmt(recompute['loss_avoidance_rate'])}\n"
        f"- net_tradeoff_score: {fmt(net_tradeoff_score)}\n"
        f"- acceptable: {'yes' if acceptable else 'no'}\n",
    )

    suspicious_features = [
        "sample bucket_start matched to classifier row built from bucket_end = bucket_start + 15m",
        "price_move_5m / 15m / 30m / 1h derived from marks up to classifier bucket_end",
        "volume_change_15m / 30m / 1h derived from marks up to classifier bucket_end",
        "tvl_change_1h derived from marks up to classifier bucket_end",
        "stale_data_flag and data_quality_score computed at classifier bucket_end, not guaranteed pre-entry",
    ]
    required_fix = [
        "shift regime lookup to previous fully known bucket before sample start",
        "recompute regime features with entry-safe timestamps only",
        "downgrade same-bucket freshness/price/volume/tvl features to diagnostic-only until alignment is fixed",
        "rerun regime-aware short-hold counterfactual after temporal alignment fix",
    ]
    lookahead = {
        "lookahead_risk": "HIGH",
        "leakage_found": True,
        "suspicious_features": suspicious_features,
        "required_fix": required_fix,
    }
    write_json(REPORT_DIR / "lookahead_leakage_audit.json", lookahead)
    write_text(
        REPORT_DIR / "LOOKAHEAD_LEAKAGE_AUDIT_CN.md",
        "# Lookahead / Leakage Audit\n\n"
        "- leakage_found: yes\n"
        "- lookahead_risk: HIGH\n"
        "- key_evidence:\n"
        "  regime classifier rows are materialized by completed 15m bucket_end, but the counterfactual maps sample start bucket_start directly onto that row.\n"
        "  This allows same-bucket post-entry marks to influence regime classification for the sample.\n"
        f"- suspicious_features: {', '.join(suspicious_features)}\n"
        f"- required_fix: {', '.join(required_fix)}\n",
    )

    tail_improvement_reproduced = all(
        recompute[k] is not None and prior_best[k] is not None and abs(recompute[k] - prior_best[k]) < 1e-9
        for k in ["tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1"]
    )
    if lookahead["leakage_found"]:
        review_v2_status = "FAIL"
        recommended_next_stage = "POOL_REGIME_RULE_FIX"
        status = "FAIL"
    else:
        if tail_improvement_reproduced and time_window_robustness == "BROAD" and horizon_robustness == "BROAD" and acceptable:
            review_v2_status = "PASS"
            recommended_next_stage = "POOL_REGIME_AWARE_SHORT_HOLD_REVIEW_V3"
            status = "PASS"
        elif tail_improvement_reproduced:
            review_v2_status = "WARN"
            recommended_next_stage = "POOL_REGIME_AWARE_SHORT_HOLD_REVIEW_V3"
            status = "WARN"
        else:
            review_v2_status = "FAIL"
            recommended_next_stage = "STOP_RESEARCH"
            status = "FAIL"

    review_summary = {
        "tail_improvement_reproduced": tail_improvement_reproduced,
        "time_window_robustness": time_window_robustness,
        "horizon_robustness": horizon_robustness,
        "missed_profit_rate": recompute["missed_profit_rate"],
        "false_quarantine_rate": recompute["false_quarantine_rate"],
        "lookahead_risk": lookahead["lookahead_risk"],
        "leakage_found": lookahead["leakage_found"],
        "review_v2_status": review_v2_status,
        "recommended_next_stage": recommended_next_stage,
    }
    write_json(REPORT_DIR / "pool_regime_aware_review_v2.json", review_summary)
    write_text(
        REPORT_DIR / "POOL_REGIME_AWARE_REVIEW_V2_CN.md",
        "# Pool Regime Aware Review V2\n\n"
        f"- tail_improvement_reproduced: {'yes' if tail_improvement_reproduced else 'no'}\n"
        f"- time_window_robustness: {time_window_robustness}\n"
        f"- horizon_robustness: {horizon_robustness}\n"
        f"- missed_profit_rate: {fmt(recompute['missed_profit_rate'])}\n"
        f"- false_quarantine_rate: {fmt(recompute['false_quarantine_rate'])}\n"
        f"- lookahead_risk: {lookahead['lookahead_risk']}\n"
        f"- leakage_found: {'yes' if lookahead['leakage_found'] else 'no'}\n"
        f"- review_v2_status: {review_v2_status}\n",
    )
    write_json(
        REPORT_DIR / "pool_regime_aware_review_next_stage_decision.json",
        {"recommended_next_stage": recommended_next_stage, "review_v2_status": review_v2_status},
    )
    write_text(
        REPORT_DIR / "POOL_REGIME_AWARE_REVIEW_NEXT_STAGE_DECISION_CN.md",
        "# Pool Regime Aware Review Next Stage Decision\n\n"
        f"- recommended_next_stage: {recommended_next_stage}\n"
        f"- review_v2_status: {review_v2_status}\n",
    )

    final_verdict = {
        "status": status,
        "stage": "POOL_REGIME_AWARE_SHORT_HOLD_REVIEW_V2",
        "data_source": "vps_postgres",
        "db_ready": True,
        "best_variant_name": BEST_VARIANT,
        "best_window": BEST_WINDOW,
        "best_horizon": BEST_HORIZON,
        "best_proof_unit": BEST_PROOF,
        "tail_improvement_reproduced": tail_improvement_reproduced,
        "time_window_robustness": time_window_robustness,
        "horizon_robustness": horizon_robustness,
        "missed_profit_rate": recompute["missed_profit_rate"],
        "false_quarantine_rate": recompute["false_quarantine_rate"],
        "lookahead_risk": lookahead["lookahead_risk"],
        "leakage_found": lookahead["leakage_found"],
        "review_v2_status": review_v2_status,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": recommended_next_stage,
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final_verdict)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# Pool Regime Aware Short Hold Review V2\n\n"
        f"- status: {status}\n"
        f"- best_variant_name: {BEST_VARIANT}\n"
        f"- best_window: {BEST_WINDOW}\n"
        f"- best_horizon: {BEST_HORIZON}\n"
        f"- best_proof_unit: {BEST_PROOF}\n"
        f"- tail_improvement_reproduced: {'yes' if tail_improvement_reproduced else 'no'}\n"
        f"- time_window_robustness: {time_window_robustness}\n"
        f"- horizon_robustness: {horizon_robustness}\n"
        f"- missed_profit_rate: {fmt(recompute['missed_profit_rate'])}\n"
        f"- false_quarantine_rate: {fmt(recompute['false_quarantine_rate'])}\n"
        f"- lookahead_risk: {lookahead['lookahead_risk']}\n"
        f"- leakage_found: {'yes' if lookahead['leakage_found'] else 'no'}\n"
        f"- review_v2_status: {review_v2_status}\n"
        f"- recommended_next_stage: {recommended_next_stage}\n"
        "- tiny_canary_allowed: no\n",
    )
    artifact_index = [
        "INPUT_ARTIFACT_AUDIT_CN.md",
        "input_artifact_audit.json",
        "VPS_DB_QUICK_CHECK_CN.md",
        "BEST_VARIANT_RECOMPUTE_CN.md",
        "best_variant_recompute.csv",
        "TIME_WINDOW_ROBUSTNESS_CN.md",
        "time_window_robustness.csv",
        "HORIZON_ROBUSTNESS_CN.md",
        "horizon_robustness.csv",
        "CONTRIBUTION_ATTRIBUTION_CN.md",
        "contribution_attribution.csv",
        "MISSED_PROFIT_FALSE_QUARANTINE_AUDIT_CN.md",
        "missed_profit_false_quarantine_audit.csv",
        "LOOKAHEAD_LEAKAGE_AUDIT_CN.md",
        "lookahead_leakage_audit.json",
        "POOL_REGIME_AWARE_REVIEW_V2_CN.md",
        "pool_regime_aware_review_v2.json",
        "POOL_REGIME_AWARE_REVIEW_NEXT_STAGE_DECISION_CN.md",
        "pool_regime_aware_review_next_stage_decision.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
        "ARTIFACT_INDEX.md",
        "pool_regime_aware_review_v2_readonly.py",
    ]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "# Artifact Index\n\n" + "\n".join(f"- {x}" for x in artifact_index) + "\n")


if __name__ == "__main__":
    main()
