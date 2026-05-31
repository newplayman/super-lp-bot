#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import shlex
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
REPORT_DIR = REPO_ROOT / "reports" / "pool_regime_aware_short_hold" / "20260531_095237"
PRIOR_CLASSIFIER_DIR = REPO_ROOT / "reports" / "pool_regime_classifier" / "20260531_092109"
INPUT_RISK_DIR = REPO_ROOT / "reports" / "risk_signal_definition_fix" / "20260531_080614"
P0_DIR = REPO_ROOT / "reports" / "risk_aware_short_hold" / "20260531_073906"

CLASSIFIER_RUN_ID = "20260531_092109"
SHORT_HOLD_RUN_ID = "20260531_073906"
TABLE_NAME = "pool_regime_aware_short_hold_counterfactual_v1"

WINDOW_LABELS = ["recent_24h", "recent_48h", "recent_72h", "recent_7d"]
HORIZONS = ["15m", "30m", "1h", "2h"]
PROOF_UNITS = ["pool_window", "intent_window"]
VALID_PROOF_UNITS = ["pool_window", "intent_window"]

RISK_QUARANTINE_SIGNALS = {
    "price_spike_down",
    "volume_collapse",
    "tvl_drop",
    "exit_depth_drop",
    "pool_mark_gap / stale data",
}

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


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
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


def connect_db(readonly: bool = True):
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("missing_postgres_dsn")
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=readonly, autocommit=True)
    return conn


