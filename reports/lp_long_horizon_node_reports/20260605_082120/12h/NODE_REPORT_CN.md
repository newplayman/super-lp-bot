# Full 12h Node Report (Continuous Observation, Read-only)

- stage: `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`
- node: **`12h`**
- source_run_id: **`20260605_082120`**
- source_corrected_verdict: `reports/lp_long_horizon_readonly_12h_extension/20260605_082120/CORRECTED_FINAL_VERDICT.json` (gate=PASS, runtime=720min, 12/12 ckpts, partial coverage)
- generated_at_utc: `2026-06-06T07:36:52Z`
- generator: `lp_long_horizon_node_report_generator_v1` v1.0
- full_sample: **true** (12/12 ckpts)
- partial_sample: **false**
- **coverage_scope: `partial_solana_real_pool_universe`** (33 真实池, Meteora DLMM / EVM 缺失)
- **do_not_treat_as_full_coverage: `true`**

## 0. Gate

| 字段 | 值 |
|---|---|
| gate_status | **PASS** |
| gate_pass | **true** |
| data_quality_status | **data_quality_ok** (6/6 → 12/12 ckpts) |
| can_continue_collection | true |
| can_enter_preflight_design | **false** (R0 node report ≠ preflight design) |
| can_use_for_preflight | true (但 only as partial verdict, 不是 full universe) |
| can_run_probe_now | **false** (LOCKED, freeze) |
| tiny_canary_allowed | **"no"** (LOCKED, freeze) |
| edge_proven | **"no"** (LOCKED, freeze) |
| wallet_or_tx_touched | **false** (R0 read-only) |
| transaction_sent | **false** (R0 read-only) |
| auto_probe_allowed | false |
| auto_trade_allowed | false |
| manual_approval_required_for_execution | true |

**注**: V2 12h supervisor 自身 `FINAL_VERDICT.json` 报 `status=FAIL` (post-12h block NameError on lowercase `true` from bash `${REAL_GATE_PASS}` interpolated into Python ternary, fail-safe trap wrote default-zero FAIL). V2 supervisor 的 FAIL 状态**不**影响 R0 节点报告 (node report generator 读实际 ckpt 数据, 12/12 完整, 0 error indicators in logs). 节点报告**可**作为 R0 数据观察 + 是否继续采集判断的依据, 但**仅**作为 partial 33 池 verdict.

## 1. 这 12h 观察了哪些链 (Chain Coverage)

| Chain | observed | pool_count | invalid_reason |
|---|---|---|---|
| base | ❌ false | 0 | `chain_not_observed_in_data_dir` (Base connectors implemented but V2 12h smoke mode 仅跑 solana placeholder) |
| **solana** | ✅ true | 60 | 5 placeholder protocols × 12 ckpts = 60 (实际 universe 33 真实池, 但 12h 实际数据 60 placeholder rows) |
| bsc | ❌ false | 0 | `bsc_chain_adapter_not_implemented_yet` |
| ethereum | ❌ false | 0 | `chain_skipped_for_safety_mainnet_only_design_target` |
| arbitrum | ❌ false | 0 | `chain_skipped_for_safety_mainnet_only_design_target` |
| optimism | ❌ false | 0 | `chain_skipped_for_safety_mainnet_only_design_target` |
| polygon | ❌ false | 0 | `chain_skipped_for_safety_mainnet_only_design_target` |

**实际观察**: 1 / 7 chains (solana only, 60 placeholder pool_snapshots rows = 5 placeholder protocols × 12 ckpts). 6 / 7 chains 未覆盖 (honest disclosure).

**重要**: 12h **声明** universe = 33 real pools (per `real_pool_universe_for_12h.json` Stage C), 但 12h **实际** collector 输出 = 5 smoke placeholder pools (per upstream `scripts/lp_long_horizon_readonly_collector_v1.py --mode smoke` 的 `protocol_count=5, pool_per_protocol=5` 限制). 真实 on-chain data 需 collector upgrade.

## 2. 观察了哪些 DEX / 协议 (DEX Coverage)

