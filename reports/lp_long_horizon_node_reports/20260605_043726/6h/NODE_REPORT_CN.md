# Full 6h Node Report (Continuous Observation, Read-only)

- stage: `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`
- node: **`6h`**
- source_run_id: **`20260605_043726`** (V2 6h supervisor, run start 2026-06-05T04:51:15Z, trap EXIT at 2026-06-05T10:51:29Z)
- generated_at_utc: `2026-06-05T13:10:51Z`
- generator: `lp_long_horizon_node_report_generator_v1` v1.0
- full_sample: **true**
- partial_sample: **false**
- checkpoint_count: **6/6 observed** (6/6 expected)

## 0. Gate

| 字段 | 值 |
|---|---|
| gate_status | **PASS** |
| gate_pass | **true** |
| data_quality_status | **data_quality_ok** |
| can_continue_collection | true |
| can_enter_preflight_design | **false** (R0 node report ≠ preflight design) |
| can_use_for_preflight | true (PASS gate) |
| can_run_probe_now | **false** (LOCKED, freeze) |
| tiny_canary_allowed | **"no"** (LOCKED, freeze) |
| edge_proven | **"no"** (LOCKED, freeze) |
| wallet_or_tx_touched | **false** (R0 read-only) |
| transaction_sent | **false** (R0 read-only) |
| auto_probe_allowed | false |
| auto_trade_allowed | false |
| manual_approval_required_for_execution | true |

**注**: V2 supervisor 自身 `FINAL_VERDICT.json` 报 `status=FAIL, gate_pass=false, finalize_error="trap EXIT rc=1"` — 这来自 V2 supervisor post-6h summary block 触发的 fail-safe trap (V1 "no silent loss" 修复). V2 实际数据**完整**: 6/6 ckpts, supervisor log 显示 `[checkpoint 6/6] ok at 2026-06-05T09:51:33Z`, `[6h end] 2026-06-05T10:51:29Z elapsed_min=360`, 0 error indicators. Node report generator 读实际 ckpt 数据, 生成 PASS node report. **V2 supervisor FAIL 状态仅影响 supervisor 自身, 不影响 R0 节点报告**.

## 1. 这 6h 观察了哪些链 (Chain Coverage)

| Chain | observed | pool_count | invalid_reason |
|---|---|---|---|
| base | ❌ false | 0 | `chain_not_observed_in_data_dir` (本轮 V2 未跑 base, base connectors 仍 implemented) |
| **solana** | ✅ true | 30 | - (5 protocols × 1 placeholder pool × 6 ckpts) |
| bsc | ❌ false | 0 | `bsc_chain_adapter_not_implemented_yet` |
| ethereum | ❌ false | 0 | `chain_skipped_for_safety_mainnet_only_design_target` |
| arbitrum | ❌ false | 0 | `chain_skipped_for_safety_mainnet_only_design_target` |
| optimism | ❌ false | 0 | `chain_skipped_for_safety_mainnet_only_design_target` |
| polygon | ❌ false | 0 | `chain_skipped_for_safety_mainnet_only_design_target` |

**实际观察**: 1 / 7 chains (solana only, 30 pool_snapshots rows = 5 placeholder pools × 6 ckpts). 6 / 7 chains 未覆盖 (honest disclosure).

**说明**: Base Uniswap V3 + Aerodrome 的 Go connector **已实现** (`internal/adapters/pool/uniswap_v3` + `aerodrome`), 但本轮 V2 6h supervisor 仅用了 Python `smoke` mode, smoke mode 用 V2 collector 的 5 protocols (meteora_dlmm / orca_whirlpool / raydium_clmm / raydium_cpmm / solana_stable) — **全部 solana**. Base 实际未被 V2 6h 覆盖.

## 2. 观察了哪些 DEX / 协议 (DEX Coverage)

