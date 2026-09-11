GOAL:
给 `scripts/lp_rh_reconciliation_v1.py` 加时间窗参数，让对账能只覆盖一个指定区间，而不是永远把全部历史算进去。

## 为什么需要

对生产库跑 dry-run 的实测结果：

```
C1 46 rows, 0 diffs | C2 23 rows, 0 diffs | C3 22757 rows, 1 diff
fee_journal_total 0  vs  marks_fee_total 2.64599302055050560136181804391
verdict UNEXPLAINED_DIFF
```

这 2.646 USD 的差额有**已知的历史原因**：shadow daemon 从 2026-09-10T20:01:46
到 2026-09-11T10:47 跑了 14.5 小时的陈旧代码（缺 commit `cf46140` 的 fee 记账），
仓位标记累计了手续费、账本却从没收到对应分录。进程已于 2026-09-11T10:52:54
重启到当前代码。

**这段历史不会自己消失。** 没有时间窗的话，C3 会永远报这同一笔差额，
Stage B 的「未解释账本差异=0」就永远过不去——而真正该被判定的是**重启之后**的账。

## 要做的事

只改 `scripts/lp_rh_reconciliation_v1.py` 与 `tests/test_lp_rh_reconciliation_v1_readonly.py`。

1. 新增命令行参数 `--since <RFC3339>`（可选）。给了就只统计该时刻**之后**的数据：
   - C1：`rh_journal.booked_at > since`
   - C2：`rh_shadow_positions.opened_at > since`
   - C3：`rh_position_marks.mark_time > since` 与对应的 journal 分录
2. `evidence_json` 里每项检查都要记下**实际生效的窗口**（`since` 为 None 时写 `null`），
   以及窗口内的 `rows_examined`。
3. **窗口收窄导致某项检查没样本时，verdict 必须是 `INSUFFICIENT_EVIDENCE`，不能是 `PASS`。**
   这是本包最容易做错的地方：加了时间窗之后，「窗口里什么都没有」会长得很像「一切正常」。
   现有的 fail-close 逻辑必须继续管用——不要为了让窗口模式好看而绕开它。
4. `--since` 格式非法（不是 RFC3339、不带时区）→ **直接报错退出（非 0），不要静默忽略**。
   静默忽略会让调用者以为窗口生效了，实际在算全量。

## 不许动

- 不要改三项检查本身的算法（C1/C2/C3 的比对逻辑保持不变，只加窗口过滤）。
- 不要改 `scripts/lp_rh_readiness_v1_readonly.py`、`lp_rh_store_v1_readonly.py`。
- **不要把对账接进 Stage B 判定**，那是另一个包。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动这两个文件会把 Stage A 的 72 小时判定窗口清零，代价极高。
- 不要写 `reports/lp_rh/` 下的任何数据库；测试用 `tmp_path`，用仓库自己的 `migrate()` 建 schema。
- **不要执行任何 git 命令。不要 kill 或重启任何进程**（PID 2271374 采集器、2575799 shadow daemon 在跑生产）。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（追加到现有测试文件，≥5 条新增）

写完把被测代码临时改坏，确认测试真的变红，再改回来。本项目已出现九次
「测试构造的输入进不去被测代码」，典型原因是 fixture 键名和被测代码读的键名对不上。

1. 不给 `--since` → 行为与现在完全一致（回归保护）
2. `--since` 落在所有数据之后 → 三项都没样本 → `INSUFFICIENT_EVIDENCE`（**不是 PASS**）
3. `--since` 把一笔有差额的历史排除在外、窗口内配平 → `PASS`，且 `rows_examined` 反映的是窗口内的行数
4. `--since` 把有差额的数据包含在内 → `UNEXPLAINED_DIFF`
5. `--since` 格式非法（如 `2026-09-11` 无时区、`not-a-date`）→ 非 0 退出码，stderr 有明确报错
6. `evidence_json` 里三项检查都带 `since` 字段，未指定时为 `null`

## ENVIRONMENT（照做，别自己找解释器）
- 直接用 `python3`（3.12.3 + pytest 7.4.4 + pycryptodome，就是本仓库钉死的版本）。
- **不要找 venv**，`/root/lp-bot/.venv` 你没权限。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`（12 万文件）。不要整读 >300 行的文件。
- 先改代码、先跑目标测试文件，**全量测试只在最后跑一次**。

## VALIDATION（命令与输出尾部原样贴进报告）
1. `python3 -m pytest tests/test_lp_rh_reconciliation_v1_readonly.py -q`（全绿，新增 ≥5 条）
2. `python3 scripts/lp_rh_reconciliation_v1.py --db reports/lp_rh/scanner.db`（dry-run，无 --since，应与上面那段实测输出一致）
3. `python3 scripts/lp_rh_reconciliation_v1.py --db reports/lp_rh/scanner.db --since 2026-09-11T10:52:54Z`（dry-run，贴完整输出）
4. `python3 scripts/lp_rh_reconciliation_v1.py --db reports/lp_rh/scanner.db --since 2026-09-11`（应报错退出）
5. `python3 -m pytest tests/ -q`（**最后才跑**；基线 4846 passed / 14 skipped / 0 failed）

最后按以下字段报告：TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
