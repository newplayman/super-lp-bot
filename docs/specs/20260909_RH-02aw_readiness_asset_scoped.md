# RH-02aw：Stage A 判定接上按资产的覆盖率（RH-02at 的接线）

## 背景

`RH-02at`（commit `bfc6ed4`）已把 `scripts/lp_rh_coverage_audit_v1_readonly.py`
改成按资产计算覆盖率，提供两个函数：

```python
coverage_for_asset(conn, *, asset_address, expected_interval_secs, health_rows=()) -> dict
coverage_by_asset(conn, *, asset_addresses, expected_interval_secs, health_rows=()) -> dict
```

`coverage_for_asset` 对库里不存在的资产返回 `{"status": "NO_ASSET_DATA", "has_data": False, ...}`，
不是 0.0。

**但 `scripts/lp_rh_readiness_v1_readonly.py:246-253` 的 Stage A 判定还没接上**：

```python
row = conn.execute("SELECT MIN(sample_time), MAX(sample_time), COUNT(*) "
                   "FROM rh_market_states").fetchone()
```

**整表统计，没有资产维度。** 实测：两个各覆盖 48.4% 的资产合并后显示 96.8%
（约 2 倍高估），而这个数经 `stage_a_status` 的 `passed` 直达
`graduation_verdict:156`。当前库里只有一个资产所以还没触发，
但多资产股票代币宇宙正是 PRD 的目标。

## 你要做的

改 `scripts/lp_rh_readiness_v1_readonly.py`：

1. `_build_state` 增加 `asset_address` 参数，Stage A 的统计**只针对该资产**。
2. `asset_address` 的来源：新增 CLI 参数 `--asset-address`。
   现有 CLI 参数见 `:280-282`（`--db` / `--out` / `--interval-secs`），照那个风格加。
3. **不要给它默认值兜底成「全表」**——漏传就应该报错退出，
   理由：一个可选的资产过滤器一旦漏传就退回全表求和，
   等于把这个缺陷又放回来。若需要「看所有资产」，用 `coverage_by_asset`
   逐资产输出，**绝不把多资产行数相加**。
4. 复用 `coverage_for_asset`，**不要在 readiness 里重写覆盖率算法**
   （同一个量的多个实现是这个项目反复出问题的根源）。
5. 该资产在库里没有数据时（`NO_ASSET_DATA`）：Stage A 必须**判为未通过**
   并在 dashboard 里写明原因，**不得**当成覆盖率 0 或静默跳过。

## 不许动

`scripts/lp_rh_coverage_audit_v1_readonly.py`（已验收入库）、
`scripts/lp_rh_shadow_runner_v1_readonly.py` 与
`scripts/lp_rh_exit_depth_v1_readonly.py`（两条线正在改）、任何 `.db`。
`tests/test_lp_rh_readiness_v1_readonly.py` **只允许新增测试**。

## 验收标准

1. 用真实库 `reports/lp_rh/scanner.db` 与真实资产
   `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca` 跑，
   Stage A 的 `coverage_ratio` 应约为 `0.9678`（与 RH-02at 实测一致），
   把实际值贴进报告。
2. 传一个库里不存在的资产 → Stage A `passed` 为 False，且原因可见。
3. 漏传 `--asset-address` → 明确报错退出，不是静默全表。
4. 构造两个资产各占一半样本的内存库，断言 Stage A 只反映被指定的那一个，
   **且其 coverage_ratio 不等于两者之和**。
5. `graduation_verdict` 的传导不变：Stage A 未通过时整体不得 PASS（防回归）。
6. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_readiness_v1_readonly.py -q -p no:cacheprovider`
   全绿，原有测试全部仍在。原有测试若因新增必填参数而失败，
   **允许在调用处补参数**，但不许删测试、不许恢复全表默认，
   并在报告里逐条说明改了哪几行。

## 交付格式（你没有仓库写权限，但这不妨碍完成任务）

**你不需要落盘。把改动打印在最后一条消息里就是交付本身**，调度者会应用。
目标文件较大，用**替换块**，标记独占一行、一字不差：

```
===REPLACE:scripts/lp_rh_readiness_v1_readonly.py===
<<<OLD
（原文，必须与文件内容逐字符一致，且在文件中恰好出现一次——
  多带几行上下文来保证唯一性）
>>>NEW
（替换后的新文）
===END-REPLACE===
```

可以有多个块。新增测试用「原文 = 某个已有函数的最后一行，新文 = 那一行 + 新测试」的追加式块。

**硬要求**：OLD 必须在目标文件中**恰好出现一次**（应用器会校验，不唯一直接拒绝）；
缩进和空行逐字符一致（这是 Python）；不要用 markdown 代码围栏包裹。
动笔前用 `grep -c` 确认你选的 OLD 在文件里唯一。
