# Stage G — 实际 Fee Accrual Schema (Actual Fee Accrual Schema)

- stage: `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`
- run_id: `20260604_062324`

## 0. 目的

定义 position-level 实际 fee accrual 的完整 schema, 解决上一阶段
`needs_actual_fee_accrual=true` 标记的缺口. R0 阶段**只写 schema, 不抓数据**;
R1 阶段用户 / paid indexer 提供 tokenId 后, 才能抓 entry / exit / collect fee event.

## 1. 背景: 为什么需要 actual fee

上一阶段 final freeze 用的是 heuristic 0.5%/day turnover, 实际是 10/20U quote
推导的 100× 上限. 真实 LP 收益受以下因素影响:

- **fee growth inside / outside tick**: V3 CL 的 fee 增长按 LP 占流动性比例分配,
  out-of-range 时不收 fee
- **dynamic fee activation rate**: Meteora DLMM 100bps base + 1000bps max,
  实际激活率在 30-70% 之间
- **tick boundary cross**: V3 CL tick 跨过 LP 区间时, fee 累积重置
- **collect fee timing**: 用户实际 collect 频率影响 realized fee

heuristic 模型无能力 capture 这些, 只能 actual 抓取.

## 2. position-level schema (3 段: entry / exit / collect)

### 2.1 entry 段 (用户在 entry 时记录, 或 R1 阶段 on-chain 抓)

```json
{
  "token_id": "string",                  // position NFT mint address
  "pool_address": "string",              // 关联 pool
  "chain": "string",                     // solana
  "protocol": "string",                  // meteora_dlmm / orca_whirlpool / raydium_clmm / raydium_cpmm
  "program_id": "string",                // 协议 program id

  "entry_fee_growth_global": "u256",     // entry 时 pool 全局 feeGrowth (Q64.64)
  "entry_fee_growth_a": "u256",          // entry 时 token_a feeGrowthOutside
  "entry_fee_growth_b": "u256",          // entry 时 token_b feeGrowthOutside
  "entry_tick_lower": "i32",             // LP 区间下界 (V3 CL) / bin_id_low (DLMM)
  "entry_tick_upper": "i32",             // LP 区间上界
  "entry_sqrt_price_x64": "u128",        // entry 时 pool sqrt_price (V3 CL only)
  "entry_bin_id": "i32",                 // entry 时 bin_id (DLMM only)
  "entry_liquidity": "u128",             // entry 时 LP 提供的流动性
  "entry_amount_a_raw": "u64",           // entry 时 token_a 数量
  "entry_amount_b_raw": "u64",           // entry 时 token_b 数量
  "entry_value_usd": "f64",              // entry 时 LP 头寸 USD 价值
  "entry_at": "ISO 8601 timestamp",      // entry 时间 (on-chain)
  "entry_tx_signature": "string",        // entry tx signature (Solana)
  "entry_block_slot": "u64",             // entry slot
  "entry_user_wallet": "string",         // 用户 wallet (R1 阶段验证用)
  "entry_source": "enum",                // user_provided / indexer / on_chain_event
  "entry_at_local": "ISO 8601 timestamp" // 本地记录时间
}
```

### 2.2 exit 段 (用户在 exit 时记录, 或 R1 阶段 on-chain 抓)

```json
{
  "exit_fee_growth_global": "u256",      // exit 时 pool 全局 feeGrowth
  "exit_fee_growth_a": "u256",           // exit 时 token_a feeGrowthOutside
  "exit_fee_growth_b": "u256",           // exit 时 token_b feeGrowthOutside
  "exit_tick_lower": "i32",              // exit 时 LP 区间下界 (after rebalance)
  "exit_tick_upper": "i32",              // exit 时 LP 区间上界
  "exit_sqrt_price_x64": "u128",         // exit 时 pool sqrt_price
  "exit_bin_id": "i32",                  // exit 时 bin_id
  "exit_liquidity": "u128",              // exit 时剩余流动性 (可能 < entry)
  "exit_amount_a_raw": "u64",            // exit 时 token_a 数量
  "exit_amount_b_raw": "u64",            // exit 时 token_b 数量
  "exit_value_usd": "f64",               // exit 时 LP 头寸 USD 价值
  "exit_at": "ISO 8601 timestamp",       // exit 时间
  "exit_tx_signature": "string",         // exit tx signature
  "exit_block_slot": "u64",              // exit slot
  "exit_user_wallet": "string",          // 退出 wallet
  "exit_source": "enum",                 // user_provided / indexer / on_chain_event
  "exit_at_local": "ISO 8601 timestamp", // 本地记录时间
  "exit_reason": "enum"                  // remove_liquidity / collect_only / rebalance
}
```

### 2.3 collect_fee 段 (R1 阶段 on-chain 抓, 多个 record per position)

```json
{
  "collect_id": "u64",                   // 自增 ID, per position
  "token_id": "string",                  // 关联 position
  "collect_amount_a_raw": "u64",         // collect token_a 数量
  "collect_amount_b_raw": "u64",         // collect token_b 数量
  "collect_value_usd": "f64",            // collect 时 USD 价值
  "collect_fee_growth_global_at_collect": "u256", // collect 时全局 feeGrowth
  "collect_at": "ISO 8601 timestamp",    // collect 时间
  "collect_tx_signature": "string",      // collect tx signature
  "collect_block_slot": "u64",           // collect slot
  "collect_at_local": "ISO 8601 timestamp" // 本地记录时间
}
```

