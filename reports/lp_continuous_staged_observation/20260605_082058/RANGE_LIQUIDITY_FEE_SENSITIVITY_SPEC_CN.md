# Stage G: Range / Tick / Bin 对手续费影响报告设计

- spec: `range_liquidity_fee_sensitivity_spec_v1`
- spec_version: `1.0`
- designed_at_utc: `2026-06-05T08:23:30Z`

## 0. 目的

为每个候选池计算 range / tick / bin 维度对 fee proxy 的影响, 输出 narrow/medium/wide 三种 range 的 fee proxy 对比 + 风险标注.

## 1. 6 条核心原则

1. **每候选必填**: 每个 `selected_for_candidate_review=true` 的池都必须有 range_sensitivity 行
2. **V3/CLMM 三 range**: 必须算 narrow/medium/wide 三种 range 的 fee proxy
3. **DLMM 三 bin coverage**: 必须算 narrow/medium/wide 三种 bin coverage 的 fee proxy
4. **CPMM 满 range**: 池本身就是 full range, 只算 full_range_fee_proxy + lp_share + price_impact + il_proxy
5. **range_risk heuristic**: 来自 range_width + in_range_time_ratio + tick_liquidity_density 三者组合
6. **R0 永远 low confidence**: `fee_estimate_confidence=low` (R0 proxy only)

## 2. V3 / CLMM Range Sensitivity

### Applies to

- uniswap_v3
- aerodrome (v3 mode)
- raydium_clmm
- orca_whirlpool
- pancakeswap_v3
- pancakeswap_v3_solana

### Range Width 定义

| 宽度 | 定义 |
|---|---|
| narrow | ±5% 当前价格 (`range_width = 0.1 × price`) |
| medium | ±15% 当前价格 (`range_width = 0.3 × price`) |
| wide | ±50% 当前价格 (`range_width = 1.0 × price`) |

### 每行字段 (每个候选池应有 3 行: narrow/medium/wide)

| 字段 | 类型 | 必填 | 描述 |
|---|---|---|---|
| `pool_address` | string | ✅ |  |
| `narrow_range_fee_proxy` | number (USD/window) | ✅ |  |
| `medium_range_fee_proxy` | number (USD/window) | ✅ |  |
| `wide_range_fee_proxy` | number (USD/window) | ✅ |  |
| `in_range_time_ratio` | number 0-1 | ✅ | 窗口内价格在 range 内的时间比例 (R0 近似) |
| `out_of_range_time_ratio` | number 0-1 | ✅ | `1 - in_range_time_ratio` |
| `active_liquidity_share_proxy` | number 0-1 | ✅ | `user_notional / total_active_liquidity_in_user_range` |
| `tick_liquidity_density` | number | ✅ | liquidity / tick |
| `range_width` | string enum [narrow, medium, wide] | ✅ | 本行对应宽度 |
| `range_risk` | string enum [low, medium, high] | ✅ | heuristic |

### range_risk 启发式

| 风险 | 触发条件 |
|---|---|
| **low** | wide range + `in_range_time_ratio >= 0.8` + `tick_liquidity_density >= median` |
| **medium** | medium range + `in_range_time_ratio 0.5-0.8` **OR** narrow range + `in_range_time_ratio >= 0.7` |
| **high** | narrow range + `in_range_time_ratio < 0.5` **OR** `tick_liquidity_density < 0.1 × median` |

### Fee Proxy 公式

```
fee_proxy_<width> = volume_window × fee_rate × active_liquidity_share_proxy × in_range_time_ratio_<width>
```

### R0 限制

- ❌ R0 不预测未来 `in_range_time_ratio`, 用窗口内 tick 历史估算
- ⚠️ 数据不足时 `in_range_time_ratio ≈ 0.5` + warning

## 3. Meteora DLMM Range Sensitivity

### Applies to

- meteora_dlmm

### Bin Coverage 定义

| 宽度 | 定义 |
|---|---|
| narrow | active bin ± 2 bins |
| medium | active bin ± 10 bins |
| wide | active bin ± 50 bins |

### 每行字段

| 字段 | 类型 | 必填 | 描述 |
|---|---|---|---|
| `pool_address` | string | ✅ |  |
| `narrow_bin_fee_proxy` | number (USD/window) | ✅ |  |
| `medium_bin_fee_proxy` | number (USD/window) | ✅ |  |
| `wide_bin_fee_proxy` | number (USD/window) | ✅ |  |
| `active_bin_distance` | number | ✅ | 窗口末 active bin 与窗口初 active bin 的 bin 数差, 表征 volatility |
| `bin_liquidity_density` | number | ✅ | liquidity per bin |
| `bins_with_liquidity_count` | integer | ✅ | active bin 两侧非零 bin 总数 |
| `sparse_liquidity_warning` | boolean | ✅ | true if `< 5/side (i.e. < 10 total)` |

