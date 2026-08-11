#!/usr/bin/env python3
"""Explain every terminal funnel loss without changing any gate.

The tool consumes a completed read-only scanner database plus the exact
Stage-1 snapshots used for the run.  It never calls RPC, opens SQLite in
read-only mode, and recomputes acceptance as the complete conjunction of the
existing status, quality, yield, stability, entry, NetCover and PositionCap
bits.

An optional raw DefiLlama snapshot reproduces the *shape* of the independent
2026-08-09 feasibility screen.  The original one-off script did not preserve
its 213 pool identities, so this run labels the reconstructed cohort with its
own count instead of pretending it is the historical list.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


GATE_ORDER = (
    "resolution_status",
    "asset_quality",
    "yield_cover",
    "multiwindow_stable",
    "entry_eligible",
    "netcover",
    "position_cap",
)
GATE_LABELS = {
    "resolution_status": "resolution/status（技术完整性）",
    "asset_quality": "资产质量 tier",
    "yield_cover": "yield_cover",
    "multiwindow_stable": "多窗口 stable",
    "entry_eligible": "entry_eligible",
    "netcover": "NetCover",
    "position_cap": "PositionCap",
}
STABLE_MIN_FRAC = 0.70
YIELD_COVER_MIN = 1.0
NETCOVER_MIN = 1.0
M1_POSITION_USD = 50.0
SUPPORTED_CHAINS = frozenset({"base", "solana"})
INDEPENDENT_PROJECTS = frozenset({
    "aerodrome-slipstream",
    "uniswap-v3",
    "orca-dex",
    "raydium-amm",
})


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _identity(record: Mapping[str, Any]) -> str:
    return str(record.get("llama_pool_id") or record.get("pool") or "")


def gate_bits(record: Mapping[str, Any]) -> dict[str, bool]:
    """Return the complete terminal conjunction from authoritative fields."""
    gates = record.get("gates") if isinstance(record.get("gates"), Mapping) else {}
    return {
        "resolution_status": bool(gates.get("status_ok", False)),
        "asset_quality": bool(gates.get("quality", False)),
        "yield_cover": bool(gates.get("yield_cover", False)),
        "multiwindow_stable": bool(gates.get("stable", False)),
        "entry_eligible": record.get("entry_eligible") is True,
        "netcover": record.get("netcover_pass") is True,
        "position_cap": record.get("position_cap_pass") is True,
    }


def first_failed_gate(record: Mapping[str, Any]) -> str | None:
    bits = gate_bits(record)
    return next((gate for gate in GATE_ORDER if not bits[gate]), None)


def recomputed_accepted(record: Mapping[str, Any]) -> bool:
    return all(gate_bits(record).values())


def _quality_distance(record: Mapping[str, Any]) -> tuple[float, str]:
    tier = str(record.get("tier_quality") or "C").upper()
    if tier in {"A", "B"}:
        return 0.0, "PASS"
    return 1.0, "tier C：两腿中至少还需 1 个 major 资产"


def gate_distance(record: Mapping[str, Any], gate: str) -> tuple[float, str]:
    """Comparable shortfall for ranking failed rows at one gate."""
    if gate == "resolution_status":
        return 1.0, str(
            record.get("permanent_fail_closed_reason")
            or record.get("error")
            or record.get("root_cause")
            or record.get("blocked_reason")
            or record.get("status")
            or record.get("resolve_status")
            or "状态证据缺失"
        )
    if gate == "asset_quality":
        return _quality_distance(record)
    if gate == "yield_cover":
        value = _finite(record.get("yield_cover"))
        return (
            (YIELD_COVER_MIN - value, f"{value:.6f}，差 {YIELD_COVER_MIN-value:.6f}")
            if value is not None
            else (math.inf, "yield_cover 输入缺失")
        )
    if gate == "multiwindow_stable":
        value = _finite(record.get("enter_frac"))
        return (
            (max(0.0, STABLE_MIN_FRAC - value), f"enter_frac={value:.3f}，差 {max(0.0, STABLE_MIN_FRAC-value):.3f}")
            if value is not None
            else (math.inf, "多窗口输入缺失")
        )
    if gate == "entry_eligible":
        measured = _finite(record.get("reward_high_duration")) or 0.0
        score = _finite(record.get("reward_persistence_score")) or 0.0
        status = str(record.get("reward_persistence_status") or "MISSING")
        reason = ",".join(str(x) for x in record.get("entry_block_reasons") or ())
        # Higher persistence score/duration is closer; encode it as a distance.
        distance = (1.0 - min(1.0, max(0.0, score))) + max(0.0, 24.0 - measured) / 2400.0
        return distance, f"{status}; score={score:.2f}; measured={measured:.2f}h; {reason or '需合格证据'}"
    if gate == "netcover":
        value = _finite(record.get("netcover_ratio", record.get("netcover")))
        return (
            (NETCOVER_MIN - value, f"{value:.6f}，差 {NETCOVER_MIN-value:.6f}")
            if value is not None
            else (math.inf, f"输入缺失：{record.get('netcover_gate_status') or record.get('rejection_reason')}")
        )
    if gate == "position_cap":
        value = _finite(record.get("position_cap_usd"))
        hard_ok = record.get("position_cap_hard_tvl_share_ok") is True
        detail = "hard-share PASS" if hard_ok else "hard-share 缺失/失败"
        return (
            (max(0.0, M1_POSITION_USD - value), f"cap={value:.6f}U，差 {max(0.0, M1_POSITION_USD-value):.6f}U；{detail}")
            if value is not None
            else (math.inf, f"cap 输入缺失；{detail}")
        )
    raise ValueError(f"unknown gate: {gate}")


def decay_table(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    survivors = list(records)
    rows: list[dict[str, Any]] = []
    for gate in GATE_ORDER:
        before = len(survivors)
        survivors = [record for record in survivors if gate_bits(record)[gate]]
        rows.append({
            "gate": gate,
            "label": GATE_LABELS[gate],
            "entered": before,
            "eliminated": before - len(survivors),
            "survived": len(survivors),
        })
    return rows


def closest_failures(
    records: Sequence[Mapping[str, Any]], gate: str, *, limit: int = 5
) -> list[dict[str, Any]]:
    """Rank failures that actually reached this gate in sequential order."""
    gate_index = GATE_ORDER.index(gate)
    prior = GATE_ORDER[:gate_index]
    eligible = []
    for record in records:
        bits = gate_bits(record)
        if all(bits[item] for item in prior) and not bits[gate]:
            distance, detail = gate_distance(record, gate)
            eligible.append((distance, str(record.get("symbol") or ""), record, detail))
    eligible.sort(key=lambda item: (math.isinf(item[0]), item[0], item[1], _identity(item[2])))
    return [{
        "symbol": record.get("symbol"),
        "llama_pool_id": record.get("llama_pool_id"),
        "resolved_pool": record.get("resolved_pool") or record.get("pool"),
        "distance": None if math.isinf(distance) else distance,
        "distance_detail": detail,
        "first_failed_gate": first_failed_gate(record),
    } for distance, _symbol, record, detail in eligible[:limit]]


def independent_feasibility_cohort(raw_pools: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Re-run the documented one-off H=30d lead screen on one raw snapshot.

    This intentionally preserves that audit's coarse assumptions (65% base
    fee retention, uniform 50% reward haircut and fixed-cost-only comparison).
    It is diagnostic only and is not the production proxy or an entry gate.
    """
    rows: list[dict[str, Any]] = []
    for source in raw_pools:
        chain = str(source.get("chain") or "").lower()
        project = str(source.get("project") or "").lower()
        if chain not in SUPPORTED_CHAINS or project not in INDEPENDENT_PROJECTS:
            continue
        tvl = _finite(source.get("tvlUsd")) or 0.0
        base = _finite(source.get("apyBase")) or 0.0
        reward = _finite(source.get("apyReward")) or 0.0
        raw_apr = base + reward
        if tvl < 100_000.0 or raw_apr <= 0.0 or raw_apr > 2_000.0:
            continue
        match = re.search(r"([\d.]+)\s*%", str(source.get("poolMeta") or ""))
        if not match:
            continue
        fee_tier = float(match.group(1)) / 100.0
        gas = 0.0795 if chain == "base" else 0.01
        fixed_drag = ((2.0 * fee_tier * M1_POSITION_USD + gas) / M1_POSITION_USD) * (365.0 / 30.0) * 100.0 + 0.5
        income = base * 0.65 + reward * 0.50
        if income <= fixed_drag:
            continue
        rows.append({
            **dict(source),
            "independent_income_apr_pct": income,
            "independent_fixed_drag_apr_pct": fixed_drag,
            "independent_il_tolerance_apr_pct": (income - fixed_drag) / 1.5,
            "independent_semantics": "historical_audit_shape_recomputed_current_snapshot_not_entry_gate",
        })
    return sorted(rows, key=lambda row: row["independent_il_tolerance_apr_pct"], reverse=True)


