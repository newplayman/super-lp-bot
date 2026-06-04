# Input Evidence Audit — Stage B

- stage: `LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1`
- run_id: `20260604_021913`
- branch: `feat/supabase-postgres-deployment`
- head_before: `852c976`

## 0. 阶段目标

定向高质量 Meteora DLMM 池源扩展 — 优先 high-fee / high-volume / USDC-anchor / 适合 10/20U 零售 LP 探测的池。
**不是随机 repeat**。本轮聚焦于公开 source 中能打中 (a) base fee >= 5% (b) 有可访问 active bin 附近 liquidity (c) quote 友好的池。

## 1. 上游证据链读取清单

| # | path | 角色 | 状态 |
|---|---|---|---|
| 1 | `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/FINAL_VERDICT.json` | **直接上游** — 上一轮结束态 | OK |
| 2 | `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/ONEPAGE_CN.md` | 上一轮一句话总结 | OK |
| 3 | `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/METEORA_BATCH_SURVIVAL_EV_CN.md` | EV model 公式与参数 | OK |
| 4 | `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_batch_survival_ev.csv` | 2688 行 EV 网格 (16 pool × 6×7×4) | OK |
| 5 | `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/METEORA_POOL_SCORING_CN.md` | Scoring 权重与 top table | OK |
| 6 | `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_pool_scoring.csv` | 16 个池 scoring 详情 | OK |
| 7 | `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/FINAL_VERDICT.json` | V7 spec hard cap 15 arrays; SOL/USDC 0 liquidity at ±10% | OK |
| 8 | `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/FINAL_VERDICT.json` | V4 connector 真链上 state — SOL/USDC 0.02% / X/USDC 1.5% | OK |
| 9 | `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/FINAL_VERDICT.json` | V2 RPC discovery: paid_rpc 必要 | OK |

## 2. 关键事实确认

```text
previous stage = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1
verified_pool_count   = 16     (确认)
sdk_decode_success    = 16     (确认)
quote_ready           = 0      (确认)
positive_realistic    = 0      (确认 — 2688 cells 全负)
near_break_even       = 1344   (50%, zero_il_lvr + optimistic 子集)
best_net_ev_proxy_usd = -0.15338 USD (2000 notional / 15m / zero_il_lvr)
recommended_next_stage (上一轮) = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT
```

## 3. 上一轮终判解读

- 16 个池覆盖 8 个 token pair；
- 16 个池 base_fee 范围 0.02–2.5 bps (即 0.0002%–0.025%) — **全部远低于本轮目标的 5% 阈值**；
- 全部 16 池 active bin ±10% 范围内 0 bins with liquidity (V7 + overnight 重复发现)；
- scoring 满分 95，top 池仅 37/95 → 全部 reject bucket；
- structural finding: 零售 10–2000 USD LP 在 Meteora DLMM SOL/USDC 类 (bin_step=2) 上不可行，固定成本 ~$0.156 主导。

## 4. 本轮转向

`LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT` (随机 repeat) 已评估为低价值。本轮改为 **targeted**:

| 维度 | 上一轮 | 本轮 |
|---|---|---|
| candidate 来源 | sdk examples + DexScreener/GeckoTerminal 随机 | Meteora UI top + UI-sortable by fee/volume + Jupiter pair |
| 目标 base fee | 无 (0.02–2.5 bps) | **>= 5%** (500 bps) 或 max_fee >= 20% (2000 bps) |
| token 偏好 | 无 | USDC / SOL / USDT / 主流 LST |
| quote notionals | 10/20/100/500/1000/2000 | 10/20 (核心) + 100/500/1000/2000 (扩展) |
| 单池 cost | ~$0.156 | ~$0.156 (不变) |
| 决策 | 全部 reject → repeat | **本轮目标 high-fee memecoin 池** — 期望 base_fee 0.5–30% (50–3000 bps) 大幅超过 5% |

## 5. 假设 (heuristic, 待 F 阶段验证)

- 高 fee Meteora DLMM 池 (5%–30% base) 几乎都是 memecoin / 投机 token；
- 它们的 bin_step 通常 100–2000 (≠ SOL/USDC bin_step=2)，单 bin 覆盖价格范围更宽；
- 10/20U quote 在此类高 bin_step 池上更有机会命中 1 个 bin。

## 6. 风险与诚实性

- 高 fee memecoin 池的 **impermanent loss / rug risk** 远高于 SOL/USDC；任何 positive net_ev 都仍受 IL/LVR 模型误差主导。
- 真实 volume 未知；fee capture 全 heuristic。
- **本轮目标不是验证 edge，而是确认"是否存在有 quote 数据的高 fee 候选"**。如果连 quote 都没有，则按 spec 推荐 Orca。

## 7. 上一轮 → 本轮显式转向

```text
上一轮   = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1
         = 50 candidate → 16 verified → 16 decoded → 0 quote → 0 positive
         = recommended: repeat (low value)

本轮     = LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1
         = 30-80 candidate (UI top + UI high-fee + Jupiter popular)
         → chain verify
         → SDK decode
         → targeted quote (10/20)
         → if 0 quote_ready → recommend Orca Whirlpools
         → if quote_ready but all negative → recommend Orca
         → if any positive near-break-even high-fee → recommend 10/20U probe preflight design
```

## 8. 安全边界继承

```text
can_run_probe_now               = false (locked)
tiny_canary_allowed             = no    (locked)
solana_wallet_or_keypair_touched = false (locked)
transaction_sent                = false (locked)
v2_line_count                   = 992 (unchanged)
send_hard_disable_still_active  = true
```

## 9. 下一阶段

进入 Stage C — 目标池源策略 (high_fee_dlmm / high_volume_dlmm / high_liquidity_near_active / quote_friendly / token_quality)。
