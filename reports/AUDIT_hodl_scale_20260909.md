# 结论摘要

| 条目 | PASS/FAIL/需关注 | 一句话结论 |
|---|---|---|
| `hodl_benchmark` 公式 | PASS（条件性） | 公式按传入两腿数量和 t1 价格计算，没有内置 50/50。 |
| Shadow 初始两腿 | FAIL | 真实样本没有覆盖键，实际始终使用虚拟 `1 token0 + 1 token1`。 |
| 规模可比性 | FAIL | 初始 HODL lot 约 $2485，LP 仓位 $1000，HODL 差额约放大 2.485 倍。 |
| PRD 一致性 | FAIL | PRD 要求实际初始两腿数量，当前实现不满足 D04/§12.2。 |
| V3 token 配比 | FAIL | 应使用区间仓位实际 token0/token1 数量，当前 lot 不是 V3 推导结果。 |
| token1 USD 报价 | FAIL | `Decimal("1")` 是全局默认值，PRD 明确 USDG 不能强制按 $1 估值。 |
| PnL/HODL 时间窗口 | FAIL | NAV 与 HODL 分别取各自可用步集合，未严格使用同一时间窗口。 |
| `net_pnl` | 需关注 | 当前手续费累计量纲错误，本文不使用 `net_pnl` 判断经济结果。 |

# 逐条证据

## 1. `hodl_benchmark` 定义、调用及初始两腿来源

证据：

- `scripts/lp_rh_pnl_v1_readonly.py:118-133`

  `hodl_benchmark` 接收：

  ```text
  initial_token0_raw
  initial_token1_raw
  dec0 / dec1
  price_t1_token1_per_token0
  quote_usd_per_token1
  ```

  计算逻辑是：

  ```text
  token0_human × t1价格 + token1_human
  再乘 quote_usd_per_token1
  ```

  因此函数本身是“固定初始两腿、按 t1 价格重估”。

- `scripts/lp_rh_shadow_runner_v1_readonly.py:48-52`

  默认值为：

  ```text
  VIRTUAL_INITIAL_TOKEN0_RAW = 1e18
  VIRTUAL_INITIAL_TOKEN1_RAW = 1e6
  DEFAULT_QUOTE_USD_PER_TOKEN1 = Decimal("1")
  ```

- `scripts/lp_rh_shadow_runner_v1_readonly.py:319-322`

  `init0`、`init1` 初始为 `None`。

- `scripts/lp_rh_shadow_runner_v1_readonly.py:382-395`

  仅在第一次处理的样本上执行：

  ```python
  init0 = _dec(sample.get("initial_token0_raw"), VIRTUAL_INITIAL_TOKEN0_RAW)
  init1 = _dec(sample.get("initial_token1_raw"), VIRTUAL_INITIAL_TOKEN1_RAW)
  ```

  所以：

  - 第一个有效样本带非空 `initial_token0_raw` / `initial_token1_raw`：对应腿覆盖默认值；
  - 字段缺失或为 `None`：使用虚拟默认；
  - 后续样本即使带字段，也不会覆盖，因为 `init0`/`init1` 已不再是 `None`；
  - token0、token1 可分别覆盖，缺哪一腿就对哪一腿使用默认值。

- 调用位置为 `scripts/lp_rh_shadow_runner_v1_readonly.py:392-395`。

- 实测 `reports/lp_rh/scanner.db` 的 `rh_market_states` 列名为：

  ```text
  asset_address, sample_time, chain_id, source_payload_hash,
  session, health_flags_json, reference_bid, reference_ask,
  reference_mid, reference_age_secs, multiplier_human, oracle_paused,
  derived_block_hash, derived_block_number, source_event_time,
  fee_growth_global_0, fee_growth_global_1
  ```

  实测不存在：

  ```text
  initial_token0_raw
  initial_token1_raw
  ```

结论：真实 scanner 样本无法覆盖两腿数量；当前 shadow 回放使用虚拟 `1 token0 + 1 token1`。

## 2. 最近 10 个 episode 的规模失真

证据：

- `scripts/lp_rh_shadow_runner_v1_readonly.py:543-544`：shadow 固定 `position_usd=1000`、`capital_usd=10000`。
- `reports/lp_rh/pool_meta.json:241-243`：`dec0=18`、`dec1=6`、`input_price_usd=2484.0`。
- 结合默认 quote `$1`，虚拟初始 lot 约为：

  ```text
  1 × 2484 + 1 × 1 = 2485 USD
  ```

- 缩放因子：

  ```text
  1000 / 2485 = 0.402414486921529...
  ```

以下为 `reports/lp_rh/shadow.db` 中按 `ended_at DESC` 最近 10 条的实测值；缩放值仅表示“保持当前错误配比、把 lot 等比例缩到 $1000”的诊断结果。

