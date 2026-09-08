# RH-04b：单 CORE 池 Shadow Runner（把六层串成闭环，离线可测）

## 背景（一段）

PRD v1.1 §19 RH-04 要求「先一个 V3 CORE 池，从输入到结果跑通，再扩展第二个」。六层已全部就位且各有配对测试：`lp_rh_registry`（身份）、`lp_rh_capabilities`（能力）、`lp_rh_pool_probe`（池探针）、`lp_rh_store`（16 表）、`lp_rh_netcover_inputs`（装配，产出引擎接受的 9 键）、`lp_rh_terminal_gate`（十项合取）、`lp_rh_pnl`（NAV 账本）、`lp_rh_bucket_ledger`（原子预占）、`lp_rh_market_session`（时段/健康）。本包只做**编排**：把它们串成一条可重放的 Shadow 闭环，**不新增任何经济逻辑，不改任何已有文件**。

目标池（已 ATTESTED_SAME_BLOCK）：`0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`，token0=WETH(18)，token1=USDG(6)，fee=100。活库 `reports/lp_rh/scanner.db` 已积累 500+ 个 `rh_market_states` 样本。

## 新增文件

1. `scripts/lp_rh_shadow_runner_v1_readonly.py`（**≤ 250 行**，分次写）
   - 顶部仓库通行 sys.path 引导；import 上述模块，**只调用不修改**。
   - `dataclass ShadowStep`：`step_index, sample_time, price, terminal_eligible, primary_status, dominant_blocker, nav, net_pnl, hodl_value, reservation_granted`。
   - `run_episode(conn, *, strategy_episode, samples: Sequence[Mapping], position_usd: Decimal, horizon_hours: float, capital_usd: Decimal, target_mode: str, now_fn) -> list[ShadowStep]`：
     对每个样本依次：① 用 `lp_rh_netcover_inputs.assemble_rh_clmm_inputs` 装配；② 喂真实 `apply_netcover_gate`；③ 组装终闸十项输入并调 `lp_rh_terminal_gate.evaluate_terminal_gate`；④ 仅当 `terminal_eligible` 且尚无持仓时，调 `lp_rh_bucket_ledger.try_reserve` 做**虚拟**预占（bucket="CORE"）；⑤ 用 `lp_rh_pnl.compute_nav` / `net_pnl` / `hodl_benchmark` 记账；⑥ 把每步写入 `rh_gate_decisions` 与 `rh_position_marks`。
   - **虚拟资金隔离**：所有 reservation 的 `policy_version` 必须是 `"rh_50_30_20_proposed_v1"`，且 `target_mode="SHADOW_SCENARIO"` 时结果必须带 `simulated_policy_only=True`。**绝不触碰真实钱包、绝不签名广播。**
   - `load_samples_from_db(conn, *, pool, limit) -> list[dict]`：从 `rh_market_states` 读真实观测样本（`reference_mid` 转 Decimal），缺 `reference_mid` 的样本**跳过并计数**，不填 0。
   - `episode_summary(steps) -> dict`：`total_steps, eligible_steps, status_counts（五类主状态计数）, dominant_blocker_counts, first_eligible_at, nav_start, nav_end, net_pnl, hodl_delta, skipped_samples`。
   - `main()`：`--db <path>`（默认活库，**只读打开**）、`--samples <n>`、`--target-mode`、`--out <file>`。**必须用 `mode=ro` URI 打开活库**，Shadow 结果写到 `--out` 的 JSON，不得写活库。
2. `tests/test_lp_rh_shadow_runner_v1_readonly.py`（≤ 250 行），全部 `tmp_path` 临时库、注入合成样本，至少 14 个测试：
   - 端到端：5 个合成样本跑完，`steps` 长度为 5，每步都有 `primary_status`。
   - **零候选是合法结果（T60）**：全部样本都因 `netcover` 低于阈值而不合格 → `eligible_steps == 0` 且**不抛异常**，`summary.status_counts` 里 `COMPUTED_FAIL` 计数正确。
   - **缺输入不当经济失败（T32）**：样本缺 `fee_apr_pct` → 该步 `primary_status == "INPUTS_UNAVAILABLE"`，与 `COMPUTED_FAIL` 分开计数。
   - **政策阻挡（T25）**：`target_mode="LIVE_READINESS"` + 资本冲突 → 所有步 `primary_status == "POLICY_BLOCKED"`，`reservation_granted` 全为 False。
   - **SHADOW 标记**：`target_mode="SHADOW_SCENARIO"` 的结果每步带 `simulated_policy_only=True`。
   - **预占只发生一次**：连续多步合格时，只有第一步 `reservation_granted=True`（已有持仓不重复占用）。
   - **NAV 连续性**：`nav_end - nav_start - external_flow == net_pnl`（Decimal 精确）。
   - **HODL 基准不被重置**：episode 内多步的 `hodl_benchmark` 初始数量恒定（T41）。
   - `load_samples_from_db` 跳过 `reference_mid IS NULL` 的样本并在 summary 里计数，**不填 0**。
   - `rh_gate_decisions` 与 `rh_position_marks` 每步各写 1 行；重复 `decision_id` 抛 `IntegrityError`。
   - `main` 以 `mode=ro` 打开活库：断言用只读连接尝试写入会抛 `sqlite3.OperationalError`。

