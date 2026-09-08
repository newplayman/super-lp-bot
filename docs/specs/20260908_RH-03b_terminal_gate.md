# RH-03b：RH 终闸合取 + 摘除变异测试（离线可测）

## 背景（一段）

PRD v1.1 §11.5 规定 RH 的终闸是一个**十项合取**，§18.3 的 RH-INV-04 要求**每一道新硬闸都必须有生产者、有读取、进终闸合取、并有"摘除后坏样本被错误放行"的变异测试**。仓库已有成熟范式：`tests/test_inv_gate_02_terminal_conjunction.py`（168 行）用 `ast` 解析函数源码断言合取式的**形状**（哪些名字参与了 `and`），再用参数化逐闸置 False 断言拒绝，最后用 mutation witness 证明"这套测试确实能抓到漏接的闸"。**本包必须照抄这套范式**，不要另发明。

上游已就位：`scripts/lp_rh_netcover_inputs_v1_readonly.py`（装配器 + `classify_zero_candidate`）、`lp_rh_bucket_ledger_v1_readonly.py`（`capital_policy_conflict`、`try_reserve`）、`lp_rh_market_session_v1_readonly.py`（`allows_new_position`）、`lp_rh_registry_v1_readonly.py`、`lp_rh_pool_probe_v1_readonly.py`、`lp_rh_capabilities_v1_readonly.py`、`lp_rh_store_v1_readonly.py`。

## 新增文件

1. `scripts/lp_rh_terminal_gate_v1_readonly.py`（**≤ 250 行**，分次写）
   - 顶部仓库通行 sys.path 引导。
   - 十个合取项**必须用这十个变量名**（PRD §11.5 逐条对应），全部为 `bool`：
     `legacy_required_conjunction, identity_verified, protocol_capabilities_sufficient, data_complete_and_fresh, profile_policy_pass, market_and_chain_risk_pass, netcover_pass, absolute_profit_pass, position_and_exit_depth_pass, capital_policy_pass`
   - `TERMINAL_CONJUNCTS = frozenset({...十个名字...})`（模块级常量，供测试断言）。
   - `dataclass GateDecision`：`decision_id, candidate_key, target_mode, terminal_eligible: bool, terminal_bits: dict[str,bool], primary_status: str, dominant_blocker: str|None, reasons: list[str], snapshot_ids: list[str], decided_at: str`。
   - `evaluate_terminal_gate(record, *, target_mode, now) -> GateDecision`：
     - `target_mode` 只允许 `"SHADOW_SCENARIO"` 或 `"LIVE_READINESS"`（其它抛 `ValueError("UNKNOWN_TARGET_MODE")`）。
     - **合取式必须写成单一表达式**，形如
       ```python
       terminal_eligible = (
           legacy_required_conjunction
           and identity_verified
           and ... （十项全列）
       )
       ```
       以便 AST 测试能提取名字集合。**不许用 `all([...])` 或循环**，那样 AST 断言无法验证形状。
     - `legacy_required_conjunction` 必须来自记录里**有真实生产者**的布尔值（读 `record["legacy_required_conjunction"]`）；若该键缺失或为 `None` → 视为 `False` 并把 `"LEGACY_CONJUNCTION_NO_PRODUCER"` 记进 `reasons`（PRD §11.5 明令不得再出现"永远没被写出的字段"）。
     - `capital_policy_pass`：`target_mode == "LIVE_READINESS"` 且存在资本政策冲突 → **恒为 False**，`dominant_blocker = "CAPITAL_POLICY_CONFLICT"`，`primary_status = "POLICY_BLOCKED"`。`SHADOW_SCENARIO` 下允许为 True，但结果必须带 `simulated_policy_only=True`（PRD §6.1：情景模拟通过不得写成生产终闸通过）。
     - `primary_status` 复用 `classify_zero_candidate`（从 `lp_rh_netcover_inputs_v1_readonly` import，**不重写分类逻辑**），但 `POLICY_BLOCKED` 优先级最高。
     - `dominant_blocker`：按固定优先级返回第一个为 False 的闸名（顺序即上面十项的书写顺序），全 True 时为 `None`。
   - `mutation_witness_removed_gate(record, *, removed: str, target_mode, now) -> bool`：把 `removed` 这一项强制置 True 后重算合取，返回 `terminal_eligible`。供测试证明摘除任一闸会让坏样本被放行。
   - `main()`：`--record-json <file> --target-mode <mode> --out <file>`，不联网、不写 db。
