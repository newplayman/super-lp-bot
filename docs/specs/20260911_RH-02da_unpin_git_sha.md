GOAL:
把 `tests/test_rh02ba_silent_failure_hunt2.py` 对 **git commit SHA 的硬依赖**去掉,
改成从仓库内的快照文件加载。**当前这 8 条测试是红的,本包要把它们修绿。**

## 现象(已实测)

```
python3 -m pytest tests/test_rh02ba_silent_failure_hunt2.py -q
8 failed, 5 passed
subprocess.CalledProcessError: Command '['git','show','4aa4497^:scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py']'
  returned non-zero exit status 128
```

## 真因

该测试是**差分测试**:加载修复前的旧版模块,证明旧版会漏、新版能抓。
思路是对的,但它靠 `git show <SHA>^:<path>` 取旧版:

```
tests/test_rh02ba_silent_failure_hunt2.py:40   PRE_FIX_REV = "4aa4497^"
tests/test_rh02ba_silent_failure_hunt2.py:43-48  _load_git_head_module() 用 subprocess 跑 git show
```

今天为清除历史中的私钥重写了 308 个 commit,**所有 SHA 都变了**,`4aa4497` 不复存在。
(对照:旧 `4aa4497` = 新 `1419621`,message 与时间戳一致。)

**把 commit SHA 钉进测试,任何一次 rebase / filter-branch / cherry-pick 都会炸。**
换个 SHA 只是把雷挪个位置,本包要的是拆雷。

## 要做的事

1. 从 commit **`1419621^`** 取出下面四个文件的**修复前版本**,存进
   `tests/fixtures/rh02ba_pre_fix/`(目录不存在就建),文件名保持原样:
   - `scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py`
   - `scripts/lp_survival_horizon_ev_model_v1_readonly.py`
   - `scripts/lp_survival_out_of_range_risk_v1_readonly.py`
   - `scripts/strategy_pivot_d4_realtime_paper_shadow_validation.py`

   取法:`git show 1419621^:<path> > tests/fixtures/rh02ba_pre_fix/<basename>`
   **这是本包唯一允许的 git 读操作**,且是只读。

2. 把 `_load_git_head_module()` 改成从那个 fixture 目录读文件,
   **删掉 `PRE_FIX_REV` 常量与 subprocess 调用**。函数名也改成能反映新来源的
   (例如 `_load_pre_fix_module`),不要留一个名字叫 `git_head` 却不读 git 的函数。

3. 在 fixture 目录放一个 `README.md`,写明:
   - 这些是 RH-02ba 修复**之前**的模块快照,用途是差分测试
   - 来源提交:`1419621`(「fix(rh-02ba): five more silent failures...」)的父提交
   - **它们是冻结的历史快照,不要跟着 scripts/ 下的现版本更新**
   - 并注明:原实现曾用 `git show <SHA>` 取,因 2026-09-11 的历史重写失效,故改为快照

4. **fail-close**:fixture 文件缺失时,测试要给出明确报错
   (例如 `FileNotFoundError` 带路径与说明),**不要静默跳过、不要退回加载现版本**。
   退回现版本会让差分测试变成「自己和自己比」,永远通过——那正是本仓库反复出现的假绿。

## 不许动

- **不要修改 `scripts/` 下的任何文件**,尤其不要改那四个模块的现版本。
- 不要改这 13 条测试的断言逻辑与判定阈值——只改「旧版模块从哪来」。
- **不要执行任何 git 写操作**(add / commit / checkout / rebase / filter-branch 一律禁止)。
  只允许 `git show 1419621^:<path>` 这一种只读取值。
- **不要 kill 或重启任何进程**(PID 2271374 采集器、2685886 shadow daemon 在跑生产)。
- 不要写 `reports/` 下的任何文件。
- 单次 Write/Edit ≤150 行或 6000 字符;四个 fixture 文件用 `git show ... > 文件` 落盘,
  不要用 Write 工具逐行抄(会超限也会抄错)。

## ENVIRONMENT(照做,别自己找解释器)
- 直接用 `python3`(3.12.3 + pytest 7.4.4 + pycryptodome,本仓库钉死的版本)。
- **不要找 venv**(`/root/lp-bot/.venv` 无权限)。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`。不要整读 >300 行的文件。

## VALIDATION(命令与输出尾部原样贴进报告)
1. `python3 -m pytest tests/test_rh02ba_silent_failure_hunt2.py -q`(**13 passed, 0 failed**)
2. `grep -n "4aa4497\|PRE_FIX_REV\|git.*show\|subprocess" tests/test_rh02ba_silent_failure_hunt2.py`
   (**应无 SHA、无 subprocess、无 git show**)
3. `ls -la tests/fixtures/rh02ba_pre_fix/`(四个 .py + 一个 README.md)
4. 临时把某个 fixture 改名,确认测试**报明确错误而不是静默通过**,再改回来;把这一步的输出贴出来
5. **不要跑全量测试**。主脑会统一跑。

最后按以下字段报告:TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
