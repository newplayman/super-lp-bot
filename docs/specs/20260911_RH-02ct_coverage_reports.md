GOAL:
补齐 PRD §19 RH-02 点名但仓库里**不存在**的两份交付物:`DATA_COVERAGE_REPORT.md` 与 `RPC_BUDGET_REPORT.json`。
新建一个生成脚本 `scripts/lp_rh_coverage_report_v1_readonly.py`,让这两份报告可重复生成,而不是手写一次就过期。

## 背景(已核实,直接用)

PRD `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md` §19 的 RH-02 包写着:
> 交付:collector／market_state、schema migration、`DATA_COVERAGE_REPORT.md`、`RPC_BUDGET_REPORT.json`。
> 验收:支持2026-09-07休市样本;记录API缓存与source age;日历／价格缺失准确分类;不中断旧进程,数据目录有上限。

只读审计确认这两个文件名在仓库里搜不到(`find` 无命中)。
PRD §21.1 还有一条硬要求:**「数据覆盖率分母必须是计划应观测的窗口,不能删掉坏窗口后报告100%」**。

现有可复用的东西(**先读它们,不要重写**):
- `scripts/lp_rh_readiness_v1_readonly.py` 里已有覆盖率计算(搜 `coverage_ratio`、`hours_covered`、`audit_coverage`),Stage A 判定就用它。
- `scripts/lp_rh_provider_health_v1_readonly.py` 与 `reports/lp_rh/provider_health.db` 有 RPC 提供方健康数据。
- 生产库 `reports/lp_rh/scanner.db`(只读)。

## 要做的事

新建 `scripts/lp_rh_coverage_report_v1_readonly.py`,参数至少有
`--db`(默认 `reports/lp_rh/scanner.db`)、`--provider-db`(默认 `reports/lp_rh/provider_health.db`)、
`--out-dir`(默认 `reports/lp_rh`)。

### 1. DATA_COVERAGE_REPORT.md

必须包含,每一项都标明**分母是什么**:
- 观测窗口起止、计划应观测的样本数(按采集间隔算)、实际取得数、**有效覆盖率**
- **分母是计划窗口,不是实际落库行数。** 如果某段时间完全没采到,它必须留在分母里拉低覆盖率。
  在报告里显式写出这一行口径说明。
- 按关键字段分列非空率(至少 `fee_growth_global_0/1`、`sqrt_price_x96`、`liquidity`、`source_event_time`)
- 缺失分类计数:日历休市 / 价格缺失 / RPC 失败 / 其他,**分类不出来的单列 `UNCLASSIFIED`,不要塞进任何一类**
- 2026-09-07(美国劳动节休市日)那一天单独一节,证明休市样本被正确识别而不是当成缺数

### 2. RPC_BUDGET_REPORT.json

- 每个 provider 的调用次数、错误数、成功率、观测到的时间范围
- 主备切换次数(如果 provider_health.db 里有)
- 明确的 `budget_status` 字段:免费额度是否可维持。**算不出来就写 `UNKNOWN` 并附 `reason`,不要写 `OK`。**

### 3. fail-close(本包的核心)

**任何一项算不出来,必须写 `UNKNOWN`/`NOT_MEASURED` 加原因,绝不能省略、绝不能填 0 或 100%。**
「删掉坏窗口后报告 100%」正是 PRD §21.1 明令禁止的;
「空表当零违反」是本仓库 `8e54926` 修过的缺陷。两个坑都不要再踩。

## 不许动

- **只新建上面那一个脚本 + 它的测试文件。不要修改任何既有 .py 文件。**
- 不要改 `scripts/lp_rh_readiness_v1_readonly.py`(只 import 复用,不修改)。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动它们会把 Stage A 的 72 小时判定窗口清零,代价极高。
- **绝对不要写 `reports/lp_rh/` 下的任何数据库**,只读打开(`file:...?mode=ro`)。
  脚本可以往 `--out-dir` 写那两份报告,但测试里一律用 `tmp_path`。
- **不要执行任何 git 命令。不要 kill 或重启任何进程**(PID 2271374 采集器、2575799 shadow daemon 在跑生产)。
- 不要碰 `scripts/lp_rh_netcover_inputs_v1_readonly.py`(另一个任务正在改它)。
- 单次 Write/Edit ≤150 行或 6000 字符,更大的分次写。

## 测试(新建 `tests/test_lp_rh_coverage_report_v1_readonly.py`,≥7 条)

写完把被测代码临时改坏,确认测试真的变红,再改回来。本项目已九次出现
「测试构造的输入进不去被测代码」,典型原因是 fixture 键名与被测代码读的键名对不上。

1. 窗口内有缺口 → 覆盖率 **<100%**,且分母是计划窗口而非实际行数
2. 把缺口那段整段删掉 → 覆盖率**仍然 <100%**(证明没有「删坏窗口刷满分」)
3. 空库 → 每项都是 `UNKNOWN`/`NOT_MEASURED` 加原因,**不是 0 也不是 100%**
4. 字段非空率:某字段全 NULL → 该字段报 0%,不影响其他字段
5. 缺失分类:造一条分类不出来的 → 计入 `UNCLASSIFIED`
6. provider_health.db 不存在 → `budget_status` 为 `UNKNOWN` 加 reason,**不是 `OK`**
7. 两份报告都能生成且是合法 Markdown / JSON

## ENVIRONMENT(照做,别自己找解释器)
- 直接用 `python3`(3.12.3 + pytest 7.4.4 + pycryptodome,本仓库钉死的版本)。
- **不要找 venv**(`/root/lp-bot/.venv` 无权限)。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`(12 万文件)。不要整读 >300 行的文件。
- 先读现有覆盖率实现再动手,**全量测试只在最后跑一次**。

## VALIDATION(命令与输出尾部原样贴进报告)
1. `python3 -m pytest tests/test_lp_rh_coverage_report_v1_readonly.py -q`(全绿,≥7 条)
2. `python3 scripts/lp_rh_coverage_report_v1_readonly.py --out-dir /tmp/covrep`(对生产库只读跑一次,贴出两份报告的完整内容)
3. `python3 -m pytest tests/ -q`(**最后才跑**;基线 4860 passed / 14 skipped / 0 failed,可能因另一任务而更高)
4. `git status --short`(只读地看)

最后按以下字段报告:TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
