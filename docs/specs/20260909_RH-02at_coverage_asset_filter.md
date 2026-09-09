# RH-02at：覆盖率不按资产过滤，接入第二个资产会立即错误毕业

## 铁证（codex 只读审计已坐实并量化）

`scripts/lp_rh_coverage_audit_v1_readonly.py:226-227` 查询全部 `sample_time`，
**没有 `WHERE asset_address = ?`**。

用现有真实样本按时间交错拆成两个虚拟资产实测：

```
虚拟 A   4551 行   覆盖率 0.4838915
虚拟 B   4551 行   覆盖率 0.4838915
未过滤合并计算      0.9676802     ← 约为单资产的 1.9998 倍
```

**两个资产各自只有 48.4% 采样率，合并后显示成 96.8%。**
若两个资产都各自拥有当前完整样本流，合计会到 1.935，**直接越过 0.99 阈值**。

传导路径（每一步都已核实）：
- `scripts/lp_rh_readiness_v1_readonly.py:247-254` 对整个 `rh_market_states`
  做 `MIN/MAX/COUNT`，传给 `stage_a_status`
- `stage_a_status` 在 `:75-83` 返回 `coverage_ratio` 与 `passed`
- `graduation_verdict` 在 `:156` 读 `stage_a.get("passed")`

**覆盖率高估会直接让 Stage A 的 `passed` 变真。**

当前不触发：`rh_market_states` 只有 1 个资产
（`0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`，9102 行，约 39.19 小时，
覆盖率 0.96769，尚未过 0.99）。**但 PRD 的目标本来就是多资产股票代币宇宙——
接入第二个资产的那一刻，这就是一个会自己变绿的毕业闸门。**

## 你要做的（只改这一个模块，readiness 的接线是下一包）

给 `scripts/lp_rh_coverage_audit_v1_readonly.py` 的覆盖率查询加资产维度：

1. 相关函数增加**必填**的 `asset_address` 关键字参数（不要给默认值，
   不要做成 `Optional` 后在内部兜底——那会让漏传变成静默的全表统计，
   正是本项目那一族缺陷的做法）。
2. SQL 加 `WHERE asset_address = ?`。
3. 若调用方需要多资产，提供一个**逐资产返回**的函数
   （返回 `{asset_address: coverage_dict}`），**不要把多资产行数相加**。
4. 若库里存在多个资产而调用方只传了一个，这是合法的（就看那一个）；
   但**如果传入的 asset_address 在库里一行都没有**，
   要返回明确的「无该资产数据」而不是 0 覆盖率——
   「没有这个资产」与「这个资产覆盖率为 0」是两件事。

## 不许动

`scripts/lp_rh_readiness_v1_readonly.py`（接线是下一包，且它今晚刚被改过）、
`scripts/lp_rh_shadow_runner_v1_readonly.py`（两条线在改）、任何 `.db`。
`tests/test_lp_rh_coverage_audit_v1_readonly.py` **只允许新增测试**。

## 验收标准

1. 用**真实库** `reports/lp_rh/scanner.db` 跑，传入
   `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`，
   覆盖率应约为 `0.96769`（与审计实测一致，容差 1e-3），把实际值贴进报告。
2. 传入一个库里不存在的地址 → 返回「无该资产数据」，**不是 0.0**。
3. 单测：构造两个资产各占一半样本的内存库，断言
   逐资产覆盖率各约 0.484，且**没有任何一个返回值等于两者之和**。
4. 漏传 `asset_address` → `TypeError`（因为是必填参数），
   写一条测试断言这一点，防止将来有人加回默认值。
5. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_coverage_audit_v1_readonly.py -q -p no:cacheprovider`
   全绿，原有测试全部仍在（若原有测试因新增必填参数而失败，
   **允许修改它们的调用处补上参数**，但不许删测试、不许放宽断言，
   并在报告里逐条说明改了哪几行）。

## 交付格式（只读沙箱，写不了文件——但这不妨碍你完成任务）

**你不需要落盘。把完整文件内容打印在最后一条消息里就是交付本身**，
调度者会写进仓库。上一轮有 worker 误以为「写不了文件 = 做不了任务」，
只回了标记没回内容，导致落盘器写入空内容。不要重蹈覆辙。

```
===FILE:scripts/lp_rh_coverage_audit_v1_readonly.py===
（完整内容，不要用 markdown 代码围栏包裹）
===FILE:tests/test_lp_rh_coverage_audit_v1_readonly.py===
（完整内容）
===END===
```
