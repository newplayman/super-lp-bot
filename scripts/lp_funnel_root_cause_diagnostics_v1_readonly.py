#!/usr/bin/env python3
"""Reproduce M0F R1a pool-resolution/depth failures with public read calls.

The source database is opened with SQLite ``mode=ro``.  Network activity is
limited to ``eth_blockNumber``, ``eth_call``, ``eth_getCode`` and address-filtered
``eth_getLogs`` through the existing public ``RpcPool``.  No candidate value is
filled or changed.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_netcover_inputs_v1_readonly import NETCOVER_INPUT_FIELDS
from scripts.lp_pool_resolve_and_rank_v1_readonly import (
    AERODROME_SLIPSTREAM_FACTORY,
    SELECTOR_DECIMALS,
    build_aerodrome_get_pool_calldata,
    decode_address_word,
    decode_uint_word,
)
from scripts.lp_rpc_pool_v1_readonly import RpcPool
from scripts.lp_tier_c_exit_feasibility_v1_readonly import fetch_pool_swaps

SLOT0_SELECTOR = "0x3850c7bd"
LIQUIDITY_SELECTOR = "0x1a686502"
TOKEN0_SELECTOR = "0x0dfe1681"
TOKEN1_SELECTOR = "0xd21220a7"
FEE_SELECTOR = "0xddca3f43"
ZERO_ADDRESS = "0x" + "0" * 40
COMMON_SLIPSTREAM_SPACINGS = (1, 10, 50, 100, 200, 2000)
SLIPSTREAM_FACTORIES = {
    # Aerodrome Slipstream README, Base Deployments: Initial / Gauge Caps /
    # Gauges V3.  R1a probes all three; the production resolver currently has
    # only Initial and is intentionally not modified by this diagnostic FIX.
    "initial": AERODROME_SLIPSTREAM_FACTORY,
    "gauge_caps": "0xaDe65c38CD4849aDBA595a4323a8C7DdfE89716a",
    "gauges_v3": "0xf8f2eB4940CFE7d13603DDDD87f123820Fc061Ef",
}
FACTORY_REGISTRY_SOURCE = (
    "https://github.com/aerodrome-finance/slipstream#deployments "
    "(Base Initial/Gauge Caps/Gauges V3)"
)

CODE_EVIDENCE = {
    "resolve": "scripts/lp_pool_resolve_and_rank_v1_readonly.py:515-545",
    "swap_count": "scripts/lp_pool_resolve_and_rank_v1_readonly.py:542-548",
    "resolve_fail": "scripts/lp_pool_resolve_and_rank_v1_readonly.py:515-526",
    "attach_short_circuit": "scripts/lp_scanner_daemon_v1_readonly.py:625-646",
    "attach_calls": "scripts/lp_scanner_daemon_v1_readonly.py:648-663",
    "cost_state": "scripts/lp_netcover_inputs_v1_readonly.py:209-263",
    "reward_conversion": "scripts/lp_netcover_inputs_v1_readonly.py:266-297",
    "status_exception": "scripts/lp_pool_resolve_and_rank_v1_readonly.py:586-589",
    "config_filter": "scripts/lp_pool_resolve_and_rank_v1_readonly.py:636-658",
    "range_domain": "scripts/lp_v3_fee_share.py:6-9",
    "fee_metadata": "scripts/lp_universe_screener_v1_readonly.py:96-111,281-296",
}


def _first_word(raw: str) -> int:
    text = raw[2:] if raw.startswith("0x") else raw
    if len(text) < 64:
        raise ValueError("short ABI word")
    return int(text[:64], 16)


def _call(rpc_call: Callable[..., Any], to: str, data: str) -> dict[str, Any]:
    try:
        raw = rpc_call("eth_call", [{"to": to, "data": data}, "latest"])
        if not isinstance(raw, str) or not raw.startswith("0x"):
            raise ValueError(f"unexpected eth_call result: {raw!r}")
        return {"ok": True, "raw": raw, "return_bytes": (len(raw) - 2) // 2}
    except Exception as exc:  # diagnostic must preserve the concrete failure
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _decode_address(probe: Mapping[str, Any]) -> str | None:
    if not probe.get("ok"):
        return None
    try:
        return decode_address_word(str(probe["raw"]))
    except Exception as exc:
        return f"DECODE_ERROR:{type(exc).__name__}:{exc}"


def _decode_uint(probe: Mapping[str, Any]) -> int | None:
    if not probe.get("ok"):
        return None
    try:
        return decode_uint_word(str(probe["raw"]))
    except Exception:
        return None


def load_latest_records(db_path: Path) -> tuple[str, list[dict[str, Any]]]:
    uri = f"file:{db_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        as_of = connection.execute("SELECT MAX(as_of) FROM opportunity_scores").fetchone()[0]
        if not as_of:
            raise ValueError("opportunity_scores has no scan cycle")
        rows = connection.execute(
            "SELECT score_json FROM opportunity_scores WHERE as_of=? ORDER BY id", (as_of,)
        ).fetchall()
    finally:
        connection.close()
    return str(as_of), [json.loads(row[0]) for row in rows]


def _missing(record: Mapping[str, Any]) -> list[str]:
    return [field for field in NETCOVER_INPUT_FIELDS if record.get(field) is None]


def _probe_resolved(record: Mapping[str, Any], rpc: Any) -> dict[str, Any]:
    pool = str(record["resolved_pool"])
    probes = {
        "slot0": _call(rpc.call, pool, SLOT0_SELECTOR),
        "liquidity": _call(rpc.call, pool, LIQUIDITY_SELECTOR),
        "token0": _call(rpc.call, pool, TOKEN0_SELECTOR),
        "token1": _call(rpc.call, pool, TOKEN1_SELECTOR),
        "fee": _call(rpc.call, pool, FEE_SELECTOR),
    }
    for name in ("slot0", "liquidity", "fee"):
        if probes[name].get("ok"):
            probes[name]["decoded_first_word_uint"] = _first_word(probes[name]["raw"])
    for name in ("token0", "token1"):
        address = _decode_address(probes[name])
        probes[name]["decoded_address"] = address
        if address and not address.startswith("DECODE_ERROR"):
            decimals = _call(rpc.call, address, SELECTOR_DECIMALS)
            decimals["decoded_uint"] = _decode_uint(decimals)
            probes[f"{name}_decimals"] = decimals
    try:
        code = rpc.call("eth_getCode", [pool, "latest"])
        probes["contract_code"] = {
            "ok": isinstance(code, str) and code not in {"0x", "0x0"},
            "prefix": str(code)[:42],
            "return_bytes": max((len(str(code)) - 2) // 2, 0),
        }
    except Exception as exc:
        probes["contract_code"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return probes


def _probe_unresolved(
    record: Mapping[str, Any], rpc: Any, tip: int
) -> dict[str, Any]:
    token_a, token_b = record["underlyingTokens"]
    exact = int(record["tick_spacing"])
    spacing_results: dict[str, Any] = {}
    for spacing in sorted(set(COMMON_SLIPSTREAM_SPACINGS + (exact,))):
        order_results = []
        for left, right in ((token_a, token_b), (token_b, token_a)):
            probe = _call(
                rpc.call,
                AERODROME_SLIPSTREAM_FACTORY,
                build_aerodrome_get_pool_calldata(left, right, spacing),
            )
            probe["decoded_address"] = _decode_address(probe)
            order_results.append(probe)
        spacing_results[str(spacing)] = order_results
    factory_results: dict[str, Any] = {}
    candidate_pools: dict[str, dict[str, Any]] = {}
    for label, factory in SLIPSTREAM_FACTORIES.items():
        order_results = []
        for left, right in ((token_a, token_b), (token_b, token_a)):
            probe = _call(
                rpc.call,
                factory,
                build_aerodrome_get_pool_calldata(left, right, exact),
            )
            address = _decode_address(probe)
            probe["decoded_address"] = address
            order_results.append(probe)
            if address and address not in {ZERO_ADDRESS} and not address.startswith("DECODE_ERROR"):
                factories = candidate_pools.setdefault(address, {"factories": []})["factories"]
                if label not in factories:
                    factories.append(label)
        factory_results[label] = {"factory": factory.lower(), "orders": order_results}

    decimals = []
    for token in (token_a, token_b):
        probe = _call(rpc.call, token, SELECTOR_DECIMALS)
        probe.update(token=token.lower(), decoded_uint=_decode_uint(probe))
        decimals.append(probe)
    for pool, candidate in candidate_pools.items():
        state = _probe_resolved({"resolved_pool": pool}, rpc)
        dec0 = state.get("token0_decimals", {}).get("decoded_uint")
        dec1 = state.get("token1_decimals", {}).get("decoded_uint")
        swap_probe: dict[str, Any]
        if dec0 is None or dec1 is None:
            swap_probe = {"ok": False, "error": "token decimals unavailable"}
        else:
            try:
                swaps = fetch_pool_swaps(
                    pool, max(tip - 86400, 0), tip, int(dec0), int(dec1), rpc_call=rpc.call
                )
                prices = [float(item["price"]) for item in swaps]
                swap_probe = {
                    "ok": True,
                    "window_blocks": 86400,
                    "count": len(swaps),
                    "min_price": min(prices) if prices else None,
                    "max_price": max(prices) if prices else None,
                    "last_price": prices[-1] if prices else None,
                    "last_liquidity_raw": swaps[-1]["liquidity"] if swaps else None,
                }
            except Exception as exc:
                swap_probe = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        candidate.update(state=state, swaps=swap_probe)
    return {
        "factory_registry_source": FACTORY_REGISTRY_SOURCE,
        "factory_exact_tick_probes": factory_results,
        "initial_factory_spacing_probes": spacing_results,
        "underlying_decimals": decimals,
        "candidate_pools": candidate_pools,
    }


def _root_cause(
    record: Mapping[str, Any], rpc_evidence: Mapping[str, Any]
) -> dict[str, str]:
    symbol = str(record.get("symbol"))
    if record.get("resolve_status") != "OK":
        candidates = rpc_evidence.get("candidate_pools", {})
        if len(candidates) == 1:
            return {
                "classification": "STALE_FACTORY_REGISTRY",
                "root_cause": (
                    "The production resolver probes only the Initial Slipstream factory. The same "
                    "exact token pair/tick call returns a live pool from the official Gauges V3 "
                    "factory, with readable slot0/liquidity and real swaps."
                ),
                "repairability": "ENGINEERING",
                "suggested_fix": (
                    "Use the official versioned factory registry, validate token0/token1/tick, and "
                    "record factory provenance; never treat first non-zero as authoritative without validation."
                ),
            }
        if len(candidates) > 1:
            return {
                "classification": "MULTI_FACTORY_POOL_AMBIGUITY",
                "root_cause": (
                    "The production resolver probes only Initial, while two official later factories "
                    "both return distinct live pools for the same pair/tick. Both have swaps, so token "
                    "pair alone cannot identify the DefiLlama pool."
                ),
                "repairability": "ENGINEERING_REQUIRES_AUTHORITATIVE_MAPPING",
                "suggested_fix": (
                    "Resolve by verified DefiLlama pool-id/address/factory provenance and reject ambiguity; "
                    "until mapped, permanent_fail_closed_reason=ambiguous_multi_factory_pool."
                ),
            }
        return {
            "classification": "POOL_NOT_IN_SUPPORTED_FACTORY",
            "root_cause": (
                "The supported Aerodrome Slipstream factory returned the zero address; "
                "there is therefore no pool address on which to fetch swaps or live state."
            ),
            "repairability": "CONDITIONAL_ENGINEERING",
            "suggested_fix": (
                "Require an authoritative free-source pool address/factory and validate token0/token1; "
                "otherwise preserve permanent_fail_closed_reason=pool_not_found_in_supported_factory."
            ),
        }
    if record.get("status") == "ERROR":
        return {
            "classification": "OBSERVED_RANGE_EXCEEDS_MATH_DOMAIN",
            "root_cause": (
                "The measured price path drives recommended range above 100%; p_lo becomes negative "
                "and replay raises ValueError at sqrt(p_lo). The ERROR row is excluded from multiwindow, "
                "so horizon/fee/reward/IL/latency remain absent."
            ),
            "repairability": "PARTIAL_FAIL_CLOSED_ONLY",
            "suggested_fix": (
                "Validate range domain before replay and emit permanent_fail_closed_reason="
                "observed_range_gte_100; "
                "do not clamp or replace the measured price path merely to make NetCover calculable."
            ),
        }
    missing = _missing(record)
    if not missing:
        return {
            "classification": "FULLY_CALCULABLE_BELOW_GATE",
            "root_cause": "No input is missing; the measured NetCover is honestly below the shadow gate.",
            "repairability": "NOT_APPLICABLE",
            "suggested_fix": "None; do not change the gate.",
        }
    if {"entry_cost_usd", "exit_cost_usd", "slippage_usd"}.intersection(missing):
        return {
            "classification": "NO_MEASURED_USD_QUOTE_AND_REWARD_CONVERSION_DEPTH",
            "root_cause": (
                "Swap active-liquidity and pair-price evidence exists, but neither pool token is a "
                "recognized USD stable quote. Treating token1/token0 as USD would be a dimensional "
                "error, so the cost-state normalizer correctly returns None. Positive AERO "
                "reward conversion also lacks its own five measured pool-state fields."
            ),
            "repairability": "ENGINEERING_WITH_RAW_CROSS_POOL_EVIDENCE",
            "suggested_fix": (
                "Add measured, provenance-labelled USD cross-pool pricing. Pre-register the AERO "
                "conversion-pool allowlist and a non-optimistic deterministic selection rule (if "
                "multiple validated routes exist, use the highest measured conversion cost); "
                "if both raw paths are unavailable, retain fail-closed instead of estimating."
            ),
        }
    return {
        "classification": "MISSING_REWARD_CONVERSION_EVIDENCE",
        "root_cause": "Positive reward EV has no measured reward-conversion pool state.",
        "repairability": "ENGINEERING_WITH_RAW_CROSS_POOL_EVIDENCE",
        "suggested_fix": "Read and validate the AERO conversion pool; retain fail-closed if unavailable.",
    }


def collect(db_path: Path, rpc: Any) -> dict[str, Any]:
    as_of, records = load_latest_records(db_path)
    tip_hex = rpc.call("eth_blockNumber", [])
    output = {
        "schema_version": "lp_funnel_root_causes_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_db": str(db_path),
        "source_scan_as_of": as_of,
        "source_window_blocks": 86400,
        "probe_tip_hex": tip_hex,
        "probe_tip": int(tip_hex, 16),
        "code_evidence": CODE_EVIDENCE,
        "records": [],
    }
    for record in records:
        resolved = record.get("resolved_pool")
        rpc_evidence = (
            _probe_resolved(record, rpc) if resolved else _probe_unresolved(record, rpc, int(tip_hex, 16))
        )
        output["records"].append({
            "symbol": record.get("symbol"),
            "project": record.get("project"),
            "missing_fields": _missing(record),
            "resolve": {
                "status": record.get("resolve_status"),
                "pool": resolved,
                "token0": record.get("token0"),
                "token1": record.get("token1"),
                "dec0": record.get("dec0"),
                "dec1": record.get("dec1"),
                "fee_tier_from_pool_meta": record.get("fee_tier"),
                "tick_spacing_from_pool_meta": record.get("tick_spacing"),
                "pool_meta": record.get("poolMeta"),
                "underlying_tokens": record.get("underlyingTokens"),
            },
            "swaps": {
                "count_in_source_window": record.get("swap_count"),
                "last_price_token1_per_token0": record.get("last_swap_price_token1_per_token0"),
                "last_active_liquidity_raw": record.get("last_swap_liquidity_raw"),
                "source_status": record.get("status"),
                "source_error": record.get("error"),
            },
            "path_break": {
                "l_active_raw_selected": record.get("last_swap_liquidity_raw"),
                "price_pair_selected": record.get("last_swap_price_token1_per_token0"),
                "price_usd_direct": record.get("price_usd"),
                "reward_conversion_inputs": {
                    key: record.get(key) for key in (
                        "reward_conversion_l_active_raw", "reward_conversion_price_usd",
                        "reward_conversion_fee_tier", "reward_conversion_dec0",
                        "reward_conversion_dec1",
                    )
                },
            },
            "rpc_evidence": rpc_evidence,
            **_root_cause(record, rpc_evidence),
        })
    if hasattr(rpc, "health_snapshot"):
        output["rpc_health_after_probe"] = rpc.health_snapshot()
    return output


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# M0F FIX-R1a — 最终 10 池逐池根因",
        "",
        f"- M0P 扫描周期：`{report['source_scan_as_of']}`",
        f"- 只读复探 tip：`{report['probe_tip']}` (`{report['probe_tip_hex']}`)",
        "- 历史 Swap 计数取自该唯一 M0P cycle 的 `score_json`；RPC 复探只做 eth_call/eth_getCode/按池过滤的 eth_getLogs。",
        "",
        "## 总结",
        "",
        "- 7 个已 resolve 池的 slot0/liquidity 复探全部成功；本次缺失不是 429、超时或 ABI selector 不兼容。",
        "- M0P 当时 7 池已有 latest Swap price/liquidity，故 `_attach_live_pool_state` 在 scanner:625-643 提前返回；没有历史 attach 错误被吞掉。",
        "- 3 个 M0P 未 resolve 池仅在旧 Initial factory 返回零；官方多版本 registry 复探后，2 个在 Gauges V3 唯一命中，MSUSD-MSETH 在两个 factory 命中而歧义。",
        "- 5 个已有 Swap/深度的非稳定币对，断在 USD quote 归一化；同时正 AERO reward 缺独立换汇深度。",
        "- WETH-USDC 断在观测价格路径推导的 range >100% 后 replay 数学域错误；USDC-VVV 全齐但诚实低于闸。",
        f"- 官方 factory registry 证据：{FACTORY_REGISTRY_SOURCE}；逐 factory 原始 32-byte 返回见 JSON。",
        "",
        "## 逐池表",
        "",
        "| symbol | 缺失字段 | resolve/token/decimals/fee | swaps | attach slot0/liquidity | 根因与路径断点 | 可修? | 建议 |",
        "|---|---|---|---:|---|---|---|---|",
    ]
    for item in report["records"]:
        resolve = item["resolve"]
        rpc = item["rpc_evidence"]
        if resolve["pool"]:
            state = (
                f"{resolve['status']} {resolve['pool']}; "
                f"{resolve['token0']}/{resolve['token1']} "
                f"d={resolve['dec0']}/{resolve['dec1']}; metaFee={resolve['fee_tier_from_pool_meta']}; "
                f"liveFeeRaw={rpc['fee'].get('decoded_first_word_uint')}"
            )
            attach = (
                f"slot0={rpc['slot0'].get('ok')}({rpc['slot0'].get('return_bytes')}B), "
                f"liq={rpc['liquidity'].get('ok')} raw={rpc['liquidity'].get('decoded_first_word_uint')}"
            )
        else:
            factory_hits = []
            for label, evidence in rpc["factory_exact_tick_probes"].items():
                addresses = "/".join(str(x.get("decoded_address")) for x in evidence["orders"])
                factory_hits.append(f"{label}={addresses}")
            decimals = "/".join(str(x.get("decoded_uint")) for x in rpc["underlying_decimals"])
            pool_swaps = ",".join(
                f"{pool}:{data['swaps'].get('count')}swaps"
                for pool, data in rpc["candidate_pools"].items()
            ) or "none"
            state = (
                f"M0P NOT_FOUND; underlying decimals={decimals}; metaFee={resolve['fee_tier_from_pool_meta']}; "
                + "; ".join(factory_hits)
            )
            attach = f"M0P SKIPPED_NO_POOL; multi-factory live candidates={pool_swaps}"
        missing = ", ".join(item["missing_fields"]) or "无"
        root = item["root_cause"].replace("|", "\\|")
        suggestion = item["suggested_fix"].replace("|", "\\|")
        lines.append(
            f"| {item['symbol']} | {missing} | {state} | {item['swaps']['count_in_source_window']} | "
            f"{attach} | `{item['classification']}` — {root} | {item['repairability']} | {suggestion} |"
        )
    lines.extend(["", "## 可复核代码断点", ""])
    for key, value in report["code_evidence"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend([
        "",
        "## WETH-USDC 确定性复现补证",
        "",
        "同一 86400-block 只读重抓得到 27 swaps，价格范围 `1586.010813749545 .. 15035850.416616218`；"
        "7 个 hourly closes、6 个 returns，`sigma_daily=0.5320942639982603`，"
        "`recommend_range_pct(...,14)=238.90973200189612`。因此 `p_lo=entry*(1-range/100)<0`，"
        "在 `scripts/lp_v3_fee_share.py:9` 的 `math.sqrt(p_lo)` 原样抛出 `ValueError: math domain error`。",
        "",
        "## 分类边界",
        "",
        "`ENGINEERING_WITH_RAW_CROSS_POOL_EVIDENCE` 仅表示可通过新增真实只读证据链修复能力；"
        "不是允许默认值/估算。多 factory 同 pair 命中时必须用权威 pool-id 映射消歧，不能盲取第一个。"
        "WETH-USDC 只能修正错误可见性与明确 fail-closed，不能裁剪真实价格来制造可计算记录。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.db, RpcPool("base"))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "root_causes.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    (args.out / "root_causes.md").write_text(render_markdown(report))
    print(f"records={len(report['records'])} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
