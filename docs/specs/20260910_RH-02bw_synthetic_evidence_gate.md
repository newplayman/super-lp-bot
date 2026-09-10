# RH-02bw — 把合成测试证据接到 Stage A 闸门上

## 背景

Stage A 现在只剩三个 blocker：

```
HOURS_COVERED_INSUFFICIENT               <- 等时间，13h/72h
STAGE_A_SYNTHETIC_TESTS_UNKNOWN          <- 本包解决
STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE <- 等账本表有数据
```

`synthetic_tests_passed` 至今**没有任何证据来源**：
`_build_state` 只把 CLI 参数 `--synthetic-tests-passed` 透传下去，
没人提供它，于是永远是 `None` → 永久阻断。

commit `4d1d5e3` 已经做好了生成器 `scripts/lp_rh_synthetic_evidence_v1.py`，
它跑一次测试套件并写出：

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-10T03:05:00Z",
  "code_version": "9e419031f2ab",
  "code_version_source": "git rev-parse --short=12 HEAD",
  "working_tree_clean": true,
  "command": "python3 -m pytest tests/ -q -p no:cacheprovider",
  "exit_code": 0,
  "total": 4611, "passed": 4611, "failed": 0, "errors": 0, "skipped": 0,
  "duration_secs": 123.4,
  "all_passed": true
}
```

本包把闸门接到这个文件上。**证据文件本身不要在这一包里生成**——
落盘是主脑裁决后的动作。

## 要做的事

改 `scripts/lp_rh_readiness_v1_readonly.py`。

### 1. 新增 `audit_synthetic_tests(path, *, repo_root) -> dict`

读证据文件并判定，返回：

```python
{
  "passed": True/False/None,     # None = 无法判定
  "reason": "OK" | "<明确的失败原因>",
  "code_version": "<文件里的值或 None>",
  "head_version": "<当前 HEAD 前 12 位或 None>",
  "generated_at": "<原样或 None>",
  "evidence_path": "<path>",
}
```

判定顺序与理由常量（**每一条都要能从 reason 分辨**）：

| 情况 | reason | passed |
|---|---|---|
| 文件不存在 | `SYNTHETIC_EVIDENCE_MISSING` | `None` |
| 文件不是合法 JSON / 不是对象 | `SYNTHETIC_EVIDENCE_INVALID` | `None` |
| `schema_version` != 1 | `SYNTHETIC_EVIDENCE_SCHEMA_MISMATCH` | `None` |
| 缺 `code_version` 或 `all_passed` 键 | `SYNTHETIC_EVIDENCE_INCOMPLETE` | `None` |
| 拿不到当前 HEAD | `SYNTHETIC_EVIDENCE_HEAD_UNRESOLVED` | `None` |
| `code_version` != 当前 HEAD | `SYNTHETIC_EVIDENCE_STALE_CODE_VERSION` | `False` |
| `working_tree_clean` 不是 `True` | `SYNTHETIC_EVIDENCE_DIRTY_WORKING_TREE` | `False` |
| `all_passed` 不是 `True` | `SYNTHETIC_TESTS_FAILED` | `False` |
| 以上都通过 | `OK` | `True` |

**`code_version` 比的是完整的 HEAD**，不是采集侧代码
（那是 RH-02bn 判定窗口的口径，两者不同，别混）。
理由：合成测试证明的是「这一版代码通过了测试」，**任何**代码变更都让它失效。
这条正是要挡住「代码改了、测试没重跑」。

**不要加 TTL**：测试结果不随时间失效，只随代码失效。
但要检查 `generated_at` 能解析，解析不了归入 `SYNTHETIC_EVIDENCE_INVALID`。

拿 HEAD 用 `git rev-parse --short=12 HEAD`，`cwd=repo_root`，
**失败就 fail-close 返回 None**，不要猜。

### 2. `_build_state` 接线

新增参数 `synthetic_evidence_path: Optional[str] = None`，
默认 `<repo_root>/reports/lp_rh/synthetic_tests_evidence.json`。

**CLI 参数 `--synthetic-tests-passed` 优先级更高**：显式传了就用它
（人工覆盖的口子要留着，排查时有用），没传才读证据文件。
把审计结果放进 `state["synthetic_evidence"]` 供报告渲染。

### 3. blocker 理由要能分辨

现在只有一个 `STAGE_A_SYNTHETIC_TESTS_UNKNOWN`。改成：

- `passed is None` → `STAGE_A_SYNTHETIC_TESTS_UNKNOWN`（现有常量，保留）
- `passed is False` → 新常量 `STAGE_A_SYNTHETIC_TESTS_FAILED`

两者都阻断，但报告里要能看出「没证据」和「有证据但没过」的区别。

### 4. 报告里显示

Stage A 段落加一行：

```
  - synthetic: OK (code_version=8e54926abc12, generated_at=2026-09-10T03:05:00Z)
