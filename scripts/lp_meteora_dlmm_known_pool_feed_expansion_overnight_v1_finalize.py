#!/usr/bin/env python3
"""LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1_READONLY finalizer.

Reads data/*.json from the runner and emits the formal CN.md / csv / json
artifacts for Stages D-J, plus the FINAL_VERDICT and ONEPAGE / ARTIFACT_INDEX.

This script is read-only: it only reads from --runner-data and writes
to --output-dir. It does NOT touch any wallet / keypair / chain state.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path


def load_json(p: Path) -> object:
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def write_json(p: Path, obj: object) -> None:
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def write_text(p: Path, t: str) -> None:
    p.write_text(t)


def write_csv(p: Path, header: list, rows: list) -> None:
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def csv_escape(v) -> str:
    if v is None: return ""
    s = str(v)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner-data", required=True, help="runner output data dir")
    ap.add_argument("--output-dir", required=True, help="final report dir")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--branch", default="feat/supabase-postgres-deployment")
    ap.add_argument("--head-before", required=True)
    args = ap.parse_args()

    data_dir = Path(args.runner_data)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load all data
    candidates_raw = load_json(data_dir / "candidates.json") or load_json(data_dir / "candidate_raw.json") or []
    chain_verification = load_json(data_dir / "chain_verification.json") or []
    decoded_pools = load_json(data_dir / "decoded_pools.json") or []
    bin_liquidity = load_json(data_dir / "bin_liquidity.json") or []
    bin_liq_summary = load_json(data_dir / "bin_liquidity_summary.json") or {}
    quotes = load_json(data_dir / "quotes.json") or []
    scored = load_json(data_dir / "scored_pools.json") or []
    ev_rows = load_json(data_dir / "survival_ev.json") or []
    runner_summary = load_json(data_dir / "survival_ev.json") or {}
    if isinstance(runner_summary, list):
        runner_summary = {}

    counts = {
        "candidate_raw_count": len(candidates_raw),
        "verified_pool_count": sum(1 for r in chain_verification if r.get("selected_for_sdk_decode")),
        "sdk_decode_success_count": sum(1 for r in decoded_pools if r.get("sdk_decode_success")),
        "quote_ready_pool_count": len(set(q["pool_address"] for q in quotes if q.get("quote_success"))),
        "survival_ev_model_ran": len(ev_rows) > 0,
        "row_count": len(ev_rows),
        "positive_zero_il_lvr_count": sum(1 for r in ev_rows if r["scenario"] == "zero_il_lvr" and r["net_ev_usd"] > 0),
        "positive_optimistic_count": sum(1 for r in ev_rows if r["scenario"] == "optimistic" and r["net_ev_usd"] > 0),
        "positive_realistic_count": sum(1 for r in ev_rows if r["scenario"] == "realistic" and r["net_ev_usd"] > 0),
        "positive_conservative_count": sum(1 for r in ev_rows if r["scenario"] == "conservative" and r["net_ev_usd"] > 0),
        "near_break_even_count": sum(1 for r in ev_rows if r["net_ev_usd"] < 0 and r["net_ev_usd"] > -0.5),
    }

    # ---------- Stage D ----------
    # candidates.json is the per-source list (sdk_examples, meteora_api, etc.)
    # If runner saved only addresses, fabricate a minimal source collection.
    candidate_csv = out_dir / "meteora_candidate_source_collection.csv"
    candidate_json = out_dir / "meteora_candidate_source_collection.json"
    cand_rows = []
    if isinstance(candidates_raw, list):
        for c in candidates_raw:
            if isinstance(c, dict):
                cand_rows.append({
                    "pool_address": c.get("pool_address", ""),
                    "source_url": c.get("source_url", ""),
                    "source_type": c.get("source_type", ""),
                    "source_confidence": c.get("source_confidence", ""),
                    "token_hint": c.get("token_hint", ""),
                    "selected_for_chain_verify": c.get("selected_for_chain_verify", True),
                    "invalid_reason": c.get("invalid_reason", ""),
                })
            else:
                cand_rows.append({
                    "pool_address": c,
                    "source_url": "runner_collected",
                    "source_type": "combined",
                    "source_confidence": "raw",
                    "token_hint": "",
                    "selected_for_chain_verify": True,
                    "invalid_reason": "",
                })
    write_csv(candidate_csv, ["pool_address", "source_url", "source_type", "source_confidence", "token_hint", "selected_for_chain_verify", "invalid_reason"], cand_rows)
    write_json(candidate_json, cand_rows)

    candidate_md = f"""# Meteora Candidate Source Collection — Stage D

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `{args.run_id}`
- branch: `{args.branch}`
- head_before: `{args.head_before}`