### 2.4 derived 段 (R1 阶段, 离线派生)

```json
{
  "actual_fee_a_raw": "u64",             // 总 collect token_a
  "actual_fee_b_raw": "u64",             // 总 collect token_b
  "actual_fee_usd": "f64",               // 总 collect USD 价值
  "actual_pnl_usd": "f64",               // exit_value + collect_value - entry_value
  "actual_pnl_pct": "f64",               // actual_pnl / entry_value
  "il_realized_pct": "f64",              // 真实 IL 实现
  "il_actual_pct": "f64",                // 与 heuristic 对比 (heuristic - actual)
  "il_divergence_pct": "f64",            // (heuristic - actual) / heuristic
  "holding_period_hours": "f64",         // entry 到 exit 小时数
  "fee_velocity_actual": "f64",          // actual_fee / holding_period
  "fee_velocity_proxy": "f64",           // heuristic 0.5%/day 推导
  "fee_velocity_divergence": "f64"       // (proxy - actual) / proxy
}
```

## 3. tokens_owed (mid-position 快照)

```json
{
  "token_id": "string",                  // 关联 position
  "snapshot_at": "ISO 8601 timestamp",   // 快照时间
  "tokens_owed_a_raw": "u64",            // 当前待 collect token_a
  "tokens_owed_b_raw": "u64",            // 当前待 collect token_b
  "fee_growth_global_at_snapshot": "u256",
  "il_unrealized_pct": "f64"             // 未实现 IL (entry vs snapshot price)
}
```

每 24h 写 1 条 tokens_owed snapshot, 用于 mid-position fee accrual 监测.

## 4. R0 阶段实施

R0 阶段**只**写 schema, 不抓任何 actual fee data:

- 表结构 (sqlite + jsonl) 在 Stage E 给出
- entry / exit / collect / tokens_owed 全部 0 record
- schema placeholder 行 (token_id = null) 也不写
- pytest 验证 schema 字段名一致, 不验证 record 内容

## 5. R1 阶段实施 (本任务不覆盖, 单独 stage)

R1 阶段激活 actual fee 抓取:
- 输入: user 提供已有 position tokenId (e.g. 10 个历史 LP NFT)
- 数据源: paid indexer (Shyft / helloMoon) 抓 collect event + on-chain state
- 输出: entry / exit / collect / tokens_owed 实际 record
- 派生命段: actual_pnl_usd, il_realized_pct 等

R1 阶段必须满足:
- can_run_probe_now = false (locked, R1 不开 probe)
- 任何 user-provided tokenId 仅用作 read-only data collection
- 不创建新 LP position (R1 不开 LP)

## 6. 与 heuristic 的对比 (R1 阶段产出)

| 维度 | heuristic | actual | 差异 |
|---|---|---|---|
| fee per day | 0.5% (assumed) | 实测 | fee_velocity_divergence |
| IL | 4 scenarios (0/0.1/0.5/1.5% per day) | 实测 | il_actual_pct |
| net EV | fee - IL - cost | exit_value + collect - entry | actual_pnl_usd |
| 持有时长 | 7d assumed | 实测 | holding_period_hours |

R1 阶段输出 il_divergence_pct, 量化 heuristic vs actual 差距. 这是 R2 阶段
regime split EV 的输入.

## 7. 测试覆盖 (R0 阶段实施, R1 阶段验证)

```python
# 7.1 schema 字段完整性
test_entry_schema_completeness()
test_exit_schema_completeness()
test_collect_schema_completeness()
test_tokens_owed_schema_completeness()

# 7.2 R0 阶段无 record
test_r0_no_records_written()
test_r0_table_schema_exists_but_empty()

# 7.3 R0 schema 与 R1 字段兼容
test_r0_schema_forward_compatible_with_r1()

# 7.4 derived 段派生正确性 (R1 阶段验证)
test_actual_pnl_calculation()
test_il_realized_calculation()
test_fee_velocity_divergence()
```

## 8. 不在本任务范围

- 任何 actual fee 数据抓取 (R1 阶段后续, 需 user-provided tokenId 或 paid indexer)
- 任何 entry / exit / collect 模拟 (R1 阶段后续)
- 任何 heuristic 修改 / 重算
- 任何 paid indexer 接入
- 任何 R1 阶段的实际跑

## 9. 结论

- 3 段 schema (entry / exit / collect) + 4 段 (derived) + 1 段 (tokens_owed) 完整
- 字段全部含类型 + 必填 + 来源 + 阶段标识
- R0 阶段只写 schema, 不抓数据
- R1 阶段是 spec 实施的实际阶段, 需 user tokenId 或 paid indexer
- 与 heuristic 对比字段 (il_divergence, fee_velocity_divergence) 定义完成
- R1 阶段输出是 R2 阶段 regime split EV 的输入
- 测试覆盖 11 项 (4 schema + 2 R0 empty + 1 兼容 + 4 derived)