```
或
```
  - synthetic: NOT_MEASURED (SYNTHETIC_EVIDENCE_MISSING)
```

## 不许动

- 不要改 `scripts/lp_rh_synthetic_evidence_v1.py`（生成器已验收入库）。
- 不要改 `resolve_judgment_window` / `audit_invariant_violations` /
  `audit_pool_attestation` / `audit_weekends_covered` /
  `audit_unexplained_ledger_diffs` / `audit_missed_risk_events` /
  `audit_key_field_health`（commit `4d1d5e3`/`8e54926`/`7ffbb24`/`bcfc3c6` 刚入库）。
- **不要生成 `reports/lp_rh/synthetic_tests_evidence.json`**，
  也不要在测试里往仓库的 `reports/` 写任何文件。
- 不要碰 `scripts/lp_rh_shadow_runner_v1_readonly.py`（另一条线正在改）。
- 不要碰 `scripts/lp_silent_failure_lint_v1_readonly.py`（工作区已有另一条线的改动）。
- **不要执行任何 git 命令**（函数内部调 `git rev-parse` 是本包要求的；
  你自己不要 add / commit / checkout / stash）。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（追加到 `tests/test_lp_rh_readiness_v1_readonly.py`）

用 `tmp_path` 造证据文件，**不要碰真实的 reports/ 目录**。
HEAD 用一个 `tmp_path` 里的真 git 仓库，或把 `repo_root` 指向真仓库后
用真实 HEAD 值构造证据——两种都行，但断言不能依赖某个具体 sha 常量
（那是数据状态，会自我失效；本会话已因此坏过两次测试）。

1. 文件不存在 → `passed is None`，reason `SYNTHETIC_EVIDENCE_MISSING`，
   Stage A blockers 含 `STAGE_A_SYNTHETIC_TESTS_UNKNOWN`。
2. 文件内容不是 JSON → `SYNTHETIC_EVIDENCE_INVALID`。
3. `schema_version: 2` → `SYNTHETIC_EVIDENCE_SCHEMA_MISMATCH`。
4. 缺 `all_passed` 键 → `SYNTHETIC_EVIDENCE_INCOMPLETE`。
5. `code_version` 是一个明显不同的值（如 `"0000deadbeef"`）→
   `passed is False`，reason `SYNTHETIC_EVIDENCE_STALE_CODE_VERSION`，
   Stage A blockers 含 `STAGE_A_SYNTHETIC_TESTS_FAILED`。
   **这条最重要：它保证「代码改了、测试没重跑」不会蒙混过关。**
6. `code_version` 正确但 `working_tree_clean: false` →
   `SYNTHETIC_EVIDENCE_DIRTY_WORKING_TREE`，`passed is False`。
7. `code_version` 正确、clean、但 `all_passed: false` →
   `SYNTHETIC_TESTS_FAILED`，`passed is False`。
8. 全部正确 → `passed is True`，reason `OK`，
   Stage A blockers **不含**任何 `STAGE_A_SYNTHETIC_TESTS_*`。
   ——这条证明修复真的能解除阻断。
9. CLI 显式传 `synthetic_tests_passed=True` 时，
   即使证据文件不存在也按 True 走（人工覆盖优先）。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_readiness_v1_readonly.py -q` 全绿，新增 ≥9 条。
2. 真实库上跑（证据文件此刻**不存在**）：
   ```
   python3 scripts/lp_rh_readiness_v1_readonly.py --db reports/lp_rh/scanner.db \
       --out /tmp/rdy_bw.md --asset-address 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
   ```
   Stage A blockers 仍含 `STAGE_A_SYNTHETIC_TESTS_UNKNOWN`，
   且报告里能看到 `synthetic: NOT_MEASURED (SYNTHETIC_EVIDENCE_MISSING)`。
3. 造一个**正确的**证据文件到 `/tmp`（用当前真实 HEAD），
   用 `--synthetic-evidence-path /tmp/ev.json` 跑，
   Stage A blockers **不再含** `STAGE_A_SYNTHETIC_TESTS_UNKNOWN`。
   把两次的 blockers 行都贴进总结。
   （需要为此加一个 `--synthetic-evidence-path` CLI 参数。）
4. `git status --short` 里只有 `scripts/lp_rh_readiness_v1_readonly.py` 和
   `tests/test_lp_rh_readiness_v1_readonly.py` 被改动
   （lint 那两个文件的改动是另一条线的，不要碰）。
