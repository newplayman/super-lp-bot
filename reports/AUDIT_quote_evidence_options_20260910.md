# 一、token1 身份（含证据）

结论：`token1` 是 USDG，不是 WETH。

- `scanner.db.rh_pool_registry` 实测 1 行：

  ```text
  chain_id=4663
  pool=0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
  token0=0x0bd7d308f8e1639fab988df18a8011f41eacad73
  token1=0x5fc5360d0400a0fd4f2af552add042d716f1d168
  fee=100, tick_spacing=1
  attestation_status=DISCOVERED_NOT_ATTESTED
  ```

- 采集器常量和注释明确写明 `token0=WETH, token1=USDG`：`scripts/lp_rh_collector_v1_readonly.py:53-56`。
- 地址、符号、精度的历史链上探针证据：

  `reports/rh_pivot/20260907T124500Z/RH-01b/LIVE_RPC_PROBE_20260907.md:19-20,28-30`

  ```text
  WETH = 0x0Bd7...AD73, symbol=WETH, decimals=18
  USDG = 0x5fc5...1d168, symbol=USDG, decimals=6
  token1 = 0x5fc536...1d168 (USDG)
  ```

- `pool_meta.json` 也记录 `token0_decimals=18`、`token1_decimals=6`、`dec0=18`、`dec1=6`：`reports/lp_rh/pool_meta.json:241-247`。
- `rh_assets` 当前共 194 行；两个底层地址查询结果均为 0 行。因此资产表没有 WETH/USDG 元数据。该缺口也被记录于 `docs/specs/20260909_RH-02bc_pool_attestation_backfill.md:12-15`。
- 注意：`pool_meta.json` 声称 `ATTESTED_SAME_BLOCK`：`reports/lp_rh/pool_meta.json:2`，但当前 `scanner.db` 注册表仍是 `DISCOVERED_NOT_ATTESTED`。两者状态不一致。

# 二、现有价格来源清单

## 1. 链上参考价 `rh_market_states.reference_mid`

口径是：

```text
token1/token0 = USDG/WETH
```

不是 USD 价格。

证据：

- 公式：`scripts/lp_rh_collector_v1_readonly.py:163-167`

  ```text
  (sqrtPriceX96 / 2^96)^2 × 10^dec0 / 10^dec1
  ```

  返回 `price_token1_per_token0`。
- 采集器读取目标池 `slot0()`：`scripts/lp_rh_collector_v1_readonly.py:222-226`。
- 计算并写入 `reference_mid`：`scripts/lp_rh_collector_v1_readonly.py:293-297,338-348`。
- 文档明确说明它是池内 DEX 价格，不是外部参考价，且采集器不调用 REST：`scripts/lp_rh_collector_v1_readonly.py:10-15`。

本次只读事务实测，约 `2026-09-10T00:24:24Z`：

```text
目标池 market_states：10052 行
reference_mid：10003/10052 = 99.513%
reference_bid：0/10052
reference_ask：0/10052
multiplier_human：0/10052
```

实测 `reference_mid` 范围为 `2442.043542` 到 `2522.002084`，单位应理解为 USDG/WETH；不是 USD/WETH。

## 2. REST 参考价

目标池的三列当前全为空：

```text
reference_bid    0/10052
reference_ask    0/10052
multiplier_human 0/10052
```

采集器硬编码写入 `None`：`scripts/lp_rh_collector_v1_readonly.py:343-348`。

现有 REST 源是：

```text
GET https://api.robinhood.com/rhj/prices
```

来源：

- `scripts/lp_rh_premium_recorder_v1_readonly.py:35-36`
- `reports/rh_pivot/20260907T124500Z/RH-05-research/REFERENCE_PRICE_AND_PREMIUM_20260908.md:10-21`

接口实测字段包括：

```text
tokenSymbol, bid, ask, currency, isTradingHalt, generatedAt
```

当前代码只为六个股票池取 REST 价：`scripts/lp_rh_premium_recorder_v1_readonly.py:40-50,320-346`，没有为目标 WETH/USDG 池写入 `scanner.db`。

仓库记录该端点为免费、约 480 次/日、无计费：`reports/rh_pivot/20260907T124500Z/RH-05-research/PREMIUM_RECORDER_20260908.md:15-21`。请求头只有 `User-Agent` 和 `Accept`，没有 API key 或 Authorization：`scripts/lp_rh_premium_recorder_v1_readonly.py:162-163`。

但仓库没有证明 `/rhj/prices` 一定返回 USDG 的 USD 报价；当前消费者只按股票符号取数。因此它是可探测的候选源，不是现成的 USDG 证据。

## 3. premium 录制器

表结构为：

