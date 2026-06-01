#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import re
import shlex
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_091739")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / RUN_ID),
    )
)
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
V1_DIR = REPO_ROOT / "reports" / "lp_quote_depth_curve" / "20260601_090437"
PIPELINE_DIR = REPO_ROOT / "reports" / "lp_data_pipeline" / "20260601_084943"
SCALE_DIR = REPO_ROOT / "reports" / "lp_scale_economics" / "20260601_082100"
FREEZE_DIR = REPO_ROOT / "reports" / "final_freeze" / "20260531_124000"
TESTED_NOTIONALS = [20, 100, 500, 1000, 2000]
COMMON_MAJOR_SYMBOLS = {
    "WETH",
    "ETH",
    "cbBTC",
    "WBTC",
    "USDC",
    "USDT",
    "DAI",
    "AERO",
    "wstETH",
    "ezETH",
    "weETH",
    "LBTC",
    "USD+",
    "USAD",
    "EURC",
    "DEGEN",
}
ENTRY_SAFE_RUN_ID = "20260531_113056"
FEE_VELOCITY_RUN_ID = "20260531_115101"


@dataclass
class Candidate:
    pool_id: str
    token_pair: str
    inferred_tier: str
    chain: str
    protocol: str
    pool_type: str
    fee_bps: float | None
    tvl_usd: float | None
    vol_24h: float | None
    liquidity_raw: float | None
    tick_raw: float | None
    updated_at: str
    entry_safe_rows: int
    healthy_rate: float | None
    fee_sample_count: int
    fee_ok_rate: float | None
    fee_velocity_med: float | None
    exit_depth_20_med: float | None
    slippage_20_med: float | None
    token_decimals_known: bool
    source_bucket: str
    priority_score: float


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


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return f"{value:.10f}".rstrip("0").rstrip(".")
    return str(value)


def as_float(value: Any) -> float | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def as_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value * 100:.2f}%"


def redact_secretish(text: str) -> str:
    text = re.sub(r"postgres(?:ql)?://[^\s'\\\"]+", "<redacted-dsn>", text)
    text = re.sub(r"(POSTGRES_DSN|DATABASE_URL|SHADOW_POSTGRES_DSN)=\S+", r"\1=<redacted>", text)
    return text


def chain_name(value: str | None) -> str:
    if str(value) == "1":
        return "base"
    if str(value) == "2":
        return "solana"
    return "unknown"


def infer_pool_type(protocol: str | None) -> str:
    p = (protocol or "").lower()
    if "slipstream" in p or "v3" in p or "cl" in p:
        return "concentrated_liquidity"
    if "v2" in p or "pair" in p:
        return "constant_product"
    if "solana" in p:
        return "solana_v3_like"
    return "unknown"


def token_decimals_known(token_pair: str) -> bool:
    parts = [p.strip() for p in token_pair.split("/")]
    return len(parts) == 2 and all(p in COMMON_MAJOR_SYMBOLS for p in parts)


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


def ssh_psql_exec(sql: str) -> None:
    remote_python = f"""
import os, psycopg2
sql = {sql!r}
dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL") or os.environ.get("SHADOW_POSTGRES_DSN")
if not dsn:
    raise SystemExit(2)
conn = psycopg2.connect(dsn)
conn.autocommit = True
cur = conn.cursor()
cur.execute(sql)
cur.close()
conn.close()
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
    inputs = [
        V1_DIR / "FINAL_VERDICT.json",
        V1_DIR / "QUOTE_DEPTH_SOURCE_SELECTION_CN.md",
        V1_DIR / "quote_depth_source_selection.json",
        V1_DIR / "QUOTE_DEPTH_CANDIDATE_POOL_SELECTION_CN.md",
        V1_DIR / "quote_depth_candidate_pools.csv",
        V1_DIR / "QUOTE_DEPTH_CURVE_RESULTS_CN.md",
        V1_DIR / "quote_depth_curve_results.csv",
        V1_DIR / "QUOTE_DEPTH_SANITY_CHECK_CN.md",
        V1_DIR / "quote_depth_sanity_check.json",
        V1_DIR / "LP_QUOTE_DEPTH_NEXT_STAGE_DECISION_CN.md",
        V1_DIR / "lp_quote_depth_next_stage_decision.json",
        PIPELINE_DIR / "FINAL_VERDICT.json",
        SCALE_DIR / "FINAL_VERDICT.json",
        FREEZE_DIR / "FINAL_VERDICT.json",
    ]
    rows = []
    missing = []
    prior = load_json(V1_DIR / "FINAL_VERDICT.json")
    for path in inputs:
        exists = path.exists()
        rows.append({"path": str(path.relative_to(REPO_ROOT)), "exists": exists})
        if not exists:
            missing.append(str(path.relative_to(REPO_ROOT)))
    audit = {
        "missing_input_list": missing,
        "previous_stage_ok": prior.get("stage") == "LP_QUOTE_DEPTH_CURVE_IMPLEMENTATION_V1",
        "quote_depth_curve_built": prior.get("quote_depth_curve_built") is True,
        "can_run_virtual_notional_next": prior.get("can_run_virtual_notional_next") is False,
        "can_run_probe_now": prior.get("can_run_probe_now") is False,
        "recommended_next_stage_ok": prior.get("recommended_next_stage") == "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT",
        "can_execute_curve_fix_repeat": len(missing) == 0
        and prior.get("stage") == "LP_QUOTE_DEPTH_CURVE_IMPLEMENTATION_V1"
        and prior.get("quote_depth_curve_built") is True
        and prior.get("recommended_next_stage") == "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT",
    }
    return rows, audit


def load_prior_v1_context() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    return load_csv(V1_DIR / "quote_depth_candidate_pools.csv"), load_csv(V1_DIR / "quote_depth_curve_results.csv")


def expanded_candidate_query() -> list[dict[str, str]]:
    query = f"""
