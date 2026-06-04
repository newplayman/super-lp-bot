# Stage F — 市场 Regime 分类器规格 (Market Regime Classifier Spec)

- stage: `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`
- run_id: `20260604_062324`

## 0. 目的

定义 7 类市场 regime 分类器规则, 配套输入数据 / 输出字段 / 决策流程. 本任务是
**spec only**, 不实施任何 classifier 模型训练 / 实际分类运行. R2 阶段才用本 spec
跑实际 regime split.

## 1. 7 类 regime 定义 (从 scope_audit 060659 继承并精确化)

| regime | 7d 价格变化 | 30d 价格变化 | 7d 实际波动率 | 30d volume/TVL | LM/bribe 状态 |
|---|---|---|---|---|---|
| uptrend | > +5% | > +10% | < 8% | any | any |
| downtrend | < -5% | < -10% | < 8% | any | any |
| sideways | -5% ~ +5% | -10% ~ +10% | < 5% | < 1% | any |
| high_volume_sideways | -5% ~ +5% | -10% ~ +10% | < 5% | ≥ 1% | any |
| high_volatility_trend | any (with trend) | any (with trend) | ≥ 10% | any | any |
| incentive_period | any | any | any | any | active |
| low_volatility_stable | any | any | < 1% | any | any |

regime **优先级** (冲突时按以下顺序匹配):
1. `low_volatility_stable` (vol < 1%)
2. `incentive_period` (LM/bribe active, override others)
3. `high_volatility_trend` (vol ≥ 10%)
4. `high_volume_sideways` (sideways + vol/TVL ≥ 1%)
5. `uptrend` / `downtrend` / `sideways` (基础 trend)

## 2. 输入数据

| 输入 | 来源 | 频率 |
|---|---|---|
| OHLC 7d | CoinGecko / on-chain | 1 sample / day |
| OHLC 30d | CoinGecko / on-chain | 1 sample / day |
| realized_vol_7d | derived from 7d OHLC | 1 sample / day |
| realized_vol_30d | derived from 30d OHLC | 1 sample / day |
| volume_30d_usd | DexScreener / on-chain | 1 sample / day |
| tvl_usd | derived from pool snapshot | 1 sample / day |
| lm_active | protocol farm program events | 1 sample / day |
| bribe_active | bribe marketplace | 1 sample / day |

## 3. 输出 schema (与 Stage E 1.5 market_regime 表一致)

```json
{
  "regime": "downtrend",
  "lookback_days": 7,
  "price_change_pct": -8.5,
  "realized_vol_pct": 12.3,
  "volume_to_tvl_pct": 0.7,
  "incentive_active": false,
  "regime_at": "2026-06-04T06:30:00Z"
}
```

每个 regime 标识都写一条 record 到 `market_regime.jsonl` (R0 阶段 1 sample/day).

## 4. 决策流程 (decision tree)

```text
1. look up 7d realized_vol (vol_7d)
2. if vol_7d < 1%:
       regime = low_volatility_stable
   else if (lm_active OR bribe_active):
       regime = incentive_period
   else if vol_7d >= 10%:
       regime = high_volatility_trend
   else:
       # check trend
       look up 7d price_change (px_7d)
       if px_7d > +5%:
           regime = uptrend
       elif px_7d < -5%:
           regime = downtrend
       else:
           # sideways
           look up 30d volume/TVL (vol_tvl_30d)
           if vol_tvl_30d >= 1%:
               regime = high_volume_sideways
           else:
               regime = sideways
```

## 5. 边界情况

| 情况 | 处理 |
|---|---|
| 数据缺失 (e.g. CoinGecko 4xx) | 跳过当日, regime = `unknown`, 不写 record |
| 多 regime 同时满足 (e.g. low vol + incentive) | 按优先级 (low_vol > incentive > high_vol > trend) |
| regime 切换瞬间 (1h 内) | 沿用旧 regime, 防止频繁切换污染数据 |
| 新上线池 (< 7d 历史) | 跳过 regime 分类, regime = `unknown` |
| 跨协议混合 (同一时段不同 protocol 不同 regime) | per-protocol 单独分类, 不合并 |

## 6. 与 R0 / R1 / R2 阶段的接口

| 阶段 | 用途 |
|---|---|
| R0 (long read-only data) | 本 spec 实施, 1 sample / day 写 market_regime.jsonl |
| R1 (real fee accrual) | 用 regime 标识 actual fee 的 regime 背景 |
| R2 (regime split EV) | 用 regime 标识加权, 算每个 regime 的 weighted EV |
| R3 (reopen candidate review) | 用 regime 分类筛激励 / 高 vol sideways 池 |
| R4 (10U tokenId probe preflight) | 用 regime 选择 probe 时机 |
| R5 (manual probe) | 用 regime 判断 probe 边界 |

## 7. classifier 实现 outline (R0 阶段后续)

```python
def classify_regime(
    vol_7d: float,
    vol_30d: float,
    px_change_7d: float,
    px_change_30d: float,
    vol_tvl_30d: float,
    lm_active: bool,
    bribe_active: bool,
) -> str:
    # priority 1: low volatility stable
    if vol_7d < 1.0:
        return "low_volatility_stable"
    # priority 2: incentive period
    if lm_active or bribe_active:
        return "incentive_period"
    # priority 3: high volatility trend
    if vol_7d >= 10.0:
        return "high_volatility_trend"
    # priority 4-6: trend
    if px_change_7d > 5.0:
        return "uptrend"
    if px_change_7d < -5.0:
        return "downtrend"
    # priority 7-8: sideways vs high_volume_sideways
    if vol_tvl_30d >= 1.0:
        return "high_volume_sideways"
    return "sideways"
```

**重要**: 上 outline 只用于 spec 验证 + unit test, R0 阶段不实装 (实装要等
collector 长期运行开始后, 单独 stage + 单独 audit).

## 8. 测试覆盖 (R0 阶段后续)

```python
# 8.1 低波动稳定
test_low_vol_stable_priority()

# 8.2 激励期覆盖其他
test_incentive_overrides_trend()

# 8.3 高波动覆盖 trend
test_high_vol_overrides_sideways()

# 8.4 trend 优先级
test_uptrend_priority()
test_downtrend_priority()

# 8.5 sideways 与 high_volume_sideways 区分
test_high_volume_sideways_distinction()

# 8.6 数据缺失 → unknown
test_missing_data_returns_unknown()

# 8.7 边界值
test_boundary_5pct()
test_boundary_1pct_vol()
test_boundary_10pct_vol()
```

## 9. 不在本任务范围

- 实际 classifier 模型训练 (R0 阶段后续)
- 任何 7d/30d OHLC 数据实际抓取 (R0 阶段后续)
- 任何 regime split EV 跑 (R2 阶段后续)
- 任何基于 regime 的自动 probe (R5 阶段后续, manual approval only)
- 任何 paid indexer / paid RPC (R0 阶段后续)

## 10. 结论

- 7 regime 定义精确化 (含优先级)
- 决策流程 decision tree 完整
- 输出 schema 与 Stage E 1.5 一致
- 边界情况处理明确
- R0 / R1 / R2 / R3 / R4 / R5 阶段接口清晰
- classifier 实现 outline 给出, R0 阶段后续实施
- 测试覆盖 8 类边界 + 数据缺失
- 实际训练 / 实施不在本任务
