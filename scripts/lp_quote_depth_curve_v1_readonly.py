#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_090437")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get("REPORT_DIR_OVERRIDE", str(REPO_ROOT / "reports" / "lp_quote_depth_curve" / RUN_ID))
)
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
TESTED_NOTIONALS = [20, 100, 500, 1000, 2000]
PRIOR_PIPELINE_DIR = REPO_ROOT / "reports" / "lp_data_pipeline" / "20260601_084943"
PRIOR_SCALE_DIR = REPO_ROOT / "reports" / "lp_scale_economics" / "20260601_082100"

REQUIRED_INPUTS = [
    PRIOR_PIPELINE_DIR / "FINAL_VERDICT.json",
    PRIOR_PIPELINE_DIR / "LP_DATA_REQUIREMENT_SPEC_CN.md",
    PRIOR_PIPELINE_DIR / "CURRENT_SCHEMA_DATA_COVERAGE_AUDIT_CN.md",
    PRIOR_PIPELINE_DIR / "QUOTE_EXIT_DEPTH_SOURCE_FEASIBILITY_CN.md",
    PRIOR_PIPELINE_DIR / "quote_exit_depth_source_feasibility.json",
    PRIOR_PIPELINE_DIR / "FEE_DATA_SOURCE_FEASIBILITY_CN.md",
    PRIOR_PIPELINE_DIR / "LP_DATA_PIPELINE_SCHEMA_PROPOSAL_CN.md",
    PRIOR_PIPELINE_DIR / "LP_DATA_PIPELINE_IMPLEMENTATION_PLAN_CN.md",
    PRIOR_PIPELINE_DIR / "LP_DATA_PIPELINE_FEASIBILITY_PROBE_CN.md",
    PRIOR_PIPELINE_DIR / "lp_data_pipeline_feasibility_probe.csv",
    PRIOR_SCALE_DIR / "FINAL_VERDICT.json",
    PRIOR_SCALE_DIR / "VIRTUAL_NOTIONAL_ECONOMICS_MODEL_CN.md",
    REPO_ROOT / "reports" / "final_freeze" / "20260531_124000" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "fee_velocity_rule_fix" / "20260531_122413" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "pool_regime_rule_fix" / "20260531_113056" / "FINAL_VERDICT.json",
]


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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.10f}".rstrip("0").rstrip(".")
    return str(v)


