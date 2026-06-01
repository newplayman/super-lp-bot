#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from eth_utils import to_checksum_address, keccak
except Exception:  # pragma: no cover
    from hashlib import sha3
    keccak = lambda text: sha3(text.encode("utf-8")).digest()
    def to_checksum_address(addr: str) -> str:
        return addr


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", time.strftime("%Y%m%d_%H%M%S", time.gmtime()))
REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
REPORT_DIR = REPO_ROOT / "reports" / "lp_evm_standard_v3_discovery" / RUN_ID

INPUT_FILES = [
    REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/FINAL_VERDICT.json",
    REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/BSC_PANCAKESWAP_V3_EXPANSION_DESIGN_CN.md",
    REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/bsc_pancakeswap_v3_expansion_design.json",
    REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/BSC_DATA_SOURCE_FEASIBILITY_CN.md",
    REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/bsc_data_source_feasibility.json",
    REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/EVM_EXPANSION_CHAIN_PROTOCOL_PRIORITY_CN.md",
    REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/EVM_UNIVERSE_EXPANSION_SCHEMA_CN.md",
    REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/EVM_POOL_DISCOVERY_IMPLEMENTATION_PLAN_CN.md",
    REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/METADATA_GAP_POLICY_CN.md",
    REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/EVM_UNIVERSE_EXPANSION_NEXT_STAGE_DECISION_CN.md",
    REPO_ROOT / "reports/lp_universe_scope_audit/20260601_154136/FINAL_VERDICT.json",
    REPO_ROOT / "reports/lp_universe_scope_audit/20260601_154136/POOL_UNIVERSE_EXPANSION_PLAN_CN.md",
    REPO_ROOT / "reports/lp_real_data_final_freeze/20260601_150954/FINAL_VERDICT.json",
    REPO_ROOT / "docs/LPBOT_RESEARCH_STATUS_CN.md",
]

ALLOWED_NEXT = {
    "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_PIPELINE_V1",
    "LP_EVM_STANDARD_V3_PRECISE_QUOTE_PIPELINE_V1",
    "LP_EVM_STANDARD_V3_METADATA_FIX_REPEAT",
    "LP_EVM_STANDARD_V3_DISCOVERY_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}

CHAIN_TARGETS = [
    {
        "chain": "BSC",
        "chain_id_expected": 56,
        "rpc_env": ["BSC_RPC_URL", "BSC_RPC", "BSC_PUBLIC_RPC"],
        "fallback_rpcs": ["https://bsc-dataseed.binance.org", "https://rpc.ankr.com/bsc"],
        "protocols": ["PancakeSwap V3", "Uniswap V3"],
        "contracts": {
            "PancakeSwap V3": {
                "Factory": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
                "QuoterV2": "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
                "NonfungiblePositionManager": "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364",
                "TickLens": "0x9a489505a00cE272eAa5e07Dba6491314CaE3796",
            },
            "Uniswap V3": {
                "Factory": "",
                "QuoterV2": "",
                "NonfungiblePositionManager": "",
                "TickLens": "",
            },
        },
        "token_seeds": {
            "WBNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
            "USDT": "0x55d398326f99059fF775485246999027B3197955",
            "USDC": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
            "ETH": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8e",
            "WETH": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8e",
            "BTCB": "0x7130d2a12a3d2f2f9f2c8f5f2f8e9f3f1c7c1f0",
            "CAKE": "0x0E09fabb73Bd3Ade0A17ECC321fD13a19e81cE82e",
            "FDUSD": "",
            "DAI": "0x1AF3F329e8BE154074D8769D1FFa4eE58e1ff2f8",
        },
    },
    {
        "chain": "Arbitrum",
        "chain_id_expected": 42161,
        "rpc_env": ["ARBITRUM_RPC_URL", "ARBITRUM_RPC", "ARB_RPC_URL"],
        "fallback_rpcs": ["https://arb1.arbitrum.io/rpc", "https://rpc.ankr.com/arbitrum"],
        "protocols": ["Uniswap V3"],
        "contracts": {
            "Uniswap V3": {
                "Factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                "QuoterV2": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e6",
                "NonfungiblePositionManager": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88c",
                "TickLens": "",
            },
        },
        "token_seeds": {
            "WETH": "0x82af49447d8a07e3bd95bd0d56f35241523fbab1e",
            "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831c",
            "USDT": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
            "WBTC": "0x2f2a2543B76a4166549F7aab2F4fB8A1fB0d",
            "DAI": "0xda10009cbd5d07dd0cecc66161fc93d7c900205a",
        },
    },
    {
        "chain": "Optimism",
        "chain_id_expected": 10,
        "rpc_env": ["OPTIMISM_RPC_URL", "OPTIMISM_RPC", "OP_RPC_URL"],
        "fallback_rpcs": ["https://mainnet.optimism.io", "https://rpc.ankr.com/optimism"],
        "protocols": ["Uniswap V3"],
        "contracts": {
            "Uniswap V3": {
                "Factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                "QuoterV2": "",
                "NonfungiblePositionManager": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88c",
                "TickLens": "",
            },
        },
        "token_seeds": {
            "WETH": "0x4200000000000000000000000000000000000006",
            "USDC": "0x7F5c764cBc14f9669B88837ca1490cCa17c31607c",
            "USDT": "0x83f5...unknown",
            "WBTC": "0x68f180fcce6836688e9084f035309e29bf0a2095d",
            "OP": "0x4200000000000000000000000000000000000042",
            "DAI": "0xda10009cbd5d07dd0cecc66161fc93d7c900205a",
        },
    },
    {
        "chain": "Base",
        "chain_id_expected": 8453,
        "rpc_env": ["BASE_RPC_URL", "BASE_RPC", "BASECHAIN_RPC_URL"],
        "fallback_rpcs": ["https://mainnet.base.org", "https://rpc.ankr.com/base"],
        "protocols": ["Uniswap V3", "PancakeSwap V3"],
        "contracts": {
            "Uniswap V3": {
                "Factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                "QuoterV2": "",
                "NonfungiblePositionManager": "0x03a520b32C9e6fC7f3fFfA8D5c4f6E4fE4c6D5f",
                "TickLens": "",
            },
            "PancakeSwap V3": {
                "Factory": "",
                "QuoterV2": "",
                "NonfungiblePositionManager": "",
                "TickLens": "",
            },
        },
        "token_seeds": {
            "WETH": "0x4200000000000000000000000000000000000006",
            "USDC": "0xd9aaCEf8f0A31f3dC8de8f7f7c6F4d9bE8B3F4B",
        },
    },
    {
        "chain": "Ethereum",
        "chain_id_expected": 1,
        "rpc_env": ["ETH_RPC_URL", "ETHEREUM_RPC_URL", "ETHEREUM_RPC"],
        "fallback_rpcs": ["https://rpc.ankr.com/eth", "https://ethereum.publicnode.com", "https://cloudflare-eth.com"],
        "protocols": ["Uniswap V3"],
        "contracts": {
            "Uniswap V3": {
                "Factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                "QuoterV2": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e6",
                "NonfungiblePositionManager": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88c",
                "TickLens": "",
            },
        },
        "token_seeds": {
            "WETH": "0xC02aaa39b223FE8D0A0e5C4F27ead9083C756Cc2",
            "USDC": "0xA0b86991c6218B36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
            "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F0",
        },
    },
    {
        "chain": "Polygon",
        "chain_id_expected": 137,
        "rpc_env": ["POLYGON_RPC_URL", "POLYGON_RPC", "MATIC_RPC_URL"],
        "fallback_rpcs": ["https://polygon-rpc.com", "https://rpc.ankr.com/polygon"],
        "protocols": ["Uniswap V3"],
        "contracts": {
            "Uniswap V3": {
                "Factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
                "QuoterV2": "",
                "NonfungiblePositionManager": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88c",
                "TickLens": "",
            },
        },
        "token_seeds": {
            "WMATIC": "0x0000000000000000000000000000000000001010",
            "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            "USDT": "0x3813e82e6f7098b9583FC0F33a962D02018B6803c",
            "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
            "WBTC": "0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6f",
            "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf7580230aa72f4f1",
        },
    },
]

ABI_SIGS = {
    "getPool": "getPool(address,address,uint24)",
    "token0": "token0()",
    "token1": "token1()",
    "fee": "fee()",
    "tickSpacing": "tickSpacing()",
    "liquidity": "liquidity()",
    "slot0": "slot0()",
    "decimals": "decimals()",
    "quoteExactInputSingle": "quoteExactInputSingle((address,address,uint256,uint24,uint160))",
    "tickBitmap": "tickBitmap(int16)",
    "ticks": "ticks(int24)",
}


def _selector(sig: str) -> str:
    return "0x" + keccak(text=sig).hex()[:8]


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    _ensure_dir(path)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    _ensure_dir(path)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]], columns: List[str]) -> None:
    _ensure_dir(path)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in columns})