def cross_validate(
    cohort: Sequence[Mapping[str, Any]],
    stage1_records: Sequence[Mapping[str, Any]],
    terminal_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    screen = {_identity(record): record for record in stage1_records}
    terminal = {_identity(record): record for record in terminal_records}
    rows = []
    for source in cohort:
        identity = str(source.get("pool") or source.get("llama_pool_id") or "")
        screened = screen.get(identity)
        scored = terminal.get(identity)
        chain = str(source.get("chain") or "").lower()
        if chain == "solana":
            death = "BEFORE_MAIN_FUNNEL:M1_A_FORBIDDEN_SOLANA"
        elif screened is None:
            death = "BEFORE_STAGE1:SNAPSHOT_OR_SCOPE_MISMATCH"
        elif screened.get("gate_ok") is not True:
            death = f"STAGE1_COARSE:{screened.get('gate_reason')}"
        elif scored is None:
            death = "AFTER_STAGE1:NOT_PRESENT_IN_TERMINAL_COHORT"
        else:
            failure = first_failed_gate(scored)
            if failure:
                _distance, detail = gate_distance(scored, failure)
                death = f"{failure}:{detail}"
            else:
                death = "ACCEPTED"
        rows.append({
            "llama_pool_id": identity,
            "symbol": source.get("symbol"),
            "chain": source.get("chain"),
            "project": source.get("project"),
            "stablecoin": source.get("stablecoin") is True,
            "independent_il_tolerance_apr_pct": source.get("independent_il_tolerance_apr_pct"),
            "stage1_gate_ok": None if screened is None else screened.get("gate_ok") is True,
            "stage1_rank": None if scored is None else scored.get("stage1_rank"),
            "terminal_first_failed_gate": None if scored is None else first_failed_gate(scored),
            "terminal_netcover": None if scored is None else scored.get("netcover_ratio"),
            "terminal_accepted": False if scored is None else recomputed_accepted(scored),
            "death": death,
        })
    return rows


def load_latest_scores(
    db_path: Path, *, as_of: str | None = None,
) -> tuple[str | None, list[dict[str, Any]]]:
    uri = f"file:{db_path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
        if as_of is None:
            latest_row = connection.execute("SELECT max(as_of) FROM opportunity_scores").fetchone()
            latest = latest_row[0] if latest_row else None
        else:
            latest = as_of
        raw_rows = [] if latest is None else connection.execute(
            "SELECT score_json, accepted FROM opportunity_scores WHERE as_of=? ORDER BY id", (latest,)
        ).fetchall()
    records = []
    for raw, accepted in raw_rows:
        record = json.loads(raw)
        record["_stored_accepted"] = bool(accepted)
        records.append(record)
    return latest, records


def build_report(
    *,
    db_path: Path,
    stage1_records: Sequence[Mapping[str, Any]],
    raw_pools: Sequence[Mapping[str, Any]] | None = None,
    scanner_rpc_health: str = "UNKNOWN",
    scanner_as_of: str | None = None,
) -> dict[str, Any]:
    latest, terminal = load_latest_scores(db_path, as_of=scanner_as_of)
    decay = decay_table(terminal)
    closest = {gate: closest_failures(terminal, gate) for gate in GATE_ORDER}
    cohort = independent_feasibility_cohort(raw_pools or ())
    cross = cross_validate(cohort, stage1_records, terminal)
    named_symbols = ("USDC-AVAIL", "CADC-USDC", "MSUSD-USDC", "XSGD-USDC", "VCHF-USDC")
    cohort_by_identity = {_identity(record): record for record in cohort}
    named_sources = [
        cohort_by_identity.get(_identity(record), record)
        for record in (raw_pools or ())
        if str(record.get("symbol") or "") in named_symbols
        and str(record.get("chain") or "").lower() in SUPPORTED_CHAINS
        and str(record.get("project") or "").lower() in INDEPENDENT_PROJECTS
    ]
    named_cross = cross_validate(named_sources, stage1_records, terminal)
    present_named = {str(record.get("symbol")) for record in named_cross}
    named_cross.extend({
        "llama_pool_id": None,
        "symbol": symbol,
        "chain": None,
        "project": None,
        "stablecoin": None,
        "independent_il_tolerance_apr_pct": None,
        "stage1_gate_ok": None,
        "stage1_rank": None,
        "terminal_first_failed_gate": None,
        "terminal_netcover": None,
        "terminal_accepted": False,
        "death": "MISSING_FROM_CURRENT_DEFILLAMA_SNAPSHOT",
    } for symbol in named_symbols if symbol not in present_named)
    accepted = sum(recomputed_accepted(record) for record in terminal)
    stored_accepted = sum(record.get("_stored_accepted") is True for record in terminal)
    return {
        "schema": "lp_funnel_autopsy_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "scanner_db": str(db_path),
            "scanner_as_of": latest,
            "stage1_records": len(stage1_records),
            "stage1_coarse_pass": sum(record.get("gate_ok") is True for record in stage1_records),
            "terminal_records": len(terminal),
            "scanner_rpc_health": str(scanner_rpc_health).upper(),
        },
        "scope": {
            "main_funnel": "Base aerodrome-slipstream + uniswap-v3; all Stage-1 coarse-pass rows, capped at top-200",
            "historical_213_identity_status": "NOT_REPRODUCIBLE_ORIGINAL_ONE_OFF_MEMBERSHIP_NOT_PRESERVED",
            "independent_crosscheck": "same documented coarse formula re-run on supplied raw snapshot; count may differ from 213",
        },
        "decay": decay,
        "closest_five": closest,
        "accepted_recomputed": accepted,
        "accepted_stored_field_count": stored_accepted,
        "terminal_conjunction_match": accepted == stored_accepted,
        "netcover_failures": {
            "missing_input": sum(
                first_failed_gate(record) == "netcover" and _finite(record.get("netcover_ratio")) is None
                for record in terminal
            ),
            "calculated_below_1": sum(
                first_failed_gate(record) == "netcover"
                and (_finite(record.get("netcover_ratio")) is not None)
                and float(record.get("netcover_ratio")) < NETCOVER_MIN
                for record in terminal
            ),
        },
        "entry_failure_reasons": dict(Counter(
            str(reason)
            for record in terminal
            if first_failed_gate(record) == "entry_eligible"
            for reason in (record.get("entry_block_reasons") or [record.get("reward_persistence_status") or "UNKNOWN"])
        )),
        "independent_cohort": {
            "count": len(cohort),
            "stablecoin_count": sum(record.get("stablecoin") is True for record in cohort),
            "death_counts": dict(Counter(record["death"] for record in cross)),
            "rows": cross,
        },
        "named_historical_crosscheck": named_cross,
        "terminal_rows": [{
            "llama_pool_id": record.get("llama_pool_id"),
            "symbol": record.get("symbol"),
            "stage1_rank": record.get("stage1_rank"),
            "resolved_pool": record.get("resolved_pool") or record.get("pool"),
            "bits": gate_bits(record),
            "first_failed_gate": first_failed_gate(record),
            "accepted": recomputed_accepted(record),
            "rejection_reason": record.get("rejection_reason"),
            "yield_cover": record.get("yield_cover"),
            "enter_frac": record.get("enter_frac"),
            "reward_persistence_status": record.get("reward_persistence_status"),
            "netcover_ratio": record.get("netcover_ratio"),
            "position_cap_usd": record.get("position_cap_usd"),
        } for record in terminal],
    }


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
        *("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows),
    ]


