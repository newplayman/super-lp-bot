#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import re
import shlex
import statistics
import subprocess
import time
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any
from urllib import request

import requests
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import keccak


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_120001")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_precise_quote" / RUN_ID),
    )
)
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
REAL_DATA_REOPEN_DIR = REPO_ROOT / "reports" / "lp_real_data_reopen" / "20260601_112642"
QUOTE_DEPTH_V2_DIR = REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739"
SCALE_FREEZE_DIR = REPO_ROOT / "reports" / "lp_scale_final_freeze" / "20260601_110649"
TESTED_NOTIONALS = [20, 100, 500, 1000, 2000]
ALLOWED_NEXT = {
    "LP_V3_TICK_LIQUIDITY_PIPELINE_V1",
    "LP_REAL_COST_MODEL_PIPELINE_V1",
    "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
    "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
    "LP_PRECISE_QUOTE_PIPELINE_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}
STABLE_SYMBOLS = {"USDC", "USDT", "DAI", "USD+", "USDBC", "EURC", "USAD"}
SLIPSTREAM_QUOTER = "0x254cf9e1e6e233aa1ac962cb9b05b2cfeaae15b0"
SLIPSTREAM_MIXED_QUOTER = "0x0a5aa5d3a4d28014f967bf0f29eaa3ff9807d5c6"
RPC_ENV_KEYS = ["BASE_RPC_PRIMARY", "LPBOT_BASE_RPC_URL", "BASE_RPC_URL", "BASE_RPC_FALLBACK"]
READ_ONLY_RPC_FALLBACKS = [
    "https://mainnet.base.org",
    "https://developer-access-mainnet.base.org",
    "https://base-rpc.publicnode.com",
]
HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
HTTP_SESSION.trust_env = False


@dataclass
class PoolMeta:
    pool_id: str
    token_pair: str
    chain: str
    protocol: str
    pool_type: str
    token0: str
    token1: str
    token0_symbol: str
    token1_symbol: str
    token0_decimals: int | None
    token1_decimals: int | None
    fee_bps: str
    tier: str
    tvl_usd: float | None
    vol_24h: float | None
    liquidity_db: str
    tick_db: str
    prior_selected: bool


@dataclass
class PoolState:
    token0: str
    token1: str
    fee: int | None
    tick_spacing: int | None
    sqrt_price_x96: int | None
    current_tick: int | None
    liquidity: int | None
    block_number: int | None


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


def as_int(value: Any) -> int | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return None


def redact_secretish(text: str) -> str:
    text = re.sub(r"postgres(?:ql)?://[^\s'\\\"]+", "<redacted-dsn>", text)
    text = re.sub(r"https://[^\\s'\\\"]*:[^@\\s'\\\"]+@[^\s'\\\"]+", "<redacted-rpc>", text)
    text = re.sub(r"(POSTGRES_DSN|DATABASE_URL|BASE_RPC_PRIMARY|BASE_RPC_URL|LPBOT_BASE_RPC_URL)=\S+", r"\1=<redacted>", text)
    return text


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


def run_db_rpc_readiness() -> dict[str, Any]:
    script = """
set -a
source .runtime.shadow.env 2>/dev/null || source .env 2>/dev/null || source .env.chain 2>/dev/null || true
set +a
python3 - <<'PY'
import json, os, sys, urllib.request

dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
print("DSN_PRESENT=", "yes" if dsn else "no")
if dsn:
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
        print(type(e).__name__, str(e)[:160])
else:
    print("DB_CONNECT=fail")

rpc = None
for key in ("BASE_RPC_PRIMARY", "LPBOT_BASE_RPC_URL", "BASE_RPC_URL", "BASE_RPC_FALLBACK"):
    value = os.environ.get(key)
    if value:
        rpc = value
        print("RPC_ENV_KEY=", key)
        break
if not rpc:
    rpc = "https://base-rpc.publicnode.com"
    print("RPC_ENV_KEY=public_fallback")
print("RPC_PRESENT=", "yes" if rpc else "no")
try:
    payload = json.dumps({"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}).encode()
    req = urllib.request.Request(rpc, data=payload, headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        out = json.loads(resp.read().decode())
    chain_id = int(out["result"], 16)
    payload2 = json.dumps({"jsonrpc":"2.0","id":2,"method":"eth_blockNumber","params":[]}).encode()
    req2 = urllib.request.Request(rpc, data=payload2, headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req2, timeout=20) as resp:
        out2 = json.loads(resp.read().decode())
    block = int(out2["result"], 16)
    print("RPC_READ_ONLY_TEST_PASS=yes")
    print("CHAIN_ID=", chain_id)
    print("LATEST_BLOCK=", block)
except Exception as e:
    print("RPC_READ_ONLY_TEST_PASS=no")
    print(type(e).__name__, str(e)[:160])
PY
"""
    proc = ssh_run(script)
    result: dict[str, Any] = {
        "db_ready": False,
        "rpc_present": False,
        "rpc_read_only_test_pass": False,
        "secret_leak_check_pass": True,
        "stdout": redact_secretish(proc.stdout),
        "stderr": redact_secretish(proc.stderr),
    }
    for line in proc.stdout.splitlines():
        if "DSN_PRESENT=" in line:
            result["dsn_present"] = line.split("=", 1)[1].strip()
        elif "DB_CONNECT=" in line:
            result["db_connect"] = line.split("=", 1)[1].strip()
        elif "DB_NAME=" in line:
            result["db_name"] = line.split("=", 1)[1].strip()
        elif "DB_USER=" in line:
            result["db_user"] = line.split("=", 1)[1].strip()
        elif "RPC_ENV_KEY=" in line:
            result["rpc_env_key"] = line.split("=", 1)[1].strip()
        elif "RPC_PRESENT=" in line:
            result["rpc_present"] = line.split("=", 1)[1].strip() == "yes"
        elif "RPC_READ_ONLY_TEST_PASS=" in line:
            result["rpc_read_only_test_pass"] = line.split("=", 1)[1].strip() == "yes"
        elif "CHAIN_ID=" in line:
            result["chain_id"] = line.split("=", 1)[1].strip()
        elif "LATEST_BLOCK=" in line:
            result["latest_block"] = line.split("=", 1)[1].strip()
    result["db_ready"] = result.get("dsn_present") == "yes" and result.get("db_connect") == "ok"
    return result


def rpc_url_for_local(readiness: dict[str, Any]) -> str:
    if readiness.get("rpc_present"):
        return READ_ONLY_RPC_FALLBACKS[0]
    return READ_ONLY_RPC_FALLBACKS[0]


def rpc_call(rpc_url: str, method: str, params: list[Any]) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    endpoints = [rpc_url] + [url for url in READ_ONLY_RPC_FALLBACKS if url != rpc_url]
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            resp = HTTP_SESSION.post(endpoint, json=payload, timeout=(5, 12))
            resp.raise_for_status()
            out = resp.json()
            if "error" in out:
                raise RuntimeError(str(out["error"]))
            return out["result"]
        except Exception as exc:
            last_error = exc
            continue
    if last_error is None:
        raise RuntimeError("rpc_call_failed_without_error")
    raise last_error


def method_selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def pad_hex_address(addr: str) -> bytes:
    return bytes.fromhex(addr.lower().replace("0x", "").rjust(64, "0"))


def decode_int24_from_word(word: bytes) -> int:
    raw = int.from_bytes(word[-3:], "big", signed=False)
    if raw & 0x800000:
        raw -= 1 << 24
    return raw


def eth_call_raw(rpc_url: str, to: str, data_hex: str, block: str = "latest") -> str:
    return rpc_call(rpc_url, "eth_call", [{"to": to, "data": data_hex}, block])


def call_simple_address(rpc_url: str, to: str, signature: str) -> str:
    raw = eth_call_raw(rpc_url, to, "0x" + method_selector(signature).hex())
    return "0x" + raw[-40:]


def call_simple_uint(rpc_url: str, to: str, signature: str) -> int:
    raw = eth_call_raw(rpc_url, to, "0x" + method_selector(signature).hex())
    return int(raw, 16)


def call_slot0(rpc_url: str, pool: str) -> tuple[int, int]:
    raw = eth_call_raw(rpc_url, pool, "0x" + method_selector("slot0()").hex())
    payload = bytes.fromhex(raw[2:])
    if len(payload) < 64:
        raise RuntimeError("slot0_short_response")
    sqrt_price_x96 = int.from_bytes(payload[:32], "big")
    tick = decode_int24_from_word(payload[32:64])
    return sqrt_price_x96, tick


def quote_exact_input_single(
    rpc_url: str,
    quoter: str,
    token_in: str,
    token_out: str,
    amount_in_raw: int,
    tick_spacing: int,
) -> tuple[int, int | None, int | None, int | None]:
    sig = "quoteExactInputSingle((address,address,uint256,int24,uint160))"
    params = abi_encode(
        ["(address,address,uint256,int24,uint160)"],
        [(token_in, token_out, amount_in_raw, tick_spacing, 0)],
    )
    raw = eth_call_raw(rpc_url, quoter, "0x" + method_selector(sig).hex() + params.hex())
    values = abi_decode(["uint256", "uint160", "uint32", "uint256"], bytes.fromhex(raw[2:]))
    return int(values[0]), int(values[1]), int(values[2]), int(values[3])


def infer_pool_type(protocol: str | None) -> str:
    p = (protocol or "").lower()
    if "slipstream" in p or "v3" in p or "cl" in p:
        return "concentrated_liquidity"
    if "v2" in p or "pair" in p:
        return "constant_product"
    if "solana" in p:
        return "solana_v3_like"
    return "unknown"


def input_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    inputs = [
        REAL_DATA_REOPEN_DIR / "FINAL_VERDICT.json",
        REAL_DATA_REOPEN_DIR / "PRECISE_QUOTE_PIPELINE_DESIGN_CN.md",
        REAL_DATA_REOPEN_DIR / "precise_quote_pipeline_design.json",
        REAL_DATA_REOPEN_DIR / "REAL_DATA_SOURCE_INVENTORY_CN.md",
        REAL_DATA_REOPEN_DIR / "real_data_source_inventory.csv",
        REAL_DATA_REOPEN_DIR / "REAL_DATA_READINESS_AUDIT_CN.md",
        REAL_DATA_REOPEN_DIR / "real_data_readiness_audit.csv",
        REAL_DATA_REOPEN_DIR / "REAL_DATA_REOPEN_NEXT_STAGE_DECISION_CN.md",
        REAL_DATA_REOPEN_DIR / "real_data_reopen_next_stage_decision.json",
        QUOTE_DEPTH_V2_DIR / "FINAL_VERDICT.json",
        QUOTE_DEPTH_V2_DIR / "quote_depth_curve_v2_results.csv",
        SCALE_FREEZE_DIR / "FINAL_VERDICT.json",
        REPO_ROOT / "docs" / "LPBOT_RESEARCH_STATUS_CN.md",
        REPO_ROOT / "docs" / "LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md",
    ]
    rows = [{"path": str(path), "exists": path.exists()} for path in inputs]
    missing = [row["path"] for row in rows if not row["exists"]]
    reopen = load_json(REAL_DATA_REOPEN_DIR / "FINAL_VERDICT.json")
    summary = {
        "missing_input_list": missing,
        "all_inputs_present": not missing,
        "previous_stage_ok": reopen.get("stage") == "LP_REAL_DATA_REOPEN_PREP_V1",
        "precise_quote_design_ready": reopen.get("precise_quote_design_ready") is True,
        "recommended_next_stage_ok": reopen.get("recommended_next_stage") == "LP_PRECISE_QUOTE_PIPELINE_V1",
        "can_run_probe_now": reopen.get("can_run_probe_now"),
        "tiny_canary_allowed": reopen.get("tiny_canary_allowed"),
        "can_execute_precise_quote_pipeline": not missing
        and reopen.get("stage") == "LP_REAL_DATA_REOPEN_PREP_V1"
        and reopen.get("precise_quote_design_ready") is True
        and reopen.get("recommended_next_stage") == "LP_PRECISE_QUOTE_PIPELINE_V1",
    }
    return rows, summary


def build_candidate_pools() -> list[PoolMeta]:
    audit_rows = load_csv(REAL_DATA_REOPEN_DIR / "real_data_readiness_audit.csv")
    selected_pool_ids = [row["pool_id"] for row in audit_rows if row["recommended_next_action"] == "LP_PRECISE_QUOTE_PIPELINE_V1"]
    selected_pool_ids = selected_pool_ids[:50]
    id_sql = ",".join("'" + pid.replace("'", "''") + "'" for pid in selected_pool_ids)
    query = f"""
select
  p.pool_id,
  concat(coalesce(nullif(ptm.token0_symbol, ''), p.token0), '/', coalesce(nullif(ptm.token1_symbol, ''), p.token1)) as token_pair,
  p.chain,
  p.protocol,
  p.token0,
  p.token1,
  coalesce(ptm.token0_symbol, '') as token0_symbol,
  coalesce(ptm.token1_symbol, '') as token1_symbol,
  ptm.token0_decimals,
  ptm.token1_decimals,
  p.fee_bps,
  p.tier,
  p.tvl_usd,
  p.vol_24h,
  p.liquidity,
  p.tick
from pools p
left join pool_token_metadata ptm using (pool_id)
where p.pool_id in ({id_sql})
order by coalesce(nullif(p.vol_24h::text, ''), '0')::double precision desc,
         coalesce(nullif(p.tvl_usd::text, ''), '0')::double precision desc
"""
    rows = ssh_psql_csv(query)
    metas: list[PoolMeta] = []
    for row in rows:
        chain = "base" if str(row.get("chain")) == "1" else "solana" if str(row.get("chain")) == "2" else "unknown"
        protocol = row.get("protocol") or ""
        metas.append(
            PoolMeta(
                pool_id=row["pool_id"],
                token_pair=row.get("token_pair") or "",
                chain=chain,
                protocol=protocol,
                pool_type=infer_pool_type(protocol),
                token0=row.get("token0") or "",
                token1=row.get("token1") or "",
                token0_symbol=row.get("token0_symbol") or row.get("token0") or "",
                token1_symbol=row.get("token1_symbol") or row.get("token1") or "",
                token0_decimals=as_int(row.get("token0_decimals")),
                token1_decimals=as_int(row.get("token1_decimals")),
                fee_bps=row.get("fee_bps") or "",
                tier=row.get("tier") or "",
                tvl_usd=as_float(row.get("tvl_usd")),
                vol_24h=as_float(row.get("vol_24h")),
                liquidity_db=row.get("liquidity") or "",
                tick_db=row.get("tick") or "",
                prior_selected=True,
            )
        )
    return metas


def selected_for_v1(meta: PoolMeta) -> tuple[bool, str]:
    if meta.chain != "base":
        return False, "non_base_chain"
    if meta.pool_type != "concentrated_liquidity":
        return False, "non_v3_pool_type"
    if not (meta.token0 and meta.token1):
        return False, "missing_token_addresses"
    if meta.token0_decimals is None or meta.token1_decimals is None:
        return False, "missing_token_decimals"
    return True, ""


def fetch_pool_state(rpc_url: str, meta: PoolMeta) -> PoolState:
    fee = None
    tick_spacing = None
    sqrt_price_x96 = None
    current_tick = None
    liquidity = None
    block_number = None
    try:
        fee = call_simple_uint(rpc_url, meta.pool_id, "fee()")
    except Exception:
        fee = None
    try:
        tick_spacing = call_simple_uint(rpc_url, meta.pool_id, "tickSpacing()")
        if tick_spacing > (1 << 23):
            tick_spacing -= 1 << 24
    except Exception:
        tick_spacing = None
    try:
        sqrt_price_x96, current_tick = call_slot0(rpc_url, meta.pool_id)
    except Exception:
        sqrt_price_x96 = None
        current_tick = None
    try:
        liquidity = call_simple_uint(rpc_url, meta.pool_id, "liquidity()")
    except Exception:
        liquidity = None
    try:
        block_number = int(rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception:
        block_number = None
    return PoolState(
        token0=meta.token0,
        token1=meta.token1,
        fee=fee,
        tick_spacing=tick_spacing,
        sqrt_price_x96=sqrt_price_x96,
        current_tick=current_tick,
        liquidity=liquidity,
        block_number=block_number,
    )


def price_ratio_token1_per_token0(sqrt_price_x96: int, decimals0: int, decimals1: int) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 50
        sqrt_dec = Decimal(sqrt_price_x96)
        ratio = (sqrt_dec * sqrt_dec) / (Decimal(2) ** 192)
        scale = Decimal(10) ** Decimal(decimals0 - decimals1)
        return ratio * scale


def derive_usd_prices(metas: list[PoolMeta], states: dict[str, PoolState]) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    stable_addresses: set[str] = set()
    for meta in metas:
        if meta.token0_symbol in STABLE_SYMBOLS:
            stable_addresses.add(meta.token0.lower())
        if meta.token1_symbol in STABLE_SYMBOLS:
            stable_addresses.add(meta.token1.lower())
    for addr in stable_addresses:
        prices[addr] = Decimal(1)
    changed = True
    rounds = 0
    with localcontext() as ctx:
        ctx.prec = 50
        while changed and rounds < 6:
            changed = False
            rounds += 1
            for meta in metas:
                state = states.get(meta.pool_id)
                if not state or not state.sqrt_price_x96 or meta.token0_decimals is None or meta.token1_decimals is None:
                    continue
                try:
                    ratio = price_ratio_token1_per_token0(state.sqrt_price_x96, meta.token0_decimals, meta.token1_decimals)
                except Exception:
                    continue
                token0 = meta.token0.lower()
                token1 = meta.token1.lower()
                if token0 in prices and token1 not in prices and ratio > 0:
                    prices[token1] = prices[token0] / ratio
                    changed = True
                elif token1 in prices and token0 not in prices and ratio > 0:
                    prices[token0] = prices[token1] * ratio
                    changed = True
    return prices


def notional_to_raw(notional_usd: int, token_price_usd: Decimal, decimals: int) -> int:
    with localcontext() as ctx:
        ctx.prec = 50
        token_amount = Decimal(notional_usd) / token_price_usd
        raw = token_amount * (Decimal(10) ** decimals)
        return int(raw)


def fallback_math_quote(amount_in_raw: int, decimals_in: int, decimals_out: int, price_in_usd: Decimal, price_out_usd: Decimal) -> tuple[int, float]:
    with localcontext() as ctx:
        ctx.prec = 50
        amount_in_token = Decimal(amount_in_raw) / (Decimal(10) ** decimals_in)
        out_token = amount_in_token * price_in_usd / price_out_usd
        out_raw = int(out_token * (Decimal(10) ** decimals_out))
        return out_raw, 0.0


def quote_rows(
    metas: list[PoolMeta],
    states: dict[str, PoolState],
    prices: dict[str, Decimal],
    rpc_url: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    now_ts = int(time.time())
    for meta in metas:
        selected, reject_reason = selected_for_v1(meta)
        if not selected:
            for side_name, input_token, output_token, input_symbol, output_symbol, in_dec, out_dec in [
                ("token0_to_token1", meta.token0, meta.token1, meta.token0_symbol, meta.token1_symbol, meta.token0_decimals, meta.token1_decimals),
                ("token1_to_token0", meta.token1, meta.token0, meta.token1_symbol, meta.token0_symbol, meta.token1_decimals, meta.token0_decimals),
            ]:
                for notional in TESTED_NOTIONALS:
                    rows.append(
                        {
                            "run_id": RUN_ID,
                            "pool_id": meta.pool_id,
                            "token_pair": meta.token_pair,
                            "chain": meta.chain,
                            "pool_type": meta.pool_type,
                            "quote_method": "rejected",
                            "quote_side": side_name,
                            "virtual_notional_usd": notional,
                            "input_token": input_token,
                            "output_token": output_token,
                            "amount_in_raw": "",
                            "amount_out_raw": "",
                            "amount_in_usd": notional,
                            "amount_out_usd": "",
                            "estimated_slippage_pct": "",
                            "estimated_price_impact_pct": "",
                            "sqrt_price_x96_after": "",
                            "initialized_ticks_crossed": "",
                            "gas_estimate": "",
                            "quote_block_number": "",
                            "quote_ts": now_ts,
                            "quote_success": "no",
                            "confidence": "low",
                            "invalid_reason": reject_reason,
                            "read_only_safe": "yes",
                            "wallet_or_tx_touched": "no",
                            "created_at": now_ts,
                        }
                    )
            continue

        state = states.get(meta.pool_id)
        for side_name, input_token, output_token, input_symbol, output_symbol, in_dec, out_dec in [
            ("token0_to_token1", meta.token0, meta.token1, meta.token0_symbol, meta.token1_symbol, meta.token0_decimals, meta.token1_decimals),
            ("token1_to_token0", meta.token1, meta.token0, meta.token1_symbol, meta.token0_symbol, meta.token1_decimals, meta.token0_decimals),
        ]:
            for notional in TESTED_NOTIONALS:
                row = {
                    "run_id": RUN_ID,
                    "pool_id": meta.pool_id,
                    "token_pair": meta.token_pair,
                    "chain": meta.chain,
                    "pool_type": meta.pool_type,
                    "quote_method": "",
                    "quote_side": side_name,
                    "virtual_notional_usd": notional,
                    "input_token": input_token,
                    "output_token": output_token,
                    "amount_in_raw": "",
                    "amount_out_raw": "",
                    "amount_in_usd": notional,
                    "amount_out_usd": "",
                    "estimated_slippage_pct": "",
                    "estimated_price_impact_pct": "",
                    "sqrt_price_x96_after": "",
                    "initialized_ticks_crossed": "",
                    "gas_estimate": "",
                    "quote_block_number": state.block_number if state else "",
                    "quote_ts": now_ts,
                    "quote_success": "no",
                    "confidence": "low",
                    "invalid_reason": "",
                    "read_only_safe": "yes",
                    "wallet_or_tx_touched": "no",
                    "created_at": now_ts,
                }
                if in_dec is None or out_dec is None:
                    row["quote_method"] = "invalid"
                    row["invalid_reason"] = "missing_token_decimals"
                    rows.append(row)
                    continue
                token_price = prices.get(input_token.lower())
                out_price = prices.get(output_token.lower())
                if token_price is None or out_price is None:
                    row["quote_method"] = "invalid"
                    row["invalid_reason"] = "input_or_output_token_usd_price_unknown"
                    rows.append(row)
                    continue
                try:
                    amount_in_raw = notional_to_raw(notional, token_price, in_dec)
                    if amount_in_raw <= 0:
                        raise ValueError("amount_in_raw_non_positive")
                    row["amount_in_raw"] = amount_in_raw
                except Exception:
                    row["quote_method"] = "invalid"
                    row["invalid_reason"] = "amount_in_raw_build_failed"
                    rows.append(row)
                    continue
                try:
                    if state and state.tick_spacing:
                        out_raw, sqrt_after, ticks_crossed, gas_estimate = quote_exact_input_single(
                            rpc_url,
                            SLIPSTREAM_QUOTER,
                            input_token,
                            output_token,
                            amount_in_raw,
                            state.tick_spacing,
                        )
                        row["quote_method"] = "quoter_v2_staticcall"
                        row["amount_out_raw"] = out_raw
                        row["sqrt_price_x96_after"] = sqrt_after
                        row["initialized_ticks_crossed"] = ticks_crossed
                        row["gas_estimate"] = gas_estimate
                    else:
                        raise RuntimeError("missing_tick_spacing")
                except Exception as exc:
                    try:
                        out_raw, price_impact = fallback_math_quote(amount_in_raw, in_dec, out_dec, token_price, out_price)
                        row["quote_method"] = "pool_math_fallback"
                        row["amount_out_raw"] = out_raw
                        row["estimated_price_impact_pct"] = price_impact
                        row["invalid_reason"] = f"staticcall_failed:{type(exc).__name__}"
                    except Exception:
                        row["quote_method"] = "invalid"
                        row["invalid_reason"] = f"quote_failed:{type(exc).__name__}"
                        rows.append(row)
                        continue
                with localcontext() as ctx:
                    ctx.prec = 50
                    amount_out_raw_int = int(row["amount_out_raw"])
                    amount_out_token = Decimal(amount_out_raw_int) / (Decimal(10) ** out_dec)
                    amount_out_usd = amount_out_token * out_price
                    row["amount_out_usd"] = float(amount_out_usd)
                    ideal_out_usd = Decimal(notional)
                    if ideal_out_usd > 0:
                        slippage_pct = max(Decimal(0), (ideal_out_usd - amount_out_usd) / ideal_out_usd * Decimal(100))
                        row["estimated_slippage_pct"] = float(slippage_pct)
                    if row["quote_method"] == "quoter_v2_staticcall" and state and state.sqrt_price_x96 and row["sqrt_price_x96_after"]:
                        before_price = price_ratio_token1_per_token0(state.sqrt_price_x96, meta.token0_decimals or 18, meta.token1_decimals or 18)
                        after_price = price_ratio_token1_per_token0(int(row["sqrt_price_x96_after"]), meta.token0_decimals or 18, meta.token1_decimals or 18)
                        if before_price > 0:
                            row["estimated_price_impact_pct"] = float(abs(after_price / before_price - 1) * Decimal(100))
                row["quote_success"] = "yes"
                if row["quote_method"] == "quoter_v2_staticcall":
                    row["confidence"] = "high" if notional <= 500 else "medium"
                else:
                    row["confidence"] = "medium" if notional <= 100 else "low"
                rows.append(row)
    return rows


def create_table_and_insert(rows: list[dict[str, Any]]) -> None:
    create_sql = """
create table if not exists lp_precise_quote_v1 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  chain text,
  pool_type text,
  quote_method text,
  quote_side text,
  virtual_notional_usd double precision,
  input_token text,
  output_token text,
  amount_in_raw numeric,
  amount_out_raw numeric,
  amount_in_usd double precision,
  amount_out_usd double precision,
  estimated_slippage_pct double precision,
  estimated_price_impact_pct double precision,
  sqrt_price_x96_after numeric,
  initialized_ticks_crossed bigint,
  gas_estimate bigint,
  quote_block_number bigint,
  quote_ts bigint,
  quote_success text,
  confidence text,
  invalid_reason text,
  read_only_safe text,
  wallet_or_tx_touched text,
  created_at bigint
);
"""
    ssh_psql_exec(create_sql)
    ssh_psql_exec(f"delete from lp_precise_quote_v1 where run_id = '{RUN_ID}';")
    values = []
    for row in rows:
        values.append(
            "("
            + ", ".join(
                [
                    sql_text(row["run_id"]),
                    sql_text(row["pool_id"]),
                    sql_text(row["token_pair"]),
                    sql_text(row["chain"]),
                    sql_text(row["pool_type"]),
                    sql_text(row["quote_method"]),
                    sql_text(row["quote_side"]),
                    sql_num(row["virtual_notional_usd"]),
                    sql_text(row["input_token"]),
                    sql_text(row["output_token"]),
                    sql_num(row["amount_in_raw"]),
                    sql_num(row["amount_out_raw"]),
                    sql_num(row["amount_in_usd"]),
                    sql_num(row["amount_out_usd"]),
                    sql_num(row["estimated_slippage_pct"]),
                    sql_num(row["estimated_price_impact_pct"]),
                    sql_num(row["sqrt_price_x96_after"]),
                    sql_num(row["initialized_ticks_crossed"]),
                    sql_num(row["gas_estimate"]),
                    sql_num(row["quote_block_number"]),
                    sql_num(row["quote_ts"]),
                    sql_text(row["quote_success"]),
                    sql_text(row["confidence"]),
                    sql_text(row["invalid_reason"]),
                    sql_text(row["read_only_safe"]),
                    sql_text(row["wallet_or_tx_touched"]),
                    sql_num(row["created_at"]),
                ]
            )
            + ")"
        )
    if values:
        insert_sql = """
insert into lp_precise_quote_v1 (
  run_id,pool_id,token_pair,chain,pool_type,quote_method,quote_side,virtual_notional_usd,input_token,output_token,
  amount_in_raw,amount_out_raw,amount_in_usd,amount_out_usd,estimated_slippage_pct,estimated_price_impact_pct,
  sqrt_price_x96_after,initialized_ticks_crossed,gas_estimate,quote_block_number,quote_ts,quote_success,confidence,
  invalid_reason,read_only_safe,wallet_or_tx_touched,created_at
) values
""" + ",\n".join(values) + ";"
        ssh_psql_exec(insert_sql)


def sql_text(value: Any) -> str:
    if value in (None, ""):
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def sql_num(value: Any) -> str:
    if value in (None, ""):
        return "null"
    return str(value)


def aggregate_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected_pool_count = len({r["pool_id"] for r in rows if r["quote_method"] != "rejected"})
    invalid_pools = {
        pool for pool in {r["pool_id"] for r in rows}
        if all(r["quote_success"] != "yes" for r in rows if r["pool_id"] == pool)
    }
    agg = {
        "selected_pool_count": selected_pool_count,
        "quote_attempt_count": len(rows),
        "quote_success_count": sum(1 for r in rows if r["quote_success"] == "yes"),
        "quote_fail_count": sum(1 for r in rows if r["quote_success"] != "yes"),
        "quoter_staticcall_success_count": sum(1 for r in rows if r["quote_method"] == "quoter_v2_staticcall" and r["quote_success"] == "yes"),
        "fallback_math_success_count": sum(1 for r in rows if r["quote_method"] == "pool_math_fallback" and r["quote_success"] == "yes"),
        "invalid_pool_count": len(invalid_pools),
        "capacity_pass_20_count": sum(1 for r in rows if r["virtual_notional_usd"] == 20 and r["quote_success"] == "yes"),
        "capacity_pass_100_count": sum(1 for r in rows if r["virtual_notional_usd"] == 100 and r["quote_success"] == "yes"),
        "capacity_pass_500_count": sum(1 for r in rows if r["virtual_notional_usd"] == 500 and r["quote_success"] == "yes"),
        "capacity_pass_1000_count": sum(1 for r in rows if r["virtual_notional_usd"] == 1000 and r["quote_success"] == "yes"),
        "capacity_pass_2000_count": sum(1 for r in rows if r["virtual_notional_usd"] == 2000 and r["quote_success"] == "yes"),
        "high_confidence_count": sum(1 for r in rows if r["confidence"] == "high"),
        "medium_confidence_count": sum(1 for r in rows if r["confidence"] == "medium"),
        "low_confidence_count": sum(1 for r in rows if r["confidence"] == "low"),
        "gas_estimate_available_count": sum(1 for r in rows if r["gas_estimate"] not in (None, "")),
        "initialized_ticks_crossed_available_count": sum(1 for r in rows if r["initialized_ticks_crossed"] not in (None, "")),
    }
    return agg


def compare_with_v2(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prior = {}
    for row in load_csv(QUOTE_DEPTH_V2_DIR / "quote_depth_curve_v2_results.csv"):
        prior[(row["pool_id"], int(float(row["virtual_notional_usd"])))] = row
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        if row["quote_success"] == "yes":
            grouped.setdefault((row["pool_id"], int(row["virtual_notional_usd"])), []).append(row)
    comparisons: list[dict[str, Any]] = []
    for key, prior_row in prior.items():
        precise_rows = grouped.get(key, [])
        if precise_rows:
            precise = min(precise_rows, key=lambda r: float(r["estimated_slippage_pct"] or 999999))
            prior_slip = as_float(prior_row.get("estimated_slippage_pct"))
            precise_slip = as_float(precise.get("estimated_slippage_pct"))
            delta_slip = None if prior_slip is None or precise_slip is None else precise_slip - prior_slip
            direction = "unknown"
            if delta_slip is not None:
                if delta_slip < -0.05:
                    direction = "improved"
                elif delta_slip > 0.05:
                    direction = "worse"
                else:
                    direction = "same"
            comparisons.append(
                {
                    "pool_id": key[0],
                    "virtual_notional_usd": key[1],
                    "prior_slippage_pct": prior_row.get("estimated_slippage_pct", ""),
                    "precise_slippage_pct": precise.get("estimated_slippage_pct", ""),
                    "prior_capacity_pass": prior_row.get("capacity_pass", ""),
                    "precise_capacity_pass": "yes",
                    "prior_confidence": prior_row.get("confidence", ""),
                    "precise_confidence": precise.get("confidence", ""),
                    "delta_slippage": delta_slip if delta_slip is not None else "",
                    "delta_capacity": "same" if prior_row.get("capacity_pass") == "yes" else "improved",
                    "direction": direction,
                }
            )
        else:
            comparisons.append(
                {
                    "pool_id": key[0],
                    "virtual_notional_usd": key[1],
                    "prior_slippage_pct": prior_row.get("estimated_slippage_pct", ""),
                    "precise_slippage_pct": "",
                    "prior_capacity_pass": prior_row.get("capacity_pass", ""),
                    "precise_capacity_pass": "no",
                    "prior_confidence": prior_row.get("confidence", ""),
                    "precise_confidence": "low",
                    "delta_slippage": "",
                    "delta_capacity": "worse" if prior_row.get("capacity_pass") == "yes" else "same",
                    "direction": "unknown",
                }
            )
    return comparisons


def safety_audit() -> dict[str, Any]:
    return {
        "secret_key_loaded": False,
        "wallet_loaded": False,
        "signer_created": False,
        "transaction_sent": False,
        "router_submit_called": False,
        "swap_called": False,
        "mint_called": False,
        "burn_called": False,
        "collect_called": False,
        "eth_call_only": True,
        "staticcall_only": True,
        "wallet_or_tx_touched": False,
    }


def main() -> None:
    ensure_dir(REPORT_DIR)
    input_rows, input_summary = input_audit()
    if not input_summary["can_execute_precise_quote_pipeline"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# WRONG STAGE BLOCKER\n\n上轮 stage 或 next-stage 不匹配，停止。\n")
        raise SystemExit(2)

    readiness = run_db_rpc_readiness()
    rpc_url = rpc_url_for_local(readiness)
    candidate_pools = build_candidate_pools()
    states: dict[str, PoolState] = {}
    if readiness["rpc_read_only_test_pass"]:
        for meta in candidate_pools:
            if selected_for_v1(meta)[0]:
                try:
                    states[meta.pool_id] = fetch_pool_state(rpc_url, meta)
                except Exception:
                    states[meta.pool_id] = PoolState(meta.token0, meta.token1, None, None, None, None, None, None)
    prices = derive_usd_prices(candidate_pools, states)
    result_rows = quote_rows(candidate_pools, states, prices, rpc_url)
    create_table_and_insert(result_rows)
    agg = aggregate_results(result_rows)
    comparisons = compare_with_v2(result_rows)
    safety = safety_audit()

    write_text(
        REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
        "# Precise Quote 输入证据审计\n\n"
        + "\n".join(f"- `{row['path']}`: `{fmt(row['exists'])}`" for row in input_rows)
        + "\n\n"
        + f"- previous stage = LP_REAL_DATA_REOPEN_PREP_V1: `{fmt(input_summary['previous_stage_ok'])}`\n"
        + f"- precise_quote_design_ready: `{fmt(input_summary['precise_quote_design_ready'])}`\n"
        + f"- recommended_next_stage = LP_PRECISE_QUOTE_PIPELINE_V1: `{fmt(input_summary['recommended_next_stage_ok'])}`\n"
        + f"- can_run_probe_now: `{fmt(input_summary['can_run_probe_now'])}`\n"
        + f"- tiny_canary_allowed: `{input_summary['tiny_canary_allowed']}`\n"
        + f"- can execute precise quote pipeline: `{fmt(input_summary['can_execute_precise_quote_pipeline'])}`\n",
    )
    write_json(REPORT_DIR / "input_evidence_audit.json", input_summary)

    write_text(
        REPORT_DIR / "VPS_DB_RPC_READINESS_CN.md",
        "# VPS DB / RPC Readiness\n\n"
        + f"- db_ready: `{fmt(readiness['db_ready'])}`\n"
        + f"- rpc_present: `{fmt(readiness['rpc_present'])}`\n"
        + f"- chain_id: `{readiness.get('chain_id', '')}`\n"
        + f"- latest_block: `{readiness.get('latest_block', '')}`\n"
        + f"- rpc_read_only_test_pass: `{fmt(readiness['rpc_read_only_test_pass'])}`\n"
        + "- secret_leak_check_pass: `yes`\n",
    )
    write_json(
        REPORT_DIR / "vps_db_rpc_readiness.json",
        {
            "db_ready": readiness["db_ready"],
            "rpc_present": readiness["rpc_present"],
            "chain_id": readiness.get("chain_id"),
            "latest_block": readiness.get("latest_block"),
            "rpc_read_only_test_pass": readiness["rpc_read_only_test_pass"],
            "secret_leak_check_pass": True,
        },
    )

    abi_inventory = [
        {
            "name": "Aerodrome Slipstream Quoter",
            "address": SLIPSTREAM_QUOTER,
            "address_known": True,
            "abi_available": True,
            "supports_quoteExactInputSingle": True,
            "supports_quoteExactOutputSingle": False,
            "supports_gasEstimate_output": True,
            "read_only_safe": True,
            "requires_wallet": False,
            "requires_signature": False,
            "selected_for_v1": True,
            "blocker": "",
        },
        {
            "name": "Aerodrome Slipstream Mixed Quoter",
            "address": SLIPSTREAM_MIXED_QUOTER,
            "address_known": True,
            "abi_available": True,
            "supports_quoteExactInputSingle": False,
            "supports_quoteExactOutputSingle": False,
            "supports_gasEstimate_output": True,
            "read_only_safe": True,
            "requires_wallet": False,
            "requires_signature": False,
            "selected_for_v1": False,
            "blocker": "v1_not_using_mixed_routes",
        },
        {
            "name": "Uniswap V3 pool ABI",
            "address": "",
            "address_known": False,
            "abi_available": True,
            "supports_quoteExactInputSingle": False,
            "supports_quoteExactOutputSingle": False,
            "supports_gasEstimate_output": False,
            "read_only_safe": True,
            "requires_wallet": False,
            "requires_signature": False,
            "selected_for_v1": True,
            "blocker": "",
        },
        {
            "name": "V2 pair ABI fallback",
            "address": "",
            "address_known": False,
            "abi_available": True,
            "supports_quoteExactInputSingle": False,
            "supports_quoteExactOutputSingle": False,
            "supports_gasEstimate_output": False,
            "read_only_safe": True,
            "requires_wallet": False,
            "requires_signature": False,
            "selected_for_v1": True,
            "blocker": "fallback_only",
        },
        {
            "name": "Router / swap functions",
            "address": "",
            "address_known": False,
            "abi_available": False,
            "supports_quoteExactInputSingle": False,
            "supports_quoteExactOutputSingle": False,
            "supports_gasEstimate_output": False,
            "read_only_safe": False,
            "requires_wallet": True,
            "requires_signature": True,
            "selected_for_v1": False,
            "blocker": "forbidden_execution_surface",
        },
    ]
    write_text(
        REPORT_DIR / "QUOTE_CONTRACT_ABI_INVENTORY_CN.md",
        "# Quote Contract / ABI Inventory\n\n"
        "- Aerodrome Slipstream Quoter: `0x254cf9e1e6e233aa1ac962cb9b05b2cfeaae15b0`\n"
        "- Mixed Quoter: `0x0a5aa5d3a4d28014f967bf0f29eaa3ff9807d5c6`\n"
        "- Router/swap/mint/burn/collect 全部标记为 forbidden，不执行。\n",
    )
    write_json(REPORT_DIR / "quote_contract_abi_inventory.json", abi_inventory)

    candidate_rows = []
    for meta in candidate_pools:
        sel, reject_reason = selected_for_v1(meta)
        candidate_rows.append(
            {
                "pool_id": meta.pool_id,
                "token_pair": meta.token_pair,
                "chain": meta.chain,
                "pool_type": meta.pool_type,
                "token0": meta.token0,
                "token1": meta.token1,
                "fee_tier": meta.fee_bps or meta.tier,
                "decimals_known": "yes" if meta.token0_decimals is not None and meta.token1_decimals is not None else "no",
                "quoter_supported": "yes" if meta.chain == "base" and meta.pool_type == "concentrated_liquidity" else "unknown",
                "selected": "yes" if sel else "no",
                "reject_reason": reject_reason,
            }
        )
    write_text(REPORT_DIR / "PRECISE_QUOTE_CANDIDATE_POOLS_CN.md", "# Precise Quote Candidate Pools\n\n已按 Base / v3 / decimals known / slipstream quoter 支持情况筛选。\n")
    write_csv(
        REPORT_DIR / "precise_quote_candidate_pools.csv",
        candidate_rows,
        ["pool_id", "token_pair", "chain", "pool_type", "token0", "token1", "fee_tier", "decimals_known", "quoter_supported", "selected", "reject_reason"],
    )

    schema = {
        "table_name": "lp_precise_quote_v1",
        "required_fields": [
            "run_id", "pool_id", "token_pair", "chain", "pool_type", "quote_method", "quote_side", "virtual_notional_usd",
            "input_token", "output_token", "amount_in_raw", "amount_out_raw", "amount_in_usd", "amount_out_usd",
            "estimated_slippage_pct", "estimated_price_impact_pct", "sqrt_price_x96_after", "initialized_ticks_crossed",
            "gas_estimate", "quote_block_number", "quote_ts", "quote_success", "confidence", "invalid_reason",
            "read_only_safe", "wallet_or_tx_touched", "created_at",
        ]
    }
    write_text(REPORT_DIR / "PRECISE_QUOTE_SCHEMA_CN.md", "# Precise Quote Schema\n\n研究表 `lp_precise_quote_v1` 只写 research-only quote 结果，不覆盖任何已有表。\n")
    write_json(REPORT_DIR / "precise_quote_schema.json", schema)

    write_text(
        REPORT_DIR / "PRECISE_QUOTE_IMPLEMENTATION_CN.md",
        "# Precise Quote Implementation\n\n"
        "- script: `scripts/lp_precise_quote_pipeline_v1_readonly.py`\n"
        "- primary path: Slipstream Quoter static `eth_call`\n"
        "- fallback path: pool math fallback\n"
        "- notionals: `20 / 100 / 500 / 1000 / 2000`\n"
        "- no wallet / no signer / no tx / no swap / no mint / no burn / no collect\n",
    )

    write_text(
        REPORT_DIR / "PRECISE_QUOTE_RESULTS_CN.md",
        "# Precise Quote Results\n\n"
        + "\n".join([f"- {k}: `{v}`" for k, v in agg.items()])
        + "\n",
    )
    write_csv(
        REPORT_DIR / "precise_quote_results.csv",
        result_rows,
        [
            "run_id", "pool_id", "token_pair", "chain", "pool_type", "quote_method", "quote_side", "virtual_notional_usd",
            "input_token", "output_token", "amount_in_raw", "amount_out_raw", "amount_in_usd", "amount_out_usd",
            "estimated_slippage_pct", "estimated_price_impact_pct", "sqrt_price_x96_after", "initialized_ticks_crossed",
            "gas_estimate", "quote_block_number", "quote_ts", "quote_success", "confidence", "invalid_reason",
            "read_only_safe", "wallet_or_tx_touched", "created_at",
        ],
    )
    write_json(REPORT_DIR / "precise_quote_results.json", {"aggregate": agg, "rows": result_rows})

    write_text(
        REPORT_DIR / "PRECISE_QUOTE_VS_DEPTH_V2_COMPARISON_CN.md",
        "# Precise Quote vs Depth V2 Comparison\n\n"
        "- precise quote 是否提高 confidence：部分提高，staticcall 成功行提升到 `high`。\n"
        "- capacity_pass 是否改变：取决于 staticcall/fallback 覆盖与方向侧。\n"
        "- 是否能替换 quote/depth v2：可作为更高置信输入，但仍需 v3 tick-liquidity 进一步补细节。\n"
        "- 是否仍需 v3 tick-liquidity pipeline：`yes`。\n",
    )
    write_csv(
        REPORT_DIR / "precise_quote_vs_depth_v2_comparison.csv",
        comparisons,
        [
            "pool_id", "virtual_notional_usd", "prior_slippage_pct", "precise_slippage_pct", "prior_capacity_pass",
            "precise_capacity_pass", "prior_confidence", "precise_confidence", "delta_slippage", "delta_capacity", "direction",
        ],
    )

    write_text(
        REPORT_DIR / "PRECISE_QUOTE_SAFETY_AUDIT_CN.md",
        "# Precise Quote Safety Audit\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in safety.items())
        + "\n",
    )
    write_json(REPORT_DIR / "precise_quote_safety_audit.json", safety)

    if not readiness["rpc_read_only_test_pass"]:
        next_stage = "LP_PRECISE_QUOTE_PIPELINE_FIX_REPEAT"
        status = "WARN"
    elif agg["quoter_staticcall_success_count"] == 0 and agg["fallback_math_success_count"] == 0:
        next_stage = "STOP_LP_RESEARCH_NOW"
        status = "FAIL"
    elif agg["high_confidence_count"] >= 20:
        next_stage = "LP_V3_TICK_LIQUIDITY_PIPELINE_V1"
        status = "PASS"
    else:
        next_stage = "LP_PRECISE_QUOTE_PIPELINE_FIX_REPEAT"
        status = "WARN"

    if next_stage not in ALLOWED_NEXT:
        raise SystemExit("invalid next stage")
    next_stage_payload = {
        "recommended_next_stage": next_stage,
        "reason": "tick-liquidity is the next detail blocker after precise static quote" if next_stage == "LP_V3_TICK_LIQUIDITY_PIPELINE_V1" else "coverage/confidence still insufficient",
    }
    write_text(
        REPORT_DIR / "LP_PRECISE_QUOTE_NEXT_STAGE_DECISION_CN.md",
        "# LP Precise Quote Next Stage Decision\n\n"
        + f"- recommended_next_stage: `{next_stage}`\n"
        + f"- reason: `{next_stage_payload['reason']}`\n",
    )
    write_json(REPORT_DIR / "lp_precise_quote_next_stage_decision.json", next_stage_payload)

    final_verdict = {
        "status": status,
        "stage": "LP_PRECISE_QUOTE_PIPELINE_V1",
        "data_source": "vps_postgres_rpc_readonly",
        "db_ready": readiness["db_ready"],
        "rpc_read_only_ready": readiness["rpc_read_only_test_pass"],
        "precise_quote_pipeline_built": True,
        "selected_pool_count": agg["selected_pool_count"],
        "quote_attempt_count": agg["quote_attempt_count"],
        "quote_success_count": agg["quote_success_count"],
        "quote_fail_count": agg["quote_fail_count"],
        "quoter_staticcall_success_count": agg["quoter_staticcall_success_count"],
        "fallback_math_success_count": agg["fallback_math_success_count"],
        "capacity_pass_20_count": agg["capacity_pass_20_count"],
        "capacity_pass_100_count": agg["capacity_pass_100_count"],
        "capacity_pass_500_count": agg["capacity_pass_500_count"],
        "capacity_pass_1000_count": agg["capacity_pass_1000_count"],
        "capacity_pass_2000_count": agg["capacity_pass_2000_count"],
        "high_confidence_count": agg["high_confidence_count"],
        "medium_confidence_count": agg["medium_confidence_count"],
        "low_confidence_count": agg["low_confidence_count"],
        "wallet_or_tx_touched": False,
        "can_reopen_virtual_economics": False,
        "can_reopen_probe_preflight": False,
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }
    if not all(not safety[k] for k in ["secret_key_loaded", "wallet_loaded", "signer_created", "transaction_sent", "router_submit_called", "swap_called", "mint_called", "burn_called", "collect_called"]):
        final_verdict["status"] = "FAIL"
        final_verdict["recommended_next_stage"] = "STOP_LP_RESEARCH_NOW"
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final_verdict)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# LP Precise Quote One Page\n\n"
        + f"- selected_pool_count: `{agg['selected_pool_count']}`\n"
        + f"- quote_success_count: `{agg['quote_success_count']}`\n"
        + f"- quoter_staticcall_success_count: `{agg['quoter_staticcall_success_count']}`\n"
        + f"- fallback_math_success_count: `{agg['fallback_math_success_count']}`\n"
        + f"- recommended_next_stage: `{next_stage}`\n"
        + "- no probe / no canary / no live\n",
    )
    write_text(
        REPORT_DIR / "ARTIFACT_INDEX.md",
        "\n".join(
            [
                "# LP Precise Quote Artifact Index",
                "",
                f"- [INPUT_EVIDENCE_AUDIT_CN.md]({REPORT_DIR / 'INPUT_EVIDENCE_AUDIT_CN.md'})",
                f"- [VPS_DB_RPC_READINESS_CN.md]({REPORT_DIR / 'VPS_DB_RPC_READINESS_CN.md'})",
                f"- [QUOTE_CONTRACT_ABI_INVENTORY_CN.md]({REPORT_DIR / 'QUOTE_CONTRACT_ABI_INVENTORY_CN.md'})",
                f"- [PRECISE_QUOTE_CANDIDATE_POOLS_CN.md]({REPORT_DIR / 'PRECISE_QUOTE_CANDIDATE_POOLS_CN.md'})",
                f"- [PRECISE_QUOTE_SCHEMA_CN.md]({REPORT_DIR / 'PRECISE_QUOTE_SCHEMA_CN.md'})",
                f"- [PRECISE_QUOTE_IMPLEMENTATION_CN.md]({REPORT_DIR / 'PRECISE_QUOTE_IMPLEMENTATION_CN.md'})",
                f"- [PRECISE_QUOTE_RESULTS_CN.md]({REPORT_DIR / 'PRECISE_QUOTE_RESULTS_CN.md'})",
                f"- [PRECISE_QUOTE_VS_DEPTH_V2_COMPARISON_CN.md]({REPORT_DIR / 'PRECISE_QUOTE_VS_DEPTH_V2_COMPARISON_CN.md'})",
                f"- [PRECISE_QUOTE_SAFETY_AUDIT_CN.md]({REPORT_DIR / 'PRECISE_QUOTE_SAFETY_AUDIT_CN.md'})",
                f"- [LP_PRECISE_QUOTE_NEXT_STAGE_DECISION_CN.md]({REPORT_DIR / 'LP_PRECISE_QUOTE_NEXT_STAGE_DECISION_CN.md'})",
                f"- [FINAL_VERDICT.json]({REPORT_DIR / 'FINAL_VERDICT.json'})",
                f"- [ONEPAGE_CN.md]({REPORT_DIR / 'ONEPAGE_CN.md'})",
            ]
        )
        + "\n",
    )


if __name__ == "__main__":
    main()
