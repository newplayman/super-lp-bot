GOAL:
新建一个对账脚本 `scripts/lp_rh_reconciliation_v1.py`，把对账结果写进 `rh_reconciliation_runs` 表。这张表 PRD 定义了、schema 建好了，但**全仓无任何写入者，至今 0 行**。Stage B 的门槛「未解释的账本差异=0」就卡在这里。

## 已确认的事实（直接用，不用重新查）

- 表 schema（`scripts/lp_rh_store_v1_readonly.py:132` 已定义，不要改它）：
  `run_id TEXT PK, started_at TEXT NOT NULL, finished_at TEXT, evidence_json TEXT, delta_json TEXT, verdict TEXT NOT NULL, derived_block_hash TEXT, derived_block_number INTEGER`
- 现有可复用逻辑：`scripts/lp_rh_readiness_v1_readonly.py` 的 `audit_unexplained_ledger_diffs(conn)`（约 1016 行）已实现「按 event_id 分组的借贷配平检查」，返回 `{"count":..., "checks_performed":[...], ...}`。**import 它，不要重写。**
- 生产库 `reports/lp_rh/scanner.db` 现状（只读查得）：
  `rh_journal` 46 行（账户对只有 `LP_POSITION_TOKEN0/WALLET_TOKEN0` 与 `LP_POSITION_TOKEN1/WALLET_TOKEN1`，各 23 条），
  `rh_shadow_positions` 23 行（`closed_at` 全为 NULL —— Shadow 没有平仓路径），
  `rh_position_marks` 21957 行，`rh_reconciliation_runs` 0 行。

## 要做的事

新建 `scripts/lp_rh_reconciliation_v1.py`，命令行参数至少有 `--db`（默认 `reports/lp_rh/scanner.db`）与 `--apply`（**默认 dry-run，只有 --apply 才写 rh_reconciliation_runs**）。

### 三项检查

**C1 借贷配平**：调用 `audit_unexplained_ledger_diffs(conn)`，拿 `count` 与 `checks_performed`。

**C2 开仓两腿勾稽**：对每个 `rh_shadow_positions` 行，把 `rh_journal` 里 `ref_json` 的 `position_id` 指向它、且账户对为 `LP_POSITION_TOKEN0/WALLET_TOKEN0`（resp. TOKEN1）的分录金额，与该行的 `initial_token0_raw`（resp. `initial_token1_raw`）比对。差额应为 0。
注意：`amount_raw` 与 `initial_token*_raw` 都是 TEXT 存的高精度数，**一律用 `Decimal` 比较，不要用 float**。

**C3 手续费勾稽**：`rh_journal` 里 `LP_FEES_RECEIVABLE/LP_FEE_INCOME` 的分录总额，与各 position 最后一条 `rh_position_marks.accrued_fee` 之和比对。
**当前生产库里 FEE 分录是 0 条**——这正是 C3 必须能报出来的情况，见下面的 fail-close。

### fail-close（本包的核心，比检查本身更重要）

| 情况 | verdict |
|---|---|
| 任一检查所需的表为空或该检查无样本 | `INSUFFICIENT_EVIDENCE`，并在 `delta_json` 里写明是哪一项、为什么 |
| 三项都有样本且差额全为 0 | `PASS` |
| 任一项差额非 0 | `UNEXPLAINED_DIFF` |

**空表绝不能算 PASS。** 「六张空表，检查在对空气打勾」是本仓库 `8e54926` 修过的缺陷，不要再造一个。
`evidence_json` 要记下每项检查**实际看了多少行**（`rows_examined`），这样「0 差异」和「没样本」在证据里天然可分。

### 不许动

- 不要改 `scripts/lp_rh_store_v1_readonly.py`（表定义）。
- 不要改 `scripts/lp_rh_readiness_v1_readonly.py`（只 import，不修改）。
- **不要把这个对账接进 Stage B 判定**，那是下一个包。
- 不要写 `reports/lp_rh/` 下的任何数据库；测试一律用 `tmp_path`，并且**用仓库自己的 `migrate()` 建 schema**，不要手搓单张表。
- **不要执行任何 git 命令。**
- **不要 kill 或重启任何进程**（PID 2271374 采集器、2571485 shadow daemon 在跑生产）。
- 单次 Write/Edit ≤150 行或 6000 字符，更大的分次写。

## 测试（新建 `tests/test_lp_rh_reconciliation_v1_readonly.py`，≥8 条）

逐条确认断言真的走到目标分支——本项目已出现九次「测试构造的输入进不去被测代码」，典型原因是 fixture 的键名和被测代码读的键名对不上。**写完把被测代码临时改坏，确认测试变红，再改回来。**

1. 三项都配平 → `PASS`
2. `rh_journal` 空 → `INSUFFICIENT_EVIDENCE`（**不是 PASS**）
3. `rh_shadow_positions` 空 → `INSUFFICIENT_EVIDENCE`
4. 无 FEE 分录但有 accrued_fee → C3 报差额 → `UNEXPLAINED_DIFF`
5. 无 FEE 分录且 accrued_fee 也全为 0/NULL → C3 无样本 → `INSUFFICIENT_EVIDENCE`
6. C2 故意让 journal 金额比 position 少 1 → `UNEXPLAINED_DIFF`，且 `delta_json` 里能定位到是哪个 position
7. dry-run 默认不写库：跑完 `rh_reconciliation_runs` 仍为 0 行
8. `--apply` 写入一行，`run_id` 唯一，`started_at`/`finished_at` 都是 UTC RFC3339（`Z` 结尾）
9. `evidence_json` 里每项检查都有 `rows_examined`

## ENVIRONMENT（照做，别自己找解释器）
- 直接用 `python3`（3.12.3 + pytest 7.4.4 + pycryptodome，就是本仓库钉死的版本）。
- **不要找 venv**，`/root/lp-bot/.venv` 你没权限。**不要 pip install**。**不要改任何全局配置**。
- 先读代码、先写实现，**全量测试只在最后跑一次**。
- 不要读 `reports/polymarket_competitor`（12 万文件，会爆上下文）。不要整读 >300 行的文件。

## VALIDATION（命令与输出尾部原样贴进报告）
1. `python3 -m pytest tests/test_lp_rh_reconciliation_v1_readonly.py -q`（全绿，≥8 条）
2. `python3 -m pytest tests/ -q`（**最后才跑**；基线 4836 passed / 14 skipped / 0 failed）
3. `python3 scripts/lp_rh_reconciliation_v1.py --db reports/lp_rh/scanner.db`（对生产库跑 **dry-run**，把完整输出贴出来；预期会报 FEE 分录缺失）
4. `git status --short`（只读地看）

最后按以下字段报告：TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, ARTIFACTS, UNRESOLVED, RISKS, NEXT_STEP。
