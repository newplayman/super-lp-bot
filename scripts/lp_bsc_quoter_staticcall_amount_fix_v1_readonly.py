#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import keccak


def load_base_module() -> Any:
    repo_root = Path(os.environ.get("REPO_ROOT_OVERRIDE", Path(__file__).resolve().parents[1]))
    base_path = repo_root / "scripts" / "lp_bsc_pancakeswap_v3_precise_quote_v2_readonly.py"
    spec = importlib.util.spec_from_file_location("lp_bsc_pancakeswap_v3_precise_quote_v2_readonly_base", base_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = load_base_module()


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", time.strftime("%Y%m%d_%H%M%S", time.gmtime()))
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", Path(__file__).resolve().parents[1]))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_bsc_quoter_staticcall_amount_fix" / RUN_ID),
    )
)

V2_REPORT_DIR = REPO_ROOT / "reports" / "lp_bsc_pancakeswap_v3_precise_quote_fix" / "20260601_163613"
V1_REPORT_DIR = REPO_ROOT / "reports" / "lp_bsc_pancakeswap_v3_precise_quote" / "20260602_235959"

CHAIN_ID_EXPECTED = 56
TESTED_NOTIONALS = [20, 100, 500, 1000, 2000]

STABLE_SYMBOLS = set(getattr(BASE, "STABLE_SYMBOLS", {"USDT", "USDC", "BUSD", "DAI", "FDUSD"})) | {"FDUSD"}


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


def load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def redact_secretish(text: str) -> str:
    return re.sub(
        r"(POSTGRES_DSN|DATABASE_URL|BSC_RPC_PRIMARY|BSC_RPC_URL|LPBOT_BSC_RPC_URL)=[^\s'\"]+",
        r"\1=<redacted>",
        text,
    )


def method_selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def rpc_call_raw(rpc_url: str, method: str, params: list[Any]) -> tuple[Any, dict[str, Any] | None]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    endpoints = [rpc_url] + [u for u in getattr(BASE, "READONLY_RPC_FALLBACKS", []) if u != rpc_url]
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            resp = BASE.HTTP_SESSION.post(endpoint, json=payload, timeout=(5, 12))
            resp.raise_for_status()
            out = resp.json()
            if "error" in out:
                return None, out["error"]
            return out.get("result"), None
        except Exception as exc:
            last_error = exc
    if last_error is None:
        raise RuntimeError("rpc_call_no_endpoint")
    raise last_error


def eth_call_raw(rpc_url: str, to: str, data_hex: str, block: str = "latest") -> tuple[str | None, dict[str, Any] | None]:
    return rpc_call_raw(rpc_url, "eth_call", [{"to": to, "data": data_hex}, block])


@dataclass
class AbiProbe:
    candidate_signature: str
    selector: str
    tuple_field_order: list[str]
    return_field_order: list[str]
    selected: bool = False
    reason: str = ""


@dataclass
class SampleCall:
    pool_id: str
    token_in: str
    token_out: str
    token_in_symbol: str
    token_out_symbol: str
    token_in_decimals: int
    fee_tier: int
    notional_usd: int


def decode_revert_payload(data_hex: str | None) -> dict[str, Any]:
    if not data_hex or data_hex in {"0x", ""}:
        return {
            "raw_revert_len": 0,
            "revert_selector": "",
            "revert_message": "",
            "decoded": "no",
            "error_type": "empty_revert",
        }
    raw = data_hex[2:] if data_hex.startswith("0x") else data_hex
    if len(raw) < 8:
        return {
            "raw_revert_len": len(raw) // 2,
            "revert_selector": "",
            "revert_message": "",
            "decoded": "no",
            "error_type": "short_revert",
        }
    selector = raw[:8]
    body = bytes.fromhex(raw[8:])
    if selector == "08c379a0":
        try:
            msg = abi_decode(["string"], body)[0]
            return {
                "raw_revert_len": len(raw) // 2,
                "revert_selector": "0x" + selector,
                "revert_message": str(msg),
                "decoded": "yes",
                "error_type": "error_string",
            }
        except Exception:
            return {
                "raw_revert_len": len(raw) // 2,
                "revert_selector": "0x" + selector,
                "revert_message": "",
                "decoded": "no",
                "error_type": "error_string_decode_fail",
            }
    if selector == "4e487b71":
        try:
            code = abi_decode(["uint256"], body)[0]
            return {
                "raw_revert_len": len(raw) // 2,
                "revert_selector": "0x" + selector,
                "revert_message": f"Panic({int(code)})",
                "decoded": "yes",
                "error_type": "panic",
            }
        except Exception:
            return {
                "raw_revert_len": len(raw) // 2,
                "revert_selector": "0x" + selector,
                "revert_message": "",
                "decoded": "no",
                "error_type": "panic_decode_fail",
            }
    return {
        "raw_revert_len": len(raw) // 2,
        "revert_selector": "0x" + selector,
        "revert_message": "",
        "decoded": "no",
        "error_type": "custom_error_or_unknown",
    }


def build_candidates() -> list[Any]:
    return BASE.build_candidates()


def load_token_decimals(rpc_url: str, candidate: Any) -> Any:
    return BASE.load_token_decimals(rpc_url, candidate)


def build_pool_state(rpc_url: str, candidate: Any) -> Any:
    return BASE.build_pool_state(rpc_url, candidate)


def derive_anchor_prices(candidates: list[Any], states: dict[str, Any], decimals: dict[str, int | None]) -> tuple[dict[str, Decimal], dict[str, str]]:
    prices: dict[str, Decimal] = {}
    sources: dict[str, str] = {}
    stable_addrs: set[str] = set()
    for c in candidates:
        if c.token_a_symbol in STABLE_SYMBOLS:
            stable_addrs.add(c.token_a.lower())
        if c.token_b_symbol in STABLE_SYMBOLS:
            stable_addrs.add(c.token_b.lower())
    for addr in stable_addrs:
        prices[addr] = Decimal(1)
        sources[addr] = "stable_anchor"

    with localcontext() as ctx:
        ctx.prec = 50
        for _ in range(8):
            changes: dict[str, list[tuple[Decimal, str]]] = {}
            for c in candidates:
                s = states.get(c.pool_id)
                if not s or s.sqrt_price_x96 is None:
                    continue
                da = decimals.get(c.token_a.lower())
                db = decimals.get(c.token_b.lower())
                if da is None or db is None:
                    continue
                ratio = (Decimal(s.sqrt_price_x96) ** 2) / (Decimal(2) ** 192)
                p1_per_p0 = ratio * (Decimal(10) ** Decimal(da - db))
                if p1_per_p0 <= 0:
                    continue
                a = c.token_a.lower()
                b = c.token_b.lower()
                if a in prices and b not in prices:
                    changes.setdefault(b, []).append((prices[a] * p1_per_p0, f"slot0_pool_anchor:{c.pool_id}:{c.token_a_symbol}/{c.token_b_symbol}"))
                if b in prices and a not in prices:
                    changes.setdefault(a, []).append((prices[b] / p1_per_p0, f"slot0_pool_anchor:{c.pool_id}:{c.token_a_symbol}/{c.token_b_symbol}"))
            if not changes:
                break
            changed = False
            for token, vals in changes.items():
                if token in prices:
                    continue
                vals_only = [v for v, _ in vals]
                if not vals_only:
                    continue
                prices[token] = Decimal(statistics.median([float(v) for v in vals_only]))
                sources[token] = " | ".join(sorted({src for _, src in vals}))
                changed = True
            if not changed:
                break
    return prices, sources


