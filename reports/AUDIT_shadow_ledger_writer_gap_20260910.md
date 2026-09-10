# AUDIT：Shadow 跑了 113 轮，PRD 规定的六张账本表为何一行都没有（2026-09-10）

- 任务：主脑派 codex（gpt-5.6-luna, xhigh, read-only）审查
- 性质：**只读**。未改动任何代码、未写任何库。
- 触发：主脑在 PRD 全量对账后核实发现 `rh_shadow_positions` 等六表 0 行，
  而 `shadow.db` 有 113 个 episode、4,487 步通过终闸。

## 一句话结论

**daemon 每轮新建一个临时 `scratch.db`，把 gate/mark/reservation 写进去，
然后在 `finally` 里关闭、临时目录销毁——整轮账本记录随之蒸发。**
另外三张表（economic / positions / journal）则是 writer 缺失或从未接入生产路径。

Stage B 要求的 14 天证据链**从来没有开始积累过**。

---

# 结论摘要

主因是复合型：

- `rh_gate_decisions`、`rh_position_marks`、`rh_bucket_reservations` 有 writer，但 daemon 把它们写入每轮临时 `scratch.db`，随后销毁，属于 **(c) 写到别的库且未持久化**。
- `rh_economic_evaluations`、`rh_shadow_positions`、`rh_journal` 没有接入 Shadow 生产路径，属于 **(a) writer 缺失或未接线**。
- 不是条件跳过：gate/mark 的 insert 不在 `eligible` 条件内。
- `shadow.db` 只保存 episode 汇总和 blocker，不是六张账本表。

## 1. 六张表的 writer 与调用链

这里把通用 `insert_row()` 与真正的业务 writer 区分开：`insert_row()` 虽然理论上可以写所有 RH 表，但只有被生产路径传入某张表名时，才算该表已接线。通用实现位于 `scripts/lp_rh_store_v1_readonly.py:354-382`。

| 表 | writer 状态 | 生产调用 |
|---|---|---|
| `rh_economic_evaluations` | **没有专用 writer，也没有生产调用。** 只有 schema 字段；`q_min/q_max` 也明确只是表字段，没有模块计算经济区间。证据：`scripts/lp_rh_store_v1_readonly.py:82-91`；`scripts/lp_rh_size_interval_v1_readonly.py:4-7` | **没有生产调用；只有 schema/测试层引用。** |
| `rh_gate_decisions` | 通过通用 `insert_row()` 写入，实际写入点：`scripts/lp_rh_shadow_runner_v1_readonly.py:659-667` | `run_episode()` 被 daemon 调用：`scripts/lp_rh_shadow_daemon_v1_readonly.py:231-236`；批处理 CLI 也调用：`scripts/lp_rh_shadow_runner_v1_readonly.py:856-860`。但两者都使用临时 scratch，见下文。 |
| `rh_shadow_positions` | **没有 writer。** schema 在 `scripts/lp_rh_store_v1_readonly.py:98-104`；runner 只在内存中维护 `position_open`，并计算 inventory，没有 insert：`scripts/lp_rh_shadow_runner_v1_readonly.py:485-503`、`557-603` | 没有生产调用；测试仅验证 schema/相关行为。 |
| `rh_journal` | writer 是 `book_journal_event()`：`scripts/lp_rh_pnl_v1_readonly.py:136-153` | 没有生产调用。唯一实际调用在测试：`tests/test_lp_rh_pnl_v1_readonly.py:141-151`、`201-208`。因此：**只有测试在调**。 |
| `rh_position_marks` | 通过通用 `insert_row()` 写入：`scripts/lp_rh_shadow_runner_v1_readonly.py:672-678` | 与 gate 相同，由 `run_episode()` 调用；daemon 调用链见 `scripts/lp_rh_shadow_daemon_v1_readonly.py:231-248`。实际只写 scratch。 |
| `rh_bucket_reservations` | `try_reserve()` 写入：`scripts/lp_rh_bucket_ledger_v1_readonly.py:94-128`；状态变更 writer 还有 `release()` / `set_status()`：`scripts/lp_rh_bucket_ledger_v1_readonly.py:135-170` | `try_reserve()` 由 runner 调用：`scripts/lp_rh_shadow_runner_v1_readonly.py:527-536`。`release()`、`set_status()` 没有生产调用，**只有测试在调**：`tests/test_lp_rh_bucket_ledger_v1_readonly.py:46-119`。 |

