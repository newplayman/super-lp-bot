# RH-02cl — T31：把经济可行区间接进主链（最后一个零引用模块）

## 背景

`scripts/lp_rh_size_interval_v1_readonly.py` 自己的 docstring 就写着
**"Not wired into netcover or the terminal gate (that is the next package)"**。
那个 next package 一直没来，模块被 runner / netcover 引用 **0 次**。

`rh_economic_evaluations` 有 `q_min` / `q_max` 两列，至今全是 NULL。

模块接口已经是对的，本包只负责算出两个边界喂给它：

```
size_interval(q_min=, q_max=) -> {"status", "q_min", "q_max", "width", "reason"}
  任一边界 None  -> INPUTS_UNAVAILABLE, width=None（None 不是 0）
  q_min > q_max  -> SIZE_INTERVAL_EMPTY, width 为负数，如实报出
  q_min == q_max -> SIZE_INTERVAL_POINT, 合法
  q_min < q_max  -> COMPUTED
```

## PRD 6.4 的公式

```text
q_max = min(
  bucket_active_room,
  global_active_room,
  approved_position_cap,
  asset_exposure_room,
  POSITION_TVL_SHARE × verified_pool_TVL,      # POSITION_TVL_SHARE = 0.0005
  measured_exit_depth_cap,
  spendable_cash_after_native_gas_reserve
)

NetEV(q,H) = q × (每美元费/奖励 − 每美元库存与可变执行成本) − 固定往返成本
  括号内 ≤ 0     -> 增大仓位也不成立
  q_min > q_max  -> COMPUTED_FAIL: SIZE_INTERVAL_EMPTY
  退出报价拿不到 -> INPUTS_UNAVAILABLE（与上面不是同一个结论）
```

## 哪些能算、哪些拿不到（已核实，照此实现）

**能算的四项：**

| 约束 | 来源 |
|---|---|
| `bucket_active_room` | `bucket_active_cap(capital_usd, "CORE") - reserved_total(conn, "CORE", POLICY_ID)` |
| `POSITION_TVL_SHARE × TVL` | `Decimal("0.0005") * pool_meta["tvl_usd"]`（生产值 32037565.0 → 16018.78） |
| `measured_exit_depth_cap` | `exit_depth_for_size(...)` 返回的 `max_exit_usd` |
| `spendable_cash_after_native_gas_reserve` | `capital_usd - <RH-02ck 的 exit gas 储备>`；RH-02ck 若尚未落地就记为 None |

**拿不到的三项**（组合层/政策层数据，本包不造）：

```
global_active_room      需要跨桶汇总，rh_bucket_reservations 目前只有 CORE
approved_position_cap   资本政策未获批（PRD D02，approved_for_live=false）
asset_exposure_room     需要钱包余额与 LP 底层暴露
```

### 部分约束绝不能冒充完整约束

`q_max` 取**能算的那些**的 min，但返回结构里必须带：

```python
{"q_max": Decimal|None,
 "q_max_binding": "<哪一项是最小的>",
 "q_max_constraints_applied": ["bucket_active_room", "tvl_share", ...],
 "q_max_constraints_missing": ["global_active_room", "approved_position_cap",
                               "asset_exposure_room"],
 "q_max_is_partial": True}
```

**`q_max_is_partial` 为 True 时，这个 q_max 不得被当作准入依据。**
本包只把结果写进 `rh_economic_evaluations`，**不接进终闸**——
用一个缺三项约束的上限去放行开仓，正是本仓库 27 例「静默假绿」的形状。
接进终闸要等那三项有了来源，那是另一个包。

### q_min 的算法

```
per_dollar_net = (fee_ev_usd + reward_ev_usd
                  - il_ev_usd - lvr_ev_usd - slippage_usd
                  - exit_latency_loss_usd - reward_conversion_cost_usd) / position_usd
fixed_round_trip = entry_cost_usd + exit_cost_usd + gas_usd

per_dollar_net <= 0  -> q_min = None, reason "NO_SIZE_IS_PROFITABLE"
否则                  -> q_min = fixed_round_trip / per_dollar_net
```

八个成本项的键名去 `_COST_COMPONENT_KEYS`（runner 里）抄，不要手写。
**任一项为 None → q_min 为 None**，绝不当 0 处理
（缺一项成本就把它当零，会把 q_min 算小，是最危险的方向）。

## 要做的事

1. 在 `scripts/lp_rh_shadow_runner_v1_readonly.py` 里新增
   `compute_size_interval(...)`：按上面两节算出 q_min / q_max，
   调 `size_interval()` 得到 status，返回完整结构。
2. 每步算出 `gated` 之后调用它（与 `rh_economic_evaluations` 写入同一处）。
3. 把 `q_min` / `q_max` 写进 `rh_economic_evaluations` 对应列
   （**这两列至今全是 NULL**），把 partial 元数据写进
   `cost_components_json` 的 `"size_interval"` 子键。
4. episode summary 里加 `size_interval_status_counts`（各 status 出现次数），
   daemon 日志能看见。

## 不许动

- **不要把 q_max 接进终闸或任何 conjunct**（见上面那段）。
- 不要改 `size_interval()` / `is_actionable()` / `clamp_to_interval()`。
- 不要改 NetCover 公式、`bucket_active_cap`、`exit_depth_for_size`。
- 不要碰 `scripts/lp_rh_shadow_daemon_v1_readonly.py`、
  `scripts/lp_rh_reorg_detector_v1_readonly.py`。
- **不要改数据库 schema**（`q_min`/`q_max` 列已存在）。
- 测试用内存库或 `tmp_path`；对生产库只读。
- **不要重启或 kill 任何进程。**
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（追加到 `tests/test_lp_rh_shadow_runner_v1_readonly.py`）

本会话已有**八次**「构造的输入进不去目标分支」，其中一次是
`insert_row` 不 commit、`close()` 静默回滚导致测试对空表断言。
写完请逐条确认断言真的走到了目标分支。

1. 正常输入 → `rh_economic_evaluations.q_min` 与 `q_max` **非 NULL**，
   `q_min < q_max`，status 为 `COMPUTED`。
   ——这两列至今全 NULL，这条是本包的核心证据。
2. `per_dollar_net <= 0`（把 fee_ev 调到很小）→ `q_min is None`，
   status `INPUTS_UNAVAILABLE`，reason 含 `NO_SIZE_IS_PROFITABLE`。
3. 任一成本项为 None → `q_min is None`（**不是把该项当 0**）。
4. `q_min > q_max`（把 TVL 调到很小使 q_max 变小）→ status
   `SIZE_INTERVAL_EMPTY`，`width` 为负且如实写入。
5. `q_max_is_partial is True`，`q_max_constraints_missing` 恰好含那三项。
6. **终闸未被影响**：同一批样本在本包前后，
   `rh_gate_decisions` 的 `terminal_bits_json` 逐字相同。
   ——这条保证 q_max 没有偷偷参与放行。
7. `exit_depth_for_size` 返回 `max_exit_usd is None` → 该约束不参与 min，
   并出现在 `q_max_constraints_missing` 里。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿，新增 ≥7 条。
2. 全量 `python3 -m pytest tests/ -q` 通过。
3. `grep -n "size_interval" scripts/lp_rh_shadow_runner_v1_readonly.py` 有生产调用。
4. `grep -n "q_max" scripts/lp_rh_terminal_gate_v1_readonly.py` **无输出**
   （确认没接进终闸）。
5. `git status --short` 里只有
   `scripts/lp_rh_shadow_runner_v1_readonly.py` 和它的测试被改动。