2. `tests/test_lp_rh_terminal_gate_v1_readonly.py`（≤ 250 行），至少 18 个测试：
   - **AST 形状断言**（照抄 `tests/test_inv_gate_02_terminal_conjunction.py:60-118` 的 `_bool_conjunct_names` 辅助函数写法，可直接 import 或复制该辅助）：`evaluate_terminal_gate` 源码中赋给 `terminal_eligible` 的 `and` 链，其参与名字集合**必须精确等于** `TERMINAL_CONJUNCTS`。新增或删除一项都会让该测试失败，强制显式更新不变量。
   - **逐闸拒绝**（`@pytest.mark.parametrize` 遍历十项）：其余九项为 True、该项为 False → `terminal_eligible is False` 且 `dominant_blocker == 该闸名`。
   - **摘除变异测试**（`@pytest.mark.parametrize` 遍历十项）：照抄 `:149-168` 的 mutation witness 写法——构造一个把该闸恢复为 True 的 mutant，断言"逐闸拒绝"这套检查在 mutant 下**必然抛 AssertionError**，消息含被摘除的闸名。这证明测试本身能抓到漏接。
   - **T25 / 资本政策**：`LIVE_READINESS` + 冲突 → `terminal_eligible False`、`primary_status == "POLICY_BLOCKED"`、`dominant_blocker == "capital_policy_pass"`；同一记录在 `SHADOW_SCENARIO` 下可 `True` 但带 `simulated_policy_only=True`。**两种 mode 的结论必须不同**。
   - **T59 / 无生产者**：记录缺 `legacy_required_conjunction` → 该项 False、`reasons` 含 `LEGACY_CONJUNCTION_NO_PRODUCER`、`primary_status` **不是** `COMPUTED_FAIL`（缺生产者不是经济证伪）。
   - **T60**：十项全 True → `terminal_eligible True`、`dominant_blocker is None`；全闲置（零候选）是合法结果，不强制下单。
   - `target_mode` 非法 → `ValueError("UNKNOWN_TARGET_MODE")`。
   - `main --record-json` 跑一份含 3 条（全通过 / 缺生产者 / 政策冲突）的合成 fixture，退出码 0。fixture 放 `tests/fixtures/rh/synthetic/terminal_records.json`，标 `"data_kind": "SYNTHETIC_NOT_CHAIN_DATA"`。

## 不许动什么

- 不改任何现有脚本/测试/配置/六常量；**尤其不许碰 `scripts/lp_rh_collector_v1_readonly.py`（正在生产运行）**、`lp_rh_netcover_inputs_v1_readonly.py`、`tests/test_lp_rh_netcover_inputs_v1_readonly.py`（另一 worker 可能在改）。
- 不重写 `classify_zero_candidate`，必须 import 复用。
- 不联网、不写 `reports/lp_rh/`、不读 `.env*`。
- 不要用 TaskCreate/TaskUpdate 工具；单次 Write/Edit ≤150 行。

## 验收标准

- [ ] `git status --short` 新增只有 1 脚本 + 1 测试 + 1 fixture；`git diff --stat` 为空。
- [ ] 新测试 ≥18 个且全绿。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` 0 failed、14 skipped。
- [ ] AST 形状测试确实生效：临时把合取式删掉一项后该测试**会失败**（worker 自己验证一次再改回，把验证输出贴进最终报告）。
- [ ] `grep -c 'all(\[' scripts/lp_rh_terminal_gate_v1_readonly.py` 为 0（合取必须是显式 and 链）。

## 验证命令

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_terminal_gate_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
env -u PYTHONPATH /root/lp-bot/.venv/bin/python scripts/lp_rh_terminal_gate_v1_readonly.py --record-json tests/fixtures/rh/synthetic/terminal_records.json --target-mode LIVE_READINESS --out /tmp/tg.json && head -c 500 /tmp/tg.json
git diff --stat; git status --short | grep -E 'lp_rh_terminal'
```

---

# 上轮退回原因（主脑验收 2026-09-08 06:45，REJECT）