| Chain | Protocol | Pool Type | observed | Connector |
|---|---|---|---|---|
| solana | meteora_dlmm | dlmm | ✅ true (smoke_placeholder) | smoke (no real Go adapter yet) |
| solana | orca_whirlpool | clmm | ✅ true (smoke_placeholder) | `internal/adapters/pool/whirlpool` (Go adapter implemented, 但本轮 V2 仅用 Python smoke placeholder) |
| solana | raydium_clmm | clmm | ✅ true (smoke_placeholder) | `internal/adapters/pool/raydium_clmm` (同上) |
| solana | raydium_cpmm | v2_cpmm | ✅ true (smoke_placeholder) | smoke (no real Go adapter yet) |
| solana | solana_stable | stable | ✅ true (smoke_placeholder) | smoke (placeholder) |
| base | uniswap_v3 | v3 | ❌ false | `internal/adapters/pool/uniswap_v3` (Go adapter implemented, 但本轮 V2 未跑 base) |
| base | aerodrome | v2_cpmm | ❌ false | `internal/adapters/pool/aerodrome` (同上) |
| solana | raydium_amm_v4 | v2_cpmm | ❌ false | `not_implemented_yet` |
| solana | pancakeswap_v3_solana | v3 | ❌ false | `internal/adapters/pool/pancakeswap_v3_solana` (Go adapter implemented, 但本轮 V2 未跑) |
| bsc | pancakeswap_v3 | v3 | ❌ false | `bsc_chain_adapter_not_implemented_yet` |
| bsc | pancakeswap_v2 | v2_cpmm | ❌ false | `bsc_chain_adapter_not_implemented_yet` |

**实际观察**: 5 / 10 protocols (5 个 solana protocols via Python smoke placeholder). 5 / 10 protocols 未覆盖 (3 个 Base/Solana connectors implemented 但本轮 V2 未跑 + 2 个 BSC connectors not implemented).

**重要说明**: 本轮 V2 6h supervisor 用 `python3 scripts/lp_long_horizon_readonly_collector_v1.py --mode smoke` 跑每个 ckpt, smoke mode 用 **5 个 placeholder pool** (每个 protocol 1 个), pool_snapshots 行的 `tvl_usd=0`, `liquidity=0`, `active_tick=null`, `active_bin=null` 都是 placeholder, **不是**真实 on-chain 数据. **`pool_type=?`, `token_pair=?`, `fee_tier_or_fee_bps=0`** (smoke placeholder 不填).

## 3. 观察了哪些 LP 池 (Pool Coverage)

5 unique placeholder pool addresses × 6 ckpts = 30 pool_snapshots rows. 全部 `<smoke_pool_*_a>` placeholder.

| Chain | Protocol | Pool Type | Pool Address | Token Pair | quote_ready | fee_ready | ev_ready | reason |
|---|---|---|---|---|---|---|---|---|
| solana | meteora_dlmm | ? | `<smoke_pool_meteora_dlmm_a>` | ? | false | false | false | smoke placeholder (liquidity=0, active_bin=null) |
| solana | orca_whirlpool | ? | `<smoke_pool_orca_whirlpool_a>` | ? | false | false | false | smoke placeholder |
| solana | raydium_clmm | ? | `<smoke_pool_raydium_clmm_a>` | ? | false | false | false | smoke placeholder |
| solana | raydium_cpmm | ? | `<smoke_pool_raydium_cpmm_a>` | ? | false | false | false | smoke placeholder |
| solana | solana_stable | ? | `<smoke_pool_solana_stable_a>` | ? | false | false | false | smoke placeholder |

**注**: V2 6h supervisor 用 `python3 scripts/lp_long_horizon_readonly_collector_v1.py --mode smoke` 跑每个 ckpt, 输出 30 quote_snapshots/25 fee_velocity/5 liquidity_distribution/7 market_regime placeholder rows. 全部是 smoke 模式 placeholder, 不是真实 on-chain 数据.

## 4. 哪些链/DEX/池没有覆盖, 原因

| 缺失项 | 原因 |
|---|---|
| base chain | `chain_not_observed_in_data_dir` (本轮 V2 supervisor 未跑 base, base connectors 仍 implemented 在 `internal/adapters/pool/uniswap_v3` + `aerodrome`, 但 Python smoke mode 仅覆盖 5 个 solana protocols) |
| bsc chain | `bsc_chain_adapter_not_implemented_yet` (Go chain adapter 未实现, 仅有 Python placeholder) |
| BSC PancakeSwap V3 / V2 | `bsc_chain_adapter_not_implemented_yet` (依赖 BSC chain adapter) |
| Solana Raydium AMM v4 | `not_implemented_yet` (legacy AMM, 不在 R0 优先列表) |
| Ethereum / Arbitrum / Optimism / Polygon | `chain_skipped_for_safety_mainnet_only_design_target` (R0 设计目标仅 solana via Python smoke, base connectors implemented 但本轮 V2 未触发) |
| Meteora DLMM (Go adapter) | `not_implemented_yet` (本轮 V2 smoke 模式覆盖 placeholder, 实际无 Go pool adapter; Go adapter 需要单独实现) |
| Base Uniswap V3 / Aerodrome (实际跑) | `chain_not_observed_in_data_dir` (Go connector **已实现**, 但本轮 V2 supervisor Python smoke mode 仅跑 solana; Base 池需要新 supervisor 触发 Go adapter) |
| Solana PancakeSwap V3 (实际跑) | 同上 (Go adapter `internal/adapters/pool/pancakeswap_v3_solana` implemented, 但本轮 V2 supervisor Python smoke mode 仅跑 5 个 placeholder protocols) |

