# RH-02bk-2 — 补完合成测试证据生成器（前一个 worker 断在半截）

## 现状

`scripts/lp_rh_synthetic_evidence_v1.py` 已经写了 **96 行**（未跟踪文件），
包含完整且质量合格的：

- 模块 docstring 与常量 `SCHEMA_VERSION` / `CODE_VERSION_SOURCE` / `SUMMARY_KEYS`
- `resolve_code_version(repo) -> tuple[str, bool]`（fail-close 已正确实现）
- `parse_pytest_summary(text) -> dict`（找不到汇总行时全部返回 `None`，正确）

**这 96 行不要改、不要重写。** 前一个 worker 是被推理网关 502 打断的，
不是代码有问题。

## 要做的事：只补两个函数 + 一个测试文件

### 1. `build_evidence(*, repo, tests_path, run=True) -> dict`

组装证据 dict，字段与顺序：

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-10T03:05:00Z",
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

- `generated_at`：UTC，形如 `2026-09-10T03:05:00Z`（用 `datetime.now(timezone.utc)`）
- `run=False`（`--dry-run` 用）：跳过 pytest，`exit_code` 与五个计数全为 `None`，
  `all_passed` 为 `False`
- `run=True`：用
  `subprocess.run([sys.executable, "-m", "pytest", tests_path, "-q", "-p", "no:cacheprovider"],
   cwd=repo, capture_output=True, text=True)`，
  把 `stdout + stderr` 一起交给 `parse_pytest_summary`

**`all_passed` 的判据（四个条件全满足才 True）**：

```python
all_passed = (exit_code == 0 and failed == 0 and errors == 0
              and total is not None and total > 0)
```

`total` 为 `None` 或 `0` 一律 `False`——**零测试绝不算通过**，这是本包最重要的一条。
注意 `failed` / `errors` 可能是 `None`（解析失败），`None == 0` 是 `False`，
所以要写成显式判断，别让 `None` 蒙混过关。

### 2. `main(argv=None) -> int`

```
python3 scripts/lp_rh_synthetic_evidence_v1.py \
    [--repo <默认: 脚本所在目录的上一级>] \
    [--out reports/lp_rh/synthetic_tests_evidence.json] \
    [--tests-path tests/] \
    [--dry-run]
```

- `resolve_code_version` 抛 `RuntimeError` → 向 **stderr** 打印原因，
  **不写任何文件**，返回 `2`
- `--dry-run` → 把证据骨架 `json.dumps(..., indent=2)` 打到 stdout，
  **不写文件**，返回 `0`
- 正常 → 写 `--out`（`Path(out).parent.mkdir(parents=True, exist_ok=True)`），
  打印一行 `wrote <path> all_passed=<bool>`，
  返回 `0` if `all_passed` else `1`

文件末尾：

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

### 3. 测试 `tests/test_lp_rh_synthetic_evidence_v1_readonly.py`

用 `importlib.util.spec_from_file_location` 加载脚本（仓库其它测试就是这么做的）。
全部用**假数据**，**不真跑 pytest 套件**，不碰真实仓库状态。

1. `parse_pytest_summary("4611 passed in 123.45s")`
   → `total=4611, passed=4611, failed=0, duration_secs=123.45`
2. `parse_pytest_summary("4609 passed, 2 failed in 130.01s")` → `passed=4609, failed=2, total=4611`
3. `parse_pytest_summary("12 failed, 4599 passed, 3 skipped, 1 error in 140.2s")`
   → `failed=12, passed=4599, skipped=3, errors=1, total=4615`
4. `parse_pytest_summary("完全无关的一段文字")` → 每个键都是 `None`
5. `build_evidence` 在 `exit_code=0` 但 `total=0` 时 → `all_passed is False`
   （**零测试不算通过**；用 monkeypatch 替掉 `subprocess.run` 造这个场景）
6. `build_evidence` 在 `failed>0` 时 → `all_passed is False`
7. `build_evidence` 在解析失败（`total is None`）时 → `all_passed is False`
8. `resolve_code_version(str(tmp_path))` 指向非 git 目录 → 抛 `RuntimeError`
9. `--dry-run` 不写出文件（`--out` 指向 `tmp_path` 下一个路径，断言该文件不存在），
   且返回 `0`

**每条断言都要真能触发目标分支。** 本仓库已四次写出「构造的输入进不去被测分支、
于是测试永远绿」的假测试，写完自己确认一遍。

## 不许动

- **不要改已有的 96 行**（docstring、常量、`resolve_code_version`、`parse_pytest_summary`）。
- **不要碰 `scripts/lp_rh_readiness_v1_readonly.py` 和
  `tests/test_lp_rh_readiness_v1_readonly.py`**——另一个 job 正在改它们，
  读了只会浪费轮次，改了会冲突。
- 不要动任何 `.db`、不要动 `reports/` 下任何文件。
- **不要执行任何 git 命令**（不要 add / commit / checkout / stash）。
- **不要跑全量 pytest**（要几分钟）；只跑你自己的新测试文件。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_synthetic_evidence_v1_readonly.py -q`
   全绿，条数 ≥ 9。
2. ```
   python3 scripts/lp_rh_synthetic_evidence_v1.py --out /tmp/ev.json \
       --tests-path tests/test_lp_rh_synthetic_evidence_v1_readonly.py
   ```
   → 退出码 0；`/tmp/ev.json` 存在；里面 `code_version` 是 12 位十六进制、
   `all_passed` 为 `true`、`total` 等于该测试文件的实际条数。
   （**输出到 `/tmp`，不要写进仓库的 `reports/`**——落盘是主脑裁决后的动作。）
3. `python3 scripts/lp_rh_synthetic_evidence_v1.py --dry-run --out /tmp/never.json`
   → 退出码 0，`/tmp/never.json` **不存在**。
4. `git status --short` 里只有这两个文件是 `??`（新文件），
   **`scripts/lp_rh_readiness_v1_readonly.py` 的改动状态不能被你改变**。