十项合取式本身**完全正确**，主脑逐闸复核：十项各自置 False 都能拒绝，`dominant_blocker` 精确指向该闸，`all([` 零命中，非法 mode 抛 `UNKNOWN_TARGET_MODE`，28 个测试全绿。**合取逻辑保留不动**。退回只针对 `primary_status`。

## FAIL-1：`primary_status` 在终闸已判否时仍返回 `COMPUTED_PASS`（假绿）

主脑实测两个反例：

| 场景 | `terminal_eligible` | `dominant_blocker` | `primary_status` | 应为 |
|---|---|---|---|---|
| `LIVE_READINESS` + `capital_policy_pass=False` | False | `capital_policy_pass` ✓ | **`COMPUTED_PASS`** ✗ | `POLICY_BLOCKED` |
| 缺 `legacy_required_conjunction` | False | `legacy_required_conjunction` ✓ | **`COMPUTED_PASS`** ✗ | `INPUTS_UNAVAILABLE` |

`COMPUTED_PASS` 的语义是"该候选的经济评估通过"。对一条被政策阻挡、或关键字段根本没有生产者的记录报这个值，等于告诉面板和下游"它算过且通过了"。这是 PRD §8.4 与 §10.1 明令禁止的形态，危险性高于合取本身出错——`dominant_blocker` 对了但 `primary_status` 错了，只读 status 的消费者会被误导。

**要求**：`primary_status` 按以下**固定优先级**决定，第一个命中即返回：

1. `target_mode == "LIVE_READINESS"` 且 `capital_policy_pass is False` → `"POLICY_BLOCKED"`
2. `reasons` 含 `"LEGACY_CONJUNCTION_NO_PRODUCER"`，或十项中任一为 `None`/缺失 → `"INPUTS_UNAVAILABLE"`
3. `protocol_capabilities_sufficient is False` 或记录的 `rejection_reason` 以 `NETCOVER_MODEL_PATH_MISMATCH:` / `NETCOVER_PROTOCOL_TYPE_INVALID:` 开头 → `"UNSUPPORTED"`
4. 否则调用 `classify_zero_candidate`（已 import）取值
5. **仅当 `terminal_eligible is True` 时才允许返回 `"COMPUTED_PASS"`**；若 `terminal_eligible is False` 而上面算出 `COMPUTED_PASS`，则降级为 `"COMPUTED_FAIL"`

## FAIL-2：`simulated_policy_only` 未产出

spec 要求 `SHADOW_SCENARIO` 下通过的结果必须带 `simulated_policy_only=True`（PRD §6.1：情景模拟通过不得被写成生产终闸通过）。主脑实测该字段**不存在**（`terminal_bits` 里查不到）。

**要求**：`GateDecision` 增加字段 `simulated_policy_only: bool`，`target_mode == "SHADOW_SCENARIO"` 时恒为 `True`，`LIVE_READINESS` 时恒为 `False`。`main()` 的输出 JSON 必须包含该字段。

## 必须新增的测试（追加，不改已有测试）

- `test_status_policy_blocked_in_live`：`LIVE_READINESS` + `capital_policy_pass=False` → `primary_status == "POLICY_BLOCKED"`。
- `test_status_inputs_unavailable_when_no_producer`：缺 `legacy_required_conjunction` → `primary_status == "INPUTS_UNAVAILABLE"`。
- `test_status_never_computed_pass_when_ineligible`：**参数化遍历十项**，任一置 False → `primary_status != "COMPUTED_PASS"`。这条是本轮的核心防回归。
- `test_shadow_scenario_marks_simulated_only`：`SHADOW_SCENARIO` → `simulated_policy_only is True`；`LIVE_READINESS` → `False`。
- `test_same_record_differs_by_target_mode`：同一条冲突记录在两种 mode 下 `primary_status` 必须不同。

## 本轮只许改这两个文件

`scripts/lp_rh_terminal_gate_v1_readonly.py` 与 `tests/test_lp_rh_terminal_gate_v1_readonly.py`。**十项合取式与 `TERMINAL_CONJUNCTS` 一个字都不许动**，AST 形状测试必须继续通过。

## 本轮验收

- [ ] 上面 5 个新测试全绿；原有 28 个测试仍全绿。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` 0 failed、14 skipped。
- [ ] 主脑复现脚本：十项逐一置 False 时 `primary_status` 无一为 `COMPUTED_PASS`。
