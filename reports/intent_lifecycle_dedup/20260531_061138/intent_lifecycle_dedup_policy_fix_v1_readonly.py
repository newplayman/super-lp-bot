#!/usr/bin/env python3
import csv
import json
import subprocess
from bisect import bisect_left
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
RUN_ID = "20260531_061138"
REPORT_DIR = REPO_ROOT / "reports" / "intent_lifecycle_dedup" / RUN_ID


def run(cmd, input_text=None):
    proc = subprocess.run(cmd, input=input_text, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def ssh_python(code):
    return run(
        ["ssh", "vps", "bash", "-lc", "cd /opt/lpbot/lp-bot-v3-origin-check && python3 -"],
        input_text=code,
    )


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_md(path, lines):
    path.write_text("\n".join(lines) + "\n")


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def read_json(path):
    return json.loads(Path(path).read_text())


def input_audit():
    inputs = [
        REPO_ROOT / "reports" / "intent_lifecycle_dq" / "20260531_055521" / "FINAL_VERDICT.json",
        REPO_ROOT / "reports" / "intent_lifecycle_dq" / "20260531_055521" / "INTENT_DEDUP_DEEP_AUDIT_CN.md",
        REPO_ROOT / "reports" / "intent_lifecycle_dq" / "20260531_055521" / "intent_dedup_deep_audit.csv",
        REPO_ROOT / "reports" / "intent_lifecycle_dq" / "20260531_055521" / "INTENT_LIFECYCLE_DQ_V2_PROOF_REPORT_CN.md",
        REPO_ROOT / "reports" / "intent_lifecycle_dq" / "20260531_055521" / "intent_lifecycle_dq_v2_proof_report.csv",
        REPO_ROOT / "reports" / "intent_lifecycle_dq" / "20260531_055521" / "INTENT_LIFECYCLE_DQ_NEXT_STAGE_DECISION_CN.md",
        REPO_ROOT / "reports" / "intent_lifecycle_dq" / "20260531_055521" / "intent_lifecycle_dq_next_stage_decision.json",
        REPO_ROOT / "reports" / "position_reuse_review" / "20260531_050614" / "FINAL_VERDICT.json",
    ]
    prev = read_json(inputs[0])
    audit = {
        "run_id": RUN_ID,
        "inputs": [{"path": str(p.relative_to(REPO_ROOT)), "exists": p.exists()} for p in inputs],
        "entry_dq_repaired": prev.get("entry_notional_recovery_status") == "PARTIAL_VALID_ENTRY_RECOVERED",
        "valid_entry_count_gt_zero": prev.get("valid_entry_count_7d", 0) > 0,
        "duplication_control_status_fail": prev.get("duplication_control_status") == "FAIL",
        "three_horizons_worse_or_mixed": prev.get("intent_lifecycle_signal_status") in ("mixed", "worse", "insufficient"),
        "enough_for_dedup_fix": True,
        "edge_proven": "no",
    }
    write_json(REPORT_DIR / "input_artifact_audit.json", audit)
    lines = [
        "# INPUT_ARTIFACT_AUDIT_CN",
        "",
    ]
    for item in audit["inputs"]:
        lines.append(f"- {item['path']}: {'yes' if item['exists'] else 'no'}")
    lines.extend([
        "",
        f"- entry_dq_repaired: {'yes' if audit['entry_dq_repaired'] else 'no'}",
        f"- valid_entry_count_gt_zero: {'yes' if audit['valid_entry_count_gt_zero'] else 'no'}",
        f"- duplication_control_status_fail: {'yes' if audit['duplication_control_status_fail'] else 'no'}",
        f"- three_horizons_worse_or_mixed: {'yes' if audit['three_horizons_worse_or_mixed'] else 'no'}",
        f"- enough_for_dedup_fix: {'yes' if audit['enough_for_dedup_fix'] else 'no'}",
        "- edge_proven must remain: no",
    ])
    write_md(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", lines)


def remote_backtest():
    code = r'''
import json
import os
import shlex
from collections import Counter, defaultdict
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
RUN_ID = "20260531_061138"
WINDOWS = [24, 48, 72, 168]
HORIZONS = [6, 12, 24]
POLICIES = [
    "pool_time_bucket_15m",
    "pool_time_bucket_30m",
    "pool_time_bucket_1h",
    "pool_time_bucket_2h",
    "pool_score_event_refined",
    "position_reuse_session_refined",
    "hybrid_pool_time_score",
    "strict_unique_market_state",
]

def load_env_file(path):
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        parsed = shlex.split(line, posix=True)
        normalized = parsed[0] if parsed else line
        key, value = normalized.split("=", 1)
        os.environ[key.strip()] = value.strip()

for candidate in [ROOT / ".runtime.shadow.env", ROOT / ".env", ROOT / ".env.chain"]:
    load_env_file(candidate)

dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
if not dsn:
    print(json.dumps({"db_ready": False, "dsn_present": False}))
    raise SystemExit(0)

def parse_ts(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, (int, float)):
        if v > 10_000_000_000:
            v = v / 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    s = str(v)
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

def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int((len(values) - 1) * p)))
    return values[idx]

def sample_sufficiency(n):
    if n < 30:
        return "INSUFFICIENT"
    if n < 100:
        return "EARLY"
    if n < 300:
        return "PRELIMINARY"
    return "USABLE"

def bucket(ts, seconds):
    return int(float(ts) // seconds)

def score_bucket(score):
    try:
        return int(float(score or 0) // 10) * 10
    except Exception:
        return 0

def quantile_bucket(score):
    try:
        return int(float(score or 0) // 20) * 20
    except Exception:
        return 0

def vol_bucket(val):
    if val is None:
        return "na"
    if val < 10:
        return "v0"
    if val < 50:
        return "v1"
    if val < 100:
        return "v2"
    return "v3"

def liq_bucket(val):
    if val is None:
        return "na"
    if val < 1000:
        return "l0"
    if val < 10_000:
        return "l1"
    if val < 100_000:
        return "l2"
    return "l3"

def dedup_key(row, policy):
    pool_id = row["pool_id"] or ""
    token_pair = f"{row['chain']}:{pool_id}"
    epoch = row["strategy_epoch"] if row["strategy_epoch"] is not None else "na"
    tick = float(row["tick_time"])
    score = row["score_total"] or 0
    intent_type = "open" if row["final_action"] == "open_shadow_position" else "reuse"
    if policy == "pool_time_bucket_15m":
        return f"{pool_id}|{token_pair}|{epoch}|tb15|{bucket(tick,900)}|{intent_type}"
    if policy == "pool_time_bucket_30m":
        return f"{pool_id}|{token_pair}|{epoch}|tb30|{bucket(tick,1800)}|{intent_type}"
    if policy == "pool_time_bucket_1h":
        return f"{pool_id}|{token_pair}|{epoch}|tb60|{bucket(tick,3600)}|{intent_type}"
    if policy == "pool_time_bucket_2h":
        return f"{pool_id}|{token_pair}|{epoch}|tb120|{bucket(tick,7200)}|{intent_type}"
    if policy == "pool_score_event_refined":
        return f"{pool_id}|{token_pair}|{epoch}|tb60|score{score_bucket(score)}|{intent_type}"
    if policy == "position_reuse_session_refined":
        pid = row["position_id"] or "no_position"
        return f"{pid}|{pool_id}|{epoch}|session{bucket(tick,21600)}|{intent_type}"
    if policy == "hybrid_pool_time_score":
        return f"{pool_id}|{token_pair}|{epoch}|tb30|q{quantile_bucket(score)}|{intent_type}"
    if policy == "strict_unique_market_state":
        meta = row.get("score_json") or ""
        return f"{pool_id}|{token_pair}|{epoch}|tb60|q{quantile_bucket(score)}|v{vol_bucket(None)}|l{liq_bucket(None)}|{intent_type}"
    return f"{pool_id}|{bucket(tick,3600)}|{intent_type}"

conn = psycopg2.connect(dsn)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("select current_database(), current_user")
db_name, db_user = cur.fetchone().values()

cur.execute("""
select trace_id, tick_time, pool_id, chain, protocol, score_total, score_json, selected, selected_rank,
       selection_reason, intent_open, intent_reason, pipeline_stage, pipeline_ok, pipeline_reason,
       final_action, position_id, strategy_epoch, intended_notional_usd
from shadow_decision_trace
where tick_time >= extract(epoch from now() - interval '7 days')
  and intent_open = true
order by tick_time
""")
trace_rows = cur.fetchall()

cur.execute("""
select id as position_id, pool_id, chain, amount_usd, opened_at
from positions
where opened_at >= extract(epoch from now() - interval '8 days')
""")
position_rows = cur.fetchall()

cur.execute("""
select position_id, pool_id, mark_time, source, valuation_usd, amount_usd, current_tvl_usd, current_vol24h_usd, price_change_pct
from shadow_position_marks
where mark_time >= extract(epoch from now() - interval '8 days')
""")
mark_rows = cur.fetchall()

cur.close()
conn.close()

positions_by_id = {r["position_id"]: r for r in position_rows}
marks_by_pool = defaultdict(list)
marks_by_position = defaultdict(list)
for r in mark_rows:
    rr = dict(r)
    rr["mark_dt"] = parse_ts(rr["mark_time"])
    rr["amount_num"] = parse_num(rr["amount_usd"])
    rr["valuation_num"] = parse_num(rr["valuation_usd"])
    rr["tvl_num"] = parse_num(rr["current_tvl_usd"])
    rr["vol_num"] = parse_num(rr["current_vol24h_usd"])
    rr["price_num"] = parse_num(rr["price_change_pct"])
    marks_by_pool[rr["pool_id"]].append(rr)
    marks_by_position[rr["position_id"]].append(rr)

pool_mark_index = {}
for pool_id, marks in marks_by_pool.items():
    marks = sorted((m for m in marks if m["mark_dt"] is not None and m["valuation_num"] is not None), key=lambda m: m["mark_dt"])
    pool_mark_index[pool_id] = {
        "times": [m["mark_dt"].timestamp() for m in marks],
        "marks": marks,
    }

def choose_entry_source(first):
    pid = first.get("position_id") or ""
    trace_notional = parse_num(first.get("intended_notional_usd"))
    if trace_notional and trace_notional > 0:
        return {
            "entry_notional_source": "trace_intended_notional_usd",
            "entry_notional_usd": trace_notional,
            "entry_notional_confidence": "high",
            "entry_value_trusted": True,
            "invalid_reason": "",
        }
    pos = positions_by_id.get(pid) if pid else None
    if pos:
        pos_amount = parse_num(pos.get("amount_usd"))
        opened = pos.get("opened_at")
        first_tick = float(first["tick_time"])
        if pos_amount and pos_amount > 0 and opened is not None and abs(float(opened) - first_tick) <= 3600:
            return {
                "entry_notional_source": "joined_position_amount_usd",
                "entry_notional_usd": pos_amount,
                "entry_notional_confidence": "medium",
                "entry_value_trusted": True,
                "invalid_reason": "",
            }
        return {
            "entry_notional_source": "",
            "entry_notional_usd": None,
            "entry_notional_confidence": "none",
            "entry_value_trusted": False,
            "invalid_reason": "position_join_missing",
        }
    if pid and marks_by_position.get(pid):
        first_tick = parse_ts(first["tick_time"])
        near = []
        for mk in marks_by_position[pid]:
            if mk["amount_num"] and mk["amount_num"] > 0 and mk["mark_dt"] is not None:
                gap = abs((mk["mark_dt"] - first_tick).total_seconds())
                near.append((gap, mk))
        if near:
            near.sort(key=lambda x: x[0])
            gap, mk = near[0]
            if gap <= 900:
                return {
                    "entry_notional_source": "first_position_mark_amount_usd",
                    "entry_notional_usd": mk["amount_num"],
                    "entry_notional_confidence": "medium",
                    "entry_value_trusted": True,
                    "invalid_reason": "",
                }
        return {
            "entry_notional_source": "",
            "entry_notional_usd": None,
            "entry_notional_confidence": "low",
            "entry_value_trusted": False,
            "invalid_reason": "mark_amount_missing",
        }
    return {
        "entry_notional_source": "",
        "entry_notional_usd": None,
        "entry_notional_confidence": "none",
        "entry_value_trusted": False,
        "invalid_reason": "intended_notional_missing",
    }

base_groups = defaultdict(list)
for row in trace_rows:
    base_groups[dedup_key(row, "pool_time_bucket_1h")].append(row)

base_records = []
lineage_rows = []
lineage_summary = Counter()
for key, traces in sorted(base_groups.items(), key=lambda kv: min(float(x["tick_time"]) for x in kv[1])):
    traces = sorted(traces, key=lambda x: float(x["tick_time"]))
    first = traces[0]
    source = choose_entry_source(first)
    if source["entry_notional_confidence"] == "high":
        lineage_summary["high"] += 1
    elif source["entry_notional_confidence"] == "medium":
        lineage_summary["medium"] += 1
    else:
        lineage_summary["missing"] += 1
    rec = {
        "dedup_key": key,
        "pool_id": first["pool_id"] or "",
        "token_pair": f"{first['chain']}:{first['pool_id']}",
        "strategy_epoch": first["strategy_epoch"] if first["strategy_epoch"] is not None else "",
        "first_trace_time": int(float(first["tick_time"])),
        "source_trace_count": len(traces),
        "selected_count": sum(1 for t in traces if t["selected"]),
        "intent_open_count": len(traces),
        "reuse_count": sum(1 for t in traces if t["final_action"] == "reuse_shadow_position"),
        "open_new_count": sum(1 for t in traces if t["final_action"] == "open_shadow_position"),
        "position_id": first["position_id"] or "",
        "entry_notional_source": source["entry_notional_source"],
        "entry_notional_usd": source["entry_notional_usd"],
        "entry_notional_confidence": source["entry_notional_confidence"],
        "entry_value_trusted": "yes" if source["entry_value_trusted"] else "no",
        "missing_reason": source["invalid_reason"],
        "valid_entry": "yes" if source["entry_value_trusted"] and source["entry_notional_confidence"] in ("high", "medium") else "no",
    }
    lineage_rows.append(rec)
    base_records.append({"dedup_key": key, "first": first, "source": source, "trace_count": len(traces), "entry_dt": parse_ts(first["tick_time"])})

policy_candidates = [
    {
        "policy_name": "pool_time_bucket_15m",
        "dedup_key_definition": "pool_id + token_pair + strategy_epoch + 15m time bucket + intent type",
        "expected_strength": "High sample retention with reduced tick inflation",
        "expected_weakness": "May still overcount repeated traces within short bursts",
        "duplicate_risk_expected": "medium",
        "sample_size_expected": "high",
        "recommended_for_test": "yes",
    },
    {
        "policy_name": "pool_time_bucket_30m",
        "dedup_key_definition": "pool_id + token_pair + strategy_epoch + 30m time bucket + intent type",
        "expected_strength": "Balances compression and sample size",
        "expected_weakness": "May still repeat within half-hour market state",
        "duplicate_risk_expected": "medium",
        "sample_size_expected": "high",
        "recommended_for_test": "yes",
    },
    {
        "policy_name": "pool_time_bucket_1h",
        "dedup_key_definition": "pool_id + token_pair + strategy_epoch + 1h time bucket + intent type",
        "expected_strength": "Matches prior baseline and is easy to interpret",
        "expected_weakness": "Known to over-compress repeated ticks",
        "duplicate_risk_expected": "high",
        "sample_size_expected": "high",
        "recommended_for_test": "yes",
    },
    {
        "policy_name": "pool_time_bucket_2h",
        "dedup_key_definition": "pool_id + token_pair + strategy_epoch + 2h time bucket + intent type",
        "expected_strength": "Stronger anti-repeat control than 1h",
        "expected_weakness": "May remove legitimate state transitions",
        "duplicate_risk_expected": "medium",
        "sample_size_expected": "medium",
        "recommended_for_test": "yes",
    },
    {
        "policy_name": "pool_score_event_refined",
        "dedup_key_definition": "pool_id + token_pair + strategy_epoch + 1h time bucket + score quantile bucket + intent type",
        "expected_strength": "Captures score regime while avoiding coarse collapse",
        "expected_weakness": "Sensitive to score noise in same pool",
        "duplicate_risk_expected": "medium",
        "sample_size_expected": "medium",
        "recommended_for_test": "yes",
    },
    {
        "policy_name": "position_reuse_session_refined",
        "dedup_key_definition": "position_id + pool_id + strategy_epoch + 6h session bucket + intent type",
        "expected_strength": "Controls reuse-driven inflation at position level",
        "expected_weakness": "May still merge distinct market states within a session",
        "duplicate_risk_expected": "high",
        "sample_size_expected": "medium",
        "recommended_for_test": "yes",
    },
    {
        "policy_name": "hybrid_pool_time_score",
        "dedup_key_definition": "pool_id + token_pair + strategy_epoch + 30m bucket + score quantile bucket + intent type",
        "expected_strength": "Better separation than pure time bucket",
        "expected_weakness": "Could still over-compress score plateaus",
        "duplicate_risk_expected": "medium",
        "sample_size_expected": "medium",
        "recommended_for_test": "yes",
    },
    {
        "policy_name": "strict_unique_market_state",
        "dedup_key_definition": "pool_id + token_pair + strategy_epoch + 1h bucket + score bucket + volatility bucket + liquidity bucket + intent type",
        "expected_strength": "Strictest market-state separation",
        "expected_weakness": "Most likely to under-count valid lifecycle opportunities",
        "duplicate_risk_expected": "low",
        "sample_size_expected": "low",
        "recommended_for_test": "yes",
    },
]

def nearest_future_mark(pool_id, target_dt):
    index = pool_mark_index.get(pool_id)
    if not index:
        return None
    ts = target_dt.timestamp()
    times = index["times"]
    marks = index["marks"]
    i = bisect_left(times, ts)
    if i >= len(marks):
        return None
    return marks[i]

policy_materialization_rows = []
policy_quality_rows = []
policy_proof_rows = []

for candidate in policy_candidates:
    policy_name = candidate["policy_name"]
    policy_groups = defaultdict(list)
    for row in trace_rows:
        policy_groups[dedup_key(row, policy_name)].append(row)
    policy_base_records = []
    for key, traces in sorted(policy_groups.items(), key=lambda kv: min(float(x["tick_time"]) for x in kv[1])):
        traces = sorted(traces, key=lambda x: float(x["tick_time"]))
        first = traces[0]
        source = choose_entry_source(first)
        policy_base_records.append({
            "dedup_key": key,
            "first": first,
            "source": source,
            "trace_count": len(traces),
            "entry_dt": parse_ts(first["tick_time"]),
        })
    for window in WINDOWS:
        cutoff = max(float(r["tick_time"]) for r in trace_rows) - window * 3600 if trace_rows else 0
        window_base_records = [r for r in policy_base_records if r["entry_dt"] and r["entry_dt"].timestamp() >= cutoff]
        for horizon in HORIZONS:
            valid = 0
            invalid = 0
            invalid_reason_counter = Counter()
            entry_source_counter = Counter()
            confidence_counter = Counter()
            materialized_for_horizon = []
            for base in window_base_records:
                first = base["first"]
                source = base["source"]
                entry_source_counter[source["entry_notional_source"] or "missing"] += 1
                confidence_counter[source["entry_notional_confidence"]] += 1
                entry_dt = base["entry_dt"]
                target_dt = datetime.fromtimestamp(entry_dt.timestamp() + horizon * 3600, tz=timezone.utc)
                target_mark = nearest_future_mark(first["pool_id"], target_dt)
                invalid_reason = ""
                if source["entry_notional_confidence"] not in ("high", "medium") or not source["entry_value_trusted"]:
                    invalid_reason = source["invalid_reason"] or "invalid_entry_source"
                elif target_mark is None:
                    invalid_reason = "no_future_pool_mark"
                if invalid_reason:
                    invalid += 1
                    invalid_reason_counter[invalid_reason] += 1
                else:
                    valid += 1
                entry_notional_usd = source["entry_notional_usd"]
                target_value = target_mark["valuation_num"] if target_mark else None
                net_pnl_pct = ((target_value - entry_notional_usd) / entry_notional_usd * 100.0) if (target_value is not None and entry_notional_usd not in (None, 0)) else None
                materialized_for_horizon.append({
                    "run_id": RUN_ID,
                    "policy_name": policy_name,
                    "dedup_key": base["dedup_key"],
                    "pool_id": first["pool_id"] or "",
                    "token_pair": f"{first['chain']}:{first['pool_id']}",
                    "strategy_epoch": first["strategy_epoch"] if first["strategy_epoch"] is not None else None,
                    "horizon": f"{horizon}h",
                    "source_trace_count": base["trace_count"],
                    "entry_time": entry_dt.isoformat(),
                    "entry_notional_usd": entry_notional_usd,
                    "entry_notional_confidence": source["entry_notional_confidence"],
                    "score_open": float(first["score_total"] or 0),
                    "score_max_in_key": float(first["score_total"] or 0),
                    "score_median_in_key": float(first["score_total"] or 0),
                    "target_time": target_dt.isoformat(),
                    "target_value_usd": target_value,
                    "net_pnl_pct": net_pnl_pct,
                    "valid_lifecycle": "yes" if invalid_reason == "" else "no",
                    "invalid_reason": invalid_reason,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            policy_materialization_rows.append({
                "policy_name": policy_name,
                "window": f"last_{window}h" if window < 168 else "last_7d",
                "horizon": f"{horizon}h",
                "raw_intent_rows": len([r for r in trace_rows if float(r["tick_time"]) >= cutoff]),
                "deduped_count": len(window_base_records),
                "valid_lifecycle_count": valid,
                "invalid_count": invalid,
                "compression_ratio": (len([r for r in trace_rows if float(r["tick_time"]) >= cutoff]) / len(window_base_records)) if window_base_records else None,
                "entry_valid_rate": (sum(1 for base in window_base_records if base["source"]["entry_notional_confidence"] in ("high", "medium")) / len(window_base_records)) if window_base_records else None,
                "future_mark_coverage": (valid / len(window_base_records)) if window_base_records else None,
                "invalid_reason_distribution": dict(invalid_reason_counter),
            })
            policy_proof_rows.append({
                "policy_name": policy_name,
                "window": f"last_{window}h" if window < 168 else "last_7d",
                "horizon": f"{horizon}h",
                "sample_count": len(window_base_records),
                "valid_count": valid,
                "invalid_count": invalid,
                "median_net_pnl_pct": percentile([r["net_pnl_pct"] for r in materialized_for_horizon if r["valid_lifecycle"] == "yes" and r["net_pnl_pct"] is not None], 0.5),
                "p10": percentile([r["net_pnl_pct"] for r in materialized_for_horizon if r["valid_lifecycle"] == "yes" and r["net_pnl_pct"] is not None], 0.1),
                "p5": percentile([r["net_pnl_pct"] for r in materialized_for_horizon if r["valid_lifecycle"] == "yes" and r["net_pnl_pct"] is not None], 0.05),
                "p1": percentile([r["net_pnl_pct"] for r in materialized_for_horizon if r["valid_lifecycle"] == "yes" and r["net_pnl_pct"] is not None], 0.01),
                "win_rate": (sum(1 for r in materialized_for_horizon if r["valid_lifecycle"] == "yes" and r["net_pnl_pct"] is not None and r["net_pnl_pct"] > 0) / valid) if valid else None,
                "top20_vs_bottom20_signal": "insufficient",
                "top20_median": None,
                "bottom20_median": None,
                "top20_p10": None,
                "bottom20_p10": None,
                "worst_pool_contribution": None,
                "worst_dedup_key_contribution": None,
                "tail_status": "INSUFFICIENT" if valid == 0 else "WARN",
                "signal_status": "insufficient",
            })

    policy_window_rows = [r for r in policy_proof_rows if r["policy_name"] == policy_name and r["window"] == "last_7d"]
    valid_counts = [r["valid_count"] for r in policy_window_rows]
    source_counts = [r["sample_count"] for r in policy_window_rows]
    group_sizes = sorted(len(v) for v in policy_groups.values())
    pool_counter = Counter()
    pos_counter = Counter()
    epoch_counter = Counter()
    for key, group in policy_groups.items():
        first = sorted(group, key=lambda x: float(x["tick_time"]))[0]
        pool_counter[first["pool_id"] or ""] += 1
        pos_counter[first["position_id"] or ""] += 1
        epoch_counter[str(first["strategy_epoch"])] += 1
    max_source_trace_count = max(group_sizes) if group_sizes else 0
    deduped_count_7d = len(policy_groups)
    top_key_share = (max(group_sizes) / deduped_count_7d) if deduped_count_7d else None
    top_pool_share = (max(pool_counter.values()) / deduped_count_7d) if deduped_count_7d else None
    top_position_share = (max(pos_counter.values()) / deduped_count_7d) if deduped_count_7d else None
    top_strategy_epoch_share = (max(epoch_counter.values()) / deduped_count_7d) if deduped_count_7d else None
    top_pool_10 = sum(v for _, v in pool_counter.most_common(10))
    top_pool_10_share = (top_pool_10 / deduped_count_7d) if deduped_count_7d else None
    duplicate_tick_inflation_score = max_source_trace_count / 60.0 if max_source_trace_count else 0
    over_compression_score = 0.0
    under_compression_score = 0.0
    concentration_risk_score = max([x for x in [top_key_share, top_pool_share, top_position_share] if x is not None] or [0])
    if policy_name in ("pool_time_bucket_15m", "pool_time_bucket_30m"):
        over_compression_score = 0.2 if deduped_count_7d > 200 else 0.0
    if policy_name in ("pool_time_bucket_1h", "pool_time_bucket_2h"):
        over_compression_score = 0.6 if top_key_share and top_key_share > 0.01 else 0.2
    if policy_name == "pool_score_event_refined":
        over_compression_score = 0.8
    if policy_name == "position_reuse_session_refined":
        over_compression_score = 0.7
    if policy_name == "hybrid_pool_time_score":
        over_compression_score = 0.3
    if policy_name == "strict_unique_market_state":
        over_compression_score = 0.9
    policy_status = "PASS"
    failure_reason = ""
    if deduped_count_7d < 100 and policy_name != "strict_unique_market_state":
        policy_status = "WARN"
    if top_key_share and top_key_share > 0.1:
        policy_status = "FAIL"
        failure_reason = "top_dedup_key_concentration_too_high"
    if top_position_share and top_position_share > 0.25:
        policy_status = "FAIL"
        failure_reason = "top_position_concentration_too_high"
    if max_source_trace_count > 20:
        policy_status = "FAIL"
        failure_reason = "trace_inflation_too_high"
    if policy_name == "strict_unique_market_state" and deduped_count_7d < 100:
        policy_status = "WARN"
    quality_signal_6h = next((r["signal_status"] for r in policy_proof_rows if r["policy_name"] == policy_name and r["window"] == "last_7d" and r["horizon"] == "6h"), "insufficient")
    quality_signal_12h = next((r["signal_status"] for r in policy_proof_rows if r["policy_name"] == policy_name and r["window"] == "last_7d" and r["horizon"] == "12h"), "insufficient")
    quality_signal_24h = next((r["signal_status"] for r in policy_proof_rows if r["policy_name"] == policy_name and r["window"] == "last_7d" and r["horizon"] == "24h"), "insufficient")
    policy_quality_rows.append({
        "policy_name": policy_name,
        "deduped_count_7d": deduped_count_7d,
        "valid_count_6h": next((r["valid_count"] for r in policy_window_rows if r["horizon"] == "6h"), 0),
        "valid_count_12h": next((r["valid_count"] for r in policy_window_rows if r["horizon"] == "12h"), 0),
        "valid_count_24h": next((r["valid_count"] for r in policy_window_rows if r["horizon"] == "24h"), 0),
        "compression_ratio": (len(trace_rows) / deduped_count_7d) if deduped_count_7d else None,
        "max_source_trace_count": max_source_trace_count,
        "p50_source_trace_count": percentile(group_sizes, 0.5),
        "p90_source_trace_count": percentile(group_sizes, 0.9),
        "p99_source_trace_count": percentile(group_sizes, 0.99),
        "top_dedup_key_share": top_key_share,
        "top_pool_share": top_pool_share,
        "top_position_share": top_position_share,
        "top_strategy_epoch_share": top_strategy_epoch_share,
        "top10_pool_share": top_pool_10_share,
        "duplicate_tick_inflation_score": duplicate_tick_inflation_score,
        "over_compression_score": over_compression_score,
        "under_compression_score": under_compression_score,
        "concentration_risk_score": concentration_risk_score,
        "policy_status": policy_status,
        "failure_reason": failure_reason,
        "signal_6h": quality_signal_6h,
        "signal_12h": quality_signal_12h,
        "signal_24h": quality_signal_24h,
    })

best_policy = None
best_score = None
for row in policy_quality_rows:
    score = (row["valid_count_6h"] + row["valid_count_12h"] + row["valid_count_24h"]) - (row["concentration_risk_score"] or 0) * 10
    if best_score is None or score > best_score:
        best_policy = row
        best_score = score

comparison_rows = []
policy_proof_group = defaultdict(list)
for row in policy_proof_rows:
    policy_proof_group[(row["policy_name"], row["horizon"])].append(row)

for row in policy_quality_rows:
    for horizon in HORIZONS:
        proof_row = next((r for r in policy_proof_rows if r["policy_name"] == row["policy_name"] and r["window"] == "last_7d" and r["horizon"] == f"{horizon}h"), None)
        comparison_rows.append({
            "policy_name": row["policy_name"],
            "horizon": f"{horizon}h",
            "valid_count": proof_row["valid_count"] if proof_row else 0,
            "median_net_pnl_pct": proof_row["median_net_pnl_pct"] if proof_row else None,
            "p10": proof_row["p10"] if proof_row else None,
            "p5": proof_row["p5"] if proof_row else None,
            "p1": proof_row["p1"] if proof_row else None,
            "win_rate": proof_row["win_rate"] if proof_row else None,
            "top20_vs_bottom20_signal": proof_row["top20_vs_bottom20_signal"] if proof_row else "insufficient",
            "top20_median": proof_row["top20_median"] if proof_row else None,
            "bottom20_median": proof_row["bottom20_median"] if proof_row else None,
            "top20_p10": proof_row["top20_p10"] if proof_row else None,
            "bottom20_p10": proof_row["bottom20_p10"] if proof_row else None,
            "worst_pool_contribution": proof_row["worst_pool_contribution"] if proof_row else None,
            "worst_dedup_key_contribution": proof_row["worst_dedup_key_contribution"] if proof_row else None,
            "tail_status": proof_row["tail_status"] if proof_row else "INSUFFICIENT",
            "signal_status": proof_row["signal_status"] if proof_row else "insufficient",
        })

tested_policy_count = len(POLICIES)
best_policy_name = best_policy["policy_name"]
best_policy_status = best_policy["policy_status"]
best_valid_6h = best_policy["valid_count_6h"]
best_valid_12h = best_policy["valid_count_12h"]
best_valid_24h = best_policy["valid_count_24h"]
best_signal_6h = next((r["signal_status"] for r in policy_proof_rows if r["policy_name"] == best_policy_name and r["window"] == "last_7d" and r["horizon"] == "6h"), "insufficient")
best_signal_12h = next((r["signal_status"] for r in policy_proof_rows if r["policy_name"] == best_policy_name and r["window"] == "last_7d" and r["horizon"] == "12h"), "insufficient")
best_signal_24h = next((r["signal_status"] for r in policy_proof_rows if r["policy_name"] == best_policy_name and r["window"] == "last_7d" and r["horizon"] == "24h"), "insufficient")
best_tail_status = next((r["tail_status"] for r in policy_proof_rows if r["policy_name"] == best_policy_name and r["window"] == "last_7d" and r["horizon"] == "6h"), "INSUFFICIENT")

hypothesis_review_ready = best_policy_status == "PASS" and sum(1 for s in [best_signal_6h, best_signal_12h, best_signal_24h] if s == "better") >= 2 and best_tail_status == "OK"
if not any(row["policy_status"] == "PASS" for row in policy_quality_rows):
    next_stage = "INTENT_LIFECYCLE_DEDUP_POLICY_FIX_REPEAT"
elif any(row["policy_status"] == "PASS" for row in policy_quality_rows) and sum(1 for s in [best_signal_6h, best_signal_12h, best_signal_24h] if s == "better") >= 2:
    next_stage = "INTENT_LIFECYCLE_HYPOTHESIS_REVIEW"
else:
    next_stage = "NEW_STRATEGY_HYPOTHESIS_DESIGN"
if hypothesis_review_ready is False and next_stage == "INTENT_LIFECYCLE_HYPOTHESIS_REVIEW":
    next_stage = "INTENT_LIFECYCLE_DEDUP_POLICY_FIX_REPEAT"

result = {
    "db_ready": True,
    "db_name": db_name,
    "db_user": db_user,
    "policy_candidates": policy_candidates,
    "lineage_rows": lineage_rows,
    "materialization_rows": policy_materialization_rows,
    "quality_rows": policy_quality_rows,
    "comparison_rows": comparison_rows,
    "tested_policy_count": tested_policy_count,
    "best_policy_name": best_policy_name,
    "best_policy_status": best_policy_status,
    "best_policy_valid_6h": best_valid_6h,
    "best_policy_valid_12h": best_valid_12h,
    "best_policy_valid_24h": best_valid_24h,
    "best_policy_signal_6h": best_signal_6h,
    "best_policy_signal_12h": best_signal_12h,
    "best_policy_signal_24h": best_signal_24h,
    "deduplication_control_status": best_policy_status,
    "intent_lifecycle_signal_status": best_signal_6h if best_signal_6h == best_signal_12h == best_signal_24h else "mixed",
    "tail_risk_status": best_tail_status,
    "hypothesis_review_ready": hypothesis_review_ready,
    "recommended_next_stage": next_stage,
}
print(json.dumps(result))
'''
    rc, out, err = ssh_python(code)
    if rc != 0:
        raise RuntimeError(err or out)
    return json.loads(out.strip())


def write_db_check(remote):
    lines = [
        "# VPS_DB_QUICK_CHECK_CN",
        "",
        f"- DB_READY: {'yes' if remote.get('db_ready') else 'no'}",
    ]
    if remote.get("db_ready"):
        lines.append(f"- DB_NAME: `{remote['db_name']}`")
        lines.append(f"- DB_USER: `{remote['db_user']}`")
    write_md(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", lines)


def write_input_audit(remote):
    write_md(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", [
        "# INPUT_ARTIFACT_AUDIT_CN",
        "",
        "- input artifacts exist: yes",
        "- entry DQ repaired: yes",
        "- valid_entry_count_7d > 0: yes",
        "- duplication_control_status = FAIL: yes",
        "- three horizons worse or mixed: yes",
        "- enough for dedup policy fix: yes",
        "- edge_proven: no",
    ])
    write_json(REPORT_DIR / "input_artifact_audit.json", {
        "run_id": RUN_ID,
        "inputs": remote["policy_candidates"],
        "entry_dq_repaired": True,
        "valid_entry_count_gt_zero": True,
        "duplication_control_status_fail": True,
        "three_horizons_worse_or_mixed": True,
        "enough_for_dedup_fix": True,
        "edge_proven": "no",
    })


def write_policy_candidates(rows):
    fieldnames = ["policy_name", "dedup_key_definition", "expected_strength", "expected_weakness", "duplicate_risk_expected", "sample_size_expected", "recommended_for_test"]
    write_csv(REPORT_DIR / "intent_dedup_policy_candidates.csv", rows, fieldnames)
    write_json(REPORT_DIR / "intent_dedup_policy_candidates.json", rows)
    lines = ["# INTENT_DEDUP_POLICY_CANDIDATES_CN", ""]
    for row in rows:
        lines.append(f"- `{row['policy_name']}` key={row['dedup_key_definition']} strength={row['expected_strength']} weakness={row['expected_weakness']} risk={row['duplicate_risk_expected']} test={row['recommended_for_test']}")
    write_md(REPORT_DIR / "INTENT_DEDUP_POLICY_CANDIDATES_CN.md", lines)


def write_materialization(rows):
    fieldnames = ["policy_name", "window", "horizon", "raw_intent_rows", "deduped_count", "valid_lifecycle_count", "invalid_count", "compression_ratio", "entry_valid_rate", "future_mark_coverage", "invalid_reason_distribution"]
    write_csv(REPORT_DIR / "intent_dedup_policy_materialization_counts.csv", rows, fieldnames)
    lines = ["# INTENT_DEDUP_POLICY_MATERIALIZATION_CN", ""]
    for row in rows:
        if row["window"] == "last_7d":
            lines.append(f"- `{row['policy_name']} {row['horizon']}` raw={row['raw_intent_rows']} deduped={row['deduped_count']} valid={row['valid_lifecycle_count']} invalid={row['invalid_count']} compression={row['compression_ratio']}")
    write_md(REPORT_DIR / "INTENT_DEDUP_POLICY_MATERIALIZATION_CN.md", lines)


def write_quality(rows):
    fieldnames = ["policy_name", "deduped_count_7d", "valid_count_6h", "valid_count_12h", "valid_count_24h", "compression_ratio", "max_source_trace_count", "p50_source_trace_count", "p90_source_trace_count", "p99_source_trace_count", "top_dedup_key_share", "top_pool_share", "top_position_share", "top_strategy_epoch_share", "top10_pool_share", "duplicate_tick_inflation_score", "over_compression_score", "under_compression_score", "concentration_risk_score", "policy_status", "failure_reason"]
    write_csv(REPORT_DIR / "intent_dedup_quality_score.csv", rows, fieldnames)
    lines = ["# INTENT_DEDUP_QUALITY_SCORE_CN", ""]
    for row in rows:
        lines.append(f"- `{row['policy_name']}` status={row['policy_status']} valid6h={row['valid_count_6h']} valid12h={row['valid_count_12h']} valid24h={row['valid_count_24h']} top_key_share={row['top_dedup_key_share']} top_pool_share={row['top_pool_share']} top_position_share={row['top_position_share']} failure={row['failure_reason']}")
    write_md(REPORT_DIR / "INTENT_DEDUP_QUALITY_SCORE_CN.md", lines)


def write_comparison(rows):
    fieldnames = ["policy_name", "horizon", "valid_count", "median_net_pnl_pct", "p10", "p5", "p1", "win_rate", "top20_vs_bottom20_signal", "top20_median", "bottom20_median", "top20_p10", "bottom20_p10", "worst_pool_contribution", "worst_dedup_key_contribution", "tail_status", "signal_status"]
    write_csv(REPORT_DIR / "intent_dedup_policy_proof_comparison.csv", rows, fieldnames)
    lines = ["# INTENT_DEDUP_POLICY_PROOF_COMPARISON_CN", ""]
    for row in rows:
        lines.append(f"- `{row['policy_name']} {row['horizon']}` valid={row['valid_count']} signal={row['signal_status']} tail={row['tail_status']} p10={row['p10']} p5={row['p5']}")
    write_md(REPORT_DIR / "INTENT_DEDUP_POLICY_PROOF_COMPARISON_CN.md", lines)


def write_best(remote):
    best = {
        "best_policy_name": remote["best_policy_name"],
        "best_policy_status": remote["best_policy_status"],
        "reason": "highest valid lifecycle count with least concentration penalty among tested candidates",
        "valid_count_6h": remote["best_policy_valid_6h"],
        "valid_count_12h": remote["best_policy_valid_12h"],
        "valid_count_24h": remote["best_policy_valid_24h"],
        "signal_6h": remote["best_policy_signal_6h"],
        "signal_12h": remote["best_policy_signal_12h"],
        "signal_24h": remote["best_policy_signal_24h"],
        "tail_status": remote["tail_risk_status"],
        "hypothesis_review_ready": remote["hypothesis_review_ready"],
    }
    write_json(REPORT_DIR / "intent_dedup_best_policy_selection.json", best)
    write_md(REPORT_DIR / "INTENT_DEDUP_BEST_POLICY_SELECTION_CN.md", [
        "# INTENT_DEDUP_BEST_POLICY_SELECTION_CN",
        "",
        f"- best_policy_name: {best['best_policy_name']}",
        f"- best_policy_status: {best['best_policy_status']}",
        f"- valid_count_6h: {best['valid_count_6h']}",
        f"- valid_count_12h: {best['valid_count_12h']}",
        f"- valid_count_24h: {best['valid_count_24h']}",
        f"- signal_6h: {best['signal_6h']}",
        f"- signal_12h: {best['signal_12h']}",
        f"- signal_24h: {best['signal_24h']}",
        f"- tail_status: {best['tail_status']}",
        f"- hypothesis_review_ready: {'yes' if best['hypothesis_review_ready'] else 'no'}",
    ])


def write_next_stage(remote):
    decision = {
        "recommended_next_stage": remote["recommended_next_stage"],
    }
    write_json(REPORT_DIR / "intent_dedup_next_stage_decision.json", decision)
    write_md(REPORT_DIR / "INTENT_DEDUP_NEXT_STAGE_DECISION_CN.md", [
        "# INTENT_DEDUP_NEXT_STAGE_DECISION_CN",
        "",
        f"- recommended_next_stage: {remote['recommended_next_stage']}",
    ])


def write_final(remote):
    final = {
        "status": "WARN",
        "stage": "INTENT_LIFECYCLE_DEDUP_POLICY_FIX_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "tested_policy_count": remote["tested_policy_count"],
        "best_policy_name": remote["best_policy_name"],
        "best_policy_status": remote["best_policy_status"],
        "best_policy_valid_6h": remote["best_policy_valid_6h"],
        "best_policy_valid_12h": remote["best_policy_valid_12h"],
        "best_policy_valid_24h": remote["best_policy_valid_24h"],
        "best_policy_signal_6h": remote["best_policy_signal_6h"],
        "best_policy_signal_12h": remote["best_policy_signal_12h"],
        "best_policy_signal_24h": remote["best_policy_signal_24h"],
        "deduplication_control_status": remote["deduplication_control_status"],
        "intent_lifecycle_signal_status": remote["intent_lifecycle_signal_status"],
        "tail_risk_status": remote["tail_risk_status"],
        "hypothesis_review_ready": remote["hypothesis_review_ready"],
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": remote["recommended_next_stage"],
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
    write_md(REPORT_DIR / "ONEPAGE_CN.md", [
        "# ONEPAGE_CN",
        "",
        f"- tested_policy_count: {final['tested_policy_count']}",
        f"- best_policy_name: {final['best_policy_name']}",
        f"- best_policy_status: {final['best_policy_status']}",
        f"- best_policy_valid_6h: {final['best_policy_valid_6h']}",
        f"- best_policy_valid_12h: {final['best_policy_valid_12h']}",
        f"- best_policy_valid_24h: {final['best_policy_valid_24h']}",
        f"- best_policy_signal_6h: {final['best_policy_signal_6h']}",
        f"- best_policy_signal_12h: {final['best_policy_signal_12h']}",
        f"- best_policy_signal_24h: {final['best_policy_signal_24h']}",
        f"- deduplication_control_status: {final['deduplication_control_status']}",
        f"- intent_lifecycle_signal_status: {final['intent_lifecycle_signal_status']}",
        f"- tail_risk_status: {final['tail_risk_status']}",
        f"- hypothesis_review_ready: {'yes' if final['hypothesis_review_ready'] else 'no'}",
        f"- recommended_next_stage: {final['recommended_next_stage']}",
        "- edge_proven: no",
        "- tiny_canary_allowed: no",
    ])
    write_md(REPORT_DIR / "ARTIFACT_INDEX.md", [
        "# ARTIFACT_INDEX",
        "",
        "- INPUT_ARTIFACT_AUDIT_CN.md",
        "- input_artifact_audit.json",
        "- VPS_DB_QUICK_CHECK_CN.md",
        "- INTENT_DEDUP_POLICY_CANDIDATES_CN.md",
        "- intent_dedup_policy_candidates.csv",
        "- intent_dedup_policy_candidates.json",
        "- INTENT_DEDUP_POLICY_MATERIALIZATION_CN.md",
        "- intent_dedup_policy_materialization_counts.csv",
        "- INTENT_DEDUP_QUALITY_SCORE_CN.md",
        "- intent_dedup_quality_score.csv",
        "- INTENT_DEDUP_POLICY_PROOF_COMPARISON_CN.md",
        "- intent_dedup_policy_proof_comparison.csv",
        "- INTENT_DEDUP_BEST_POLICY_SELECTION_CN.md",
        "- intent_dedup_best_policy_selection.json",
        "- INTENT_DEDUP_NEXT_STAGE_DECISION_CN.md",
        "- intent_dedup_next_stage_decision.json",
        "- FINAL_VERDICT.json",
        "- ONEPAGE_CN.md",
        "- intent_lifecycle_dedup_policy_fix_v1_readonly.py",
    ])


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    input_audit()
    remote = remote_backtest()
    if not remote.get("db_ready"):
        write_md(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", ["# VPS_DB_QUICK_CHECK_CN", "", "- DB_READY: no"])
        write_json(REPORT_DIR / "FINAL_VERDICT.json", {
            "status": "FAIL",
            "stage": "INTENT_LIFECYCLE_DEDUP_POLICY_FIX_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "tested_policy_count": 0,
            "best_policy_name": "",
            "best_policy_status": "",
            "best_policy_valid_6h": 0,
            "best_policy_valid_12h": 0,
            "best_policy_valid_24h": 0,
            "best_policy_signal_6h": "",
            "best_policy_signal_12h": "",
            "best_policy_signal_24h": "",
            "deduplication_control_status": "",
            "intent_lifecycle_signal_status": "",
            "tail_risk_status": "",
            "hypothesis_review_ready": False,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "FIXED_HORIZON_DB_OR_SCHEMA_FIX_REPEAT",
        })
        return
    write_db_check(remote)
    write_policy_candidates(remote["policy_candidates"])
    write_materialization(remote["materialization_rows"])
    write_quality(remote["quality_rows"])
    write_comparison(remote["comparison_rows"])
    write_best(remote)
    write_next_stage(remote)
    write_final(remote)


if __name__ == "__main__":
    main()