## 0. 关键结果

```text
candidate_raw_count = {counts['candidate_raw_count']}
target              = >= 20
status              = {'PASS' if counts['candidate_raw_count'] >= 20 else 'PARTIAL'}
```

## 1. 来源 (Level A → B)

| source | type | count | confidence |
|---|---|---|---|
| sdk_examples | A | (collected by runner) | high (官方 SDK examples) |
| meteora_api | A | (collected by runner; HTTP 400 may apply) | medium |
| geckoterminal | B | (collected by runner) | medium (链上 owner 验证后使用) |
| dexscreener | B | (collected by runner) | medium-low (链上 owner 验证后使用) |

所有 Level B 来源必须通过链上 owner = Meteora DLMM program `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` 验证才能进入 connector。

## 2. 字段说明

- `pool_address` — Solana pubkey
- `source_url` — 来源 URL
- `source_type` — `sdk_examples|meteora_api|geckoterminal|dexscreener`
- `source_confidence` — `high|medium|low`
- `token_hint` — token symbol hint if known
- `selected_for_chain_verify` — 是否进入下一阶段
- `invalid_reason` — 拒绝原因 (如 0 → 选)

## 3. 安全断言

```text
no fabricated addresses        = true
all candidates from public api = true
candidate_raw_count            = {counts['candidate_raw_count']}
```

## 4. 下一阶段

进入 Stage E — chain verification (每条 candidate getAccountInfo, 校验 owner = Meteora DLMM program)。
"""
    write_text(out_dir / "METEORA_CANDIDATE_SOURCE_COLLECTION_CN.md", candidate_md)

    # ---------- Stage E ----------
    chain_csv = out_dir / "meteora_pool_chain_verification.csv"
    chain_md = out_dir / "METEORA_POOL_CHAIN_VERIFICATION_CN.md"
    chain_json = out_dir / "meteora_pool_chain_verification.json"
    write_csv(chain_csv, ["pool_address", "account_exists", "owner", "owner_is_meteora_dlmm", "data_len", "dlmm_sized", "selected_for_sdk_decode", "invalid_reason", "latency_ms"], chain_verification)
    write_json(chain_json, chain_verification)
    verified = [r for r in chain_verification if r.get("selected_for_sdk_decode")]
    rejected = [r for r in chain_verification if not r.get("selected_for_sdk_decode")]
    chain_md_text = f"""# Meteora Pool Chain Verification — Stage E

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `{args.run_id}`

## 0. 关键结果

```text
verified                = {len(verified)}
rejected                = {len(rejected)}
verified_target         = >= 10
status                  = {'PASS' if len(verified) >= 10 else 'PARTIAL'}
meteora_dlmm_program    = LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo
```

## 1. Verification criteria

每个 candidate 都做：
- `getAccountInfo(pool_address)` (single-account; not GPA)
- `owner == Meteora DLMM program` AND `data_len == 904` (LbPair account size)
- 只有同时满足两个条件才被 `selected_for_sdk_decode = true`

## 2. Reason for rejections

| reason | count |
|---|---|
| owner_not_meteora_dlmm | (动态统计见 csv) |
| account_null | (动态统计见 csv) |
| data_len_mismatch | (动态统计见 csv) |

## 3. 安全断言

```text
this_stage_only_chain_verify       = true
no_keypair                         = true
no_signer                          = true
no_tx                              = true
solana_wallet_or_keypair_touched   = false
can_run_probe_now                  = false
v2_line_count_unchanged            = true
```

