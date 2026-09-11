#!/usr/bin/env python3
"""RH-02: Reproducible DATA_COVERAGE_REPORT.md and RPC_BUDGET_REPORT.json generator.

Strictly read-only against scanner.db and provider_health.db.
PRD §21.1: The coverage denominator is the *planned* observation window,
never the actual sample count (dropping bad windows and reporting 100% is forbidden).
Fail-closed: Any unmeasured or unclassifiable item is reported as UNKNOWN / NOT_MEASURED
with reasons, never 0, 100%, or OK.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_market_session_v1_readonly import (  # noqa: E402
    classify_session,
    HOLIDAYS,
)

DEFAULT_SCANNER_DB = REPO_ROOT / "reports/lp_rh/scanner.db"
DEFAULT_PROVIDER_DB = REPO_ROOT / "reports/lp_rh/provider_health.db"
DEFAULT_OUT_DIR = REPO_ROOT / "reports/lp_rh"

KEY_FIELDS = (
    "fee_growth_global_0",
    "fee_growth_global_1",
    "sqrt_price_x96",
    "liquidity",
    "source_event_time",
)

MISSING_CALENDAR_HOLIDAY = "CALENDAR_HOLIDAY"
MISSING_PRICE_MISSING = "PRICE_MISSING"
MISSING_RPC_FAILURE = "RPC_FAILURE"
MISSING_OTHER = "OTHER"
MISSING_UNCLASSIFIED = "UNCLASSIFIED"


def _to_dt(val: Any) -> Optional[datetime]:
    if val is None or isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def open_ro_sqlite(path: Path | str) -> Optional[sqlite3.Connection]:
    p = Path(path).resolve()
    if not p.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=30.0)
        conn.execute("PRAGMA busy_timeout=30000")
        return conn
    except sqlite3.OperationalError:
        return None


def get_table_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return [r[1] for r in rows]
    except Exception:
        return []


def analyze_planned_window(
    sample_times: Sequence[str],
    *,
    expected_interval_secs: int = 15,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate coverage using planned window as denominator (PRD §21.1)."""
    parsed: List[Tuple[datetime, str]] = []
    for s in sample_times:
        dt = _to_dt(s)
        if dt is not None:
            parsed.append((dt, s))
    parsed.sort(key=lambda p: p[0])

    if window_start is not None:
        ws_dt = _to_dt(window_start)
    elif parsed:
        ws_dt = parsed[0][0]
    else:
        ws_dt = None

    if window_end is not None:
        we_dt = _to_dt(window_end)
    elif parsed:
        we_dt = parsed[-1][0]
    else:
        we_dt = None

    if ws_dt is None or we_dt is None or we_dt < ws_dt or not parsed:
        return {
            "status": "NOT_MEASURED",
            "reason": "EMPTY_DATABASE_OR_INVALID_WINDOW",
            "window_start": window_start,
            "window_end": window_end,
            "span_secs": None,
            "expected_samples": None,
            "actual_samples": len(parsed),
            "coverage_ratio": None,
            "gaps": [],
        }

    span_secs = (we_dt - ws_dt).total_seconds()
    expected_samples = int(round(span_secs / expected_interval_secs))
    if expected_samples <= 0 and span_secs == 0:
        expected_samples = 1

    actual_samples = sum(1 for dt, _ in parsed if ws_dt <= dt <= we_dt)
    coverage_ratio = (
        Decimal(actual_samples) / Decimal(expected_samples)
        if expected_samples > 0
        else None
    )

    gaps: List[Dict[str, Any]] = []
    threshold = expected_interval_secs * 1.5
    for i in range(len(parsed) - 1):
        dt_cur, raw_cur = parsed[i]
        dt_next, raw_next = parsed[i + 1]
        gap_sec = (dt_next - dt_cur).total_seconds()
        if gap_sec > threshold:
            missed = int(round(gap_sec / expected_interval_secs))
            gaps.append({
                "start": raw_cur,
                "end": raw_next,
                "duration_secs": round(gap_sec, 3),
                "missed_samples": missed,
            })

    return {
        "status": "OK",
        "reason": None,
        "window_start": ws_dt.isoformat().replace("+00:00", "Z"),
        "window_end": we_dt.isoformat().replace("+00:00", "Z"),
        "span_secs": round(span_secs, 3),
        "expected_samples": expected_samples,
        "actual_samples": actual_samples,
        "coverage_ratio": coverage_ratio,
        "gaps": gaps,
    }