def q(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def parse_ts(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, (int, float)):
        if v > 10_000_000_000:
            v = v / 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    s = str(v).strip()
    if not s:
        return None
    if s.isdigit():
        return parse_ts(int(s))
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_num(v):
    if v in (None, "", "null", "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def fmt_num(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.10f}".rstrip("0").rstrip(".")
    return str(v)


def median(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    vals = sorted(vals)
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def percentile(values, p):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    vals = sorted(vals)
    idx = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * p))))
    return vals[idx]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def as_float(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    try:
        return float(v)
    except Exception:
        return None


def as_bool(v):
    return bool(v)


def bucket_floor(ts_seconds: int, bucket_seconds: int = 15 * 60) -> int:
    return ts_seconds - (ts_seconds % bucket_seconds)


def window_label_for_age(age_hours: float) -> str:
    if age_hours <= 24:
        return "recent_24h"
    if age_hours <= 48:
        return "recent_48h"
    if age_hours <= 72:
        return "recent_72h"
    return "recent_7d"


def build_token_pair(pool_id: str, pools: dict[str, dict[str, Any]], meta: dict[str, dict[str, Any]]) -> str:
    m = meta.get(pool_id) or {}
    if m.get("token0_symbol") and m.get("token1_symbol"):
        return f"{m['token0_symbol']}/{m['token1_symbol']}"
    if m.get("token0") and m.get("token1"):
        return f"{str(m['token0'])[:8]}/{str(m['token1'])[:8]}"
    p = pools.get(pool_id) or {}
    if p.get("token0") and p.get("token1"):
        return f"{str(p['token0'])[:8]}/{str(p['token1'])[:8]}"
    return pool_id


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_input_artifacts() -> dict[str, bool]:
    paths = {
        "pool_regime_classifier_final": PRIOR_CLASSIFIER_DIR / "FINAL_VERDICT.json",
        "pool_regime_taxonomy": PRIOR_CLASSIFIER_DIR / "POOL_REGIME_TAXONOMY_V1_CN.md",
        "pool_regime_taxonomy_json": PRIOR_CLASSIFIER_DIR / "pool_regime_taxonomy_v1.json",
        "pool_regime_features": PRIOR_CLASSIFIER_DIR / "POOL_REGIME_FEATURES_CN.md",
        "pool_regime_features_csv": PRIOR_CLASSIFIER_DIR / "pool_regime_features.csv",
        "pool_regime_materialization": PRIOR_CLASSIFIER_DIR / "POOL_REGIME_MATERIALIZATION_CN.md",
        "pool_regime_materialization_csv": PRIOR_CLASSIFIER_DIR / "pool_regime_materialization_counts.csv",
        "pool_regime_tail_audit": PRIOR_CLASSIFIER_DIR / "POOL_REGIME_TAIL_OUTCOME_AUDIT_CN.md",
        "pool_regime_tail_audit_csv": PRIOR_CLASSIFIER_DIR / "pool_regime_tail_outcome_audit.csv",
        "pool_regime_quarantine_backtest": PRIOR_CLASSIFIER_DIR / "POOL_REGIME_QUARANTINE_BACKTEST_CN.md",
        "pool_regime_quarantine_backtest_csv": PRIOR_CLASSIFIER_DIR / "pool_regime_quarantine_backtest.csv",
        "pool_regime_best_filter": PRIOR_CLASSIFIER_DIR / "POOL_REGIME_BEST_FILTER_SELECTION_CN.md",
        "pool_regime_best_filter_json": PRIOR_CLASSIFIER_DIR / "pool_regime_best_filter_selection.json",
        "pool_regime_next_stage": PRIOR_CLASSIFIER_DIR / "POOL_REGIME_NEXT_STAGE_DECISION_CN.md",
        "pool_regime_next_stage_json": PRIOR_CLASSIFIER_DIR / "pool_regime_next_stage_decision.json",
    }
    return {k: v.exists() for k, v in paths.items()}


def load_classifier_lookup(cur):
    rows = q(
        cur,
        """
        select pool_id, token_pair, bucket_start, bucket_end, window_label,
               regime_primary, regime_secondary, regime_confidence,
               should_enter, should_quarantine, should_research_only,
               risk_score, exit_depth_score, volatility_score, volume_score,
               tvl_score, data_quality_score, fee_proxy_score, rule_hits, missing_features
        from pool_regime_classifier_v1
        where run_id = %s
        """,
        (CLASSIFIER_RUN_ID,),
    )
    lookup = {}
    by_pool = defaultdict(list)
    for r in rows:
        key = (r["pool_id"], int(parse_ts(r["bucket_start"]).timestamp()), r["window_label"])
        lookup[key] = dict(r)
        by_pool[r["pool_id"]].append(dict(r))
    return lookup, by_pool, rows


def load_sample_rows(cur):
    rows = q(
        cur,
        """
        select run_id, sample_id, proof_unit_type, pool_id, token_pair, start_time, horizon,
               entry_value_source, entry_value, target_value_hold, risk_exit_time, risk_exit_value,
               first_risk_signal, risk_signal_severity, fee_proxy, exit_cost_proxy,
               hold_to_horizon_pnl_pct, risk_aware_exit_pnl_pct, no_entry_quarantine_pnl_pct,
               loss_saved_vs_hold, missed_profit_vs_hold, false_exit_flag, opportunity_flag,
               data_quality_status, invalid_reason, created_at
        from risk_aware_short_hold_counterfactual_v1
        where run_id = %s
          and proof_unit_type = any(%s)
        order by start_time
        """,
        (SHORT_HOLD_RUN_ID, VALID_PROOF_UNITS),
    )
    out = []
    now = datetime.now(timezone.utc)
    for r in rows:
        start_time = parse_ts(r["start_time"])
        if not start_time:
            continue
        age_hours = (now - start_time).total_seconds() / 3600.0
        sample_window = window_label_for_age(age_hours)
        out.append(
            {
                **dict(r),
                "start_time_dt": start_time,
                "bucket_start_dt": datetime.fromtimestamp(bucket_floor(int(start_time.timestamp())), tz=timezone.utc),
                "sample_window": sample_window,
                "age_hours": age_hours,
                "hold_pnl": parse_num(r["hold_to_horizon_pnl_pct"]),
                "risk_pnl": parse_num(r["risk_aware_exit_pnl_pct"]),
                "no_entry_quarantine_pnl": parse_num(r["no_entry_quarantine_pnl_pct"]),
                "entry_value_f": parse_num(r["entry_value"]),
                "target_value_f": parse_num(r["target_value_hold"]),
                "fee_proxy_f": parse_num(r["fee_proxy"]),
                "exit_cost_proxy_f": parse_num(r["exit_cost_proxy"]),
            }
        )
    return out


def regime_for_sample(sample, classifier_lookup):
    key = (sample["pool_id"], int(sample["bucket_start_dt"].timestamp()), sample["sample_window"])
    regime = classifier_lookup.get(key)
    if regime:
        return regime
    # fallback to any regime row for the pool on the same bucket regardless of window.
    for k, v in classifier_lookup.items():
        if k[0] == sample["pool_id"] and k[1] == int(sample["bucket_start_dt"].timestamp()):
            return v
    return None


def apply_variant(sample, regime, variant_name):
    hold = sample["hold_pnl"]
    valid = sample["data_quality_status"] == "ok" and hold is not None
    if not valid:
        return False, "invalid_sample", 0.0, False, False, False, False

    regime_primary = regime["regime_primary"] if regime else "UNKNOWN"
    risk_score = parse_num(regime["risk_score"]) if regime else None
    fee_proxy = sample["fee_proxy_f"]
    exit_cost = sample["exit_cost_proxy_f"]
    first_signal = (sample["first_risk_signal"] or "").strip()
    signal_block = first_signal in RISK_QUARANTINE_SIGNALS
    regime_block = regime_primary in BAD_REGIMES

    allowed = True
    quarantine_reason = ""

    if variant_name == "baseline_hold_all":
        allowed = True
    elif variant_name == "risk_signal_v2_quarantine_first":
        allowed = not signal_block
        if signal_block:
            quarantine_reason = f"risk_signal:{first_signal}"
    elif variant_name == "regime_exclude_data_stale":
        allowed = regime_primary != "DATA_STALE_OR_INCOMPLETE"
        if not allowed:
            quarantine_reason = "DATA_STALE_OR_INCOMPLETE"
    elif variant_name == "regime_enter_only_healthy":
        allowed = regime_primary == "HEALTHY_SHORT_HOLD"
        if not allowed:
            quarantine_reason = regime_primary or "UNKNOWN"
    elif variant_name == "regime_enter_healthy_or_stable_fee":
        allowed = regime_primary in {"HEALTHY_SHORT_HOLD", "STABLE_FEE"}
        if not allowed:
            quarantine_reason = regime_primary or "UNKNOWN"
    elif variant_name == "regime_exclude_bad_all":
        allowed = not regime_block
        if not allowed:
            quarantine_reason = regime_primary or "UNKNOWN"
    elif variant_name == "regime_score_threshold_loose":
        allowed = risk_score is not None and risk_score <= 35.0
        if not allowed:
            quarantine_reason = "risk_score_gt_35"
    elif variant_name == "regime_score_threshold_strict":
        allowed = risk_score is not None and risk_score <= 20.0
        if not allowed:
            quarantine_reason = "risk_score_gt_20"
    elif variant_name == "hybrid_regime_plus_signal":
        allowed = not regime_block
        if not allowed:
            quarantine_reason = regime_primary or "UNKNOWN"
        elif signal_block:
            allowed = False
            quarantine_reason = f"risk_signal:{first_signal}"
    elif variant_name == "hybrid_regime_plus_signal_plus_fee":
        allowed = not regime_block
        if not allowed:
            quarantine_reason = regime_primary or "UNKNOWN"
        elif signal_block:
            allowed = False
            quarantine_reason = f"risk_signal:{first_signal}"
        elif fee_proxy is None or exit_cost is None or fee_proxy <= exit_cost:
            allowed = False
            quarantine_reason = "fee_proxy_vs_exit_cost_low"
    else:
        raise KeyError(variant_name)

    pnl = hold if allowed else 0.0
    opportunity_retained = bool(allowed and hold > 0)
    loss_avoided = abs(hold) if (not allowed and hold < 0) else 0.0
    missed_profit = hold if (not allowed and hold > 0) else 0.0
    false_quarantine = bool(not allowed and hold > 0)
    return allowed, quarantine_reason, pnl, opportunity_retained, loss_avoided, missed_profit, false_quarantine


def variant_definitions():
    return [
        {
            "variant_name": "baseline_hold_all",
            "entry_filter_rule": "none",
            "no_entry_quarantine_rule": "none",
            "risk_exit_rule": "none",
            "expected_false_quarantine_risk": "none",
            "expected_missed_profit_risk": "none",
            "data_requirements": ["hold_to_horizon_pnl_pct"],
            "known_limitations": "Baseline only.",
        },
        {
            "variant_name": "risk_signal_v2_quarantine_first",
            "entry_filter_rule": "quarantine on quarantine-first price/volume/depth signal",
            "no_entry_quarantine_rule": "price_spike_down, volume_collapse, tvl_drop, exit_depth_drop, pool_mark_gap / stale data",
            "risk_exit_rule": "none",
            "expected_false_quarantine_risk": "medium",
            "expected_missed_profit_risk": "low",
            "data_requirements": ["first_risk_signal", "hold_to_horizon_pnl_pct"],
            "known_limitations": "Uses precomputed signal classification only.",
        },
        {
            "variant_name": "regime_exclude_data_stale",
            "entry_filter_rule": "exclude DATA_STALE_OR_INCOMPLETE",
            "no_entry_quarantine_rule": "DATA_STALE_OR_INCOMPLETE",
            "risk_exit_rule": "none",
            "expected_false_quarantine_risk": "medium",
            "expected_missed_profit_risk": "low",
            "data_requirements": ["regime_primary", "data_quality_score"],
            "known_limitations": "Single-factor freshness filter.",
        },
        {
            "variant_name": "regime_enter_only_healthy",
            "entry_filter_rule": "enter HEALTHY_SHORT_HOLD only",
            "no_entry_quarantine_rule": "all others",
            "risk_exit_rule": "none",
            "expected_false_quarantine_risk": "high",
            "expected_missed_profit_risk": "high",
            "data_requirements": ["regime_primary"],
            "known_limitations": "Very selective.",
        },
        {
            "variant_name": "regime_enter_healthy_or_stable_fee",
            "entry_filter_rule": "enter HEALTHY_SHORT_HOLD or STABLE_FEE",
            "no_entry_quarantine_rule": "all others",
            "risk_exit_rule": "none",
            "expected_false_quarantine_risk": "medium",
            "expected_missed_profit_risk": "medium",
            "data_requirements": ["regime_primary"],
            "known_limitations": "May still admit volatile but liquid pools.",
        },
        {
            "variant_name": "regime_exclude_bad_all",
            "entry_filter_rule": "exclude all bad regimes",
            "no_entry_quarantine_rule": "bad regimes",
            "risk_exit_rule": "none",
            "expected_false_quarantine_risk": "medium",
            "expected_missed_profit_risk": "medium",
            "data_requirements": ["regime_primary"],
            "known_limitations": "Relies on regime classifier quality.",
        },
        {
            "variant_name": "regime_score_threshold_loose",
            "entry_filter_rule": "risk_score <= 35",
            "no_entry_quarantine_rule": "risk_score > 35",
            "risk_exit_rule": "none",
            "expected_false_quarantine_risk": "medium",
            "expected_missed_profit_risk": "medium",
            "data_requirements": ["risk_score"],
            "known_limitations": "Threshold chosen from prior classifier range.",
        },
        {
            "variant_name": "regime_score_threshold_strict",
            "entry_filter_rule": "risk_score <= 20",
            "no_entry_quarantine_rule": "risk_score > 20",
            "risk_exit_rule": "none",
            "expected_false_quarantine_risk": "high",
            "expected_missed_profit_risk": "high",
            "data_requirements": ["risk_score"],
            "known_limitations": "May over-filter and shrink sample too much.",
        },
        {
            "variant_name": "hybrid_regime_plus_signal",
            "entry_filter_rule": "regime not bad and signal not quarantine",
            "no_entry_quarantine_rule": "bad regimes + quarantine-first signal",
            "risk_exit_rule": "none",
            "expected_false_quarantine_risk": "medium",
            "expected_missed_profit_risk": "low",
            "data_requirements": ["regime_primary", "first_risk_signal"],
            "known_limitations": "Two-stage filter can overfit if signal dominates.",
        },
        {
            "variant_name": "hybrid_regime_plus_signal_plus_fee",
            "entry_filter_rule": "regime not bad, signal not quarantine, fee_proxy > exit_cost_proxy",
            "no_entry_quarantine_rule": "bad regimes + quarantine signal + fee proxy weak",
            "risk_exit_rule": "none",
            "expected_false_quarantine_risk": "medium",
            "expected_missed_profit_risk": "medium",
            "data_requirements": ["regime_primary", "first_risk_signal", "fee_proxy", "exit_cost_proxy"],
            "known_limitations": "Most conservative; sample may shrink quickly.",
        },
    ]


@dataclass
class GroupStats:
    sample_count: int = 0
    valid_sample_count: int = 0
    entry_allowed_count: int = 0
    quarantined_count: int = 0
    invalid_count: int = 0
    hold_values: list[float] = None
    filtered_values: list[float] = None
    retained_opportunities: int = 0
    total_opportunities: int = 0
    filtered_opportunities: int = 0
    total_losses: int = 0
    filtered_losses: int = 0
    loss_avoided_sum: float = 0.0
    missed_profit_sum: float = 0.0
    false_quarantine_count: int = 0
    fee_proxy_count: int = 0
    exit_cost_count: int = 0
    regime_counts: Counter = None
    quarantine_reason_counts: Counter = None
    data_quality_counts: Counter = None
    pool_loss: Counter = None
    regime_loss: Counter = None

    def __post_init__(self):
        self.hold_values = []
        self.filtered_values = []
        self.regime_counts = Counter()
        self.quarantine_reason_counts = Counter()
        self.data_quality_counts = Counter()
        self.pool_loss = Counter()
        self.regime_loss = Counter()


def group_key(variant, sample, proof_unit):
    return (variant, sample["sample_window"], sample["horizon"], proof_unit)


def main() -> None:
    bootstrap_env()
    run_id = os.environ.get("RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_dir = REPO_ROOT / "reports" / "pool_regime_aware_short_hold" / run_id
    ensure_dir(report_dir)

    input_exists = load_input_artifacts()
    classifier_verdict = load_json(PRIOR_CLASSIFIER_DIR / "FINAL_VERDICT.json")
    classifier_next_stage = load_json(PRIOR_CLASSIFIER_DIR / "pool_regime_next_stage_decision.json")
    classifier_best = load_json(PRIOR_CLASSIFIER_DIR / "pool_regime_best_filter_selection.json")
    classifier_taxonomy = load_json(PRIOR_CLASSIFIER_DIR / "pool_regime_taxonomy_v1.json")

    conn = connect_db(readonly=True)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("select current_database(), current_user")
        db_name, db_user = cur.fetchone()
        pools = {r["pool_id"]: dict(r) for r in q(cur, "select pool_id, chain, protocol, token0, token1, fee_bps, tier, tvl_usd, vol_24h, fee_apr_24h from pools")}
        meta = {r["pool_id"]: dict(r) for r in q(cur, "select pool_id, token0, token1, token0_symbol, token1_symbol, token0_decimals, token1_decimals from pool_token_metadata")}
        clf_lookup, clf_by_pool, clf_rows = load_classifier_lookup(cur)
        samples = load_sample_rows(cur)
    conn.close()

    # Input audit
    input_md = [
        "# Input Artifact Audit",
        "",
    ]
    for name, exists in input_exists.items():
        input_md.append(f"- {name}: {'yes' if exists else 'no'}")
    input_md.extend(
        [
            "",
            f"- pool_regime_classifier_review_ready: {'yes' if classifier_verdict.get('review_ready') else 'no'}",
            f"- best_filter_name_is_exclude_DATA_STALE_OR_INCOMPLETE: {'yes' if classifier_best.get('best_filter_name') == 'exclude_DATA_STALE_OR_INCOMPLETE' else 'no'}",
            f"- tail_improved_confirmed: {'yes' if classifier_verdict.get('tail_improved') else 'no'}",
            f"- tiny_canary_allowed_confirmed: {'yes' if classifier_verdict.get('tiny_canary_allowed') == 'no' else 'no'}",
            f"- regime_aware_short_hold_counterfactual_possible: {'yes' if input_exists.get('pool_regime_classifier_final') and input_exists.get('pool_regime_quarantine_backtest_csv') else 'no'}",
            "- edge_proven: no",
        ]
    )
    write_text(report_dir / "INPUT_ARTIFACT_AUDIT_CN.md", "\n".join(input_md) + "\n")
    write_json(
        report_dir / "input_artifact_audit.json",
        {
            **input_exists,
            "pool_regime_classifier_review_ready": bool(classifier_verdict.get("review_ready")),
            "best_filter_name_is_exclude_DATA_STALE_OR_INCOMPLETE": classifier_best.get("best_filter_name") == "exclude_DATA_STALE_OR_INCOMPLETE",
            "tail_improved_confirmed": bool(classifier_verdict.get("tail_improved")),
            "tiny_canary_allowed_confirmed": classifier_verdict.get("tiny_canary_allowed") == "no",
            "regime_aware_short_hold_counterfactual_possible": bool(input_exists.get("pool_regime_classifier_final")) and bool(input_exists.get("pool_regime_quarantine_backtest_csv")),
            "edge_proven": "no",
        },
    )

    # DB quick check
    vps_db_md = "\n".join(
        [
            "# VPS DB Quick Check",
            "",
            "- DSN_PRESENT: yes",
            "- DB_CONNECT: ok",
            f"- DB_NAME: {db_name}",
            f"- DB_USER: {db_user}",
        ]
    )
    write_text(report_dir / "VPS_DB_QUICK_CHECK_CN.md", vps_db_md + "\n")

    # Regime-aware variants spec
    variants = variant_definitions()
    write_text(report_dir / "REGIME_AWARE_SHORT_HOLD_VARIANTS_CN.md", "# Regime Aware Short Hold Variants\n\n" + "\n".join([f"- {v['variant_name']}: {v['entry_filter_rule']}" for v in variants]) + "\n")
    write_json(report_dir / "regime_aware_short_hold_variants.json", {"variants": variants})

    # Materialize and aggregate
    group_stats: dict[tuple, GroupStats] = defaultdict(GroupStats)
    materialized_rows: list[tuple] = []
    insert_sql = f"""
        insert into {TABLE_NAME} (
            run_id, variant_name, sample_id, proof_unit_type, pool_id, token_pair, "window", horizon,
            bucket_start, bucket_end, regime_primary, regime_secondary, regime_confidence,
            entry_allowed, quarantine_reason, entry_value, target_value, fee_proxy, exit_cost_proxy,
            hold_to_horizon_pnl_pct, regime_filtered_pnl_pct, opportunity_retained, loss_avoided,
            missed_profit, false_quarantine_flag, data_quality_status, invalid_reason, created_at
        ) values %s
    """
    create_sql = f"""
        create table if not exists {TABLE_NAME} (
            run_id text not null,
            variant_name text not null,
            sample_id text not null,
            proof_unit_type text not null,
            pool_id text not null,
            token_pair text not null,
            "window" text not null,
            horizon text not null,
            bucket_start timestamptz not null,
            bucket_end timestamptz not null,
            regime_primary text not null,
            regime_secondary text not null,
            regime_confidence text not null,
            entry_allowed boolean not null,
            quarantine_reason text not null,
            entry_value double precision,
            target_value double precision,
            fee_proxy double precision,
            exit_cost_proxy double precision,
            hold_to_horizon_pnl_pct double precision,
            regime_filtered_pnl_pct double precision,
            opportunity_retained boolean not null,
            loss_avoided double precision,
            missed_profit double precision,
            false_quarantine_flag boolean not null,
            data_quality_status text not null,
            invalid_reason text not null,
            created_at timestamptz default now()
        )
    """

    write_conn = connect_db(readonly=False)
    with write_conn.cursor(cursor_factory=RealDictCursor) as wcur:
        wcur.execute(f"drop table if exists {TABLE_NAME}")
        wcur.execute(create_sql)

        batch = []
        batch_size = 5000
        for sample in samples:
            regime = regime_for_sample(sample, clf_lookup)
            if not regime:
                regime = {
                    "regime_primary": "UNKNOWN",
                    "regime_secondary": "",
                    "regime_confidence": "low",
                    "risk_score": None,
                    "exit_depth_score": None,
                    "volatility_score": None,
                    "volume_score": None,
                    "tvl_score": None,
                    "data_quality_score": 0.0,
                    "fee_proxy_score": None,
                }

            if sample["data_quality_status"] != "ok" or sample["hold_pnl"] is None:
                valid = False
            else:
                valid = True

            for variant in variants:
                entry_allowed, quarantine_reason, filtered_pnl, opp_retained, loss_avoided, missed_profit, false_quarantine = apply_variant(sample, regime, variant["variant_name"])
                reg = group_key(variant["variant_name"], sample, sample["proof_unit_type"])
                gs = group_stats[reg]
                gs.sample_count += 1
                if valid:
                    gs.valid_sample_count += 1
                    gs.hold_values.append(sample["hold_pnl"])
                    if entry_allowed:
                        gs.entry_allowed_count += 1
                        gs.filtered_values.append(filtered_pnl)
                    else:
                        gs.quarantined_count += 1
                        gs.filtered_values.append(filtered_pnl)
                    if opp_retained:
                        gs.retained_opportunities += 1
                    if sample["hold_pnl"] > 0:
                        gs.total_opportunities += 1
                        if not entry_allowed:
                            gs.filtered_opportunities += 1
                    if sample["hold_pnl"] < 0:
                        gs.total_losses += 1
                        if not entry_allowed:
                            gs.filtered_losses += 1
                    gs.loss_avoided_sum += loss_avoided
                    gs.missed_profit_sum += missed_profit
                    gs.false_quarantine_count += 1 if false_quarantine else 0
                    if sample["fee_proxy_f"] is not None:
                        gs.fee_proxy_count += 1
                    if sample["exit_cost_proxy_f"] is not None:
                        gs.exit_cost_count += 1
                    gs.regime_counts[regime["regime_primary"]] += 1
                    if quarantine_reason:
                        gs.quarantine_reason_counts[quarantine_reason] += 1
                    gs.data_quality_counts[sample["data_quality_status"]] += 1
                    if entry_allowed and sample["hold_pnl"] < 0:
                        loss = abs(sample["hold_pnl"])
                        gs.pool_loss[sample["pool_id"]] += loss
                        gs.regime_loss[regime["regime_primary"]] += loss
                else:
                    gs.invalid_count += 1
                    gs.data_quality_counts[sample["data_quality_status"]] += 1
                    if quarantine_reason:
                        gs.quarantine_reason_counts[quarantine_reason] += 1

                bucket_start_dt = sample["bucket_start_dt"]
                bucket_end_dt = bucket_start_dt + timedelta(minutes=15)
                entry_value_f = as_float(sample["entry_value_f"])
                target_value_f = as_float(sample["target_value_f"])
                fee_proxy_f = as_float(sample["fee_proxy_f"])
                exit_cost_proxy_f = as_float(sample["exit_cost_proxy_f"])
                hold_pnl = as_float(sample["hold_pnl"])
                filtered_pnl = as_float(filtered_pnl)
                opp_retained = as_bool(opp_retained)
                loss_avoided = as_float(loss_avoided) or 0.0
                missed_profit = as_float(missed_profit) or 0.0
                false_quarantine = as_bool(false_quarantine)
                materialized_rows.append(
                    (
                        sample["run_id"],
                        variant["variant_name"],
                        sample["sample_id"],
                        sample["proof_unit_type"],
                        sample["pool_id"],
                        sample["token_pair"],
                        sample["sample_window"],
                        sample["horizon"],
                        bucket_start_dt,
                        bucket_end_dt,
                        regime["regime_primary"],
                        regime.get("regime_secondary", ""),
                        regime.get("regime_confidence", "low"),
                        entry_allowed,
                        quarantine_reason,
                        entry_value_f,
                        target_value_f,
                        fee_proxy_f,
                        exit_cost_proxy_f,
                        hold_pnl,
                        filtered_pnl,
                        opp_retained,
                        loss_avoided,
                        missed_profit,
                        false_quarantine,
                        sample["data_quality_status"],
                        sample.get("invalid_reason", ""),
                        datetime.now(timezone.utc),
                    )
                )
                if len(materialized_rows) >= batch_size:
                    execute_values(wcur, insert_sql, materialized_rows, page_size=1000)
                    materialized_rows.clear()

        if materialized_rows:
            execute_values(wcur, insert_sql, materialized_rows, page_size=1000)
            materialized_rows.clear()
        wcur.execute(f"select count(*) as count from {TABLE_NAME}")
        materialized_count = wcur.fetchone()["count"]
    write_conn.close()

    # Build aggregation rows
    materialization_rows = []
    counterfactual_rows = []
    best_rows = []
    robustness_rows = []
    for (variant, window, horizon, proof_unit), gs in sorted(group_stats.items()):
        hold_p10 = percentile(gs.hold_values, 0.1)
        hold_p5 = percentile(gs.hold_values, 0.05)
        hold_p1 = percentile(gs.hold_values, 0.01)
        retained_p10 = percentile(gs.filtered_values, 0.1)
        retained_p5 = percentile(gs.filtered_values, 0.05)
        retained_p1 = percentile(gs.filtered_values, 0.01)
        tail_improve_p10 = (retained_p10 - hold_p10) if retained_p10 is not None and hold_p10 is not None else None
        tail_improve_p5 = (retained_p5 - hold_p5) if retained_p5 is not None and hold_p5 is not None else None
        tail_improve_p1 = (retained_p1 - hold_p1) if retained_p1 is not None and hold_p1 is not None else None
        false_quarantine_rate = (gs.false_quarantine_count / gs.sample_count) if gs.sample_count else None
        missed_profit_rate = (gs.missed_profit_sum / gs.total_opportunities) if gs.total_opportunities else None
        opportunity_retention_rate = (gs.retained_opportunities / gs.total_opportunities) if gs.total_opportunities else None
        loss_avoidance_rate = (gs.filtered_losses / gs.total_losses) if gs.total_losses else None
        worst_pool_contribution = (max(gs.pool_loss.values()) / sum(gs.pool_loss.values())) if gs.pool_loss else None
        worst_regime_contribution = (max(gs.regime_loss.values()) / sum(gs.regime_loss.values())) if gs.regime_loss else None
        if gs.valid_sample_count >= 100:
            if tail_improve_p10 is not None and tail_improve_p5 is not None and tail_improve_p1 is not None:
                if tail_improve_p10 > 0 and tail_improve_p5 > 0 and tail_improve_p1 > 0:
                    verdict = "PROMISING"
                elif tail_improve_p10 > -0.01 and tail_improve_p5 > -0.01:
                    verdict = "WEAK"
                else:
                    verdict = "BAD"
            else:
                verdict = "BAD"
        else:
            verdict = "INSUFFICIENT"

        materialization_rows.append(
            {
                "variant_name": variant,
                "window": window,
                "horizon": horizon,
                "proof_unit_type": proof_unit,
                "raw_sample_count": gs.sample_count,
                "valid_sample_count": gs.valid_sample_count,
                "entry_allowed_count": gs.entry_allowed_count,
                "quarantined_count": gs.quarantined_count,
                "invalid_count": gs.invalid_count,
                "data_quality_distribution": json.dumps(dict(gs.data_quality_counts), ensure_ascii=False),
                "regime_distribution": json.dumps(dict(gs.regime_counts), ensure_ascii=False),
                "quarantine_reason_distribution": json.dumps(dict(gs.quarantine_reason_counts), ensure_ascii=False),
                "fee_proxy_coverage": (gs.fee_proxy_count / gs.valid_sample_count) if gs.valid_sample_count else None,
                "exit_depth_coverage": (gs.exit_cost_count / gs.valid_sample_count) if gs.valid_sample_count else None,
            }
        )
        counterfactual_rows.append(
            {
                "variant_name": variant,
                "window": window,
                "horizon": horizon,
                "proof_unit_type": proof_unit,
                "sample_count": gs.valid_sample_count,
                "hold_median": median(gs.hold_values),
                "hold_p10": hold_p10,
                "hold_p5": hold_p5,
                "hold_p1": hold_p1,
                "retained_sample_count": len(gs.filtered_values),
                "retained_median": median(gs.filtered_values),
                "retained_p10": retained_p10,
                "retained_p5": retained_p5,
                "retained_p1": retained_p1,
                "opportunity_retention_rate": opportunity_retention_rate,
                "false_quarantine_rate": false_quarantine_rate,
                "missed_profit_rate": missed_profit_rate,
                "loss_avoidance_rate": loss_avoidance_rate,
                "tail_improvement_p10": tail_improve_p10,
                "tail_improvement_p5": tail_improve_p5,
                "tail_improvement_p1": tail_improve_p1,
                "fee_proxy_vs_exit_cost": None,
                "worst_pool_contribution": worst_pool_contribution,
                "worst_regime_contribution": worst_regime_contribution,
                "verdict": verdict,
            }
        )
        if tail_improve_p10 is not None and tail_improve_p5 is not None and tail_improve_p1 is not None:
            best_rows.append(
                {
                    "variant_name": variant,
                    "window": window,
                    "horizon": horizon,
                    "proof_unit_type": proof_unit,
                    "sample_count": gs.valid_sample_count,
                    "retained_sample_count": len(gs.filtered_values),
                    "baseline_p10": hold_p10,
                    "baseline_p5": hold_p5,
                    "baseline_p1": hold_p1,
                    "filtered_p10": retained_p10,
                    "filtered_p5": retained_p5,
                    "filtered_p1": retained_p1,
                    "tail_improvement_p10": tail_improve_p10,
                    "tail_improvement_p5": tail_improve_p5,
                    "tail_improvement_p1": tail_improve_p1,
                    "opportunity_retention_rate": opportunity_retention_rate,
                    "false_quarantine_rate": false_quarantine_rate,
                    "missed_profit_rate": missed_profit_rate,
                    "loss_avoidance_rate": loss_avoidance_rate,
                    "worst_pool_contribution": worst_pool_contribution,
                    "worst_regime_contribution": worst_regime_contribution,
                    "verdict": verdict,
                }
            )
        robustness_rows.append(
            {
                "variant_name": variant,
                "window": window,
                "horizon": horizon,
                "proof_unit_type": proof_unit,
                "tail_improvement_p10": tail_improve_p10,
                "tail_improvement_p5": tail_improve_p5,
                "tail_improvement_p1": tail_improve_p1,
                "retained_sample_count": len(gs.filtered_values),
                "false_quarantine_rate": false_quarantine_rate,
                "missed_profit_rate": missed_profit_rate,
                "opportunity_retention_rate": opportunity_retention_rate,
                "worst_pool_contribution": worst_pool_contribution,
                "worst_regime_contribution": worst_regime_contribution,
                "hold_median": median(gs.hold_values),
                "retained_median": median(gs.filtered_values),
            }
        )

    # Persist report tables
    materialization_fields = [
        "variant_name",
        "window",
        "horizon",
        "proof_unit_type",
        "raw_sample_count",
        "valid_sample_count",
        "entry_allowed_count",
        "quarantined_count",
        "invalid_count",
        "data_quality_distribution",
        "regime_distribution",
        "quarantine_reason_distribution",
        "fee_proxy_coverage",
        "exit_depth_coverage",
    ]
    counterfactual_fields = [
        "variant_name",
        "window",
        "horizon",
        "proof_unit_type",
        "sample_count",
        "hold_median",
        "hold_p10",
        "hold_p5",
        "hold_p1",
        "retained_sample_count",
        "retained_median",
        "retained_p10",
        "retained_p5",
        "retained_p1",
        "opportunity_retention_rate",
        "false_quarantine_rate",
        "missed_profit_rate",
        "loss_avoidance_rate",
        "tail_improvement_p10",
        "tail_improvement_p5",
        "tail_improvement_p1",
        "fee_proxy_vs_exit_cost",
        "worst_pool_contribution",
        "worst_regime_contribution",
        "verdict",
    ]
    write_csv(report_dir / "regime_aware_short_hold_materialization_counts.csv", materialization_rows, materialization_fields)
    write_csv(report_dir / "regime_aware_short_hold_counterfactual_report.csv", counterfactual_rows, counterfactual_fields)

    # Select best variant
    candidate_best = []
    for row in best_rows:
        if row["retained_sample_count"] < 100:
            continue
        if row["tail_improvement_p10"] is None or row["tail_improvement_p5"] is None or row["tail_improvement_p1"] is None:
            continue
        if row["tail_improvement_p10"] <= 0 or row["tail_improvement_p5"] <= 0 or row["tail_improvement_p1"] <= 0:
            continue
        if row["opportunity_retention_rate"] is not None and row["opportunity_retention_rate"] < 0.7:
            continue
        if row["false_quarantine_rate"] is not None and row["false_quarantine_rate"] > 0.5:
            continue
        if row["missed_profit_rate"] is not None and row["missed_profit_rate"] > 0.5:
            continue
        if row["worst_pool_contribution"] is not None and row["worst_pool_contribution"] > 0.6:
            continue
        candidate_best.append(row)
    candidate_best.sort(
        key=lambda r: (
            r["tail_improvement_p10"],
            r["tail_improvement_p5"],
            r["tail_improvement_p1"],
            r["opportunity_retention_rate"] or 0.0,
            -(r["false_quarantine_rate"] or 1.0),
        ),
        reverse=True,
    )
    best = candidate_best[0] if candidate_best else None

    if best:
        review_ready = bool(
            best["retained_sample_count"] >= 300
            and best["tail_improvement_p10"] > 0
            and best["tail_improvement_p5"] > 0
            and best["tail_improvement_p1"] > 0
            and (best["opportunity_retention_rate"] or 0) >= 0.7
            and (best["false_quarantine_rate"] or 1) <= 0.35
            and (best["missed_profit_rate"] or 1) <= 0.3
            and (best["worst_pool_contribution"] or 0) <= 0.6
        )
    else:
        review_ready = False

    # Robustness
    robustness_rows_out = []
    if best:
        best_variant = best["variant_name"]
        by_window = defaultdict(list)
        by_horizon = defaultdict(list)
        by_proof = defaultdict(list)
        for row in robustness_rows:
            if row["variant_name"] != best_variant:
                continue
            by_window[row["window"]].append(row)
            by_horizon[row["horizon"]].append(row)
            by_proof[row["proof_unit_type"]].append(row)

        window_signs = {k: sum(1 for r in v if r["tail_improvement_p10"] is not None and r["tail_improvement_p10"] > 0) for k, v in by_window.items()}
        horizon_signs = {k: sum(1 for r in v if r["tail_improvement_p10"] is not None and r["tail_improvement_p10"] > 0) for k, v in by_horizon.items()}
        proof_signs = {k: sum(1 for r in v if r["tail_improvement_p10"] is not None and r["tail_improvement_p10"] > 0) for k, v in by_proof.items()}
        total_window = len(by_window) or 1
        total_horizon = len(by_horizon) or 1
        total_proof = len(by_proof) or 1
        window_positive_rate = sum(1 for v in by_window.values() if any(r["tail_improvement_p10"] and r["tail_improvement_p10"] > 0 for r in v)) / total_window
        horizon_positive_rate = sum(1 for v in by_horizon.values() if any(r["tail_improvement_p10"] and r["tail_improvement_p10"] > 0 for r in v)) / total_horizon
        proof_positive_rate = sum(1 for v in by_proof.values() if any(r["tail_improvement_p10"] and r["tail_improvement_p10"] > 0 for r in v)) / total_proof
        best_pool_contrib = max((r["worst_pool_contribution"] or 0.0) for r in robustness_rows if r["variant_name"] == best_variant)
        best_regime_contrib = max((r["worst_regime_contribution"] or 0.0) for r in robustness_rows if r["variant_name"] == best_variant)
        if window_positive_rate >= 0.75 and horizon_positive_rate >= 0.75 and proof_positive_rate >= 0.75:
            robustness_status = "PASS"
            overfit_risk = "LOW" if best_pool_contrib <= 0.35 and best_regime_contrib <= 0.5 else "MEDIUM"
        elif window_positive_rate >= 0.5 and horizon_positive_rate >= 0.5:
            robustness_status = "WARN"
            overfit_risk = "MEDIUM" if best_pool_contrib <= 0.5 else "HIGH"
        else:
            robustness_status = "FAIL"
            overfit_risk = "HIGH"
        robustness_rows_out = [
            {
                "dimension": "window",
                "summary": json.dumps(window_signs, ensure_ascii=False),
                "positive_rate": window_positive_rate,
            },
            {
                "dimension": "horizon",
                "summary": json.dumps(horizon_signs, ensure_ascii=False),
                "positive_rate": horizon_positive_rate,
            },
            {
                "dimension": "proof_unit",
                "summary": json.dumps(proof_signs, ensure_ascii=False),
                "positive_rate": proof_positive_rate,
            },
            {
                "dimension": "dominance",
                "summary": json.dumps({"best_pool_contribution": best_pool_contrib, "best_regime_contribution": best_regime_contrib}, ensure_ascii=False),
                "positive_rate": None,
            },
        ]
        write_csv(report_dir / "regime_aware_robustness_audit.csv", robustness_rows_out, ["dimension", "summary", "positive_rate"])
    else:
        robustness_status = "FAIL"
        overfit_risk = "HIGH"
        write_csv(report_dir / "regime_aware_robustness_audit.csv", [], ["dimension", "summary", "positive_rate"])

    # Next stage
    if best and review_ready and robustness_status in {"PASS", "WARN"}:
        recommended_next_stage = "POOL_REGIME_AWARE_SHORT_HOLD_REVIEW_V2"
    elif best and best["worst_pool_contribution"] and best["worst_pool_contribution"] > 0.6:
        recommended_next_stage = "POOL_REGIME_RULE_FIX"
    elif best and (best["tail_improvement_p10"] or 0) > 0 and (best["retained_sample_count"] or 0) < 300:
        recommended_next_stage = "POOL_REGIME_RULE_FIX"
    elif best and best["tail_improvement_p10"] and best["tail_improvement_p10"] > 0 and (best["opportunity_retention_rate"] or 0) < 0.7:
        recommended_next_stage = "POOL_REGIME_RULE_FIX"
    elif best and any("DATA_STALE" in str(k) for k in best.keys()):
        recommended_next_stage = "POOL_REGIME_DATA_FIX"
    elif best and (best["variant_name"].startswith("hybrid") or "fee" in best["variant_name"]):
        recommended_next_stage = "FEE_VELOCITY_EXIT_DEPTH_COUNTERFACTUAL_V1"
    elif best:
        recommended_next_stage = "NEW_STRATEGY_HYPOTHESIS_DESIGN_REPEAT"
    else:
        recommended_next_stage = "STOP_RESEARCH"

    if best:
        best_variant_name = best["variant_name"]
        best_window = best["window"]
        best_horizon = best["horizon"]
        best_proof_unit = best["proof_unit_type"]
        retained_sample_count = best["retained_sample_count"]
        tail_improved = True
        tail_improvement_p10 = best["tail_improvement_p10"]
        tail_improvement_p5 = best["tail_improvement_p5"]
        tail_improvement_p1 = best["tail_improvement_p1"]
        opportunity_retention_rate = best["opportunity_retention_rate"]
        false_quarantine_rate = best["false_quarantine_rate"]
        missed_profit_rate = best["missed_profit_rate"]
        loss_avoidance_rate = best["loss_avoidance_rate"]
        worst_pool_contribution = best["worst_pool_contribution"]
        best_data_quality_status = "sufficient" if retained_sample_count >= 300 else "preliminary" if retained_sample_count >= 100 else "insufficient"
    else:
        best_variant_name = ""
        best_window = ""
        best_horizon = ""
        best_proof_unit = ""
        retained_sample_count = 0
        tail_improved = False
        tail_improvement_p10 = None
        tail_improvement_p5 = None
        tail_improvement_p1 = None
        opportunity_retention_rate = None
        false_quarantine_rate = None
        missed_profit_rate = None
        loss_avoidance_rate = None
        worst_pool_contribution = None
        best_data_quality_status = "insufficient"

    # Reports
    write_text(
        report_dir / "REGIME_AWARE_SHORT_HOLD_SCHEMA_CN.md",
        "\n".join(
            [
                "# Regime Aware Short Hold Schema",
                "",
                f"- target_table: {TABLE_NAME}",
                "- fields: run_id, variant_name, sample_id, proof_unit_type, pool_id, token_pair, window, horizon, bucket_start, bucket_end, regime_primary, regime_secondary, regime_confidence, entry_allowed, quarantine_reason, entry_value, target_value, fee_proxy, exit_cost_proxy, hold_to_horizon_pnl_pct, regime_filtered_pnl_pct, opportunity_retained, loss_avoided, missed_profit, false_quarantine_flag, data_quality_status, invalid_reason, created_at",
                "- scope: research-only",
                "- proof_unit_priority: pool_window, then intent_window",
                "- tiny_canary_allowed: no",
            ]
        )
        + "\n",
    )
    write_json(
        report_dir / "regime_aware_short_hold_schema.json",
        {
            "table_name": TABLE_NAME,
            "proof_units": PROOF_UNITS,
            "horizons": HORIZONS,
            "windows": WINDOW_LABELS,
            "fields": [
                "run_id",
                "variant_name",
                "sample_id",
                "proof_unit_type",
                "pool_id",
                "token_pair",
                "window",
                "horizon",
                "bucket_start",
                "bucket_end",
                "regime_primary",
                "regime_secondary",
                "regime_confidence",
                "entry_allowed",
                "quarantine_reason",
                "entry_value",
                "target_value",
                "fee_proxy",
                "exit_cost_proxy",
                "hold_to_horizon_pnl_pct",
                "regime_filtered_pnl_pct",
                "opportunity_retained",
                "loss_avoided",
                "missed_profit",
                "false_quarantine_flag",
                "data_quality_status",
                "invalid_reason",
                "created_at",
            ],
        },
    )
    write_text(
        report_dir / "REGIME_AWARE_SHORT_HOLD_MATERIALIZATION_CN.md",
        "\n".join(
            [
                "# Regime Aware Short Hold Materialization",
                "",
                f"- materialized_rows: {materialized_count}",
                f"- tested_variant_count: {len(variants)}",
                f"- windows: {json.dumps(WINDOW_LABELS, ensure_ascii=False)}",
                f"- horizons: {json.dumps(HORIZONS, ensure_ascii=False)}",
                f"- proof_units: {json.dumps(PROOF_UNITS, ensure_ascii=False)}",
                f"- data_quality_distribution_total: {sum(v.valid_sample_count for v in group_stats.values())}",
            ]
        )
        + "\n",
    )
    write_text(
        report_dir / "REGIME_AWARE_SHORT_HOLD_COUNTERFACTUAL_REPORT_CN.md",
        "\n".join(
            [
                "# Regime Aware Short Hold Counterfactual",
                "",
                f"- best_variant_name: {best_variant_name}",
                f"- best_window: {best_window}",
                f"- best_horizon: {best_horizon}",
                f"- best_proof_unit: {best_proof_unit}",
                f"- tail_improved: {'yes' if tail_improved else 'no'}",
                f"- retained_sample_count: {retained_sample_count}",
                f"- opportunity_retention_rate: {fmt_num(opportunity_retention_rate)}",
                f"- false_quarantine_rate: {fmt_num(false_quarantine_rate)}",
                f"- missed_profit_rate: {fmt_num(missed_profit_rate)}",
                f"- loss_avoidance_rate: {fmt_num(loss_avoidance_rate)}",
                f"- robustness_status: {robustness_status}",
                f"- overfit_risk: {overfit_risk}",
                f"- review_ready: {'yes' if review_ready else 'no'}",
            ]
        )
        + "\n",
    )
    write_csv(report_dir / "regime_aware_short_hold_counterfactual_report.csv", counterfactual_rows, counterfactual_fields)
    write_text(
        report_dir / "REGIME_AWARE_BEST_VARIANT_SELECTION_CN.md",
        "\n".join(
            [
                "# Regime Aware Best Variant Selection",
                "",
                f"- best_variant_name: {best_variant_name}",
                f"- best_window: {best_window}",
                f"- best_horizon: {best_horizon}",
                f"- best_proof_unit: {best_proof_unit}",
                f"- baseline_p10: {fmt_num(best['baseline_p10'] if best else None)}",
                f"- baseline_p5: {fmt_num(best['baseline_p5'] if best else None)}",
                f"- baseline_p1: {fmt_num(best['baseline_p1'] if best else None)}",
                f"- filtered_p10: {fmt_num(best['filtered_p10'] if best else None)}",
                f"- filtered_p5: {fmt_num(best['filtered_p5'] if best else None)}",
                f"- filtered_p1: {fmt_num(best['filtered_p1'] if best else None)}",
                f"- tail_improvement_p10: {fmt_num(tail_improvement_p10)}",
                f"- tail_improvement_p5: {fmt_num(tail_improvement_p5)}",
                f"- tail_improvement_p1: {fmt_num(tail_improvement_p1)}",
                f"- retained_sample_count: {retained_sample_count}",
                f"- opportunity_retention_rate: {fmt_num(opportunity_retention_rate)}",
                f"- false_quarantine_rate: {fmt_num(false_quarantine_rate)}",
                f"- missed_profit_rate: {fmt_num(missed_profit_rate)}",
                f"- loss_avoidance_rate: {fmt_num(loss_avoidance_rate)}",
                f"- worst_pool_contribution: {fmt_num(worst_pool_contribution)}",
                f"- data_quality_status: {best_data_quality_status}",
                f"- review_ready: {'yes' if review_ready else 'no'}",
            ]
        )
        + "\n",
    )
    write_json(
        report_dir / "regime_aware_best_variant_selection.json",
        {
            "best_variant_name": best_variant_name,
            "best_window": best_window,
            "best_horizon": best_horizon,
            "best_proof_unit": best_proof_unit,
            "baseline_p10": best["baseline_p10"] if best else None,
            "baseline_p5": best["baseline_p5"] if best else None,
            "baseline_p1": best["baseline_p1"] if best else None,
            "filtered_p10": best["filtered_p10"] if best else None,
            "filtered_p5": best["filtered_p5"] if best else None,
            "filtered_p1": best["filtered_p1"] if best else None,
            "tail_improvement_p10": tail_improvement_p10,
            "tail_improvement_p5": tail_improvement_p5,
            "tail_improvement_p1": tail_improvement_p1,
            "retained_sample_count": retained_sample_count,
            "opportunity_retention_rate": opportunity_retention_rate,
            "false_quarantine_rate": false_quarantine_rate,
            "missed_profit_rate": missed_profit_rate,
            "loss_avoidance_rate": loss_avoidance_rate,
            "worst_pool_contribution": worst_pool_contribution,
            "data_quality_status": best_data_quality_status,
            "review_ready": review_ready,
        },
    )
    write_text(
        report_dir / "REGIME_AWARE_ROBUSTNESS_AUDIT_CN.md",
        "\n".join(
            [
                "# Regime Aware Robustness Audit",
                "",
                f"- robustness_status: {robustness_status}",
                f"- overfit_risk: {overfit_risk}",
                f"- best_variant_name: {best_variant_name}",
                f"- window_count: {len({r['window'] for r in robustness_rows if r['variant_name'] == best_variant_name}) if best_variant_name else 0}",
                f"- horizon_count: {len({r['horizon'] for r in robustness_rows if r['variant_name'] == best_variant_name}) if best_variant_name else 0}",
                f"- proof_unit_count: {len({r['proof_unit_type'] for r in robustness_rows if r['variant_name'] == best_variant_name}) if best_variant_name else 0}",
            ]
        )
        + "\n",
    )
    write_csv(report_dir / "regime_aware_robustness_audit.csv", robustness_rows_out, ["dimension", "summary", "positive_rate"])

    write_text(
        report_dir / "REGIME_AWARE_NEXT_STAGE_DECISION_CN.md",
        "\n".join(
            [
                "# Regime Aware Next Stage Decision",
                "",
                f"- recommended_next_stage: {recommended_next_stage}",
                f"- review_ready: {'yes' if review_ready else 'no'}",
                f"- robustness_status: {robustness_status}",
                f"- overfit_risk: {overfit_risk}",
                f"- tail_improved: {'yes' if tail_improved else 'no'}",
            ]
        )
        + "\n",
    )
    write_json(
        report_dir / "regime_aware_next_stage_decision.json",
        {
            "recommended_next_stage": recommended_next_stage,
            "best_variant_name": best_variant_name,
            "best_window": best_window,
            "best_horizon": best_horizon,
            "best_proof_unit": best_proof_unit,
            "tail_improved": tail_improved,
            "robustness_status": robustness_status,
            "overfit_risk": overfit_risk,
            "review_ready": review_ready,
        },
    )

    final_status = "PASS" if review_ready and robustness_status == "PASS" else "WARN" if tail_improved else "FAIL"
    final_verdict = {
        "status": final_status,
        "stage": "POOL_REGIME_AWARE_SHORT_HOLD_COUNTERFACTUAL_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "tested_variant_count": len(variants),
        "best_variant_name": best_variant_name,
        "best_window": best_window,
        "best_horizon": best_horizon,
        "best_proof_unit": best_proof_unit,
        "retained_sample_count": retained_sample_count,
        "tail_improved": tail_improved,
        "tail_improvement_p10": tail_improvement_p10,
        "tail_improvement_p5": tail_improvement_p5,
        "tail_improvement_p1": tail_improvement_p1,
        "opportunity_retention_rate": opportunity_retention_rate,
        "false_quarantine_rate": false_quarantine_rate,
        "missed_profit_rate": missed_profit_rate,
        "robustness_status": robustness_status,
        "overfit_risk": overfit_risk,
        "review_ready": review_ready,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": recommended_next_stage,
    }
    write_json(report_dir / "FINAL_VERDICT.json", final_verdict)
    write_text(
        report_dir / "ONEPAGE_CN.md",
        "\n".join(
            [
                "# Pool Regime Aware Short Hold Counterfactual",
                "",
                f"- status: {final_status}",
                f"- best_variant_name: {best_variant_name}",
                f"- best_window: {best_window}",
                f"- best_horizon: {best_horizon}",
                f"- best_proof_unit: {best_proof_unit}",
                f"- retained_sample_count: {retained_sample_count}",
                f"- tail_improved: {'yes' if tail_improved else 'no'}",
                f"- tail_improvement_p10: {fmt_num(tail_improvement_p10)}",
                f"- tail_improvement_p5: {fmt_num(tail_improvement_p5)}",
                f"- tail_improvement_p1: {fmt_num(tail_improvement_p1)}",
                f"- opportunity_retention_rate: {fmt_num(opportunity_retention_rate)}",
                f"- false_quarantine_rate: {fmt_num(false_quarantine_rate)}",
                f"- missed_profit_rate: {fmt_num(missed_profit_rate)}",
                f"- robustness_status: {robustness_status}",
                f"- overfit_risk: {overfit_risk}",
                f"- review_ready: {'yes' if review_ready else 'no'}",
                f"- recommended_next_stage: {recommended_next_stage}",
                f"- tiny_canary_allowed: no",
            ]
        )
        + "\n",
    )
    artifact_lines = [
        "# Artifact Index",
        "",
        "- INPUT_ARTIFACT_AUDIT_CN.md",
        "- VPS_DB_QUICK_CHECK_CN.md",
        "- REGIME_AWARE_SHORT_HOLD_VARIANTS_CN.md",
        "- REGIME_AWARE_SHORT_HOLD_SCHEMA_CN.md",
        "- REGIME_AWARE_SHORT_HOLD_MATERIALIZATION_CN.md",
        "- REGIME_AWARE_SHORT_HOLD_COUNTERFACTUAL_REPORT_CN.md",
        "- REGIME_AWARE_BEST_VARIANT_SELECTION_CN.md",
        "- REGIME_AWARE_ROBUSTNESS_AUDIT_CN.md",
        "- REGIME_AWARE_NEXT_STAGE_DECISION_CN.md",
        "- FINAL_VERDICT.json",
        "- ONEPAGE_CN.md",
        "- input_artifact_audit.json",
        "- regime_aware_short_hold_variants.json",
        "- regime_aware_short_hold_schema.json",
        "- regime_aware_short_hold_materialization_counts.csv",
        "- regime_aware_short_hold_counterfactual_report.csv",
        "- regime_aware_best_variant_selection.json",
        "- regime_aware_robustness_audit.csv",
        "- regime_aware_next_stage_decision.json",
        "- pool_regime_aware_short_hold_counterfactual_v1_readonly.py",
    ]
    write_text(report_dir / "ARTIFACT_INDEX.md", "\n".join(artifact_lines) + "\n")

    print(json.dumps({"report_dir": str(report_dir), "final_verdict": str(report_dir / "FINAL_VERDICT.json")}, indent=2))


if __name__ == "__main__":
    main()