```text
symbol, sample_time, pool, block, sqrt_price_x96,
token0_is_quote, quote_symbol, token_paused,
chain_price_usd, reference_bid, reference_ask, reference_mid,
multiplier, reference_token_price, premium_bps,
reference_generated_at, reference_age_secs, is_trading_halt,
status, error
```

来源：`scripts/lp_rh_premium_recorder_v1_readonly.py:60-70`。

当前只读实测：

```text
premium.db 总行数：4062
6 个股票各 677 行
目标池行数：0
quote_symbol=USDG：4062/4062
```

填充率：

```text
chain_price_usd       3968/4062 = 97.686%
reference_mid         4002/4062 = 98.523%
multiplier            3974/4062 = 97.834%
premium_bps           3892/4062 = 95.815%
```

示例首行：

```text
SGOV
quote_symbol=USDG
chain_price_usd=101.3587483759
reference_mid=100.475
multiplier=1.005101770003214918
reference_token_price=100.9876003411
premium_bps=36.751842...
reference_generated_at=2026-09-08T14:36:25.276097600Z
```

这些是“股票池价格（以 USDG 计价）”与股票 REST 参考价的溢价，不是 USDG/USD 价格。计算公式是 `chain_price_usd` 与 `reference_token_price` 的比较：`scripts/lp_rh_premium_recorder_v1_readonly.py:266-275`。

## 4. 稳定币价格源

没有现成的 USDG/USD 或 USDG/USDC 价格采集器。