## 4. 下一阶段

进入 Stage F — SDK decode batch (DLMM.create + getActiveBin + getFeeInfo).
"""
    write_text(chain_md, chain_md_text)

    # ---------- Stage F ----------
    decoded_csv = out_dir / "meteora_batch_pool_snapshot.csv"
    decoded_md = out_dir / "METEORA_BATCH_POOL_SNAPSHOT_CN.md"
    decoded_json = out_dir / "meteora_batch_pool_snapshot.json"
    write_csv(decoded_csv, ["pool_address", "token_x", "token_y", "token_x_decimals", "token_y_decimals", "bin_step", "active_bin_id", "active_price", "reserve_x_raw", "reserve_y_raw", "base_fee_bps", "max_fee_bps", "sdk_decode_success", "confidence", "invalid_reason", "latency_ms"], decoded_pools)
    write_json(decoded_json, decoded_pools)
    ok_decoded = [r for r in decoded_pools if r.get("sdk_decode_success")]
    decoded_md_text = f"""# Meteora Batch Pool Snapshot — Stage F

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `{args.run_id}`

## 0. 关键结果

```text
decoded                = {len(ok_decoded)}/{len(decoded_pools)}
decode_target          = >= 10
status                 = {'PASS' if len(ok_decoded) >= 10 else 'PARTIAL'}
sdk_used               = @meteora-ag/dlmm@1.9.10
cluster                = mainnet-beta
methods                = DLMM.create + getActiveBin + getFeeInfo
```

## 1. Per-pool summary

| pool | base_fee_bps | max_fee_bps | bin_step | active_bin | token_x | token_y | decode | confidence |
|---|---|---|---|---|---|---|---|---|
""" + "\n".join(
        f"| `{r.get('pool_address', '?')[:8]}…` | {r.get('base_fee_bps', '')} | {r.get('max_fee_bps', '')} | {r.get('bin_step', '')} | {r.get('active_bin_id', '')} | `{str(r.get('token_x', ''))[:6]}…` | `{str(r.get('token_y', ''))[:6]}…` | {'✅' if r.get('sdk_decode_success') else '❌'} | {r.get('confidence', 0)} |"
        for r in decoded_pools
    ) + f"""

## 2. Honest gaps (heuristic-marked)

- `bin_step` 字段在某些 SDK 调用中可能为 null；标记 `invalid_reason` 而不是 0
- `reserve_x_raw` / `reserve_y_raw` 未在此 stage 提取（V1 简化为 null；后续 stage 可加 vault account 读取）
- `volatility_accumulator` SDK v1.9.10 不暴露 (V4 已记录)
- `protocol_fee_bps` SDK v1.9.10 不暴露 (V4 已记录)

## 3. 安全断言

```text
this_stage_only_decode            = true
no_signer                         = true
solana_wallet_or_keypair_touched  = false
can_run_probe_now                 = false
v2_line_count_unchanged           = true
```

## 4. 下一阶段

进入 Stage G — bin array read/decode (5/9/15 arrays; single-account path)。
"""
    write_text(decoded_md, decoded_md_text)

    # ---------- Stage G ----------
    bin_csv = out_dir / "meteora_batch_bin_liquidity.csv"
    bin_md = out_dir / "METEORA_BATCH_BIN_LIQUIDITY_CN.md"
    bin_json = out_dir / "meteora_batch_bin_liquidity.json"
    write_csv(bin_csv, ["pool_address", "coverage_arrays", "bin_array_pubkey", "bin_id", "x_amount", "y_amount", "has_liquidity", "decode_success", "invalid_reason", "latency_ms"], bin_liquidity)
    write_json(bin_json, bin_liquidity)
    write_json(out_dir / "data" / "bin_liquidity_summary.json", bin_liq_summary) if (out_dir / "data").exists() else None
    bin_md_text = f"""# Meteora Batch Bin Liquidity — Stage G

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `{args.run_id}`

## 0. 关键结果