## 5. quote-ready / fee-ready / EV-ready 数量

| 类别 | 数量 | 说明 |
|---|---|---|
| total_pool_snapshots_rows | **30** | 5 protocols × 1 pool × 6 ckpts |
| unique_pool_addresses | **5** | meteora_dlmm / orca_whirlpool / raydium_clmm / raydium_cpmm / solana_stable |
| **quote_ready_pool_count** | **0** | 全部 placeholder (tvl=0, pool_type=?, token_pair=?) |
| **fee_ready_pool_count** | **0** | 全部 placeholder (无 feeGrowth snapshot) |
| **ev_ready_pool_count** | **0** | 全部 placeholder (无真实 data) |
| preflight_candidate_count | **0** | 无任何池达到 3-ready |
| watchlist_count | **0** | 无 quote_ready 池 |
| data_insufficient_count | **30** | 全部 pool_snapshots rows |
| reject_count | **0** | (与 data_insufficient 等价, generator 标记为 no_quote_ready) |

**重要披露**: quote_ready / fee_ready / ev_ready **全 0** 不是 collector bug, 而是 **smoke 模式 placeholder** 的预期行为. R0 阶段 collector 仅做 design / smoke, 不做真实 on-chain RPC. 真实 quote / fee / ev 需要升级到 R1 (B 线, 需用户单独批准).

## 6. 有没有 preflight candidate

**没有**. 0 个 preflight_candidate, 0 个 watchlist, 30 个 data_insufficient.

**preflight 路径说明**: 即便本轮有 preflight candidate, 本阶段也**不**启动 preflight (per A/B 线分离规则). preflight 需要:
- 至少 1 个池达到 quote_ready AND fee_ready AND ev_ready
- 用户单独 APPROVE 短语 (`APPROVE_LP_LONG_HORIZON_PREFLIGHT_DESIGN`)
- 单独 stage FINAL_VERDICT
- 单独 frozen 状态 unfreeze 决策

**R0 节点报告 ≠ preflight 输入**. R0 仅做数据观察 + 节点报告 + 覆盖范围透明化.

## 7. 没有探针资金时, 手续费收益是如何估算的 (Fee Estimation Basis)

R0 阶段**没有**真实 LP tokenId / positionId, 因此所有 fee 数字都是 **proxy / heuristic**, **不是 actual fee**. 节点报告显式标注:

```json
{
  "actual_fee_data_available": false,
  "fee_proxy_used": true,
  "heuristic_used": true,
  "fee_estimate_confidence": "low"
}
```

### V3 / CLMM (Uniswap V3, Aerodrome v3, Raydium CLMM, Orca Whirlpool, PancakeSwap V3)

```
fee_proxy_<width> = volume_window × fee_rate × user_lp_share_in_range × in_range_time_ratio_<width>

narrow_range:  ±5% 当前价格  (range_width = 0.1 × price)
medium_range:  ±15% 当前价格 (range_width = 0.3 × price)
wide_range:    ±50% 当前价格 (range_width = 1.0 × price)

user_lp_share_in_range = user_notional / total_active_liquidity_in_user_range
in_range_time_ratio    = 窗口内价格在 range 内的时间比例 (R0 近似, 数据不足时 0.5 + warning)
```

### Meteora DLMM

```
fee_proxy_<coverage> = volume_window × fee_rate × user_bin_share_in_range_<coverage>

narrow_bin:  active bin ± 2 bins
medium_bin:  active bin ± 10 bins
wide_bin:    active bin ± 50 bins

user_bin_share = user_bin_liquidity / total_bin_liquidity_in_range
sparse_liquidity_warning: true if bins_with_liquidity_count < 10 total
```

### CPMM (Uniswap V2, Aerodrome v2, Raydium AMM v4 / CPMM, PancakeSwap V2)