## 2. 4487 个 eligible 为什么没有落到 `scanner.db`

### 2.1 Gate、mark、reservation：写到了临时库

daemon 先用只读连接读取 `scanner.db`：

`scripts/lp_rh_shadow_daemon_v1_readonly.py:221-226`

然后创建每轮临时数据库：

`scripts/lp_rh_shadow_daemon_v1_readonly.py:227-239`

再把这个 scratch connection 传给 `run_episode()`：

`scripts/lp_rh_shadow_daemon_v1_readonly.py:231-236`

`run_episode()` 确实写入：

- `rh_gate_decisions`：`scripts/lp_rh_shadow_runner_v1_readonly.py:659-667`
- `rh_position_marks`：`scripts/lp_rh_shadow_runner_v1_readonly.py:672-678`
- eligible 且尚无持仓时写 reservation：`scripts/lp_rh_shadow_runner_v1_readonly.py:527-536`

但 scratch connection 在 `finally` 中关闭，临时目录退出后被销毁：`scripts/lp_rh_shadow_daemon_v1_readonly.py:227-239`。

daemon 在 scratch 关闭后只保留 episode 汇总和 blocker：

`scripts/lp_rh_shadow_daemon_v1_readonly.py:240-248`

其自有库 DDL 也只有两张表：

`scripts/lp_rh_shadow_daemon_v1_readonly.py:49-66`

因此 4487 个 eligible 只被聚合成 `rh_shadow_episodes.eligible_steps`，并没有形成可逐步对账的六张表记录。

### 2.2 不是条件跳过

`rh_gate_decisions` 和 `rh_position_marks` 的 insert 不受 `eligible` 控制，insert 位于 reservation 条件之后、循环每步都会执行：

`scripts/lp_rh_shadow_runner_v1_readonly.py:524-536`、`659-678`

所以如果目标 connection 是持久库，至少 gate/mark 应该每步落一行，包括不 eligible 的步骤。

reservation 则本来就不是每个 eligible 一行：只在 `eligible and not position_open` 时尝试，首次成功后 `position_open=True`：

`scripts/lp_rh_shadow_runner_v1_readonly.py:527-536`

### 2.3 Economic、position、journal 是真正缺 writer/调用

每步只做了：

1. 组装经济输入；
2. 调 NetCover；
3. 在内存中计算 terminal decision；
4. 在内存中计算 NAV/HODL。

证据：`scripts/lp_rh_shadow_runner_v1_readonly.py:506-523`、`639-657`。

随后实际持久化的只有 gate 和 mark：`scripts/lp_rh_shadow_runner_v1_readonly.py:659-678`。

因此最终分类是：

- `rh_gate_decisions` / `rh_position_marks` / `rh_bucket_reservations`：**(c) 临时 scratch 写入后丢失**；
- `rh_economic_evaluations` / `rh_shadow_positions` / `rh_journal`：**(a) 生产 writer 缺失或未接线**；
- **不是 (b)**：gate/mark insert 没有被 eligible 条件跳过；
- **不是 (d)**：唯一持久化的其它表是 `shadow.db` 中的 episode/blocker 汇总，不包含六张目标表，见 `scripts/lp_rh_shadow_daemon_v1_readonly.py:49-66`、`240-248`。

## 3. Stage B 每条验收需要的数据与缺口

PRD 的 Stage B 要求是至少 14 个完整日、覆盖一个周末，并同时满足账差、关键不变量、漏闸、全成本、HODL、OOS、不确定性、最差日和 NetCover 条件：

`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:1066-1078`

