# LP Bot PRD v2.1 · WP-10 SOL 最终验收归档

**日期：** 2026-08-08  
**分支：** `feat/prd-v2.1-m0-shadow`  
**WP-10：** `DONE`  
**授权边界：** M0 代码与集成 smoke 完成；14d shadow 未启动，§12.0 gate 为 `FAIL`，本文不授权 M1、合并、推送或真实交易。

## 1. 测试裁决

- Solana 实现后的定向验收：`93 passed`，覆盖 Solana runner、原 Base runner、ledger-v2、RpcPool 与 shadow gate。
- Solana 实现后的全量验收：`2660 passed, 14 skipped in 37.51s`。
- Solana 实现后的 collect：`2674 tests collected in 1.06s`，0 collection error。
- 14 个 skip 均为 `tests/conftest.py::LEGACY_ENVIRONMENT_BOUND_NODEIDS` 中的精确 nodeid quarantine，不是 pass，也不是整文件忽略。
- TDD 提交：红测 `920c85f`；实现 `fb88eb2`。

## 2. Live scanner → vetted menu → allocator

验收官亲跑 live scanner 的 stdout 计数为：

```text
screened=736 top=1 resolved=1 scored=1 accepted=0
```

唯一进入 score 阶段的记录缺少以下 9 个 horizon USD 输入，NetCover 按 fail-closed 返回 `MISSING_FAIL_CLOSED`：

```text
fee_ev_usd
reward_ev_usd
il_ev_usd
entry_cost_usd
exit_cost_usd
gas_usd
slippage_usd
reward_conversion_cost_usd
exit_latency_loss_usd
```

因此 live vetted menu 为 `[]`。live allocator 的结果是 `n_pools=0`、`deployed=0.0`、`idle=100.0`，且 `runtime_gates_enforced=true`。这是正确的拒绝结果；没有用 fixture 填补 accepted=0。

## 3. Base 1-tick：仅证明集成接线

为验证非空 allocation → runner → ledger-v2 → gate SQLite 的机械链路，验收使用了历史真实 Base WETH-USDC 池，但 allocation 被明确标记为：

```text
scanner_evidence_origin=fixture_only_not_live_vetted
source_kind=historical_real_base_vetted_pool
purpose=integration_plumbing_only
```

该 fixture 不属于本次 live-vetted menu，不得用于启动 14d shadow。Base runner 完成 1 tick：block `49712404`、`portfolio_nav_usd=100.0`、RPC `NORMAL`、23 个 attribution 字段齐全，并自动写入同一 `scanner.db`。Base-only gate 当时为：0d FAIL、1 position FAIL、fee error 100% FAIL、raw PnL `1.4210854715202004e-14` 经 `<=1e-9 USD` 去噪归零后 PnL FAIL、DD 0 PASS、未解决 severe RPC 0 PASS。

## 4. Solana Orca Whirlpool 1-tick

### 4.1 证据边界

allocation 明确声明 `protocol=orca_whirlpool` 与 `solana_adapter=orca_whirlpool_account_v1`，不根据地址猜 adapter。该 allocation 同样标记为 `fixture_only_not_live_vetted`；但下列 slot、owner、账户字节、价格和流动性均是通过 WP-01 免费 RpcPool 对真实 Orca Whirlpool 账户的 live read-only 观测。

runner 仅调用 `getSlot` 与 `getAccountInfo`，没有钱包、签名、approve、广播、写方法或 EVM reader。它校验：

- owner 为 `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`；
- RPC `value.space=653` 且 base64 解码后长度也为 653；
- Anchor Whirlpool discriminator 正确；
- `sqrt_price_x64` 与 `liquidity` 均为正数；
- 价格方向明确为 token B per token A，即 USDC/SPYx：`(sqrt_price_x64 / 2^64)^2 × 10^(8-6)`。

### 4.2 验收官 stdout

```text
[run] dir=reports/lp_m0_integration_smoke/20260808_sol_acceptance/solana_runner_1tick pools=1 poll=0s max_ticks=1 chain=solana rpc_pool=6 endpoints (rotating, free public)
[init] SPYx-USDC      B cap=100 anchor=777.69 range=±10.00% exit_on_breach=False pool=Fae5dWVntUt6zbWu2voXxioDpMii7SqQwtsxBmoVCsHR
[tick 0] blk=438047909 net=$0.00 SPYx-USDC:+0.00%
[done] 1 ticks; state flushed to reports/lp_m0_integration_smoke/20260808_sol_acceptance/solana_runner_1tick
```

### 4.3 heartbeat / final_state / gate

- tick block：`438047909`；account context slot：`438047910`。
- pool：`Fae5dWVntUt6zbWu2voXxioDpMii7SqQwtsxBmoVCsHR`。
- owner：`whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`；space：`653`。
- `sqrt_price_x64=51442595230560696483`；`liquidity=619420826944`。
- `price=777.6896076046631`；方向 `token_b_per_token_a`。
- RPC `NORMAL`；NAV `100.0`；risk `HEALTHY`；23 个 attribution 字段齐全；gate 自动写入 SQLite。
- `observation_kind=account_state`、`amount1=0`、`n_swaps=0`、fees `0.0`。这是一条完整进入现有账本与 gate 路径的 M0 只读 1-tick，但不是 swap event decoder 或 swap-fee 证据；系统没有伪造 swap 或 fee。

跟踪归档：

- `evidence_20260808/acceptance_summary.json`
- `evidence_20260808/solana_runner_heartbeat_tick0.json`
- `evidence_20260808/solana_runner_final_state.json`

原始运行目录 `20260808_sol_acceptance/` 保持 untracked；其中 SQLite、PID、CSV 和运行产物不会提交。摘要中记录了必要源文件的 SHA-256。

## 5. §12.0 gate 最终 smoke 快照

加入 Solana 1-tick 后，gate 报告为：

| 检查 | 值 | 结果 |
|---|---:|---|
| shadow duration | `0.01499527079861111 d` | FAIL（要求 ≥14d） |
| unique simulated positions | `2` | FAIL（要求 ≥50） |
| fee prediction error | `100.0%` | FAIL（要求 <20%） |
| shadow net PnL | raw `1.4210854715202004e-14`，normalized `0.0` | FAIL（要求 >0） |
| simulated drawdown | `0.0%` | PASS（要求 <8%） |
| unresolved severe RPC | `0` | PASS（要求 =0） |

overall 为 `FAIL`。这符合 smoke 只有两个 fixture 仓且观察期不足的事实，不是启动成功或 M1 授权。

## 6. 最终结论

WP-10 所要求的 Base 真实池机械链路与 Solana Orca 真实账户 account-state 1-tick 均已通过只读集成验收；实现后定向、全量与 collect 均通过，因此 WP-10 标记为 `DONE`。

14d shadow 尚未启动，live scanner 本轮 accepted=0，当前无可批准的非空 live-vetted allocation，§12.0 gate 未通过。必须继续保持 paper/read-only；M1-A 签名 sidecar与 M1-B EVM 执行均不得开工。