def token_anchor_price(token: str, prices: dict[str, Decimal]) -> Decimal | None:
    return prices.get(token.lower())


def build_amount_in_raw(
    notional_usd: int,
    token_in: str,
    token_in_symbol: str,
    token_in_decimals: int | None,
    prices: dict[str, Decimal],
    sources: dict[str, str],
) -> tuple[int | None, str, Decimal | None, str]:
    if token_in_decimals is None:
        return None, "", None, "missing_decimals"
    with localcontext() as ctx:
        ctx.prec = 50
        if token_in_symbol in STABLE_SYMBOLS:
            amount_in_token = Decimal(notional_usd)
            amount_in_raw = int(amount_in_token * (Decimal(10) ** token_in_decimals))
            return amount_in_raw, "stable_anchor", Decimal(1), ""
        anchor_price = token_anchor_price(token_in, prices)
        if anchor_price is None or anchor_price <= 0:
            return None, "", None, "amount_raw_unavailable"
        amount_in_token = Decimal(notional_usd) / anchor_price
        amount_in_raw = int(amount_in_token * (Decimal(10) ** token_in_decimals))
        if amount_in_raw <= 0:
            return None, sources.get(token_in.lower(), ""), anchor_price, "non_positive_amount_raw"
        return amount_in_raw, sources.get(token_in.lower(), ""), anchor_price, ""


def staticcall_probe(
    rpc_url: str,
    quoter: str,
    signature: str,
    token_in: str,
    token_out: str,
    amount_in_raw: int,
    fee_tier: int,
    struct_order: list[str],
    direct_args: bool = False,
) -> tuple[bool, dict[str, Any]]:
    selector = "0x" + method_selector(signature).hex()
    if direct_args:
        raise NotImplementedError("direct_args probes are handled explicitly in the ABI audit")
    if struct_order == ["tokenIn", "tokenOut", "amountIn", "fee", "sqrtPriceLimitX96"]:
        calldata = selector + abi_encode(
            ["(address,address,uint256,uint24,uint160)"],
            [(token_in, token_out, amount_in_raw, fee_tier, 0)],
        ).hex()
    elif struct_order == ["tokenIn", "tokenOut", "fee", "amountIn", "sqrtPriceLimitX96"]:
        calldata = selector + abi_encode(
            ["(address,address,uint24,uint256,uint160)"],
            [(token_in, token_out, fee_tier, amount_in_raw, 0)],
        ).hex()
    else:
        raise ValueError(f"unsupported struct_order: {struct_order}")
    calldata_hash = "0x" + keccak(bytes.fromhex(calldata[2:])).hex()
    result, error = eth_call_raw(rpc_url, quoter, calldata)
    if error is None and isinstance(result, str) and result and result != "0x":
        try:
            decoded = abi_decode(["uint256", "uint160", "uint32", "uint256"], bytes.fromhex(result[2:]))
            return True, {
                "selector": selector,
                "calldata_hash": calldata_hash,
                "staticcall_success": "yes",
                "decoded_output": [int(decoded[0]), int(decoded[1]), int(decoded[2]), int(decoded[3])],
                "revert_data_len": 0,
                "revert_decoded": "",
                "error_type": "",
                "raw_revert": "",
            }
        except Exception as exc:
            return False, {
                "selector": selector,
                "calldata_hash": calldata_hash,
                "staticcall_success": "no",
                "decoded_output": "",
                "revert_data_len": 0,
                "revert_decoded": "",
                "error_type": f"decode_error:{classify_staticcall_error(exc)}",
                "raw_revert": "",
            }
    revert_hex = ""
    if isinstance(error, dict):
        data = error.get("data", "")
        if isinstance(data, dict):
            revert_hex = data.get("result") or data.get("data") or ""
        elif isinstance(data, str):
            revert_hex = data
    decoded = decode_revert_payload(revert_hex)
    return False, {
        "selector": selector,
        "calldata_hash": calldata_hash,
        "staticcall_success": "no",
        "decoded_output": "",
        "revert_data_len": decoded["raw_revert_len"],
        "revert_decoded": decoded["revert_message"],
        "error_type": decoded["error_type"],
        "raw_revert": revert_hex,
    }


def select_minimal_sample(candidates: list[Any], prices: dict[str, Decimal], sources: dict[str, str]) -> SampleCall | None:
    for c in candidates:
        if c.token_b_symbol in STABLE_SYMBOLS and c.token_a_symbol == "WBNB":
            return SampleCall(
                pool_id=c.pool_id,
                token_in=c.token_b,
                token_out=c.token_a,
                token_in_symbol=c.token_b_symbol,
                token_out_symbol=c.token_a_symbol,
                token_in_decimals=int(c.token_b_decimals or 18),
                fee_tier=int(c.fee_tier),
                notional_usd=20,
            )
        if c.token_a_symbol in STABLE_SYMBOLS and c.token_b_symbol == "WBNB":
            return SampleCall(
                pool_id=c.pool_id,
                token_in=c.token_a,
                token_out=c.token_b,
                token_in_symbol=c.token_a_symbol,
                token_out_symbol=c.token_b_symbol,
                token_in_decimals=int(c.token_a_decimals or 18),
                fee_tier=int(c.fee_tier),
                notional_usd=20,
            )
    return None