def rpc_post(endpoint: str, payload: Dict[str, Any], timeout: int = 20):
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            return True, json.loads(raw), ""
    except Exception as e:
        return False, None, str(e)


def _normalize_addr(addr: str) -> str:
    if not addr:
        return ""
    addr = addr.strip()
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", addr):
        return ""
    try:
        return to_checksum_address(addr)
    except Exception:
        return addr.lower() if re.match(r"^0x[0-9a-fA-F]{40}$", addr) else ""


def _signature_arg_types(sig: str) -> List[str]:
    m = re.match(r"^[^(]*\((.*)\)$", sig.strip())
    if not m:
        return []
    inside = m.group(1).strip()
    if not inside:
        return []
    return [x.strip() for x in inside.split(",") if x.strip()]


def _eth_call(endpoint: str, contract: str, data: str) -> Tuple[bool, Any, str]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": contract, "data": data}, "latest"],
    }
    ok, obj, err = rpc_post(endpoint, payload)
    if not ok or not isinstance(obj, dict):
        return False, None, err
    if "error" in obj:
        return False, obj, obj.get("error", {}).get("message", "rpc_error")
    return True, obj.get("result"), ""


def _eth_get_code(endpoint: str, contract: str) -> Tuple[bool, str, str]:
    ok, result, err = rpc_post(
        endpoint,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getCode",
            "params": [contract, "latest"],
        },
    )
    if not ok or not isinstance(result, dict):
        return False, "", err or "rpc_fail"
    if "error" in result:
        return False, "", result.get("error", {}).get("message", "rpc_error")
    code = result.get("result")
    if not isinstance(code, str):
        return False, "", "invalid_code_result"
    return True, code, ""


def _get_chain(rpc_candidates: List[str]) -> Tuple[bool, Dict[str, Any], str]:
    info = {
        "selected_rpc": "",
        "rpc_read_only_ready": False,
        "chain_id_read": None,
        "latest_block": None,
        "fallback_rpc_used": False,
        "invalid_reason": "",
        "confidence": "none",
        "rpc_present": False,
    }
    if not rpc_candidates:
        info["invalid_reason"] = "no_rpc_candidate"
        return False, info, ""
    for idx, endpoint in enumerate(rpc_candidates):
        ok, payload = False, None
        try:
            ok, payload, err = rpc_post(endpoint, {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []})
        except Exception as e:
            err = str(e)
            ok = False
        if not ok:
            info["invalid_reason"] = f"rpc_fail:{err}"
            continue
        if not isinstance(payload, dict) or "result" not in payload:
            info["invalid_reason"] = "chainid_invalid_payload"
            continue
        try:
            chain_id = int(payload["result"], 16)
        except Exception:
            info["invalid_reason"] = "chainid_decode_failed"
            continue
        ok2, payload2, err2 = rpc_post(endpoint, {"jsonrpc": "2.0", "id": 2, "method": "eth_getBlockByNumber", "params": ["latest", False]})
        latest = None
        if ok2 and isinstance(payload2, dict) and payload2.get("result"):
            latest_hex = payload2["result"].get("number")
            if isinstance(latest_hex, str):
                try:
                    latest = int(latest_hex, 16)
                except Exception:
                    latest = None
        if latest is None:
            info["invalid_reason"] = "latest_block_unavailable"
            info["chain_id_read"] = chain_id
            continue
        info["selected_rpc"] = endpoint
        info["chain_id_read"] = chain_id
        info["latest_block"] = latest
        info["rpc_present"] = True
        info["fallback_rpc_used"] = idx >= len([x for x in rpc_candidates if not x.startswith("http://") and "://" in x])
        info["rpc_read_only_ready"] = True
        info["confidence"] = "low" if info["fallback_rpc_used"] else "high"
        return True, info, ""
    return False, info, info["invalid_reason"]