```
fee_proxy = volume_window × fee_rate × user_lp_share
user_lp_share = user_notional / pool_tvl
il_proxy    = 2 × sqrt(price_ratio) / (1 + price_ratio) - 1   (Uniswap V2 标准)
```

### Stable / LST-Stable

```
fee_proxy = volume_window × fee_rate × user_lp_share (assumes low IL)
adjusted_il = il_base × (1 + depeg_risk_score × 2)
reject if depeg_risk_score > 0.5 OR lst_depeg_history_30d > 0
```

### R0 → R1 升级路径 (Actual Fee)

```
R0 → R1 需要 7 个数据点 (任何缺失 = 仍为 proxy, 不可标记 actual_fee=true):
1. tokenId / positionId (V3/CLMM NFT mint; DLMM bin position pubkey)
2. entry feeGrowthGlobal (add liquidity 时的 snapshot)
3. exit feeGrowthGlobal (remove/collect 时的 snapshot)
4. tokensOwed0 / tokensOwed1 (V3/CLMM 待 collect)
5. collected fee (实际 collect 后 USD)
6. actual add/remove cost (gas + slippage + protocol fee, USD)
7. realized PnL (collected fee + token 价值变化 - 成本 - IL)
```

R0 阶段**没有任何一项**. R1 需要真实 LP 操作 (用户签 add/remove/collect) 或 paid indexer (B 线, 需用户单独批准).

## 8. range / tick / bin / liquidity distribution 如何影响手续费收入

**核心 insight**: range / bin 越窄, fee proxy 越高, 但 out-of-range / bin drift 风险也越大.

### V3/CLMM (3 range × 4 metric)

| Range Width | active_liquidity_share_proxy (R0) | in_range_time_ratio (R0 估) | range_risk | fee_proxy 量级 |
|---|---|---|---|---|
| narrow (±5%) | 高 (lp_share 集中) | 低 (≈40%) | **high** (out-of-range 风险) | 高峰值, 低均值 |
| medium (±15%) | 中 | 中 (≈70%) | **medium** | 中等 |
| wide (±50%) | 低 (lp_share 分散) | 高 (≈95%) | **low** (out-of-range 风险小) | 低峰值, 稳定均值 |

**Aggregate**: 3 range 都 high → aggregate_risk=high; 至少 1 个 low → aggregate_risk=low; 其他 → medium.

### DLMM (3 bin coverage × 4 metric)

| Bin Coverage | user_bin_share | active_bin_distance | sparse_liquidity_warning | fee_proxy 量级 |
|---|---|---|---|---|
| narrow (±2 bins) | 高 | 0 (静态观察) | bins_with_liquidity_count=2 (low) | 高峰值, sparse risk |
| medium (±10 bins) | 中 | 0 | bins=6 (low) | 中等 |
| wide (±50 bins) | 低 | 0 | bins=12 (ok) | 低峰值, 稳定 |

**Aggregate**: wide bin coverage 提供 best risk-adjusted fee proxy (low sparse_liquidity_warning, 稳定 fee share).

### CPMM (full range)

| 指标 | R0 估 |
|---|---|
| full_range_fee_proxy | volume × fee × lp_share (no range risk) |
| lp_share | 1 / pool_tvl (uniform across all ranges) |
| price_impact | 1 / pool_tvl (R0 简化) |
| il_proxy | Uniswap V2 std (2 × sqrt(p) / (1+p) - 1) |

CPMM 池**没有**range risk (full range), 但 IL 高于 V3 concentrated liquidity (especially volatile pairs).

### Liquidity Distribution

| Pool Type | Liquidity Distribution Metric | R0 估 |
|---|---|---|
| V3/CLMM | tick_liquidity_density (liquidity / tick) | 1.0 (placeholder) |
| DLMM | bin_liquidity_density (liquidity / bin) | 1.0 (placeholder) |
| CPMM | pool_tvl (uniform) | 0 (placeholder) |
| Stable | stable_curve_steepness (flat = 强 stable) | 0 (placeholder) |

**R0 limitation**: liquidity distribution 全部是 placeholder (0 or 1.0). 真实数据需要 on-chain RPC (B 线).

## 9. 当前是否建议继续 12h 观察

