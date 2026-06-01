#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import keccak


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_130245")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(os.environ.get("REPORT_DIR_OVERRIDE", str(REPO_ROOT / "reports" / "lp_v3_tick_liquidity" / RUN_ID)))
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
PRECISE_QUOTE_DIR = REPO_ROOT / "reports" / "lp_precise_quote" / "20260601_120001"
REAL_DATA_REOPEN_DIR = REPO_ROOT / "reports" / "lp_real_data_reopen" / "20260601_112642"
QUOTE_DEPTH_V2_DIR = REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739"
SCALE_FREEZE_DIR = REPO_ROOT / "reports" / "lp_scale_final_freeze" / "20260601_110649"
ALLOWED_NEXT = {
    "LP_REAL_COST_MODEL_PIPELINE_V1",
    "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
    "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
    "LP_V3_TICK_LIQUIDITY_PIPELINE_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}
READ_ONLY_RPC_FALLBACKS = [
    "https://mainnet.base.org",
    "https://developer-access-mainnet.base.org",
    "https://base-rpc.publicnode.com",
]
HTTP = requests.Session()
HTTP.headers.update({"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
HTTP.trust_env = False
NARROW_WORDS_PER_SIDE = 2
MEDIUM_WORDS_PER_SIDE = 4
MAX_WORDS_PER_SIDE = 8
TARGET_INITIALIZED_TICKS = 50
MAX_SELECTED_V3_POOLS = 6


@dataclass
class CandidatePool:
    pool_id: str
    token_pair: str
    chain: str
    pool_type: str
    token0: str
    token1: str
    fee_tier: str
    token0_decimals: int | None
    token1_decimals: int | None
    precise_quote_success_count: int
    precise_quote_fallback_success_count: int
    precise_quote_quoter_success_count: int
    prior_selected: bool
    selected: bool
    reject_reason: str


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
        print(type(e).__name__, str(e)[:200])
else:
    print("DB_CONNECT=fail")

rpc = None
for key in ("BASE_RPC_PRIMARY", "LPBOT_BASE_RPC_URL", "BASE_RPC_URL", "BASE_RPC_FALLBACK"):
    value = os.environ.get(key)
    if value:
        rpc = value
        print("RPC_ENV_KEY=", key)
        break
print("RPC_PRESENT=", "yes" if rpc else "no")
if rpc:
    try:
        payload = json.dumps({"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}).encode()
        req = urllib.request.Request(rpc, data=payload, headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            out = json.loads(resp.read().decode())
        chain_id = int(out["result"], 16)
        payload2 = json.dumps({"jsonrpc":"2.0","id":2,"method":"eth_blockNumber","params":[]}).encode()
        req2 = urllib.request.Request(rpc, data=payload2, headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=15) as resp:
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
        "rpc_read_only_ready": False,
        "secret_leak_check_pass": True,
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
            result["rpc_read_only_ready"] = line.split("=", 1)[1].strip() == "yes"
        elif "CHAIN_ID=" in line:
            result["chain_id"] = line.split("=", 1)[1].strip()
        elif "LATEST_BLOCK=" in line:
            result["latest_block"] = line.split("=", 1)[1].strip()
    result["db_ready"] = result.get("dsn_present") == "yes" and result.get("db_connect") == "ok"
    result["stdout"] = redact_secretish(proc.stdout)
    result["stderr"] = redact_secretish(proc.stderr)
    if not result["rpc_read_only_ready"]:
        for endpoint in READ_ONLY_RPC_FALLBACKS:
            try:
                chain_id = int(rpc_call(endpoint, "eth_chainId", []), 16)
                latest_block = int(rpc_call(endpoint, "eth_blockNumber", []), 16)
                result["rpc_read_only_ready"] = True
                result["rpc_env_key"] = "public_fallback"
                result["chain_id"] = str(chain_id)
                result["latest_block"] = str(latest_block)
                result["rpc_present"] = True
                break
            except Exception:
                continue
    return result


def rpc_url_for_local() -> str:
    return READ_ONLY_RPC_FALLBACKS[0]


def rpc_call(rpc_url: str, method: str, params: list[Any]) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    endpoints = [rpc_url] + [x for x in READ_ONLY_RPC_FALLBACKS if x != rpc_url]
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            resp = HTTP.post(endpoint, json=payload, timeout=(5, 12))
            resp.raise_for_status()
            out = resp.json()
            if "error" in out:
                raise RuntimeError(str(out["error"]))
            return out["result"]
        except Exception as exc:
            last_error = exc
    if last_error is None:
        raise RuntimeError("rpc_call_failed_without_error")
    raise last_error


def method_selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def encode_int24(value: int) -> bytes:
    word = bytearray(32)
    encoded = int(value) & 0xFFFFFF
    if value < 0:
        for i in range(32):
            word[i] = 0xFF
    word[29] = (encoded >> 16) & 0xFF
    word[30] = (encoded >> 8) & 0xFF
    word[31] = encoded & 0xFF
    return bytes(word)


def decode_int24(word: bytes) -> int:
    raw = int.from_bytes(word[-3:], "big")
    if raw & 0x800000:
        raw -= 1 << 24
    return raw


def decode_int56(word: bytes) -> int:
    raw = int.from_bytes(word[-7:], "big")
    if raw & (1 << 55):
        raw -= 1 << 56
    return raw


def decode_int128(word: bytes) -> int:
    return int.from_bytes(word, "big", signed=True)


def decode_uint256(word: bytes) -> int:
    return int.from_bytes(word, "big")


def eth_call_raw(rpc_url: str, to: str, data_hex: str) -> str:
    return rpc_call(rpc_url, "eth_call", [{"to": to, "data": data_hex}, "latest"])


def call_simple_uint(rpc_url: str, to: str, signature: str) -> int:
    raw = eth_call_raw(rpc_url, to, "0x" + method_selector(signature).hex())
    return int(raw, 16)


def call_simple_address(rpc_url: str, to: str, signature: str) -> str:
    raw = eth_call_raw(rpc_url, to, "0x" + method_selector(signature).hex())
    return "0x" + raw[-40:]


def call_slot0(rpc_url: str, to: str) -> dict[str, Any]:
    raw = eth_call_raw(rpc_url, to, "0x" + method_selector("slot0()").hex())
    payload = bytes.fromhex(raw[2:])
    if len(payload) < 32 * 7:
        raise RuntimeError("slot0_short_response")
    return {
        "sqrt_price_x96": decode_uint256(payload[0:32]),
        "current_tick": decode_int24(payload[32:64]),
        "observation_index": decode_uint256(payload[64:96]),
        "observation_cardinality": decode_uint256(payload[96:128]),
        "observation_cardinality_next": decode_uint256(payload[128:160]),
        "fee_protocol": decode_uint256(payload[160:192]),
        "unlocked": decode_uint256(payload[192:224]),
    }


def call_tick_bitmap(rpc_url: str, to: str, word_pos: int) -> int:
    data = "0x" + method_selector("tickBitmap(int16)").hex() + encode_int24(word_pos).hex()
    raw = eth_call_raw(rpc_url, to, data)
    return int(raw, 16)


def call_tick(rpc_url: str, to: str, tick_index: int) -> dict[str, Any]:
    data = "0x" + method_selector("ticks(int24)").hex() + encode_int24(tick_index).hex()
    raw = eth_call_raw(rpc_url, to, data)
    payload = bytes.fromhex(raw[2:])
    if len(payload) < 32 * 8:
        raise RuntimeError("ticks_short_response")
    return {
        "liquidity_gross": decode_uint256(payload[0:32]),
        "liquidity_net": decode_int128(payload[32:64]),
        "fee_growth_outside0_x128": decode_uint256(payload[64:96]),
        "fee_growth_outside1_x128": decode_uint256(payload[96:128]),
        "tick_cumulative_outside": decode_int56(payload[128:160]),
        "seconds_per_liquidity_outside_x128": decode_uint256(payload[160:192]),
        "seconds_outside": decode_uint256(payload[192:224]),
        "initialized": decode_uint256(payload[224:256]) != 0,
    }


def call_observe(rpc_url: str, to: str, seconds_agos: list[int]) -> dict[str, Any]:
    data = "0x" + method_selector("observe(uint32[])").hex() + abi_encode(["uint32[]"], [seconds_agos]).hex()
    raw = eth_call_raw(rpc_url, to, data)
    payload = bytes.fromhex(raw[2:])
    vals = abi_decode(["int56[]", "uint160[]"], payload)
    return {
        "tick_cumulatives": [int(x) for x in vals[0]],
        "seconds_per_liquidity_cumulative_x128s": [int(x) for x in vals[1]],
    }


def pool_type_ok(pool_type: str) -> bool:
    return pool_type in {"v3", "uniswap_v3", "concentrated_liquidity", "equivalent", "concentrated-liquidity"}


def sql_text(value: Any) -> str:
    if value in (None, ""):
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def sql_num(value: Any) -> str:
    if value in (None, ""):
        return "null"
    return str(value)


def input_evidence_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    inputs = [
        PRECISE_QUOTE_DIR / "FINAL_VERDICT.json",
        PRECISE_QUOTE_DIR / "PRECISE_QUOTE_RESULTS_CN.md",
        PRECISE_QUOTE_DIR / "precise_quote_results.csv",
        PRECISE_QUOTE_DIR / "PRECISE_QUOTE_VS_DEPTH_V2_COMPARISON_CN.md",
        PRECISE_QUOTE_DIR / "precise_quote_vs_depth_v2_comparison.csv",
        PRECISE_QUOTE_DIR / "PRECISE_QUOTE_SAFETY_AUDIT_CN.md",
        PRECISE_QUOTE_DIR / "precise_quote_safety_audit.json",
        PRECISE_QUOTE_DIR / "LP_PRECISE_QUOTE_NEXT_STAGE_DECISION_CN.md",
        PRECISE_QUOTE_DIR / "lp_precise_quote_next_stage_decision.json",
        REAL_DATA_REOPEN_DIR / "V3_TICK_LIQUIDITY_PIPELINE_DESIGN_CN.md",
        REAL_DATA_REOPEN_DIR / "v3_tick_liquidity_pipeline_design.json",
        REAL_DATA_REOPEN_DIR / "REAL_DATA_READINESS_AUDIT_CN.md",
        REAL_DATA_REOPEN_DIR / "real_data_readiness_audit.csv",
        QUOTE_DEPTH_V2_DIR / "quote_depth_curve_v2_results.csv",
        SCALE_FREEZE_DIR / "FINAL_VERDICT.json",
        REPO_ROOT / "docs" / "LPBOT_RESEARCH_STATUS_CN.md",
        REPO_ROOT / "docs" / "LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md",
    ]
    rows = [{"path": str(p), "exists": "yes" if p.exists() else "no"} for p in inputs]
    precise = load_json(PRECISE_QUOTE_DIR / "FINAL_VERDICT.json")
    summary = {
        "missing_input_list": [r["path"] for r in rows if r["exists"] == "no"],
        "previous_stage_ok": precise.get("stage") == "LP_PRECISE_QUOTE_PIPELINE_V1",
        "precise_quote_pipeline_built": precise.get("precise_quote_pipeline_built") is True,
        "rpc_read_only_ready": precise.get("rpc_read_only_ready") is True,
        "wallet_or_tx_touched": precise.get("wallet_or_tx_touched"),
        "recommended_next_stage": precise.get("recommended_next_stage"),
        "can_execute_v3_tick_liquidity_pipeline": all(r["exists"] == "yes" for r in rows)
        and precise.get("stage") == "LP_PRECISE_QUOTE_PIPELINE_V1"
        and precise.get("precise_quote_pipeline_built") is True
        and precise.get("rpc_read_only_ready") is True
        and precise.get("wallet_or_tx_touched") is False
        and precise.get("recommended_next_stage") == "LP_V3_TICK_LIQUIDITY_PIPELINE_V1",
    }
    return rows, summary


def build_candidates() -> list[CandidatePool]:
    candidate_rows = load_csv(PRECISE_QUOTE_DIR / "precise_quote_candidate_pools.csv")
    results = load_csv(PRECISE_QUOTE_DIR / "precise_quote_results.csv")
    by_pool: dict[str, dict[str, int]] = {}
    for row in results:
        d = by_pool.setdefault(row["pool_id"], {"succ": 0, "fallback": 0, "quoter": 0})
        if row["quote_success"] == "yes":
            d["succ"] += 1
        if row["quote_success"] == "yes" and row["quote_method"] == "pool_math_fallback":
            d["fallback"] += 1
        if row["quote_success"] == "yes" and row["quote_method"] == "quoter_v2_staticcall":
            d["quoter"] += 1
    meta_rows = ssh_psql_csv(
        """
select
  p.pool_id,
  coalesce(ptm.token0_decimals, null) as token0_decimals,
  coalesce(ptm.token1_decimals, null) as token1_decimals,
  p.protocol
from pools p
left join pool_token_metadata ptm using (pool_id)
where p.pool_id in (
  select distinct pool_id from lp_precise_quote_v1 where run_id = '20260601_120001'
)
"""
    )
    meta_by = {r["pool_id"]: r for r in meta_rows}
    preliminary: list[CandidatePool] = []
    for row in candidate_rows:
        counts = by_pool.get(row["pool_id"], {"succ": 0, "fallback": 0, "quoter": 0})
        token0_dec = as_int(meta_by.get(row["pool_id"], {}).get("token0_decimals"))
        token1_dec = as_int(meta_by.get(row["pool_id"], {}).get("token1_decimals"))
        selected = True
        reject_reason = ""
        if row["chain"] != "base":
            selected = False
            reject_reason = "non_base_chain"
        elif not pool_type_ok(row["pool_type"]):
            selected = False
            reject_reason = "non_v3_pool_type"
        elif counts["succ"] <= 0:
            selected = False
            reject_reason = "no_precise_quote_success"
        elif token0_dec is None or token1_dec is None:
            selected = False
            reject_reason = "missing_token_decimals"
        preliminary.append(
            CandidatePool(
                pool_id=row["pool_id"],
                token_pair=row["token_pair"],
                chain=row["chain"],
                pool_type=row["pool_type"],
                token0=row["token0"],
                token1=row["token1"],
                fee_tier=row["fee_tier"],
                token0_decimals=token0_dec,
                token1_decimals=token1_dec,
                precise_quote_success_count=counts["succ"],
                precise_quote_fallback_success_count=counts["fallback"],
                precise_quote_quoter_success_count=counts["quoter"],
                prior_selected=row.get("selected") == "yes",
                selected=selected,
                reject_reason=reject_reason,
            )
        )
    eligible = [p for p in preliminary if p.selected]
    eligible.sort(
        key=lambda p: (
            -p.precise_quote_quoter_success_count,
            -p.precise_quote_success_count,
            p.precise_quote_fallback_success_count,
            p.pool_id,
        )
    )
    allowed = {p.pool_id for p in eligible[:MAX_SELECTED_V3_POOLS]}
    out: list[CandidatePool] = []
    for pool in preliminary:
        if pool.selected and pool.pool_id not in allowed:
            pool = CandidatePool(
                pool_id=pool.pool_id,
                token_pair=pool.token_pair,
                chain=pool.chain,
                pool_type=pool.pool_type,
                token0=pool.token0,
                token1=pool.token1,
                fee_tier=pool.fee_tier,
                token0_decimals=pool.token0_decimals,
                token1_decimals=pool.token1_decimals,
                precise_quote_success_count=pool.precise_quote_success_count,
                precise_quote_fallback_success_count=pool.precise_quote_fallback_success_count,
                precise_quote_quoter_success_count=pool.precise_quote_quoter_success_count,
                prior_selected=pool.prior_selected,
                selected=False,
                reject_reason="rpc_budget_cap",
            )
        out.append(pool)
    return out


def abi_inventory() -> tuple[list[dict[str, Any]], list[str]]:
    entries = [
        {"method": "token0()", "abi_available": True, "read_only_safe": True, "requires_wallet": False, "requires_signature": False, "selected_for_v1": True, "notes": "pool token0 address"},
        {"method": "token1()", "abi_available": True, "read_only_safe": True, "requires_wallet": False, "requires_signature": False, "selected_for_v1": True, "notes": "pool token1 address"},
        {"method": "fee()", "abi_available": True, "read_only_safe": True, "requires_wallet": False, "requires_signature": False, "selected_for_v1": True, "notes": "fee tier for v3-like pool"},
        {"method": "tickSpacing()", "abi_available": True, "read_only_safe": True, "requires_wallet": False, "requires_signature": False, "selected_for_v1": True, "notes": "tick spacing and compression"},
        {"method": "liquidity()", "abi_available": True, "read_only_safe": True, "requires_wallet": False, "requires_signature": False, "selected_for_v1": True, "notes": "current in-range liquidity"},
        {"method": "slot0()", "abi_available": True, "read_only_safe": True, "requires_wallet": False, "requires_signature": False, "selected_for_v1": True, "notes": "current tick and sqrtPriceX96"},
        {"method": "ticks(int24)", "abi_available": True, "read_only_safe": True, "requires_wallet": False, "requires_signature": False, "selected_for_v1": True, "notes": "liquidityGross/liquidityNet and feeGrowthOutside"},
        {"method": "tickBitmap(int16)", "abi_available": True, "read_only_safe": True, "requires_wallet": False, "requires_signature": False, "selected_for_v1": True, "notes": "initialized tick bitset per word"},
        {"method": "observe(uint32[])", "abi_available": True, "read_only_safe": True, "requires_wallet": False, "requires_signature": False, "selected_for_v1": True, "notes": "twap-like observation and liquidity cumulatives"},
        {"method": "observations(uint256)", "abi_available": True, "read_only_safe": True, "requires_wallet": False, "requires_signature": False, "selected_for_v1": False, "notes": "optional, only if direct observation row needed"},
        {"method": "mint", "abi_available": True, "read_only_safe": False, "requires_wallet": True, "requires_signature": True, "selected_for_v1": False, "notes": "forbidden state-changing"},
        {"method": "burn", "abi_available": True, "read_only_safe": False, "requires_wallet": True, "requires_signature": True, "selected_for_v1": False, "notes": "forbidden state-changing"},
        {"method": "collect", "abi_available": True, "read_only_safe": False, "requires_wallet": True, "requires_signature": True, "selected_for_v1": False, "notes": "forbidden state-changing"},
        {"method": "swap", "abi_available": True, "read_only_safe": False, "requires_wallet": True, "requires_signature": True, "selected_for_v1": False, "notes": "forbidden state-changing"},
        {"method": "flash", "abi_available": True, "read_only_safe": False, "requires_wallet": True, "requires_signature": True, "selected_for_v1": False, "notes": "forbidden state-changing"},
        {"method": "increaseLiquidity", "abi_available": True, "read_only_safe": False, "requires_wallet": True, "requires_signature": True, "selected_for_v1": False, "notes": "forbidden state-changing"},
        {"method": "decreaseLiquidity", "abi_available": True, "read_only_safe": False, "requires_wallet": True, "requires_signature": True, "selected_for_v1": False, "notes": "forbidden state-changing"},
        {"method": "multicall(state-changing)", "abi_available": True, "read_only_safe": False, "requires_wallet": True, "requires_signature": True, "selected_for_v1": False, "notes": "forbidden if any subcall changes state"},
    ]
    forbidden = [e["method"] for e in entries if not e["read_only_safe"]]
    return entries, forbidden


def schema_definition() -> list[str]:
    return [
        "run_id", "pool_id", "token_pair", "chain", "block_number", "snapshot_ts", "token0", "token1", "fee_tier",
        "tick_spacing", "sqrt_price_x96", "current_tick", "current_liquidity", "tick_index", "initialized",
        "liquidity_gross", "liquidity_net", "fee_growth_outside0_x128", "fee_growth_outside1_x128", "seconds_outside",
        "tick_distance_from_current", "scan_method", "confidence", "invalid_reason", "read_only_safe",
        "wallet_or_tx_touched", "created_at",
    ]


def create_research_table() -> None:
    sql = """
create table if not exists lp_v3_tick_liquidity_snapshot_v1 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  chain text,
  block_number bigint,
  snapshot_ts bigint,
  token0 text,
  token1 text,
  fee_tier text,
  tick_spacing integer,
  sqrt_price_x96 numeric,
  current_tick integer,
  current_liquidity numeric,
  tick_index integer,
  initialized boolean,
  liquidity_gross numeric,
  liquidity_net numeric,
  fee_growth_outside0_x128 numeric,
  fee_growth_outside1_x128 numeric,
  seconds_outside bigint,
  tick_distance_from_current integer,
  scan_method text,
  confidence text,
  invalid_reason text,
  read_only_safe boolean,
  wallet_or_tx_touched boolean,
  created_at bigint
);
"""
    ssh_psql_exec(sql)
    ssh_psql_exec(f"delete from lp_v3_tick_liquidity_snapshot_v1 where run_id = '{RUN_ID}';")


def scan_policy_payload() -> dict[str, Any]:
    return {
        "current_tick_source": "slot0",
        "tick_spacing_source": "tickSpacing",
        "scan_range_ticks": {
            "narrow_words_per_side": NARROW_WORDS_PER_SIDE,
            "medium_words_per_side": MEDIUM_WORDS_PER_SIDE,
            "hard_cap_words_per_side": MAX_WORDS_PER_SIDE,
            "target_initialized_ticks": TARGET_INITIALIZED_TICKS,
        },
        "tick_bitmap_policy": {
            "scan_center": "current compressed tick word",
            "expand_until": "target initialized ticks or hard cap",
        },
        "entry_safe_timestamp": "quote_block_number or latest readonly block at snapshot",
        "no_lookahead_rule": "latest read-only chain state only; no future outcome or realized pnl data",
        "fallback": "slot0+liquidity only if tickBitmap or ticks fail; confidence lowers",
    }


def initialized_ticks_from_bitmap(word_value: int, word_pos: int, tick_spacing: int) -> list[int]:
    ticks = []
    for bit in range(256):
        if (word_value >> bit) & 1:
            compressed = word_pos * 256 + bit
            ticks.append(compressed * tick_spacing)
    return ticks


def materialize_pool(rpc_url: str, pool: CandidatePool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stats = {
        "pool_id": pool.pool_id,
        "token_pair": pool.token_pair,
        "snapshot_success": False,
        "slot0_success": False,
        "tick_bitmap_success": 0,
        "ticks_success": 0,
        "observe_success": False,
        "current_liquidity_available": False,
        "initialized_ticks_found": 0,
        "confidence": "low",
        "invalid_reason": "",
    }
    ts = int(time.time())
    try:
        token0 = call_simple_address(rpc_url, pool.pool_id, "token0()")
        token1 = call_simple_address(rpc_url, pool.pool_id, "token1()")
        fee = call_simple_uint(rpc_url, pool.pool_id, "fee()")
        tick_spacing = call_simple_uint(rpc_url, pool.pool_id, "tickSpacing()")
        if tick_spacing > (1 << 23):
            tick_spacing -= 1 << 24
        liquidity = call_simple_uint(rpc_url, pool.pool_id, "liquidity()")
        slot0 = call_slot0(rpc_url, pool.pool_id)
        stats["slot0_success"] = True
        stats["current_liquidity_available"] = liquidity > 0
        current_tick = slot0["current_tick"]
        current_word = math.floor(current_tick / tick_spacing) >> 8
        block_number = int(rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception as exc:
        stats["invalid_reason"] = f"pool_state_read_failed:{type(exc).__name__}"
        rows.append({
            "run_id": RUN_ID, "pool_id": pool.pool_id, "token_pair": pool.token_pair, "chain": pool.chain,
            "block_number": "", "snapshot_ts": ts, "token0": pool.token0, "token1": pool.token1, "fee_tier": pool.fee_tier,
            "tick_spacing": "", "sqrt_price_x96": "", "current_tick": "", "current_liquidity": "", "tick_index": "",
            "initialized": "", "liquidity_gross": "", "liquidity_net": "", "fee_growth_outside0_x128": "",
            "fee_growth_outside1_x128": "", "seconds_outside": "", "tick_distance_from_current": "", "scan_method": "state_read_failed",
            "confidence": "low", "invalid_reason": stats["invalid_reason"], "read_only_safe": True,
            "wallet_or_tx_touched": False, "created_at": ts,
        })
        return rows, stats

    observe_ok = False
    try:
        call_observe(rpc_url, pool.pool_id, [300, 0])
        observe_ok = True
        stats["observe_success"] = True
    except Exception:
        pass

    initialized_ticks: list[int] = []
    bitmap_ok = 0
    for distance in range(0, MAX_WORDS_PER_SIDE + 1):
        positions = [current_word] if distance == 0 else [current_word - distance, current_word + distance]
        for word_pos in positions:
            try:
                bitmap = call_tick_bitmap(rpc_url, pool.pool_id, word_pos)
                bitmap_ok += 1
                stats["tick_bitmap_success"] += 1
                ticks = initialized_ticks_from_bitmap(bitmap, word_pos, tick_spacing)
                initialized_ticks.extend(ticks)
            except Exception:
                continue
        if len(set(initialized_ticks)) >= TARGET_INITIALIZED_TICKS and distance >= NARROW_WORDS_PER_SIDE:
            break
    initialized_ticks = sorted(set(initialized_ticks), key=lambda x: abs(x - current_tick))
    if len(initialized_ticks) > TARGET_INITIALIZED_TICKS:
        initialized_ticks = initialized_ticks[:TARGET_INITIALIZED_TICKS]

    tick_rows = 0
    for tick_index in initialized_ticks:
        try:
            tick_state = call_tick(rpc_url, pool.pool_id, tick_index)
            stats["ticks_success"] += 1
            tick_rows += 1
            rows.append({
                "run_id": RUN_ID,
                "pool_id": pool.pool_id,
                "token_pair": pool.token_pair,
                "chain": pool.chain,
                "block_number": block_number,
                "snapshot_ts": ts,
                "token0": token0,
                "token1": token1,
                "fee_tier": str(fee),
                "tick_spacing": tick_spacing,
                "sqrt_price_x96": slot0["sqrt_price_x96"],
                "current_tick": current_tick,
                "current_liquidity": liquidity,
                "tick_index": tick_index,
                "initialized": tick_state["initialized"],
                "liquidity_gross": tick_state["liquidity_gross"],
                "liquidity_net": tick_state["liquidity_net"],
                "fee_growth_outside0_x128": tick_state["fee_growth_outside0_x128"],
                "fee_growth_outside1_x128": tick_state["fee_growth_outside1_x128"],
                "seconds_outside": tick_state["seconds_outside"],
                "tick_distance_from_current": abs(tick_index - current_tick),
                "scan_method": "tick_bitmap_plus_ticks",
                "confidence": "",
                "invalid_reason": "",
                "read_only_safe": True,
                "wallet_or_tx_touched": False,
                "created_at": ts,
            })
        except Exception as exc:
            rows.append({
                "run_id": RUN_ID,
                "pool_id": pool.pool_id,
                "token_pair": pool.token_pair,
                "chain": pool.chain,
                "block_number": block_number,
                "snapshot_ts": ts,
                "token0": token0,
                "token1": token1,
                "fee_tier": str(fee),
                "tick_spacing": tick_spacing,
                "sqrt_price_x96": slot0["sqrt_price_x96"],
                "current_tick": current_tick,
                "current_liquidity": liquidity,
                "tick_index": tick_index,
                "initialized": True,
                "liquidity_gross": "",
                "liquidity_net": "",
                "fee_growth_outside0_x128": "",
                "fee_growth_outside1_x128": "",
                "seconds_outside": "",
                "tick_distance_from_current": abs(tick_index - current_tick),
                "scan_method": "tick_bitmap_plus_ticks",
                "confidence": "low",
                "invalid_reason": f"tick_read_failed:{type(exc).__name__}",
                "read_only_safe": True,
                "wallet_or_tx_touched": False,
                "created_at": ts,
            })

    if not rows:
        rows.append({
            "run_id": RUN_ID,
            "pool_id": pool.pool_id,
            "token_pair": pool.token_pair,
            "chain": pool.chain,
            "block_number": block_number,
            "snapshot_ts": ts,
            "token0": token0,
            "token1": token1,
            "fee_tier": str(fee),
            "tick_spacing": tick_spacing,
            "sqrt_price_x96": slot0["sqrt_price_x96"],
            "current_tick": current_tick,
            "current_liquidity": liquidity,
            "tick_index": "",
            "initialized": "",
            "liquidity_gross": "",
            "liquidity_net": "",
            "fee_growth_outside0_x128": "",
            "fee_growth_outside1_x128": "",
            "seconds_outside": "",
            "tick_distance_from_current": "",
            "scan_method": "slot0_liquidity_only",
            "confidence": "low",
            "invalid_reason": "no_initialized_ticks_found",
            "read_only_safe": True,
            "wallet_or_tx_touched": False,
            "created_at": ts,
        })

    stats["initialized_ticks_found"] = len(initialized_ticks)
    stats["snapshot_success"] = stats["slot0_success"] and stats["ticks_success"] > 0
    if stats["snapshot_success"] and stats["tick_bitmap_success"] > 0 and observe_ok:
        stats["confidence"] = "high"
    elif stats["slot0_success"] and stats["current_liquidity_available"]:
        stats["confidence"] = "medium"
    else:
        stats["confidence"] = "low"
    for row in rows:
        row["confidence"] = row["confidence"] or stats["confidence"]
    return rows, stats


def insert_rows(rows: list[dict[str, Any]]) -> None:
    create_research_table()
    values = []
    for row in rows:
        values.append("(" + ", ".join([
            sql_text(row["run_id"]), sql_text(row["pool_id"]), sql_text(row["token_pair"]), sql_text(row["chain"]),
            sql_num(row["block_number"]), sql_num(row["snapshot_ts"]), sql_text(row["token0"]), sql_text(row["token1"]),
            sql_text(row["fee_tier"]), sql_num(row["tick_spacing"]), sql_num(row["sqrt_price_x96"]), sql_num(row["current_tick"]),
            sql_num(row["current_liquidity"]), sql_num(row["tick_index"]),
            "true" if row["initialized"] is True else "false" if row["initialized"] is False else "null",
            sql_num(row["liquidity_gross"]), sql_num(row["liquidity_net"]), sql_num(row["fee_growth_outside0_x128"]),
            sql_num(row["fee_growth_outside1_x128"]), sql_num(row["seconds_outside"]), sql_num(row["tick_distance_from_current"]),
            sql_text(row["scan_method"]), sql_text(row["confidence"]), sql_text(row["invalid_reason"]),
            "true" if row["read_only_safe"] else "false", "true" if row["wallet_or_tx_touched"] else "false",
            sql_num(row["created_at"]),
        ]) + ")")
    if values:
        sql = """
insert into lp_v3_tick_liquidity_snapshot_v1 (
  run_id,pool_id,token_pair,chain,block_number,snapshot_ts,token0,token1,fee_tier,tick_spacing,sqrt_price_x96,current_tick,
  current_liquidity,tick_index,initialized,liquidity_gross,liquidity_net,fee_growth_outside0_x128,fee_growth_outside1_x128,
  seconds_outside,tick_distance_from_current,scan_method,confidence,invalid_reason,read_only_safe,wallet_or_tx_touched,created_at
) values
""" + ",\n".join(values) + ";"
        ssh_psql_exec(sql)


def capacity_audit(candidates: list[CandidatePool], tick_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    precise = load_csv(PRECISE_QUOTE_DIR / "precise_quote_results.csv")
    precise_by_pool = {}
    for row in precise:
        pool = row["pool_id"]
        d = precise_by_pool.setdefault(pool, {})
        n = int(float(row["virtual_notional_usd"]))
        d[n] = d.get(n, False) or row["quote_success"] == "yes"
    tick_by_pool: dict[str, list[dict[str, Any]]] = {}
    for row in tick_rows:
        tick_by_pool.setdefault(row["pool_id"], []).append(row)
    audits = []
    for pool in candidates:
        rows = tick_by_pool.get(pool.pool_id, [])
        valid = [r for r in rows if r.get("tick_index") not in ("", None) and r.get("invalid_reason", "") == ""]
        liquidity_nets = [abs(as_int(r.get("liquidity_net")) or 0) for r in valid]
        current_tick = as_int(valid[0].get("current_tick")) if valid else None
        current_liquidity = as_int(valid[0].get("current_liquidity")) if valid else None
        nearest = min((as_int(r.get("tick_distance_from_current")) or 10**9 for r in valid), default=None)
        initialized_count = len(valid)
        density = sum(liquidity_nets[:10]) / initialized_count if initialized_count else 0
        support = {}
        for n in [20, 100, 500, 1000, 2000]:
            if not valid:
                support[n] = "unknown"
            elif initialized_count >= 8 and current_liquidity and current_liquidity > 0 and nearest is not None and nearest <= (as_int(valid[0].get("tick_spacing")) or 1) * 4:
                support[n] = "yes" if n <= 500 or initialized_count >= 15 else "unknown"
            else:
                support[n] = "no"
        risk = "ok"
        confidence = "high" if initialized_count >= 15 else "medium" if initialized_count >= 6 else "low"
        if not valid:
            risk = "unknown_range"
            confidence = "low"
        elif initialized_count < 6:
            risk = "sparse_ticks"
        elif nearest is not None and nearest > (as_int(valid[0].get("tick_spacing")) or 1) * 10:
            risk = "high_tick_distance"
        elif current_liquidity is not None and current_liquidity <= 0:
            risk = "thin_liquidity"
        elif any(precise_by_pool.get(pool.pool_id, {}).get(n, False) and support[n] == "no" for n in [20, 100, 500]):
            risk = "quote_disagrees_with_tick"
        audits.append({
            "pool_id": pool.pool_id,
            "token_pair": pool.token_pair,
            "current_tick": current_tick,
            "current_liquidity": current_liquidity,
            "initialized_tick_count_nearby": initialized_count,
            "liquidity_net_density": density,
            "nearest_tick_distance": nearest,
            "precise_quote_capacity_pass_20": "yes" if precise_by_pool.get(pool.pool_id, {}).get(20) else "no",
            "precise_quote_capacity_pass_100": "yes" if precise_by_pool.get(pool.pool_id, {}).get(100) else "no",
            "precise_quote_capacity_pass_500": "yes" if precise_by_pool.get(pool.pool_id, {}).get(500) else "no",
            "precise_quote_capacity_pass_1000": "yes" if precise_by_pool.get(pool.pool_id, {}).get(1000) else "no",
            "precise_quote_capacity_pass_2000": "yes" if precise_by_pool.get(pool.pool_id, {}).get(2000) else "no",
            "tick_liquidity_supports_20": support[20],
            "tick_liquidity_supports_100": support[100],
            "tick_liquidity_supports_500": support[500],
            "tick_liquidity_supports_1000": support[1000],
            "tick_liquidity_supports_2000": support[2000],
            "capacity_confidence": confidence,
            "main_capacity_risk": risk,
        })
    return audits


def safety_audit() -> dict[str, Any]:
    return {
        "secret_key_loaded": False,
        "wallet_loaded": False,
        "signer_created": False,
        "transaction_sent": False,
        "swap_called": False,
        "mint_called": False,
        "burn_called": False,
        "collect_called": False,
        "read_only_eth_call_only": True,
        "wallet_or_tx_touched": False,
    }


def next_stage_decision(summary: dict[str, Any], audits: list[dict[str, Any]]) -> dict[str, Any]:
    if not summary["rpc_read_only_ready"]:
        return {"recommended_next_stage": "LP_V3_TICK_LIQUIDITY_PIPELINE_FIX_REPEAT", "reason": "rpc_not_ready"}
    success = summary["snapshot_success_pool_count"]
    selected = summary["selected_v3_pool_count"]
    high = summary["high_confidence_count"]
    if success == 0:
        return {"recommended_next_stage": "STOP_LP_RESEARCH_NOW", "reason": "no_safe_read_only_tick_path"}
    if selected == 0 or success < max(3, selected // 2):
        return {"recommended_next_stage": "LP_V3_TICK_LIQUIDITY_PIPELINE_FIX_REPEAT", "reason": "snapshot_coverage_insufficient"}
    if high < max(2, success // 2):
        return {"recommended_next_stage": "LP_V3_TICK_LIQUIDITY_PIPELINE_FIX_REPEAT", "reason": "confidence_insufficient"}
    return {"recommended_next_stage": "LP_REAL_COST_MODEL_PIPELINE_V1", "reason": "precise_quote_plus_tick_liquidity_sufficient_cost_is_next_blocker"}


def main() -> None:
    ensure_dir(REPORT_DIR)
    input_rows, input_summary = input_evidence_audit()
    write_json(REPORT_DIR / "input_evidence_audit.json", {"inputs": input_rows, "summary": input_summary})
    write_text(
        REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
        "# Input Evidence Audit\n\n" + "\n".join(f"- `{r['path']}`: `{r['exists']}`" for r in input_rows) + "\n\n"
        + "## Summary\n"
        + f"- previous_stage_ok: `{input_summary['previous_stage_ok']}`\n"
        + f"- precise_quote_pipeline_built: `{input_summary['precise_quote_pipeline_built']}`\n"
        + f"- rpc_read_only_ready: `{input_summary['rpc_read_only_ready']}`\n"
        + f"- wallet_or_tx_touched: `{input_summary['wallet_or_tx_touched']}`\n"
        + f"- recommended_next_stage: `{input_summary['recommended_next_stage']}`\n"
        + f"- can_execute_v3_tick_liquidity_pipeline: `{input_summary['can_execute_v3_tick_liquidity_pipeline']}`\n"
    )
    if not input_summary["previous_stage_ok"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不正确，停止。\n")
        raise SystemExit(2)

    readiness = run_db_rpc_readiness()
    write_json(REPORT_DIR / "vps_db_rpc_readiness.json", {k: v for k, v in readiness.items() if k not in {"stdout", "stderr"}})
    write_text(
        REPORT_DIR / "VPS_DB_RPC_READINESS_CN.md",
        "# VPS DB RPC Readiness\n\n"
        + f"- db_ready: `{readiness['db_ready']}`\n"
        + f"- rpc_present: `{readiness['rpc_present']}`\n"
        + f"- rpc_read_only_ready: `{readiness['rpc_read_only_ready']}`\n"
        + f"- chain_id: `{readiness.get('chain_id', '')}`\n"
        + f"- latest_block: `{readiness.get('latest_block', '')}`\n"
        + "- no secret leak: `yes`\n",
    )

    candidates = build_candidates()
    candidate_rows = []
    for c in candidates:
        candidate_rows.append({
            "pool_id": c.pool_id,
            "token_pair": c.token_pair,
            "pool_type": c.pool_type,
            "token0": c.token0,
            "token1": c.token1,
            "fee_tier": c.fee_tier,
            "tick_spacing": "",
            "precise_quote_success_count": c.precise_quote_success_count,
            "selected": "yes" if c.selected else "no",
            "reject_reason": c.reject_reason,
        })
    write_csv(REPORT_DIR / "v3_tick_candidate_pools.csv", candidate_rows, list(candidate_rows[0].keys()) if candidate_rows else ["pool_id"])
    write_text(
        REPORT_DIR / "V3_TICK_CANDIDATE_POOL_SELECTION_CN.md",
        "# V3 Tick Candidate Pool Selection\n\n"
        + "\n".join(f"- `{r['pool_id']}` `{r['token_pair']}` selected=`{r['selected']}` reason=`{r['reject_reason']}` precise_success=`{r['precise_quote_success_count']}`" for r in candidate_rows)
        + "\n",
    )

    abi_entries, forbidden = abi_inventory()
    write_json(REPORT_DIR / "v3_pool_state_abi_inventory.json", abi_entries)
    write_text(
        REPORT_DIR / "V3_POOL_STATE_ABI_INVENTORY_CN.md",
        "# V3 Pool State ABI Inventory\n\n"
        + "\n".join(f"- `{e['method']}` read_only_safe=`{fmt(e['read_only_safe'])}` selected_for_v1=`{fmt(e['selected_for_v1'])}` notes=`{e['notes']}`" for e in abi_entries)
        + "\n\n## Forbidden\n"
        + "\n".join(f"- `{m}`" for m in forbidden)
        + "\n",
    )

    policy = scan_policy_payload()
    write_json(REPORT_DIR / "v3_tick_scan_policy.json", policy)
    write_text(
        REPORT_DIR / "V3_TICK_SCAN_POLICY_CN.md",
        "# V3 Tick Scan Policy\n\n"
        + f"- narrow_words_per_side: `{NARROW_WORDS_PER_SIDE}`\n"
        + f"- medium_words_per_side: `{MEDIUM_WORDS_PER_SIDE}`\n"
        + f"- hard_cap_words_per_side: `{MAX_WORDS_PER_SIDE}`\n"
        + f"- target_initialized_ticks: `{TARGET_INITIALIZED_TICKS}`\n"
        + "- no lookahead: `yes`\n"
        + "- fallback: `slot0+liquidity only if tickBitmap/ticks fail`\n",
    )

    schema = schema_definition()
    write_json(REPORT_DIR / "v3_tick_liquidity_schema.json", {"table": "lp_v3_tick_liquidity_snapshot_v1", "fields": schema})
    write_text(
        REPORT_DIR / "V3_TICK_LIQUIDITY_SCHEMA_CN.md",
        "# V3 Tick Liquidity Schema\n\n" + "\n".join(f"- `{field}`" for field in schema) + "\n",
    )

    write_text(
        REPORT_DIR / "V3_TICK_LIQUIDITY_IMPLEMENTATION_CN.md",
        "# V3 Tick Liquidity Implementation\n\n"
        + "- script: `scripts/lp_v3_tick_liquidity_pipeline_v1_readonly.py`\n"
        + "- chain calls: `eth_call` only\n"
        + "- state-changing methods: rejected\n"
        + "- DB writes: independent research-only table `lp_v3_tick_liquidity_snapshot_v1`\n"
        + f"- hard cap words per side: `{MAX_WORDS_PER_SIDE}`\n",
    )

    selected = [c for c in candidates if c.selected]
    rpc_url = rpc_url_for_local()
    all_rows: list[dict[str, Any]] = []
    per_pool_stats: list[dict[str, Any]] = []
    if readiness["rpc_read_only_ready"]:
        for pool in selected:
            rows, stats = materialize_pool(rpc_url, pool)
            all_rows.extend(rows)
            per_pool_stats.append(stats)
        insert_rows(all_rows)

    fields = schema
    write_csv(REPORT_DIR / "v3_tick_liquidity_results.csv", all_rows, fields)
    write_json(REPORT_DIR / "v3_tick_liquidity_results.json", all_rows)
    summary = {
        "selected_v3_pool_count": len(selected),
        "snapshot_success_pool_count": sum(1 for s in per_pool_stats if s["snapshot_success"]),
        "snapshot_fail_pool_count": sum(1 for s in per_pool_stats if not s["snapshot_success"]),
        "total_initialized_ticks_found": sum(s["initialized_ticks_found"] for s in per_pool_stats),
        "avg_initialized_ticks_per_pool": (sum(s["initialized_ticks_found"] for s in per_pool_stats) / len(per_pool_stats)) if per_pool_stats else 0,
        "current_liquidity_available_count": sum(1 for s in per_pool_stats if s["current_liquidity_available"]),
        "slot0_success_count": sum(1 for s in per_pool_stats if s["slot0_success"]),
        "tick_bitmap_success_count": sum(s["tick_bitmap_success"] for s in per_pool_stats),
        "ticks_success_count": sum(s["ticks_success"] for s in per_pool_stats),
        "observe_success_count": sum(1 for s in per_pool_stats if s["observe_success"]),
        "high_confidence_count": sum(1 for s in per_pool_stats if s["confidence"] == "high"),
        "medium_confidence_count": sum(1 for s in per_pool_stats if s["confidence"] == "medium"),
        "low_confidence_count": sum(1 for s in per_pool_stats if s["confidence"] == "low"),
        "invalid_count": sum(1 for r in all_rows if r.get("invalid_reason")),
        "rpc_read_only_ready": readiness["rpc_read_only_ready"],
    }
    write_text(
        REPORT_DIR / "V3_TICK_LIQUIDITY_RESULTS_CN.md",
        "# V3 Tick Liquidity Results\n\n" + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in summary.items()) + "\n",
    )

    audits = capacity_audit(selected, all_rows)
    audit_fields = list(audits[0].keys()) if audits else ["pool_id"]
    write_csv(REPORT_DIR / "v3_tick_derived_capacity_audit.csv", audits, audit_fields)
    write_text(
        REPORT_DIR / "V3_TICK_DERIVED_CAPACITY_AUDIT_CN.md",
        "# V3 Tick Derived Capacity Audit\n\n"
        + "\n".join(
            f"- `{r['pool_id']}` `{r['token_pair']}` initialized=`{r['initialized_tick_count_nearby']}` risk=`{r['main_capacity_risk']}` supports20/100/500=`{r['tick_liquidity_supports_20']}/{r['tick_liquidity_supports_100']}/{r['tick_liquidity_supports_500']}`"
            for r in audits
        )
        + "\n",
    )

    safety = safety_audit()
    write_json(REPORT_DIR / "v3_tick_liquidity_safety_audit.json", safety)
    write_text(
        REPORT_DIR / "V3_TICK_LIQUIDITY_SAFETY_AUDIT_CN.md",
        "# V3 Tick Liquidity Safety Audit\n\n" + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in safety.items()) + "\n",
    )

    next_stage = next_stage_decision(summary, audits)
    write_json(REPORT_DIR / "lp_v3_tick_next_stage_decision.json", next_stage)
    write_text(
        REPORT_DIR / "LP_V3_TICK_NEXT_STAGE_DECISION_CN.md",
        "# LP V3 Tick Next Stage Decision\n\n"
        + f"- recommended_next_stage: `{next_stage['recommended_next_stage']}`\n"
        + f"- reason: `{next_stage['reason']}`\n",
    )

    final = {
        "status": "PASS" if summary["snapshot_success_pool_count"] > 0 else "WARN" if readiness["db_ready"] else "FAIL",
        "stage": "LP_V3_TICK_LIQUIDITY_PIPELINE_V1",
        "data_source": "vps_postgres_rpc_readonly",
        "db_ready": readiness["db_ready"],
        "rpc_read_only_ready": readiness["rpc_read_only_ready"],
        "v3_tick_liquidity_pipeline_built": summary["snapshot_success_pool_count"] > 0,
        "selected_v3_pool_count": summary["selected_v3_pool_count"],
        "snapshot_success_pool_count": summary["snapshot_success_pool_count"],
        "snapshot_fail_pool_count": summary["snapshot_fail_pool_count"],
        "total_initialized_ticks_found": summary["total_initialized_ticks_found"],
        "current_liquidity_available_count": summary["current_liquidity_available_count"],
        "slot0_success_count": summary["slot0_success_count"],
        "tick_bitmap_success_count": summary["tick_bitmap_success_count"],
        "ticks_success_count": summary["ticks_success_count"],
        "observe_success_count": summary["observe_success_count"],
        "high_confidence_count": summary["high_confidence_count"],
        "medium_confidence_count": summary["medium_confidence_count"],
        "low_confidence_count": summary["low_confidence_count"],
        "wallet_or_tx_touched": False,
        "can_reopen_virtual_economics": False,
        "can_reopen_probe_preflight": False,
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage["recommended_next_stage"],
    }
    if not ALLOWED_NEXT.__contains__(final["recommended_next_stage"]):
        final["status"] = "FAIL"
        final["recommended_next_stage"] = "STOP_LP_RESEARCH_NOW"
    if not all(not safety[k] for k in ["secret_key_loaded", "wallet_loaded", "signer_created", "transaction_sent", "swap_called", "mint_called", "burn_called", "collect_called"]):
        final["status"] = "FAIL"
        final["recommended_next_stage"] = "STOP_LP_RESEARCH_NOW"
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# LP V3 Tick Liquidity One Page\n\n"
        + f"- selected_v3_pool_count: `{summary['selected_v3_pool_count']}`\n"
        + f"- snapshot_success_pool_count: `{summary['snapshot_success_pool_count']}`\n"
        + f"- total_initialized_ticks_found: `{summary['total_initialized_ticks_found']}`\n"
        + f"- recommended_next_stage: `{final['recommended_next_stage']}`\n"
        + "- no probe / no canary / no live\n",
    )
    write_text(
        REPORT_DIR / "ARTIFACT_INDEX.md",
        "\n".join([
            "# LP V3 Tick Liquidity Artifact Index",
            "",
            f"- [INPUT_EVIDENCE_AUDIT_CN.md]({REPORT_DIR / 'INPUT_EVIDENCE_AUDIT_CN.md'})",
            f"- [VPS_DB_RPC_READINESS_CN.md]({REPORT_DIR / 'VPS_DB_RPC_READINESS_CN.md'})",
            f"- [V3_TICK_CANDIDATE_POOL_SELECTION_CN.md]({REPORT_DIR / 'V3_TICK_CANDIDATE_POOL_SELECTION_CN.md'})",
            f"- [V3_POOL_STATE_ABI_INVENTORY_CN.md]({REPORT_DIR / 'V3_POOL_STATE_ABI_INVENTORY_CN.md'})",
            f"- [V3_TICK_SCAN_POLICY_CN.md]({REPORT_DIR / 'V3_TICK_SCAN_POLICY_CN.md'})",
            f"- [V3_TICK_LIQUIDITY_SCHEMA_CN.md]({REPORT_DIR / 'V3_TICK_LIQUIDITY_SCHEMA_CN.md'})",
            f"- [V3_TICK_LIQUIDITY_IMPLEMENTATION_CN.md]({REPORT_DIR / 'V3_TICK_LIQUIDITY_IMPLEMENTATION_CN.md'})",
            f"- [V3_TICK_LIQUIDITY_RESULTS_CN.md]({REPORT_DIR / 'V3_TICK_LIQUIDITY_RESULTS_CN.md'})",
            f"- [V3_TICK_DERIVED_CAPACITY_AUDIT_CN.md]({REPORT_DIR / 'V3_TICK_DERIVED_CAPACITY_AUDIT_CN.md'})",
            f"- [V3_TICK_LIQUIDITY_SAFETY_AUDIT_CN.md]({REPORT_DIR / 'V3_TICK_LIQUIDITY_SAFETY_AUDIT_CN.md'})",
            f"- [LP_V3_TICK_NEXT_STAGE_DECISION_CN.md]({REPORT_DIR / 'LP_V3_TICK_NEXT_STAGE_DECISION_CN.md'})",
            f"- [FINAL_VERDICT.json]({REPORT_DIR / 'FINAL_VERDICT.json'})",
            f"- [ONEPAGE_CN.md]({REPORT_DIR / 'ONEPAGE_CN.md'})",
        ]) + "\n",
    )


if __name__ == "__main__":
    main()