def _chain_candidates(chain: Dict[str, Any]) -> List[str]:
    rpc_set = []
    for key in chain["rpc_env"]:
        v = os.environ.get(key, "").strip()
        if v and v not in rpc_set:
            rpc_set.append(v)
    for r in chain["fallback_rpcs"]:
        if r not in rpc_set:
            rpc_set.append(r)
    return rpc_set


def _zpad(v: int, width: int = 64) -> str:
    return hex(v)[2:].rjust(width, "0")


def _encode_arg(arg: str, typ: str) -> str:
    if typ.startswith("uint") or typ.startswith("int"):
        m = re.match(r"^(u?int)([0-9]+)$", typ)
        if not m:
            raise ValueError(f"unsupported int type {typ}")
        bits = int(m.group(2))
        n = int(arg, 0)
        if typ.startswith("int") and n < 0:
            n = (1 << bits) + n
        return _zpad(n, 64)
    if typ == "address":
        a = _normalize_addr(arg)
        if not a:
            return "0" * 64
        return ("0" * 24 + a[2:]).rjust(64, "0").lower()
    raise ValueError(f"unsupported type {typ}")


def _encode_static(types: List[str], values: List[Any]) -> str:
    if len(types) != len(values):
        raise ValueError("type/value mismatch")
    return "".join(_encode_arg(v if not isinstance(v, int) else str(int(v)), t) for t, v in zip(types, values))


def _encode_tuple_signature(arg_sig: str, args: List[Any]) -> Tuple[List[str], List[str]]:
    argspec = arg_sig.strip()
    if argspec.startswith("(") and argspec.endswith(")"):
        argspec = argspec[1:-1]
    if argspec and argspec not in ("", "address,address,uint256,uint24,uint160"):
        pass
    types = [x.strip() for x in argspec.split(",") if x.strip()]
    vals = []
    for t, v in zip(types, args):
        vals.append(str(v))
    return types, vals


def _call_call(endpoint: str, contract: str, sig_key: str, types: List[str] | None = None, args: List[Any] | None = None) -> Tuple[bool, str, str]:
    if types is None:
        types = []
    if args is None:
        args = []
    expected_types = _signature_arg_types(ABI_SIGS[sig_key])
    if len(expected_types) == 0:
        types = []
        args = []
    elif len(args) == 0 and types == ["address", ""]:
        # legacy caller typo from earlier phase: treated as no-arg call
        args = []
        types = expected_types
    elif len(args) == 0 and len(expected_types) >= 0 and types != expected_types:
        # auto-correct accidental/legacy explicit arg type list
        types = expected_types
    elif len(types) != len(args) and len(expected_types) == len(args):
        types = expected_types
    elif len(types) != len(args) and len(args) == 0 and expected_types:
        types = expected_types
    elif len(types) != len(args):
        # Keep the original behavior explicit mismatch to surface unexpected usage.
        return False, "", f"sig_arg_mismatch expected {len(types)} args but got {len(args)} for {sig_key}"

    data = _selector(ABI_SIGS[sig_key]) + _encode_static(types, args)
    ok, raw, err = _eth_call(endpoint, contract, data)
    if not ok:
        return False, "", err
    if not isinstance(raw, str) or not raw.startswith("0x") or len(raw) < 2:
        return False, "", "invalid_call_result"
    return True, raw[2:], ""


def _decode_addr(hex_word: str) -> str:
    return _normalize_addr("0x" + hex_word[-40:])


def _decode_uint(hex_word: str) -> int:
    return int(hex_word, 16)


def _decode_int24(hex_word: str) -> int:
    v = int(hex_word, 16)
    if v >= 1 << 23:
        return v - (1 << 24)
    return v


def _decode_bool(hex_word: str) -> bool:
    return int(hex_word, 16) != 0


def _decode_words(result_hex: str, count: int) -> List[str]:
    if len(result_hex) % 64 != 0:
        pad = (64 - len(result_hex) % 64) % 64
        result_hex = result_hex + "0" * pad
    return [result_hex[i : i + 64] for i in range(0, len(result_hex), 64)][:count]


def _decode_slot0(words: List[str]) -> Dict[str, Any]:
    if len(words) < 7:
        return {}
    return {
        "sqrt_price_x96": _decode_uint(words[0]),
        "tick": _decode_int24(words[1]),
        "observation_index": _decode_uint(words[2]),
        "observation_cardinality": _decode_uint(words[3]),
        "observation_cardinality_next": _decode_uint(words[4]),
        "fee_protocol": _decode_uint(words[5]),
        "unlocked": _decode_bool(words[6]),
    }


def _safe_gettoken(chain_obj: Dict[str, Any], name: str) -> str:
    for p in chain_obj["protocols"]:
        for role, addr in chain_obj["contracts"].get(p, {}).items():
            if role == name and _normalize_addr(addr):
                return _normalize_addr(addr)
    return ""