| Stage B 验收 | 需要的数据表 | 当前缺口 |
|---|---|---|
| 14 个完整日、一个周末 | `rh_market_states.sample_time`；Shadow 实际运行连续性还需要 `shadow.db.rh_shadow_episodes.started_at/ended_at` | readiness 只用市场表的 `MIN/MAX` 计算跨度，周末直接传 `None`：`scripts/lp_rh_readiness_v1_readonly.py:739-760`。daemon 的 episode 时间只在 `shadow.db`：`scripts/lp_rh_shadow_daemon_v1_readonly.py:49-60`、`195-210`。 |
| 未解释账本差异 = 0 | 主表是 `rh_journal`；正式审计结果应落 `rh_reconciliation_runs`；NAV 勾稽还需 `rh_position_marks` | `rh_journal` 为空；`rh_reconciliation_runs` 也为空。现有 invariant audit 只检查账户非空和金额非负，不做借贷配平：`scripts/lp_rh_readiness_v1_readonly.py:611-627`。Stage B 调用还把它硬编码成 0：`scripts/lp_rh_readiness_v1_readonly.py:758-760`。 |
| 关键不变量违反 = 0 | `rh_gate_decisions`、`rh_market_states`、`rh_position_marks`、`rh_journal`；资金并发不变量还需 `rh_bucket_reservations`；仓位生命周期需 `rh_shadow_positions` | 现有 audit 只覆盖 gate 一致性、市场价、mark NAV、journal 基础格式：`scripts/lp_rh_readiness_v1_readonly.py:538-627`。六张表为空时，很多检查实际上没有样本可查。 |
| 已知严重事件漏闸 = 0 | `rh_market_states.health_flags_json` + `sample_time`；对应的 `rh_gate_decisions.terminal_bits_json/reasons_json/primary_status`；RPC 类事件还需 `rh_rpc_health`；源证据来自 `rh_source_snapshots` | `rh_gate_decisions` 为空，无法证明“事件被拦住”；Stage B 当前把 `missed_risk_events` 写死为 0：`scripts/lp_rh_readiness_v1_readonly.py:758-760`。判据本身需要 gate 与市场样本关联，见 `docs/specs/20260910_RH-02bm_stage_b_evidence.md:60-68`。 |
| 实际全成本 | `rh_economic_evaluations.fee_ev/reward_ev/cost_components_json/netcover/abs_profit`；输入来自 `rh_market_states`、`rh_pool_events`、`rh_rpc_health`、`rh_source_snapshots`；结果由 `rh_gate_decisions` 固化 | 经济表为空。runner 虽调用 `apply_netcover_gate()`，但只保存 gate bits/reasons，没有保存 `gated` 经济字段：`scripts/lp_rh_shadow_runner_v1_readonly.py:506-510`、`659-667`。PRD 全成本清单见 `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:559-567`。 |
| HODL 差异 | `rh_shadow_positions` 保存实际初始两腿和 liquidity；`rh_position_marks` 保存逐时刻 NAV；`rh_journal` 提供外部资金流 | HODL 只在内存计算：`scripts/lp_rh_shadow_runner_v1_readonly.py:655-657`；episode 只保存一个 `hodl_delta` 汇总：`scripts/lp_rh_shadow_runner_v1_readonly.py:800-806`。`rh_shadow_positions` 没有生产 writer，无法证明初始 lot。PRD 要求实际初始两腿而非 50/50：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:625-629`。 |
| OOS | `rh_economic_evaluations.model_version/policy_version/evaluated_at`；`rh_gate_decisions.snapshot_ids_json/decided_at`；不可变输入来自 `rh_source_snapshots` | 当前没有训练窗口/评价窗口边界，也没有持久经济 evaluation。版本字段虽在 schema 中存在：`scripts/lp_rh_store_v1_readonly.py:82-97`，但没有 writer。PRD 要求参数冻结、训练/评价分离：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:1074-1075`。 |
| 最差日 | 至少需要逐日 `rh_position_marks` 的 NAV/PnL，结合 `rh_journal.booked_at` 的外部流和 `rh_shadow_positions` 的持仓生命周期 | 当前只有 episode 起止 NAV，没有逐日 mark 的持久数据：`scripts/lp_rh_shadow_runner_v1_readonly.py:800-809`。 |
| 不确定性、收益集中度 | 同一批逐步 NAV/收益序列，来源是 `rh_position_marks`、`rh_journal`、`rh_economic_evaluations`；然后做区块重采样、时段分组等报告 | 当前没有逐步持久序列，也没有对应的统计产出。PRD 明确要求区块重采样、时段分组和收益集中度：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:1074-1075`。 |
| NetCover 门槛 | `rh_economic_evaluations.netcover/abs_profit/horizon_hours/position_usd`；`rh_gate_decisions.terminal_bits_json` 中的 `netcover_pass` 和 `absolute_profit_pass`；输入源为市场/池/成本证据 | economic 表为空，gate 表在 scanner.db 为空。引擎确实计算 `netcover` 并比较 Shadow/Tiny Live 阈值：`scripts/lp_netcover_engine_v1_readonly.py:177-220`，但结果没有落到持久证据库。PRD 阈值见 `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:540-547`、`1076`。 |

### 六张空表对应的缺口清单

1. `rh_economic_evaluations`：缺每步全成本、NetCover、绝对利润、模型/策略版本。
2. `rh_gate_decisions`：缺逐步十项合取、拒绝理由、快照关联和漏闸审计入口。
3. `rh_shadow_positions`：缺实际初始 token 两腿、区间、虚拟 liquidity、开闭仓生命周期。
4. `rh_position_marks`：缺逐时刻 reference/liquidation NAV、费用和回撤序列。
5. `rh_journal`：缺双边记账、外部资金流、gas/费用/库存变动的原始账。
6. `rh_bucket_reservations`：缺持久化资金占用、释放和并发超配证据。

另外，六张表之外的 `rh_reconciliation_runs` 也为空；PRD 将它定义为原始余额/头寸证据、差额和 verdict 的正式对账表：`scripts/lp_rh_store_v1_readonly.py:132-136`、`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:804-811`。

## 4. `_build_state` 的 `terminal_gate` 空表行为

当 `rh_gate_decisions` 为 0 行时：

```python
tg = ...fetchone()
```

得到 `None`，条件不成立，因此不会设置 `state["terminal_gate"]`：

`scripts/lp_rh_readiness_v1_readonly.py:762-765`

准确说：

```python
"terminal_gate" not in state
state.get("terminal_gate") is None
```

下游 dashboard 通过 `state.get()` 读取：

`scripts/lp_rh_readiness_v1_readonly.py:691-694`

`_render_terminal_gate()` 对 `None` 使用空字典，并把十项都渲染为 `NOT_MEASURED`：

`scripts/lp_rh_readiness_v1_readonly.py:337-342`；`78-80`

所以，**单就 `terminal_gate` 这条路径，不会把空表变成乐观的 True；它显示的是 `NOT_MEASURED`。** `graduation_verdict()` 也不使用 `terminal_gate`，只使用 Stage A、Stage B 和 live gate：

`scripts/lp_rh_readiness_v1_readonly.py:261-287`、`678-693`

但是同一文件存在更严重的同族问题：

```python
unexplained_ledger_diffs=0
missed_risk_events=0
```

`scripts/lp_rh_readiness_v1_readonly.py:758-760`

而 `stage_b_status()` 把数值 0 当成“已经查证且确实为零”：

`scripts/lp_rh_readiness_v1_readonly.py:206-232`

因此，一旦天数和周末条件被满足，账本差异和漏闸会被静默放行。当前还被 `weekends_covered=None` 阻挡，所以整体暂时未必显示 Stage B PASS，但这两个字段已经是错误的乐观输入。

此外，空表 invariant audit 也会返回 0：

`scripts/lp_rh_readiness_v1_readonly.py:552-563`、`621-627`

随后被 `_build_state` 当成真实 invariant count 使用：

`scripts/lp_rh_readiness_v1_readonly.py:718-721`

### 同族缺陷节点

`RH-READINESS-EMPTY-EVIDENCE-AS-ZERO`

覆盖：

- Stage B ledger diff / missed risk 被硬编码为 0：`scripts/lp_rh_readiness_v1_readonly.py:758-760`
- 空 invariant 表返回 `violations_count=0`：`scripts/lp_rh_readiness_v1_readonly.py:552-563`、`621-627`

这正是“无证据却当作零、无异常、数字正常、结论失真”的静默假绿族。

## 5. 最小接线方案

### 必须做

| 改动 | 所需输入 | 影响的 Stage B 验收 |
|---|---|---|
| 在 `scripts/lp_rh_shadow_daemon_v1_readonly.py:221-248` 增加持久化 ledger connection，把 per-round scratch 的六张表写入 `scanner.db`，同时保留 live source 的只读连接 | `scanner.db` 路径、episode ID、单 writer 事务、每步 sample identity | 全部；尤其 gate、NAV、reservation、逐步审计 |
| 在 `scripts/lp_rh_shadow_runner_v1_readonly.py:506-510` 后增加 economic evaluation writer | `candidate_key`、`source_payload_hash/snapshot_id`、model/policy version、horizon、position、fee/reward EV、各成本项、NetCover、absolute profit、missing inputs、block hash/number、评价时间 | 实际全成本、OOS、NetCover、最差日/不确定性原始数据 |
| 在首次 reservation 成功处写 `rh_shadow_positions` | `strategy_episode`、position ID、pool/profile/bucket、实际初始 token0/token1 raw、tick lower/upper、virtual liquidity、opened_at | HODL、持仓生命周期、资产/资金不变量 |
| 在现有 mark 写入处补齐持久化 provenance 和 liquidation NAV | `price_snapshot_id`、reference NAV、liquidation NAV、accrued fee、unvalued risk、block hash/number；当前 `price_snapshot_id` 与 `liquidation_nav` 都是空：`scripts/lp_rh_shadow_runner_v1_readonly.py:672-678` | 实际全成本退出、HODL、最差日、不确定性、回撤 |
| 把 `book_journal_event()` 接入 Shadow 的虚拟开仓、费用、collect、remove、swap、外部流事件 | raw amount、asset、debit/credit account、idempotency key、flow kind、event time、引用的 episode/step；writer 目前只在 `scripts/lp_rh_pnl_v1_readonly.py:136-153` | 未解释账差、外部流、gas 只扣一次、NAV 勾稽 |
| reservation 使用持久 connection，并补齐虚拟 close/release 生命周期 | `intent_id`、policy/bucket/amount、PENDING/CONFIRMED/RELEASED 状态、释放时间和原因；现有 production 只有 `try_reserve()`：`scripts/lp_rh_shadow_runner_v1_readonly.py:527-536` | 资金桶超配、reservation 不变量、持仓生命周期 |
| 处理持久化后的 `decision_id` 幂等性 | sample identity、episode/step identity、重复样本的 skip/compare 规则。当前 decision ID 不含 episode：`scripts/lp_rh_terminal_gate_v1_readonly.py:167-179`，重复会抛错：`tests/test_lp_rh_shadow_runner_v1_readonly.py:227-238` | 14 天连续运行、重启恢复、逐步 gate 完整性 |
| 修 readiness 的三个 Stage B 输入：周末、账差、漏闸；空表返回 `None`，不能返回 0 | `rh_market_states.sample_time`、`rh_journal`、`rh_gate_decisions` 与同期 `health_flags_json` | 14 日/周末、零未解释账差、零漏闸 |
| 修空 invariant evidence 的语义 | 相关表不存在或为空时返回 unavailable，而不是 `violations_count=0`；当前行为见 `scripts/lp_rh_readiness_v1_readonly.py:552-563`、`621-627` | 零关键不变量违反，避免同族假绿 |

上述 readiness 接线方向已经在规格中明确规定：`docs/specs/20260910_RH-02bm_stage_b_evidence.md:33-89`。

### 可以后做，但在宣布 Stage B PASS 前必须完成

- 增加按自然日/周末统计完整覆盖、最差日、收益集中度的只读聚合报告。影响：14 日、周末、最差日。依据：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:1066-1075`。
- 固化训练窗口、评价窗口、模型版本和策略版本，生成 OOS 报告。影响：OOS。依据：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:1074-1075`。
- 对持久化的逐步 NAV/PnL 做区块重采样和时段分组不确定性分析。影响：不确定性。依据：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:1074-1075`。
- 增加正式 `rh_reconciliation_runs` writer，保存原始余额/仓位、差额、审计 verdict。影响：零账差。表定义：`scripts/lp_rh_store_v1_readonly.py:132-136`。
- 为 HODL 值、quote provenance、OOS 边界增加结构化字段；当前 HODL 只在内存和 episode 汇总中存在：`scripts/lp_rh_shadow_runner_v1_readonly.py:655-657`、`800-806`。
- 完成 `q_min/q_max` 经济区间计算；当前明确没有计算模块：`scripts/lp_rh_size_interval_v1_readonly.py:4-7`。影响：经济可行仓位与 NetCover/绝对利润报告。
---