| episode | ended_at | 原 `hodl_delta` | ×1000/2485 后 | 缩放后−原值 |
|---|---|---:|---:|---:|
| `...192146-3` | 19:21:46 | -7.516844 | -3.024887 | 4.491957 |
| `...190646-2` | 19:06:46 | -10.557217 | -4.248377 | 6.308840 |
| `...185146-1` | 18:51:46 | -7.892254 | -3.175957 | 4.716297 |
| `...183646-0` | 18:36:46 | -1.420528 | -0.571641 | 0.848887 |
| `...183306-7` | 18:33:06 | -0.443189 | -0.178346 | 0.264843 |
| `...181806-6` | 18:18:06 | -7.137136 | -2.872087 | 4.265049 |
| `...180306-5` | 18:03:06 | -3.160171 | -1.271699 | 1.888472 |
| `...174806-4` | 17:48:06 | -4.220770 | -1.698499 | 2.522271 |
| `...173306-3` | 17:33:06 | -2.724320 | -1.096306 | 1.628014 |
| `...171806-2` | 17:18:06 | 5.965361 | 2.400548 | -3.564813 |

合计：

```text
原始 hodl_delta：-39.107068
等比例缩放后：  -15.737251
```

结论：当前 HODL 差额在相同资产配比假设下约被放大 `2.485×`。这只量化规模问题，不代表正确的 V3 配比修正；`net_pnl` 另受已知手续费公式错误影响。

## 3. 正确口径及 PRD 一致性

PRD 命中证据：

- `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:69-70`

  D04 明确规定：主基准使用实际初始 token 数量，50/50 只能作为额外策略对照。

- `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:625-629`

  HODL 应使用：

  ```text
  同样的外部资金流和实际初始两腿数量
  ```

  并明确“50% WETH + 50% USDG”不能替代头寸实际初始数量。

- `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:1033`

  T41 要求 recenter 后不重置 HODL 初始 lot 和累计亏损。

正确建议口径：

1. 在 episode 开仓时确定实际初始 token0/token1 raw 数量。
2. 两腿数量来自：
   - 真实 V3 mint/position 证据；或
   - shadow 假设的 `liquidity + sqrt_price + tick_lower/tick_upper` 推导。
3. 初始 lot 的 USD 价值应与 `position_usd=1000` 对齐。
4. 两腿数量固定持有，之后只按每个 t1 时点价格重估。
5. add/withdraw/recenter 不重置旧 lot；新增资金建立新的 HODL lot。
6. HODL 与 LP NAV 必须使用相同外部现金流、相同起止时刻。

结论：上述建议与 PRD 一致；当前 shadow runner 的虚拟 lot 不符合 PRD D04。

## 4a. 是否应使用 V3 区间仓位实际配比

证据：

- 当前虚拟 lot 为 `1 token0 + 1 token1`，对应 USD 价值约：

  ```text
  token0：2484 USD，占 99.95976%
  token1：1 USD，占 0.04024%
  ```

- `scripts/lp_rh_shadow_runner_v1_readonly.py:48-50` 只定义了固定虚拟数量，没有使用 liquidity、sqrt price、tick lower/upper 推导 token 数量。
- `reports/lp_rh/pool_meta.json:4-8` 提供池子的 `sqrt_price_x96`、`current_tick`、`liquidity`；`reports/lp_rh/pool_meta.json:252` 提供 `range_pct=10.0`，但没有本次 shadow position 的实际初始两腿。
- `scripts/lp_rh_store_v1_readonly.py:98-104` 的 `rh_shadow_positions` schema 已预留 `initial_token0_raw`、`initial_token1_raw`、`tick_lower`、`tick_upper`、`virtual_liquidity_raw`。

结论：应使用 V3 区间仓位的实际 token 配比，不应使用任意 1:1 raw-unit lot，也不应机械使用 50/50 USD。当前实现的 1:1 raw-unit 配比既不是 50/50 USD，也没有 V3 经济来源。

## 4b. `quote_usd_per_token1=1` 是否适用于所有池

证据：

- `scripts/lp_rh_shadow_runner_v1_readonly.py:52`：

  ```python
  DEFAULT_QUOTE_USD_PER_TOKEN1 = Decimal("1")
  ```

- `scripts/lp_rh_shadow_runner_v1_readonly.py:389`：样本没有 `quote_usd_per_token1` 时直接回退到上述默认值。
- `scripts/lp_rh_shadow_runner_v1_readonly.py:424-436`：scanner 查询没有选择 token1 USD 报价字段。
- `scripts/lp_rh_collector_v1_readonly.py:53-56`：当前目标池为 `token0=WETH, token1=USDG`。
- `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:651`：明确规定 USDG 不能强制按 `$1` 估值。