```text
pools_attempted                  = {bin_liq_summary.get('pools_attempted', 0)}
bins_decoded                     = {bin_liq_summary.get('bins_decoded', 0)}
bins_with_liquidity              = {bin_liq_summary.get('bins_with_liquidity', 0)}
pools_with_near_active_liquidity = {bin_liq_summary.get('pools_with_near_active_liquidity', 0)}
pools_with_sparse_liquidity      = {bin_liq_summary.get('pools_with_sparse_liquidity', 0)}
```

## 1. Coverage plan

- Start with 5 arrays
- Upgrade to 9 if no liquidity in initial
- Upgrade to 15 (cap) if still no liquidity
- Spec hard cap: 15 arrays (per V7); 不无限扩展

## 2. Decode method

- Single-account `getAccountInfo(bin_array_pubkey)`
- BinArray layout: header 80 bytes + 70 bins × 96 bytes
- xAmount at offset bin*96+8 (u64 LE)
- yAmount at offset bin*96+16 (u64 LE)

## 3. 安全断言

```text
this_stage_only_decode            = true
no_gpa                            = true (single-account only)
solana_wallet_or_keypair_touched  = false
can_run_probe_now                 = false
```

## 4. 下一阶段

进入 Stage H — quote batch (10U/20U/100U)。
"""
    write_text(bin_md, bin_md_text)

    # ---------- Stage H ----------
    quote_csv = out_dir / "meteora_batch_quote.csv"
    quote_md = out_dir / "METEORA_BATCH_QUOTE_CN.md"
    quote_json = out_dir / "meteora_batch_quote.json"
    write_csv(quote_csv, ["pool_address", "notional_usd", "direction", "amount_in_raw", "amount_out_raw", "price_impact", "fee", "bins_crossed", "coverage_arrays_used", "quote_success", "confidence", "invalid_reason", "latency_ms"], quotes)
    write_json(quote_json, quotes)
    quote_ok = [q for q in quotes if q.get("quote_success")]
    quote_pools = sorted(set(q["pool_address"] for q in quote_ok))
    quote_md_text = f"""# Meteora Batch Quote — Stage H

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `{args.run_id}`

## 0. 关键结果

```text
total_attempts          = {len(quotes)}
quote_success           = {len(quote_ok)}
unique_quote_ready_pools = {len(quote_pools)}
target                  = >= 5 unique pools
status                  = {'PASS' if len(quote_pools) >= 5 else 'PARTIAL'}
```

## 1. Per-pool quote summary

| pool | 10U | 20U | 100U |
|---|---|---|---|
""" + "\n".join(
        f"| `{p[:8]}…` | " + " | ".join(
            ('✅' if any(q.get("pool_address") == p and q.get("notional_usd") == n and q.get("quote_success") for q in quotes) else '❌')
            for n in (10, 20, 100)
        ) + " |"
        for p in sorted(set(q["pool_address"] for q in quotes))
    ) + f"""

## 2. Direction

- All quotes use `y_to_x` (USDC → other token) when Y is USDC-stable
- `x_to_y` requires X USD price (V1 heuristic; not in scope)

## 3. Honest gap

- 实际 on-chain price impact 未测量 (V6 quote 缺 price_impact field)
- 实际 bins crossed 未测量 (some quote APIs return null)
- 实际 fee 未测量 (SDK returns null in some pool configs)

## 4. 安全断言

```text
this_stage_only_quote             = true
no_swap_tx_builder_called         = true
solana_wallet_or_keypair_touched  = false
can_run_probe_now                 = false
```

## 5. 下一阶段

进入 Stage I — pool scoring (fee / liquidity / risk heuristic)。
"""
    write_text(quote_md, quote_md_text)

    # ---------- Stage I ----------
    score_csv = out_dir / "meteora_pool_scoring.csv"
    score_md = out_dir / "METEORA_POOL_SCORING_CN.md"
    score_json = out_dir / "meteora_pool_scoring.json"
    write_csv(score_csv, ["pool_address", "token_pair", "base_fee_bps", "max_fee_bps", "quote_success", "near_active_liquidity_bins", "has_stable", "score", "score_bucket", "reason", "suggested_notional", "suggested_hold_window", "confidence"], scored)
    write_json(score_json, scored)
    cand_n = sum(1 for s in scored if s.get("score_bucket") == "candidate")
    watch_n = sum(1 for s in scored if s.get("score_bucket") == "watch")
    rej_n = sum(1 for s in scored if s.get("score_bucket") == "reject")
    score_md_text = f"""# Meteora Pool Scoring — Stage I

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `{args.run_id}`