## 主脑补充：codex 揪出了一个我自己上一轮引入的缺陷

报告 §4 指出 `audit_invariant_violations` 在**表存在但为空**时返回
`violations_count=0`（`scripts/lp_rh_readiness_v1_readonly.py:552-563`、`621-627`），
随后被 `_build_state` 当成「已查证、确实零违反」使用（`:718-721`）。

这是上一轮我把该函数**从「永久阻断」改成「接真实审计」时引入的**。
当时解决的问题是「`invariant_violations` 全仓库无人提供 → 闸门永久阻断」，
改法本身对，但漏了「表存在却是空的」这个状态：

```
表不存在   -> 应为 None（未知）
表存在但空 -> 应为 None（未知）   <-- 漏了这个，当前返回 0
表存在有行 -> 真实计数
```

六张账本表现在**全部是空的**，所以这个缺陷此刻正在生效：
Stage A 的 `invariant_violations` 检查是在对着空气打勾。

与 `unexplained_ledger_diffs=0` / `missed_risk_events=0`（RH-02bm 正在修）
属于同一族，codex 给这族起的节点名是 `RH-READINESS-EMPTY-EVIDENCE-AS-ZERO`。
本仓库「静默假绿」计数由此增至 **27 例**（第 27 例是主脑自己写的）。