### Fee Proxy 公式

```
fee_proxy_<coverage> = volume_window × fee_rate × user_bin_share_in_range_<coverage>
user_bin_share = user_bin_liquidity / total_bin_liquidity_in_range_<coverage>
```

### R0 限制

- ❌ R0 不预测未来 bin drift
- ⚠️ sparse_liquidity 时 narrow/medium coverage 风险高

## 4. CPMM Range Sensitivity

### Applies to

- uniswap_v2
- aerodrome (v2_cpmm mode)
- pancakeswap_v2
- raydium_amm_v4
- raydium_cpmm

### Note

CPMM 池本身就是 full range, 不分 narrow/medium/wide. 只算 `full_range_fee_proxy` + 风险字段.

### 每行字段

| 字段 | 类型 | 必填 | 描述 |
|---|---|---|---|
| `pool_address` | string | ✅ |  |
| `full_range_fee_proxy` | number (USD/window) | ✅ |  |
| `lp_share` | number 0-1 | ✅ | `user_notional / pool_tvl` |
| `price_impact` | number | ✅ | `user_notional / pool_tvl` (R0 简化) |
| `il_proxy` | number (USD/window) | ✅ | `2 × sqrt(price_ratio) / (1 + price_ratio) - 1` (Uniswap V2 标准) |

### R0 限制

- ❌ 不做实际 swap 模拟
- ❌ 不做时间加权 IL
- ❌ 不做多周期 compounding

## 5. Stable / LST-Stable 特殊处理

### Applies to

- curve
- meteora_stable
- aerodrome_stable
- uniswap_v3_stable_fees

### 额外字段

| 字段 | 类型 | 必填 | 描述 |
|---|---|---|---|
| `depeg_risk_score` | number 0-1 | ✅ | heuristic, R0 简化 |
| `lst_depeg_history_30d` | integer | ✅ | 事件数, R0 来自 on-chain event log |
| `stable_curve_steepness` | number | ✅ | stable pool 的 curve 斜率; flat = 强 stable |

### Reject 准则

- `depeg_risk_score > 0.5` → **reject**
- `lst_depeg_history_30d > 0` → **reject LST-stable** 池 (但 stable-stable 池可保留)

### Fee Proxy 继承 CPMM

`stable` 池的 fee_proxy 用 `cpmm_range_sensitivity.full_range_fee_proxy`

## 6. Sensitivity Summary 模板

每个 `best_candidate` 在 node_report 中给出一句话 range_sensitivity 总结:

```
{pool_address}: narrow_fee=${X} (in_range={Y1}%, risk=Z1), medium_fee=${X2} (in_range={Y2}%, risk=Z2), wide_fee=${X3} (in_range={Y3}%, risk=Z3)
```

**示例**:

```
0xABC...: narrow_fee=$0.12 (in_range=42%, risk=high), medium_fee=$0.08 (in_range=78%, risk=medium), wide_fee=$0.04 (in_range=99%, risk=low)
```

## 7. Aggregate Range Risk 评分

| 条件 | aggregate_risk |
|---|---|
| 3 range 都 high | `high` |
| 至少 1 个 low (宽 range 对冲) | `low` |
| 其他 | `medium` |

## 8. 节点报告必填字段

`range_sensitivity_block`:

- `range_assumption_used`: `"all_three_compared"` (R0 节点必须 3 range 都算)
- `range_sensitivity_available`: `true`
- `v3_clmm_range_sensitivity`: `[]` (3 row per V3/CLMM candidate)
- `meteora_dlmm_range_sensitivity`: `[]` (3 row per DLMM candidate)
- `cpmm_range_sensitivity`: `[]` (1 row per CPMM candidate)
- `fee_estimate_confidence`: `"low"` (R0)

## 9. R0 Locked Fields

| 字段 | 锁定值 |
|---|---|
| `actual_fee` | `false` |
| `fee_proxy` | `true` |
| `heuristic` | `true` |
| `in_range_time_ratio_estimated_from_history` | `true` |
| `no_future_prediction` | `true` |

## 10. 硬性不动作

| ID | 约束 |
|---|---|
| G1 | 不读 wallet / 不签名 |
| G2 | 不发送 transaction |
| G3 | 不接 paid indexer |
| G4 | 不写 production |
| G5 | `can_run_probe_now=false` 锁定 |

## 11. 结论

Range / tick / bin sensitivity spec 设计完成. 3 种 pool type 各有 1 套公式 + 字段 + 风险启发式. 每个候选池 3 range 必填. R0 永远 low confidence.

**Stage G PASS** → 进入 Stage H (节点报告生成器实现).