def render_markdown(report: Mapping[str, Any]) -> str:
    source = report["source"]
    entry_reasons = "；".join(
        f"{reason}={count}"
        for reason, count in sorted(report["entry_failure_reasons"].items())
    ) or "无"
    lines = [
        "# LP funnel autopsy — top-200 / all Stage-1 coarse-pass",
        "",
        f"结论：本批终闸完整合取后 `accepted={report['accepted_recomputed']}`；分析的是 {source['stage1_coarse_pass']} 个 Stage-1 粗筛通过池中的 {source['terminal_records']} 个终端记录。",
        "未改动任何阈值；resolution/status 被单列为技术完整性闸，防止统计表遗漏终闸条件。",
        "",
        "## 1. 逐闸衰减",
        "",
        *_md_table(
            ("闸", "进入", "本闸淘汰", "存活"),
            ((row["label"], row["entered"], row["eliminated"], row["survived"]) for row in report["decay"]),
        ),
        "",
        f"entry_eligible 首次淘汰子原因：{entry_reasons}。",
        f"NetCover 首次淘汰细分：输入缺失 {report['netcover_failures']['missing_input']}；可计算但 `<1.0` {report['netcover_failures']['calculated_below_1']}。",
        "",
        "## 2. 每闸最接近通过的 5 个池",
        "",
    ]
    for gate in GATE_ORDER:
        rows = report["closest_five"][gate]
        table_rows = [
            (row["symbol"], row["llama_pool_id"], row["distance_detail"])
            for row in rows
        ] or [("—", "—", "没有到达本闸后失败的池")]
        lines.extend([
            f"### {GATE_LABELS[gate]}",
            "",
            *_md_table(
                ("池", "Llama ID", "差距"),
                table_rows,
            ),
            "",
        ])
    independent = report["independent_cohort"]
    highlighted = report["named_historical_crosscheck"]
    lines.extend([
        "## 3. 独立核查交叉验证",
        "",
        "2026-08-09 一次性核查只保留了汇总数 `213`，没有保留 213 个池的身份列表或原始快照，因此无法诚实地声称逐个复原历史成员。下表是在本次随报告保存的 DefiLlama 快照上，用该文档披露的 H=30d、50U、65% fee、统一 50% reward haircut 和 fixed-cost-only 公式重跑的当前 cohort；它不是主漏斗入场闸。",
        "",
        f"当前重跑 cohort={independent['count']}，其中 stablecoin={independent['stablecoin_count']}；逐池结果全部保存在 `AUTOPSY.json.independent_cohort.rows`。",
        "",
        *_md_table(
            ("池", "链/项目", "IL 容忍 APR", "死点"),
            ((
                row["symbol"],
                f"{row['chain']}/{row['project']}",
                "—" if row["independent_il_tolerance_apr_pct"] is None else f"{float(row['independent_il_tolerance_apr_pct']):.3f}%",
                row["death"],
            ) for row in highlighted)
            or (("点名池均未进入当前重跑 cohort", "—", "—", "快照/收益变化"),),
        ),
        "",
        "差异来源：历史核查覆盖 Base+Solana 且 TVL 门槛为 100K；主漏斗只支持 Base 两协议、M1 粗筛 TVL 为 150K、vol1d 为 50K，还要求资产质量、链上多窗口、reward persistence、完整 NetCover 和 PositionCap。Solana 因 M1-A 明令禁止而停在主漏斗之前。",
        "",
        "## 4. 可审计性",
        "",
        f"- scanner as_of: `{source['scanner_as_of']}`",
        f"- scanner cycle RPC health: `{source['scanner_rpc_health']}`（健康状态不参与放宽任何闸）",
        f"- terminal conjunction 与存储 accepted 计数一致：`{report['terminal_conjunction_match']}`",
        "- JSON 保留每个终端池的逐位 gate bits、first failure、差距输入，以及独立 cohort 的逐池 death。",
        "- 本工具仅以 SQLite `mode=ro` 读取；无钱包、签名、广播或阈值写入路径。",
        "",
    ])
    return "\n".join(lines)


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        for key in ("data", "records", "pools", "merged"):
            if isinstance(value.get(key), list):
                return value[key]
    raise ValueError("expected a JSON list or object containing data/records/pools/merged")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only LP funnel autopsy")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--stage1-screen", required=True, type=Path)
    parser.add_argument("--defillama-raw", type=Path)
    parser.add_argument(
        "--scanner-rpc-health", choices=("NORMAL", "DEGRADED", "UNKNOWN"), default="UNKNOWN"
    )
    parser.add_argument(
        "--scanner-as-of",
        help="exact scanner opportunity_scores.as_of snapshot; defaults to latest",
    )
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    stage1 = _as_list(json.loads(args.stage1_screen.read_text(encoding="utf-8")))
    raw = None if args.defillama_raw is None else _as_list(
        json.loads(args.defillama_raw.read_text(encoding="utf-8"))
    )
    report = build_report(
        db_path=args.db,
        stage1_records=stage1,
        raw_pools=raw,
        scanner_rpc_health=args.scanner_rpc_health,
        scanner_as_of=args.scanner_as_of,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "AUTOPSY.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (args.out / "AUTOPSY.md").write_text(render_markdown(report), encoding="utf-8")
    print(
        f"autopsy terminal={report['source']['terminal_records']} "
        f"accepted={report['accepted_recomputed']} independent={report['independent_cohort']['count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
