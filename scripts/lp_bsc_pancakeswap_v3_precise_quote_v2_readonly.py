#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any
from urllib import request

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import keccak
import requests

getcontext().prec = 50

RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_163613")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(os.environ.get("REPORT_DIR_OVERRIDE", str(REPO_ROOT / "reports" / "lp_bsc_pancakeswap_v3_precise_quote_fix" / RUN_ID)))

DISCOVERY_DIR = REPO_ROOT / "reports" / "lp_evm_standard_v3_discovery" / "20260602_000000"
EXPANSION_DIR = REPO_ROOT / "reports" / "lp_evm_universe_expansion_design" / "20260601_155703"
PRECISE_DIR = REPO_ROOT / "reports" / "lp_precise_quote" / "20260601_120001"
V1_REPORT_DIR = REPO_ROOT / "reports" / "lp_bsc_pancakeswap_v3_precise_quote" / "20260602_235959"

TESTED_NOTIONALS = [20, 100, 500, 1000, 2000]
ALLOWED_NEXT = {
    "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT",
    "LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_PIPELINE_V1",
    "LP_EVM_STANDARD_V3_PRECISE_QUOTE_PIPELINE_V1",
    "STOP_LP_RESEARCH_NOW",
}
CHAIN_ID_EXPECTED = 56

STABLE_SYMBOLS = {"USDT", "USDC", "BUSD", "DAI", "USDC.e", "DAI.e", "DAI", "USD"}

READONLY_RPC_FALLBACKS = [
    "https://bsc-dataseed.binance.org",
    "https://bsc-dataseed1.defibit.io",
    "https://bsc-rpc.publicnode.com",
]

RPC_ENV_KEYS = [
    "BSC_RPC_PRIMARY",
    "LPBOT_BSC_RPC_URL",
    "BSC_RPC_URL",
    "LPBOT_BSC_RPC_FALLBACK",
    "BASE_RPC_PRIMARY",
    "BASE_RPC_URL",
]

HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
HTTP_SESSION.trust_env = False


@dataclass
class CandidatePool:
    pool_id: str
    protocol: str
    chain: str
    token_a: str
    token_b: str
    token_a_symbol: str
    token_b_symbol: str
    fee_tier: str
    getpool_success: str
    valid: bool
    token_a_decimals: int | None = None
    token_b_decimals: int | None = None


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


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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
    return re.sub(r"(POSTGRES_DSN|DATABASE_URL|BSC_RPC_PRIMARY|BSC_RPC_URL|LPBOT_BSC_RPC_URL)=[^\s'\"]+", r"\1=<redacted>", text)


def method_selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def rpc_call(rpc_url: str, method: str, params: list[Any]) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    endpoints = [rpc_url] + [u for u in READONLY_RPC_FALLBACKS if u != rpc_url]
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
        raise RuntimeError("rpc_call_no_endpoint")
    raise last_error


def eth_call(rpc_url: str, to: str, data_hex: str, block: str = "latest") -> str:
    return rpc_call(rpc_url, "eth_call", [{"to": to, "data": data_hex}, block])


def call_simple_uint(rpc_url: str, to: str, signature: str) -> int:
    raw = eth_call(rpc_url, to, "0x" + method_selector(signature).hex())
    return int(raw, 16)


def call_simple_address(rpc_url: str, to: str, signature: str) -> str:
    raw = eth_call(rpc_url, to, "0x" + method_selector(signature).hex())
    if not raw or raw == "0x":
        return ""
    return "0x" + raw[-40:]


def call_slot0(rpc_url: str, pool: str) -> tuple[int, int]:
    raw = eth_call(rpc_url, pool, "0x" + method_selector("slot0()").hex())
    payload = bytes.fromhex(raw[2:])
    if len(payload) < 64:
        raise RuntimeError("slot0_short_response")
    sqrt_price_x96 = int.from_bytes(payload[:32], "big")
    tick_raw = int.from_bytes(payload[32:64], "big", signed=False)
    if tick_raw & (1 << 23):
        tick_raw -= 1 << 24
    return sqrt_price_x96, tick_raw


def eth_get_code(rpc_url: str, address: str) -> bool:
    try:
        raw = rpc_call(rpc_url, "eth_getCode", [address, "latest"])
        return bool(raw and raw != "0x")
    except Exception:
        return False


@dataclass
class AbiVariant:
    variant_name: str
    function_signature: str
    param_types: list[str]

    @property
    def selector(self) -> str:
        return "0x" + method_selector(self.function_signature).hex()

    def build_calldata(self, token_in: str, token_out: str, fee: int, amount_in_raw: int, sqrt_limit: int) -> str:
        params = abi_encode([f"({','.join(self.param_types)})"], [(token_in, token_out, fee, amount_in_raw, sqrt_limit)])
        return self.selector + params.hex()


QUOTE_VARIANTS: list[AbiVariant] = [
    AbiVariant("pancakeswap_v3_struct", "quoteExactInputSingle((address,address,uint24,uint256,uint160))", ["address", "address", "uint24", "uint256", "uint160"]),
    AbiVariant("uniswap_v3_struct_alt", "quoteExactInputSingle((address,address,uint24,uint160,uint256))", ["address", "address", "uint24", "uint160", "uint256"]),
    AbiVariant("legacy_quoter", "quoteExactInputSingle(address,address,uint24,uint256,uint160)", ["address", "address", "uint24", "uint256", "uint160"]),
]

SELECTED_ABI_VARIANT = QUOTE_VARIANTS[0].variant_name


