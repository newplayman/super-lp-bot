# RH-04f：把九个非 netcover 合取项接进 Shadow 闭环（Stage B 的硬拦路石）

## 实测现状

主脑 2026-09-08 18:0x 用实盘数据跑 `lp_rh_shadow_runner_v1_readonly`（40 个样本）：

```
total_steps        : 40
eligible_steps     : 0
status_counts      : {"INPUTS_UNAVAILABLE": 40}
dominant_blocker   : {"legacy_required_conjunction": 40}
```

**40 步全部不合格，且全部卡在同一项。** 根因不是数据缺失，是**接线缺失**：

- `load_samples_from_db`（第 167 行）只取 5 个字段：
  `asset_address, sample_time, chain_id, reference_mid, multiplier_human`。
- `_terminal_record`（第 66 行）用 `if key in sample` 逐个搬运合取项——
  **样本里一个合取项都没有**，于是十项全缺，优先级第一的
  `legacy_required_conjunction` 成为主阻塞。

十项合取（`CONJUNCT_ORDER`，PRD §11.5）里 `netcover_pass` 已由闸自己算，
**其余九项没有任何生产者**。本包补上它们。

## 关键：这九项必须**调用已有模块算出来**，不是从库里读，也不是硬编码 True

本仓已有对应模块，逐一对应如下。**只调用，不重写它们的逻辑**：

| 合取项 | 用哪个模块 |
|---|---|
| `identity_verified` | `scripts.lp_rh_registry_v1_readonly`（chainId 4663 身份闸） |
| `protocol_capabilities_sufficient` | `scripts.lp_rh_capabilities_v1_readonly` |
| `data_complete_and_fresh` | 样本自身的 `reference_age_secs` / `source_payload_hash` + `scripts.lp_rh_market_session_v1_readonly` |
| `market_and_chain_risk_pass` | `scripts.lp_rh_market_session_v1_readonly` + `scripts.lp_rh_premium_guard_v1_readonly` |
| `profile_policy_pass` | `scripts.lp_rh_bucket_ledger_v1_readonly` |
| `absolute_profit_pass` | 已 gated 记录里的 `fee_ev_usd` 与固定成本 |
| `position_and_exit_depth_pass` | `scripts.lp_rh_exit_depth_v1_readonly` |
| `capital_policy_pass` | `scripts.lp_rh_bucket_ledger_v1_readonly`（`CAPITAL_POLICY_CONFLICT` 不可自动解锁） |
| `legacy_required_conjunction` | 上述八项的合取 **加上** 旧 Base 闸的必需项 |

**任何一项算不出来时必须为 `False` 并在 `reasons` 里写明具体是哪一项、为什么**，
**绝不允许为了让 Shadow 跑通而默认 `True`**。fail-closed 是本项目的底线。

## 改哪些文件

只改 `scripts/lp_rh_shadow_runner_v1_readonly.py`，测试追加进
`tests/test_lp_rh_shadow_runner_v1_readonly.py`。**现有测试一条不许改、不许删。**
若某条因本次变更失败，停下来写明是哪条、为什么，交主脑裁决。

### 1. `load_samples_from_db` 取全所需列

改成同时取 `session`, `health_flags_json`, `reference_age_secs`, `oracle_paused`,
`source_payload_hash`, `reference_bid`, `reference_ask`（`rh_market_states` 全部有这些列）。
缺列的行**不得丢弃**，把缺失字段留 `None`，由下游判 False。

### 2. 新增 `compute_conjuncts(sample, gated, *, pool_meta, now_fn) -> tuple[dict, list[str]]`

返回 `({合取项名: bool}, [失败原因字符串])`。九项逐一按上表计算。
`pool_meta` 由调用方传入（attestation、tick 数据、decimals 等），
**缺 `pool_meta` 时对应项为 False**，不得跳过。

### 3. `_terminal_record` 改为使用 `compute_conjuncts` 的结果

保留现有「样本里显式给了就用样本的」行为作为**测试注入通道**，
但真实路径走 `compute_conjuncts`。

### 4. 顺带修一个误导性字段

`episode_summary` 第 208 行：
`"skipped_samples": sum(1 for s in steps if s.nav is None) + load_skipped`
把「装载时跳过的样本」与「没产出 NAV 的步」加在一起。实测库里只有 7 行空
`reference_mid`，却报 `skipped_samples: 40`。拆成两个字段：
`skipped_at_load`（装载跳过）与 `steps_without_nav`（无 NAV 步数），
**`skipped_samples` 字段删除**，避免继续误导。

## 新增测试（**≥14 条**）

- 九项全部满足的注入样本 → `terminal_eligible True`，`primary_status` 不是 `INPUTS_UNAVAILABLE`。
- 逐项摘除：对九项**每一项**各写一条测试，只让该项为 False，
  断言 `dominant_blocker` 正是该项（**九条，变异见证**）。
- `pool_meta` 为 `None` → 依赖它的项为 False 且 `reasons` 里点名，
  **不得整体抛异常**。
- `capital_policy_pass`：`CAPITAL_POLICY_CONFLICT` 存在时恒 False，
  且**无法通过任何入参组合被置 True**（自证其罪测试）。
- `skipped_at_load` 与 `steps_without_nav` 分别正确；断言旧的
  `skipped_samples` 键**已不存在**。
- 真实库回归：从 `reports/lp_rh/scanner.db` 读 40 个样本跑一遍，
  断言 `dominant_blocker_counts` 里**不再全是** `legacy_required_conjunction`
  （即接线生效；不要求 eligible > 0，那取决于市场）。

## 不许动
不改其他脚本；不写活库（只读打开）；不联网；不碰任何签名/广播路径。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python scripts/lp_rh_shadow_runner_v1_readonly.py --samples 40 --out /tmp/shadow_check.json
```
定向全绿且 ≥14 新增；全量 0 failed / 14 skipped；
第三条命令的 `summary` 原样贴出（重点看 `dominant_blocker_counts` 是否已分散）。