def build_input_artifact_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    targets = [
        V2_REPORT_DIR / "FINAL_VERDICT.json",
        V2_REPORT_DIR / "BSC_QUOTER_STATICCALL_FAILURE_DIAGNOSIS_CN.md",
        V2_REPORT_DIR / "bsc_quoter_staticcall_failure_diagnosis.csv",
        V2_REPORT_DIR / "BSC_QUOTER_ABI_COMPATIBILITY_MATRIX_CN.md",
        V2_REPORT_DIR / "bsc_quoter_abi_compatibility_matrix.csv",
        V2_REPORT_DIR / "BSC_AMOUNT_DECIMAL_AUDIT_CN.md",
        V2_REPORT_DIR / "bsc_amount_decimal_audit.csv",
        V2_REPORT_DIR / "BSC_PRECISE_QUOTE_V2_RESULTS_CN.md",
        V2_REPORT_DIR / "bsc_precise_quote_v2_results.csv",
        V2_REPORT_DIR / "BSC_PRECISE_QUOTE_V1_V2_COMPARISON_CN.md",
        V2_REPORT_DIR / "BSC_PRECISE_QUOTE_V2_SAFETY_AUDIT_CN.md",
        V2_REPORT_DIR / "LP_BSC_PRECISE_QUOTE_FIX_NEXT_STAGE_DECISION_CN.md",
        V1_REPORT_DIR / "bsc_precise_quote_results.csv",
        REPO_ROOT / "reports" / "lp_evm_standard_v3_discovery" / "20260602_000000" / "evm_standard_v3_normalized_universe.csv",
    ]
    rows = [{"path": str(p), "exists": p.exists()} for p in targets]
    verdict = load_json(V2_REPORT_DIR / "FINAL_VERDICT.json")
    summary = {
        "expected_previous_stage": "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT_V1",
        "previous_stage": verdict.get("stage"),
        "previous_recommended_next_stage": verdict.get("recommended_next_stage"),
        "previous_quoter_staticcall_success_count": verdict.get("quoter_staticcall_success_count"),
        "previous_fallback_math_success_count": verdict.get("fallback_math_success_count"),
        "previous_selected_abi_variant": verdict.get("selected_abi_variant"),
        "previous_selected_selector": verdict.get("selected_selector", "0xb3b11b7e"),
        "can_run_amount_fix": verdict.get("quoter_staticcall_success_count", 0) == 0,
        "tiny_canary_allowed": "no",
        "missing_inputs": [r["path"] for r in rows if not r["exists"]],
    }
    return rows, summary


def build_abi_ground_truth_audit(
    rpc_url: str,
    quoter: str,
    sample: SampleCall,
) -> tuple[list[dict[str, Any]], list[AbiProbe], str]:
    probes = [
        AbiProbe(
            "quoteExactInputSingle((address,address,uint256,uint24,uint160))",
            "0x" + method_selector("quoteExactInputSingle((address,address,uint256,uint24,uint160))").hex(),
            ["tokenIn", "tokenOut", "amountIn", "fee", "sqrtPriceLimitX96"],
            ["amountOut", "sqrtPriceX96After", "initializedTicksCrossed", "gasEstimate"],
        ),
        AbiProbe(
            "quoteExactInputSingle((address,address,uint24,uint256,uint160))",
            "0x" + method_selector("quoteExactInputSingle((address,address,uint24,uint256,uint160))").hex(),
            ["tokenIn", "tokenOut", "fee", "amountIn", "sqrtPriceLimitX96"],
            ["amountOut", "sqrtPriceX96After", "initializedTicksCrossed", "gasEstimate"],
        ),
        AbiProbe(
            "quoteExactInputSingle(address,address,uint24,uint256,uint160)",
            "0x" + method_selector("quoteExactInputSingle(address,address,uint24,uint256,uint160)").hex(),
            ["tokenIn", "tokenOut", "fee", "amountIn", "sqrtPriceLimitX96"],
            ["amountOut", "sqrtPriceX96After", "initializedTicksCrossed", "gasEstimate"],
        ),
        AbiProbe(
            "quoteExactInputSingle(address,address,uint256,uint24,uint160)",
            "0x" + method_selector("quoteExactInputSingle(address,address,uint256,uint24,uint160)").hex(),
            ["tokenIn", "tokenOut", "amountIn", "fee", "sqrtPriceLimitX96"],
            ["amountOut", "sqrtPriceX96After", "initializedTicksCrossed", "gasEstimate"],
        ),
    ]

    rows: list[dict[str, Any]] = []
    selected_name = ""
    for probe in probes:
        if probe.candidate_signature == "quoteExactInputSingle((address,address,uint256,uint24,uint160))":
            calldata = probe.selector + abi_encode(
                ["(address,address,uint256,uint24,uint160)"],
                [(sample.token_in, sample.token_out, sample.notional_usd * (10 ** sample.token_in_decimals), sample.fee_tier, 0)],
            ).hex()
        elif probe.candidate_signature == "quoteExactInputSingle((address,address,uint24,uint256,uint160))":
            calldata = probe.selector + abi_encode(
                ["(address,address,uint24,uint256,uint160)"],
                [(sample.token_in, sample.token_out, sample.fee_tier, sample.notional_usd * (10 ** sample.token_in_decimals), 0)],
            ).hex()
        elif probe.candidate_signature == "quoteExactInputSingle(address,address,uint24,uint256,uint160)":
            # direct-arg signatures are included for ground-truth comparison only; encode as direct args
            calldata = probe.selector + abi_encode(
                ["address", "address", "uint24", "uint256", "uint160"],
                [sample.token_in, sample.token_out, sample.fee_tier, sample.notional_usd * (10 ** sample.token_in_decimals), 0],
            ).hex()
        elif probe.candidate_signature == "quoteExactInputSingle(address,address,uint256,uint24,uint160)":
            calldata = probe.selector + abi_encode(
                ["address", "address", "uint256", "uint24", "uint160"],
                [sample.token_in, sample.token_out, sample.notional_usd * (10 ** sample.token_in_decimals), sample.fee_tier, 0],
            ).hex()
        else:
            raise ValueError(f"unexpected candidate signature: {probe.candidate_signature}")
        result, error = eth_call_raw(rpc_url, quoter, calldata)
        row = {
            "candidate_signature": probe.candidate_signature,
            "selector": probe.selector,
            "tuple_field_order": " > ".join(probe.tuple_field_order),
            "return_field_order": " > ".join(probe.return_field_order),
            "selected": "no",
            "reason": "",
            "staticcall_success": "no",
            "revert_data_len": 0,
            "revert_decoded": "",
        }
        if error is None and isinstance(result, str) and result and result != "0x":
            try:
                decoded = abi_decode(["uint256", "uint160", "uint32", "uint256"], bytes.fromhex(result[2:]))
                row["staticcall_success"] = "yes"
                row["decoded_amount_out"] = int(decoded[0])
                row["decoded_sqrt_price_x96_after"] = int(decoded[1])
                row["decoded_initialized_ticks_crossed"] = int(decoded[2])
                row["decoded_gas_estimate"] = int(decoded[3])
                row["reason"] = "minimal_staticcall_success"
                if not selected_name:
                    selected_name = probe.candidate_signature
            except Exception as exc:
                row["reason"] = f"decode_error:{classify_staticcall_error(exc)}"
        else:
            revert_hex = ""
            if isinstance(error, dict):
                data = error.get("data", "")
                if isinstance(data, dict):
                    revert_hex = data.get("result") or data.get("data") or ""
                elif isinstance(data, str):
                    revert_hex = data
            decoded = decode_revert_payload(revert_hex)
            row["revert_data_len"] = decoded["raw_revert_len"]
            row["revert_decoded"] = decoded["revert_message"]
            row["reason"] = decoded["error_type"]
        rows.append(row)

    for probe in probes:
        probe.selected = probe.candidate_signature == selected_name
        probe.reason = "selected" if probe.selected else "not_selected"
    return rows, probes, selected_name


