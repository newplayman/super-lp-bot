# RH-02cf — RH-08 的三个交付物（毕业收尾证据）

## 背景

PRD L973 要求 RH-08 交付四份文件，目前只有一份存在：

```
READINESS_DASHBOARD.md    不存在   <- 本包
FULL_TEST_RAW.log         不存在   <- 本包
FAULT_INJECTION_REPORT.md 已有     (a2f2625，六场景全过)
GRADUATION_VERDICT.json   不存在   <- 本包
```

三份都要**可重复生成**，不是一次性手写——毕业判定会反复跑，
手写的快照第二天就是陈旧证据，本仓库今晚已因「把当前状态写死」坏过三次测试。

## 唯一任务

新建 `scripts/lp_rh_graduation_evidence_v1.py`，一次生成三份产物。

```
python3 scripts/lp_rh_graduation_evidence_v1.py \
    [--db reports/lp_rh/scanner.db] \
    [--asset-address 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca] \
    [--out-dir reports/lp_rh] \
    [--skip-tests]        # 跳过跑测试，只出 dashboard + verdict
```

### 1. `READINESS_DASHBOARD.md`

直接复用 `scripts/lp_rh_readiness_v1_readonly.py` 的渲染结果
（它已经能产出完整面板，`--out` 指定路径）。本脚本负责：
- 调它生成到 `--out-dir/READINESS_DASHBOARD.md`
- 在文件**开头**加一段生成元信息：生成时刻（UTC）、`git rev-parse --short=12 HEAD`、
  工作区是否干净、数据库路径与 as-of 时间

**不要重写面板渲染逻辑**，只加头部。

### 2. `FULL_TEST_RAW.log`

跑 `python3 -m pytest tests/ -q -p no:cacheprovider`，把
**stdout + stderr 原样**写入 `--out-dir/FULL_TEST_RAW.log`，
开头同样加元信息头（时刻、HEAD、工作区状态、命令行）。

- `--skip-tests` 时不跑、不写这个文件，并在 verdict 里标注 `full_test_log: "SKIPPED"`
- 测试失败**不要吞掉**：日志照写，退出码照传，verdict 里如实反映

### 3. `GRADUATION_VERDICT.json`

机器可读的裁决，结构：

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-10T16:00:00Z",
  "code_version": "a2f26259c9fd",
  "working_tree_clean": true,
  "db_path": "reports/lp_rh/scanner.db",
  "as_of": "<readiness 的 as_of>",
  "stage_a": {"passed": false, "blockers": [...], "hours_covered": 7.7,
              "hours_required": 72, "coverage_ratio": "0.9935"},
  "stage_b": {"passed": false, "blockers": [...], "days_covered": 2,
              "days_required": 14},
  "live_gate": {"live_allowed": false, "blockers": [...]},
  "full_test": {"total": 4769, "passed": 4755, "failed": 0, "exit_code": 0},
  "fault_injection": {"report_present": true, "scenarios_passed": 6,
                      "scenarios_total": 6},
  "verdict": "NOT_GRADUATED",
  "verdict_reasons": ["STAGE_A: HOURS_COVERED_INSUFFICIENT", "..."],
  "tiny_live_authorized": false
}
```

**`verdict` 的取值只有三种**：`NOT_GRADUATED` / `STAGE_A_PASSED` / `SHADOW_COMPLETE`。
**`tiny_live_authorized` 恒为 `false`**，除非 Stage A、Stage B、live_gate 三者
**全部** `passed`/`live_allowed` 为真 —— 且即便如此也要在 `verdict_reasons` 里
写明「代码判定通过不等于所有者批准」（PRD 要求真钱须由所有者明确批准，
本仓库至今**从未有任何文档批准过真钱**，见
`reports/AUDIT_stale_conclusions_20260909.md`）。

`fault_injection` 一节：读 `--out-dir/FAULT_INJECTION_REPORT.md` 是否存在；
存在就解析其中的 PASS/FAIL 计数。**解析不出就写 `null`，不要猜 6/6。**

### 缺失数据一律 fail-close

任何一节取不到就写 `null` 并在 `verdict_reasons` 里记一条
`EVIDENCE_UNAVAILABLE:<节名>`，**绝不用 0 或乐观默认值顶替**——
本仓库已确认 27 例「静默假绿」都是这么来的。

退出码：`verdict == "NOT_GRADUATED"` → 0（这是正常状态，不是错误）；
生成过程本身失败 → 非 0。

## 不许动

- 不要改 `scripts/lp_rh_readiness_v1_readonly.py`（另一条线可能在改，且它已验收）。
- 不要改 `scripts/lp_rh_fault_injection_v1_readonly.py`。
- 不要改 `scripts/lp_rh_shadow_runner_v1_readonly.py` /
  `scripts/lp_rh_shadow_daemon_v1_readonly.py`（RH-02ce 正在改它们）。
- 对 `reports/lp_rh/scanner.db` **只读**（`mode=ro`）。
- **不要重启或 kill 任何进程**（采集器 1168725 / daemon 1569118 在跑生产）。
- **不要执行任何 git 命令**（脚本内部调 `git rev-parse` / `git status --porcelain`
  是本包要求的；你自己不要 add / commit）。
- 单次 Write ≤150 行或 6000 字符，脚本超了分次写。

## 测试（`tests/test_lp_rh_graduation_evidence_v1_readonly.py`）

用 `tmp_path` 造库与产出目录，**不要写仓库的 `reports/`**，
**不要在测试里跑全量 pytest**（用 `--skip-tests` 或 monkeypatch 掉）。

1. `--skip-tests` 时：dashboard 与 verdict 生成，`FULL_TEST_RAW.log` **不生成**，
   verdict 里 `full_test` 为 `"SKIPPED"` 或 `null`。
2. Stage A 未通过时 `verdict == "NOT_GRADUATED"`，且
   `verdict_reasons` 含该 blocker 名。
3. **`tiny_live_authorized` 在三者全通过时仍需 `verdict_reasons` 里带所有者批准提醒**
   （构造一个全通过的假 state 验证）。
4. `FAULT_INJECTION_REPORT.md` 不存在 → `fault_injection.report_present is False`，
   `scenarios_passed is None`（**不是 0**）。
5. 缺失的一节写 `null` 且 `verdict_reasons` 里有 `EVIDENCE_UNAVAILABLE:` 前缀的条目。
6. 生成的 JSON 可被 `json.load` 解析，含全部顶层键。
7. dashboard 文件开头含 HEAD 与生成时刻。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_graduation_evidence_v1_readonly.py -q` 全绿，条数 ≥ 7。
2. 真跑一次（**输出到 /tmp，不要写仓库**）：
   ```
   python3 scripts/lp_rh_graduation_evidence_v1.py --out-dir /tmp/grad --skip-tests
   ```
   三个路径下 `READINESS_DASHBOARD.md` 与 `GRADUATION_VERDICT.json` 生成，
   verdict 为 `NOT_GRADUATED`，`verdict_reasons` 里能看到
   `HOURS_COVERED_INSUFFICIENT`。把 verdict 的 JSON 贴进总结。
3. `grep -n "scanner.db" scripts/lp_rh_graduation_evidence_v1.py` 每处都带 `mode=ro`
   （或经由 readiness 脚本的只读接口）。
4. `git status --short` 里只有这两个新文件是 `??`。