结论：不成立。即使当前池的 token1 是 USDG，也必须使用带时间戳和来源证据的 token1 USD 价格；不能将 `$1` 作为所有池、所有时点的通用默认值。

## 4c. `hodl_delta` 与 `net_pnl` 的窗口是否严格对齐

证据：

- `scripts/lp_rh_shadow_runner_v1_readonly.py:443-445`：`reference_mid IS NULL` 的样本在加载阶段被跳过。
- `scripts/lp_rh_shadow_runner_v1_readonly.py:356-360`：NAV 只有在 `fee_growth_global_0` 和 `fee_growth_global_1` 同时非空时才产生。
- `scripts/lp_rh_shadow_runner_v1_readonly.py:486-492`：

  ```python
  navs = [s.nav for s in steps if s.nav is not None]
  hodls = [s.hodl_value for s in steps if s.hodl_value is not None]
  ```

  因此：

  ```text
  net_pnl   = 最早可用 NAV 到最晚可用 NAV
  hodl_delta = 最早可用 HODL 到最晚可用 HODL
  ```

  两者不是同一个显式时间集合。

- 最近 10 条 episode 实测：

  ```text
  steps_without_nav = 1 的 episode：4 条
  skipped_at_load = 1 的 episode：1 条
  ```

  例如：

  ```text
  rh-shadow-20260909185146-1: steps_without_nav=1
  rh-shadow-20260909183646-0: steps_without_nav=1
  rh-shadow-20260909183306-7: steps_without_nav=1
  rh-shadow-20260909181806-6: steps_without_nav=1
  ```

结论：窗口未严格对齐，且已经出现 NAV 缺步。应在同一组 `sample_time` 上同时计算 NAV 和 HODL；至少应以 `nav_start_time/nav_end_time` 重新取得对应 HODL 值，并在缺 quote/price 时 fail closed，而不是各自取列表首尾。

# 修复建议

1. 修改 `scripts/lp_rh_shadow_runner_v1_readonly.py` 的 `run_episode()`：

   - 删除或废弃 `VIRTUAL_INITIAL_TOKEN0_RAW` / `VIRTUAL_INITIAL_TOKEN1_RAW` 作为生产默认；
   - 在 episode 开始时从真实 position evidence 或 V3 区间公式得到 `initial_token0_raw`、`initial_token1_raw`；
   - 令两腿初始 USD 总值严格等于 `position_usd`；
   - 将初始两腿写入 `rh_shadow_positions`；
   - 验收断言：

     ```text
     initial_token0_raw > 0
     initial_token1_raw > 0
     initial_lot_usd == position_usd ± rounding_tolerance
     ```

2. 新增 V3 初始库存计算函数，输入至少包括：

   ```text
   sqrt_price_x96
   sqrt_price_lower
   sqrt_price_upper
   liquidity
   dec0 / dec1
   ```

   输出：

   ```text
   amount0_raw
   amount1_raw
   reconstructed_usd
   ```

   验收：

   ```text
   amount0_raw/amount1_raw 不等于任意固定 1:1 常量；
   reconstructed_usd 与 position_usd 对齐；
   价格位于区间内时两腿均为正。
   ```

3. 修改 `load_samples_from_db()` 和样本 schema：

   - 每个 sample 必须携带 `quote_usd_per_token1` 或可追溯的 `token1_usd`；
   - 删除全局 `Decimal("1")` fallback；
   - 只有经过明确稳定币白名单和时点有效性验证，才允许 `$1` 作为池级 policy；
   - 缺 quote 时该步 HODL 标记为不可用并 fail closed。

4. 修改 `episode_summary()`：

   - 先按 `sample_time` 建立共同步集合；
   - 对同一 `nav_start_time`、`nav_end_time` 计算 HODL；
   - 输出并断言：

     ```text
     hodl_start_time == nav_start_time
     hodl_end_time == nav_end_time
     ```

   - 若无法在 NAV 起止时点取得价格或 quote，返回明确的 `INCOMPLETE_HODL_WINDOW`，不得静默使用另一组首尾步。

5. 为 add/withdraw/recenter 增加 lot 账本：

   - 旧 lot 保持原始数量和成本；
   - 新增资金建立新 HODL lot；
   - 验收 T41：recenter 后历史 HODL lot 不被重置，累计亏损不归零。

6. `net_pnl` 的手续费量纲修复完成前，所有报告应明确标记：

   ```text
   net_pnl_unreliable = true
   ```

   不得用当前 `net_pnl` 与修正前的 `hodl_delta` 做经济胜负判断。