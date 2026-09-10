# RH-02bk-1 — 合成测试证据生成器（**只建一个新脚本，不碰任何已有文件**）

## 上一轮失败原因（务必读，不要重蹈）

RH-02bk 的 worker 跑了 28 分钟、96 个 turn，做了 36 次 Bash + 12 次 Read、
**一次 Write/Edit 都没有**，目标文件一个都没建。它把时间全花在
「研究 readiness 闸门怎么接线」上，而且开始读
`tests/test_lp_rh_readiness_v1_readonly.py`——那个文件另一个 worker 正在改，
差点撞车。

**本包已经把范围砍到只剩一件事：写一个新脚本。**
不要去研究闸门、不要读 readiness、不要读 readiness 的测试。
下面给出的内容已经足够，**直接开始写文件**。

## 唯一任务

新建 `scripts/lp_rh_synthetic_evidence_v1.py`：跑一次仓库测试套件，
把结果连同**当前代码版本**写成机器可读的证据文件。

这个文件将来会被 Stage A 闸门用作 `synthetic_tests_passed` 的证据来源
（**闸门接线是下一个包的事，本包不做**）。

### 命令行

```
python3 scripts/lp_rh_synthetic_evidence_v1.py \
    [--repo <仓库根，默认为脚本所在目录的上一级>] \
    [--out reports/lp_rh/synthetic_tests_evidence.json] \
    [--tests-path tests/] \
    [--dry-run]
```

`--dry-run`：不真跑 pytest，只解析版本信息并打印将要写入的骨架，**不写文件**。

### 产出 JSON（`reports/lp_rh/synthetic_tests_evidence.json`）

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-10T02:50:00Z",
  "code_version": "9e419031f2ab",
  "code_version_source": "git rev-parse --short=12 HEAD",
  "working_tree_clean": true,
  "command": "python3 -m pytest tests/ -q -p no:cacheprovider",
  "exit_code": 0,
  "total": 4611,
  "passed": 4611,
  "failed": 0,
  "errors": 0,
  "skipped": 0,
  "duration_secs": 123.4,
  "all_passed": true
}
```

### 必须遵守的三条语义

1. **`code_version` 取不到就 fail-close。**
   拿不到 git HEAD（不是 git 仓库、git 不可用、命令失败）时：
   **不要写文件**，向 stderr 打印原因并以退出码 `2` 结束。
   绝不能写一个 `code_version: null` 或 `"unknown"` 的证据文件出去——
   本仓库今晚已确认 26 例「静默假绿」，都是这类宽容默认值造成的。

2. **`working_tree_clean`** = `git status --porcelain` 里**已跟踪文件**是否 0 改动
   （即过滤掉 `??` 开头的行后为空）。工作区脏时仍然写文件，但这个字段为 `false`，
   让下游闸门自己决定要不要认。

3. **`all_passed`** 必须同时满足 `exit_code == 0` **且** `failed == 0` **且**
   `errors == 0` **且** `total > 0`。
   任何一条不满足就是 `false`。`total == 0`（一个测试都没收集到）
   **绝不能**算通过——这是典型的假绿。

### 解析 pytest 输出

用 `subprocess.run([...], capture_output=True, text=True)` 跑
`python3 -m pytest <tests-path> -q -p no:cacheprovider`。
从**输出末尾**的汇总行解析数字，例如：

```
4611 passed in 123.45s
4609 passed, 2 failed in 130.01s
12 failed, 4599 passed, 3 skipped, 1 error in 140.2s
```

写一个独立函数 `parse_pytest_summary(text: str) -> dict`，
返回 `{"total","passed","failed","errors","skipped","duration_secs"}`。
**解析不出汇总行时返回全 `None`**（不是 0），调用方据此把 `all_passed` 置 `false`。

### 建议的函数结构（照着写即可）

```python
def resolve_code_version(repo: str) -> tuple[str, bool]:
    """返回 (short_sha_12, working_tree_clean)。失败抛 RuntimeError。"""

def parse_pytest_summary(text: str) -> dict:
    """解析 pytest -q 的末尾汇总行。解析不出返回各键为 None 的 dict。"""

def build_evidence(*, repo: str, tests_path: str, run: bool = True) -> dict:
    """组装证据 dict。run=False 时跳过 pytest（--dry-run 用）。"""

def main(argv=None) -> int: ...
```

## 不许动

- **只新建两个文件**：`scripts/lp_rh_synthetic_evidence_v1.py` 和
  `tests/test_lp_rh_synthetic_evidence_v1_readonly.py`。
- **不要读、不要改 `scripts/lp_rh_readiness_v1_readonly.py`**，
  也不要读 `tests/test_lp_rh_readiness_v1_readonly.py`——
  另一个 worker 正在改它，读了只会浪费你的轮次。
- 不要动任何 `.db`、不要动 `reports/lp_rh/pool_meta.json`。
- **不要执行任何 git 命令去改仓库状态**（`git status` / `git rev-parse` 这类
  只读查询在脚本内部是允许的；但你自己**不要** add / commit / checkout / stash）。
- 单次 Write ≤150 行或 6000 字符；脚本超过 150 行就分两次写。
- **不要跑全量 pytest 来验证**（要几分钟）；只跑你自己的新测试文件。

## 测试（`tests/test_lp_rh_synthetic_evidence_v1_readonly.py`）

全部用**假数据**，不真跑 pytest、不碰真实仓库状态。

1. `parse_pytest_summary("4611 passed in 123.45s")`
   → `total=4611, passed=4611, failed=0, duration_secs=123.45`
2. `parse_pytest_summary("4609 passed, 2 failed in 130.01s")`
   → `passed=4609, failed=2, total=4611`
3. `parse_pytest_summary("12 failed, 4599 passed, 3 skipped, 1 error in 140.2s")`
   → `failed=12, passed=4599, skipped=3, errors=1, total=4615`
4. `parse_pytest_summary("完全无关的一段文字")` → 每个键都是 `None`
5. `build_evidence` 在 `exit_code=0` 但 `total=0` 时 → `all_passed is False`
   （**这条最重要：零测试不算通过**）
6. `build_evidence` 在 `failed>0` 时 → `all_passed is False`
7. `resolve_code_version` 指向一个非 git 目录（用 `tmp_path`）→ 抛 `RuntimeError`
8. `--dry-run` 不写出文件（用 `tmp_path` 作 `--out`，断言文件不存在）

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_synthetic_evidence_v1_readonly.py -q` 全绿，条数 ≥ 8。
2. 真实跑一次
   `python3 scripts/lp_rh_synthetic_evidence_v1.py --out /tmp/ev.json --tests-path tests/test_lp_rh_synthetic_evidence_v1_readonly.py`
   → 退出码 0，`/tmp/ev.json` 存在，里面 `code_version` 是 12 位十六进制、
   `all_passed` 为 `true`、`total` 等于该文件的测试条数。
   （**输出到 `/tmp`，不要写进仓库的 `reports/`**——落盘是主脑裁决后的动作。）
3. `git status --short` 里只有这**两个新文件**（`??` 状态），
   **没有任何已跟踪文件被改动**。