## 不许动什么

- **不改任何现有脚本/测试**；尤其不许碰 `scripts/lp_rh_collector_v1_readonly.py`（正在生产运行，已积累 2.5h 观测）。
- 不写活库 `reports/lp_rh/scanner.db`（只读打开）；不联网；不读 `.env*`；不签名不广播。
- 不新增经济公式，全部复用既有模块。
- 不要用 TaskCreate/TaskUpdate 工具；单次 Write/Edit ≤150 行。

## 验收标准

- [ ] `git status --short` 新增只有 1 脚本 + 1 测试；`git diff --stat` 为空。
- [ ] 脚本 ≤250 行；新测试 ≥14 个且全绿。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` 0 failed、14 skipped。
- [ ] `main --db reports/lp_rh/scanner.db --samples 20 --target-mode SHADOW_SCENARIO --out /tmp/ep.json` 退出码 0，且**活库行数不变**（跑前跑后 `rh_market_states` 计数相同）。
- [ ] `grep -nE "open_store\(.*scanner\.db" scripts/lp_rh_shadow_runner_v1_readonly.py` 不得出现可写打开活库。

## 验证命令

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
env -u PYTHONPATH /root/lp-bot/.venv/bin/python scripts/lp_rh_shadow_runner_v1_readonly.py --db reports/lp_rh/scanner.db --samples 20 --target-mode SHADOW_SCENARIO --out /tmp/ep.json && head -c 600 /tmp/ep.json
git diff --stat; git status --short | grep -E 'lp_rh_shadow'
```

---

# 第一轮作废（主脑 2026-09-08 10:0x）

第一轮 worker 在写 `run_episode` 时被工具错误（`Edit` 参数名不合法）打断，产出的 `scripts/lp_rh_shadow_runner_v1_readonly.py` **150 行且语法错误**——第 147 行 `insert_row(conn, "rh_gate_decisions", {` 的括号从未闭合，`ast.parse` 直接失败。该文件已被主脑删除，**不要试图修复它，从零重写**。

第二轮（补测试）也因把回合耗在调研接口上而未产出。

## 本轮重写要求（在原 spec 基础上补充）

1. **先写脚本再写测试**，脚本写完立刻 `ast.parse` 自检：
   ```bash
   /root/lp-bot/.venv/bin/python -c "import ast;ast.parse(open('scripts/lp_rh_shadow_runner_v1_readonly.py').read());print('OK')"
   ```
   自检不过就不要往下走。
2. **每次 Write 不超过 120 行**，写完立刻自检语法。宁可分四次写，不要一次写完导致被截断。
3. 上游模块的真实签名（**已由主脑核实，直接用，不要再花回合调研**）：
   - `lp_rh_netcover_inputs_v1_readonly.assemble_rh_clmm_inputs(evidence, *, position_usd: Decimal, horizon_hours: float) -> dict`
   - `lp_rh_netcover_inputs_v1_readonly.classify_zero_candidate(record) -> str`
   - `lp_netcover_engine_v1_readonly.apply_netcover_gate(records, *, reward_haircut=..., lvr_coefficient=...) -> list[dict]`
   - `lp_rh_terminal_gate_v1_readonly.evaluate_terminal_gate(record, *, target_mode, now) -> GateDecision`（字段 `terminal_eligible / primary_status / dominant_blocker / terminal_bits / simulated_policy_only / decision_id`）
   - `lp_rh_bucket_ledger_v1_readonly.try_reserve(conn, *, intent_id, bucket, amount_usd: Decimal, capital_usd: Decimal, policy_version=POLICY_ID, now: str) -> dict`（返回含 `granted`）
   - `lp_rh_pnl_v1_readonly.compute_nav(*, wallet, lp_principal, accrued_fees, verified_rewards, liabilities) -> Decimal`
   - `lp_rh_pnl_v1_readonly.net_pnl(nav_t1, nav_t0, external_net_flow) -> Decimal`
   - `lp_rh_pnl_v1_readonly.hodl_benchmark(*, initial_token0_raw, initial_token1_raw, dec0, dec1, price_t1_token1_per_token0, quote_usd_per_token1) -> Decimal`
   - `lp_rh_store_v1_readonly.open_store(path, *, read_only=False)` / `migrate(conn)` / `insert_row(conn, table, row)`
4. **应计费用的正确来源**（主脑 09:1x 实测，见 `reports/rh_pivot/20260907T124500Z/RH-05-research/POSITION_FEE_GROWTH_20260908.md`）：Shadow 账本的 `accrued_fees` 应按
   `L_position × Δ(feeGrowthGlobal_token) / 2**128` 累加，**不得**按 TVL 占比分摊全池费用。样本里若带 `fee_growth_global_0` / `fee_growth_global_1` 就用增量法；没有则 `accrued_fees` 记 `None` 并计入 `skipped_samples`，**不填 0**。
