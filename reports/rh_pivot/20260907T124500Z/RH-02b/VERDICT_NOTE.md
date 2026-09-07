# RH-02b 主脑裁决：第一轮 REJECT，第二轮 ACCEPT

## 第一轮退回（2026-09-07 18:50）

资金桶与时段分类全部通过，仅 `evaluate_health` 退回两条：

- **FAIL-1** 时间参数隐含要求 datetime，但存储层统一 RFC3339 字符串，传字符串抛 `TypeError: unsupported operand type(s) for -: 'str' and 'str'`（主脑实测复现）。
- **FAIL-2** 陈旧判定主路径 `(now - t).total_seconds() > 阈值` **零测试覆盖**，测试只打到 `None` 分支与全正常分支。属 PRD §10.1 所述假绿形态。

退回原因已追加进 spec，明确要求 `lp_rh_bucket_ledger_v1_readonly.py` 及其测试一行不动。

## 第二轮验收（主脑独立复核，不依赖 worker 自报）

| 检查 | 结果 |
|---|---|
| 字符串时间戳 | 不再崩，返回 `['ORACLE_STALE']` |
| oracle 差 7200s / 阈值 3600 | `['ORACLE_STALE']`；阈值改 10800 → `[]` |
| api 差 600s / 阈值 300 | `['API_STALE']` |
| 字符串与 aware datetime | 结果**完全相等** |
| naive datetime | 抛 `NAIVE_DATETIME: now` |
| 无时区字符串 | 抛 `NON_UTC_TIMESTAMP: now` |
| 新测试 | 34 passed（29 + 5） |
| 全量 pytest | **3208 passed / 14 skipped / 0 failed** |
| 脚本行数 | 227（≤250） |
| tracked diff | 空；bucket_ledger 两文件未被改动 |

## 第一轮已通过、第二轮回归无损的硬规则

| 用例 | 验证 |
|---|---|
| **T15** | `2026-09-07 14:30 UTC`（ET 10:30 周一）→ `HOLIDAY`，`allows_new_position` False |
| **T16** | 工作日跨 DST：3/6 ET 09:35(-05:00) 与 3/9 ET 10:35(-04:00) 同为 `RTH`，偏移正确；11/27 提前收市 ET 13:30 → `POSTMARKET`；收盘边界 ET 15:59 `RTH` / 16:01 `POSTMARKET` |
| **T25** | C=100 → CORE 42.5 / STOCK 21 / MEME 8；与旧 50U 下限冲突显式报告 `CAPITAL_POLICY_CONFLICT`，函数不改任何金额 |
| **T27** | 先占 40U 成功（room_after 2.5），再占 10U 拒绝 `BUCKET_ACTIVE_CAP_EXCEEDED`，库中仅 1 条 PENDING |
| **T51** | `BROADCAST_UNKNOWN` 拒绝释放（`CANNOT_RELEASE_BROADCAST_UNKNOWN`），且仍计入占用，后续 5U 申请被拒 |

**裁决：ACCEPT。**