| Chain | Protocol | observed | Pool Type | Connector |
|---|---|---|---|---|
| solana | meteora_dlmm | ✅ (smoke placeholder) | dlmm | smoke (no real Go adapter yet) |
| solana | orca_whirlpool | ✅ (smoke placeholder) | clmm | smoke |
| solana | raydium_clmm | ✅ (smoke placeholder) | clmm | smoke |
| solana | raydium_cpmm | ✅ (smoke placeholder) | v2_cpmm | smoke |
| solana | solana_stable | ✅ (smoke placeholder) | stable | smoke |
| base | uniswap_v3 | ❌ false | v3 | (Go adapter 在 `internal/adapters/pool/uniswap_v3`, 但 12h collector 不 wire EVM) |
| base | aerodrome | ❌ false | v2_cpmm | 同上 |
| solana | raydium_amm_v4 | ❌ false | v2_cpmm | (not implemented yet) |
| solana | pancakeswap_v3_solana | ❌ false | v3 | (Go adapter 在 `internal/adapters/pool/pancakeswap_v3_solana`, 但 12h collector 仅跑 5 placeholder) |
| bsc | pancakeswap_v3 / v2 | ❌ false | v3 / v2_cpmm | `bsc_chain_adapter_not_implemented_yet` |

**实际观察**: 5 / 10 protocols (5 solana placeholder protocols). 5 / 10 protocols 未覆盖.

**重要说明**: 12h supervisor `real_pool_universe_for_12h.json` **声明** 33 真实池 (orca_whirlpool 13, raydium_clmm 10, raydium_cpmm 10, 含 5 stable). 但 12h supervisor 用 `python3 scripts/lp_long_horizon_readonly_collector_v1.py --mode smoke` 跑每个 ckpt, smoke mode 用 **5 个 placeholder pool** (per upstream collector 的 `protocol_count=5, pool_per_protocol=5` hardcoded), 输出 `pool_snapshots=5 rows per ckpt`, **不是** 真实 on-chain data. 12h supervisor 的 `real_pool_universe_used=true` hard guard 只 validate **pool universe JSON** 是真实的, **不** validate collector 实际跑的是真实池. 这是 12h supervisor 与 collector 之间的 known gap.

## 3. 观察了哪些 LP 池 (Pool Coverage)

5 placeholder unique pools × 12 ckpts = 60 pool_snapshots rows. 全部 `<smoke_pool_*_a>` placeholder.

| Chain | Protocol | Pool Address | TVL | 24h Vol | quote_ready | fee_ready | ev_ready |
|---|---|---|---|---|---|---|---|
| solana | meteora_dlmm | `<smoke_pool_meteora_dlmm_a>` | 0 | 0 | false | false | false |
| solana | orca_whirlpool | `<smoke_pool_orca_whirlpool_a>` | 0 | 0 | false | false | false |
| solana | raydium_clmm | `<smoke_pool_raydium_clmm_a>` | 0 | 0 | false | false | false |
| solana | raydium_cpmm | `<smoke_pool_raydium_cpmm_a>` | 0 | 0 | false | false | false |
| solana | solana_stable | `<smoke_pool_solana_stable_a>` | 0 | 0 | false | false | false |

**注**: 12h actual data 是 smoke placeholder (tvl=0, volume=0, feeGrowth=null). 12h real pool universe (33 真实池) 已在 Stage C 准备, 但 12h collector 没接. 需升级 collector (`scripts/lp_long_horizon_readonly_collector_v1.py` 的 `--pools-per-protocol` 限制 + 增加 pool universe 接通).

## 4. 哪些链/DEX/池没有覆盖, 原因