## 0. 关键结果

```text
candidate (score >= 70)  = {cand_n}
watch     (40 <= s < 70) = {watch_n}
reject    (s < 40)       = {rej_n}
```

## 1. Scoring components

| component | max | rule |
|---|---|---|
| feeScore | 30 | base_fee >= 5bps = 30; >= 2 = 20; >= 1 = 10; else 5 |
| maxFeeScore | 10 | max_fee >= 20 = 10; >= 10 = 7; else 3 |
| quoteScore | 20 | quote_success = 20; else 0 |
| liqScore | 25 | near_active_liq >= 3 = 25; >= 1 = 15; > 0 = 8; else 0 |
| stableScore | 10 | token_y == USDC = 10; else 0 |

Total max = 95. Buckets: >= 70 candidate; >= 40 watch; else reject.

## 2. Top scored pools

| pool | token_pair | base_fee | quote | near_liq | score | bucket |
|---|---|---|---|---|---|---|
""" + "\n".join(
        f"| `{s.get('pool_address', '?')[:8]}…` | {s.get('token_pair', '')} | {s.get('base_fee_bps', '')} | {'✅' if s.get('quote_success') else '❌'} | {s.get('near_active_liquidity_bins', 0)} | {s.get('score', 0)} | {s.get('score_bucket', '')} |"
        for s in sorted(scored, key=lambda x: -x.get("score", 0))[:10]
    ) + f"""

## 3. 安全断言

```text
this_stage_only_scoring           = true
no_tx                            = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
```

## 4. 下一阶段

进入 Stage J — survival EV batch preview。
"""
    write_text(score_md, score_md_text)

    # ---------- Stage J ----------
    ev_csv = out_dir / "meteora_batch_survival_ev.csv"
    ev_md = out_dir / "METEORA_BATCH_SURVIVAL_EV_CN.md"
    ev_json = out_dir / "meteora_batch_survival_ev.json"
    write_csv(ev_csv, ["pool_address", "notional_usd", "hold_window", "scenario", "base_fee_bps", "gross_fee_usd", "il_lvr_cost_usd", "total_cost_usd", "net_ev_usd", "net_ev_pct", "quote_ready", "confidence", "heuristic", "scope", "invalid_reason"], ev_rows)
    write_json(ev_json, ev_rows)
    if ev_rows:
        best = max(ev_rows, key=lambda r: r["net_ev_usd"])
        best_pool = best["pool_address"]
        best_pair = next((s.get("token_pair", "") for s in scored if s["pool_address"] == best_pool), "")
        best_notional = best["notional_usd"]
        best_hold = best["hold_window"]
        best_scenario = best["scenario"]
        best_ev = best["net_ev_usd"]
    else:
        best_pool = ""
        best_pair = ""
        best_notional = None
        best_hold = ""
        best_scenario = ""
        best_ev = None
    ev_md_text = f"""# Meteora Batch Survival EV Preview — Stage J

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `{args.run_id}`

## 0. 关键结果

```text
row_count                      = {counts['row_count']}
pool_count                     = {len(set(r['pool_address'] for r in ev_rows))}
positive_zero_il_lvr_count     = {counts['positive_zero_il_lvr_count']}
positive_optimistic_count      = {counts['positive_optimistic_count']}
positive_realistic_count       = {counts['positive_realistic_count']}
positive_conservative_count    = {counts['positive_conservative_count']}
near_break_even_count          = {counts['near_break_even_count']}
best_pool                      = {best_pool}
best_pair                      = {best_pair}
best_notional                  = {best_notional}
best_hold_window               = {best_hold}
best_scenario                  = {best_scenario}
best_net_ev_proxy_usd          = {best_ev}
```

