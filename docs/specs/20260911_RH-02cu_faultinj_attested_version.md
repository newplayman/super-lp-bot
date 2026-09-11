GOAL:
修一条**当前正在红的**回归测试。这是个小包,只改两个文件里的一处逻辑。

## 现象(已复现)

```
python3 -m pytest tests/test_lp_rh_fault_injection_v1_readonly.py -q
FAILED test_fault_injection_scenario_5_synthetic_evidence_stale_code_version
    assert res["control_passed"] is True, "对照组未通过"
FAILED test_fault_injection_e2e_run_and_report
2 failed, 5 passed
```

## 真因(已查明,直接用)

commit `302afac` 把合成证据的 `code_version` 口径从「整仓 HEAD」收窄成
「只看 `scripts` / `tests` / `configs` / `pytest.ini` 的最后一次提交」。
常量是 `ATTESTED_CODE_PATHS`,定义在 `scripts/lp_rh_synthetic_evidence_v1.py:26`,
`scripts/lp_rh_readiness_v1_readonly.py` 已 import 它。

但 `scripts/lp_rh_fault_injection_v1_readonly.py` 的场景 5 没跟着改:

```
scripts/lp_rh_fault_injection_v1_readonly.py:73   def get_repo_head(...)  ← git rev-parse --short=12 HEAD
scripts/lp_rh_fault_injection_v1_readonly.py:544  head = get_repo_head()  ← 场景 5 用它造「对照组」
```

场景 5 的对照组把 `code_version` 设成整仓 HEAD,然后期望
`audit_synthetic_tests` 判它「新鲜」。但 `audit_synthetic_tests` 现在比的是
ATTESTED 口径,两者在提交了一个 `reports/` 下的文件之后就不相等了,
于是对照组被判成「陈旧」,测试红。

**这不是口径改错了,恰恰是收窄生效了。** 场景 5 的对照组需要跟上新口径。

`get_repo_head` 全仓**只有 544 行这一处调用**(已 grep 确认,无其他引用)。

## 要做的事

改 `scripts/lp_rh_fault_injection_v1_readonly.py` 与
`tests/test_lp_rh_fault_injection_v1_readonly.py`。

1. 让场景 5 的对照组用 **ATTESTED 口径**算出的版本,而不是整仓 HEAD。
   - 从 `scripts.lp_rh_synthetic_evidence_v1` import `ATTESTED_CODE_PATHS`
     (**不要在这个文件里再写一份路径字面量** —— 两处字面量漂移正是本仓库反复出现的静默假绿)。
   - 等价于 `git log -1 --format=%H -- scripts tests configs pytest.ini`,取前 12 位。
   - 如果 `lp_rh_synthetic_evidence_v1` 里已经有现成的解析函数(看 `resolve_code_version`
     附近),**优先直接复用那个函数**,而不是自己再写一遍 subprocess 调用。
2. `get_repo_head` 只有这一处用,可以改成新语义并改个准确的名字
   (例如 `get_attested_code_version`),也可以保留旧函数另加新函数 —— 你决定,
   但**不能留下一个名字叫 head、语义却不是 head 的函数**。
3. 注入组保持原样(用一个明显不存在的假 sha,期望被判陈旧)。
4. 场景 5 的 docstring 要更新,说明对照组现在用的是 ATTESTED 口径。

## 关键:新增一条防复发测试

这次的教训是「**对照组和被测逻辑用了两套口径,而且长期巧合相等,直到某次提交才分叉**」。
加一条测试钉住这个等式:

> **构造出「整仓 HEAD 与 ATTESTED 版本不相等」的状态**(例如在 `tmp_path` 里 `git init`,
> 先提交一个 `scripts/x.py`,再提交一个 `reports/y.md`),此时场景 5 的对照组**仍须通过**。

没有这条测试,同样的巧合还会再骗一次。

## 不许动

- 不要改 `scripts/lp_rh_synthetic_evidence_v1.py`、`scripts/lp_rh_readiness_v1_readonly.py`
  (只 import,不修改)。
- 不要改场景 1/2/3/4/6 的任何逻辑。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动它们会把 Stage A 的 72 小时判定窗口清零。
- 不要碰 `scripts/lp_rh_netcover_inputs_v1_readonly.py`、
  `scripts/lp_rh_coverage_report_v1_readonly.py`(别的任务在改/在建)。
- 不要写 `reports/lp_rh/` 下的任何文件或数据库;测试用 `tmp_path`。
- **不要执行任何 git 命令(测试里在 tmp_path 内 git init 是可以的,
  但绝不要在本仓库 commit/add/checkout/stash)。不要 kill 或重启任何进程**
  (PID 2271374 采集器、2575799 shadow daemon 在跑生产)。
- 单次 Write/Edit ≤150 行或 6000 字符。

## ENVIRONMENT(照做,别自己找解释器)
- 直接用 `python3`(3.12.3 + pytest 7.4.4 + pycryptodome,本仓库钉死的版本)。
- **不要找 venv**(`/root/lp-bot/.venv` 无权限)。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`(12 万文件)。不要整读 >300 行的文件。

## VALIDATION(命令与输出尾部原样贴进报告)
1. `python3 -m pytest tests/test_lp_rh_fault_injection_v1_readonly.py -q`(**7 passed,0 failed** + 你新增的那条)
2. `grep -n "ATTESTED_CODE_PATHS" scripts/lp_rh_fault_injection_v1_readonly.py`(应有 import,**不是重新定义**)
3. `grep -n "rev-parse --short=12 HEAD" scripts/lp_rh_fault_injection_v1_readonly.py`(应无输出,或仅存于已废弃且无人调用的函数)
4. **不要跑全量测试**(`pytest tests/ -q`)。另有 worker 在并行跑它,会撞车。主脑会统一跑。

最后按以下字段报告:TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