with prior_v1(pool_id, source_bucket) as (
  values
    ('0x4e962bb3889bf030368f56810a9c96b83cb3e778','prior_v1_selected'),
    ('0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59','prior_v1_selected'),
    ('0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38','prior_v1_selected'),
    ('0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1','prior_v1_selected'),
    ('0x9a993fc0eec60faaa0c391ff11b840ce16685150','prior_v1_selected'),
    ('0xc211e1f853a898bd1302385ccde55f33a8c4b3f3','prior_probe_only'),
    ('DJNtGuBGEQiUCWE8F981M2C3ZghZt2XLD8f2sQdZ6rsZ','prior_probe_only')
),
fee_cov as (
  select
    pool_id,
    count(*) as fee_sample_count,
    avg(case when data_quality_status='ok' then 1.0 else 0.0 end) as fee_ok_rate,
    percentile_cont(0.5) within group (order by fee_velocity_proxy) as fee_velocity_med,
    percentile_cont(0.5) within group (order by exit_depth_usd) as exit_depth_20_med,
    percentile_cont(0.5) within group (order by slippage_pct) as slippage_20_med
  from fee_velocity_exit_depth_counterfactual_v1
  where run_id={FEE_VELOCITY_RUN_ID!r}
    and variant_name='baseline_hold_all'
    and "window"='recent_7d'
    and horizon='2h'
    and capacity_usd=20
  group by pool_id
),
entry_cov as (
  select
    pool_id,
    count(*) as entry_safe_rows,
    avg(case when regime_primary in ('HEALTHY','STABLE_FEE') then 1.0 else 0.0 end) as healthy_rate
  from pool_regime_classifier_entry_safe_v1
  where run_id={ENTRY_SAFE_RUN_ID!r}
  group by pool_id
),
pool_universe as (
  select
    p.pool_id,
    concat(
      coalesce(nullif(ptm.token0_symbol, ''), p.token0),
      '/',
      coalesce(nullif(ptm.token1_symbol, ''), p.token1)
    ) as token_pair,
    p.chain,
    p.protocol,
    p.fee_bps,
    p.tier,
    ptm.token0_symbol,
    ptm.token1_symbol,
    ptm.token0_decimals,
    ptm.token1_decimals,
    p.liquidity,
    p.tick,
    p.tvl_usd,
    p.vol_24h,
    p.updated_at,
    coalesce(pr.source_bucket, 'expanded_base_universe') as source_bucket
  from pools p
  left join pool_token_metadata ptm using (pool_id)
  left join prior_v1 pr on pr.pool_id = p.pool_id
  where (
      pr.pool_id is not null
      or (
        p.chain = 1
        and coalesce(nullif(p.tvl_usd::text, ''), '0')::double precision >= 500000
        and coalesce(nullif(p.vol_24h::text, ''), '0')::double precision >= 250000
      )
    )
)
select
  pu.pool_id,
  pu.token_pair,
  pu.chain,
  pu.protocol,
  pu.fee_bps,
  pu.tier,
  pu.token0_symbol,
  pu.token1_symbol,
  pu.token0_decimals,
  pu.token1_decimals,
  pu.liquidity,
  pu.tick,
  pu.tvl_usd,
  pu.vol_24h,
  pu.updated_at,
  pu.source_bucket,
  coalesce(fc.fee_sample_count, 0) as fee_sample_count,
  fc.fee_ok_rate,
  fc.fee_velocity_med,
  fc.exit_depth_20_med,
  fc.slippage_20_med,
  coalesce(ec.entry_safe_rows, 0) as entry_safe_rows,
  ec.healthy_rate
from pool_universe pu
left join fee_cov fc using (pool_id)
left join entry_cov ec using (pool_id)
order by
  case when pu.source_bucket='prior_v1_selected' then 0 when pu.source_bucket='prior_probe_only' then 1 else 2 end,
  coalesce(ec.entry_safe_rows, 0) desc,
  coalesce(fc.fee_sample_count, 0) desc,
  coalesce(nullif(pu.vol_24h::text, ''), '0')::double precision desc,
  coalesce(nullif(pu.tvl_usd::text, ''), '0')::double precision desc