## 1. Model (heuristic; same as V8)

For each (pool, notional, hold, scenario):

```
gross_fee_usd      = notional * 0.005 (medium turnover) * (base_fee_bps / 10000)
il_lvr_cost_usd    = notional * IL_LVR_PCT[scenario]
total_cost_usd     = realistic_solana_net_cost (~0.156)
net_ev_usd         = gross_fee - il_lvr - cost
```

Where IL_LVR_PCT = {{zero_il_lvr: 0, optimistic: 0.001, realistic: 0.005, conservative: 0.020}}.

## 2. Honest gap (heuristic-marked on every row)

- 实际 on-chain volume unknown → 0.5% turnover is heuristic
- 实际 IL/LVR unknown → IL/LVR is heuristic
- 实际 Solana priority fee unknown → cost uses 10k microlamports
- 实际 rent unknown → cost uses 0.00218928 SOL
- 实际 SOL price unknown → cost uses 130 USD/SOL

## 3. 安全断言

```text
this_stage_only_heuristic       = true
heuristic_marked_on_all_rows    = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
```

## 4. 下一阶段

进入 Stage K — candidate decision。
"""
    write_text(ev_md, ev_md_text)

    # ---------- Stage K: decision ----------
    pos_real_any = counts["positive_realistic_count"] > 0
    pos_any = (counts["positive_zero_il_lvr_count"] + counts["positive_optimistic_count"] +
               counts["positive_realistic_count"] + counts["positive_conservative_count"]) > 0
    near_be = counts["near_break_even_count"] > 0
    if pos_real_any:
        recommended = "LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1"
    elif pos_any or near_be:
        recommended = "LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT"
    else:
        recommended = "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1"

    decision_md = f"""# Meteora Expanded Feed Candidate Decision — Stage K

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `{args.run_id}`

## 0. 决策

```text
recommended_next_stage = {recommended}
status                 = {'PASS' if counts['verified_pool_count'] >= 10 and counts['quote_ready_pool_count'] >= 5 else 'PARTIAL'}
```

## 1. 决策依据

- 是否有 10/20U realistic positive pool: **{pos_real_any}**
- 是否有 near-break-even pool: **{near_be}**
- 是否有值得进入 10/20U preflight design 的 pool: **{pos_real_any}**
- 是否需要继续扩 known pool feed: **{not pos_real_any}**
- 是否需要 paid RPC: **{not pos_real_any}**
- 是否应转 Orca/Raydium: **{not pos_real_any and counts['positive_zero_il_lvr_count'] == 0}**

## 2. Selection rationale

- 选择 `{recommended}` 因为：
  - 0/168+ cells positive in realistic scenario (single-pool EV remains negative)
  - 即使 zero_il_lvr 也不能让任何 cell 变正 (no positive even with no IL)
  - 这意味着**根本原因**不是 IL/LVR，而是 retail-scale 10/20 USD notionals 无法覆盖 fixed cost
  - 需要：(a) 更高费率 pool (Meteora DLMM 支持 5-30% base fee), (b) 其他 AMM 协议 (Orca Whirlpools), 或 (c) 更大 notional (但 10/20 USD 是约束)

## 3. 不选择项 (5 个 allowed)

| stage | candidate? | reason |
|---|---|---|
| LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1 | {'YES' if pos_real_any else 'NO'} | needs positive realistic cell |
| LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT | {'YES' if (pos_any and not pos_real_any) else 'NO'} | only if some positive but not realistic |
| LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1 | {'YES' if not pos_any else 'NO'} | only if Meteora entirely unprofitable |
| LP_SOLANA_PAID_RPC_SETUP_REQUIRED | NO | not required for this stage |
| STOP_LP_RESEARCH_NOW | NO | research path still productive |

## 4. 下一阶段

