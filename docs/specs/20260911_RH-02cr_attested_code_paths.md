GOAL:
把合成测试证据的 `code_version` 从「整仓 HEAD」收窄到「真正可能影响测试结果的路径」，
打破一个**无出口的死循环**。

## 为什么

`reports/lp_rh/synthetic_tests_evidence.json` 记录 `code_version = git rev-parse --short=12 HEAD`，
`scripts/lp_rh_readiness_v1_readonly.py` 拿它和当前 HEAD 比，不等就报
`SYNTHETIC_EVIDENCE_STALE_CODE_VERSION`，Stage A 出现 `STAGE_A_SYNTHETIC_TESTS_FAILED`。

**而这个证据文件本身是被 git 跟踪的。** 于是：
生成证据 → 提交证据 → HEAD 变了 → 刚生成的证据当场过期 → 再生成 → 再提交 → ……
**没有出口。** 2026-09-11 一天之内触发了四次。

## 要做的事

改 `scripts/lp_rh_synthetic_evidence_v1.py`（生成侧）与
`scripts/lp_rh_readiness_v1_readonly.py`（比对侧）。

### 1. 一个共享常量，两侧都用它

```python
ATTESTED_CODE_PATHS = ("scripts", "tests", "configs", "pytest.ini")
```

**必须定义在一个模块里，另一个模块 import 它。** 两处各写一份字面量列表是不行的——
两边漂移之后，生成的证据和比对的口径就对不上，而且**不会报错**，
正是本仓库反复出现的静默假绿形状。
仓库里已有同类先例可抄：`lp_rh_readiness_v1_readonly.py` 的 `COLLECTION_CODE_PATHS`
与 `resolve_judgment_window()` 就是 `git log -1 --format=... -- <paths>` 的写法。

### 2. 版本解析改成按路径取

两侧都改成等价于：
```
git log -1 --format=%H -- scripts tests configs pytest.ini
```
再截取前 12 位。拿不到（空输出、非 0 退出、格式不对）→ **沿用现有的失败处理，
不要回退到 HEAD，也不要返回空字符串当成「通过」**。

### 3. `working_tree_clean` 不要动

它现在用 `git status --porcelain` 并**已经忽略未跟踪文件**（`?? ` 开头的行），
逻辑是对的，保持原样。

### 4. 口径变更要写进证据文件本身

`code_version_source` 字段现在写的是 `"git rev-parse --short=12 HEAD"`，
改成反映新口径的字符串（例如 `"git log -1 --format=%H -- scripts tests configs pytest.ini"`）。
**这一条很重要**：将来有人看到一份旧证据，能从这个字段分辨它是按哪种口径生成的。

## 不许动

- 不要改 `working_tree_clean` 的计算方式。
- 不要改 Stage A/B 的任何判定阈值、不要改 `stage_a_status` / `stage_b_status` 的其他逻辑。
- 不要改 `COLLECTION_CODE_PATHS`（那是 Stage A 的 72 小时判定窗口，是另一回事，**绝不能碰**）。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动它们会把 Stage A 的 72 小时计时清零，代价极高。
- 不要重新生成 `reports/lp_rh/synthetic_tests_evidence.json`（主脑会在最后统一做）。
- 不要写 `reports/lp_rh/` 下的任何数据库或文件。
- **不要执行任何 git 命令（读取仓库状态请用被测代码自己的函数或 subprocess 只读查询，
  但绝不要 commit/add/checkout/stash）。不要 kill 或重启任何进程**
  （PID 2271374 采集器、2575799 shadow daemon 在跑生产）。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（≥6 条，加到对应的现有测试文件）

写完把被测代码临时改坏，确认测试真的变红，再改回来。

1. **两侧口径一致**：同一个仓库状态下，生成侧算出的 version 与比对侧算出的 version **必须相等**。
   这是本包最重要的一条测试——它是防两边漂移的唯一保护。
2. 只改 `docs/` 或 `reports/` 或根目录 `.md` 的提交 → version **不变** → 证据**不过期**
3. 改 `scripts/` 下的文件的提交 → version **变** → 证据**过期**
4. 改 `tests/` 下的文件 → version 变
5. 改 `configs/` 下的文件 → version 变
6. 改 `pytest.ini` → version 变
7. `git log` 对这些路径返回空输出 → **沿用失败处理，不得当成通过**

测试里造 git 仓库请用 `tmp_path` + `git init`，不要在真仓库上试。

## ENVIRONMENT（照做，别自己找解释器）
- 直接用 `python3`（3.12.3 + pytest 7.4.4 + pycryptodome，就是本仓库钉死的版本）。
- **不要找 venv**，`/root/lp-bot/.venv` 你没权限。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`（12 万文件）。不要整读 >300 行的文件。

## VALIDATION
1. `python3 -m pytest tests/test_lp_rh_synthetic_evidence_v1_readonly.py tests/test_lp_rh_readiness_v1_readonly.py -q`（全绿）
2. `grep -n "ATTESTED_CODE_PATHS" scripts/*.py`（应能看到一处定义 + 一处 import，**不是两处定义**）
3. `grep -n "rev-parse --short=12 HEAD" scripts/lp_rh_synthetic_evidence_v1.py`（应无输出）
4. **不要跑全量测试**（`pytest tests/ -q`）。另一个 worker 正在并行跑它，会撞车。主脑会统一跑。

最后按以下字段报告：TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
