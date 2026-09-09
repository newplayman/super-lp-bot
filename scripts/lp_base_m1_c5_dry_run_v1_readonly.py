#!/usr/bin/env python3
"""C5 Base open/exit eth_call dry-runs; contains no signing or send path."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.base_m1_executor_v1 import (
    MAX_SLIPPAGE_BPS,
    UNISWAP_V3_NPM,
    Action,
    Intent,
    JsonRpc,
    Protocol,
    UINT128_MAX,
    build_transaction,
    encode_approve,
    encode_burn,
    encode_collect,
    encode_decrease,
)

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
POOL = "0xd0b53D9277642d899DF5C87A3966A349A798F224"  # Uniswap v3 WETH/USDC 0.05%
FEE = 500
SIMULATION_SENDER = "0xc216bfa5da000965e820845c32e6fd88db275743"
EXIT_TOKEN_ID = 5_736_107
EXIT_OWNER = "0x9f96a96CEB50Ddb4e6eCa498dF9b524f1Fd2fa8f"


def _word(value: int) -> str:
    return f"{value:064x}"


def _decode_words(data: str) -> list[int]:
    raw = data[2:] if data.startswith("0x") else data
    return [int(raw[i : i + 64], 16) for i in range(0, len(raw), 64)]


def _signed(value: int) -> int:
    return value - (1 << 256) if value >> 255 else value


def encode_multicall(calls: list[str]) -> str:
    """ABI encode multicall(bytes[]) using the official NPM selector."""
    tails: list[str] = []
    offsets: list[int] = []
    cursor = 32 * len(calls)
    for call in calls:
        raw = call[2:]
        padded = raw.ljust(((len(raw) + 63) // 64) * 64, "0")
        offsets.append(cursor)
        tail = _word(len(raw) // 2) + padded
        tails.append(tail)
        cursor += len(tail) // 2
    return "0xac9650d8" + _word(32) + _word(len(calls)) + "".join(_word(x) for x in offsets) + "".join(tails)


def _fetch_tvl(pool: str) -> tuple[float, dict[str, Any]]:
    url = f"https://api.dexscreener.com/latest/dex/pairs/base/{pool}"
    request = urllib.request.Request(url, headers={"User-Agent": "lpbot-c5-dryrun/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    pairs = payload.get("pairs") or []
    if not pairs:
        raise RuntimeError("DexScreener returned no pool")
    pair = pairs[0]
    return float(pair["liquidity"]["usd"]), {
        "source": url,
        "dex_id": pair.get("dexId"),
        "pair_address": pair.get("pairAddress"),
        "observed_liquidity": pair.get("liquidity"),
        "observed_volume": pair.get("volume"),
    }


def _active_notional(liquidity: int, sqrt_price_x96: int, lower: int, upper: int) -> float:
    with localcontext() as ctx:
        ctx.prec = 60
        q96 = Decimal(2) ** 96
        sqrt_p = Decimal(sqrt_price_x96) / q96
        sqrt_a = Decimal("1.0001") ** (Decimal(lower) / 2)
        sqrt_b = Decimal("1.0001") ** (Decimal(upper) / 2)
        amount0 = Decimal(liquidity) * (sqrt_b - sqrt_p) / (sqrt_p * sqrt_b) / Decimal(10**18)
        amount1 = Decimal(liquidity) * (sqrt_p - sqrt_a) / Decimal(10**6)
        price = Decimal("1.0001") ** Decimal(_tick_from_sqrt(sqrt_price_x96)) * Decimal(10**12)
        return float(amount0 * price + amount1)


def _tick_from_sqrt(sqrt_price_x96: int) -> int:
    return math.floor(2 * math.log(sqrt_price_x96 / 2**96) / math.log(1.0001))


def _tx_dict(tx) -> dict[str, Any]:
    data = asdict(tx)
    data["action"] = tx.action.value
    return data


def _intent_dict(intent: Intent) -> dict[str, Any]:
    data = asdict(intent)
    data["action"] = intent.action.value
    data["protocol"] = intent.protocol.value
    return data


def _call_and_gas(rpc: JsonRpc, tx) -> dict[str, Any]:
    return {"result": rpc.simulate(tx), "gas_estimate": rpc.estimate_gas(tx), "ok": True}


def _rpc_tx(sender: str, to: str, data: str) -> dict[str, str]:
    return {"from": sender, "to": to, "data": data, "value": "0x0"}


def run(out_dir: Path, rpc_url: str, now: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    now = int(time.time()) if now is None else now
    deadline = now + 600
    rpc = JsonRpc(rpc_url, retries=4)
    chain_id = int(rpc.call("eth_chainId", []), 16)
    if chain_id != 8453:
        raise RuntimeError(f"refusing non-Base chain id {chain_id}")
    latest_block = int(rpc.call("eth_blockNumber", []), 16)
    max_fee_per_gas, max_priority_fee_per_gas = rpc.eip1559_fees()

    token0 = "0x" + rpc.call("eth_call", [{"to": POOL, "data": "0x0dfe1681"}, "latest"])[-40:]
    token1 = "0x" + rpc.call("eth_call", [{"to": POOL, "data": "0xd21220a7"}, "latest"])[-40:]
    fee = int(rpc.call("eth_call", [{"to": POOL, "data": "0xddca3f43"}, "latest"]), 16)
    spacing = _signed(int(rpc.call("eth_call", [{"to": POOL, "data": "0xd0c93a7c"}, "latest"]), 16))
    slot0 = _decode_words(rpc.call("eth_call", [{"to": POOL, "data": "0x3850c7bd"}, "latest"]))
    sqrt_price_x96, tick = slot0[0], _signed(slot0[1])
    liquidity = int(rpc.call("eth_call", [{"to": POOL, "data": "0x1a686502"}, "latest"]), 16)
    if (token0.lower(), token1.lower(), fee) != (WETH.lower(), USDC.lower(), FEE):
        raise RuntimeError("pool identity mismatch")
    lower = ((tick - 250) // spacing) * spacing
    upper = ((tick + 250) // spacing) * spacing
    price_usdc_per_weth = (1.0001**tick) * 1e12

    tvl_usd, tvl_evidence = _fetch_tvl(POOL)
    active_notional_usd = _active_notional(liquidity, sqrt_price_x96, lower, upper)
    position_cap = min(60.0, tvl_usd * 0.0005, active_notional_usd * 0.02)
    notional = min(50.0, position_cap)
    if notional < 50:
        raise RuntimeError(f"PositionCap {position_cap:.6f} is below M1 minimum 50U")
    amount0_desired = int((notional / 2) / price_usdc_per_weth * 1e18)
    amount1_desired = int(notional / 2 * 1e6)

    approvals = []
    for token, amount in ((WETH, amount0_desired), (USDC, amount1_desired)):
        data = encode_approve(UNISWAP_V3_NPM, amount)
        tx = _rpc_tx(SIMULATION_SENDER, token, data)
        approvals.append(
            {
                "token": token,
                "spender": UNISWAP_V3_NPM,
                "amount_raw": amount,
                "calldata": data,
                "simulation_result": rpc.call("eth_call", [tx, "latest"]),
                "gas_estimate": int(rpc.call("eth_estimateGas", [tx]), 16),
                "policy": "ApproveExact",
            }
        )

    mint = Intent(
        protocol=Protocol.UNISWAP_V3, npm=UNISWAP_V3_NPM, action=Action.MINT,
        wallet=SIMULATION_SENDER, pool=POOL, strategy_decision_id="C5-OPEN-20260809",
        risk_verdict_id="C5-SIMULATION-ONLY", idempotency_key="c5-open-20260809-v1",
        notional_usd=notional, slippage_bps=MAX_SLIPPAGE_BPS, deadline=deadline,
        token0=WETH, token1=USDC, fee=FEE, tick_lower=lower, tick_upper=upper,
        amount0_desired=amount0_desired, amount1_desired=amount1_desired,
    )
    quote_tx = build_transaction(mint)
    quote_result = rpc.simulate(quote_tx)
    quote_words = _decode_words(quote_result)
    if len(quote_words) < 4:
        raise RuntimeError("mint quote did not return four words")
    mint = replace(
        mint,
        amount0_min=quote_words[2] * (10_000 - MAX_SLIPPAGE_BPS) // 10_000,
        amount1_min=quote_words[3] * (10_000 - MAX_SLIPPAGE_BPS) // 10_000,
    )
    mint_tx = build_transaction(mint)
    mint_simulation = _call_and_gas(rpc, mint_tx)

    balance_data = {}
    for label, token in (("WETH", WETH), ("USDC", USDC)):
        balance = int(
            rpc.call("eth_call", [{"to": token, "data": "0x70a08231" + SIMULATION_SENDER[2:].rjust(64, "0")}, "latest"]),
            16,
        )
        balance_data[label] = balance
    preflight = {
        "simulate": mint_simulation["ok"],
        "quote": quote_words[2] > 0 and quote_words[3] > 0,
        "basis": tvl_usd >= 150_000 and fee == FEE and spacing == 10,
        "rpc_health": chain_id == 8453 and latest_block > 0,
        "wallet_balance": balance_data["WETH"] >= amount0_desired and balance_data["USDC"] >= amount1_desired,
    }
    open_report = {
        "stage": "C5_OPEN_DRY_RUN", "generated_at": datetime.now(timezone.utc).isoformat(),
        "rpc_url": rpc_url, "chain_id": chain_id, "latest_block": latest_block,
        "selection": {
            "source": "calibration fallback after C2 terminal accepted_count=0",
            "accepted_for_live": False,
            "reason": (
                "C2 produced no eligible live candidate. This authoritative Uniswap v3 WETH/USDC pool "
                "validates the pipe only and cannot be promoted to C6 without a later terminal-gate pass."
            ),
        },
        "pool": {"address": POOL, "protocol": "Uniswap v3", "token0": token0, "token1": token1,
                 "fee": fee, "tick_spacing": spacing, "tick": tick, "sqrt_price_x96": sqrt_price_x96,
                 "liquidity": liquidity, "price_usdc_per_weth": price_usdc_per_weth},
        "position_cap": {"capital_tier": "M1", "tier_max_usd": 60.0, "tvl_usd": tvl_usd,
                         "tvl_0_05pct_cap_usd": tvl_usd * 0.0005,
                         "active_liquidity_notional_usd": active_notional_usd,
                         "active_2pct_cap_usd": active_notional_usd * 0.02,
                         "position_cap_usd": position_cap, "planned_notional_usd": notional,
                         "tvl_share": notional / tvl_usd, "hard_0_10pct_pass": notional / tvl_usd <= 0.001,
                         "tvl_evidence": tvl_evidence},
        "preflight": preflight, "preflight_all_pass": all(preflight.values()),
        "simulation_identity": {"sender": SIMULATION_SENDER, "source": "public on-chain address used only as eth_call from",
                                "production_wallet": False, "keystore_loaded": False},
        "approve_exact": approvals, "mint_intent": _intent_dict(mint),
        "mint_transaction": _tx_dict(mint_tx), "quote_result": quote_result,
        "quote_consumed": {"amount0": quote_words[2], "amount1": quote_words[3]},
        "mint_simulation": mint_simulation,
        "eip1559": {"max_fee_per_gas": max_fee_per_gas,
                    "max_priority_fee_per_gas": max_priority_fee_per_gas},
        "estimated_max_cost_wei": (sum(x["gas_estimate"] for x in approvals) + mint_simulation["gas_estimate"])
                                  * max_fee_per_gas,
        "broadcast_count": 0, "signed": False, "transaction_hashes": [],
    }

    # Exit rail uses a current public position in the same pool.  All steps run in one
    # eth_call multicall so decrease/collect/burn state transitions are simulated atomically.
    token_id = EXIT_TOKEN_ID
    owner_result = rpc.call("eth_call", [{"to": UNISWAP_V3_NPM, "data": "0x6352211e" + _word(token_id)}, "latest"])
    owner = "0x" + owner_result[-40:]
    if owner.lower() != EXIT_OWNER.lower():
        raise RuntimeError("exit evidence position owner changed; choose another public position")
    position = _decode_words(
        rpc.call("eth_call", [{"to": UNISWAP_V3_NPM, "data": "0x99fbab88" + _word(token_id)}, "latest"])
    )
    exit_liquidity = position[7]
    if exit_liquidity <= 0:
        raise RuntimeError("exit evidence position has no liquidity")
    quote_decrease = encode_decrease(token_id, exit_liquidity, 0, 0, deadline)
    decrease_quote = _decode_words(
        rpc.call("eth_call", [_rpc_tx(owner, UNISWAP_V3_NPM, quote_decrease), "latest"])
    )
    decrease = encode_decrease(
        token_id, exit_liquidity,
        decrease_quote[0] * (10_000 - MAX_SLIPPAGE_BPS) // 10_000,
        decrease_quote[1] * (10_000 - MAX_SLIPPAGE_BPS) // 10_000,
        deadline,
    )
    collect = encode_collect(token_id, owner, UINT128_MAX, UINT128_MAX)
    burn = encode_burn(token_id)
    multicall = encode_multicall([decrease, collect, burn])
    multicall_tx = _rpc_tx(owner, UNISWAP_V3_NPM, multicall)
    multicall_result = rpc.call("eth_call", [multicall_tx, "latest"])
    multicall_gas = int(rpc.call("eth_estimateGas", [multicall_tx]), 16)
    revokes = []
    for token in (WETH, USDC):
        data = encode_approve(UNISWAP_V3_NPM, 0)
        tx = _rpc_tx(owner, token, data)
        revokes.append({"token": token, "spender": UNISWAP_V3_NPM, "amount_raw": 0,
                        "calldata": data, "simulation_result": rpc.call("eth_call", [tx, "latest"]),
                        "gas_estimate": int(rpc.call("eth_estimateGas", [tx]), 16)})
    exit_report = {
        "stage": "C5_EXIT_DRY_RUN", "generated_at": datetime.now(timezone.utc).isoformat(),
        "rpc_url": rpc_url, "chain_id": chain_id, "latest_block": latest_block,
        "pool": POOL, "npm": UNISWAP_V3_NPM,
        "simulation_identity": {"owner": owner, "token_id": token_id,
                                "source": "current public position, eth_call only", "production_wallet": False,
                                "keystore_loaded": False},
        "position": {"token0": "0x" + f"{position[2]:040x}", "token1": "0x" + f"{position[3]:040x}",
                     "fee": position[4], "tick_lower": _signed(position[5]), "tick_upper": _signed(position[6]),
                     "liquidity": exit_liquidity, "tokens_owed0": position[10], "tokens_owed1": position[11]},
        "decrease_quote": {"amount0": decrease_quote[0], "amount1": decrease_quote[1]},
        "steps": [
            {"action": "decreaseLiquidity", "calldata": decrease},
            {"action": "collect", "calldata": collect},
            {"action": "burn", "calldata": burn},
            *[{"action": "revoke", **item} for item in revokes],
        ],
        "atomic_simulation": {"wrapper": "multicall(bytes[])", "calldata": multicall,
                              "result": multicall_result, "gas_estimate": multicall_gas, "ok": True},
        "eip1559": {"max_fee_per_gas": max_fee_per_gas,
                    "max_priority_fee_per_gas": max_priority_fee_per_gas},
        "estimated_max_cost_wei": (multicall_gas + sum(x["gas_estimate"] for x in revokes))
                                  * max_fee_per_gas,
        "broadcast_count": 0, "signed": False, "transaction_hashes": [],
    }
    assert open_report["broadcast_count"] == exit_report["broadcast_count"] == 0
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "C5_OPEN_DRY_RUN.json").write_text(json.dumps(open_report, indent=2, sort_keys=True) + "\n")
    (out_dir / "C5_EXIT_DRY_RUN.json").write_text(json.dumps(exit_report, indent=2, sort_keys=True) + "\n")
    (out_dir / "C5_OPEN_DRY_RUN.md").write_text(_markdown_open(open_report))
    (out_dir / "C5_EXIT_DRY_RUN.md").write_text(_markdown_exit(exit_report))
    return open_report, exit_report


def _markdown_open(report: dict[str, Any]) -> str:
    cap = report["position_cap"]
    return f"""# C5 开仓 dry-run\n\n- Base block: `{report['latest_block']}`\n- pool: `{report['pool']['address']}` (Uniswap v3 WETH/USDC 0.05%)\n- PositionCap: `{cap['position_cap_usd']:.4f} U`; planned: `{cap['planned_notional_usd']:.2f} U`\n- tick range: `{report['mint_intent']['tick_lower']} .. {report['mint_intent']['tick_upper']}`\n- slippage hard limit: `{report['mint_intent']['slippage_bps']} bps`\n- approve: exact amounts only; full calldata is in JSON\n- mint simulate: `{report['mint_simulation']['ok']}`; gas: `{report['mint_simulation']['gas_estimate']}`\n- five preflights: `{report['preflight']}`\n- signed: `false`; keystore loaded: `false`; **broadcast_count: `0`**\n\n此报告只证明构建与 eth_call 管路；不构成 C6 放行或 live 入场许可。\n"""


def _markdown_exit(report: dict[str, Any]) -> str:
    return f"""# C5 退出 dry-run\n\n- Base block: `{report['latest_block']}`\n- evidence token id: `{report['simulation_identity']['token_id']}` (public position, eth_call only)\n- sequence: `decreaseLiquidity → collect → burn → approve(0)`\n- atomic decrease/collect/burn simulate: `{report['atomic_simulation']['ok']}`\n- atomic gas estimate: `{report['atomic_simulation']['gas_estimate']}`\n- revoke count: `2`; each amount is `0`\n- signed: `false`; keystore loaded: `false`; **broadcast_count: `0`**\n\n完整逐步 calldata、multicall calldata、模拟返回值与 gas 均在 JSON。\n"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--rpc-url", default="https://mainnet.base.org")
    args = parser.parse_args()
    run(args.out_dir, args.rpc_url)
    print(f"C5 dry-runs written to {args.out_dir}; broadcast_count=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