**待派**：`docs/specs/` 下将补 RH-02bo 修此项——需等 RH-02bm-2 改完
`lp_rh_readiness_v1_readonly.py` 才能派，两包改同一文件。

## 主脑据此派出的包

| 包 | 内容 | 通道 | 状态 |
|---|---|---|---|
| RH-02bp | daemon 加 `--ledger-db`，**默认行为一字不改**；给了路径才持久化 | qwen | 跑 |
| RH-02bq | runner 里补 `rh_economic_evaluations` writer | qwen | 跑 |
| RH-02bm-2 | 修 `datetime.time.min` 崩溃 + 补 Stage B 三证据的测试 | gemini | 跑 |
| RH-02bo | 修 invariant 空表返回 0（本节的缺陷） | — | **待派**（等 bm-2） |
| RH-02bn | Stage A 判定窗口（coverage 口径） | — | **待派**（等 bm-2） |

RH-02bp 刻意设计成**零风险**：不给 `--ledger-db` 时与现在完全一致，
代码就绪但不生效。是否切换到持久库、是否重启 daemon，是主脑验收后
**需要用户点头**的决定——那意味着让一个至今只读的 daemon 开始写生产库。

---

## 更正（2026-09-10 07:20）：`rh_position_marks` 的「重复」是误判

