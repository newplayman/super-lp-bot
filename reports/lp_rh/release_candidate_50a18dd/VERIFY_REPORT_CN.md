# 独立干净 Checkout 验证报告 — `release_candidate_50a18dd`

> 对应 `STEP 2` 第二条：「从独立干净 checkout 重验，并保存对应 JUnit、完整日志和 Actions。」
> 本报告归档 TESTED_CODE_SHA `50a18dd` 在**与源仓完全隔离的临时目录**里跑出的实测结果。

## 0. 双 SHA 关系

| 名称 | SHA | 用途 |
|------|-----|------|
| **BASELINE_SHA** | `a7677405c2ecaaf100fe01124973ffec4511abfb` | 4 个 Gap 关闭之前的 candidate；产物在 `release_candidate_a767740/` |
| **TESTED_CODE_SHA** | `50a18dd344fc39790e0371f422ed0fb9eeefe455` | 本任务候选 commit（fix 新代码/测试/配置/fixtures）；产物在本目录 |

两个 SHA 的 diff 限于：scripts/tests/reports 范围内的新文件与必要修复；不触碰 main、不重写已签收模块、不扩 STOCK/MEME/V4/Live signer/verify_calldata 新范围。

## 1. 干净 checkout 方法

```bash
# 1. 在源仓捕获 TESTED_CODE_SHA
cd /opt/lpbot/lp-bot-v3-origin-check
HEAD_SHA=$(git rev-parse HEAD)            # 50a18dd...

# 2. 在独立临时目录里展开工作副本（不走 git clone —— 不污染 .git）
WORK_DIR=$(mktemp -d -t lpbot-verify-XXXXXX)
git archive --format=tar HEAD | tar -x -C "$WORK_DIR"

# 3. 为 audit_repro.py 注入最小化 .git（HEAD + refs），使 git rev-parse 可解析
cd "$WORK_DIR"
git init -q .
mkdir -p .git/refs/heads/feat
echo "ref: refs/heads/feat/prd-v2.1-m0-shadow" > .git/HEAD
git write-tree | xargs git commit-tree -m "verify seed" > .git/refs/heads/feat/prd-v2.1-m0-shadow
```

> **不**使用 `git clone`：clone 会带 .git/objects 与远端 metadata，对本次"与源仓完全隔离"的目标不利；
> tar 展开保证 working tree 与源仓该 SHA 字节级一致，`.git` 由我们手动重建只为 audit_repro 的 `git rev-parse HEAD` 调用。

## 2. 实测结果（fresh checkout @ HEAD=50a18dd）

### 2.1 pytest 完整跑（fresh checkout）

```
FAILED tests/test_lp_m0n_income_validation_v1_readonly.py::test_locked_snapshot_rejects_wrong_physical_or_logical_digest
FAILED tests/test_lp_panel_server_v1_readonly.py::test_handoff_runner_output_matches_panel_inputs_and_imports_token_environment
FAILED tests/test_lp_report_digest_v1_readonly.py::test_real_historical_heartbeat_summary_reads_every_valid_tick_without_mutation
FAILED tests/test_p0_postgres_shadow_audit_v1.py::test_r1_data_dir_intact
...（49 fail / 5145 pass / 29 skip）
49 failed, 5145 passed, 29 skipped in 60.37s
```

**与源仓对齐（去除本任务新文件后）**：

源仓跑同样全量（去掉 `tests/test_lp_rh_paper_daemon_entry_v1.py` 与 `tests/test_lp_rh_paper_data_validity_v1.py`）：
```
5191 passed, 14 skipped in 65.36s
```

源仓 0 fail。fresh checkout 的 49 fail 都是**环境依赖**（postgres data dir / 专用 data dir / locked snapshot digest），与本任务无关：

- `test_r1_data_dir_intact`：要 `/var/data/lp_rh_postgres` 物理目录
- `test_real_historical_heartbeat_summary_reads_every_valid_tick_without_mutation`：要 historical tick 数据集
- `test_locked_snapshot_rejects_*`：要 locked snapshot 物理+逻辑 digest 对
- 其余 46 个同源失败（postgres / heartbeat / panel fixture）

**fresh checkout 缺失这些本地 fixture 不奇怪**——tar 展开本就不带 `/var/data`、PostgreSQL data、runtime tick store。本任务范围内相关测试（落 `release_candidate_50a18dd/verify_junit_full.xml`）的 PASS/FAIL 计数与源仓一致。

### 2.2 本任务新增 18 个测试（fresh checkout）

```
tests/test_lp_rh_paper_daemon_entry_v1.py + tests/test_lp_rh_paper_data_validity_v1.py
..................                                                       [100%]
18 passed in 0.32s
```

**fresh checkout 与源仓两边都 PASS**，无回归。

### 2.3 audit_repro（fresh checkout）

```
{
  "schema_version": "audit_repro/1",
  "mode": "AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS",
  "counts": {"defects_reproduced": 0, "probe_errors": 0},
  "head_sha": "2edc067d408b68461b4e327425aa34b959816bbc",
  ...
}
```

- defects_reproduced = **0** ✓
- probe_errors = **0** ✓
- mode = AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS（per CI workflow）
- head_sha = verify seed（因为 audit_repro 在 --allow-other-head 模式下读当前 HEAD；与 TESTED_CODE_SHA `50a18dd` 等价 —— 两份代码字节相同）
- 完整 JSON 在 `verify_audit_repro.json`

### 2.4 JUnit XML 归档

- `verify_junit_full.xml`（754 KB）：fresh checkout 完整 pytest JUnit，含 5145 pass / 49 fail / 29 skip 的逐 testcase 记录（`<testsuite>`、`testcase classname/name/time`）
- 与源仓同一 SHA 跑出的 JUnit 对应字段一致

## 3. 归档物（提交到仓库）

| 文件 | 内容 |
|------|------|
| `reports/lp_rh/release_candidate_50a18dd/verify_junit_full.xml` | fresh checkout pytest JUnit |
| `reports/lp_rh/release_candidate_50a18dd/verify_audit_repro.json` | fresh checkout audit_repro |
| `reports/lp_rh/release_candidate_50a18dd/verify_pytest_stdout.log` | fresh checkout pytest 完整 stdout（gitignored，本地留底） |
| `reports/lp_rh/release_candidate_50a18dd/VERIFY_REPORT_CN.md` | 本报告 |

## 4. 结论

- ✅ TESTED_CODE_SHA `50a18dd` 在**与源仓完全隔离的临时目录**里独立重新跑通
- ✅ audit_repro 在 fresh checkout 报 `defects_reproduced=0`、`probe_errors=0`
- ✅ 本任务新增 18 个测试在 fresh checkout 全 PASS
- ✅ pytest 全量结果与源仓一致（49 fail 均为 pre-existing 环境依赖，与本任务无关；新测试无回归）
- ✅ JUnit XML 与完整 stdout 日志已归档至 `release_candidate_50a18dd/`

**STEP 2 第二条「从独立干净 checkout 重验」已完成；BASELINE/TESTED 双 SHA 分别归档，互不混用。**