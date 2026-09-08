# RH-01e：提供方可用性录制器（把时点快照变成序列）

## 背景

`PROVIDER_MATRIX_20260908.md` 自列边界第 1 条：

> 这是一次时点快照，不是可用性序列。三个提供方此刻全通，不等于观测窗口内持续可用。
> `arrowrpc` 恰好证明注册表里的端点会挂。

而且实测已经出现过**同一端点同一请求二十分钟内由成功变失败**（primary 的 10k 块
`eth_getLogs`）。单次探测判定不了「可用」。本包把它变成周期序列。

`scripts/lp_rh_provider_pool_v1_readonly.py`（RH-01d，30 测试）已就位，**复用它**。

## 已核实事实（直接用，不要另猜）

chainId 4663 的端点，来自 ethereum-lists 注册表：
- `https://rpc.mainnet.chain.robinhood.com`（状态保留 10.4 分钟）
- `https://robinhood-rpc.publicnode.com`（不支持历史查询，带区间 getLogs 全 403）
- `https://rpc.ordofi.network`（状态保留 51 小时，10k 块 getLogs 稳定）
- `https://rpc.arrowrpc.com`（全方法 HTTP 530，已死）

PRD §8.3 要求实测的能力：**chainId、block/hash 一致性、历史读取、日志范围、eth_call、
gas estimate、错误结构**。CORE 种子池 `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`，
`slot0()` 选择器 `0x3850c7bd`，Swap topic0
`0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67`。

## 只写三个文件

1. `scripts/lp_rh_provider_health_recorder_v1_readonly.py`（≤300 行）
   复用 `scripts.lp_rh_provider_pool_v1_readonly` 的
   `verify_provider_methods` / `detect_disagreement` / `usable_providers` / `live_readiness`。
   **不要重新实现这些逻辑。**

   - 自己的库 `reports/lp_rh/provider_health.db`（**独立文件**，不碰 `scanner.db`、
     `premium.db`、`organic.db`，那三个各有单写者）。WAL。两张表：
     - `rh_provider_capability`：`sample_time, provider, capability, ok, latency_ms,
       error, result_digest`，主键 `(sample_time, provider, capability)`。
     - `rh_provider_rollup`：`sample_time, usable_count, usable_providers_json,
       disagreements_json, live_gate_status, live_gate_reason, head_block, pinned_block`，
       主键 `sample_time`。
     `latency_ms` 缺失写 NULL，**不写 0**；`ok` 存 0/1。
   - **能力清单必须按 PRD §8.3 全列**，每项一条记录：
     `chain_id` / `block_hash_consistency` / `historical_read` / `log_range_1k` /
     `log_range_10k` / `eth_call` / `gas_estimate` / `error_structure`。
     - `historical_read`：`eth_call(slot0, head-100000)`。
     - `error_structure`：调用不存在的方法，**返回结构化 JSON-RPC error 才算 ok**；
       返回 HTTP 层错误算 **not ok**。
   - **一致性比对只在固定区块上做**：取 `head - 60` 作 `pinned_block`，
     `eth_call` 与 `block_hash_consistency` 都打这个块。
     **绝不把 `eth_blockNumber` 放进 `consensus_methods`**——各家返回自己的链头，
     本来就该不同，拿它比对会把正常同步延迟误报成 `SOURCE_DISAGREEMENT` 从而无谓禁仓。
   - `usable_count` 按**全能力**口径算（少一项即不可用），写进 rollup；
     `live_readiness(usable_count)` 的结果一并写入。
   - `main()`：`--db --period-secs 900 --pid-file --once`。
     循环 deadline **从本轮起点算**。`SIGTERM`/`SIGINT` 优雅退出并删 pid 文件。
     单个提供方超时/异常**不得中断整轮**，记进该行 `error` 继续下一个。

2. `tests/test_lp_rh_provider_health_recorder_v1_readonly.py`（≤280 行，**≥16 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
   全部用**内存 SQLite + 注入的假 `call_fn`**，**不许联网、不许写 `reports/` 下任何文件**。必测：
   - 三方全能力通过 → `usable_count == 3`，`live_gate_status == "PASS"`。
   - 某方缺 `log_range_10k` → 不计入 `usable_count`（**这正是 publicnode 的真实情况**）。
   - 某方**全部**能力失败 → 该轮仍写满 8 条 capability 行（不是少写），`usable_count` 相应减少。
   - 一个提供方抛超时**不影响**其余提供方的记录（断言行数仍完整）。
   - `error_structure`：假 `call_fn` 抛 HTTP 层错误 → `ok == 0`；抛结构化 JSON-RPC error → `ok == 1`。
   - `detect_disagreement` 只吃固定区块方法：构造三方 `eth_blockNumber` 各不相同但
     `eth_call` 全一致 → `disagreements_json` **为空**。**这条是本包核心陷阱。**
   - `eth_call` 三方不一致 → `disagreements_json` 非空且含三方 digest。
   - `usable_count == 1` → `live_gate_reason == "SINGLE_PROVIDER"`；`0` → `"NO_PROVIDER"`。
   - `latency_ms` 在失败行为 `None`（**用 `is None` 断言，不是 0**）。
   - 同一 `(sample_time, provider, capability)` 写两次只有一行。
   - `--once` 只跑一轮返回 0。

3. `scripts/lp_rh_provider_health_watchdog.sh`
   照抄 `scripts/lp_rh_premium_watchdog.sh` 结构（**按行增长判活**），改成
   `provider_health.db` / `rh_provider_rollup` / `provider_health_recorder.pid`，
   `STALL_SECS=2400`，`MAX_RESTARTS=50`。**不要装 cron，我来装。**

## 不许动
不改任何现有脚本或测试。不写其他三个库。测试不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完对每个 .py 跑 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_provider_health_recorder_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
ls -la reports/lp_rh/
```
定向 ≥16 全绿；全量 0 failed / 14 skipped；`ls` 确认**未新建任何库文件**。三条命令尾部原样贴出。
