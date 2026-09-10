# RH-02bo — 空的证据表不等于「零违反」

## 缺陷（主脑自己上一轮引入，已核实，不要重新调研）

`scripts/lp_rh_readiness_v1_readonly.py` 的 `audit_invariant_violations()`
（L539 起）这样开头：

```python
tbls = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
violations = 0            # <-- 起点就是「零」
details = []
checks_performed = []
```

四个检查各自包在 `if "<表名>" in tbls:` 里。**表存在但一行都没有时，
循环跑零次、`violations` 保持 `0`**，函数返回
`{"passed": True, "violations_count": 0}`。

`_build_state`（L920-923）把这个 `0` 当成真实计数交给 Stage A/B，
`stage_a_status`（L178）于是认为「已查证、确实零违反」。

**当前六张账本表全部是 0 行**（`rh_gate_decisions` / `rh_position_marks` /
`rh_journal` / `rh_shadow_positions` / `rh_bucket_reservations` /
`rh_economic_evaluations`），所以这个检查此刻正在对着空气打勾。

这是上一轮把该函数从「永久阻断」改成「接真实审计」时漏掉的状态：

```
表不存在   -> 应为 None（未知）
表存在但空 -> 应为 None（未知）   <-- 漏了这个，当前返回 0
表存在有行 -> 真实计数
```

同族的 `unexplained_ledger_diffs=0` / `missed_risk_events=0` 已在 commit
`4d1d5e3` 修掉，本包补上这最后一个。codex 给这族起的节点名是
`RH-READINESS-EMPTY-EVIDENCE-AS-ZERO`。

## 要做的事

### 1. `audit_invariant_violations` 区分「查过」与「没得查」

给返回 dict 新增 `unavailable_checks: list[str]`，记录每一个
**因表不存在或表为空而无法执行**的检查（用现有 `checks_performed`
里同样的命名，如 `"rh_journal:balance_integrity"`）。

判定规则：

- 该检查涉及的表**不存在** → 计入 `unavailable_checks`
- 该表**存在但 `COUNT(*) == 0`** → 同样计入 `unavailable_checks`
- 表有行 → 正常执行，结果计入 `violations` 与 `checks_performed`

**只要 `unavailable_checks` 非空，`violations_count` 就是 `None`**，
`passed` 为 `False`。

理由：Stage A/B 要的断言是「零关键不变量违反」，不是「我查过的那部分是零」。
有一项没法验证，整体结论就是未知。

`unsupported` 那三条（INV-IL-01 / INV-V4-01 / INV-TVLSHARE-01）
是**已知且已声明不支持**的，不要算进 `unavailable_checks`——
它们与「本该能查却没数据」是两回事，保持现状。

### 2. blocker 理由要能分辨

现在 `stage_a_status`（L177-180）对「未知」和「有违反」用同一个
`STAGE_A_INVARIANT_VIOLATIONS`，看报告的人分不出是哪种。

新增常量 `STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE`，并改成：

```python
invariant_ok = True
if invariant_violations is None:
    invariant_ok = False
    blockers.append(STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE)
elif invariant_violations > 0:
    invariant_ok = False
    blockers.append(STAGE_A_INVARIANT_VIOLATIONS)
```

**Stage B 那边不用改**——`stage_b_status`（L220-222）已经正确区分了
`None` 与非零。

### 3. 报告里显示出来

Markdown 报告的 Stage A 段落，在 invariant 那一行后面补一行列出
`unavailable_checks`（有的话），形如：

```
  - invariant: NOT_MEASURED (未执行的检查: rh_journal:balance_integrity,
    rh_gate_decisions:conjunction_consistency, rh_position_marks:nav_non_negative)
```

## 不许动

- **不要改 `stage_b_status()`**——它已经是对的。
- 不要改 `audit_weekends_covered` / `audit_unexplained_ledger_diffs` /
  `audit_missed_risk_events`（commit `4d1d5e3` 刚验收入库）。
- 不要改 `audit_key_field_health` / `coverage_for_asset` / `stage_a_status`
  里除 invariant 那三行以外的任何逻辑。
- 不要改那三条 `unsupported` 的内容。
- 不要动任何 `.db`，全部只读 SQL。测试一律用内存库。
- **不要执行任何 git 命令**（不要 add / commit / checkout / stash）。
- 单次 Write/Edit ≤150 行或 6000 字符。
- 不要整读这个 1000 行的文件；用 `grep -n` 定位，
  `sed -n '539,640p'` 读该函数，`sed -n '170,200p'` 读 stage_a 分支。

## 测试（追加到 `tests/test_lp_rh_readiness_v1_readonly.py`）

内存库，每条都要真能触发目标分支。

1. 四张相关表**全部不存在** → `violations_count is None`，
   `unavailable_checks` 含全部四项。
2. 四张表**都存在但都是 0 行** → `violations_count is None`。
   **这条是本包核心：空表 ≠ 零违反。**
3. `rh_market_states` 有正常行、其余三张为空 →
   `violations_count is None`（有一项没法查就是未知），
   `checks_performed` 含市场那项、`unavailable_checks` 含其余三项。
4. 四张表都有行且都干净 → `violations_count == 0`，
   `unavailable_checks == []`，`passed is True`。
   ——这条证明修复没有把正常情况也变成 None。
5. 四张表都有行、其中 `rh_journal` 有一条借贷账户为空的行 →
   `violations_count >= 1`。
6. `stage_a_status(invariant_violations=None, ...)` →
   blockers 含 `STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE`
   且**不含** `STAGE_A_INVARIANT_VIOLATIONS`。
7. `stage_a_status(invariant_violations=3, ...)` →
   blockers 含 `STAGE_A_INVARIANT_VIOLATIONS`
   且**不含** `..._UNAVAILABLE`。

## 验收标准（主脑会逐条查）

1. 在**真实库**上跑：
   ```
   python3 -c "
   import importlib.util,sqlite3
   s=importlib.util.spec_from_file_location('r','scripts/lp_rh_readiness_v1_readonly.py')
   m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
   c=sqlite3.connect('file:reports/lp_rh/scanner.db?mode=ro',uri=True)
   r=m.audit_invariant_violations(c)
   print(r['violations_count'], r.get('unavailable_checks'))
   "
   ```
   `violations_count` **必须是 None**（真实库那几张表都是空的），
   `unavailable_checks` **非空**。
   ——这条是本包核心证据；修之前它打印的是 `0 None`。
2. 真实库上跑 readiness，Stage A blockers 里出现
   `STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE`。
3. `python3 -m pytest tests/test_lp_rh_readiness_v1_readonly.py -q` 全绿，新增 ≥7 条。
4. 全量 `python3 -m pytest tests/ -q` 通过。
5. `git status --short` 里只有 `scripts/lp_rh_readiness_v1_readonly.py` 和
   `tests/test_lp_rh_readiness_v1_readonly.py` 被改动。