`d957453` 的 commit message 与当时给用户的汇报里，把
「`rh_position_marks` 778 行但只有 317 个不同 `mark_time`」称为缺陷，
并写了「重复的 NAV 序列会污染最差日与不确定性统计」。**这是错的。**

按 episode 拆开看，每个 episode 内部零重复：

```
rh-shadow-...064033-0   181 行, 181 个不同时刻
rh-shadow-...065533-1   197 行, 197 个不同时刻
rh-shadow-...071033-2   200 行, 200 个不同时刻
rh-shadow-...071432-0   200 行, 200 个不同时刻

主键 (position_id, mark_time) 重复组数: 0
```

`position_id` 是 `f"rh-shadow-{strategy_episode}"`，含 episode，
所以**跨 episode 在同一时刻各有一行是主键允许的，语义上也应该允许**——
每一轮是一次独立的反事实模拟，各自记录自己的 NAV 序列。
把它们合并或去掉才会真正破坏 Stage B 的统计。

**误判的原因**：只看了聚合数字 `count(*) != count(distinct mark_time)`，
没有按 `position_id` 分组再看。这正是本仓库反复出现的那类错误——
聚合掩盖分组结构。同一个毛病本轮已在别人的产出里批评过四次。

**修复本身没有做错事**：RH-02ca 要求按 `(position_id, mark_time)` 去重，
防的是**同一 episode 内** rollback 重跑造成的重复，那是真实存在的路径。
跨 episode 的多行不受影响。所以代码是对的，只是当初给出的理由有一半站不住。

**仍然成立的部分**：`rh_economic_evaluations` 卡在 181 不再增长是真缺陷，
根因（三张表不在 `_copy_new_rows` 里）也是真的。修复后：

```
rh_economic_evaluations  181 -> 317   与 rh_gate_decisions 的 317 一致
economic 主键重复         0
daemon 日志              copied={gate:16, econ:136, marks:200, pos:0, journal:0, resv:0}
```

`econ:136` 就是修复前会被丢掉的那部分。