- `scripts/lp_rh_stock_reference_v1_readonly.py:66-70` 只有一个要求调用方传入 `usdg_price_usd` 的归一化函数，没有数据源。
- `scripts/lp_rh_gas_history_cron.sh:2-4` 使用的是 WETH/USDG 池中间价作为 WETH 价格，不是 USDG/USD。
- `scripts/lp_rh_registry_v1_readonly.py:36-42` 只有 WETH、USDG、目标池等发现种子，没有 USDC 或稳定币参考池。
- `PRD` 明确要求独立追踪 USDG/USD：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:686-690`。

# 三、方案对比表

| 方案 | 具体做法 | 调用次数 | 证据时效 | 可逆性 / 授权 |
|---|---|---:|---|---|
| C 静态断言 | 在 `reports/lp_rh/pool_meta.json` 增加 `quote_usd_per_token1`，并增加 `source`、`observed_at`、`valid_until`、`payload_hash`、`bid/ask` 等 provenance；在 `scripts/lp_rh_shadow_runner_v1_readonly.py:389-417` 强制校验来源和过期时间 | 回放运行时 0；每次刷新 1 次 REST 或人工链上观测 | 例如有效 24h；过期后必须无 NAV，不能回退 1.0 | 无钱包授权；修改生产配置需要运维授权；可删除/过期回滚 |
| B REST | 接现有 `GET /rhj/prices`，或验证 `/rhj/prices/USDG`，取 USDG 的 `bid/ask/generatedAt`，新增独立 `quote_usd_per_token1` 字段，不复用股票 `reference_mid` | 1 REST/刷新；当前 180 秒周期约 480 次/日：`PREMIUM_RECORDER_20260908.md:15-21` | 使用服务端 `generatedAt`；代码建议 60 秒阈值：`scripts/lp_rh_reference_freshness_v1_readonly.py:18-24,107-119` | 当前代码无 key、无钱包授权；接口是否长期免费需以服务方规则为准 |
| D 隐含 WETH/USD | 用目标池 `USDG/WETH` 的 `reference_mid`，加独立 WETH/USD 源：`USDG_USD = WETH_USD / USDG_per_WETH`；保存两个来源及时间戳 | 现有目标池 RPC 不增加；另 1 REST 或 1 个 oracle RPC/刷新 | 取两个源的较小有效期；任一源 stale 或分歧过大即失败 | 只读，无钱包授权；外部 WETH/USD 源的 key/费用取决于供应商，仓库目前没有 |
| A 链上 USDG/USDC 池 | 找到并 attestation 一个独立 USDG/USDC V3 池，读取 `slot0()`；若要换算成 USD，还需独立 USDC/USD 证据，不能无出处地把 USDC 强制当 1 | 已知池：每个样本至少 1 次 `eth_call(slot0)`，另可复用区块时间；一次性身份核验约 6 次 RPC，精度再加 2 次 | 以参考池所在区块号/hash/timestamp 为出处；按区块新鲜度失效 | 只读 `eth_call`，无钱包授权；当前仓库没有 USDG/USDC 池地址，暂不可直接落地 |
| D 双源 quorum | 同时取链上参考池和 REST，保存两套值；只有两者在注册阈值内才产出 quote，否则无 NAV | 每次约 1 REST + 1 额外链上 `slot0`；一次性需要 A 的身份核验 | 两源都须 fresh；分歧、单源丢失都 fail-close | 只读，无钱包授权；实现和运维复杂度最高 |

链上方案的身份核验调用依据：`scripts/lp_rh_pool_probe_v1_readonly.py:167-211`。现有目标池采集器每轮本身约 8 次 RPC：`scripts/lp_rh_collector_v1_readonly.py:212-277`。

## C 是否满足 PRD:651

判断：满足 PRD:651 的最低要求，但必须带真实出处、时间戳和过期 fail-close。

PRD 原文只是：

```text
USDG 不是强制按 $1 估值
```

见 `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:647-651`，没有要求必须实时取价。

因此，类似：

```text
quote_usd_per_token1 = 0.9998
source = X
observed_at = 2026-09-10T...
valid_until = 2026-09-11T...
```

不是强制按 `$1`，可以满足该条要求。过期后无 NAV 也符合 `PRD:684`“无法计算可靠 NAV 则停新”。

但当前 runner 只检查 quote 是否存在：`scripts/lp_rh_shadow_runner_v1_readonly.py:389-417`，不会检查 provenance 或 `valid_until`。只添加数字、不添加来源验证，不足以满足 PRD 的可追溯要求。PRD 还要求保存报价基准与来源：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:300-306`，并要求追踪独立 USDG/USD 标记和报价分歧：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:686-688`。

# 四、脱锚 1% 的量化影响

计算使用报告中的 948 个有效费率样本：

```text
2026-09-09T16:05:55Z -> 2026-09-09T20:03:12Z
```

来源：`reports/ECONOMICS_corrected_20260909.md:7-19`。

基准结果：

```text
LP 市值：1000.000000 -> 994.537791
手续费：0.153902
net_pnl：-5.308307
hodl_delta：-5.159831
手续费年化：34.0901%
```

与报告 `reports/ECONOMICS_corrected_20260909.md:21-32` 一致。

正确的脱锚压力测试是：冻结开仓时的原始库存和 liquidity，开仓 quote=1.0，期末 quote=0.99。不能用 `q=.99` 重新构造一个新的 $1,000 仓位；因为 `inventory_for_position` 会按 `1/q` 放大库存，见 `scripts/lp_rh_v3_inventory_v1_readonly.py:78-95`。

| 口径 | net_pnl | hodl_delta | 手续费年化 |
|---|---:|---:|---:|
| q=1.00 基准 | -5.308307 | -5.159831 | 34.0901% |
| 原始库存冻结，期末 q=0.99 | -15.255224 | -15.108232 | 33.7492% |
| 变化 | -9.946917 | -9.948402 | -0.3409 个百分点 |

手续费金额从：

```text
0.153902 -> 0.152363
```

下降 `0.001539`，即下降 1%。

`position_value_at` 的估值公式确实将两腿同时乘以 quote：`scripts/lp_rh_v3_inventory_v1_readonly.py:173-181`。因此期末 LP 价值约为：

```text
994.537791 × 0.99 = 984.592413
```

HODL 期末价值约为：

```text
994.840169 × 0.99 = 984.891768
```

补充：如果把 `q=.99` 同时传给 `inventory_for_position` 和 `position_value_at`，重新建立固定 $1,000 仓位，则实测三项结果几乎完全不变：

```text
net_pnl       -5.308307
hodl_delta    -5.159831
fee APR       34.0901%
```

这是因为初始库存和 liquidity 按 `1/0.99` 放大后又乘回 `0.99`。这不是脱锚压力测试，而是重新标定仓位。当前 runner 在开仓时缓存 quote、库存和 liquidity：`scripts/lp_rh_shadow_runner_v1_readonly.py:389-417`，所以要表达真实的中途脱锚，未来需要保存原始 token 数量，并按每个估值时刻的 quote 重估。

# 五、你的推荐（一条，说清理由与它满足 PRD 的依据）

推荐：立即采用“C：带 provenance 和 24h TTL 的静态 quote”，但实际数字必须来自一次真实、可追溯的 USDG/USD 或 USDG/USDC 观测；同时保留过期即无 NAV 的 fail-close。

理由：

1. 当前唯一缺口就是显式 `quote_usd_per_token1`；`pool_meta.json` 当前确实没有该键，实测 JSON key 中不存在。
2. C 的运行时调用成本为 0，不需要新增 RPC、API key、钱包或签名。
3. PRD:651 禁止的是强制按 `$1`，不是禁止低频或静态证据：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:647-651`。
4. 只要保存来源、观测时间、有效期，并在过期时回到无 NAV，就满足“有出处、可追溯、不静默默认”的要求。
5. 但必须补 runner 的 provenance/expiry 校验；否则只是把缺失默认改成了“无出处的显式数字”，不够合规。
6. 后续再把 C 升级为 B 或 D 的自动刷新；在当前仓库尚未证明存在 USDG REST 报价、也没有 USDG/USDC 参考池的情况下，不应为了恢复 NAV 而擅自填 `$1`。