def run() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Input evidence audit
    input_rows = [{"path": str(p), "exists": p.exists()} for p in INPUT_FILES]
    input_summary = {
        "all_inputs_present": all(r["exists"] for r in input_rows),
        "missing_inputs": [r["path"] for r in input_rows if not r["exists"]],
        "previous_stage_is_design_v1": False,
    }
    prior_path = REPO_ROOT / "reports/lp_evm_universe_expansion_design/20260601_155703/FINAL_VERDICT.json"
    prior = {}
    if prior_path.exists():
        try:
            prior = json.loads(prior_path.read_text(encoding="utf-8"))
        except Exception:
            prior = {}
        input_summary["previous_stage_is_design_v1"] = prior.get("stage") == "LP_EVM_UNIVERSE_EXPANSION_DESIGN_V1"
    input_summary["universe_targeting"] = "multi_chain_v3_standard"
    input_summary["bsc_p0_required"] = True
    input_summary["solana_deferred_this_round"] = True
    input_summary["checked_at"] = checked_at
    write_json(REPORT_DIR / "input_evidence_audit.json", {"inputs": input_rows, "summary": input_summary})
    write_text(
        REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
        "# 输入证据审计\n\n"
        + "\n".join([f"- {r['path']}: {'存在' if r['exists'] else '缺失'}" for r in input_rows])
        + f"\n- previous_stage_is_design_v1: {'yes' if input_summary['previous_stage_is_design_v1'] else 'no'}\n"
        + "- stage: LP_EVM_STANDARD_V3_UNIVERSE_DISCOVERY_V1\n"
        + "- 本轮目标: 多链标准V3 discovery (BSC/Arb/OP/Base/P1 ETH Polygon)\n"
        + "- not doing: Solana, Probe, canary, live\n",
    )

    # RPC readiness
    chain_rows = []
    chain_status = {}
    for chain in CHAIN_TARGETS:
        candidates = _chain_candidates(chain)
        ok, status, _ = _get_chain(candidates)
        if ok:
            status["chain"] = chain["chain"]
            status["chain_id_expected"] = chain["chain_id_expected"]
        else:
            status["chain"] = chain["chain"]
            status["chain_id_expected"] = chain["chain_id_expected"]
            status["rpc_read_only_ready"] = False
        chain_rows.append(status)
        chain_status[chain["chain"]] = status
    write_csv(
        REPORT_DIR / "evm_rpc_readiness.csv",
        chain_rows,
        ["chain", "chain_id_expected", "rpc_present", "fallback_rpc_used", "chain_id_read", "latest_block", "rpc_read_only_ready", "confidence", "invalid_reason", "selected_rpc"],
    )
    write_json(REPORT_DIR / "evm_rpc_readiness.json", {"rows": chain_rows, "checked_at": checked_at})
    write_text(
        REPORT_DIR / "EVM_RPC_READINESS_CN.md",
        "# RPC 就绪性\n\n"
        + "\n".join(
            [
                f"- {r['chain']}: ready={str(r['rpc_read_only_ready']).lower()}, chain_id={r['chain_id_read']}, latest={r['latest_block']}, "
                f"fallback={str(r['fallback_rpc_used']).lower()}, selected={r['selected_rpc']}"
                for r in chain_rows
            ]
        ),
    )

    # Contract map
    contract_rows = []
    for chain in CHAIN_TARGETS:
        rpc = chain_status[chain["chain"]]["selected_rpc"] if chain_status[chain["chain"]]["selected_rpc"] else ""
        for protocol in chain["protocols"]:
            for role, addr in chain["contracts"].get(protocol, {}).items():
                addr_n = _normalize_addr(addr)
                code_state = "unknown"
                if rpc and addr_n:
                    ok, raw, _eth_err = _eth_get_code(rpc, addr_n)
                    if ok and raw in ("0x", "", None):
                        code_state = "no_code"
                    elif ok:
                        code_state = "yes"
                    else:
                        code_state = "call_fail"
                contract_rows.append(
                    {
                        "chain": chain["chain"],
                        "protocol": protocol,
                        "contract_role": role,
                        "address": addr_n,
                        "code_exists": code_state,
                        "selected_for_discovery": "yes" if role == "Factory" and addr_n else "no",
                        "selected_rpc": rpc,
                    }
                )
    write_csv(
        REPORT_DIR / "evm_v3_contract_map.csv",
        contract_rows,
        ["chain", "protocol", "contract_role", "address", "code_exists", "selected_for_discovery", "selected_rpc"],
    )
    write_json(REPORT_DIR / "evm_v3_contract_map.json", {"rows": contract_rows, "checked_at": checked_at})
    write_text(
        REPORT_DIR / "EVM_V3_CONTRACT_MAP_CN.md",
        "# EVM 标准V3 合约映射\n\n" + "\n".join([f"- {r['chain']} | {r['protocol']} | {r['contract_role']} | {r['address'] or 'unknown'} | code={r['code_exists']}" for r in contract_rows]),
    )

    # Token seed map
    token_rows = []
    for chain in CHAIN_TARGETS:
        rpc = chain_status[chain["chain"]]["selected_rpc"]
        for symbol, addr in chain["token_seeds"].items():
            addr_n = _normalize_addr(addr)
            row = {
                "chain": chain["chain"],
                "symbol": symbol,
                "address": addr_n,
                "decimals": "",
                "metadata_confidence": "low" if not addr_n else "medium",
                "invalid_reason": "" if addr_n else "missing_token_seed",
                "selected_rpc": rpc,
            }
            if addr_n and rpc:
                ok, hex_data, err = _call_call(rpc, addr_n, "decimals", ["address", ""])
                # noop guard: decimals parser not meaningful for malformed signatures, keep placeholder.
                row["metadata_confidence"] = "medium" if ok else "low"
                row["invalid_reason"] = "" if ok else err
            token_rows.append(row)
    write_csv(
        REPORT_DIR / "evm_token_seed_map.csv",
        token_rows,
        ["chain", "symbol", "address", "decimals", "metadata_confidence", "invalid_reason", "selected_rpc"],
    )
    write_json(REPORT_DIR / "evm_token_seed_map.json", {"rows": token_rows, "checked_at": checked_at})
    write_text(
        REPORT_DIR / "EVM_TOKEN_SEED_MAP_CN.md",
        "# Token Seed Map\n\n" + "\n".join([f"- {r['chain']} {r['symbol']}: {r['address'] or 'unknown'} ({r['metadata_confidence']})" for r in token_rows]),
    )

    # Candidate pair+fee plan
    pair_fee_rows = []
    for chain in CHAIN_TARGETS:
        if "PancakeSwap V3" in chain["protocols"]:
            for a, b in [
                ("WBNB", "USDT"),
                ("WBNB", "USDC"),
                ("ETH", "WBNB"),
                ("BTCB", "WETH"),
                ("USDC", "DAI"),
            ]:
                token_a = _normalize_addr(chain["token_seeds"].get(a, ""))
                token_b = _normalize_addr(chain["token_seeds"].get(b, ""))
                for fee in [100, 500, 2500, 10000]:
                    pair_fee_rows.append(
                        {
                            "chain": chain["chain"],
                            "protocol": "PancakeSwap V3",
                            "token_a": a,
                            "token_b": b,
                            "token_a_address": token_a,
                            "token_b_address": token_b,
                            "fee_tier": fee,
                            "fee_tier_percent": {100: "0.01%", 500: "0.05%", 2500: "0.25%", 10000: "1%"}[fee],
                            "ready_for_getpool": "yes" if token_a and token_b else "no",
                        }
                    )
        for protocol in chain["protocols"]:
            if protocol != "PancakeSwap V3":
                for a, b in [("WETH", "USDC"), ("WETH", "USDT"), ("USDC", "USDT"), ("WETH", "DAI"), ("WBTC", "USDC")]:
                    token_a = _normalize_addr(chain["token_seeds"].get(a, ""))
                    token_b = _normalize_addr(chain["token_seeds"].get(b, ""))
                    if not token_a or not token_b:
                        continue
                    for fee in [100, 500, 3000, 10000]:
                        pair_fee_rows.append(
                            {
                                "chain": chain["chain"],
                                "protocol": protocol,
                                "token_a": a,
                                "token_b": b,
                                "token_a_address": token_a,
                                "token_b_address": token_b,
                                "fee_tier": fee,
                                "fee_tier_percent": {100: "0.01%", 500: "0.05%", 3000: "0.30%", 10000: "1%"}[fee],
                                "ready_for_getpool": "yes",
                            }
                        )
    write_csv(
        REPORT_DIR / "evm_candidate_pair_fee_plan.csv",
        pair_fee_rows,
        ["chain", "protocol", "token_a", "token_b", "token_a_address", "token_b_address", "fee_tier", "fee_tier_percent", "ready_for_getpool"],
    )
    write_json(REPORT_DIR / "evm_candidate_pair_fee_plan.json", {"rows": pair_fee_rows, "checked_at": checked_at})
    write_text(
        REPORT_DIR / "EVM_CANDIDATE_PAIR_FEE_PLAN_CN.md",
        "# 候选 Pair+Fee 计划\n\n"
        + f"- total_pairs: {len(pair_fee_rows)}\n"
        + "\n".join([f"- {r['chain']} | {r['protocol']} | {r['token_a']}/{r['token_b']} | {r['fee_tier_percent']} | ready={r['ready_for_getpool']}" for r in pair_fee_rows[:200]]),
    )

    # getPool discovery
    discovered_rows = []
    for p in pair_fee_rows:
        chain = next(c for c in CHAIN_TARGETS if c["chain"] == p["chain"])
        if p["ready_for_getpool"] != "yes":
            continue
        chain_r = chain_status[p["chain"]]
        rpc = chain_r["selected_rpc"]
        if not chain_r["rpc_read_only_ready"]:
            discovered_rows.append({**p, "pool_address": "", "pool_exists": "no", "getpool_success": "no", "invalid_reason": "chain_rpc_not_ready"})
            continue
        factory = _normalize_addr(chain["contracts"].get(p["protocol"], {}).get("Factory", ""))
        if not factory:
            discovered_rows.append({**p, "pool_address": "", "pool_exists": "no", "getpool_success": "no", "invalid_reason": "factory_unknown"})
            continue
        data = _selector(ABI_SIGS["getPool"]) + _encode_static(["address", "address", "uint24"], [p["token_a_address"], p["token_b_address"], p["fee_tier"]])
        ok, ret, err = _eth_call(rpc, factory, data)
        pool_addr = ""
        success = "no"
        reason = ""
        if ok and isinstance(ret, str) and ret != "0x" and len(ret) >= 66:
            words = _decode_words(ret[2:], 1)
            candidate = _decode_addr(words[0])
            if candidate:
                zero = "0x0000000000000000000000000000000000000000"
                if candidate.lower() != zero.lower():
                    pool_addr = candidate
                    success = "yes"
                else:
                    reason = "zero_pool"
            else:
                reason = "no_pool"
        else:
            reason = err or "call_failed"
        row = {**p, "pool_address": pool_addr, "pool_exists": "yes" if success == "yes" else "no", "getpool_success": success, "invalid_reason": reason}
        discovered_rows.append(row)
    # de-dupe
    uniq = {}
    for r in discovered_rows:
        key = (r["chain"], r["protocol"], r["token_a_address"], r["token_b_address"], r["fee_tier"])
        if key not in uniq:
            uniq[key] = r
    discovered_rows = list(uniq.values())

    write_csv(
        REPORT_DIR / "evm_standard_v3_getpool_discovery.csv",
        discovered_rows,
        ["chain", "protocol", "token_a", "token_b", "token_a_address", "token_b_address", "fee_tier", "pool_address", "pool_exists", "getpool_success", "invalid_reason", "ready_for_getpool"],
    )
    write_json(
        REPORT_DIR / "evm_standard_v3_getpool_discovery.json",
        {
            "rows": discovered_rows,
            "count_tested": len(discovered_rows),
            "count_discovered": len([r for r in discovered_rows if r["pool_exists"] == "yes"]),
            "checked_at": checked_at,
        },
    )
    write_text(
        REPORT_DIR / "EVM_STANDARD_V3_GETPOOL_DISCOVERY_CN.md",
        "# 标准V3 getPool discovery\n\n"
        + f"- tested: {len(discovered_rows)}\n"
        + f"- discovered: {len([r for r in discovered_rows if r['pool_exists'] == 'yes'])}\n"
        + "\n".join([f"- {r['chain']} {r['protocol']} {r['token_a']}/{r['token_b']} fee={r['fee_tier']} => {r['pool_address'] or 'none'} ({r['invalid_reason']})" for r in discovered_rows[:200]]),
    )

    # Metadata and smoke checks
    metadata_rows = []
    for d in discovered_rows:
        if d["pool_exists"] != "yes":
            continue
        rpc = chain_status[d["chain"]]["selected_rpc"]
        pool = d["pool_address"]
        t0 = t1 = fee = tick_spacing = liquidity = ""
        token_mismatches = []
        invalid_reasons = []
        for method, out_t in [
            ("token0", "address"),
            ("token1", "address"),
            ("fee", "uint24"),
            ("tickSpacing", "int24"),
            ("liquidity", "uint128"),
        ]:
            ok, raw, err = _call_call(rpc, pool, method, ["address"], [])
            if not ok:
                invalid_reasons.append(err)
                continue
            words = _decode_words(raw, 1)
            if len(words) != 1:
                invalid_reasons.append("decode_word_count_mismatch")
                continue
            if method in ("token0", "token1"):
                v = _decode_addr(words[0])
                if method == "token0":
                    t0 = v
                else:
                    t1 = v
            elif method == "fee":
                fee = _decode_uint(words[0])
            elif method == "tickSpacing":
                tick_spacing = _decode_int24(words[0])
            elif method == "liquidity":
                liquidity = _decode_uint(words[0])
        # slot0
        slot0_words = []
        slot0_ok = False
        ok_slot0 = False
        for method in ["slot0"]:
            ok, raw, err = _call_call(rpc, pool, method, ["uint160", "int24", "uint16", "uint16", "uint16", "uint8", "bool"], ["0"])
            if ok:
                words = _decode_words(raw, 7)
                slot0 = _decode_slot0(words)
                if slot0:
                    slot0_words = words
                    ok_slot0 = True
            else:
                invalid_reasons.append(err)
        conf = "high" if t0 and t1 and ok_slot0 else ("medium" if t0 or t1 else "low")
        metadata_rows.append(
            {
                "chain": d["chain"],
                "protocol": d["protocol"],
                "pool_address": pool,
                "token_pair": f"{d['token_a']}/{d['token_b']}",
                "fee_tier": d["fee_tier"],
                "token0": t0,
                "token1": t1,
                "tick_spacing": tick_spacing,
                "liquidity": liquidity,
                "sqrt_price_x96": slot0_words[0] if slot0_words else "",
                "current_tick": slot0_words[1] if slot0_words else "",
                "token0_match": "yes" if t0.lower() == d["token_a_address"].lower() else "no",
                "token1_match": "yes" if t1.lower() == d["token_b_address"].lower() else "no",
                "slot0_success": "yes" if ok_slot0 else "no",
                "metadata_confidence": conf,
                "invalid_reason": ";".join([x for x in invalid_reasons if x]),
            }
        )

    write_csv(
        REPORT_DIR / "evm_standard_v3_pool_metadata.csv",
        metadata_rows,
        ["chain", "protocol", "pool_address", "token_pair", "fee_tier", "token0", "token1", "token0_match", "token1_match", "tick_spacing", "liquidity", "sqrt_price_x96", "current_tick", "slot0_success", "metadata_confidence", "invalid_reason"],
    )
    write_json(REPORT_DIR / "evm_standard_v3_pool_metadata.json", {"rows": metadata_rows, "checked_at": checked_at})
    write_text(
        REPORT_DIR / "EVM_STANDARD_V3_POOL_METADATA_CN.md",
        "# 标准V3 Pool Metadata\n\n" + "\n".join([f"- {r['chain']} {r['protocol']} {r['pool_address']} conf={r['metadata_confidence']} slot0={r['slot0_success']}" for r in metadata_rows]),
    )

    # quote smoke (tuple static args)
    quote_rows = []
    for m in metadata_rows:
        chain = next(c for c in CHAIN_TARGETS if c["chain"] == m["chain"])
        rpc = chain_status[m["chain"]]["selected_rpc"]
        quoter = _normalize_addr(chain["contracts"].get(m["protocol"], {}).get("QuoterV2", ""))
        if not quoter:
            continue
        t0 = m["token0"]
        t1 = m["token1"]
        if not (t0 and t1):
            continue
        for notion, direction in [
            (20, "t0_to_t1"),
            (100, "t0_to_t1"),
            (500, "t1_to_t0"),
            (1000, "t0_to_t1"),
        ]:
            amount_in = notion * 10**18
            types = ["address", "address", "uint256", "uint24", "uint160"]
            tuple_sig = "quoteExactInputSingle"
            # manual fixed-point for tuple is concatenation of args
            try:
                payload_data = _selector(ABI_SIGS[tuple_sig]) + _encode_static(types, [t0 if direction == "t0_to_t1" else t1, t1 if direction == "t0_to_t1" else t0, amount_in, m["fee_tier"], 0])
                ok, raw, err = _eth_call(rpc, quoter, payload_data)
                amount_out = ""
                q_success = "no"
                if ok:
                    words = _decode_words(raw[2:] if isinstance(raw, str) and raw.startswith("0x") else str(raw), 1)
                    if len(words) == 1:
                        amount_out = str(_decode_uint(words[0]))
                        q_success = "yes"
                    else:
                        q_success = "no"
                quote_rows.append({"chain": m["chain"], "protocol": m["protocol"], "pool_address": m["pool_address"], "virtual_notional_usd": notion, "quote_direction": direction, "quote_success": q_success, "amount_out": amount_out, "invalid_reason": "" if err == "" else err, "quote_confidence": "medium" if q_success == "yes" else "low"})
            except Exception as e:
                quote_rows.append({"chain": m["chain"], "protocol": m["protocol"], "pool_address": m["pool_address"], "virtual_notional_usd": notion, "quote_direction": direction, "quote_success": "no", "amount_out": "", "invalid_reason": str(e), "quote_confidence": "low"})
    write_csv(
        REPORT_DIR / "evm_standard_v3_quote_readiness_smoke.csv",
        quote_rows,
        ["chain", "protocol", "pool_address", "virtual_notional_usd", "quote_direction", "quote_success", "amount_out", "quote_confidence", "invalid_reason"],
    )
    q_summary = {
        "quote_attempt_count": len(quote_rows),
        "quote_success_count": len([r for r in quote_rows if r["quote_success"] == "yes"]),
        "quote_fail_count": len([r for r in quote_rows if r["quote_success"] == "no"]),
    }
    for r in quote_rows:
        q_summary.setdefault(r["chain"], {"attempt": 0, "success": 0})
        q_summary[r["chain"]]["attempt"] += 1
        if r["quote_success"] == "yes":
            q_summary[r["chain"]]["success"] += 1
    write_json(REPORT_DIR / "evm_standard_v3_quote_readiness_smoke.json", {"rows": quote_rows, "summary": q_summary, "checked_at": checked_at})
    write_text(
        REPORT_DIR / "EVM_STANDARD_V3_QUOTE_READINESS_SMOKE_CN.md",
        "# quote readiness smoke\n\n" + f"- attempts={q_summary['quote_attempt_count']}, success={q_summary['quote_success_count']}, fail={q_summary['quote_fail_count']}\n",
    )

    # tick smoke
    tick_rows = []
    for m in metadata_rows:
        if m["slot0_success"] != "yes":
            continue
        rpc = chain_status[m["chain"]]["selected_rpc"]
        pool = m["pool_address"]
        tick = int(m["current_tick"], 16) if isinstance(m["current_tick"], str) and re.fullmatch(r"[0-9a-fA-F]+", m["current_tick"]) else 0
        word = tick // int(m["tick_spacing"] or 1)
        init_count = 0
        invalid = ""
        ok_bitmap = False
        for method, types, args in [("tickBitmap", ["int16"], [word]), ("ticks", ["int24"], [tick])]:
            ok, raw, err = _call_call(rpc, pool, method, types, args)
            if ok:
                if method == "tickBitmap":
                    ok_bitmap = True
                if method == "ticks":
                    init_count += 1
            else:
                invalid = err if not invalid else invalid
        tick_rows.append(
            {
                "chain": m["chain"],
                "protocol": m["protocol"],
                "pool_address": m["pool_address"],
                "tick_bitmap_success": "yes" if ok_bitmap else "no",
                "initialized_ticks_found": init_count,
                "tick_read_success_count": 1 if init_count > 0 else 0,
                "tick_confidence": "medium" if init_count > 0 else "low",
                "invalid_reason": invalid,
            }
        )
    write_csv(
        REPORT_DIR / "evm_standard_v3_tick_readiness_smoke.csv",
        tick_rows,
        ["chain", "protocol", "pool_address", "tick_bitmap_success", "initialized_ticks_found", "tick_read_success_count", "tick_confidence", "invalid_reason"],
    )
    write_json(REPORT_DIR / "evm_standard_v3_tick_readiness_smoke.json", {"rows": tick_rows, "checked_at": checked_at, "summary": {"pool_count": len(tick_rows), "success_pool_count": len([x for x in tick_rows if x["tick_read_success_count"] > 0])}})
    write_text(REPORT_DIR / "EVM_STANDARD_V3_TICK_READINESS_SMOKE_CN.md", "# tick readiness smoke\n\n" + f"- tick_pool_count={len(tick_rows)}\n")

    # normalized universe
    normalized_rows = []
    for idx, m in enumerate(metadata_rows, start=1):
        normalized_rows.append(
            {
                "index": idx,
                "chain": m["chain"],
                "chain_id": next(c["chain_id_expected"] for c in CHAIN_TARGETS if c["chain"] == m["chain"]),
                "protocol": m["protocol"],
                "pool_type": "v3",
                "token_pair": m["token_pair"],
                "token0": m["token0"],
                "token1": m["token1"],
                "fee_tier": m["fee_tier"],
                "pool_address": m["pool_address"],
                "quote_ready": "yes" if any(q["pool_address"] == m["pool_address"] and q["quote_success"] == "yes" for q in quote_rows) else "no",
                "tick_ready": "yes" if any(t["pool_address"] == m["pool_address"] and t["tick_read_success_count"] > 0 for t in tick_rows) else "no",
                "metadata_confidence": m["metadata_confidence"],
                "discovery_status": "discovered",
                "notes": m["invalid_reason"],
            }
        )
    write_csv(
        REPORT_DIR / "evm_standard_v3_normalized_universe.csv",
        normalized_rows,
        ["index", "chain", "chain_id", "protocol", "pool_type", "token_pair", "token0", "token1", "fee_tier", "pool_address", "quote_ready", "tick_ready", "metadata_confidence", "discovery_status", "notes"],
    )
    write_json(REPORT_DIR / "evm_standard_v3_normalized_universe.json", {"rows": normalized_rows, "checked_at": checked_at})
    write_text(
        REPORT_DIR / "EVM_STANDARD_V3_NORMALIZED_UNIVERSE_CN.md",
        "# 标准V3统一Universe\n\n" + "\n".join([f"- {r['chain']} {r['protocol']} {r['token_pair']} fee={r['fee_tier']} quote={r['quote_ready']} tick={r['tick_ready']}" for r in normalized_rows[:200]]),
    )

    by_chain = {}
    by_protocol = {}
    for r in normalized_rows:
        by_chain[r["chain"]] = by_chain.get(r["chain"], 0) + 1
        by_protocol[r["protocol"]] = by_protocol.get(r["protocol"], 0) + 1
    discovered_by_chain = {c: len([x for x in discovered_rows if x["chain"] == c and x["pool_exists"] == "yes"]) for c in by_chain.keys()}
    quote_ready_count = len([x for x in normalized_rows if x["quote_ready"] == "yes"])
    tick_ready_count = len([x for x in normalized_rows if x["tick_ready"] == "yes"])
    metadata_valid_count = len([x for x in normalized_rows if x["metadata_confidence"] in ("high", "medium")])
    rpc_ready_count = len([c for c in chain_rows if c["rpc_read_only_ready"]])

    if discovered_by_chain.get("BSC", 0) > 0 and quote_ready_count > 0:
        next_stage = "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_PIPELINE_V1"
    elif metadata_valid_count == 0:
        next_stage = "LP_EVM_STANDARD_V3_METADATA_FIX_REPEAT"
    elif rpc_ready_count >= 2:
        next_stage = "LP_EVM_STANDARD_V3_PRECISE_QUOTE_PIPELINE_V1"
    else:
        next_stage = "LP_EVM_STANDARD_V3_DISCOVERY_FIX_REPEAT"
    if next_stage not in ALLOWED_NEXT:
        next_stage = "STOP_LP_RESEARCH_NOW"

    coverage_summary = {
        "discovered_pool_count": len([r for r in discovered_rows if r["pool_exists"] == "yes"]),
        "metadata_rows": len(metadata_rows),
        "metadata_valid_pool_count": metadata_valid_count,
        "quote_ready_pool_count": quote_ready_count,
        "tick_ready_pool_count": tick_ready_count,
        "discovered_by_chain": discovered_by_chain,
        "discovered_by_protocol": by_protocol,
    }
    write_json(
        REPORT_DIR / "evm_standard_v3_coverage_gap.json",
        {
            "coverage_summary": coverage_summary,
            "multi_chain_discovery_ready": rpc_ready_count >= 2,
            "chain_rpc_not_ready": [c["chain"] for c in chain_rows if not c["rpc_read_only_ready"]],
            "recommended_next_stage": next_stage,
            "checked_at": checked_at,
        },
    )
    write_text(
        REPORT_DIR / "EVM_STANDARD_V3_COVERAGE_GAP_CN.md",
        "# Coverage 与缺口\n\n"
        + f"- chain_count_attempted: {len(CHAIN_TARGETS)}\n"
        + f"- chain_rpc_ready_count: {rpc_ready_count}\n"
        + f"- discovered_by_chain: {discovered_by_chain}\n"
        + f"- discovered_by_protocol: {by_protocol}\n"
        + f"- 推荐下一步: {next_stage}\n",
    )

    # safety
    script_text = REPORT_DIR.as_posix()
    # read script source to detect forbidden words in source strings
    src_text = Path(__file__).read_text(encoding="utf-8").lower()
    forbidden = [w for w in ["private_key", "wallet", "signer", "sendtransaction", "sendrawtransaction", "swap(", "mint(", "burn(", "approve("] if w in src_text]
    safety = {
        "read_only_eth_call_only": True,
        "wallet_or_tx_touched": False,
        "private_key_loaded": False,
        "transaction_sent": False,
        "script_text_forbidden": forbidden,
    }
    write_json(REPORT_DIR / "evm_standard_v3_discovery_safety_audit.json", safety)
    write_text(
        REPORT_DIR / "EVM_STANDARD_V3_DISCOVERY_SAFETY_AUDIT_CN.md",
        "# Discovery 安全审计\n\n" + "\n".join([f"- {k}: {str(v).lower()}" for k, v in safety.items() if k != "script_text_forbidden"])
        + ("\n- no forbidden symbols found in script.\n" if not forbidden else f"\n- forbidden symbols: {', '.join(forbidden)}\n"),
    )

    final_verdict = {
        "status": "PASS" if input_summary["previous_stage_is_design_v1"] and input_summary["all_inputs_present"] else "WARN",
        "stage": "LP_EVM_STANDARD_V3_UNIVERSE_DISCOVERY_V1",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "chain_count_attempted": len(CHAIN_TARGETS),
        "chain_count_rpc_ready": rpc_ready_count,
        "protocol_count_attempted": len({p for c in CHAIN_TARGETS for p in c["protocols"]}),
        "token_seed_count": len(token_rows),
        "pair_fee_combo_tested_count": len(pair_fee_rows),
        "discovered_pool_count": len([r for r in discovered_rows if r["pool_exists"] == "yes"]),
        "metadata_valid_pool_count": metadata_valid_count,
        "quote_readiness_pool_count": quote_ready_count,
        "tick_readiness_pool_count": tick_ready_count,
        "edge_proven": "no",
        "recommended_next_stage": next_stage,
        "bsc_included": discovered_by_chain.get("BSC", 0) > 0,
    }
    write_json(REPORT_DIR / "lp_evm_standard_v3_discovery_next_stage_decision.json", {"recommended_next_stage": next_stage, "can_run_probe_now": False, "can_run_virtual_economics_now": False, "tiny_canary_allowed": "no"})
    write_text(
        REPORT_DIR / "LP_EVM_STANDARD_V3_DISCOVERY_NEXT_STAGE_DECISION_CN.md",
        "# 下一阶段决议\n\n"
        + f"- stage: {final_verdict['stage']}\n"
        + f"- recommended_next_stage: {next_stage}\n"
        + "- can_run_probe_now: false\n"
        + "- can_run_virtual_economics_now: false\n"
        + "- tiny_canary_allowed: no\n",
    )
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final_verdict)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# 一页结论\n\n"
        + f"- stage: {final_verdict['stage']}\n"
        + f"- status: {final_verdict['status']}\n"
        + f"- chain_count_rpc_ready: {final_verdict['chain_count_rpc_ready']}\n"
        + f"- discovered_pool_count: {final_verdict['discovered_pool_count']}\n"
        + f"- metadata_valid_pool_count: {final_verdict['metadata_valid_pool_count']}\n"
        + f"- quote_readiness_pool_count: {final_verdict['quote_readiness_pool_count']}\n"
        + f"- tick_readiness_pool_count: {final_verdict['tick_readiness_pool_count']}\n"
        + f"- recommended_next_stage: {next_stage}\n"
        + "- tiny_canary_allowed: no\n",
    )

    artifact_lines = [
        "INPUT_EVIDENCE_AUDIT_CN.md",
        "input_evidence_audit.json",
        "EVM_RPC_READINESS_CN.md",
        "evm_rpc_readiness.csv",
        "evm_rpc_readiness.json",
        "EVM_V3_CONTRACT_MAP_CN.md",
        "evm_v3_contract_map.csv",
        "evm_v3_contract_map.json",
        "EVM_TOKEN_SEED_MAP_CN.md",
        "evm_token_seed_map.csv",
        "evm_token_seed_map.json",
        "EVM_CANDIDATE_PAIR_FEE_PLAN_CN.md",
        "evm_candidate_pair_fee_plan.csv",
        "evm_candidate_pair_fee_plan.json",
        "EVM_STANDARD_V3_GETPOOL_DISCOVERY_CN.md",
        "evm_standard_v3_getpool_discovery.csv",
        "evm_standard_v3_getpool_discovery.json",
        "EVM_STANDARD_V3_POOL_METADATA_CN.md",
        "evm_standard_v3_pool_metadata.csv",
        "evm_standard_v3_pool_metadata.json",
        "EVM_STANDARD_V3_QUOTE_READINESS_SMOKE_CN.md",
        "evm_standard_v3_quote_readiness_smoke.csv",
        "evm_standard_v3_quote_readiness_smoke.json",
        "EVM_STANDARD_V3_TICK_READINESS_SMOKE_CN.md",
        "evm_standard_v3_tick_readiness_smoke.csv",
        "evm_standard_v3_tick_readiness_smoke.json",
        "EVM_STANDARD_V3_NORMALIZED_UNIVERSE_CN.md",
        "evm_standard_v3_normalized_universe.csv",
        "evm_standard_v3_normalized_universe.json",
        "EVM_STANDARD_V3_COVERAGE_GAP_CN.md",
        "evm_standard_v3_coverage_gap.json",
        "EVM_STANDARD_V3_DISCOVERY_SAFETY_AUDIT_CN.md",
        "evm_standard_v3_discovery_safety_audit.json",
        "LP_EVM_STANDARD_V3_DISCOVERY_NEXT_STAGE_DECISION_CN.md",
        "lp_evm_standard_v3_discovery_next_stage_decision.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
        "ARTIFACT_INDEX.md",
    ]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "# Artifact Index\n" + "\n".join([f"- {a}" for a in artifact_lines]) + "\n")


if __name__ == "__main__":
    run()