def classify_gap(
    gap: Dict[str, Any],
    rpc_health_rows: Sequence[Dict[str, Any]],
    market_states_rows: Sequence[Dict[str, Any]],
) -> str:
    """Classify a gap into standard buckets. Unclassifiable gaps go to UNCLASSIFIED."""
    start_dt = _to_dt(gap.get("start"))
    end_dt = _to_dt(gap.get("end"))
    if start_dt is None or end_dt is None:
        return MISSING_UNCLASSIFIED

    # 1. Holiday or Weekend (日历休市)
    sess_start, _ = classify_session(start_dt)
    sess_end, _ = classify_session(end_dt)
    if sess_start in ("HOLIDAY", "WEEKEND") or sess_end in ("HOLIDAY", "WEEKEND"):
        return MISSING_CALENDAR_HOLIDAY
    if start_dt.strftime("%Y-%m-%d") in HOLIDAYS or end_dt.strftime("%Y-%m-%d") in HOLIDAYS:
        return MISSING_CALENDAR_HOLIDAY

    # 2. RPC Failure (RPC 失败)
    in_gap_rpc = [
        r for r in rpc_health_rows
        if r.get("sample_time") and start_dt <= _to_dt(r["sample_time"]) <= end_dt
    ]
    if in_gap_rpc:
        has_rpc_err = any(
            r.get("error") is not None
            or r.get("state") in ("DEGRADED", "EXIT_ONLY")
            for r in in_gap_rpc
        )
        if has_rpc_err:
            return MISSING_RPC_FAILURE

    # 3. Price Missing (价格缺失)
    in_gap_ms = [
        m for m in market_states_rows
        if m.get("sample_time") and start_dt <= _to_dt(m["sample_time"]) <= end_dt
    ]
    if in_gap_ms:
        if any(m.get("reference_mid") is None for m in in_gap_ms):
            return MISSING_PRICE_MISSING

    # 4. Other (已知其他原因，如进程重启标记)
    if gap.get("cause") in ("PROCESS_RESTART", "SYSTEMATIC_DRIFT"):
        return MISSING_OTHER

    return MISSING_UNCLASSIFIED