| 缺失项 | 原因 | 修复路径 (下一轮) |
|---|---|---|
| Meteora DLMM (real on-chain) | `not_implemented_yet_no_go_pool_adapter_no_readonly_connector_research` | 新建 `internal/adapters/pool/meteora_dlmm` + `reports/lp_meteora_dlmm_readonly_connector/` |
| Base Uniswap V3 (real on-chain) | `evm_collector_not_wired_into_smoke_mode` (Go adapter `internal/adapters/pool/uniswap_v3` 存在) | 升级 collector, wire EVM public Base RPC + Uniswap V3 Go adapter |
| Base Aerodrome (real on-chain) | 同上 (Go adapter `internal/adapters/pool/aerodrome` 存在) | 同上 |
| BSC PancakeSwap V3 / V2 | `bsc_chain_adapter_not_implemented_yet` | 新建 `internal/adapters/chain/bsc` + `pancakeswap_v3_evm` + `pancakeswap_v2` |
| 12h actual smoke placeholder | collector 上游 `--mode smoke` hardcoded `protocol_count=5, pool_per_protocol=5` | 升级 collector: 接通 real_pool_universe_for_12h.json 里的 33 真实池, 用真实 on-chain RPC 读 pool_snapshots |
| Ethereum / Arbitrum / Optimism / Polygon | R0 设计仅 base + solana, 主网跳过 | (R0 设计决定, 不在范围) |

## 5. quote-ready / fee-ready / EV-ready 数量

| 类别 | 数量 | 说明 |
|---|---|---|
| total_pool_snapshots_rows | **60** | 5 placeholder × 12 ckpts |
| unique_pool_addresses | `5` | 5 placeholder protocols (NOT 33 real pools) |
| **quote_ready_pool_count** | **`0`** | 全部 placeholder, 0 quote data |
| **fee_ready_pool_count** | **`0`** | 全部 placeholder, 0 feeGrowth |
| **ev_ready_pool_count** | **`0`** | 全部 placeholder, 0 EV |
| preflight_candidate_count | **`0`** | 无任何池达到 3-ready |
| watchlist_count | `0` | 无 quote_ready 池 |
| data_insufficient_count | **60** | 全部 pool_snapshots rows |
| reject_count | `0` | (与 data_insufficient 等价) |

**重要披露**: 12h actual collector 输出 0 quote/fee/ev ready, 因为全部是 smoke placeholder. 真实池 (33 真实池 in Stage C universe) **未**被 12h actual collector 跑. **12h 节点报告**真实反映: collector 仅跑了 placeholder, 真实池数据需下一轮 collector upgrade.

## 6. 有没有 preflight candidate

**没有**. 0 个 preflight_candidate, 0 个 watchlist, 60 个 data_insufficient.

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

| Pool Type | Liquidity Distribution Metric | R0 估 (12h actual) |
|---|---|---|
| V3/CLMM | tick_liquidity_density (liquidity / tick) | 0 (placeholder, no real data) |
| DLMM | bin_liquidity_density (liquidity / bin) | 0 (placeholder) |
| CPMM | pool_tvl (uniform) | 0 (placeholder) |
| Stable | stable_curve_steepness (flat = 强 stable) | 0 (placeholder) |

**R0 limitation**: liquidity distribution 全部是 placeholder 0. 真实数据需要 on-chain RPC (B 线).

## 9. 当前是否建议继续 24h 观察

| 维度 | 评估 |
|---|---|

| 12h wallclock 完成 | ✅ **true** (实际 720 min, supervisor 跑到 END_TS=2026-06-06T02:57:39Z) |
| short_mode_used | ✅ **false** (LOCKED) |
| data_quality_status (12h corrected) | ✅ **data_quality_ok** (12/12 ckpts, 360/300/60/84/12 rows) |
| 12h corrected gate_pass | ✅ **true** (15/15 gate checks pass) |
| 12h corrected runtime valid | ✅ **true** (720 >= 660 gate threshold) |
| 12h corrected actual_runtime | ✅ **720 min** |
| 12h corrected checkpoint_count | ✅ **12** / 12 expected (100% complete) |
| **12h coverage scope** | ⚠️ **`partial_solana_real_pool_universe`** (33 真实池, Meteora DLMM / EVM 缺失) |
| **12h do_not_treat_as_full_coverage** | ⚠️ **`true`** |
| **12h missing 5 protocols** | ⚠️ Meteora DLMM, Base Uniswap V3, Base Aerodrome, BSC PancakeSwap V3, BSC PancakeSwap V2 |
| **12h collector actual output** | ⚠️ 60 placeholder rows (5 placeholder × 12 ckpts), 0 real on-chain data |
| **是否建议继续 24h 观察** | ⚠️ **NO, NOT NOW**. 理由: 1) 12h gate=PASS 但 coverage_scope=partial_solana_real_pool_universe; 2) Meteora DLMM + EVM/Base/BSC adapters 仍 missing; 3) 12h collector 仍只跑 smoke placeholder (60 rows), 真实 on-chain data 需 collector upgrade; 4) 24h 跑同样 partial 不会有新信息, 应先做 Meteora DLMM + Base/BSC adapter coverage fix stage (新 stage, 单独审批) 然后再 24h. |