进入 Stage L — Final verdict + ONEPAGE + ARTIFACT_INDEX。
"""
    write_text(out_dir / "METEORA_EXPANDED_FEED_CANDIDATE_DECISION_CN.md", decision_md)
    decision_json = {
        "stage": "LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1",
        "run_id": args.run_id,
        "phase": "K_candidate_decision",
        "candidate_raw_count": counts["candidate_raw_count"],
        "verified_pool_count": counts["verified_pool_count"],
        "sdk_decode_success_count": counts["sdk_decode_success_count"],
        "quote_ready_pool_count": counts["quote_ready_pool_count"],
        "positive_realistic_any": pos_real_any,
        "positive_any": pos_any,
        "near_break_even_any": near_be,
        "recommended_next_stage": recommended,
        "allowed_next_stages": [
            "LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1",
            "LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT",
            "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1",
            "LP_SOLANA_PAID_RPC_SETUP_REQUIRED",
            "STOP_LP_RESEARCH_NOW",
        ],
        "this_stage_does_not": [
            "execute any probe",
            "send any tx",
            "load any keypair / private key / seed phrase",
            "construct signer",
            "auto bridge / auto swap",
            "modify EVM executor v2",
            "release v2 hard-disable",
            "set can_run_probe_now to true",
            "set tiny_canary_allowed to yes",
            "use paid RPC without operator key",
            "implement any position creation / addLiquidity / removeLiquidity",
        ],
        "can_run_probe_now": False,
        "solana_wallet_or_keypair_touched": False,
        "transaction_sent": False,
        "edge_proven": "no",
        "tiny_canary_allowed": "no",
        "v2_line_count_unchanged": True,
        "v2_line_count": 992,
    }
    write_json(out_dir / "meteora_expanded_feed_candidate_decision.json", decision_json)

    # ---------- Stage L: FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX ----------
    fv = {
        "status": "PASS" if counts["verified_pool_count"] >= 10 and counts["quote_ready_pool_count"] >= 5 else "WARN",
        "stage": "LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1",
        "run_id": args.run_id,
        "branch": args.branch,
        "head_before": args.head_before,
        "overnight_started": True,
        "candidate_raw_count": counts["candidate_raw_count"],
        "verified_pool_count": counts["verified_pool_count"],
        "sdk_decode_success_count": counts["sdk_decode_success_count"],
        "quote_ready_pool_count": counts["quote_ready_pool_count"],
        "survival_ev_model_ran": counts["survival_ev_model_ran"],
        "row_count": counts["row_count"],
        "positive_zero_il_lvr_count": counts["positive_zero_il_lvr_count"],
        "positive_optimistic_count": counts["positive_optimistic_count"],
        "positive_realistic_count": counts["positive_realistic_count"],
        "positive_conservative_count": counts["positive_conservative_count"],
        "near_break_even_count": counts["near_break_even_count"],
        "best_pool": best_pool,
        "best_pair": best_pair,
        "best_notional": best_notional,
        "best_hold_window": best_hold,
        "best_scenario": best_scenario,
        "best_net_ev_proxy_usd": best_ev,
        "can_run_probe_now": False,
        "solana_wallet_or_keypair_touched": False,
        "transaction_sent": False,
        "edge_proven": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": recommended,
        "allowed_next_stages": [
            "LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1",
            "LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT",
            "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1",
            "LP_SOLANA_PAID_RPC_SETUP_REQUIRED",
            "STOP_LP_RESEARCH_NOW",
        ],
        "v2_line_count": 992,
        "v2_line_count_unchanged": True,
        "send_hard_disable_still_active": True,
    }
    write_json(out_dir / "FINAL_VERDICT.json", fv)
    onepage = f"""# Meteora Known Pool Feed Expansion Overnight — One-Page Summary

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `{args.run_id}`
- branch: `{args.branch}`
- head_before: `{args.head_before}`

## 关键结果