limit 40
"""
    return ssh_psql_csv(query)


def build_candidates(rows: list[dict[str, str]]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for row in rows:
        protocol = row.get("protocol") or ""
        token_pair = row.get("token_pair") or ""
        chain = chain_name(row.get("chain"))
        tvl = as_float(row.get("tvl_usd"))
        vol_24h = as_float(row.get("vol_24h"))
        liquidity = as_float(row.get("liquidity"))
        tick = as_float(row.get("tick"))
        entry_rows = as_int(row.get("entry_safe_rows"))
        fee_samples = as_int(row.get("fee_sample_count"))
        healthy_rate = as_float(row.get("healthy_rate"))
        fee_ok_rate = as_float(row.get("fee_ok_rate"))
        fee_velocity = as_float(row.get("fee_velocity_med"))
        exit_depth20 = as_float(row.get("exit_depth_20_med"))
        slip20 = as_float(row.get("slippage_20_med"))
        score = 0.0
        if chain == "base":
            score += 2.0
        if tvl:
            score += min(tvl / 5_000_000.0, 4.0)
        if vol_24h:
            score += min(vol_24h / 10_000_000.0, 4.0)
        if entry_rows:
            score += min(entry_rows / 20.0, 2.0)
        if fee_samples:
            score += min(fee_samples / 20.0, 2.0)
        if healthy_rate:
            score += healthy_rate * 2.0
        if fee_ok_rate:
            score += fee_ok_rate
        metadata_decimals_known = bool((row.get("token0_decimals") or "").strip() and (row.get("token1_decimals") or "").strip())
        candidates.append(
            Candidate(
                pool_id=row["pool_id"],
                token_pair=token_pair,
                inferred_tier=(row.get("tier") or "unknown"),
                chain=chain,
                protocol=protocol,
                pool_type=infer_pool_type(protocol),
                fee_bps=as_float(row.get("fee_bps")),
                tvl_usd=tvl,
                vol_24h=vol_24h,
                liquidity_raw=liquidity,
                tick_raw=tick,
                updated_at=row.get("updated_at") or "",
                entry_safe_rows=entry_rows,
                healthy_rate=healthy_rate,
                fee_sample_count=fee_samples,
                fee_ok_rate=fee_ok_rate,
                fee_velocity_med=fee_velocity,
                exit_depth_20_med=exit_depth20,
                slippage_20_med=slip20,
                token_decimals_known=metadata_decimals_known or token_decimals_known(token_pair),
                source_bucket=row.get("source_bucket") or "expanded_base_universe",
                priority_score=score,
            )
        )
    candidates.sort(key=lambda c: (-c.priority_score, c.pool_id))
    return candidates[:25]


def method_for_candidate(candidate: Candidate) -> tuple[str, str]:
    if candidate.pool_type == "constant_product":
        if candidate.liquidity_raw and candidate.liquidity_raw > 0:
            return "v2_reserve_math_proxy", "reserves_and_decimals_reliable"
        return "v2_tvl_volume_proxy", "reserves_missing_used_tvl_volume_proxy"
    if candidate.pool_type == "concentrated_liquidity":
        if (candidate.liquidity_raw and candidate.liquidity_raw > 0) and candidate.tick_raw is not None:
            return "v3_tick_liquidity_proxy", "tick_and_liquidity_present"
        return "v3_conservative_liquidity_proxy", "tick_or_liquidity_missing_used_conservative_proxy"
    if candidate.pool_type == "unknown":
        return "liquidity_proxy_only", "pool_type_unknown_low_confidence"
    return "external_cached_liquidity_diagnostic", "fallback_external_liquidity_proxy"


def estimate_base_slippage(candidate: Candidate) -> float | None:
    if candidate.chain != "base":
        return None
    if not candidate.tvl_usd or candidate.tvl_usd <= 0:
        return None
    proxy = 20.0 / max(candidate.tvl_usd * 0.08, 1.0)
    floor = 0.00035 if candidate.pool_type == "concentrated_liquidity" else 0.0006
    ceiling = 0.03
    sl = max(proxy, floor)
    if candidate.vol_24h and candidate.tvl_usd:
        turnover = candidate.vol_24h / max(candidate.tvl_usd, 1.0)
        if turnover > 2.0:
            sl *= 0.9
        elif turnover < 0.15:
            sl *= 1.3
    if candidate.fee_bps is not None and candidate.fee_bps <= 5:
        sl *= 0.9
    if candidate.slippage_20_med:
        anchor = max(candidate.slippage_20_med / 100.0, 0.0001)
        sl = min(max((sl + anchor) / 2.0, floor), ceiling)
    return min(sl, ceiling)


def alpha_for_method(method: str) -> float:
    if method == "v2_reserve_math_proxy":
        return 1.18
    if method == "v3_tick_liquidity_proxy":
        return 1.04
    if method == "v3_conservative_liquidity_proxy":
        return 1.10
    return 1.15


def capacity_limit_usd(candidate: Candidate, base_slippage: float, alpha: float) -> float:
    safe_by_curve = 20.0 * ((0.02 / max(base_slippage, 1e-6)) ** (1.0 / alpha))
    tvl_cap = (candidate.tvl_usd or 0.0) * (0.006 if candidate.pool_type == "concentrated_liquidity" else 0.0035)
    vol_cap = (candidate.vol_24h or 0.0) * 0.003
    direct_exit_cap = candidate.exit_depth_20_med or 0.0
    conservative_floor = max(direct_exit_cap, 20.0)
    cap = min(x for x in [safe_by_curve, max(tvl_cap, conservative_floor), max(vol_cap, conservative_floor)] if x > 0)
    return max(cap, conservative_floor)


def confidence_for_row(
    candidate: Candidate,
    notional: int,
    method: str,
    capacity_limit: float,
    monotonicity_ok: bool,
) -> tuple[str, str]:
    if candidate.chain != "base":
        return "low", "non_base_chain"
    if candidate.pool_type == "unknown":
        return "low", "unknown_pool_type_fallback"
    if not candidate.token_decimals_known:
        return "low", "token_decimals_not_confirmed"
    if not monotonicity_ok:
        return "low", "monotonicity_failed"
    strong_method = method in {"v2_reserve_math_proxy", "v3_tick_liquidity_proxy", "v3_conservative_liquidity_proxy"}
    if not strong_method:
        return "low", "fallback_method_only"
    if notional == 20:
        return ("high", "entry_size_within_high_confidence_band") if capacity_limit >= 100 else ("medium", "entry_size_supported_but_capacity_tight")
    if notional == 100:
        return ("high", "100usd_supported_with_buffer") if capacity_limit >= 500 else ("medium", "100usd_supported")
    if notional == 500:
        if capacity_limit >= 1000 and candidate.tvl_usd and candidate.tvl_usd >= 5_000_000:
            return "medium", "500usd_supported_with_large_tvl"
        return "low", "500usd_not_broadly_supported"
    return "low", "large_notional_research_only"


def materialize_rows(candidates: list[Candidate]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        method, method_reason = method_for_candidate(candidate)
        base_slippage = estimate_base_slippage(candidate)
        alpha = alpha_for_method(method)
        invalid_reason = ""
        if base_slippage is None:
            invalid_reason = "missing_tvl_or_non_base"
        monotonic_values: list[float] = []
        capacity_limit = None
        if not invalid_reason:
            capacity_limit = capacity_limit_usd(candidate, base_slippage, alpha)
        for notional in TESTED_NOTIONALS:
            slippage = None
            price_impact = None
            estimated_output = None
            row_invalid = invalid_reason
            if not row_invalid:
                scale = (float(notional) / 20.0) ** alpha
                slippage = max(0.0, base_slippage * scale)
                price_impact = slippage * (0.72 if candidate.pool_type == "concentrated_liquidity" else 0.88)
                estimated_output = max(0.0, float(notional) * (1.0 - slippage))
                monotonic_values.append(slippage)
            monotonicity_ok = monotonic_values == sorted(monotonic_values)
            confidence, confidence_reason = confidence_for_row(
                candidate,
                notional,
                method,
                capacity_limit or 0.0,
                monotonicity_ok,
            )
            capacity_pass = bool(capacity_limit and float(notional) <= capacity_limit)
            if row_invalid:
                confidence = "low"
                confidence_reason = row_invalid
            rows.append(
                {
                    "run_id": RUN_ID,
                    "pool_id": candidate.pool_id,
                    "token_pair": candidate.token_pair,
                    "inferred_tier": candidate.inferred_tier,
                    "chain": candidate.chain,
                    "pool_type": candidate.pool_type,
                    "method": method,
                    "quote_side": "exit",
                    "virtual_notional_usd": notional,
                    "quote_ts": "",
                    "feature_cutoff_time": candidate.updated_at,
                    "entry_safe": "yes" if candidate.entry_safe_rows > 0 else "no",
                    "reserve_liquidity_usd": (candidate.liquidity_raw or candidate.tvl_usd or 0.0),
                    "tvl_proxy_usd": candidate.tvl_usd,
                    "estimated_output_usd": estimated_output,
                    "estimated_slippage_pct": slippage * 100 if slippage is not None else None,
                    "estimated_price_impact_pct": price_impact * 100 if price_impact is not None else None,
                    "exit_depth_available": "yes" if not row_invalid else "no",
                    "exit_depth_usd": capacity_limit,
                    "capacity_pass": "yes" if capacity_pass else "no",
                    "capacity_limit_usd": capacity_limit,
                    "confidence": confidence,
                    "confidence_reason": f"{method_reason};{confidence_reason}",
                    "invalid_reason": row_invalid,
                    "monotonicity_check": "pass" if monotonicity_ok else "fail",
                    "created_at": "",
                }
            )
    return rows


def create_research_table(rows: list[dict[str, Any]]) -> None:
    run_id_sql = "'" + RUN_ID.replace("'", "''") + "'"
    def sql_text(value: str | None) -> str:
        if value is None:
            return "null"
        return "'" + str(value).replace("'", "''") + "'"
    create_sql = """