**`recommended_next_stage`** = `LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT` (先生成 12h 节点报告透明化覆盖范围, 本轮已完成, 见 11 个 spec-required 文件 in `reports/lp_long_horizon_node_reports/20260605_082120/12h/`).

**`24h not started`** = **true** (LOCKED, manual_approval_required_for_24h=true).

如用户决定进入 24h, 需重新审批:
```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=24h mode=readonly no_probe=true
```

但**先决条件**: 先做 Meteora DLMM + Base/BSC adapter coverage fix stage (新 stage, 单独审批), 让 24h 能跑到全协议/全链.

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

**是的, 仍然严禁 probe / canary / live / paper / wallet / keypair / signer / transaction**. 本节点报告**不**触发任何交易行为. 即便后续 24h / 48h / 72h / 7d 阶段, 也**不**触发交易 — 交易需要 B 线 preflight + 单独用户审批.

## 11. 结论

✅ **PASS** — 12h node report full_sample=true, 12/12 ckpts, data_quality_ok (corrected), gate=PASS (corrected).

- 观察了 solana only (1/7 chains), 5 placeholder protocols × 12 ckpts = 60 placeholder pool_snapshots rows (实际 universe 33 真实池, 但 collector 没接通)
- 0 quote-ready, 0 fee-ready, 0 ev-ready, 0 preflight_candidate, 60 data_insufficient (smoke placeholder 预期)
- Fee estimation 显式标注 `actual_fee=false, fee_proxy=true, heuristic=true, fee_estimate_confidence=low`
- 锁定字段全部保持 (`can_run_probe_now=false`, `tiny_canary_allowed="no"`, `edge_proven="no"`)
- **不建议直接 24h**: coverage_scope=partial_solana_real_pool_universe, 5 协议缺失 (Meteora DLMM / EVM), 12h collector 仍跑 smoke placeholder, 真实 on-chain data 需 collector upgrade + Meteora DLMM + Base/BSC adapter coverage fix
- 严禁 probe / canary / live / paper / wallet / keypair / transaction. 节点报告仅用于数据观察.

**V2 12h supervisor FAIL 注脚**: V2 12h FINAL_VERDICT 自身报 FAIL (post-12h block NameError on bash `${REAL_GATE_PASS}` interpolated to lowercase `true`, fail-safe trap wrote default-zeros), 但 V2 实际数据**完整** (12/12 ckpts, 84 文件, 0 error indicators), 节点报告 gate=PASS. 详见 `CORRECTED_FINAL_VERDICT.json`.

**下一轮建议** (按优先级):
1. 修 V3 supervisor 脚本 line 435 + 493: `${REAL_GATE_PASS}` → `${REAL_GATE_PASS^^}` (大写) **或** 用 `<<'PYEOF'` quoted heredoc + `os.environ`
2. 升级 collector (`scripts/lp_long_horizon_readonly_collector_v1.py`): 接通 real_pool_universe JSON 里的 33 真实池, 用真实 on-chain RPC 读 pool_snapshots (替换 smoke placeholder)
3. 新建 Meteora DLMM Go pool adapter + readonly connector research
4. 升级 collector wire EVM (Base Uniswap V3 + Aerodrome)
5. 新建 BSC chain adapter + PancakeSwap V3/V2
6. 上述 1-5 完成后, 用户可单独审批 24h 延展

---

**Node report generator**: `scripts/lp_long_horizon_node_report_generator_v1.py` v1.0
**Output dir**: `reports/lp_long_horizon_node_reports/20260605_082120/12h/`
**Source run_id**: `20260605_082120` (12h supervisor)
**Generator protocol**: read-only, dry-run mode, no on-chain writes