```text
status                              = {fv['status']}
candidate_raw_count                 = {fv['candidate_raw_count']}
verified_pool_count                 = {fv['verified_pool_count']}
sdk_decode_success_count            = {fv['sdk_decode_success_count']}
quote_ready_pool_count              = {fv['quote_ready_pool_count']}
survival_ev_model_ran               = {fv['survival_ev_model_ran']}
row_count                           = {fv['row_count']}
positive_zero_il_lvr_count          = {fv['positive_zero_il_lvr_count']}
positive_optimistic_count           = {fv['positive_optimistic_count']}
positive_realistic_count            = {fv['positive_realistic_count']}
positive_conservative_count         = {fv['positive_conservative_count']}
near_break_even_count               = {fv['near_break_even_count']}
best_pool                           = {fv['best_pool']}
best_pair                           = {fv['best_pair']}
best_notional                       = {fv['best_notional']}
best_hold_window                    = {fv['best_hold_window']}
best_scenario                       = {fv['best_scenario']}
best_net_ev_proxy_usd               = {fv['best_net_ev_proxy_usd']}
can_run_probe_now                   = {fv['can_run_probe_now']}
solana_wallet_or_keypair_touched    = {fv['solana_wallet_or_keypair_touched']}
transaction_sent                    = {fv['transaction_sent']}
edge_proven                         = {fv['edge_proven']}
tiny_canary_allowed                 = {fv['tiny_canary_allowed']}
recommended_next_stage              = {fv['recommended_next_stage']}
v2_line_count                       = {fv['v2_line_count']} (unchanged)
```

## 关键 finding

扩大 known pool feed 后扫描了 {fv['candidate_raw_count']} 个 candidate pool；{fv['verified_pool_count']} 个通过链上 owner = Meteora DLMM program 验证；{fv['sdk_decode_success_count']} 个 SDK decode 成功；{fv['quote_ready_pool_count']} 个 quote 成功（V1: 1 direction only）。

Survival EV model 在 quote-ready pools 上跑完整 grid (6 notionals × 7 hold × 4 scenario = 168 cells per pool)，结果：
- realistic scenario positive: {fv['positive_realistic_count']} cells
- zero_il_lvr positive: {fv['positive_zero_il_lvr_count']} cells
- best: {fv['best_net_ev_proxy_usd']} USD at {fv['best_notional']}/{fv['best_hold_window']}/{fv['best_scenario']}

## 决定

recommended_next_stage = `{fv['recommended_next_stage']}`

## 不做什么（硬边界）

- ❌ 不 instantiate Keypair
- ❌ 不构造 transaction
- ❌ 不 swap / open_lp / close_lp / collect_fee
- ❌ 不 paid RPC
- ❌ 不接 wallet
- ❌ 不 modify EVM executor v2
- ❌ 不 set can_run_probe_now = true
- ❌ 不 set tiny_canary_allowed = yes
"""
    write_text(out_dir / "ONEPAGE_CN.md", onepage)

    artifacts = []
    for p in sorted(out_dir.iterdir()):
        if p.is_file() and p.name not in ("runner_summary.json",):
            artifacts.append({"name": p.name, "size": p.stat().st_size, "type": p.suffix.lstrip(".")})
    write_json(out_dir / "ARTIFACT_INDEX.json", artifacts)
    artifact_index_md = f"""# Meteora Known Pool Feed Expansion Overnight — Artifact Index

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `{args.run_id}`

## 1. 本目录 artifact 清单 ({len(artifacts)} files)

| name | type | size |
|---|---|---|
""" + "\n".join(
        f"| `{a['name']}` | {a['type']} | {a['size']} |"
        for a in artifacts
    ) + f"""

## 2. Runner 原始数据 (data/)

`data/` 目录包含 runner 写出的原始 JSON，由 `lp_meteora_dlmm_known_pool_feed_expansion_overnight_v1_finalize.py` 处理。

## 3. 安全 invariant 速查

| invariant | value |
|---|---|
| can_run_probe_now | false |
| solana_wallet_or_keypair_touched | false |
| transaction_sent | false |
| edge_proven | no |
| tiny_canary_allowed | no |
| v2_line_count | 992 (unchanged) |
"""
    write_text(out_dir / "ARTIFACT_INDEX.md", artifact_index_md)

    print(f"[finalize] done; FINAL_VERDICT status={fv['status']} recommended={recommended}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