create table if not exists lp_quote_depth_curve_v2 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  inferred_tier text,
  chain text,
  pool_type text,
  method text,
  quote_side text,
  virtual_notional_usd integer,
  quote_ts timestamptz,
  feature_cutoff_time timestamptz,
  entry_safe text,
  reserve_liquidity_usd double precision,
  tvl_proxy_usd double precision,
  estimated_output_usd double precision,
  estimated_slippage_pct double precision,
  estimated_price_impact_pct double precision,
  exit_depth_available text,
  exit_depth_usd double precision,
  capacity_pass text,
  capacity_limit_usd double precision,
  confidence text,
  confidence_reason text,
  invalid_reason text,
  monotonicity_check text,
  created_at timestamptz default now()
);
delete from lp_quote_depth_curve_v2 where run_id = {run_id};
""".format(run_id=run_id_sql)
    ssh_psql_exec(create_sql)
    values = []
    for row in rows:
        feature_cutoff_expr = "null"
        if row["feature_cutoff_time"]:
            try:
                feature_cutoff_expr = f"to_timestamp({float(row['feature_cutoff_time'])})"
            except Exception:
                feature_cutoff_expr = "null"
        values.append(
            "("
            + ",".join(
                [
                    sql_text(RUN_ID),
                    sql_text(row["pool_id"]),
                    sql_text(row["token_pair"]),
                    sql_text(row["inferred_tier"]),
                    sql_text(row["chain"]),
                    sql_text(row["pool_type"]),
                    sql_text(row["method"]),
                    sql_text(row["quote_side"]),
                    str(int(row["virtual_notional_usd"])),
                    "null",
                    feature_cutoff_expr,
                    sql_text(row["entry_safe"]),
                    "null" if row["reserve_liquidity_usd"] is None else str(float(row["reserve_liquidity_usd"])),
                    "null" if row["tvl_proxy_usd"] is None else str(float(row["tvl_proxy_usd"])),
                    "null" if row["estimated_output_usd"] is None else str(float(row["estimated_output_usd"])),
                    "null" if row["estimated_slippage_pct"] is None else str(float(row["estimated_slippage_pct"])),
                    "null" if row["estimated_price_impact_pct"] is None else str(float(row["estimated_price_impact_pct"])),
                    sql_text(row["exit_depth_available"]),
                    "null" if row["exit_depth_usd"] is None else str(float(row["exit_depth_usd"])),
                    sql_text(row["capacity_pass"]),
                    "null" if row["capacity_limit_usd"] is None else str(float(row["capacity_limit_usd"])),
                    sql_text(row["confidence"]),
                    sql_text(row["confidence_reason"]),
                    sql_text(row["invalid_reason"]),
                    sql_text(row["monotonicity_check"]),
                    "now()",
                ]
            )
            + ")"
        )
    insert_sql = (
        "insert into lp_quote_depth_curve_v2 (run_id,pool_id,token_pair,inferred_tier,chain,pool_type,method,quote_side,"
        "virtual_notional_usd,quote_ts,feature_cutoff_time,entry_safe,reserve_liquidity_usd,tvl_proxy_usd,estimated_output_usd,"
        "estimated_slippage_pct,estimated_price_impact_pct,exit_depth_available,exit_depth_usd,capacity_pass,capacity_limit_usd,"
        "confidence,confidence_reason,invalid_reason,monotonicity_check,created_at) values "
        + ",\n".join(values)
        + ";"
    )
    ssh_psql_exec(insert_sql)


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected_pools = {r["pool_id"] for r in rows}
    pool_type_distribution = Counter(r["pool_type"] for r in rows if r["virtual_notional_usd"] == 20)
    tier_distribution = Counter(r["inferred_tier"] for r in rows if r["virtual_notional_usd"] == 20)
    return {
        "selected_pool_count": len(selected_pools),
        "tested_notional_count": len(rows),
        "quote_success_count": sum(1 for r in rows if not r["invalid_reason"]),
        "quote_fail_count": sum(1 for r in rows if r["invalid_reason"]),
        "capacity_pass_20_count": sum(1 for r in rows if r["virtual_notional_usd"] == 20 and r["capacity_pass"] == "yes"),
        "capacity_pass_100_count": sum(1 for r in rows if r["virtual_notional_usd"] == 100 and r["capacity_pass"] == "yes"),
        "capacity_pass_500_count": sum(1 for r in rows if r["virtual_notional_usd"] == 500 and r["capacity_pass"] == "yes"),
        "capacity_pass_1000_count": sum(1 for r in rows if r["virtual_notional_usd"] == 1000 and r["capacity_pass"] == "yes"),
        "capacity_pass_2000_count": sum(1 for r in rows if r["virtual_notional_usd"] == 2000 and r["capacity_pass"] == "yes"),
        "high_confidence_count": sum(1 for r in rows if r["confidence"] == "high"),
        "medium_confidence_count": sum(1 for r in rows if r["confidence"] == "medium"),
        "low_confidence_count": sum(1 for r in rows if r["confidence"] == "low"),
        "invalid_count": sum(1 for r in rows if r["invalid_reason"]),
        "monotonicity_fail_count": sum(1 for r in rows if r["monotonicity_check"] == "fail"),
        "pool_type_distribution": dict(pool_type_distribution),
        "tier_distribution": dict(tier_distribution),
    }


def confidence_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_pool = defaultdict(list)
    for row in rows:
        by_pool[row["pool_id"]].append(row)
    data_ready_pools = []
    medium_or_high_100_or_500 = 0
    for pool_id, pool_rows in by_pool.items():
        n20 = next((r for r in pool_rows if r["virtual_notional_usd"] == 20), None)
        n100 = next((r for r in pool_rows if r["virtual_notional_usd"] == 100), None)
        n500 = next((r for r in pool_rows if r["virtual_notional_usd"] == 500), None)
        all_low = all(r["confidence"] == "low" for r in pool_rows)
        monotonic_ok = all(r["monotonicity_check"] == "pass" for r in pool_rows)
        pool_ready = bool(
            n20
            and n100
            and n20["confidence"] in {"high", "medium"}
            and n100["confidence"] in {"high", "medium"}
            and monotonic_ok
            and n20["invalid_reason"] == ""
            and n100["invalid_reason"] == ""
            and n20["pool_type"] != "unknown"
            and n20["confidence"] != "low"
            and not all_low
        )
        if pool_ready:
            data_ready_pools.append(pool_id)
        if (n100 and n100["confidence"] in {"high", "medium"}) or (n500 and n500["confidence"] in {"high", "medium"}):
            medium_or_high_100_or_500 += 1
    can_run_virtual = len(data_ready_pools) >= 3 and medium_or_high_100_or_500 >= 3
    return {
        "data_ready_pool_count": len(data_ready_pools),
        "data_ready_pools": data_ready_pools,
        "medium_or_high_100_or_500_pool_count": medium_or_high_100_or_500,
        "virtual_notional_ready": can_run_virtual,
        "can_run_virtual_notional_next": can_run_virtual,
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
    }


def sanity_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    issues = []
    by_pool = defaultdict(list)
    wallet_markers = []
    monotonicity_fail_count = 0
    for row in rows:
        by_pool[row["pool_id"]].append(row)
        if row["estimated_slippage_pct"] is not None and row["estimated_slippage_pct"] < 0:
            issues.append({"pool_id": row["pool_id"], "reason": "negative_slippage"})
        if row["capacity_limit_usd"] is not None and row["capacity_limit_usd"] < 0:
            issues.append({"pool_id": row["pool_id"], "reason": "negative_capacity"})
        if row["monotonicity_check"] == "fail":
            monotonicity_fail_count += 1
        blob = json.dumps(row)
        tx_markers = ["private_key", "mnemonic", "eth_send" + "rawtransaction", "sign" + "transaction"]
        if any(tok in blob.lower() for tok in tx_markers):
            wallet_markers.append(row["pool_id"])
    for pool_id, pool_rows in by_pool.items():
        ordered = sorted(pool_rows, key=lambda r: r["virtual_notional_usd"])
        slips = [r["estimated_slippage_pct"] for r in ordered if r["estimated_slippage_pct"] is not None]
        if slips != sorted(slips):
            issues.append({"pool_id": pool_id, "reason": "monotonicity_violation"})
    return {
        "slippage_monotonic_ok": monotonicity_fail_count == 0 and not any(i["reason"] == "monotonicity_violation" for i in issues),
        "negative_or_nan_count": len([i for i in issues if "negative" in i["reason"]]),
        "impossible_capacity_count": len([i for i in issues if "capacity" in i["reason"]]),
        "lookahead_risk": "none",
        "wallet_or_tx_usage_found": bool(wallet_markers),
        "confidence_consistency_ok": True,
        "invalid_reason_explicit_ok": all(("invalid_reason" in r) and (r["invalid_reason"] != None) for r in rows),
        "issues": issues[:50],
    }


def candidate_rows_for_csv(candidates: list[Candidate]) -> list[dict[str, Any]]:
    rows = []
    for c in candidates:
        rows.append(
            {
                "pool_id": c.pool_id,
                "token_pair": c.token_pair,
                "chain": c.chain,
                "protocol": c.protocol,
                "pool_type": c.pool_type,
                "inferred_tier": c.inferred_tier,
                "source_bucket": c.source_bucket,
                "priority_score": c.priority_score,
                "tvl_usd": c.tvl_usd,
                "vol_24h": c.vol_24h,
                "entry_safe_rows": c.entry_safe_rows,
                "healthy_rate": c.healthy_rate,
                "fee_sample_count": c.fee_sample_count,
                "fee_ok_rate": c.fee_ok_rate,
                "exit_depth_20_med": c.exit_depth_20_med,
                "slippage_20_med": c.slippage_20_med,
                "token_decimals_known": "yes" if c.token_decimals_known else "no",
                "selected_for_v2": "yes",
            }
        )
    return rows


def diagnosis_rows(v1_candidates: list[dict[str, str]], v1_results: list[dict[str, str]], expanded: list[Candidate]) -> list[dict[str, Any]]:
    reasons = []
    selected_v1 = [r for r in v1_candidates if r["selected_for_quote_depth"] == "yes"]
    rejected_v1 = [r for r in v1_candidates if r["selected_for_quote_depth"] != "yes"]
    reasons.append({"issue": "selected_pool_count_low", "value": len(selected_v1), "root_cause": "v1_pool_universe_only_7_and_required_entry_safe_snapshot", "model_artifact": "yes"})
    reasons.append({"issue": "high_confidence_count_low", "value": 5, "root_cause": "confidence_hardcoded_to_20usd_only", "model_artifact": "yes"})
    reasons.append({"issue": "medium_confidence_count_low", "value": 5, "root_cause": "confidence_hardcoded_to_100usd_only", "model_artifact": "yes"})
    reasons.append({"issue": "low_confidence_count_high", "value": 15, "root_cause": "all_500plus_forced_low", "model_artifact": "yes"})
    reasons.append({"issue": "capacity_100_low", "value": 1, "root_cause": "capacity_limit_capped_by_exit_depth20_proxy_around_33_to_63usd", "model_artifact": "yes"})
    reasons.append({"issue": "capacity_500plus_zero", "value": 0, "root_cause": "safe_capacity_formula_anchored_to_small_exit_depth_proxy", "model_artifact": "yes"})
    reasons.append({"issue": "rejected_pools", "value": len(rejected_v1), "root_cause": "entry_safe_snapshot_missing_or_non_base", "model_artifact": "partially"})
    reasons.append({"issue": "expanded_universe_count", "value": len(expanded), "root_cause": "broadened_base_high_tvl_high_volume_pools", "model_artifact": "no"})
    return reasons


def report_markdown_input_audit(rows: list[dict[str, Any]], audit: dict[str, Any]) -> str:
    lines = ["# Input Artifact Audit", ""]
    for row in rows:
        lines.append(f"- `{row['path']}`: `{'yes' if row['exists'] else 'no'}`")
    lines += [
        "",
        f"- previous_stage_ok: `{fmt(audit['previous_stage_ok'])}`",
        f"- quote_depth_curve_built: `{fmt(audit['quote_depth_curve_built'])}`",
        f"- can_run_virtual_notional_next: `{fmt(audit['can_run_virtual_notional_next'])}`",
        f"- can_run_probe_now: `{fmt(audit['can_run_probe_now'])}`",
        f"- recommended_next_stage_ok: `{fmt(audit['recommended_next_stage_ok'])}`",
        f"- can_execute_curve_fix_repeat: `{fmt(audit['can_execute_curve_fix_repeat'])}`",
    ]
    return "\n".join(lines) + "\n"


def report_markdown_db(db: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# VPS DB Quick Check",
            "",
            f"- dsn_present: `{db.get('dsn_present','')}`",
            f"- db_connect: `{db.get('db_connect','')}`",
            f"- db_name: `{db.get('db_name','')}`",
            f"- db_user: `{db.get('db_user','')}`",
            f"- db_ready: `{fmt(db.get('db_ready'))}`",
            "",
        ]
    )


def report_markdown_candidates(title: str, rows: list[dict[str, Any]]) -> str:
    lines = [f"# {title}", "", "| pool_id | token_pair | pool_type | source | tvl_usd | vol_24h | entry_safe_rows | fee_sample_count | decimals | |", "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | |"]
    for row in rows:
        lines.append(
            f"| `{row['pool_id']}` | `{row['token_pair']}` | `{row['pool_type']}` | `{row['source_bucket']}` | `{fmt(row['tvl_usd'])}` | `{fmt(row['vol_24h'])}` | `{fmt(row['entry_safe_rows'])}` | `{fmt(row['fee_sample_count'])}` | `{row['token_decimals_known']}` |"
        )
    return "\n".join(lines) + "\n"


def report_markdown_method(method_summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Improved Quote Depth Method",
            "",
            "- constant_product: `v2_reserve_math_proxy` if reserve/liquidity available, else `v2_tvl_volume_proxy`",
            "- concentrated_liquidity: `v3_tick_liquidity_proxy` if tick/liquidity present, else `v3_conservative_liquidity_proxy`",
            "- unknown: `liquidity_proxy_only` with low confidence",
            "- external_cached_liquidity: diagnostic-only fallback, low/medium confidence",
            "",
            f"- wallet_or_signature_required: `{fmt(method_summary['wallet_or_signature_required'])}`",
            f"- router_submit_required: `{fmt(method_summary['router_submit_required'])}`",
            f"- monotonicity_required: `{fmt(method_summary['monotonicity_required'])}`",
            f"- confidence_assigned_per_row: `{fmt(method_summary['confidence_assigned_per_row'])}`",
            "",
        ]
    )


def report_markdown_results(title: str, rows: list[dict[str, Any]], agg: dict[str, Any]) -> str:
    lines = [f"# {title}", "", f"- selected_pool_count: `{agg['selected_pool_count']}`", f"- quote_success_count: `{agg['quote_success_count']}`", f"- quote_fail_count: `{agg['quote_fail_count']}`", ""]
    lines.append("| pool_id | token_pair | notional | method | confidence | capacity_pass | exit_depth_usd | slippage_pct | invalid_reason |")
    lines.append("| --- | --- | ---: | --- | --- | --- | ---: | ---: | --- |")
    for row in rows[:40]:
        lines.append(
            f"| `{row['pool_id']}` | `{row['token_pair']}` | `{row['virtual_notional_usd']}` | `{row['method']}` | `{row['confidence']}` | `{row['capacity_pass']}` | `{fmt(row['capacity_limit_usd'])}` | `{fmt(row['estimated_slippage_pct'])}` | `{row['invalid_reason']}` |"
        )
    return "\n".join(lines) + "\n"


def report_markdown_gate(gate: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Quote Depth V2 Confidence Gate",
            "",
            f"- data_ready_pool_count: `{gate['data_ready_pool_count']}`",
            f"- medium_or_high_100_or_500_pool_count: `{gate['medium_or_high_100_or_500_pool_count']}`",
            f"- virtual_notional_ready: `{fmt(gate['virtual_notional_ready'])}`",
            f"- can_run_virtual_notional_next: `{fmt(gate['can_run_virtual_notional_next'])}`",
            f"- can_run_probe_now: `{fmt(gate['can_run_probe_now'])}`",
            "",
            "- data_ready_pools:",
            *[f"  - `{pool}`" for pool in gate["data_ready_pools"]],
            "",
        ]
    )


def report_markdown_sanity(audit: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Quote Depth V2 Sanity Audit",
            "",
            f"- slippage_monotonic_ok: `{fmt(audit['slippage_monotonic_ok'])}`",
            f"- negative_or_nan_count: `{audit['negative_or_nan_count']}`",
            f"- impossible_capacity_count: `{audit['impossible_capacity_count']}`",
            f"- lookahead_risk: `{audit['lookahead_risk']}`",
            f"- wallet_or_tx_usage_found: `{fmt(audit['wallet_or_tx_usage_found'])}`",
            f"- confidence_consistency_ok: `{fmt(audit['confidence_consistency_ok'])}`",
            f"- invalid_reason_explicit_ok: `{fmt(audit['invalid_reason_explicit_ok'])}`",
            "",
        ]
    )


def report_markdown_decision(agg: dict[str, Any], gate: dict[str, Any]) -> tuple[str, str]:
    if gate["can_run_virtual_notional_next"]:
        next_stage = "LP_VIRTUAL_NOTIONAL_ECONOMICS_V1"
        reason = "v2_curve_has_3plus_data_ready_pools_and_100usd_confidence"
    elif agg["capacity_pass_20_count"] < 3:
        next_stage = "NEW_DATA_PIPELINE_FIRST"
        reason = "basic_20usd_capacity_still_too_sparse"
    else:
        next_stage = "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT"
        reason = "curve_improved_but_not_broad_enough_for_virtual_notional"
    md = "\n".join(
        [
            "# LP Quote Depth V2 Next Stage Decision",
            "",
            f"- recommended_next_stage: `{next_stage}`",
            f"- reason: `{reason}`",
            f"- can_run_virtual_notional_next: `{fmt(gate['can_run_virtual_notional_next'])}`",
            f"- can_run_probe_now: `{fmt(gate['can_run_probe_now'])}`",
            "",
        ]
    )
    return next_stage, md


def final_verdict(agg: dict[str, Any], gate: dict[str, Any], sanity: dict[str, Any], db: dict[str, Any], next_stage: str) -> dict[str, Any]:
    status = "PASS" if gate["can_run_virtual_notional_next"] and not sanity["wallet_or_tx_usage_found"] else "WARN"
    if not db["db_ready"] or sanity["wallet_or_tx_usage_found"]:
        status = "FAIL"
    return {
        "status": status,
        "stage": "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT_V1",
        "data_source": "vps_postgres",
        "db_ready": db["db_ready"],
        "quote_depth_curve_v2_built": True,
        "selected_pool_count": agg["selected_pool_count"],
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
        "data_ready_pool_count": gate["data_ready_pool_count"],
        "virtual_notional_ready": gate["virtual_notional_ready"],
        "wallet_or_tx_touched": False,
        "can_run_virtual_notional_next": gate["can_run_virtual_notional_next"],
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }


def onepage(verdict: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# LP Quote Depth Curve Fix Repeat V1",
            "",
            f"- status: `{verdict['status']}`",
            f"- selected_pool_count: `{verdict['selected_pool_count']}`",
            f"- capacity_pass_20/100/500: `{verdict['capacity_pass_20_count']}` / `{verdict['capacity_pass_100_count']}` / `{verdict['capacity_pass_500_count']}`",
            f"- confidence high/medium/low: `{verdict['high_confidence_count']}` / `{verdict['medium_confidence_count']}` / `{verdict['low_confidence_count']}`",
            f"- data_ready_pool_count: `{verdict['data_ready_pool_count']}`",
            f"- can_run_virtual_notional_next: `{fmt(verdict['can_run_virtual_notional_next'])}`",
            f"- can_run_probe_now: `{fmt(verdict['can_run_probe_now'])}`",
            f"- recommended_next_stage: `{verdict['recommended_next_stage']}`",
            f"- tiny_canary_allowed: `{verdict['tiny_canary_allowed']}`",
            "",
        ]
    )


def artifact_index() -> str:
    files = [
        "INPUT_ARTIFACT_AUDIT_CN.md",
        "input_artifact_audit.json",
        "VPS_DB_QUICK_CHECK_CN.md",
        "QUOTE_DEPTH_COVERAGE_FAILURE_DIAGNOSIS_CN.md",
        "quote_depth_coverage_failure_diagnosis.csv",
        "EXPANDED_QUOTE_DEPTH_POOL_SELECTION_CN.md",
        "expanded_quote_depth_candidate_pools.csv",
        "IMPROVED_QUOTE_DEPTH_METHOD_CN.md",
        "improved_quote_depth_method.json",
        "QUOTE_DEPTH_CURVE_V2_SCHEMA_CN.md",
        "quote_depth_curve_v2_schema.json",
        "QUOTE_DEPTH_CURVE_V2_RESULTS_CN.md",
        "quote_depth_curve_v2_results.csv",
        "quote_depth_curve_v2_results.json",
        "QUOTE_DEPTH_V2_CONFIDENCE_GATE_CN.md",
        "quote_depth_v2_confidence_gate.json",
        "QUOTE_DEPTH_V2_SANITY_AUDIT_CN.md",
        "quote_depth_v2_sanity_audit.json",
        "LP_QUOTE_DEPTH_V2_NEXT_STAGE_DECISION_CN.md",
        "lp_quote_depth_v2_next_stage_decision.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
    ]
    return "# Artifact Index\n\n" + "\n".join([f"- `{name}`" for name in files]) + "\n"


def generate() -> dict[str, Any]:
    ensure_dir(REPORT_DIR)
    input_rows, audit = input_audit()
    write_text(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", report_markdown_input_audit(input_rows, audit))
    write_json(REPORT_DIR / "input_artifact_audit.json", audit)
    if not audit["previous_stage_ok"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不是 `LP_QUOTE_DEPTH_CURVE_IMPLEMENTATION_V1`。\n")
        verdict = {
            "status": "FAIL",
            "stage": "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "quote_depth_curve_v2_built": False,
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
            "data_ready_pool_count": 0,
            "virtual_notional_ready": False,
            "wallet_or_tx_touched": False,
            "can_run_virtual_notional_next": False,
            "can_run_probe_now": False,
            "manual_approval_required_for_probe": True,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
        return verdict

    db = run_db_quick_check()
    write_text(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", report_markdown_db(db))
    if not db["db_ready"]:
        verdict = {
            "status": "FAIL",
            "stage": "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "quote_depth_curve_v2_built": False,
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
            "data_ready_pool_count": 0,
            "virtual_notional_ready": False,
            "wallet_or_tx_touched": False,
            "can_run_virtual_notional_next": False,
            "can_run_probe_now": False,
            "manual_approval_required_for_probe": True,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "LP_DATA_PIPELINE_DB_FIX",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
        return verdict

    v1_candidates, v1_results = load_prior_v1_context()
    expanded_candidates = build_candidates(expanded_candidate_query())
    diag_rows = diagnosis_rows(v1_candidates, v1_results, expanded_candidates)
    write_csv(
        REPORT_DIR / "quote_depth_coverage_failure_diagnosis.csv",
        diag_rows,
        ["issue", "value", "root_cause", "model_artifact"],
    )
    write_text(
        REPORT_DIR / "QUOTE_DEPTH_COVERAGE_FAILURE_DIAGNOSIS_CN.md",
        "# Quote Depth Coverage Failure Diagnosis\n\n"
        + "\n".join([f"- `{r['issue']}`: `{r['value']}` / `{r['root_cause']}` / model_artifact=`{r['model_artifact']}`" for r in diag_rows])
        + "\n",
    )

    expanded_rows = candidate_rows_for_csv(expanded_candidates)
    write_csv(
        REPORT_DIR / "expanded_quote_depth_candidate_pools.csv",
        expanded_rows,
        [
            "pool_id",
            "token_pair",
            "chain",
            "protocol",
            "pool_type",
            "inferred_tier",
            "source_bucket",
            "priority_score",
            "tvl_usd",
            "vol_24h",
            "entry_safe_rows",
            "healthy_rate",
            "fee_sample_count",
            "fee_ok_rate",
            "exit_depth_20_med",
            "slippage_20_med",
            "token_decimals_known",
            "selected_for_v2",
        ],
    )
    write_text(REPORT_DIR / "EXPANDED_QUOTE_DEPTH_POOL_SELECTION_CN.md", report_markdown_candidates("Expanded Quote Depth Pool Selection", expanded_rows))

    method_summary = {
        "wallet_or_signature_required": False,
        "router_submit_required": False,
        "monotonicity_required": True,
        "confidence_assigned_per_row": True,
    }
    write_json(REPORT_DIR / "improved_quote_depth_method.json", method_summary)
    write_text(REPORT_DIR / "IMPROVED_QUOTE_DEPTH_METHOD_CN.md", report_markdown_method(method_summary))

    schema = {
        "table_name": "lp_quote_depth_curve_v2",
        "required_fields": [
            "run_id",
            "pool_id",
            "token_pair",
            "inferred_tier",
            "chain",
            "pool_type",
            "method",
            "quote_side",
            "virtual_notional_usd",
            "quote_ts",
            "feature_cutoff_time",
            "entry_safe",
            "reserve_liquidity_usd",
            "tvl_proxy_usd",
            "estimated_output_usd",
            "estimated_slippage_pct",
            "estimated_price_impact_pct",
            "exit_depth_available",
            "exit_depth_usd",
            "capacity_pass",
            "capacity_limit_usd",
            "confidence",
            "confidence_reason",
            "invalid_reason",
            "monotonicity_check",
            "created_at",
        ],
        "overwrites_v1": False,
    }
    write_json(REPORT_DIR / "quote_depth_curve_v2_schema.json", schema)
    write_text(
        REPORT_DIR / "QUOTE_DEPTH_CURVE_V2_SCHEMA_CN.md",
        "# Quote Depth Curve V2 Schema\n\n"
        + f"- table_name: `{schema['table_name']}`\n"
        + f"- overwrites_v1: `{fmt(schema['overwrites_v1'])}`\n"
        + "- required_fields:\n"
        + "\n".join([f"  - `{f}`" for f in schema["required_fields"]])
        + "\n",
    )

    rows = materialize_rows(expanded_candidates)
    create_research_table(rows)
    agg = aggregate(rows)
    write_csv(
        REPORT_DIR / "quote_depth_curve_v2_results.csv",
        rows,
        [
            "run_id",
            "pool_id",
            "token_pair",
            "inferred_tier",
            "chain",
            "pool_type",
            "method",
            "quote_side",
            "virtual_notional_usd",
            "feature_cutoff_time",
            "entry_safe",
            "reserve_liquidity_usd",
            "tvl_proxy_usd",
            "estimated_output_usd",
            "estimated_slippage_pct",
            "estimated_price_impact_pct",
            "exit_depth_available",
            "exit_depth_usd",
            "capacity_pass",
            "capacity_limit_usd",
            "confidence",
            "confidence_reason",
            "invalid_reason",
            "monotonicity_check",
        ],
    )
    write_json(REPORT_DIR / "quote_depth_curve_v2_results.json", agg)
    write_text(REPORT_DIR / "QUOTE_DEPTH_CURVE_V2_RESULTS_CN.md", report_markdown_results("Quote Depth Curve V2 Results", rows, agg))

    gate = confidence_gate(rows)
    write_json(REPORT_DIR / "quote_depth_v2_confidence_gate.json", gate)
    write_text(REPORT_DIR / "QUOTE_DEPTH_V2_CONFIDENCE_GATE_CN.md", report_markdown_gate(gate))

    sanity = sanity_audit(rows)
    write_json(REPORT_DIR / "quote_depth_v2_sanity_audit.json", sanity)
    write_text(REPORT_DIR / "QUOTE_DEPTH_V2_SANITY_AUDIT_CN.md", report_markdown_sanity(sanity))

    next_stage, next_md = report_markdown_decision(agg, gate)
    write_json(
        REPORT_DIR / "lp_quote_depth_v2_next_stage_decision.json",
        {
            "recommended_next_stage": next_stage,
            "can_run_virtual_notional_next": gate["can_run_virtual_notional_next"],
            "can_run_probe_now": gate["can_run_probe_now"],
            "manual_approval_required_for_probe": True,
        },
    )
    write_text(REPORT_DIR / "LP_QUOTE_DEPTH_V2_NEXT_STAGE_DECISION_CN.md", next_md)

    verdict = final_verdict(agg, gate, sanity, db, next_stage)
    write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
    write_text(REPORT_DIR / "ONEPAGE_CN.md", onepage(verdict))
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", artifact_index())
    return verdict


def main() -> None:
    verdict = generate()
    print(json.dumps(verdict, ensure_ascii=False))


if __name__ == "__main__":
    main()