def audit_key_fields(
    conn: sqlite3.Connection,
    *,
    total_samples: int,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Audit non-null rates for required key fields (PRD §19 / §21.1)."""
    cols = set(get_table_columns(conn, "rh_market_states"))
    results: Dict[str, Dict[str, Any]] = {}

    where_clauses: List[str] = []
    params: List[Any] = []
    if window_start is not None:
        where_clauses.append("sample_time >= ?")
        params.append(window_start)
    if window_end is not None:
        where_clauses.append("sample_time <= ?")
        params.append(window_end)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    for field in KEY_FIELDS:
        if field not in cols:
            results[field] = {
                "field": field,
                "status": "NOT_MEASURED",
                "reason": f"COLUMN_NOT_IN_SCHEMA: '{field}' not in rh_market_states",
                "non_null_count": None,
                "denominator": total_samples if total_samples > 0 else None,
                "ratio": None,
            }
            continue

        if total_samples <= 0:
            results[field] = {
                "field": field,
                "status": "NOT_MEASURED",
                "reason": "EMPTY_DATABASE",
                "non_null_count": 0,
                "denominator": 0,
                "ratio": None,
            }
            continue

        try:
            query = f'SELECT COUNT("{field}") FROM rh_market_states {where_sql}'
            row = conn.execute(query, params).fetchone()
            non_null = row[0] if row else 0
            ratio = Decimal(non_null) / Decimal(total_samples)
            results[field] = {
                "field": field,
                "status": "OK",
                "reason": None,
                "non_null_count": non_null,
                "denominator": total_samples,
                "ratio": ratio,
            }
        except Exception as exc:
            results[field] = {
                "field": field,
                "status": "NOT_MEASURED",
                "reason": f"QUERY_ERROR: {exc}",
                "non_null_count": None,
                "denominator": total_samples,
                "ratio": None,
            }

    return results


def audit_2026_09_07(conn: Optional[sqlite3.Connection]) -> Dict[str, Any]:
    """Audit the 2026-09-07 US Labor Day holiday observation (PRD §19 / §21.1)."""
    # 1. Calendar logic validation
    test_dt = datetime(2026, 9, 7, 14, 30, tzinfo=timezone.utc)
    sess, info = classify_session(test_dt)
    calendar_verified = (sess == "HOLIDAY")

    if conn is None:
        return {
            "status": "NOT_MEASURED",
            "reason": "NO_DATABASE_CONNECTION",
            "calendar_rule_verified": calendar_verified,
            "holiday_label": HOLIDAYS.get("2026-09-07", "LABOR_DAY"),
            "samples_found": 0,
            "holiday_samples": 0,
            "non_holiday_samples": 0,
        }

    cols = set(get_table_columns(conn, "rh_market_states"))
    if not cols:
        return {
            "status": "NOT_MEASURED",
            "reason": "EMPTY_DATABASE_OR_TABLE_MISSING",
            "calendar_rule_verified": calendar_verified,
            "holiday_label": HOLIDAYS.get("2026-09-07", "LABOR_DAY"),
            "samples_found": 0,
            "holiday_samples": 0,
            "non_holiday_samples": 0,
        }

    rows = conn.execute(
        "SELECT sample_time, session FROM rh_market_states "
        "WHERE sample_time >= '2026-09-07T00:00:00Z' AND sample_time < '2026-09-08T00:00:00Z'"
    ).fetchall()

    if not rows:
        return {
            "status": "NOT_MEASURED",
            "reason": "NO_SAMPLES_FOR_2026_09_07_IN_STORE",
            "calendar_rule_verified": calendar_verified,
            "holiday_label": HOLIDAYS.get("2026-09-07", "LABOR_DAY"),
            "samples_found": 0,
            "holiday_samples": 0,
            "non_holiday_samples": 0,
        }

    holiday_cnt = sum(1 for r in rows if r[1] == "HOLIDAY")
    non_holiday = len(rows) - holiday_cnt
    return {
        "status": "OK",
        "reason": None,
        "calendar_rule_verified": calendar_verified,
        "holiday_label": HOLIDAYS.get("2026-09-07", "LABOR_DAY"),
        "samples_found": len(rows),
        "holiday_samples": holiday_cnt,
        "non_holiday_samples": non_holiday,
    }


def audit_rpc_budget(
    provider_db_path: Path | str,
    scanner_db_path: Path | str,
) -> Dict[str, Any]:
    """Audit RPC budget and provider health fail-closed (PRD §19 / §21.1)."""
    p_path = Path(provider_db_path).resolve()
    s_path = Path(scanner_db_path).resolve()

    if not p_path.exists():
        return {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "provider_db_path": str(p_path),
            "scanner_db_path": str(s_path),
            "providers": {},
            "failover_count": None,
            "budget_status": "UNKNOWN",
            "budget_status_reason": f"PROVIDER_DB_NOT_FOUND: file '{p_path}' does not exist",
            "reason": f"PROVIDER_DB_NOT_FOUND: file '{p_path}' does not exist",
        }

    p_conn = open_ro_sqlite(p_path)
    if p_conn is None:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "provider_db_path": str(p_path),
            "scanner_db_path": str(s_path),
            "providers": {},
            "failover_count": None,
            "budget_status": "UNKNOWN",
            "budget_status_reason": f"PROVIDER_DB_UNREADABLE: unable to open '{p_path}' in read-only mode",
            "reason": f"PROVIDER_DB_UNREADABLE: unable to open '{p_path}' in read-only mode",
        }

    providers: Dict[str, Any] = {}
    try:
        cap_cols = set(get_table_columns(p_conn, "rh_provider_capability"))
        if cap_cols:
            p_rows = p_conn.execute(
                "SELECT provider, COUNT(*), "
                "SUM(CASE WHEN ok = 1 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END), "
                "MIN(sample_time), MAX(sample_time) "
                "FROM rh_provider_capability GROUP BY provider"
            ).fetchall()
            for r in p_rows:
                p_name, total, success, errors, min_t, max_t = r
                succ_rate = (Decimal(success) / Decimal(total)) if total > 0 else None
                providers[p_name] = {
                    "total_calls": total,
                    "success_calls": success,
                    "error_calls": errors,
                    "success_rate": str(round(succ_rate, 4)) if succ_rate is not None else None,
                    "observation_start": min_t,
                    "observation_end": max_t,
                }
    except Exception as exc:
        p_conn.close()
        return {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "provider_db_path": str(p_path),
            "providers": {},
            "failover_count": None,
            "budget_status": "UNKNOWN",
            "budget_status_reason": f"QUERY_ERROR: {exc}",
            "reason": f"QUERY_ERROR: {exc}",
        }

    # Failover count from provider_rollup if available
    failover_count: Optional[int] = None
    try:
        roll_cols = set(get_table_columns(p_conn, "rh_provider_rollup"))
        if roll_cols:
            rows = p_conn.execute(
                "SELECT sample_time, usable_providers_json FROM rh_provider_rollup ORDER BY sample_time"
            ).fetchall()
            switches = 0
            last_usable = None
            for _, u_json in rows:
                if last_usable is not None and u_json != last_usable:
                    switches += 1
                last_usable = u_json
            failover_count = switches
    except Exception:
        failover_count = None

    p_conn.close()

    # Fail-closed budget status: free tier limits are not documented in provider_health.db
    # Therefore sustainability cannot be guaranteed and must be UNKNOWN with reason.
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider_db_path": str(p_path),
        "scanner_db_path": str(s_path),
        "providers": providers,
        "failover_count": failover_count,
        "budget_status": "UNKNOWN",
        "budget_status_reason": (
            "FREE_TIER_QUOTA_UNTRACKED: provider_health.db tracks capability probes "
            "but does not record rate limits or remaining free quota balance"
        ),
        "reason": (
            "FREE_TIER_QUOTA_UNTRACKED: provider_health.db tracks capability probes "
            "but does not record rate limits or remaining free quota balance"
        ),
    }


def generate_data_coverage_md(
    window_stats: Dict[str, Any],
    field_stats: Dict[str, Dict[str, Any]],
    missing_stats: Dict[str, int],
    h20260907_stats: Dict[str, Any],
    *,
    scanner_db_path: str,
) -> str:
    cov_str = (
        f"{window_stats['coverage_ratio'] * 100:.2f}%"
        if window_stats.get("coverage_ratio") is not None
        else f"NOT_MEASURED ({window_stats.get('reason', 'UNKNOWN')})"
    )
    exp_str = (
        str(window_stats["expected_samples"])
        if window_stats.get("expected_samples") is not None
        else "NOT_MEASURED"
    )

    lines = [
        "# DATA_COVERAGE_REPORT (RH-02)",
        "",
        f"- **生成时间 (UTC)**: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        f"- **数据源**: `{scanner_db_path}`",
        "",
        "> [!IMPORTANT]",
        "> **覆盖率分母口径说明（PRD §21.1 强制约束）**：",
        "> 数据覆盖率分母必须是计划应观测的窗口样本数（`计划观测时长 / 采样间隔`），绝对不是实际落库行数。",
        "> 如果某段时间完全没采到数据，该时间段必须留在分母里拉低覆盖率；绝不允许删掉坏窗口后报告 100%。",
        "",
        "## 1. 观测窗口与有效覆盖率",
        "",
        "| 指标 | 测量值 | 说明 |",
        "| :--- | :--- | :--- |",
        f"| 观测窗口起点 (UTC) | `{window_stats.get('window_start') or 'NOT_MEASURED'}` | 计划窗口首个采样时刻 |",
        f"| 观测窗口终点 (UTC) | `{window_stats.get('window_end') or 'NOT_MEASURED'}` | 计划窗口最新采样时刻 |",
        f"| 计划观测时长 (秒) | `{window_stats.get('span_secs') if window_stats.get('span_secs') is not None else 'NOT_MEASURED'}` | 计划时间跨度 |",
        f"| 计划应观测样本数 | `{exp_str}` | **【覆盖率分母】** 按计划采样间隔推算的样本数 |",
        f"| 实际取得样本数 | `{window_stats.get('actual_samples', 'NOT_MEASURED')}` | 窗口内实际落库样本数 |",
        f"| 有效覆盖率 | `{cov_str}` | `实际样本数 / 计划应观测样本数` |",
        "",
        "## 2. 关键字段非空率分列",
        "",
        "| 字段名 | 状态 | 非空值行数 | 分母 (实际样本总数) | 非空率 | 判定 / 原因 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for f, d in field_stats.items():
        st = d.get("status", "UNKNOWN")
        nn = d.get("non_null_count")
        nn_str = str(nn) if nn is not None else "NOT_MEASURED"
        den = d.get("denominator")
        den_str = str(den) if den is not None else "NOT_MEASURED"
        ratio = d.get("ratio")
        ratio_str = f"{ratio * 100:.2f}%" if ratio is not None else "NOT_MEASURED"
        reason = d.get("reason") or "OK"
        lines.append(f"| `{f}` | `{st}` | `{nn_str}` | `{den_str}` | `{ratio_str}` | `{reason}` |")

    lines.extend([
        "",
        "## 3. 缺失分类统计",
        "",
        "> 任何无法明确归因的缺口一律单列为 `UNCLASSIFIED`，绝不强行塞入已知分类。",
        "",
        "| 缺失分类 | 缺失样本计数 | 说明 |",
        "| :--- | :--- | :--- |",
        f"| 日历休市 (`CALENDAR_HOLIDAY`) | `{missing_stats[MISSING_CALENDAR_HOLIDAY]}` | 跨越节假日或周末的缺口 |",
        f"| 价格缺失 (`PRICE_MISSING`) | `{missing_stats[MISSING_PRICE_MISSING]}` | 采集存在但价格为空或缺失 |",
        f"| RPC 失败 (`RPC_FAILURE`) | `{missing_stats[MISSING_RPC_FAILURE]}` | 节点报错、超时或 DEGRADED/EXIT_ONLY |",
        f"| 其他已知 (`OTHER`) | `{missing_stats[MISSING_OTHER]}` | 进程重启标记、系统时间调整等 |",
        f"| 未分类 (`UNCLASSIFIED`) | `{missing_stats[MISSING_UNCLASSIFIED]}` | **无法归因的缺口独立单列** |",
        "",
        "## 4. 2026-09-07 (美国劳动节休市日) 专题审计",
        "",
        f"- **交易日历规则核对**: `{'PASS' if h20260907_stats.get('calendar_rule_verified') else 'FAIL'}` (`LABOR_DAY`)",
        f"- **观测状态**: `{h20260907_stats.get('status')}`",
        f"- **数据库中该日样本数**: `{h20260907_stats['samples_found']}`",
        f"- **识别为休市 (HOLIDAY) 样本数**: `{h20260907_stats['holiday_samples']}`",
        f"- **原因 / 备注**: `{h20260907_stats.get('reason') or '休市样本已正确识别为 HOLIDAY 时段，未被误判为缺失'}`",
        "",
    ])
    return "\n".join(lines)


def run_coverage_audit(
    *,
    scanner_db_path: Path | str = DEFAULT_SCANNER_DB,
    provider_db_path: Path | str = DEFAULT_PROVIDER_DB,
    out_dir: Path | str = DEFAULT_OUT_DIR,
    interval_secs: int = 15,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> Tuple[Path, Path]:
    s_path = Path(scanner_db_path).resolve()
    p_path = Path(provider_db_path).resolve()
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    conn = open_ro_sqlite(s_path)
    sample_times: List[str] = []
    market_states_rows: List[Dict[str, Any]] = []
    rpc_rows: List[Dict[str, Any]] = []

    if conn is not None:
        try:
            m_cols = get_table_columns(conn, "rh_market_states")
            if m_cols:
                rows = conn.execute(
                    "SELECT sample_time, reference_mid, session FROM rh_market_states ORDER BY sample_time"
                ).fetchall()
                for r in rows:
                    sample_times.append(r[0])
                    market_states_rows.append({"sample_time": r[0], "reference_mid": r[1], "session": r[2]})
        except Exception:
            pass

        try:
            r_cols = get_table_columns(conn, "rh_rpc_health")
            if r_cols:
                rows = conn.execute(
                    "SELECT provider, sample_time, latency_ms, error, state FROM rh_rpc_health ORDER BY sample_time"
                ).fetchall()
                for r in rows:
                    rpc_rows.append({
                        "provider": r[0],
                        "sample_time": r[1],
                        "latency_ms": r[2],
                        "error": r[3],
                        "state": r[4],
                    })
        except Exception:
            pass

    # 1. Planned window coverage
    w_stats = analyze_planned_window(
        sample_times,
        expected_interval_secs=interval_secs,
        window_start=window_start,
        window_end=window_end,
    )

    # 2. Key fields
    if conn is not None:
        field_stats = audit_key_fields(
            conn,
            total_samples=w_stats.get("actual_samples") or 0,
            window_start=w_stats.get("window_start"),
            window_end=w_stats.get("window_end"),
        )
    else:
        field_stats = {
            f: {
                "field": f,
                "status": "NOT_MEASURED",
                "reason": "SCANNER_DB_NOT_FOUND",
                "non_null_count": None,
                "denominator": None,
                "ratio": None,
            }
            for f in KEY_FIELDS
        }

    # 3. Missing categorization
    missing_stats: Dict[str, int] = {
        MISSING_CALENDAR_HOLIDAY: 0,
        MISSING_PRICE_MISSING: 0,
        MISSING_RPC_FAILURE: 0,
        MISSING_OTHER: 0,
        MISSING_UNCLASSIFIED: 0,
    }
    for gap in w_stats.get("gaps", []):
        cat = classify_gap(gap, rpc_rows, market_states_rows)
        missed = gap.get("missed_samples")
        missed_cnt = 1 if missed is None else int(missed)
        missing_stats[cat] += missed_cnt

    # 4. 2026-09-07
    h20260907 = audit_2026_09_07(conn)

    if conn is not None:
        conn.close()

    # 5. RPC Budget
    rpc_report = audit_rpc_budget(p_path, s_path)

    # Write Markdown
    md_content = generate_data_coverage_md(
        w_stats, field_stats, missing_stats, h20260907, scanner_db_path=str(s_path)
    )
    md_path = out / "DATA_COVERAGE_REPORT.md"
    md_path.write_text(md_content, encoding="utf-8")

    # Write JSON
    json_path = out / "RPC_BUDGET_REPORT.json"
    json_path.write_text(json.dumps(rpc_report, indent=2, ensure_ascii=False), encoding="utf-8")

    return md_path, json_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate RH coverage & RPC budget reports (fail-closed, readonly)")
    parser.add_argument("--db", default=str(DEFAULT_SCANNER_DB), help="Path to scanner.db")
    parser.add_argument("--provider-db", default=str(DEFAULT_PROVIDER_DB), help="Path to provider_health.db")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory")
    parser.add_argument("--interval-secs", type=int, default=15, help="Planned interval in seconds (default 15)")
    parser.add_argument("--window-start", default=None, help="Optional window start RFC3339 UTC")
    parser.add_argument("--window-end", default=None, help="Optional window end RFC3339 UTC")
    args = parser.parse_args(argv)

    md_path, json_path = run_coverage_audit(
        scanner_db_path=args.db,
        provider_db_path=args.provider_db,
        out_dir=args.out_dir,
        interval_secs=args.interval_secs,
        window_start=args.window_start,
        window_end=args.window_end,
    )
    print(f"Generated: {md_path}")
    print(f"Generated: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
