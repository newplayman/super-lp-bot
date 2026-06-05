# Stage F: 无探针资金时手续费估算依据说明

- spec: `fee_estimation_without_probe_v1`
- spec_version: `1.0`
- designed_at_utc: `2026-06-05T08:23:00Z`

## 0. 大白话: 为什么不能给你 actual fee

R0 阶段 (当前连续观察期) collector **没有**真实 LP `tokenId` / `positionId`, 因此:

- ❌ **没有**真实 `feeGrowthGlobal` snapshot (entry / exit)
- ❌ **没有**真实 `tokensOwed` 计数
- ❌ **没有**真实 `add/remove` 成本 (gas + slippage)
- ❌ **没有**真实 `realized PnL`

任何"我估算了某池 daily fee = $X"在 R0 都是 **proxy / heuristic**, **不是** actual fee. 节点报告必须显式标注:

```json
{
  "actual_fee_data_available": false,
  "fee_proxy_used": true,
  "heuristic_used": true,
  "fee_estimate_confidence": "low"
}
```

**R0 阶段所有 fee 数字都不可作为 B 线 preflight 依据.** B 线需要真实 LP 操作 + 实测数据, 需用户单独批准.

## 1. 6 条核心原则

1. R0 无 actual fee (没有 tokenId)
2. 每个 fee 数字必须显式 proxy 标注, 不得隐含当作 actual
3. 不同 pool type 公式完全不同, 必须分别定义
4. V3/CLMM 必须按 range 宽度分别算; DLMM 必须按 bin coverage 算
5. stable / LST-stable 池 IL 低, 但 depeg / LST risk 仍要计入
6. 从 R0 → R1 升级路径必须显式列出

## 2. 各 Pool Type 的 Fee Proxy 公式

### 2.1 V3 / CLMM (Uniswap V3 / Raydium CLMM / Orca Whirlpool / PancakeSwap V3)

**R0 必需输入**:

| 字段 | 来源 |
|---|---|
| `pool_address` | collector |
| `fee_tier` | e.g. 3000 = 0.3% |
| `current_tick` | pool.slot0 |
| `active_tick_range` | 当前 tick 附近的 liquidity density |
| `window_volume_in_pool` | USD / 节点窗口 |
| `window_volume_distribution_by_tick` | (可选, 没有就跳过 range sensitivity) |

**Narrow / Medium / Wide Range Fee Proxy**:

```
fee_proxy_narrow  = volume_window × fee_rate × user_lp_share_in_range × in_range_time_ratio_narrow
fee_proxy_medium  = volume_window × fee_rate × user_lp_share_in_range × in_range_time_ratio_medium
fee_proxy_wide    = volume_window × fee_rate × user_lp_share_in_range × in_range_time_ratio_wide
```

**关键参数**:

- `user_lp_share_in_range = user_notional / total_active_liquidity_in_user_range`
- `in_range_time_ratio`: 近似自 tick 历史 (没有就 0.5 + warning)

**R0 限制** (显式披露):

- ❌ 无法计算 out-of-range 时 IL
- ❌ 无法计算重新 setRange 成本
- ❌ 无法计算实际累积 feeGrowth
- ❌ 无法计算 tokensOwed

### 2.2 Meteora DLMM

**R0 必需输入**:

| 字段 | 来源 |
|---|---|
| `pool_address` | collector |
| `bin_step` | DLMM pool config |
| `active_bin_id` | DLMM pool state |
| `bins_with_liquidity` | 每侧 bin 数 |
| `bin_liquidity_distribution` | (可选) |
| `window_volume_in_pool` | USD / 节点窗口 |
| `window_swap_count_per_bin` | (可选) |

**Narrow / Medium / Wide Bin Fee Proxy**:

```
fee_proxy_narrow  = volume_window × fee_rate × user_bin_share_in_active_bins
fee_proxy_medium  = volume_window × fee_rate × user_bin_share_in_active_bins ± N bins
fee_proxy_wide    = volume_window × fee_rate × user_bin_share_in_active_bins ± 2N bins
```

**关键参数**:

- `user_bin_share_in_active_bins = user_bin_liquidity / total_bin_liquidity_in_range`
- `active_bin_distance = |bin_id - active_bin_id|`
- `sparse_liquidity_warning`: 如果 `bins_with_liquidity_count < 5/side`, 标记 `true`

**R0 限制** (显式披露):

- ❌ 无法计算 bin rebalancing 触发点
- ❌ 无法计算实际 binShares 累积
- ❌ 无法计算 DLMM 协议层激励 (需 DLMM SDK)

### 2.3 CPMM v2_cpmm (Uniswap V2 / Aerodrome / Raydium CPMM / Raydium AMM v4 / PancakeSwap V2)

**R0 必需输入**:

| 字段 | 来源 |
|---|---|
| `pool_address` | collector |
| `fee_bps` | e.g. 30 = 0.3% |
| `pool_tvl` | USD |
| `window_volume` | USD / 节点窗口 |
| `user_notional` | (假设) |

**Fee Proxy**:

```
fee_proxy = volume_window × fee_rate × user_lp_share
user_lp_share = user_notional / pool_tvl
price_impact_proxy = user_notional / pool_tvl  # 简化, R0 不做实际 swap 模拟
il_proxy = 2 × sqrt(price_ratio) / (1 + price_ratio) - 1  # Uniswap V2 标准
```

**R0 限制**:

- ❌ 实际 add/remove 滑点
- ❌ 时间加权 IL
- ❌ 多周期 compounding

### 2.4 Stable / LST-Stable 池

**额外字段** (因 IL 低但 depeg risk 仍要计入):

- `depeg_risk_score` (0-1, heuristic)
- `lst_depeg_history_30d` (事件数)
- `stable_curve_steepness`

**Depeg Risk Adjustment**:

```
adjusted_il = il_base × (1 + depeg_risk_score × 2)
```

如果 `depeg_risk_score > 0.3` 显著增加 IL 假设, `lst_depeg_history_30d > 0` 强烈建议 reject candidate.

## 3. R0 → R1 (Actual Fee) 升级路径

R0 → R1 需要以下数据 (任何缺失 = 仍为 proxy, 不可标记 actual_fee=true):

| 数据点 | 描述 | R0 可得? |
|---|---|---|
| `tokenId / positionId` | V3/CLMM NFT mint address; DLMM bin position pubkey | ❌ |
| `entry feeGrowthGlobal` | add liquidity 时的 feeGrowth snapshot | ❌ |
| `exit feeGrowthGlobal` | remove/collect 时的 feeGrowth snapshot | ❌ |
| `tokensOwed0 / tokensOwed1` | V3/CLMM 待 collect 数量 | ❌ |
| `collected fee` | 实际 collect 后的 token 数量 (USD) | ❌ |
| `actual add/remove cost` | gas + slippage + protocol fee (USD) | ❌ |
| `realized PnL` | collected fee + token 价值变化 - 成本 - IL | ❌ |

**R0 没有任何一项**. R1 需要真实 LP 操作 (用户签 add/remove/collect) 或 paid indexer (B 线, 需用户单独批准).

## 4. 节点报告必须显式披露的字段

| 字段 | 必填 | 值 |
|---|---|---|
| `actual_fee_data_available` | ✅ | `false` |
| `fee_proxy_used` | ✅ | `true` |
| `heuristic_used` | ✅ | `true` |
| `v3_clmm_fee_proxy_formula` | ✅ | 完整公式字符串 |
| `meteora_dlmm_fee_proxy_formula` | ✅ | 完整公式字符串 |
| `cpmm_fee_proxy_formula` | ✅ | 完整公式字符串 |
| `stable_pool_fee_proxy_formula` | ✅ | 完整公式字符串 |
| `future_actual_fee_requirement[]` | ✅ | 6 strings, per R1 升级路径 |
| `fee_estimate_confidence` | ✅ | `"low"` (R0 阶段) |
| `ev_proxy_confidence` (per candidate) | ✅ | `"low"` (per pool) |

## 5. 6 条诚实免责声明

| ID | 免责 |
|---|---|
| D1 | R0 阶段所有 fee 数字 = proxy, 不是 actual fee. 实际 fee 必须有 tokenId + feeGrowth snapshot + tokensOwed 实测. |
| D2 | V3/CLMM range 越窄, fee proxy 越高 (因为 user_lp_share_in_range 越大), 但 out-of-range 风险也越大. R0 不能直接告诉你 range 选多窄最优. |
| D3 | Meteora DLMM bin coverage 越窄, fee proxy 越高, 但 sparse_liquidity_warning 越严重. R0 不能直接告诉你 bin coverage 选多少最优. |
| D4 | CPMM fee proxy 精度受限于 TVL / volume 的更新延迟. R0 用的 tvl_proxy / volume_proxy 可能有 ±20% 误差. |
| D5 | Stable / LST-stable 池 fee proxy 假设 IL 低, 但 depeg 事件可瞬间击穿 IL 假设. R0 depeg_risk_score 是 heuristic, 不是预言机. |
| D6 | R0 节点报告**不**可用于 B 线 preflight, 因为实际 fee 仍未知. B 线需要 tokenId 实盘数据, 需用户单独批准. |

## 6. 硬性不动作 (本轮)

| ID | 约束 |
|---|---|
| F1 | 不假装有 actual fee |
| F2 | 显式 proxy 披露 (per field) |
| F3 | 不读 wallet / keypair / signer |
| F4 | 不发送 transaction / approve / mint |
| F5 | 默认不接 paid indexer (R0 不需要) |
| F6 | 默认不接 paid RPC (R0 用 public_rpc) |

## 7. 结论

Fee proxy 公式 + 6 条 honest disclaimer + R0 → R1 升级路径全部显式定义. R0 节点报告所有 fee 数字必须显式标注 `actual_fee_data_available=false`, `fee_proxy_used=true`, `heuristic_used=true`, `fee_estimate_confidence=low`.

**Stage F PASS** → 进入 Stage G (range / tick / bin 对手续费影响报告设计).