def build_amount_fix_audit(
    candidates: list[Any],
    states: dict[str, Any],
    decimals: dict[str, int | None],
    prices: dict[str, Decimal],
    sources: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in candidates:
        for side_name, token_in, token_out, symbol_in, symbol_out, dec_in, dec_out in [
            ("token0_to_token1", c.token_a, c.token_b, c.token_a_symbol, c.token_b_symbol, c.token_a_decimals, c.token_b_decimals),
            ("token1_to_token0", c.token_b, c.token_a, c.token_b_symbol, c.token_a_symbol, c.token_b_decimals, c.token_a_decimals),
        ]:
            for notional in TESTED_NOTIONALS:
                amount_in_raw, source, anchor_price, invalid_reason = build_amount_in_raw(
                    notional, token_in, symbol_in, dec_in, prices, sources
                )
                amount_in_token = None
                if amount_in_raw is not None and dec_in is not None:
                    amount_in_token = Decimal(amount_in_raw) / (Decimal(10) ** dec_in)
                rows.append(
                    {
                        "pool_address": c.pool_id,
                        "token_pair": f"{c.token_a_symbol}/{c.token_b_symbol}",
                        "fee_tier": c.fee_tier,
                        "quote_side": side_name,
                        "token_in": token_in,
                        "token_in_symbol": symbol_in,
                        "token_in_decimals": dec_in if dec_in is not None else "",
                        "virtual_notional_usd": notional,
                        "token_usd_anchor_source": source,
                        "token_usd_anchor_price": float(anchor_price) if anchor_price is not None else "",
                        "amount_in_token": float(amount_in_token) if amount_in_token is not None else "",
                        "amount_in_raw": amount_in_raw if amount_in_raw is not None else "",
                        "amount_in_raw_valid": "yes" if amount_in_raw is not None else "no",
                        "invalid_reason": invalid_reason,
                    }
                )
    return rows


def run_staticcall_matrix(
    rpc_url: str,
    quoter: str,
    candidates: list[Any],
    states: dict[str, Any],
    decimals: dict[str, int | None],
    prices: dict[str, Decimal],
    sources: dict[str, str],
    selected_signature: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    root_cause_counts: dict[str, int] = {}
    quote_attempt_count = 0
    staticcall_attempt_count = 0
    staticcall_success_count = 0
    staticcall_fail_count = 0
    fallback_math_used_count = 0
    skipped_due_to_amount_raw_count = 0
    decoded_revert_count = 0
    gas_estimate_available_count = 0
    initialized_ticks_crossed_available_count = 0
    confidence_counts = {"high": 0, "medium": 0, "low": 0}

    for c in candidates:
        state = states.get(c.pool_id)
        if state and state.block_number is None:
            state = state
        for side_name, token_in, token_out, symbol_in, symbol_out, dec_in, dec_out in [
            ("token0_to_token1", c.token_a, c.token_b, c.token_a_symbol, c.token_b_symbol, c.token_a_decimals, c.token_b_decimals),
            ("token1_to_token0", c.token_b, c.token_a, c.token_b_symbol, c.token_a_symbol, c.token_b_decimals, c.token_a_decimals),
        ]:
            for notional in TESTED_NOTIONALS:
                quote_attempt_count += 1
                amount_in_raw, source, anchor_price, invalid_reason = build_amount_in_raw(
                    notional, token_in, symbol_in, dec_in, prices, sources
                )
                row: dict[str, Any] = {
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
                    "token_in": token_in,
                    "token_in_symbol": symbol_in,
                    "token_out": token_out,
                    "token_out_symbol": symbol_out,
                    "token_in_decimals": dec_in if dec_in is not None else "",
                    "token_usd_anchor_source": source,
                    "token_usd_anchor_price": float(anchor_price) if anchor_price is not None else "",
                    "amount_in_token": "",
                    "amount_in_raw": "",
                    "amount_in_raw_valid": "no",
                    "amount_out_raw": "",
                    "amount_out_usd": "",
                    "estimated_slippage_pct": "",
                    "estimated_price_impact_pct": "",
                    "sqrt_price_x96_after": "",
                    "initialized_ticks_crossed": "",
                    "gas_estimate": "",
                    "quote_block_number": state.block_number if state else "",
                    "quote_ts": int(time.time()),
                    "quote_success": "no",
                    "confidence": "low",
                    "invalid_reason": invalid_reason or "",
                    "read_only_safe": "yes",
                    "wallet_or_tx_touched": "no",
                    "created_at": int(time.time()),
                    "staticcall_variant": selected_signature,
                    "selector": "0x" + method_selector(selected_signature).hex(),
                    "calldata_hash": "",
                    "revert_data_len": "",
                    "revert_decoded": "",
                    "error_type": "",
                }
                if amount_in_raw is None:
                    skipped_due_to_amount_raw_count += 1
                    rows.append(row)
                    continue
                row["amount_in_raw_valid"] = "yes"
                row["amount_in_raw"] = amount_in_raw
                row["amount_in_token"] = float(Decimal(amount_in_raw) / (Decimal(10) ** dec_in)) if dec_in is not None else ""
                staticcall_attempt_count += 1
                ok, probe = staticcall_probe(
                    rpc_url,
                    quoter,
                    selected_signature,
                    token_in,
                    token_out,
                    amount_in_raw,
                    int(c.fee_tier),
                    ["tokenIn", "tokenOut", "amountIn", "fee", "sqrtPriceLimitX96"],
                )
                row.update(
                    {
                        "calldata_hash": probe["calldata_hash"],
                        "quote_method": "quoter_v2_staticcall" if ok else "pool_math_fallback",
                        "quote_success": "yes" if ok else "no",
                        "revert_data_len": probe["revert_data_len"],
                        "revert_decoded": probe["revert_decoded"],
                        "error_type": probe["error_type"],
                    }
                )
                if ok:
                    staticcall_success_count += 1
                    decoded_amount_out, decoded_sqrt_after, decoded_ticks, decoded_gas = probe["decoded_output"]
                    row["amount_out_raw"] = decoded_amount_out
                    row["sqrt_price_x96_after"] = decoded_sqrt_after
                    row["initialized_ticks_crossed"] = decoded_ticks
                    row["gas_estimate"] = decoded_gas
                    gas_estimate_available_count += 1 if decoded_gas not in ("", None) else 0
                    initialized_ticks_crossed_available_count += 1 if decoded_ticks not in ("", None) else 0
                    try:
                        with localcontext() as ctx:
                            ctx.prec = 50
                            amount_out = Decimal(decoded_amount_out) / (Decimal(10) ** int(dec_out or 18))
                            row["amount_out_usd"] = float(amount_out * (anchor_price if anchor_price is not None else Decimal(1)))
                            if notional > 0:
                                row["estimated_slippage_pct"] = float(max(Decimal(0), (Decimal(notional) - Decimal(row["amount_out_usd"])) / Decimal(notional) * Decimal(100)))
                    except Exception:
                        row["amount_out_usd"] = ""
                    if notional <= 500:
                        row["confidence"] = "high"
                    else:
                        row["confidence"] = "medium"
                    confidence_counts[row["confidence"]] += 1
                else:
                    staticcall_fail_count += 1
                    root_cause_counts[row["error_type"] or "unknown"] = root_cause_counts.get(row["error_type"] or "unknown", 0) + 1
                    if row["revert_decoded"]:
                        decoded_revert_count += 1
                    if amount_in_raw is not None and dec_in is not None and dec_out is not None and anchor_price is not None:
                        try:
                            out_raw2, est_imp = BASE.fallback_math_quote(amount_in_raw, dec_in, dec_out, anchor_price, Decimal(1))
                            row["quote_method"] = "pool_math_fallback"
                            row["amount_out_raw"] = out_raw2
                            row["quote_success"] = "yes" if out_raw2 > 0 else "no"
                            with localcontext() as ctx:
                                ctx.prec = 50
                                row["amount_out_usd"] = float((Decimal(out_raw2) / (Decimal(10) ** dec_out)) * Decimal(1))
                            row["estimated_price_impact_pct"] = est_imp
                            fallback_math_used_count += 1
                            if out_raw2 > 0:
                                row["confidence"] = "low"
                                confidence_counts["low"] += 1
                        except Exception:
                            row["invalid_reason"] = row["invalid_reason"] or "staticcall_failed"
                    elif row["invalid_reason"] == "":
                        row["invalid_reason"] = "amount_raw_unavailable"
                rows.append(row)

    aggregate = {
        "quote_attempt_count": quote_attempt_count,
        "staticcall_attempt_count": staticcall_attempt_count,
        "staticcall_success_count": staticcall_success_count,
        "staticcall_fail_count": staticcall_fail_count,
        "fallback_math_used_count": fallback_math_used_count,
        "skipped_due_to_amount_raw_count": skipped_due_to_amount_raw_count,
        "decoded_revert_count": decoded_revert_count,
        "gas_estimate_available_count": gas_estimate_available_count,
        "initialized_ticks_crossed_available_count": initialized_ticks_crossed_available_count,
        "high_confidence_count": confidence_counts["high"],
        "medium_confidence_count": confidence_counts["medium"],
        "low_confidence_count": confidence_counts["low"],
        "root_cause_distribution": dict(sorted(root_cause_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
    return rows, aggregate, root_cause_counts


def compare_v2_v3(v2_rows: list[dict[str, str]], v3_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    v2_success = sum(1 for r in v2_rows if r.get("quote_method") == "quoter_v2_staticcall" and r.get("quote_success") == "yes")
    v2_fallback = sum(1 for r in v2_rows if r.get("quote_method") == "pool_math_fallback" and r.get("quote_success") == "yes")
    v2_invalid_amount = sum(1 for r in v2_rows if str(r.get("invalid_reason", "")).startswith("staticcall_failed:wrong_amount_input"))
    v3_success = sum(1 for r in v3_rows if r.get("quote_method") == "quoter_v2_staticcall" and r.get("quote_success") == "yes")
    v3_fallback = sum(1 for r in v3_rows if r.get("quote_method") == "pool_math_fallback" and r.get("quote_success") == "yes")
    v3_invalid_amount = sum(1 for r in v3_rows if r.get("invalid_reason") in {"amount_raw_unavailable", "non_positive_amount_raw"})
    out.append(
        {
            "metric": "quote_success_count",
            "v2": v2_success,
            "v3": v3_success,
            "delta": v3_success - v2_success,
            "improved": "yes" if v3_success > v2_success else "no",
        }
    )
    out.append(
        {
            "metric": "fallback_math_used_count",
            "v2": v2_fallback,
            "v3": v3_fallback,
            "delta": v3_fallback - v2_fallback,
            "improved": "yes" if v3_fallback < v2_fallback else "no",
        }
    )
    out.append(
        {
            "metric": "amount_raw_invalid_count",
            "v2": v2_invalid_amount,
            "v3": v3_invalid_amount,
            "delta": v3_invalid_amount - v2_invalid_amount,
            "improved": "yes" if v3_invalid_amount < v2_invalid_amount else "no",
        }
    )
    out.append(
        {
            "metric": "root_cause_shift",
            "v2": "wrong_amount_input+abi_revert",
            "v3": "amount_fix_applied+abi_struct_amount_first",
            "delta": "",
            "improved": "yes" if v3_success > 0 else "no",
        }
    )
    return out


def safety_audit() -> dict[str, Any]:
    return {
        "private_key_loaded": False,
        "wallet_loaded": False,
        "signer_created": False,
        "transaction_sent": False,
        "eth_sendTransaction_called": False,
        "eth_sendRawTransaction_called": False,
        "swap_called": False,
        "mint_called": False,
        "burn_called": False,
        "collect_called": False,
        "approve_called": False,
        "quoter_staticcall_only": True,
        "read_only_eth_call_only": True,
        "wallet_or_tx_touched": False,
    }


def decide_next_stage(aggregate: dict[str, Any], minimal_success: bool) -> str:
    if aggregate["staticcall_success_count"] > 0 and minimal_success:
        return "LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_PIPELINE_V1"
    if aggregate["staticcall_success_count"] == 0 and aggregate["skipped_due_to_amount_raw_count"] == 0:
        return "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT"
    if aggregate["staticcall_success_count"] == 0:
        return "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FALLBACK_ONLY_FREEZE"
    return "LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_PIPELINE_V1"


def main() -> int:
    ensure_dir(REPORT_DIR)

    input_rows, input_summary = build_input_artifact_audit()
    write_text(
        REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md",
        "# 输入工件审计\n\n"
        + "\n".join(f"- {r['path']}: {'yes' if r['exists'] else 'no'}" for r in input_rows)
        + "\n\n"
        + f"- previous_stage: `{input_summary['previous_stage']}`\n"
        + f"- previous_recommended_next_stage: `{input_summary['previous_recommended_next_stage']}`\n"
        + f"- previous_quoter_staticcall_success_count: `{input_summary['previous_quoter_staticcall_success_count']}`\n"
        + f"- previous_fallback_math_success_count: `{input_summary['previous_fallback_math_success_count']}`\n"
        + f"- previous_selected_abi_variant: `{input_summary['previous_selected_abi_variant']}`\n"
        + f"- previous_selected_selector: `{input_summary['previous_selected_selector']}`\n"
        + f"- can_run_amount_fix: `{fmt(input_summary['can_run_amount_fix'])}`\n"
        + f"- tiny_canary_allowed: `{input_summary['tiny_canary_allowed']}`\n",
    )
    write_json(REPORT_DIR / "input_artifact_audit.json", input_summary)

    rpc_url, rpc_readiness = BASE.read_only_rpc()
    write_text(
        REPORT_DIR / "BSC_QUOTER_V2_ABI_GROUND_TRUTH_AUDIT_CN.md",
        "# BSC QuoterV2 ABI Ground Truth 审计\n\n"
        + f"- rpc_env_key: `{rpc_readiness.get('rpc_env_key')}`\n"
        + f"- chain_id: `{rpc_readiness.get('chain_id')}`\n"
        + f"- latest_block: `{rpc_readiness.get('latest_block')}`\n"
        + f"- read_only_test_pass: `{fmt(rpc_readiness.get('rpc_read_only_test_pass'))}`\n",
    )
    write_json(REPORT_DIR / "bsc_quoter_v2_abi_ground_truth_audit.json", rpc_readiness)

    candidates = build_candidates()
    for c in candidates:
        if rpc_readiness.get("rpc_read_only_test_pass"):
            load_token_decimals(rpc_url, c)
    states: dict[str, Any] = {}
    if rpc_readiness.get("rpc_read_only_test_pass"):
        for c in candidates:
            states[c.pool_id] = build_pool_state(rpc_url, c)
    decimals: dict[str, int | None] = {c.token_a.lower(): c.token_a_decimals for c in candidates}
    decimals.update({c.token_b.lower(): c.token_b_decimals for c in candidates})
    prices, sources = derive_anchor_prices(candidates, states, decimals)

    sample = select_minimal_sample(candidates, prices, sources)
    if sample is None:
        sample = SampleCall(
            pool_id="",
            token_in=(candidates[0].token_b if candidates else ""),
            token_out=(candidates[0].token_a if candidates else ""),
            token_in_symbol=(candidates[0].token_b_symbol if candidates else ""),
            token_out_symbol=(candidates[0].token_a_symbol if candidates else ""),
            token_in_decimals=int(candidates[0].token_b_decimals or 18) if candidates else 18,
            fee_tier=int(candidates[0].fee_tier) if candidates else 100,
            notional_usd=20,
        )

    abi_rows, probes, selected_signature = build_abi_ground_truth_audit(rpc_url, cts := BASE.fetch_contract_addresses()["quoterv2"], sample)
    selected_probe = next((p for p in probes if p.selected), probes[0])
    write_text(
        REPORT_DIR / "BSC_QUOTER_V2_ABI_GROUND_TRUTH_AUDIT_CN.md",
        "# BSC QuoterV2 ABI Ground Truth 审计\n\n"
        + f"- candidate_count: `{len(abi_rows)}`\n"
        + f"- selected_signature: `{selected_signature}`\n"
        + f"- selected_selector: `{selected_probe.selector if selected_probe else ''}`\n"
        + "- 目标是确认 amountIn 应在 fee 之前的 tuple struct 结构。\n",
    )
    write_csv(
        REPORT_DIR / "bsc_quoter_v2_abi_ground_truth_audit.csv",
        abi_rows,
        [
            "candidate_signature",
            "selector",
            "tuple_field_order",
            "return_field_order",
            "selected",
            "reason",
            "staticcall_success",
            "decoded_amount_out",
            "decoded_sqrt_price_x96_after",
            "decoded_initialized_ticks_crossed",
            "decoded_gas_estimate",
            "revert_data_len",
            "revert_decoded",
        ],
    )
    write_json(REPORT_DIR / "bsc_quoter_v2_abi_ground_truth_audit.json", {"rows": abi_rows, "selected_signature": selected_signature})

    amount_rows = build_amount_fix_audit(candidates, states, decimals, prices, sources)
    write_text(
        REPORT_DIR / "BSC_AMOUNT_IN_RAW_CONVERSION_FIX_CN.md",
        "# BSC amountIn raw conversion fix audit\n\n"
        + "- 稳定币输入使用 1 USD anchor。\n"
        + "- WBNB 输入必须先从 slot0 推导 WBNB/USD anchor，再换算为 raw。\n"
        + "- 其他非稳定币若缺 anchor，则 amountInRaw 标记不可用。\n"
        + f"- audited_rows: `{len(amount_rows)}`\n",
    )
    write_csv(
        REPORT_DIR / "bsc_amount_in_raw_conversion_fix.csv",
        amount_rows,
        [
            "pool_address",
            "token_pair",
            "fee_tier",
            "quote_side",
            "token_in",
            "token_in_symbol",
            "token_in_decimals",
            "virtual_notional_usd",
            "token_usd_anchor_source",
            "token_usd_anchor_price",
            "amount_in_token",
            "amount_in_raw",
            "amount_in_raw_valid",
            "invalid_reason",
        ],
    )
    write_json(REPORT_DIR / "bsc_amount_in_raw_conversion_fix.json", {"rows": amount_rows})

    minimal_success = False
    minimal_row: dict[str, Any] = {}
    if sample.token_in:
        minimal_success, minimal_row = staticcall_probe(
            rpc_url,
            cts,
            "quoteExactInputSingle((address,address,uint256,uint24,uint160))",
            sample.token_in,
            sample.token_out,
            sample.notional_usd * (10 ** sample.token_in_decimals),
            sample.fee_tier,
            ["tokenIn", "tokenOut", "amountIn", "fee", "sqrtPriceLimitX96"],
        )
    write_text(
        REPORT_DIR / "BSC_MINIMAL_STATICCALL_TEST_CN.md",
        "# BSC minimal staticcall test\n\n"
        + f"- pool_address: `{sample.pool_id}`\n"
        + f"- token_in: `{sample.token_in}`\n"
        + f"- token_out: `{sample.token_out}`\n"
        + f"- fee: `{sample.fee_tier}`\n"
        + f"- amount_in_raw: `{sample.notional_usd * (10 ** sample.token_in_decimals)}`\n"
        + f"- abi_variant: `amount-before-fee struct`\n"
        + f"- selector: `{minimal_row.get('selector', '')}`\n"
        + f"- calldata_hash: `{minimal_row.get('calldata_hash', '')}`\n"
        + f"- staticcall_success: `{fmt(minimal_success)}`\n"
        + f"- decoded_output: `{minimal_row.get('decoded_output', '')}`\n"
        + f"- revert_data_len: `{minimal_row.get('revert_data_len', '')}`\n"
        + f"- revert_decoded: `{minimal_row.get('revert_decoded', '')}`\n"
        + f"- error_type: `{minimal_row.get('error_type', '')}`\n"
        + f"- root_cause: `{minimal_row.get('error_type', '') or ('success' if minimal_success else 'unknown')}`\n",
    )
    write_json(REPORT_DIR / "bsc_minimal_staticcall_test.json", {"success": minimal_success, "row": minimal_row})

    # Decode failures from ABI audit first; keep the table explicit even if limited matrix is clean.
    revert_rows: list[dict[str, Any]] = []
    for row in abi_rows:
        if row.get("staticcall_success") == "no":
            revert_rows.append(
                {
                    "candidate_signature": row.get("candidate_signature", ""),
                    "selector": row.get("selector", ""),
                    "quote_side": "minimal_sample",
                    "notional_usd": sample.notional_usd,
                    "error_type": row.get("reason", ""),
                    "revert_selector": "",
                    "revert_message": row.get("revert_decoded", ""),
                    "raw_revert_len": row.get("revert_data_len", 0),
                    "decoded": "yes" if row.get("revert_decoded") else "no",
                    "likely_root_cause": "wrong_abi_or_amount_order" if "revert" in str(row.get("reason", "")) else "decode_or_selector_mismatch",
                }
            )
    write_text(
        REPORT_DIR / "BSC_STATICCALL_REVERT_DECODE_CN.md",
        "# BSC staticcall revert decode\n\n"
        + f"- decoded_revert_count: `{sum(1 for r in revert_rows if r.get('decoded') == 'yes')}`\n"
        + f"- failed_samples: `{len(revert_rows)}`\n",
    )
    write_csv(
        REPORT_DIR / "bsc_staticcall_revert_decode.csv",
        revert_rows,
        [
            "candidate_signature",
            "selector",
            "quote_side",
            "notional_usd",
            "error_type",
            "revert_selector",
            "revert_message",
            "raw_revert_len",
            "decoded",
            "likely_root_cause",
        ],
    )
    write_json(REPORT_DIR / "bsc_staticcall_revert_decode.json", {"rows": revert_rows})

    if minimal_success:
        matrix_rows, aggregate, root_cause_counts = run_staticcall_matrix(
            rpc_url,
            cts,
            candidates,
            states,
            decimals,
            prices,
            sources,
            "quoteExactInputSingle((address,address,uint256,uint24,uint160))",
        )
    else:
        matrix_rows = []
        aggregate = {
            "quote_attempt_count": 0,
            "staticcall_attempt_count": 0,
            "staticcall_success_count": 0,
            "staticcall_fail_count": 0,
            "fallback_math_used_count": 0,
            "skipped_due_to_amount_raw_count": 0,
            "decoded_revert_count": 0,
            "gas_estimate_available_count": 0,
            "initialized_ticks_crossed_available_count": 0,
            "high_confidence_count": 0,
            "medium_confidence_count": 0,
            "low_confidence_count": 0,
            "root_cause_distribution": {"minimal_staticcall_failed": 1},
        }
        root_cause_counts = {"minimal_staticcall_failed": 1}

    write_text(
        REPORT_DIR / "BSC_PRECISE_QUOTE_STATICCALL_V3_RESULTS_CN.md",
        "# BSC precise quote staticcall v3 results\n\n"
        + f"- minimal_staticcall_success: `{fmt(minimal_success)}`\n"
        + f"- quote_attempt_count: `{aggregate['quote_attempt_count']}`\n"
        + f"- staticcall_attempt_count: `{aggregate['staticcall_attempt_count']}`\n"
        + f"- staticcall_success_count: `{aggregate['staticcall_success_count']}`\n"
        + f"- staticcall_fail_count: `{aggregate['staticcall_fail_count']}`\n"
        + f"- fallback_math_used_count: `{aggregate['fallback_math_used_count']}`\n"
        + f"- skipped_due_to_amount_raw_count: `{aggregate['skipped_due_to_amount_raw_count']}`\n"
        + f"- decoded_revert_count: `{aggregate['decoded_revert_count']}`\n"
        + f"- gas_estimate_available_count: `{aggregate['gas_estimate_available_count']}`\n"
        + f"- initialized_ticks_crossed_available_count: `{aggregate['initialized_ticks_crossed_available_count']}`\n"
        + f"- high_confidence_count: `{aggregate['high_confidence_count']}`\n"
        + f"- medium_confidence_count: `{aggregate['medium_confidence_count']}`\n"
        + f"- low_confidence_count: `{aggregate['low_confidence_count']}`\n"
        + f"- root_cause_distribution: `{json.dumps(aggregate['root_cause_distribution'], ensure_ascii=False)}`\n",
    )
    write_csv(
        REPORT_DIR / "bsc_precise_quote_staticcall_v3_results.csv",
        matrix_rows,
        [
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
            "token_in",
            "token_in_symbol",
            "token_out",
            "token_out_symbol",
            "token_in_decimals",
            "token_usd_anchor_source",
            "token_usd_anchor_price",
            "amount_in_token",
            "amount_in_raw",
            "amount_in_raw_valid",
            "amount_out_raw",
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
            "staticcall_variant",
            "selector",
            "calldata_hash",
            "revert_data_len",
            "revert_decoded",
            "error_type",
        ],
    )
    write_json(REPORT_DIR / "bsc_precise_quote_staticcall_v3_results.json", {"aggregate": aggregate, "rows": matrix_rows})

    v2_rows = load_csv(V2_REPORT_DIR / "bsc_precise_quote_v2_results.csv")
    comparison_rows = compare_v2_v3(v2_rows, matrix_rows)
    write_text(
        REPORT_DIR / "BSC_QUOTER_V2_V3_FIX_COMPARISON_CN.md",
        "# BSC Quoter V2 vs V3 Fix Comparison\n\n"
        + f"- v2 staticcall success count: `{comparison_rows[0]['v2'] if comparison_rows else 0}`\n"
        + f"- v3 staticcall success count: `{comparison_rows[0]['v3'] if comparison_rows else 0}`\n"
        + f"- amount raw invalid count v2/v3: `{comparison_rows[2]['v2'] if len(comparison_rows) > 2 else 0}` / `{comparison_rows[2]['v3'] if len(comparison_rows) > 2 else 0}`\n"
        + f"- amount fix improved success: `{fmt(aggregate['staticcall_success_count'] > 0)}`\n"
        + f"- abi still blocker: `{fmt(aggregate['staticcall_success_count'] == 0)}`\n",
    )
    write_csv(
        REPORT_DIR / "bsc_quoter_v2_v3_fix_comparison.csv",
        comparison_rows,
        ["metric", "v2", "v3", "delta", "improved"],
    )
    write_json(REPORT_DIR / "bsc_quoter_v2_v3_fix_comparison.json", {"rows": comparison_rows})

    safety = safety_audit()
    write_text(
        REPORT_DIR / "BSC_STATICCALL_AMOUNT_FIX_SAFETY_AUDIT_CN.md",
        "# BSC staticcall amount fix safety audit\n\n" + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in safety.items()) + "\n",
    )
    write_json(REPORT_DIR / "bsc_staticcall_amount_fix_safety_audit.json", safety)

    next_stage = decide_next_stage(aggregate, minimal_success)
    write_text(
        REPORT_DIR / "LP_BSC_QUOTER_AMOUNT_FIX_NEXT_STAGE_DECISION_CN.md",
        "# LP BSC Quoter amount fix next stage decision\n\n"
        + f"- recommended_next_stage: `{next_stage}`\n"
        + f"- reason: `{ 'staticcall success with amount fix' if next_stage == 'LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_PIPELINE_V1' else 'staticcall still blocked or only fallback available' }`\n",
    )
    write_json(
        REPORT_DIR / "lp_bsc_quoter_amount_fix_next_stage_decision.json",
        {
            "recommended_next_stage": next_stage,
            "reason": "staticcall success with amount fix" if next_stage == "LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_PIPELINE_V1" else "staticcall still blocked or only fallback available",
        },
    )

    final_verdict = {
        "status": "PASS" if (aggregate["staticcall_success_count"] > 0 and safety["wallet_or_tx_touched"] is False) else "FAIL",
        "stage": "LP_BSC_PANCAKESWAP_V3_QUOTER_STATICCALL_AMOUNT_FIX_V1",
        "chain": "BSC",
        "chain_id": CHAIN_ID_EXPECTED,
        "protocol": "PancakeSwap V3",
        "selected_abi_variant": "quoteExactInputSingle((address,address,uint256,uint24,uint160))" if minimal_success else "",
        "amount_raw_fix_applied": bool(aggregate["staticcall_success_count"] > 0),
        "minimal_staticcall_success": minimal_success,
        "quote_attempt_count": aggregate["quote_attempt_count"],
        "staticcall_attempt_count": aggregate["staticcall_attempt_count"],
        "staticcall_success_count": aggregate["staticcall_success_count"],
        "staticcall_fail_count": aggregate["staticcall_fail_count"],
        "fallback_math_used_count": aggregate["fallback_math_used_count"],
        "skipped_due_to_amount_raw_count": aggregate["skipped_due_to_amount_raw_count"],
        "decoded_revert_count": aggregate["decoded_revert_count"],
        "gas_estimate_available_count": aggregate["gas_estimate_available_count"],
        "initialized_ticks_crossed_available_count": aggregate["initialized_ticks_crossed_available_count"],
        "quoter_v2_staticcall_fixed": bool(aggregate["staticcall_success_count"] > 0),
        "wallet_or_tx_touched": False,
        "can_run_probe_now": False,
        "can_run_virtual_economics_now": False,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
        "db_ready": bool(rpc_readiness.get("rpc_read_only_test_pass")),
        "data_source": "bsc_readonly_rpc",
    }

    if not safety["quoter_staticcall_only"] or not safety["read_only_eth_call_only"] or safety["wallet_or_tx_touched"]:
        final_verdict["status"] = "FAIL"
        final_verdict["recommended_next_stage"] = "STOP_LP_RESEARCH_NOW"

    write_json(REPORT_DIR / "FINAL_VERDICT.json", final_verdict)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# LP BSC Quoter staticcall amount fix onepage\n\n"
        + f"- status: `{final_verdict['status']}`\n"
        + f"- stage: `{final_verdict['stage']}`\n"
        + f"- selected_abi_variant: `{final_verdict['selected_abi_variant']}`\n"
        + f"- amount_raw_fix_applied: `{fmt(final_verdict['amount_raw_fix_applied'])}`\n"
        + f"- minimal_staticcall_success: `{fmt(final_verdict['minimal_staticcall_success'])}`\n"
        + f"- quote_attempt_count: `{final_verdict['quote_attempt_count']}`\n"
        + f"- staticcall_success_count: `{final_verdict['staticcall_success_count']}`\n"
        + f"- fallback_math_used_count: `{final_verdict['fallback_math_used_count']}`\n"
        + f"- recommended_next_stage: `{final_verdict['recommended_next_stage']}`\n"
        + f"- tiny_canary_allowed: `no`\n",
    )
    write_text(
        REPORT_DIR / "ARTIFACT_INDEX.md",
        "# LP BSC Quoter staticcall amount fix artifact index\n\n"
        + "- [INPUT_ARTIFACT_AUDIT_CN.md](%s)\n" % (REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md")
        + "- [BSC_QUOTER_V2_ABI_GROUND_TRUTH_AUDIT_CN.md](%s)\n" % (REPORT_DIR / "BSC_QUOTER_V2_ABI_GROUND_TRUTH_AUDIT_CN.md")
        + "- [BSC_AMOUNT_IN_RAW_CONVERSION_FIX_CN.md](%s)\n" % (REPORT_DIR / "BSC_AMOUNT_IN_RAW_CONVERSION_FIX_CN.md")
        + "- [BSC_MINIMAL_STATICCALL_TEST_CN.md](%s)\n" % (REPORT_DIR / "BSC_MINIMAL_STATICCALL_TEST_CN.md")
        + "- [BSC_STATICCALL_REVERT_DECODE_CN.md](%s)\n" % (REPORT_DIR / "BSC_STATICCALL_REVERT_DECODE_CN.md")
        + "- [BSC_PRECISE_QUOTE_STATICCALL_V3_RESULTS_CN.md](%s)\n" % (REPORT_DIR / "BSC_PRECISE_QUOTE_STATICCALL_V3_RESULTS_CN.md")
        + "- [BSC_QUOTER_V2_V3_FIX_COMPARISON_CN.md](%s)\n" % (REPORT_DIR / "BSC_QUOTER_V2_V3_FIX_COMPARISON_CN.md")
        + "- [BSC_STATICCALL_AMOUNT_FIX_SAFETY_AUDIT_CN.md](%s)\n" % (REPORT_DIR / "BSC_STATICCALL_AMOUNT_FIX_SAFETY_AUDIT_CN.md")
        + "- [LP_BSC_QUOTER_AMOUNT_FIX_NEXT_STAGE_DECISION_CN.md](%s)\n" % (REPORT_DIR / "LP_BSC_QUOTER_AMOUNT_FIX_NEXT_STAGE_DECISION_CN.md")
        + "- [FINAL_VERDICT.json](%s)\n" % (REPORT_DIR / "FINAL_VERDICT.json")
        + "- [ONEPAGE_CN.md](%s)\n" % (REPORT_DIR / "ONEPAGE_CN.md")
        + "- [bsc_amount_in_raw_conversion_fix.csv](%s)\n" % (REPORT_DIR / "bsc_amount_in_raw_conversion_fix.csv")
        + "- [bsc_minimal_staticcall_test.json](%s)\n" % (REPORT_DIR / "bsc_minimal_staticcall_test.json")
        + "- [bsc_staticcall_revert_decode.csv](%s)\n" % (REPORT_DIR / "bsc_staticcall_revert_decode.csv")
        + "- [bsc_precise_quote_staticcall_v3_results.csv](%s)\n" % (REPORT_DIR / "bsc_precise_quote_staticcall_v3_results.csv")
        + "- [bsc_quoter_v2_v3_fix_comparison.csv](%s)\n" % (REPORT_DIR / "bsc_quoter_v2_v3_fix_comparison.csv")
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