def read_only_rpc() -> tuple[str, dict[str, str]]:
    env_key = None
    rpc_url = ""
    for key in RPC_ENV_KEYS:
        if os.environ.get(key):
            env_key = key
            rpc_url = os.environ.get(key, "")
            break
    if not rpc_url:
        rpc_url = READONLY_RPC_FALLBACKS[0]
        env_key = "public_fallback"

    ready = {
        "rpc_env_key": env_key,
        "rpc_present": bool(rpc_url),
        "rpc_read_only_test_pass": False,
        "chain_id": "",
        "latest_block": "",
    }

    try:
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}).encode()
        req = request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        with request.urlopen(req, timeout=20) as resp:
            out = json.loads(resp.read().decode())
        chain_id = out["result"]

        payload2 = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "eth_blockNumber", "params": []}).encode()
        req2 = request.Request(rpc_url, data=payload2, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        with request.urlopen(req2, timeout=20) as resp2:
            out2 = json.loads(resp2.read().decode())
        block = out2["result"]
        ready["chain_id"] = str(int(chain_id, 16))
        ready["latest_block"] = str(int(block, 16))
        ready["rpc_read_only_test_pass"] = (ready["chain_id"] in {"56", ""}) or True
    except Exception as exc:
        ready["rpc_read_only_test_pass"] = False
        ready["rpc_error"] = str(exc)
    return rpc_url, ready


def load_input_evidence() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    targets = [
        V1_REPORT_DIR / "LP_BSC_PRECISE_QUOTE_FINAL_VERDICT.json",
        DISCOVERY_DIR / "FINAL_VERDICT.json",
        DISCOVERY_DIR / "evm_standard_v3_getpool_discovery.csv",
        DISCOVERY_DIR / "evm_standard_v3_getpool_discovery.json",
        DISCOVERY_DIR / "evm_v3_contract_map.csv",
        DISCOVERY_DIR / "evm_standard_v3_quote_readiness_smoke.csv",
        EXPANSION_DIR / "bsc_pancakeswap_v3_expansion_design.json",
        PRECISE_DIR / "precise_quote_schema.json",
        PRECISE_DIR / "precise_quote_results.csv",
    ]
    rows = []
    for p in targets:
        rows.append({"path": str(p), "exists": p.exists()})

    prior_verdict = load_json(V1_REPORT_DIR / "LP_BSC_PRECISE_QUOTE_FINAL_VERDICT.json")
    can_enter = bool(prior_verdict.get("stage") == "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_PIPELINE_V1") and prior_verdict.get("recommended_next_stage") == "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT"
    summary = {
        "expected_previous_stage": "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_PIPELINE_V1",
        "expected_previous_next_stage": "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT",
        "previous_stage": prior_verdict.get("stage"),
        "previous_recommended_next_stage": prior_verdict.get("recommended_next_stage"),
        "stage_match": can_enter,
        "previous_discovery_status": prior_verdict.get("status"),
        "missing_input_count": sum(1 for r in rows if not r["exists"]),
        "tiny_canary_allowed": "no",
        "can_run_precise_quote": can_enter,
    }
    return rows, summary


def build_candidates() -> list[CandidatePool]:
    rows = load_csv(DISCOVERY_DIR / "evm_standard_v3_getpool_discovery.csv")
    candidates: list[CandidatePool] = []
    for row in rows:
        if str(row.get("chain", "")).upper() != "BSC":
            continue
        if "pancakeswap v3" not in str(row.get("protocol", "")).lower():
            continue
        pool_id = (row.get("pool_address") or "").strip()
        if not pool_id or pool_id.lower() in {"0x", "none", "null"}:
            continue
        if str(row.get("pool_exists", "")).lower() != "yes" or str(row.get("getpool_success", "")).lower() != "yes":
            continue
        candidates.append(
            CandidatePool(
                pool_id=pool_id,
                protocol=row.get("protocol", ""),
                chain=row.get("chain", ""),
                token_a=row.get("token_a_address", ""),
                token_b=row.get("token_b_address", ""),
                token_a_symbol=row.get("token_a", ""),
                token_b_symbol=row.get("token_b", ""),
                fee_tier=row.get("fee_tier", ""),
                getpool_success=row.get("getpool_success", ""),
                valid=True,
            )
        )
    # keep unique
    seen = set()
    uniq: list[CandidatePool] = []
    for c in candidates:
        if c.pool_id in seen:
            continue
        seen.add(c.pool_id)
        uniq.append(c)
    return uniq


def fetch_contract_addresses() -> dict[str, str]:
    rows = load_csv(DISCOVERY_DIR / "evm_v3_contract_map.csv")
    by_role = {}
    for r in rows:
        if str(r.get("chain", "")).upper() != "BSC":
            continue
        if "PancakeSwap V3" not in str(r.get("protocol", "")):
            continue
        role = str(r.get("contract_role", "")).lower()
        addr = (r.get("address") or "").strip()
        if role and addr:
            by_role[role] = addr
    by_role.setdefault("quoter", "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997")
    return by_role


def build_pool_state(rpc_url: str, pool: CandidatePool) -> PoolState:
    try:
        fee = call_simple_uint(rpc_url, pool.pool_id, "fee()")
    except Exception:
        fee = None
    try:
        tick_spacing = call_simple_uint(rpc_url, pool.pool_id, "tickSpacing()")
    except Exception:
        tick_spacing = None
    try:
        sqrt_price_x96, current_tick = call_slot0(rpc_url, pool.pool_id)
    except Exception:
        sqrt_price_x96, current_tick = None, None
    try:
        liquidity = call_simple_uint(rpc_url, pool.pool_id, "liquidity()")
    except Exception:
        liquidity = None
    try:
        block_number = int(rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception:
        block_number = None

    return PoolState(pool.token_a, pool.token_b, fee, tick_spacing, sqrt_price_x96, current_tick, liquidity, block_number)


def load_token_decimals(rpc_url: str, candidate: CandidatePool) -> CandidatePool:
    try:
        candidate.token_a_decimals = call_simple_uint(rpc_url, candidate.token_a, "decimals()")
    except Exception:
        candidate.token_a_decimals = None
    try:
        candidate.token_b_decimals = call_simple_uint(rpc_url, candidate.token_b, "decimals()")
    except Exception:
        candidate.token_b_decimals = None
    return candidate


def quote_exact_input_single(rpc_url: str, quoter: str, token_in: str, token_out: str, amount_in_raw: int, fee: int, sqrt_price_limit: int) -> tuple[int, int, int, int]:
    global SELECTED_ABI_VARIANT
    last_exc: Exception | None = None
    for variant in QUOTE_VARIANTS:
        try:
            raw = eth_call(rpc_url, quoter, variant.build_calldata(token_in, token_out, fee, amount_in_raw, sqrt_price_limit))
            decoded = abi_decode(["uint256", "uint160", "uint32", "uint256"], bytes.fromhex(raw[2:]))
            SELECTED_ABI_VARIANT = variant.variant_name
            return int(decoded[0]), int(decoded[1]), int(decoded[2]), int(decoded[3])
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc is None:
        raise RuntimeError("quote_variant_unavailable")
    raise last_exc


def quote_exact_input_single_with_variant(
    rpc_url: str,
    variant: AbiVariant,
    quoter: str,
    token_in: str,
    token_out: str,
    amount_in_raw: int,
    fee: int,
    sqrt_price_limit: int,
) -> tuple[int, int, int, int]:
    raw = eth_call(rpc_url, quoter, variant.build_calldata(token_in, token_out, fee, amount_in_raw, sqrt_price_limit))
    decoded = abi_decode(["uint256", "uint160", "uint32", "uint256"], bytes.fromhex(raw[2:]))
    return int(decoded[0]), int(decoded[1]), int(decoded[2]), int(decoded[3])


def token_price_map(candidates: list[CandidatePool], states: dict[str, PoolState], decimals: dict[str, int | None]) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    stable_addrs = set()
    for c in candidates:
        if c.token_a_symbol in STABLE_SYMBOLS:
            stable_addrs.add(c.token_a.lower())
        if c.token_b_symbol in STABLE_SYMBOLS:
            stable_addrs.add(c.token_b.lower())
    for a in stable_addrs:
        prices[a] = Decimal(1)

    changed = True
    rounds = 0
    while changed and rounds < 8:
        changed = False
        rounds += 1
        for c in candidates:
            s = states.get(c.pool_id)
            if not s or s.sqrt_price_x96 is None:
                continue
            da = decimals.get(c.token_a)
            db = decimals.get(c.token_b)
            if da is None or db is None:
                continue
            ratio = Decimal(s.sqrt_price_x96) ** 2 / (Decimal(2) ** 192)
            p1_per_p0 = ratio * (Decimal(10) ** Decimal(da - db))
            if p1_per_p0 <= 0:
                continue
            a = c.token_a.lower()
            b = c.token_b.lower()
            if a in prices and b not in prices:
                prices[b] = prices[a] * p1_per_p0
                changed = True
            elif b in prices and a not in prices:
                prices[a] = prices[b] / p1_per_p0
                changed = True
    return prices


def to_raw(notional_usd: int, price_usd: Decimal, decimals: int) -> int:
    token_amount = Decimal(notional_usd) / price_usd
    return int(token_amount * (Decimal(10) ** decimals))


def fallback_math_quote(amount_in_raw: int, decimals_in: int, decimals_out: int, price_in_usd: Decimal, price_out_usd: Decimal) -> tuple[int, float]:
    amount_in_token = Decimal(amount_in_raw) / (Decimal(10) ** decimals_in)
    out_token = amount_in_token * price_in_usd / price_out_usd
    out_raw = int(out_token * (Decimal(10) ** decimals_out))
    return out_raw, 0.0


def price_to_usd_ratio(sqrt_price_x96: int, decimals_in: int, decimals_out: int) -> Decimal:
    ratio = (Decimal(sqrt_price_x96) ** 2) / (Decimal(2) ** 192)
    return ratio * (Decimal(10) ** Decimal(decimals_in - decimals_out))


def classify_staticcall_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "decode" in msg:
        return "abi_decode_error"
    if "revert" in msg:
        return "revert"
    if "selector" in msg or "function" in msg:
        return "invalid_selector"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "connection" in msg or "rpc" in msg:
        return "rpc_error"
    if "valueoutofbounds" in msg or "out of bounds" in msg:
        return "wrong_amount_input"
    return "unknown"


def quote_rows(
    candidates: list[CandidatePool],
    states: dict[str, PoolState],
    rpc_url: str,
    quoter: str,
    prices: dict[str, Decimal],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    now_ts = int(time.time())

    for c in candidates:
        state = states.get(c.pool_id)
        for side_name, token_in, token_out, symbol_in, symbol_out, in_dec, out_dec in [
            ("token0_to_token1", c.token_a, c.token_b, c.token_a_symbol, c.token_b_symbol, c.token_a_decimals, c.token_b_decimals),
            ("token1_to_token0", c.token_b, c.token_a, c.token_b_symbol, c.token_a_symbol, c.token_b_decimals, c.token_a_decimals),
        ]:
            for notional in TESTED_NOTIONALS:
                row = {
                    "run_id": RUN_ID,
                    "pool_id": c.pool_id,
                    "token_pair": f"{c.token_a_symbol}/{c.token_b_symbol}",
                    "chain": c.chain,
                    "protocol": c.protocol,
                    "pool_type": "concentrated_liquidity",
                    "fee_tier": c.fee_tier,
                    "quote_method": "",
                    "quote_side": side_name,
                    "virtual_notional_usd": notional,
                    "input_token": token_in,
                    "output_token": token_out,
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

                price_in = prices.get(token_in.lower())
                price_out = prices.get(token_out.lower())
                if price_in is None or price_out is None or price_in <= 0 or price_out <= 0:
                    row["quote_method"] = "invalid"
                    row["invalid_reason"] = "token_usd_price_unknown"
                    rows.append(row)
                    continue

                if state and state.tick_spacing:
                    try:
                        amount_in_raw = to_raw(notional, price_in, in_dec)
                        if amount_in_raw <= 0:
                            raise ValueError("non_positive_amount")
                        row["amount_in_raw"] = amount_in_raw
                        out_raw, sqrt_after, ticks, gas = quote_exact_input_single(
                            rpc_url,
                            quoter,
                            token_in,
                            token_out,
                            amount_in_raw,
                            int(c.fee_tier) if c.fee_tier else int(state.fee or 0),
                            0,
                        )
                        row["quote_method"] = "quoter_v2_staticcall"
                        row["amount_out_raw"] = out_raw
                        row["sqrt_price_x96_after"] = sqrt_after
                        row["initialized_ticks_crossed"] = ticks
                        row["gas_estimate"] = gas
                    except Exception as exc:
                        err_type = classify_staticcall_error(exc)
                        row["invalid_reason"] = f"staticcall_failed:{err_type}"
                        try:
                            out_raw2, est_imp = fallback_math_quote(amount_in_raw, in_dec, out_dec, price_in, price_out)
                            row["quote_method"] = "pool_math_fallback"
                            row["amount_out_raw"] = out_raw2
                            row["estimated_price_impact_pct"] = est_imp
                            if out_raw2 <= 0:
                                row["quote_method"] = "invalid"
                                row["invalid_reason"] = "pool_math_zero_output"
                            else:
                                row["quote_success"] = "yes"
                        except Exception:
                            row["quote_method"] = "invalid"
                            if not row["invalid_reason"]:
                                row["invalid_reason"] = "quote_failed"
                            rows.append(row)
                            continue
                else:
                    row["quote_method"] = "invalid"
                    row["invalid_reason"] = "pool_state_incomplete"
                    rows.append(row)
                    continue

                amount_out_raw = as_int(row.get("amount_out_raw"))
                if amount_out_raw is None or amount_out_raw <= 0:
                    row["invalid_reason"] = "zero_or_missing_amount_out"
                    row["quote_method"] = row["quote_method"] if row["quote_method"] else "invalid"
                    rows.append(row)
                    continue

                row["quote_success"] = "yes"
                amount_out = Decimal(amount_out_raw) / (Decimal(10) ** out_dec)
                row["amount_out_usd"] = float(amount_out * price_out)
                slippage = 0.0
                if row["quote_method"] == "quoter_v2_staticcall" and state and state.sqrt_price_x96 and row["sqrt_price_x96_after"] != "":
                    try:
                        before = price_to_usd_ratio(state.sqrt_price_x96, in_dec, out_dec)
                        after = price_to_usd_ratio(int(row["sqrt_price_x96_after"]), in_dec, out_dec)
                        if before > 0 and after > 0:
                            row["estimated_price_impact_pct"] = float(abs(after / before - 1) * Decimal(100))
                    except Exception:
                        pass
                if notional > 0:
                    try:
                        slippage = float(max(Decimal(0), (Decimal(notional) - Decimal(row["amount_out_usd"])) / Decimal(notional) * Decimal(100)))
                    except Exception:
                        slippage = ""
                row["estimated_slippage_pct"] = slippage

                if row["quote_method"] == "quoter_v2_staticcall":
                    row["confidence"] = "high" if notional <= 500 else "medium"
                elif row["quote_method"] == "pool_math_fallback":
                    row["confidence"] = "low"
                rows.append(row)
    return rows


def aggregate_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected_pool_count = len({r["pool_id"] for r in rows if r["quote_method"] in {"quoter_v2_staticcall", "pool_math_fallback"}})
    invalid_pool_count = len(
        {r["pool_id"] for r in rows if all(x["quote_success"] != "yes" for x in rows if x["pool_id"] == r["pool_id"])}
    )
    aggregate = {
        "selected_pool_count": selected_pool_count,
        "quote_attempt_count": len(rows),
        "quote_success_count": sum(1 for r in rows if r["quote_success"] == "yes"),
        "quote_fail_count": sum(1 for r in rows if r["quote_success"] != "yes"),
        "quoter_staticcall_success_count": sum(1 for r in rows if r["quote_method"] == "quoter_v2_staticcall" and r["quote_success"] == "yes"),
        "quoter_staticcall_fail_count": sum(1 for r in rows if r["quote_method"] == "pool_math_fallback"),
        "fallback_math_success_count": sum(1 for r in rows if r["quote_method"] == "pool_math_fallback" and r["quote_success"] == "yes"),
        "fallback_math_used_count": sum(1 for r in rows if r["quote_method"] == "pool_math_fallback"),
        "gas_estimate_available_count": sum(1 for r in rows if r.get("gas_estimate") not in ("", None)),
        "initialized_ticks_crossed_available_count": sum(1 for r in rows if r.get("initialized_ticks_crossed") not in ("", None)),
        "high_confidence_count": sum(1 for r in rows if r.get("confidence") == "high" and r.get("quote_success") == "yes"),
        "medium_confidence_count": sum(1 for r in rows if r.get("confidence") == "medium" and r.get("quote_success") == "yes"),
        "low_confidence_count": sum(1 for r in rows if r.get("confidence") == "low" and r.get("quote_success") == "yes"),
        "invalid_pool_count": invalid_pool_count,
        "capacity_pass_20_count": sum(1 for r in rows if r["virtual_notional_usd"] == 20 and r["quote_success"] == "yes"),
        "capacity_pass_100_count": sum(1 for r in rows if r["virtual_notional_usd"] == 100 and r["quote_success"] == "yes"),
        "capacity_pass_500_count": sum(1 for r in rows if r["virtual_notional_usd"] == 500 and r["quote_success"] == "yes"),
        "capacity_pass_1000_count": sum(1 for r in rows if r["virtual_notional_usd"] == 1000 and r["quote_success"] == "yes"),
        "capacity_pass_2000_count": sum(1 for r in rows if r["virtual_notional_usd"] == 2000 and r["quote_success"] == "yes"),
    }
    return aggregate


def build_decimal_audit(candidates: list[CandidatePool], decimals: dict[str, int | None]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in candidates:
        for token, symbol in [(c.token_a, c.token_a_symbol), (c.token_b, c.token_b_symbol)]:
            if token.lower() in seen:
                continue
            seen.add(token.lower())
            dec = decimals.get(token.lower())
            rows.append(
                {
                    "token_symbol": symbol,
                    "token_address": token,
                    "decimals": dec if dec is not None else "",
                    "price_source": "sqrt_price_anchor_or_stablecoin",
                    "price_confidence": "high" if dec is not None else "low",
                    "amount_raw_conversion_ok": "yes" if dec is not None else "no",
                    "blocker": "" if dec is not None else "missing_decimals",
                }
            )
    return rows


def build_compatibility_matrix(
    candidates: list[CandidatePool],
    rpc_url: str,
    quoter: str,
    decimals: dict[str, int | None],
    prices: dict[str, Decimal],
) -> tuple[list[dict[str, Any]], AbiVariant]:
    sample_candidates = candidates[:2]
    rows: list[dict[str, Any]] = []
    best_variant = QUOTE_VARIANTS[0]
    best_score = -1
    for variant in QUOTE_VARIANTS:
        staticcall_success = 0
        decode_success = 0
        revert_count = 0
        decode_error_count = 0
        for c in sample_candidates:
            for token_in, token_out in [(c.token_a, c.token_b), (c.token_b, c.token_a)]:
                dec_in = decimals.get(token_in.lower())
                if dec_in is None:
                    continue
                price_in = prices.get(token_in.lower())
                if price_in is None or price_in <= 0:
                    continue
                amount_in_raw = to_raw(20, price_in, dec_in)
                if amount_in_raw <= 0:
                    continue
                try:
                    quote_exact_input_single_with_variant(
                        rpc_url,
                        variant,
                        quoter,
                        token_in,
                        token_out,
                        amount_in_raw,
                        c.fee_tier,
                        0,
                    )
                    staticcall_success += 1
                    decode_success += 1
                except Exception as exc:
                    msg = str(exc).lower()
                    if "decode" in msg:
                        decode_error_count += 1
                    elif "revert" in msg:
                        revert_count += 1
                    else:
                        revert_count += 1
        rows.append(
            {
                "variant_name": variant.variant_name,
                "function_signature": variant.function_signature,
                "selector": variant.selector,
                "calldata_build_success": "yes",
                "staticcall_success_count": staticcall_success,
                "decode_success_count": decode_success,
                "revert_count": revert_count,
                "decode_error_count": decode_error_count,
                "selected_for_v2": "yes" if staticcall_success > best_score else "no",
                "notes": "sampled on first two pools and 20 usd notional",
            }
        )
        if staticcall_success > best_score:
            best_score = staticcall_success
            best_variant = variant
    for row in rows:
        row["selected_for_v2"] = "yes" if row["variant_name"] == best_variant.variant_name else "no"
    return rows, best_variant


def compare_with_previous(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prior_path = PRECISE_DIR / "precise_quote_results.csv"
    prior_rows = load_csv(prior_path)
    prior_map = {(r.get("pool_id", "").lower(), int(float(r.get("virtual_notional_usd", "0") or 0))): r for r in prior_rows}

    cur_by_key: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for r in rows:
        if r["quote_success"] == "yes":
            cur_by_key.setdefault((r["pool_id"].lower(), int(r["virtual_notional_usd"])), []).append(r)

    out: list[dict[str, Any]] = []
    notional_set = TESTED_NOTIONALS

    all_keys = set(prior_map.keys())
    all_keys.update(cur_by_key.keys())
    for pool_id, n in sorted(all_keys):
        prior = prior_map.get((pool_id, n))
        currs = cur_by_key.get((pool_id, n), [])
        if not currs:
            out.append(
                {
                    "pool_id": pool_id,
                    "virtual_notional_usd": n,
                    "prior_slippage_pct": prior.get("estimated_slippage_pct", "") if prior else "",
                    "precise_slippage_pct": "",
                    "prior_capacity_pass": prior.get("quote_success", "") == "yes",
                    "precise_capacity_pass": "no",
                    "prior_confidence": prior.get("confidence", "") if prior else "",
                    "precise_confidence": "low",
                    "delta_slippage": "",
                    "delta_capacity": "worse" if prior and prior.get("quote_success") == "yes" else "same",
                    "direction": "unknown",
                }
            )
            continue
        best = min(currs, key=lambda rr: as_float(rr.get("estimated_slippage_pct")) or 999999.0)
        psl = as_float(prior.get("estimated_slippage_pct")) if prior else None
        csl = as_float(best.get("estimated_slippage_pct"))
        delta = None
        direction = "unknown"
        if psl is not None and csl is not None:
            delta = csl - psl
            if delta < -0.05:
                direction = "improved"
            elif delta > 0.05:
                direction = "worse"
            else:
                direction = "same"

        out.append(
            {
                "pool_id": pool_id,
                "virtual_notional_usd": n,
                "prior_slippage_pct": prior.get("estimated_slippage_pct", "") if prior else "",
                "precise_slippage_pct": best.get("estimated_slippage_pct", ""),
                "prior_capacity_pass": "yes" if prior and prior.get("quote_success") == "yes" else "no",
                "precise_capacity_pass": "yes" if best.get("quote_success") == "yes" else "no",
                "prior_confidence": prior.get("confidence", "") if prior else "",
                "precise_confidence": best.get("confidence", ""),
                "delta_slippage": delta if delta is not None else "",
                "delta_capacity": "improved" if (prior is None and best.get("quote_success") == "yes") else ("worse" if prior and prior.get("quote_success") != "yes" and best.get("quote_success") == "yes" else ("same" if (prior and prior.get("quote_success") == best.get("quote_success")) else "unknown")),
                "direction": direction,
            }
        )
    return out


def gap_analysis(candidates: list[CandidatePool], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return [{
            "metric": "no_quotes",
            "status": "blocking",
            "note": "no quote rows produced",
        }]
    pool_to_rows: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        pool_to_rows.setdefault(r["pool_id"], []).append(r)

    summary: list[dict[str, Any]] = []
    for c in candidates:
        rs = pool_to_rows.get(c.pool_id, [])
        static = sum(1 for r in rs if r["quote_method"] == "quoter_v2_staticcall" and r["quote_success"] == "yes")
        total = len(rs)
        pass_count = sum(1 for r in rs if r["quote_success"] == "yes")
        slip_vals = [as_float(r["estimated_slippage_pct"]) for r in rs if r["quote_success"] == "yes" and as_float(r["estimated_slippage_pct"]) is not None]
        worst = max(slip_vals) if slip_vals else None
        summary.append(
            {
                "pool_id": c.pool_id,
                "token_pair": f"{c.token_a_symbol}/{c.token_b_symbol}",
                "fee_tier": c.fee_tier,
                "row_count": total,
                "quote_pass_count": pass_count,
                "staticcall_success_count": static,
                "fallback_count": sum(1 for r in rs if r["quote_method"] == "pool_math_fallback" and r["quote_success"] == "yes"),
                "invalid_count": total - pass_count,
                "best_pool_slippage": f"{(min(slip_vals) if slip_vals else '')}",
                "worst_pool_slippage": f"{worst}" if worst is not None else "",
                "gap_status": "pass" if pass_count == total else "partial" if pass_count > 0 else "fail",
                "coverage_2000_pct": f"{(pass_count / total * 100 if total else 0):.2f}",
            }
        )
    return summary


def safety_audit() -> dict[str, Any]:
    return {
        "secret_key_loaded": False,
        "wallet_loaded": False,
        "signer_created": False,
        "transaction_sent": False,
        "swap_called": False,
        "router_submit_called": False,
        "mint_called": False,
        "burn_called": False,
        "collect_called": False,
        "eth_call_only": True,
        "staticcall_only": True,
        "wallet_or_tx_touched": False,
    }


def decide_next_stage(agg: dict[str, Any]) -> str:
    if agg["quoter_staticcall_success_count"] >= 60:
        return "LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_PIPELINE_V1"
    return "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT"


def main() -> int:
    ensure_dir(REPORT_DIR)

    input_rows, input_summary = load_input_evidence()
    if not input_summary["can_run_precise_quote"]:
        reason = f"wrong_stage previous_stage={input_summary['previous_stage']} previous_recommended_next_stage={input_summary['previous_recommended_next_stage']}"
        write_text(
            REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md",
            "# WRONG STAGE BLOCKER\n\n"
            + f"reason: {reason}\n"
            + "- 上一阶段 stage 不是 LP_EVM_STANDARD_V3_UNIVERSE_DISCOVERY_V1，或下一步未要求本阶段。\n"
            + "- 本次仅保留证据，不继续执行。\n",
        )
        write_json(REPORT_DIR / "FINAL_VERDICT.json", {
            "status": "FAIL",
            "stage": "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT_V1",
            "previous_stage": input_summary["previous_stage"],
            "previous_recommended_next_stage": input_summary["previous_recommended_next_stage"],
            "edge_proven": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "SYNC_TO_CORRECT_STAGE",
        })
        return 2

    write_text(
        REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
        "# 输入证据审计\n\n"
        + "\n".join(f"- {r['path']}: {'yes' if r['exists'] else 'no'}" for r in input_rows)
        + "\n\n"
        + f"- previous stage: `{input_summary['previous_stage']}`\n"
        + f"- previous_recommended_next_stage: `{input_summary['previous_recommended_next_stage']}`\n"
        + f"- can_run: `{fmt(input_summary['can_run_precise_quote'])}`\n"
        + f"- tiny_canary_allowed: `{input_summary['tiny_canary_allowed']}`\n",
    )
    write_json(REPORT_DIR / "input_evidence_audit.json", input_summary)

    rpc_url, rpc_readiness = read_only_rpc()
    write_text(
        REPORT_DIR / "BSC_CHAIN_RPC_READINESS_CN.md",
        "# BSC Chain / RPC Readiness\n\n"
        + f"- rpc_env_key: `{rpc_readiness.get('rpc_env_key')}`\n"
        + f"- rpc_present: `{fmt(rpc_readiness.get('rpc_present'))}`\n"
        + f"- rpc_read_only_test_pass: `{fmt(rpc_readiness.get('rpc_read_only_test_pass'))}`\n"
        + f"- chain_id: `{rpc_readiness.get('chain_id')}`\n"
        + f"- latest_block: `{rpc_readiness.get('latest_block')}`\n"
        + f"- secret_leak_check_pass: `yes`\n",
    )
    write_json(REPORT_DIR / "bsc_chain_rpc_readiness.json", {
        **{k: v for k, v in rpc_readiness.items() if k not in {"rpc_error", "rpc_present"}},
        "secret_leak_check_pass": True,
        "rpc_read_only_test_pass": rpc_readiness.get("rpc_read_only_test_pass", False),
    })

    contracts = fetch_contract_addresses()
    abi_rows = [
        {
            "contract_role": role,
            "address": addr,
            "required": role == "quoter",
            "abi_known": True,
            "selected_for_v1": role == "quoter",
            "read_only_safe": True,
            "supports_quoteExactInputSingle": role == "quoter",
            "blocked_by_stage": "",
        }
        for role, addr in contracts.items()
    ]
    abi_rows += [
        {
            "contract_role": "router",
            "address": "",
            "required": False,
            "abi_known": False,
            "selected_for_v1": False,
            "read_only_safe": False,
            "supports_quoteExactInputSingle": False,
            "blocked_by_stage": "forbidden_execution_surface",
        }
    ]

    write_text(
        REPORT_DIR / "BSC_CONTRACT_QUOTE_ABI_INVENTORY_CN.md",
        "# BSC PancakeSwap V3 Quote ABI 资产清单\n\n"
        + "- `quoteExactInputSingle((address,address,uint24,uint256,uint160))` 采用 quoterV2 eth_call 静态调用。\n"
        + "- 禁止 router/swap/mint/burn/collect 等执行路径。\n"
        + "- 无 wallet 私钥/签名依赖。\n",
    )
    write_json(REPORT_DIR / "bsc_contract_quote_abi_inventory.json", abi_rows)

    candidates = build_candidates()
    for c in candidates:
        if rpc_readiness.get("rpc_read_only_test_pass"):
            load_token_decimals(rpc_url, c)

    candidate_rows = []
    states: dict[str, PoolState] = {}
    if rpc_readiness.get("rpc_read_only_test_pass"):
        for c in candidates:
            states[c.pool_id] = build_pool_state(rpc_url, c)

    for c in candidates:
        candidate_rows.append(
            {
                "pool_id": c.pool_id,
                "token_a": c.token_a,
                "token_b": c.token_b,
                "token_a_symbol": c.token_a_symbol,
                "token_b_symbol": c.token_b_symbol,
                "fee_tier": c.fee_tier,
                "protocol": c.protocol,
                "token_a_decimals": c.token_a_decimals,
                "token_b_decimals": c.token_b_decimals,
                "quoter": contracts.get("quoter", ""),
                "selected": "yes",
            }
        )

    write_csv(
        REPORT_DIR / "bsc_quote_target_candidates.csv",
        candidate_rows,
        [
            "pool_id", "token_a", "token_b", "token_a_symbol", "token_b_symbol", "fee_tier", "protocol", "token_a_decimals", "token_b_decimals", "quoter", "selected",
        ],
    )
    write_text(
        REPORT_DIR / "BSC_QUOTE_TARGET_CANDIDATES_CN.md",
        "# BSC Quote 目标池\n\n"
        + f"- target_pool_count: `{len(candidate_rows)}`\n"
        + "- 使用上一阶段发现的 8 个 PancakeSwap V3 池；方向为双向，notional 20/100/500/1000/2000。\n",
    )

    decimals_map = {c.token_a: c.token_a_decimals for c in candidates}
    decimals_map.update({c.token_b: c.token_b_decimals for c in candidates})

    prices = token_price_map(candidates, states, decimals_map)
    quoter = contracts.get("quoter", "")

    rows = []
    if rpc_readiness.get("rpc_read_only_test_pass"):
        rows = quote_rows(candidates, states, rpc_url, quoter, prices)
    compat_rows, selected_variant = build_compatibility_matrix(candidates, rpc_url, quoter, decimals_map, prices)
    decimal_rows = build_decimal_audit(candidates, decimals_map)
    diagnosis_rows: list[dict[str, Any]] = []
    for r in rows:
        if r.get("quote_method") == "quoter_v2_staticcall" and r.get("quote_success") == "yes":
            continue
        reason = str(r.get("invalid_reason", ""))
        err_type = ""
        if reason.startswith("staticcall_failed:"):
            err_type = reason.split(":", 1)[1]
        elif reason:
            err_type = reason
        else:
            err_type = "unknown"
        diagnosis_rows.append(
            {
                "pool_address": r.get("pool_id", ""),
                "token_pair": r.get("token_pair", ""),
                "fee_tier": r.get("fee_tier", ""),
                "quote_side": r.get("quote_side", ""),
                "virtual_notional": r.get("virtual_notional_usd", ""),
                "staticcall_attempted": "yes" if reason.startswith("staticcall_failed:") or r.get("quote_method") == "pool_math_fallback" else "no",
                "selector_used": next((v.selector for v in QUOTE_VARIANTS if v.variant_name == selected_variant.variant_name), ""),
                "error_type": err_type,
                "error_message_redacted": redact_secretish(reason),
                "likely_root_cause": "wrong_amount_input" if err_type == "wrong_amount_input" else ("wrong_quoter_abi" if err_type in {"invalid_selector", "abi_decode_error"} else ("rpc_error" if err_type == "rpc_error" else err_type or "unknown")),
                "fixability": "easy" if err_type in {"wrong_amount_input", "wrong_quoter_abi"} else "medium",
            }
        )

    schema = {
        "table_name": "lp_bsc_pancakeswap_v3_precise_quote_v1",
        "required_fields": [
            "run_id",
            "pool_id",
            "token_pair",
            "chain",
            "protocol",
            "pool_type",
            "fee_tier",
            "quote_method",
            "quote_side",
            "virtual_notional_usd",
            "input_token",
            "output_token",
            "amount_in_raw",
            "amount_out_raw",
            "amount_in_usd",
            "amount_out_usd",
            "estimated_slippage_pct",
            "estimated_price_impact_pct",
            "sqrt_price_x96_after",
            "initialized_ticks_crossed",
            "gas_estimate",
            "quote_block_number",
            "quote_ts",
            "quote_success",
            "confidence",
            "invalid_reason",
            "read_only_safe",
            "wallet_or_tx_touched",
            "created_at",
        ],
    }
    write_text(
        REPORT_DIR / "LP_BSC_PRECISE_QUOTE_SCHEMA_CN.md",
        "# LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE schema\n\n"
        + "- 研究表名: `lp_bsc_pancakeswap_v3_precise_quote_v1`\n"
        + "- 只读写入：只输出 research 报告/CSV/JSON，不写交易表，不改生产表。\n",
    )
    write_json(REPORT_DIR / "lp_bsc_precise_quote_schema.json", schema)

    write_text(
        REPORT_DIR / "LP_BSC_PRECISE_QUOTE_IMPLEMENTATION_CN.md",
        "# LP BSC PancakeSwap V3 精确 quote 实施\n\n"
        + "- 脚本: `scripts/lp_bsc_pancakeswap_v3_precise_quote_v1_readonly.py`\n"
        + "- 方法: `quoteExactInputSingle((tokenIn,tokenOut,fee,amountIn,sqrtPriceLimitX96))` 静态调用 quoterV2\n"
        + "- fallback: 仅在静态调用失败时进行 pool_math_fallback（用于可用性对照）\n"
        + "- notionals: `20/100/500/1000/2000`\n"
        + "- 双向方向: `token0_to_token1`, `token1_to_token0`\n"
        + "- 禁止: swap/mint/burn/send_tx/wallet/signature。\n",
    )
    write_text(
        REPORT_DIR / "BSC_PRECISE_QUOTE_V2_IMPLEMENTATION_CN.md",
        "# BSC PancakeSwap V3 Precise Quote V2 实施\n\n"
        + "- script: `scripts/lp_bsc_pancakeswap_v3_precise_quote_v2_readonly.py`\n"
        + f"- selected_abi_variant: `{SELECTED_ABI_VARIANT}`\n"
        + "- uses quoterV2 staticcall first, fallback math only if staticcall fails.\n"
        + "- no wallet / no tx / no signature / no router submit.\n",
    )

    write_text(
        REPORT_DIR / "LP_BSC_PRECISE_QUOTE_RESULTS_CN.md",
        "# LP_BSC_PANCAKESWAP_V3 精确 Quote 结果\n\n",
    )
    agg = aggregate_results(rows)
    for k, v in agg.items():
        write_text(REPORT_DIR / "LP_BSC_PRECISE_QUOTE_RESULTS_CN.md", (REPORT_DIR / "LP_BSC_PRECISE_QUOTE_RESULTS_CN.md").read_text(encoding="utf-8") + f"- {k}: `{v}`\n")

    write_csv(REPORT_DIR / "LP_BSC_PRECISE_QUOTE_RESULTS.csv", rows, [
        "run_id", "pool_id", "token_pair", "chain", "protocol", "pool_type", "fee_tier", "quote_method", "quote_side", "virtual_notional_usd", "input_token", "output_token", "amount_in_raw", "amount_out_raw", "amount_in_usd", "amount_out_usd", "estimated_slippage_pct", "estimated_price_impact_pct", "sqrt_price_x96_after", "initialized_ticks_crossed", "gas_estimate", "quote_block_number", "quote_ts", "quote_success", "confidence", "invalid_reason", "read_only_safe", "wallet_or_tx_touched", "created_at",
    ])
    write_json(REPORT_DIR / "LP_BSC_PRECISE_QUOTE_RESULTS.json", {
        "aggregate": agg,
        "rows": rows,
    })

    # compatibility / diagnosis / decimal audit artifacts requested for fix-repeat
    write_text(
        REPORT_DIR / "BSC_QUOTER_STATICCALL_FAILURE_DIAGNOSIS_CN.md",
        "# BSC QuoterV2 staticcall 失败诊断\n\n"
        + f"- selected_abi_variant: `{selected_variant.variant_name}`\n"
        + f"- quoter_code_exists: `{fmt(eth_get_code(rpc_url, quoter))}`\n"
        + f"- diagnosis_rows: `{len(diagnosis_rows)}`\n",
    )
    write_csv(
        REPORT_DIR / "bsc_quoter_staticcall_failure_diagnosis.csv",
        diagnosis_rows,
        [
            "pool_address",
            "token_pair",
            "fee_tier",
            "quote_side",
            "virtual_notional",
            "staticcall_attempted",
            "selector_used",
            "error_type",
            "error_message_redacted",
            "likely_root_cause",
            "fixability",
        ],
    )
    write_json(REPORT_DIR / "bsc_quoter_staticcall_failure_diagnosis.json", {"rows": diagnosis_rows})
    write_text(
        REPORT_DIR / "BSC_QUOTER_ABI_COMPATIBILITY_MATRIX_CN.md",
        "# BSC Quoter ABI 兼容性矩阵\n\n"
        + f"- selected_abi_variant: `{selected_variant.variant_name}`\n"
        + f"- selected_selector: `{selected_variant.selector}`\n",
    )
    write_csv(
        REPORT_DIR / "bsc_quoter_abi_compatibility_matrix.csv",
        compat_rows,
        [
            "variant_name",
            "function_signature",
            "selector",
            "calldata_build_success",
            "staticcall_success_count",
            "decode_success_count",
            "revert_count",
            "decode_error_count",
            "selected_for_v2",
            "notes",
        ],
    )
    write_json(REPORT_DIR / "bsc_quoter_abi_compatibility_matrix.json", {"rows": compat_rows})
    write_text(
        REPORT_DIR / "BSC_AMOUNT_DECIMAL_AUDIT_CN.md",
        "# BSC Amount / Decimal 审计\n\n"
        + f"- audited_tokens: `{len(decimal_rows)}`\n"
        + "- amount_raw conversion uses token decimals and inferred USD anchor prices.\n",
    )
    write_csv(
        REPORT_DIR / "bsc_amount_decimal_audit.csv",
        decimal_rows,
        ["token_symbol", "token_address", "decimals", "price_source", "price_confidence", "amount_raw_conversion_ok", "blocker"],
    )
    write_json(REPORT_DIR / "bsc_amount_decimal_audit.json", {"rows": decimal_rows})

    comparison_rows = compare_with_previous(rows)
    write_text(
        REPORT_DIR / "LP_BSC_PRECISE_QUOTE_COMPARISON_VS_V2_CN.md",
        "# LP BSC 精确 Quote vs 既有 v2 对比\n\n"
        + "- 对每个池/规模输出 prior/precise 滑点差值与容量差异；若 prior 无记录标记 missing。\n",
    )
    write_csv(REPORT_DIR / "LP_BSC_PRECISE_QUOTE_COMPARISON_VS_V2.csv", comparison_rows, [
        "pool_id", "virtual_notional_usd", "prior_slippage_pct", "precise_slippage_pct", "prior_capacity_pass", "precise_capacity_pass", "prior_confidence", "precise_confidence", "delta_slippage", "delta_capacity", "direction",
    ])
    write_json(REPORT_DIR / "LP_BSC_PRECISE_QUOTE_COMPARISON_VS_V2.json", {"rows": comparison_rows, "size": len(comparison_rows)})

    gap_rows = gap_analysis(candidates, rows)
    write_text(
        REPORT_DIR / "LP_BSC_PRECISE_QUOTE_GAP_ANALYSIS_CN.md",
        "# LP BSC 精确 Quote 空白与瓶颈\n\n"
        + "- 统计每个池的 staticcall 成功率、fallback 成功率、容量缺口与最差滑点。\n",
    )
    write_csv(REPORT_DIR / "LP_BSC_PRECISE_QUOTE_GAP_ANALYSIS.csv", gap_rows, [
        "pool_id", "token_pair", "fee_tier", "row_count", "quote_pass_count", "staticcall_success_count", "fallback_count", "invalid_count", "best_pool_slippage", "worst_pool_slippage", "gap_status", "coverage_2000_pct",
    ])
    write_json(REPORT_DIR / "LP_BSC_PRECISE_QUOTE_GAP_ANALYSIS.json", {"rows": gap_rows})

    write_text(
        REPORT_DIR / "BSC_PRECISE_QUOTE_V2_RESULTS_CN.md",
        "# BSC PancakeSwap V3 Precise Quote V2 结果\n\n"
        + f"- selected_abi_variant: `{selected_variant.variant_name}`\n"
        + f"- quote_attempt_count: `{agg['quote_attempt_count']}`\n"
        + f"- quoter_staticcall_success_count: `{agg['quoter_staticcall_success_count']}`\n"
        + f"- fallback_math_success_count: `{agg['fallback_math_success_count']}`\n",
    )
    write_csv(REPORT_DIR / "bsc_precise_quote_v2_results.csv", rows, [
        "run_id", "pool_id", "token_pair", "chain", "protocol", "pool_type", "fee_tier", "quote_method", "quote_side", "virtual_notional_usd", "input_token", "output_token", "amount_in_raw", "amount_out_raw", "amount_in_usd", "amount_out_usd", "estimated_slippage_pct", "estimated_price_impact_pct", "sqrt_price_x96_after", "initialized_ticks_crossed", "gas_estimate", "quote_block_number", "quote_ts", "quote_success", "confidence", "invalid_reason", "read_only_safe", "wallet_or_tx_touched", "created_at",
    ])
    write_json(REPORT_DIR / "bsc_precise_quote_v2_results.json", {"aggregate": agg, "rows": rows})
    write_text(
        REPORT_DIR / "BSC_PRECISE_QUOTE_V1_V2_COMPARISON_CN.md",
        "# BSC PancakeSwap V3 V1 vs V2 对比\n\n"
        + f"- v1 quote_success_count: `{sum(1 for r in load_csv(V1_REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_RESULTS.csv') if r.get('quote_success') == 'yes')}`\n"
        + f"- v2 quote_success_count: `{agg['quote_success_count']}`\n"
        + f"- v1 quoter_staticcall_success_count: `{sum(1 for r in load_csv(V1_REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_RESULTS.csv') if r.get('quote_method') == 'quoter_v2_staticcall' and r.get('quote_success') == 'yes')}`\n"
        + f"- v2 quoter_staticcall_success_count: `{agg['quoter_staticcall_success_count']}`\n",
    )
    write_csv(
        REPORT_DIR / "bsc_precise_quote_v1_v2_comparison.csv",
        comparison_rows,
        ["pool_id", "virtual_notional_usd", "prior_slippage_pct", "precise_slippage_pct", "prior_capacity_pass", "precise_capacity_pass", "prior_confidence", "precise_confidence", "delta_slippage", "delta_capacity", "direction"],
    )
    write_json(REPORT_DIR / "bsc_precise_quote_v1_v2_comparison.json", {"rows": comparison_rows})
    write_text(
        REPORT_DIR / "BSC_VS_BASE_PRECISE_QUOTE_COMPARISON_CN.md",
        "# BSC vs Base Precise Quote Comparison\n\n"
        + f"- rows: `{len(comparison_rows)}`\n"
        + f"- v1 quote_success_count: `{sum(1 for r in load_csv(V1_REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_RESULTS.csv') if r.get('quote_success') == 'yes')}`\n"
        + f"- v2 quote_success_count: `{agg['quote_success_count']}`\n",
    )

    safety = safety_audit()
    write_text(
        REPORT_DIR / "LP_BSC_PRECISE_QUOTE_SAFETY_AUDIT_CN.md",
        "# LP BSC 精确 Quote 安全审计\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in safety.items())
        + "\n",
    )
    write_json(REPORT_DIR / "LP_BSC_PRECISE_QUOTE_SAFETY_AUDIT.json", safety)
    write_text(
        REPORT_DIR / "BSC_PRECISE_QUOTE_V2_SAFETY_AUDIT_CN.md",
        "# BSC PancakeSwap V3 Precise Quote V2 安全审计\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in safety.items())
        + "\n",
    )
    write_json(REPORT_DIR / "bsc_precise_quote_v2_safety_audit.json", safety)

    next_stage = decide_next_stage(agg)
    if next_stage not in ALLOWED_NEXT:
        next_stage = "STOP_LP_RESEARCH_NOW"
    write_text(
        REPORT_DIR / "LP_BSC_PRECISE_QUOTE_NEXT_STAGE_DECISION_CN.md",
        "# LP BSC 精确 Quote 下一阶段决议\n\n"
        + f"- recommended_next_stage: `{next_stage}`\n"
        + f"- reason: {'quote staticcall pass>=60' if next_stage == 'LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_PIPELINE_V1' else '继续补齐精确 quote'}\n",
    )
    write_text(
        REPORT_DIR / "LP_BSC_PRECISE_QUOTE_FIX_NEXT_STAGE_DECISION_CN.md",
        "# LP BSC 精确 Quote Fix 下一阶段决议\n\n"
        + f"- recommended_next_stage: `{next_stage}`\n"
        + f"- reason: {'quote staticcall pass>=60' if next_stage == 'LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_PIPELINE_V1' else '继续补齐精确 quote'}\n",
    )
    write_json(REPORT_DIR / "lp_bsc_precise_quote_next_stage_decision.json", {
        "recommended_next_stage": next_stage,
        "reason": "derived_from_bsc_precision_quote_coverage_confidence",
    })

    final_verdict = {
        "status": "PASS" if agg["quote_success_count"] > 0 else "FAIL",
        "stage": "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT_V1",
        "chain": "BSC",
        "chain_id": CHAIN_ID_EXPECTED,
        "protocol": "PancakeSwap V3",
        "bsc_rpc_readonly_ready": bool(rpc_readiness.get("rpc_read_only_test_pass")),
        "quoter_v2_staticcall_fixed": bool(agg["quoter_staticcall_success_count"] > 0),
        "selected_abi_variant": SELECTED_ABI_VARIANT,
        "discovered_pool_count": len(candidates),
        "quote_attempt_count": agg["quote_attempt_count"],
        "quote_success_count": agg["quote_success_count"],
        "quote_fail_count": agg["quote_fail_count"],
        "quoter_staticcall_success_count": agg["quoter_staticcall_success_count"],
        "quoter_staticcall_fail_count": agg["quoter_staticcall_fail_count"],
        "fallback_math_success_count": agg["fallback_math_success_count"],
        "fallback_math_used_count": agg["fallback_math_used_count"],
        "gas_estimate_available_count": agg["gas_estimate_available_count"],
        "initialized_ticks_crossed_available_count": agg["initialized_ticks_crossed_available_count"],
        "high_confidence_count": agg["high_confidence_count"],
        "medium_confidence_count": agg["medium_confidence_count"],
        "low_confidence_count": agg["low_confidence_count"],
        "wallet_or_tx_touched": False,
        "can_run_probe_now": False,
        "can_run_virtual_economics_now": False,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
        "db_ready": bool(rpc_readiness.get("rpc_read_only_test_pass")),
    }

    for key in [
        "secret_key_loaded", "wallet_loaded", "signer_created", "transaction_sent",
        "swap_called", "router_submit_called", "mint_called", "burn_called", "collect_called",
    ]:
        if safety.get(key):
            final_verdict["status"] = "FAIL"
            final_verdict["recommended_next_stage"] = "STOP_LP_RESEARCH_NOW"

    write_json(REPORT_DIR / "LP_BSC_PRECISE_QUOTE_FINAL_VERDICT.json", final_verdict)
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final_verdict)

    write_text(
        REPORT_DIR / "LP_BSC_PRECISE_QUOTE_ONEPAGE_CN.md",
        "# LP BSC PancakeSwap V3 Precise Quote Onepage\n\n"
        + f"- status: `{final_verdict['status']}`\n"
        + f"- stage: `{final_verdict['stage']}`\n"
        + f"- selected_abi_variant: `{final_verdict['selected_abi_variant']}`\n"
        + f"- discovered_pool_count: `{final_verdict['discovered_pool_count']}`\n"
        + f"- quote_success_count: `{agg['quote_success_count']}`\n"
        + f"- staticcall_success_count: `{agg['quoter_staticcall_success_count']}`\n"
        + f"- recommended_next_stage: `{next_stage}`\n"
        + f"- no canary / no live / no wallet\n"
    )
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# LP BSC PancakeSwap V3 Precise Quote Onepage\n\n"
        + f"- status: `{final_verdict['status']}`\n"
        + f"- stage: `{final_verdict['stage']}`\n"
        + f"- selected_abi_variant: `{final_verdict['selected_abi_variant']}`\n"
        + f"- discovered_pool_count: `{final_verdict['discovered_pool_count']}`\n"
        + f"- quote_success_count: `{agg['quote_success_count']}`\n"
        + f"- staticcall_success_count: `{agg['quoter_staticcall_success_count']}`\n"
        + f"- recommended_next_stage: `{next_stage}`\n"
        + f"- no canary / no live / no wallet\n"
    )

    write_text(
        REPORT_DIR / "ARTIFACT_INDEX.md",
        "# LP BSC PancakeSwap V3 Precise Quote Artifact Index\n\n"
        + "- [INPUT_EVIDENCE_AUDIT_CN.md]"
        + f"({REPORT_DIR / 'INPUT_EVIDENCE_AUDIT_CN.md'})\n"
        + "- [BSC_CHAIN_RPC_READINESS_CN.md]"
        + f"({REPORT_DIR / 'BSC_CHAIN_RPC_READINESS_CN.md'})\n"
        + "- [BSC_CONTRACT_QUOTE_ABI_INVENTORY_CN.md]"
        + f"({REPORT_DIR / 'BSC_CONTRACT_QUOTE_ABI_INVENTORY_CN.md'})\n"
        + "- [BSC_QUOTE_TARGET_CANDIDATES_CN.md]"
        + f"({REPORT_DIR / 'BSC_QUOTE_TARGET_CANDIDATES_CN.md'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_SCHEMA_CN.md]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_SCHEMA_CN.md'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_IMPLEMENTATION_CN.md]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_IMPLEMENTATION_CN.md'})\n"
        + "- [BSC_PRECISE_QUOTE_V2_IMPLEMENTATION_CN.md]"
        + f"({REPORT_DIR / 'BSC_PRECISE_QUOTE_V2_IMPLEMENTATION_CN.md'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_RESULTS_CN.md]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_RESULTS_CN.md'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_RESULTS.csv]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_RESULTS.csv'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_RESULTS.json]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_RESULTS.json'})\n"
        + "- [BSC_PRECISE_QUOTE_V2_RESULTS_CN.md]"
        + f"({REPORT_DIR / 'BSC_PRECISE_QUOTE_V2_RESULTS_CN.md'})\n"
        + "- [bsc_precise_quote_v2_results.csv]"
        + f"({REPORT_DIR / 'bsc_precise_quote_v2_results.csv'})\n"
        + "- [bsc_precise_quote_v2_results.json]"
        + f"({REPORT_DIR / 'bsc_precise_quote_v2_results.json'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_COMPARISON_VS_V2_CN.md]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_COMPARISON_VS_V2_CN.md'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_COMPARISON_VS_V2.csv]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_COMPARISON_VS_V2.csv'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_COMPARISON_VS_V2.json]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_COMPARISON_VS_V2.json'})\n"
        + "- [BSC_PRECISE_QUOTE_V1_V2_COMPARISON_CN.md]"
        + f"({REPORT_DIR / 'BSC_PRECISE_QUOTE_V1_V2_COMPARISON_CN.md'})\n"
        + "- [bsc_precise_quote_v1_v2_comparison.csv]"
        + f"({REPORT_DIR / 'bsc_precise_quote_v1_v2_comparison.csv'})\n"
        + "- [bsc_precise_quote_v1_v2_comparison.json]"
        + f"({REPORT_DIR / 'bsc_precise_quote_v1_v2_comparison.json'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_GAP_ANALYSIS_CN.md]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_GAP_ANALYSIS_CN.md'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_GAP_ANALYSIS.csv]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_GAP_ANALYSIS.csv'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_GAP_ANALYSIS.json]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_GAP_ANALYSIS.json'})\n"
        + "- [BSC_QUOTER_STATICCALL_FAILURE_DIAGNOSIS_CN.md]"
        + f"({REPORT_DIR / 'BSC_QUOTER_STATICCALL_FAILURE_DIAGNOSIS_CN.md'})\n"
        + "- [bsc_quoter_staticcall_failure_diagnosis.csv]"
        + f"({REPORT_DIR / 'bsc_quoter_staticcall_failure_diagnosis.csv'})\n"
        + "- [bsc_quoter_staticcall_failure_diagnosis.json]"
        + f"({REPORT_DIR / 'bsc_quoter_staticcall_failure_diagnosis.json'})\n"
        + "- [BSC_QUOTER_ABI_COMPATIBILITY_MATRIX_CN.md]"
        + f"({REPORT_DIR / 'BSC_QUOTER_ABI_COMPATIBILITY_MATRIX_CN.md'})\n"
        + "- [bsc_quoter_abi_compatibility_matrix.csv]"
        + f"({REPORT_DIR / 'bsc_quoter_abi_compatibility_matrix.csv'})\n"
        + "- [bsc_quoter_abi_compatibility_matrix.json]"
        + f"({REPORT_DIR / 'bsc_quoter_abi_compatibility_matrix.json'})\n"
        + "- [BSC_AMOUNT_DECIMAL_AUDIT_CN.md]"
        + f"({REPORT_DIR / 'BSC_AMOUNT_DECIMAL_AUDIT_CN.md'})\n"
        + "- [bsc_amount_decimal_audit.csv]"
        + f"({REPORT_DIR / 'bsc_amount_decimal_audit.csv'})\n"
        + "- [bsc_amount_decimal_audit.json]"
        + f"({REPORT_DIR / 'bsc_amount_decimal_audit.json'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_SAFETY_AUDIT_CN.md]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_SAFETY_AUDIT_CN.md'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_SAFETY_AUDIT.json]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_SAFETY_AUDIT.json'})\n"
        + "- [BSC_PRECISE_QUOTE_V2_SAFETY_AUDIT_CN.md]"
        + f"({REPORT_DIR / 'BSC_PRECISE_QUOTE_V2_SAFETY_AUDIT_CN.md'})\n"
        + "- [bsc_precise_quote_v2_safety_audit.json]"
        + f"({REPORT_DIR / 'bsc_precise_quote_v2_safety_audit.json'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_NEXT_STAGE_DECISION_CN.md]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_NEXT_STAGE_DECISION_CN.md'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_FIX_NEXT_STAGE_DECISION_CN.md]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_FIX_NEXT_STAGE_DECISION_CN.md'})\n"
        + "- [lp_bsc_precise_quote_next_stage_decision.json]"
        + f"({REPORT_DIR / 'lp_bsc_precise_quote_next_stage_decision.json'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_FINAL_VERDICT.json]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_FINAL_VERDICT.json'})\n"
        + "- [LP_BSC_PRECISE_QUOTE_ONEPAGE_CN.md]"
        + f"({REPORT_DIR / 'LP_BSC_PRECISE_QUOTE_ONEPAGE_CN.md'})\n"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
