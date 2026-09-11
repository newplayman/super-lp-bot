# RH-02ck — T29：把 native gas 储备检查接进终闸（默认只记录不阻断）

## 背景

`scripts/lp_rh_gas_reserve_v1_readonly.py` 有完整的 T29 实现：

```
exit_gas_requirement_usd(gas_price_wei=, native_price_usd=, multiplier=3)
    平掉一个仓位需要的 gas（USD），x3 冗余。只算 close，不算 open。
native_reserve_gate(native_balance_wei=, ...)
    余额够不够。docstring 明写：未知余额一律判不足，绝不当成充足。
wrapped_does_not_count(weth_balance_wei=)
    WETH 不能顶 native ETH（T29 的核心主张）。
```

**被 runner / netcover 引用 0 次。** PRD 对账把 T29 标为
「已实现且有测试 ⚠ 尚未接入完整端到端主链」。

原料现成：`reports/lp_rh/gas_history.db` 的 `rh_gas_observations` 每 15 分钟
一条，含 `gas_price_wei` 与 `native_price_usd`——RH-02cg 刚刚为 gas 成本接过同一个库。

## 设计：能力就位，默认不阻断

Shadow 没有真实钱包，`native_balance_wei` 无处可取。按模块语义
「未知余额判不足」直接接进终闸，会让**每一个 episode 立刻不 eligible**，
Stage B 的数据积累当场停摆。

所以采用与 `--ledger-db` 相同的模式：**算、记录、默认不阻断**，
需要时用开关打开。Tiny Live 之前必须打开——那时钱是真的。

## 要做的事

### 1. runner 每轮算一次 gas 储备需求

`scripts/lp_rh_shadow_runner_v1_readonly.py`，在 RH-02cg 取 `observed_gas_usd`
的同一处（`run_episode` 开头，**整轮一次**，不要每步）：

- 从同一个 gas 库取最新一条的 `gas_price_wei` 与 `native_price_usd`
- 调 `exit_gas_requirement_usd(...)` 得到退出所需 USD
- 调 `native_reserve_gate(native_balance_wei=<见下>, ...)` 得到判定

`native_balance_wei` 的来源：`pool_meta.get("native_balance_wei")`。
**取不到就是 None**，`native_reserve_gate` 会判不足并给出理由——
这正是它的设计，不要绕过。

### 2. 新增 runner 参数 `enforce_gas_reserve`

```python
def run_episode(conn, *, strategy_episode, samples, ..., enforce_gas_reserve=False):
```

- `False`（默认）→ 结果**只记录**，不影响任何 conjunct，
  现有行为逐字不变（测试第 1 条钉这个）
- `True` → 判定不足时让 `position_and_exit_depth_pass` 失败，
  理由 `NATIVE_GAS_RESERVE_INSUFFICIENT:<模块给的 reason>`

**不要新增第十一个 conjunct**。终闸十项是 PRD 定义的，加一项要改 PRD；
gas 储备属于「能否退出」，并入 `position_and_exit_depth_pass` 是最小改动。

### 3. 记录到哪

- episode summary 加 `gas_reserve`：
  `{"required_usd": str|None, "sufficient": bool|None, "reason": str,
    "enforced": bool, "native_balance_known": bool}`
- `rh_economic_evaluations.cost_components_json` 里加
  `"exit_gas_reserve_usd"`（取不到写 `null`，**不是 0**）
- daemon 日志行打印 `gas_reserve=<sufficient|insufficient|unknown>`

### 4. WETH 不顶 native

`wrapped_does_not_count` 也要调用：若 `pool_meta` 里有 `weth_balance_wei`
而没有 `native_balance_wei`，结果里要能看出「有 WETH 但没有 native ETH」，
理由里带上它。这是 T29 的核心主张（PRD L1021），不能只算总额。

## 不许动

- 不要改 `lp_rh_gas_reserve_v1_readonly.py` 的任何行为，只调用。
- 不要改终闸十项的定义、`CONJUNCT_ORDER`、NetCover 公式。
- 不要改 RH-02cg 的 `observed_gas_usd` 逻辑（同一个库，不同用途）。
- 不要碰 `scripts/lp_rh_shadow_daemon_v1_readonly.py`、
  `scripts/lp_rh_reorg_detector_v1_readonly.py`（另一条线正在写）。
- 对 gas 库与 scanner.db **只读**（`mode=ro`）。
- **不要重启或 kill 任何进程**（采集器 1168725 / daemon 1789399 在跑生产）。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（追加到 `tests/test_lp_rh_shadow_runner_v1_readonly.py`）

复用 RH-02cg 那几条注入临时 gas 库的 fixture（`grep -n "rh02cg"` 找样板）。
**注意**：本会话已有七次「构造的输入进不去目标分支」，
写完请确认断言在开关关闭/打开两种情况下确实走了不同路径。

1. `enforce_gas_reserve=False`（默认）+ 余额未知 → episode 行为与现在**逐字相同**，
   `position_and_exit_depth_pass` 不受影响，但 summary 里
   `gas_reserve.sufficient is False`、`enforced is False`。
   ——**这条是向后兼容的保证**。
2. `enforce_gas_reserve=True` + 余额未知 →
   `position_and_exit_depth_pass` 为 False，reasons 含
   `NATIVE_GAS_RESERVE_INSUFFICIENT`。
3. `enforce_gas_reserve=True` + `native_balance_wei` 充足 → 该 conjunct 不因此失败。
4. `enforce_gas_reserve=True` + 只有 `weth_balance_wei` 没有 native →
   判不足，理由里能看出 WETH 不顶（T29 的主张）。
5. gas 库缺失 → `required_usd is None`，`reason` 说明原因，
   默认开关下 episode 照常跑完。
6. `cost_components_json` 里 `exit_gas_reserve_usd` 在取不到时是 `null` 而非 `0`。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿，新增 ≥6 条。
2. 全量 `python3 -m pytest tests/ -q --ignore=tests/test_lp_rh_reorg_detector_v1_readonly.py`
   通过（reorg 那个文件是另一条线的在建产物）。
3. `grep -n "native_reserve_gate\|wrapped_does_not_count" scripts/lp_rh_shadow_runner_v1_readonly.py`
   两者都有生产调用。
4. 用真实 gas 库算一次退出储备需求（只读），把数值贴进总结：
   ```
   python3 -c "
   import importlib.util, sqlite3
   s=importlib.util.spec_from_file_location('g','scripts/lp_rh_gas_reserve_v1_readonly.py')
   m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
   c=sqlite3.connect('file:reports/lp_rh/gas_history.db?mode=ro',uri=True)
   r=c.execute('SELECT gas_price_wei, native_price_usd FROM rh_gas_observations ORDER BY observed_at DESC LIMIT 1').fetchone()
   print('gas_price_wei=%s native_price_usd=%s' % r)
   print('exit reserve USD =', m.exit_gas_requirement_usd(gas_price_wei=r[0], native_price_usd=r[1]))
   "
   ```
5. `git status --short` 里只有
   `scripts/lp_rh_shadow_runner_v1_readonly.py` 和它的测试被改动。