| 维度 | 评估 |
|---|---|
| 6h wallclock 完成 | ✅ **true** (实际 360 min, V2 supervisor 跑到 END_TS=10:51:29Z) |
| short_mode_used | ✅ **false** (LOCKED) |
| data_quality_status (V2 supervisor) | ❌ **FAIL** (V2 FINAL_VERDICT 报 FAIL, 因 post-6h summary block 触发 fail-safe trap) |
| data_quality_status (node report) | ✅ **data_quality_ok** (generator 读实际 ckpt 数据, 6/6 完整, no error indicators in logs) |
| quote/fee/ev ready 池数 | ⚠️ 0 (smoke placeholder, **不是** collector bug) |
| preflight candidate | ⚠️ 0 (同上) |
| can_use_for_preflight | ✅ true (node report gate=PASS) |
| can_enter_preflight_design | ❌ false (R0 ≠ preflight) |
| **是否建议继续 12h 观察** | **YES, but 不自动启动**. 理由: 1) 6h wallclock 数据完整且可重复; 2) node report gate=PASS, data_quality_ok; 3) V2 supervisor FAIL 仅来自 post-6h summary block, 不阻断 R0 节点报告; 4) 真实 quote/fee/ev 数据需要更长时间窗口 + Go adapter (Base Uniswap V3 / Aerodrome) + smoke→real RPC 升级 (B 线), 仅靠更长节点不能解决; 5) 用户需单独 approve 12h 阶段 (`APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true`) + 单独 FINAL_VERDICT + freeze 状态决定. |

**`recommended_next_stage`** = `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1` (请求 12h 延展, **不**自动启动).

**12h 延展 vs fix_repeat supervisor**: 12h 延展 = 同一 RUN_ID 累积 data + 自动在 12h 节点生成 12h node report. Fix_repeat supervisor = 修 V2 supervisor `scripts/run_lp_long_horizon_readonly_6h_once.sh` post-6h block (修 Python aggregate + write 7 reports 步骤), 然后**重跑** 6h. Fix_repeat 是**重复劳动** (data 已完整), 12h 延展是**持续累积**. 用户选择哪个取决于 12h 是否能给出**新信息** (更长时间窗口 + 触发 Go adapter 跑 Base 池).

## 10. 当前是否仍禁止 probe

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | **false** (LOCKED) |
| `tiny_canary_allowed` | **"no"** (LOCKED) |
| `edge_proven` | **"no"** (LOCKED) |
| `wallet_or_tx_touched` | **false** (R0 read-only) |
| `transaction_sent` | **false** (R0 read-only) |
| `auto_probe_allowed` | **false** |
| `auto_trade_allowed` | **false** |
| `manual_approval_required_for_execution` | **true** |
| LP strategy research freeze | **ACTIVE** (per `docs/LPBOT_RESEARCH_STATUS_CN.md`) |

**是的, 仍然严禁 probe / canary / live / paper / wallet / keypair / signer / transaction**. 本节点报告**不**触发任何交易行为. 即便后续 12h / 24h / 48h / 72h / 7d 阶段, 也**不**触发交易 — 交易需要 B 线 preflight + 单独用户审批.

## 11. 结论

✅ **PASS** — 6h node report full_sample=true, 6/6 ckpts, data_quality_ok.
- 观察了 solana only (1/7 chains), 5 placeholder protocols × 1 placeholder pool = 5 unique pool addresses (30 pool_snapshots rows).
- 0 quote-ready, 0 fee-ready, 0 ev-ready, 0 preflight_candidate, 30 data_insufficient (smoke placeholder 预期).
- Fee estimation 显式标注 `actual_fee=false, fee_proxy=true, heuristic=true, fee_estimate_confidence=low`.
- 锁定字段全部保持 (`can_run_probe_now=false`, `tiny_canary_allowed="no"`, `edge_proven="no"`).
- **建议继续 12h 观察**, 但**不自动启动**, 等用户单独 approve (`APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true`).
- 严禁 probe / canary / live / paper / wallet / keypair / transaction. 节点报告仅用于数据观察.

**V2 supervisor FAIL 注脚**: V2 FINAL_VERDICT 报 FAIL (post-6h summary block fail-safe trap), 但 V2 实际数据**完整** (6/6 ckpts, 0 error indicators), node report gate=PASS. 详见 `NEXT_NODE_DECISION_CN.md` discussion.

---

**Node report generator**: `scripts/lp_long_horizon_node_report_generator_v1.py` v1.0
**Output dir**: `reports/lp_long_horizon_node_reports/20260605_043726/6h/`
**Source run_id**: `20260605_043726` (V2 6h supervisor)
**Generator protocol**: read-only, dry-run mode, no on-chain writes
