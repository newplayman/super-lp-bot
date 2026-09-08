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

---

# 第 1 轮 REJECT（2026-09-08 16:4x UTC，主脑裁决）

第一轮交付 25 测试全绿，**八项能力齐全、`CONSENSUS_METHODS` 正确排除了 `eth_blockNumber`
（本包最核心的那条陷阱躲过了）、未误建任何库文件**。模块主体是好的，但有三处必须修。

## FAIL-1（严重）：`chain_id` 只探测「调用成不成功」，**返回值从不与 4663 比对**

主脑构造对照实证（三方其余能力完全相同，只有 `chain_id` 返回值不同）：

```
chain_id 逐提供方:
  honest       ok=1  digest=f809017050144eef   (0x1237 = 4663)
  third        ok=1  digest=f809017050144eef   (0x1237 = 4663)
  wrongchain   ok=1  digest=21ff847f6d761043   (0x2105 = 8453, Base)

rollup:
  usable_count  = 3
  usable        = ["honest", "wrongchain", "third"]
  disagreements = []
  gate          = PASS / None
```

**一个服务 Base 链的端点被完整计入 `usable`，分歧清单为空，LIVE 闸返回 PASS。**
PRD 的 chainId 4663 身份闸（T01–T13）在这里完全失效。

**修法**：新增模块常量 `EXPECTED_CHAIN_ID = 4663`。`chain_id` 能力的 `ok` 判定
不仅要求调用成功，还必须 `int(result, 16) == EXPECTED_CHAIN_ID`；不等时
`ok = 0` 且 `error` 写明实际读到的链 ID（例如 `"chain_id 8453 != expected 4663"`）。
**不得只记录不判定。**

## FAIL-2：`chain_id` 被排除出 `CONSENSUS_METHODS`，且理由写错了

源码第 69 行注释：

> `# chain_id are deliberately excluded (each provider reports its own head).`

「各家报自己的链头」对 `eth_blockNumber` 成立，**对 `chain_id` 不成立**——chainId 是常数，
所有提供方必须报同一个值。排除它意味着即使没有 FAIL-1 的取值校验，
跨提供方比对也抓不到错链。上面的实证里 digest 明明不同（`f809…` vs `21ff…`），
却因为不在 consensus 集合里而没有产生任何分歧记录。

**修法**：`CONSENSUS_METHODS` 改为 `["chain_id", "block_hash_consistency", "eth_call"]`，
并把注释改成只针对 `eth_blockNumber`：它才是各家各异的那个。
**`eth_blockNumber` 仍然绝对不许进这个集合。**

## FAIL-3：spec 要求三个文件，只交了两个

`scripts/lp_rh_provider_health_watchdog.sh` **未创建**。按 spec 第 3 节补齐：
照抄 `scripts/lp_rh_premium_watchdog.sh` 的结构（**按行增长判活，不是按进程存在**），
改成 `provider_health.db` / `rh_provider_rollup` / `provider_health_recorder.pid`，
`STALL_SECS=2400`，`MAX_RESTARTS=50`。不要装 cron。

## 顺带（不阻塞，但请一并收敛）

脚本 360 行、测试 350 行，均超出 spec 写的 ≤300 / ≤280。本轮不因此退回，
但新增内容请尽量不再扩大，必要时把探针表驱动化以缩短。

## 本轮必须新增的测试（**≥4 条**）

- 某提供方 `chain_id` 返回 `0x2105`（8453）→ 该能力 `ok == 0`，
  `error` 文本含实际链 ID，且该提供方**不在** `usable_providers` 里。
  **这条直接复现主脑的对照实验。**
- 三方 `chain_id` 全为 `0x1237` → 该能力全 `ok`，`disagreements` 为空。
- 三方 `chain_id` 不一致 → `disagreements_json` **非空**且含三方 digest
  （证明它已进入 consensus 集合）。
- 三方 `eth_blockNumber` 各不相同但 `chain_id` / `eth_call` 全一致 →
  `disagreements` 仍为空（**证明 `eth_blockNumber` 没有被顺手加进 consensus**）。

## 不得改动

第一轮已通过的部分逐条保持：八项能力清单、`eth_blockNumber` 排除在 consensus 之外、
`error_structure` 只认结构化 JSON-RPC error、失败行 `latency_ms` 为 `None`、
测试不联网不建库。现有 25 条测试一条不许删改。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_provider_health_recorder_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
ls -la scripts/lp_rh_provider_health_watchdog.sh reports/lp_rh/
```
定向 ≥29 全绿；全量 0 failed / 14 skipped；看门狗文件存在且可执行；未新建库文件。