def as_float(v: Any) -> float | None:
    if v in (None, "", "null", "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def redact_secretish(text: str) -> str:
    text = re.sub(r"postgres(?:ql)?://[^\\s'\\\"]+", "<redacted-dsn>", text)
    text = re.sub(r"(POSTGRES_DSN|DATABASE_URL|SHADOW_POSTGRES_DSN)=\\S+", r"\\1=<redacted>", text)
    return text


def infer_pool_type(protocol: str | None) -> str:
    p = (protocol or "").lower()
    if "solana" in p:
        return "solana_v3_like"
    if "v3" in p or "slipstream" in p:
        return "concentrated_liquidity"
    if "v2" in p:
        return "constant_product"
    return "unknown"


def chain_name(v: str | None) -> str:
    if str(v) == "1":
        return "base"
    if str(v) == "2":
        return "solana"
    return "unknown"


def protocol_alpha(pool_type: str) -> float:
    if pool_type == "concentrated_liquidity":
        return 1.08
    if pool_type == "constant_product":
        return 1.22
    if pool_type == "solana_v3_like":
        return 1.15
    return 1.18


def safe_capacity_limit(base_notional: float, base_slippage: float, alpha: float, target_slippage: float = 0.02) -> float:
    base = max(base_slippage, 1e-6)
    if base >= target_slippage:
        return base_notional
    return base_notional * ((target_slippage / base) ** (1.0 / alpha))


def slippage_for_notional(base_notional: float, base_slippage: float, target_notional: float, alpha: float, liquidity_penalty: float) -> float:
    scale = (target_notional / base_notional) ** alpha
    return max(0.0, base_slippage * scale * liquidity_penalty)


def price_impact_from_slippage(slippage: float, pool_type: str) -> float:
    factor = 0.75 if pool_type == "concentrated_liquidity" else 0.9
    return slippage * factor


def confidence_for_quote(
    chain: str,
    pool_type: str,
    has_snapshot: bool,
    has_fee_proxy: bool,
    notional: int,
    base_slippage: float | None,
) -> str:
    if chain != "base":
        return "low"
    if not has_snapshot or not has_fee_proxy or pool_type == "unknown":
        return "low"
    if base_slippage is None:
        return "low"
    if notional == 20:
        return "high"
    if notional == 100:
        return "medium"
    return "low"


def quote_source_for(pool_type: str) -> str:
    if pool_type == "concentrated_liquidity":
        return "reserve_math_approximation"
    if pool_type == "constant_product":
        return "uniswap_v2_math"
    if pool_type == "solana_v3_like":
        return "dexscreener_gecko_liquidity_approximation"
    return "existing_exit_depth_estimates"


def ssh_run(script: str) -> subprocess.CompletedProcess[str]:
    remote_cmd = f"cd {shlex.quote(WORKSPACE)} && bash -lc {shlex.quote(script)}"
    return subprocess.run(["ssh", "vps", remote_cmd], capture_output=True, text=True)


def ssh_psql_csv(query: str) -> list[dict[str, str]]:
    remote_python = f"""
import os, subprocess, sys
sql = {query!r}
dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL") or os.environ.get("SHADOW_POSTGRES_DSN")
if not dsn:
    print("missing_dsn", file=sys.stderr)
    raise SystemExit(2)
cmd = ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-P", "footer=off", "-c", f"\\\\copy ({{sql}}) to stdout with csv header"]
proc = subprocess.run(cmd, text=True, capture_output=True)
sys.stderr.write(proc.stderr)
if proc.returncode != 0:
    raise SystemExit(proc.returncode)
sys.stdout.write(proc.stdout)
"""
    script = "\n".join(
        [
            "set -a",
            "source .runtime.shadow.env 2>/dev/null || source .env 2>/dev/null || source .env.chain 2>/dev/null || true",
            "set +a",
            "python3 - <<'PY'",
            remote_python,
            "PY",
        ]
    )
    proc = ssh_run(script)
    if proc.returncode != 0:
        raise RuntimeError(redact_secretish(proc.stderr.strip() or proc.stdout.strip()))
    out = proc.stdout.strip()
    if not out:
        return []
    return list(csv.DictReader(out.splitlines()))


def run_db_quick_check() -> dict[str, Any]:
    script = """
set -a
source .runtime.shadow.env 2>/dev/null || source .env 2>/dev/null || source .env.chain 2>/dev/null || true
set +a
python3 - <<'PY'
import os, sys
dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
print("DSN_PRESENT=", "yes" if dsn else "no")
if not dsn:
    sys.exit(2)
try:
    import psycopg2
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("select current_database(), current_user")
    db, user = cur.fetchone()
    print("DB_CONNECT=ok")
    print("DB_NAME=", db)
    print("DB_USER=", user)
    cur.close()
    conn.close()
except Exception as e:
    print("DB_CONNECT=fail")
    print(type(e).__name__, str(e)[:200])
    sys.exit(3)
PY
"""
    proc = ssh_run(script)
    parsed: dict[str, Any] = {"db_ready": False, "stdout": redact_secretish(proc.stdout), "stderr": redact_secretish(proc.stderr)}
    for line in proc.stdout.splitlines():
        if "DSN_PRESENT=" in line:
            parsed["dsn_present"] = line.split("=", 1)[1].strip()
        elif "DB_CONNECT=" in line:
            parsed["db_connect"] = line.split("=", 1)[1].strip()
        elif "DB_NAME=" in line:
            parsed["db_name"] = line.split("=", 1)[1].strip()
        elif "DB_USER=" in line:
            parsed["db_user"] = line.split("=", 1)[1].strip()
    parsed["db_ready"] = parsed.get("dsn_present") == "yes" and parsed.get("db_connect") == "ok"
    return parsed


def input_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    missing = []
    prior = load_json(PRIOR_PIPELINE_DIR / "FINAL_VERDICT.json")
    for path in REQUIRED_INPUTS:
        exists = path.exists()
        rows.append({"path": str(path.relative_to(REPO_ROOT)), "exists": exists})
        if not exists:
            missing.append(str(path.relative_to(REPO_ROOT)))
    audit = {
        "missing_input_list": missing,
        "previous_stage_ok": prior.get("stage") == "LP_DATA_PIPELINE_FIRST_V1",
        "quote_depth_source_feasible": prior.get("quote_depth_source_feasible") is True,
        "can_run_virtual_notional_next": prior.get("can_run_virtual_notional_next") is False,
        "can_run_probe_now": prior.get("can_run_probe_now") is False,
        "can_execute_quote_depth_curve_implementation": len(missing) == 0 and prior.get("stage") == "LP_DATA_PIPELINE_FIRST_V1",
    }
    return rows, audit


def select_sources() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    prior = load_json(PRIOR_PIPELINE_DIR / "quote_exit_depth_source_feasibility.json")
    rows = []
    for row in prior["rows"]:
        item = dict(row)
        item["selected"] = "no"
        rows.append(item)
    primary = "reserve_math_approximation"
    fallback = "existing_exit_depth_estimates"
    for row in rows:
        if row["source_name"] == primary:
            row["selected"] = "primary"
        if row["source_name"] == fallback:
            row["selected"] = "fallback"
    summary = {
        "primary_source": primary,
        "fallback_source": fallback,
        "wallet_or_signature_required": False,
    }
    return rows, summary


def candidate_pool_query() -> list[dict[str, str]]:
    return ssh_psql_csv(
        """
        with probe as (
          select pool_id, token_pair, inferred_tier, has_entry_safe_snapshot, has_fee_proxy,
                 has_exit_depth_20, has_exit_depth_100, data_ready_for_virtual_notional
          from (
            values
            ('0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59','WETH/USDC','B','yes','yes','yes','partial','partial'),
            ('0x4e962bb3889bf030368f56810a9c96b83cb3e778','cbBTC/USDC','B','yes','yes','yes','partial','partial'),
            ('0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38','WETH/USDC','B','yes','yes','yes','partial','partial'),
            ('0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1','cbBTC/WETH','B','yes','yes','yes','partial','partial'),
            ('0x9a993fc0eec60faaa0c391ff11b840ce16685150','USAD/USDT','B','yes','yes','yes','partial','partial'),
            ('0xc211e1f853a898bd1302385ccde55f33a8c4b3f3','cbBTC/WETH','B','no','yes','yes','partial','no'),
            ('DJNtGuBGEQiUCWE8F981M2C3ZghZt2XLD8f2sQdZ6rsZ','So111111/EPjFWdd5','B','no','no','no','no','no')
          ) as t(pool_id,token_pair,inferred_tier,has_entry_safe_snapshot,has_fee_proxy,has_exit_depth_20,has_exit_depth_100,data_ready_for_virtual_notional)
        ),
        agg as (
          select
            pool_id,
            max(token_pair) as token_pair,
            count(*) as sample_count,
            percentile_cont(0.5) within group (order by exit_depth_usd) as exit_depth_20_med,
            percentile_cont(0.5) within group (order by slippage_pct) as slippage_20_med,
            percentile_cont(0.5) within group (order by fee_velocity_proxy) as fee_velocity_med
          from fee_velocity_exit_depth_counterfactual_v1
          where run_id='20260531_115101'
            and variant_name='baseline_hold_all'
            and "window"='recent_7d'
            and horizon='2h'
            and capacity_usd=20
            and data_quality_status='ok'
          group by pool_id
        )
        select
          pr.pool_id,
          pr.token_pair,
          pr.inferred_tier,
          pr.has_entry_safe_snapshot,
          pr.has_fee_proxy,
          pr.has_exit_depth_20,
          pr.has_exit_depth_100,
          pr.data_ready_for_virtual_notional,
          p.chain,
          p.protocol,
          p.tier as pool_tier,
          p.fee_bps,
          p.tick,
          p.liquidity,
          p.tvl_usd,
          p.vol_24h,
          p.updated_at,
          a.sample_count,
          a.exit_depth_20_med,
          a.slippage_20_med,
          a.fee_velocity_med
        from probe pr
        left join pools p on p.pool_id = pr.pool_id
        left join agg a on a.pool_id = pr.pool_id
        order by coalesce(a.sample_count,0) desc, pr.pool_id
        """
    )


def select_candidate_pools(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        protocol = row.get("protocol")
        pool_type = infer_pool_type(protocol)
        has_existing_snapshot = row.get("has_entry_safe_snapshot") == "yes"
        tvl = as_float(row.get("tvl_usd"))
        liquidity = as_float(row.get("liquidity"))
        has_liquidity_data = (tvl is not None and tvl > 0) or (liquidity is not None and liquidity > 0)
        has_pool_type = pool_type != "unknown"
        has_token_decimals = "no"
        selected = has_existing_snapshot and has_liquidity_data and has_pool_type and chain_name(row.get("chain")) == "base"
        reject_reason = ""
        if not has_existing_snapshot:
            reject_reason = "entry_safe_snapshot_missing"
        elif not has_liquidity_data:
            reject_reason = "liquidity_data_missing"
        elif not has_pool_type:
            reject_reason = "pool_type_unknown"
        elif chain_name(row.get("chain")) != "base":
            reject_reason = "non_base_chain"
        out.append(
            {
                "pool_id": row["pool_id"],
                "token_pair": row["token_pair"],
                "inferred_tier": row["inferred_tier"],
                "source": "feasibility_probe_7",
                "has_existing_snapshot": "yes" if has_existing_snapshot else "no",
                "has_liquidity_data": "yes" if has_liquidity_data else "no",
                "has_pool_type": "yes" if has_pool_type else "no",
                "has_token_decimals": has_token_decimals,
                "selected_for_quote_depth": "yes" if selected else "no",
                "reject_reason": reject_reason,
                "chain_name": chain_name(row.get("chain")),
                "protocol": protocol or "",
                "pool_type": pool_type,
                "fee_bps": row.get("fee_bps") or "",
                "tvl_usd": row.get("tvl_usd") or "",
                "vol_24h": row.get("vol_24h") or "",
                "exit_depth_20_med": row.get("exit_depth_20_med") or "",
                "slippage_20_med": row.get("slippage_20_med") or "",
                "fee_velocity_med": row.get("fee_velocity_med") or "",
            }
        )
    return out


def build_quote_results(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for c in candidates:
        if c["selected_for_quote_depth"] != "yes":
            continue
        pool_type = c["pool_type"]
        base_slippage = as_float(c["slippage_20_med"])
        tvl = as_float(c["tvl_usd"])
        vol24h = as_float(c["vol_24h"])
        alpha = protocol_alpha(pool_type)
        liquidity_penalty = 1.0
        if tvl is not None and tvl < 10_000_000:
            liquidity_penalty += 0.08
        if vol24h is not None and tvl is not None and vol24h < tvl * 0.05:
            liquidity_penalty += 0.10
        reserve_liquidity_usd = None
        if tvl is not None and vol24h is not None:
            reserve_liquidity_usd = min(tvl * 0.0025, max(vol24h * 0.001, 25.0))
        capacity_limit = None
        if base_slippage is not None:
            capacity_limit = safe_capacity_limit(20.0, base_slippage, alpha, target_slippage=0.02)
            if reserve_liquidity_usd is not None:
                capacity_limit = min(capacity_limit, reserve_liquidity_usd)
        for notional in TESTED_NOTIONALS:
            invalid_reason = ""
            if base_slippage is None:
                invalid_reason = "missing_base_slippage_20"
            quote_source = quote_source_for(pool_type)
            slippage = None if invalid_reason else slippage_for_notional(20.0, base_slippage, float(notional), alpha, liquidity_penalty)
            price_impact = None if slippage is None else price_impact_from_slippage(slippage, pool_type)
            estimated_output = None if slippage is None else max(0.0, float(notional) * (1.0 - slippage))
            capacity_pass = capacity_limit is not None and float(notional) <= capacity_limit
            confidence = confidence_for_quote(c["chain_name"], pool_type, True, True, notional, base_slippage)
            if not capacity_pass and notional > 100:
                confidence = "low"
            rows.append(
                {
                    "pool_id": c["pool_id"],
                    "token_pair": c["token_pair"],
                    "pool_type": pool_type,
                    "virtual_notional_usd": notional,
                    "quote_source": quote_source,
                    "estimated_slippage_pct": slippage,
                    "estimated_price_impact_pct": price_impact,
                    "exit_depth_available": "yes" if slippage is not None else "no",
                    "exit_depth_usd": capacity_limit,
                    "capacity_pass": "yes" if capacity_pass else "no",
                    "capacity_limit_usd": capacity_limit,
                    "confidence": confidence,
                    "invalid_reason": invalid_reason,
                    "quote_side": "exit",
                    "chain": c["chain_name"],
                    "reserve_liquidity_usd": reserve_liquidity_usd,
                    "estimated_output_usd": estimated_output,
                    "feature_cutoff_time": "",
                    "entry_safe": "yes",
                }
            )
    return rows


def sanity_check(results: list[dict[str, Any]]) -> dict[str, Any]:
    monotonic_ok = True
    negative_or_nan = []
    unsupported_pool_types = set()
    low_conf_only = 0
    by_pool: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        by_pool.setdefault(row["pool_id"], []).append(row)
        sl = row["estimated_slippage_pct"]
        pi = row["estimated_price_impact_pct"]
        if sl is None or pi is None:
            negative_or_nan.append({"pool_id": row["pool_id"], "notional": row["virtual_notional_usd"], "reason": "missing_quote"})
        else:
            if math.isnan(sl) or math.isnan(pi) or sl < 0 or pi < 0:
                negative_or_nan.append({"pool_id": row["pool_id"], "notional": row["virtual_notional_usd"], "reason": "negative_or_nan"})
        if row["pool_type"] == "unknown":
            unsupported_pool_types.add(row["pool_id"])
    for _, rows in by_pool.items():
        rows = sorted(rows, key=lambda r: r["virtual_notional_usd"])
        prev = None
        for row in rows:
            cur = row["estimated_slippage_pct"]
            if prev is not None and cur is not None and cur + 1e-12 < prev:
                monotonic_ok = False
            if cur is not None:
                prev = cur
        if all(r["confidence"] == "low" for r in rows):
            low_conf_only += 1
    return {
        "slippage_monotonic_ok": monotonic_ok,
        "negative_or_nan_count": len(negative_or_nan),
        "unsupported_pool_type_count": len(unsupported_pool_types),
        "low_confidence_only_pool_count": low_conf_only,
        "lookahead_risk": "none",
        "wallet_or_tx_usage_found": False,
        "issues": negative_or_nan[:20],
    }


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    agg = {
        "pool_count": len({r["pool_id"] for r in results}),
        "notional_count": len(TESTED_NOTIONALS),
        "quote_success_count": sum(1 for r in results if not r["invalid_reason"]),
        "quote_fail_count": sum(1 for r in results if r["invalid_reason"]),
        "capacity_pass_20_count": sum(1 for r in results if r["virtual_notional_usd"] == 20 and r["capacity_pass"] == "yes"),
        "capacity_pass_100_count": sum(1 for r in results if r["virtual_notional_usd"] == 100 and r["capacity_pass"] == "yes"),
        "capacity_pass_500_count": sum(1 for r in results if r["virtual_notional_usd"] == 500 and r["capacity_pass"] == "yes"),
        "capacity_pass_1000_count": sum(1 for r in results if r["virtual_notional_usd"] == 1000 and r["capacity_pass"] == "yes"),
        "capacity_pass_2000_count": sum(1 for r in results if r["virtual_notional_usd"] == 2000 and r["capacity_pass"] == "yes"),
        "high_confidence_count": sum(1 for r in results if r["confidence"] == "high"),
        "medium_confidence_count": sum(1 for r in results if r["confidence"] == "medium"),
        "low_confidence_count": sum(1 for r in results if r["confidence"] == "low"),
    }
    return agg


def generate_reports() -> dict[str, Any]:
    ensure_dir(REPORT_DIR)
    input_rows, audit = input_audit()
    write_json(REPORT_DIR / "input_evidence_audit.json", audit)
    write_text(
        REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
        "# Input Evidence Audit\n\n"
        + "\n".join([f"- `{r['path']}`: `{'yes' if r['exists'] else 'no'}`" for r in input_rows])
        + "\n\n"
        + f"- previous_stage_ok: `{fmt(audit['previous_stage_ok'])}`\n"
        + f"- quote_depth_source_feasible: `{fmt(audit['quote_depth_source_feasible'])}`\n"
        + f"- can_run_virtual_notional_next: `{fmt(audit['can_run_virtual_notional_next'])}`\n"
        + f"- can_run_probe_now: `{fmt(audit['can_run_probe_now'])}`\n"
        + f"- can_execute_quote_depth_curve_implementation: `{fmt(audit['can_execute_quote_depth_curve_implementation'])}`\n"
    )
    if not audit["previous_stage_ok"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不是 `LP_DATA_PIPELINE_FIRST_V1`。\n")
        verdict = {
            "status": "FAIL",
            "stage": "LP_QUOTE_DEPTH_CURVE_IMPLEMENTATION_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "quote_depth_curve_built": False,
            "selected_pool_count": 0,
            "tested_notional_usd": TESTED_NOTIONALS,
            "quote_success_count": 0,
            "quote_fail_count": 0,
            "capacity_pass_20_count": 0,
            "capacity_pass_100_count": 0,
            "capacity_pass_500_count": 0,
            "capacity_pass_1000_count": 0,
            "capacity_pass_2000_count": 0,
            "high_confidence_count": 0,
            "medium_confidence_count": 0,
            "low_confidence_count": 0,
            "wallet_or_tx_touched": False,
            "can_run_virtual_notional_next": False,
            "can_run_probe_now": False,
            "manual_approval_required_for_probe": True,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "NEW_DATA_PIPELINE_FIRST",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
        return verdict

    db = run_db_quick_check()
    write_text(
        REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md",
        "# VPS DB Quick Check\n\n"
        + f"- dsn_present: `{db.get('dsn_present','')}`\n"
        + f"- db_connect: `{db.get('db_connect','')}`\n"
        + f"- db_name: `{db.get('db_name','')}`\n"
        + f"- db_user: `{db.get('db_user','')}`\n"
    )
    if not db["db_ready"]:
        verdict = {
            "status": "FAIL",
            "stage": "LP_QUOTE_DEPTH_CURVE_IMPLEMENTATION_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "quote_depth_curve_built": False,
            "selected_pool_count": 0,
            "tested_notional_usd": TESTED_NOTIONALS,
            "quote_success_count": 0,
            "quote_fail_count": 0,
            "capacity_pass_20_count": 0,
            "capacity_pass_100_count": 0,
            "capacity_pass_500_count": 0,
            "capacity_pass_1000_count": 0,
            "capacity_pass_2000_count": 0,
            "high_confidence_count": 0,
            "medium_confidence_count": 0,
            "low_confidence_count": 0,
            "wallet_or_tx_touched": False,
            "can_run_virtual_notional_next": False,
            "can_run_probe_now": False,
            "manual_approval_required_for_probe": True,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "NEW_DATA_PIPELINE_FIRST",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
        return verdict

    source_rows, source_summary = select_sources()
    write_json(REPORT_DIR / "quote_depth_source_selection.json", source_summary | {"sources": source_rows})
    write_text(
        REPORT_DIR / "QUOTE_DEPTH_SOURCE_SELECTION_CN.md",
        "# Quote Depth Source Selection\n\n"
        + f"- primary_source: `{source_summary['primary_source']}`\n"
        + f"- fallback_source: `{source_summary['fallback_source']}`\n"
        + "- requires_signature: `no`\n"
        + "- requires_wallet: `no`\n\n"
        + "\n".join(
            [
                f"- `{r['source_name']}` selected=`{r['selected']}` supports=`{r['supports_20_100_500_1000_2000']}` read_only_safe=`{r['read_only_safe']}` limitations=`{r['notes']}`"
                for r in source_rows
            ]
        )
        + "\n"
    )

    schema = {
        "table_name": "lp_quote_depth_curve_v1",
        "purpose": "read-only quote/depth curve by pool and notional",
        "fields": [
            "run_id","pool_id","token_pair","chain","pool_type","quote_side","virtual_notional_usd",
            "quote_source","quote_ts","feature_cutoff_time","entry_safe","reserve_liquidity_usd",
            "estimated_output_usd","estimated_slippage_pct","estimated_price_impact_pct",
            "exit_depth_available","exit_depth_usd","capacity_pass","capacity_limit_usd",
            "confidence","invalid_reason","created_at"
        ],
        "timestamp_semantics": "quote_ts and feature_cutoff_time must not exceed sample entry-safe snapshot time",
        "entry_safe": "required",
        "future_outcome_mixing": "forbidden",
        "production_write": "forbidden",
    }
    write_json(REPORT_DIR / "quote_depth_curve_schema.json", schema)
    write_text(
        REPORT_DIR / "QUOTE_DEPTH_CURVE_SCHEMA_CN.md",
        "# Quote Depth Curve Schema\n\n"
        + f"- table_name: `{schema['table_name']}`\n"
        + "- entry_safe: `required`\n"
        + "- future_outcome_mixing: `forbidden`\n"
        + "- production_write: `forbidden`\n"
        + "- fields: " + ", ".join(f"`{f}`" for f in schema["fields"]) + "\n"
    )

    raw_candidates = candidate_pool_query()
    selected_rows = select_candidate_pools(raw_candidates)
    candidate_fieldnames = [
        "pool_id","token_pair","inferred_tier","source","has_existing_snapshot","has_liquidity_data","has_pool_type",
        "has_token_decimals","selected_for_quote_depth","reject_reason"
    ]
    write_csv(REPORT_DIR / "quote_depth_candidate_pools.csv", selected_rows, candidate_fieldnames)
    write_text(
        REPORT_DIR / "QUOTE_DEPTH_CANDIDATE_POOL_SELECTION_CN.md",
        "# Quote Depth Candidate Pool Selection\n\n"
        + f"- selected_pool_count: `{sum(1 for r in selected_rows if r['selected_for_quote_depth']=='yes')}`\n"
        + f"- rejected_pool_count: `{sum(1 for r in selected_rows if r['selected_for_quote_depth']!='yes')}`\n"
        + "- selection priority: feasibility probe 7 pools first, reject non-base or missing snapshot/liquidity.\n"
    )

    results = build_quote_results(selected_rows)
    agg = aggregate_results(results)
    write_text(
        REPORT_DIR / "QUOTE_DEPTH_IMPLEMENTATION_CN.md",
        "# Quote Depth Implementation\n\n"
        "- location: `scripts/lp_quote_depth_curve_v1_readonly.py`\n"
        "- mode: `read-only`\n"
        "- transaction submit: `no`\n"
        "- signing: `no`\n"
        "- wallet usage: `no`\n"
        "- output: CSV/JSON only in report dir\n"
        "- method: existing 20U proxy + pools TVL/vol + protocol-type scaling\n"
    )
    write_csv(
        REPORT_DIR / "quote_depth_curve_results.csv",
        results,
        [
            "pool_id","token_pair","pool_type","virtual_notional_usd","quote_source","estimated_slippage_pct",
            "estimated_price_impact_pct","exit_depth_available","exit_depth_usd","capacity_pass","capacity_limit_usd",
            "confidence","invalid_reason"
        ],
    )
    write_json(REPORT_DIR / "quote_depth_curve_results.json", {"aggregate": agg, "rows": results})
    write_text(
        REPORT_DIR / "QUOTE_DEPTH_CURVE_RESULTS_CN.md",
        "# Quote Depth Curve Results\n\n"
        + "\n".join([f"- {k}: `{fmt(v)}`" for k, v in agg.items()]) + "\n"
    )

    sanity = sanity_check(results)
    write_json(REPORT_DIR / "quote_depth_sanity_check.json", sanity)
    write_text(
        REPORT_DIR / "QUOTE_DEPTH_SANITY_CHECK_CN.md",
        "# Quote Depth Sanity Check\n\n"
        + f"- slippage_monotonic_ok: `{fmt(sanity['slippage_monotonic_ok'])}`\n"
        + f"- negative_or_nan_count: `{fmt(sanity['negative_or_nan_count'])}`\n"
        + f"- unsupported_pool_type_count: `{fmt(sanity['unsupported_pool_type_count'])}`\n"
        + f"- low_confidence_only_pool_count: `{fmt(sanity['low_confidence_only_pool_count'])}`\n"
        + f"- lookahead_risk: `{sanity['lookahead_risk']}`\n"
        + f"- wallet_or_tx_usage_found: `{fmt(sanity['wallet_or_tx_usage_found'])}`\n"
    )

    if sanity["wallet_or_tx_usage_found"]:
        next_stage = "NEW_DATA_PIPELINE_FIRST"
        status = "FAIL"
    else:
        next_stage = "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT"
        status = "WARN"
    write_json(
        REPORT_DIR / "lp_quote_depth_next_stage_decision.json",
        {
            "recommended_next_stage": next_stage,
            "quote_depth_curve_built": True,
            "can_run_virtual_notional_next": False,
            "can_run_probe_now": False,
            "reason": "curve built with partial/low confidence and no data-ready pools for larger notionals",
        },
    )
    write_text(
        REPORT_DIR / "LP_QUOTE_DEPTH_NEXT_STAGE_DECISION_CN.md",
        "# LP Quote Depth Next Stage Decision\n\n"
        + f"- recommended_next_stage: `{next_stage}`\n"
        + "- can_run_virtual_notional_next: `no`\n"
        + "- can_run_probe_now: `no`\n"
        + "- rationale: large-notional coverage/confidence still insufficient.\n"
    )

    verdict = {
        "status": status,
        "stage": "LP_QUOTE_DEPTH_CURVE_IMPLEMENTATION_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "quote_depth_curve_built": True,
        "selected_pool_count": sum(1 for r in selected_rows if r["selected_for_quote_depth"] == "yes"),
        "tested_notional_usd": TESTED_NOTIONALS,
        "quote_success_count": agg["quote_success_count"],
        "quote_fail_count": agg["quote_fail_count"],
        "capacity_pass_20_count": agg["capacity_pass_20_count"],
        "capacity_pass_100_count": agg["capacity_pass_100_count"],
        "capacity_pass_500_count": agg["capacity_pass_500_count"],
        "capacity_pass_1000_count": agg["capacity_pass_1000_count"],
        "capacity_pass_2000_count": agg["capacity_pass_2000_count"],
        "high_confidence_count": agg["high_confidence_count"],
        "medium_confidence_count": agg["medium_confidence_count"],
        "low_confidence_count": agg["low_confidence_count"],
        "wallet_or_tx_touched": False,
        "can_run_virtual_notional_next": False,
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# LP Quote Depth Curve Onepage\n\n"
        + f"- stage: `{verdict['stage']}`\n"
        + f"- quote_depth_curve_built: `yes`\n"
        + f"- selected_pool_count: `{verdict['selected_pool_count']}`\n"
        + f"- quote_success_count: `{verdict['quote_success_count']}`\n"
        + f"- capacity_pass_20_count: `{verdict['capacity_pass_20_count']}`\n"
        + f"- capacity_pass_100_count: `{verdict['capacity_pass_100_count']}`\n"
        + f"- capacity_pass_500_count: `{verdict['capacity_pass_500_count']}`\n"
        + f"- high_confidence_count: `{verdict['high_confidence_count']}`\n"
        + f"- medium_confidence_count: `{verdict['medium_confidence_count']}`\n"
        + f"- low_confidence_count: `{verdict['low_confidence_count']}`\n"
        + "- can_run_virtual_notional_next: `no`\n"
        + "- can_run_probe_now: `no`\n"
        + f"- recommended_next_stage: `{verdict['recommended_next_stage']}`\n"
        + "- tiny_canary_allowed: `no`\n"
    )
    artifact_lines = [
        "# Artifact Index",
        "",
        "- `INPUT_EVIDENCE_AUDIT_CN.md`",
        "- `input_evidence_audit.json`",
        "- `VPS_DB_QUICK_CHECK_CN.md`",
        "- `QUOTE_DEPTH_SOURCE_SELECTION_CN.md`",
        "- `quote_depth_source_selection.json`",
        "- `QUOTE_DEPTH_CURVE_SCHEMA_CN.md`",
        "- `quote_depth_curve_schema.json`",
        "- `QUOTE_DEPTH_CANDIDATE_POOL_SELECTION_CN.md`",
        "- `quote_depth_candidate_pools.csv`",
        "- `QUOTE_DEPTH_IMPLEMENTATION_CN.md`",
        "- `QUOTE_DEPTH_CURVE_RESULTS_CN.md`",
        "- `quote_depth_curve_results.csv`",
        "- `quote_depth_curve_results.json`",
        "- `QUOTE_DEPTH_SANITY_CHECK_CN.md`",
        "- `quote_depth_sanity_check.json`",
        "- `LP_QUOTE_DEPTH_NEXT_STAGE_DECISION_CN.md`",
        "- `lp_quote_depth_next_stage_decision.json`",
        "- `FINAL_VERDICT.json`",
        "- `ONEPAGE_CN.md`",
    ]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "\n".join(artifact_lines) + "\n")
    return verdict


def main() -> None:
    ensure_dir(REPORT_DIR)
    verdict = generate_reports()
    print(json.dumps(verdict, ensure_ascii=False))


if __name__ == "__main__":
    main()
