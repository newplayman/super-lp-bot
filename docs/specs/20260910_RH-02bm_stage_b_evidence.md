# RH-02bm — Stage B 三个证据不许再硬编码成「零」

## 缺陷（已由主脑核实，不要重新调研）

`scripts/lp_rh_readiness_v1_readonly.py` 第 758-760 行：

```python
state["stage_b"] = stage_b_status(
    days_covered=span_days, weekends_covered=None, unexplained_ledger_diffs=0,
    invariant_violations=invariant_violations, missed_risk_events=0)
```

`stage_b_status()`（同文件 L206-231）的接口本身是**对的**：
- 传 `None` → 追加 `*_UNAVAILABLE` blocker（fail-close，正确）
- 传非零 → 追加 `*` blocker（正确）
- 传 `0` → **视为「已查证、确实为零」而放行**

但调用处把 `unexplained_ledger_diffs` 和 `missed_risk_events` **写死成 `0`**，
仓库里根本没有任何代码去查过这两件事。这是本仓库已确认 24 例的
「静默假绿」缺陷族的第 25、26 例：不抛异常、闸门照常出结论、结论是假的。

**当前之所以看不出来**，是因为 Stage B 还被 `DAYS_COVERED_INSUFFICIENT`
（1/14 天）挡着。一旦跑满 14 天，这两个假 `0` 会让 Stage B 直接放行。

`weekends_covered=None` 行为上是安全的（已阻断），但**阻断理由是错的**——
报的是「周末覆盖不足」，真实情况是「从来没数过周末」。也要一并修。

`invariant_violations` 已经在上一轮接了真实审计（`audit_invariant_violations`），
**不要动它**，它是本包三个新函数的样板。

## 要做的事

在 `scripts/lp_rh_readiness_v1_readonly.py` 里**新增三个只读审计函数**，
并把 `_build_state`（L757-760）改为使用它们的返回值。

三个函数一律遵守：**查不到证据就返回 `None`，绝不返回 `0`。**
返回 dict，形如 `audit_invariant_violations` 的风格
（含 `count` 或等价字段、`checks_performed`、`reason`）。

### 1. `audit_weekends_covered(conn, *, asset_address) -> dict`

数 `rh_market_states` 里 `asset_address` 匹配（**用 `LOWER(asset_address) = LOWER(?)`**，
本仓库踩过 EIP-55 大小写的坑）的样本覆盖了多少个**完整周末日**。

- 「完整」判据：该自然日（UTC）内样本数 ≥ 该日应有样本数的 90%
  （应有 = 86400/interval；`interval` 从函数参数传入，默认 15）。
  首末不完整的自然日按实际时间跨度折算，不要一刀切判不完整。
- 周六和周日**各算一个周末日**；返回 `weekends_covered` = 完整周末日的个数。
- 表不存在或该资产 0 行 → 返回 `weekends_covered=None`，`reason` 写清楚。

### 2. `audit_unexplained_ledger_diffs(conn) -> dict`

查 `rh_journal` 的借贷是否配平。

- 表不存在 **或表为 0 行** → `count=None`，`reason="NO_JOURNAL_EVIDENCE"`。
  **这是本包最重要的一条**：没有账本就是「未知」，不是「零差异」。
- 有行时：按 `amount_raw` 汇总，借方合计与贷方合计不等的条目计入 `count`；
  `debit_account` / `credit_account` 为空的条目也计入。

### 3. `audit_missed_risk_events(conn) -> dict`

查「该拦却没拦」的证据。

- 判据：`rh_gate_decisions` 中 `primary_status = 'COMPUTED_PASS'`，
  但同一 `decided_at`（取最近的 `rh_market_states.sample_time <= decided_at`）
  对应的样本 `health_flags_json` 非空且非 `[]`。
- `rh_gate_decisions` 表不存在 **或为 0 行** → `count=None`，
  `reason="NO_GATE_DECISION_EVIDENCE"`。**同样不许返回 0。**

### 4. 接线

`_build_state` 里：

```python
wk = audit_weekends_covered(conn, asset_address=asset_address)
led = audit_unexplained_ledger_diffs(conn)
mre = audit_missed_risk_events(conn)
state["weekends_audit"] = wk
state["ledger_diffs_audit"] = led
state["missed_risk_events_audit"] = mre
state["stage_b"] = stage_b_status(
    days_covered=span_days,
    weekends_covered=wk.get("weekends_covered"),
    unexplained_ledger_diffs=led.get("count"),
    invariant_violations=invariant_violations,
    missed_risk_events=mre.get("count"))
```

（`invariant_violations` 保持原样传入，不要改。）

## 不许动

- **不要改 `stage_b_status()` 本身**——它的 fail-close 语义已经是对的。
- 不要改 `audit_invariant_violations` / `stage_a_status` / `coverage_for_asset`。
- 不要改任何 `.db` 文件，不要写任何数据。全部只读 SQL（`SELECT` only）。
- **不要执行任何 git 命令**（不要 add / commit / checkout / stash）——入库是主脑裁决后的动作。
- 单次 Write/Edit ≤150 行或 6000 字符，更大的改动分次做。
- 不要整读这个 800+ 行的文件；用 `sed -n 'X,Yp'` 读需要的段
  （关键段：L196-231 `stage_b_status`、L538-620 `audit_invariant_violations` 样板、
  L698-765 `_build_state`）。

## 测试（新增到 `tests/test_lp_rh_readiness_v1_readonly.py`）

用**内存 SQLite**（`sqlite3.connect(":memory:")`）自建表，不要碰真实库。
每条都必须真能触发被测分支——本仓库已四次因为「构造的输入进不去目标分支」
而写出永远绿的测试，务必先确认断言在**修复前会失败**。

1. `rh_journal` 表不存在 → `unexplained_ledger_diffs is None`，
   Stage B blockers 含 `UNEXPLAINED_LEDGER_DIFFS_UNAVAILABLE`。
2. `rh_journal` 存在但 0 行 → 同上（**这条最关键：空表 ≠ 零差异**）。
3. `rh_journal` 有一条借贷不平的行 → `count == 1`，blockers 含 `UNEXPLAINED_LEDGER_DIFFS`。
4. `rh_gate_decisions` 为 0 行 → `missed_risk_events is None`，
   blockers 含 `MISSED_RISK_EVENTS_UNAVAILABLE`。
5. 构造一条 `COMPUTED_PASS` + 同期样本 `health_flags_json='["CHAIN_DEGRADED"]'`
   → `count >= 1`，blockers 含 `MISSED_RISK_EVENTS`。
6. 造两个完整周末日的样本（周六 + 周日各 ≥90% 密度）→ `weekends_covered == 2`。
7. 周六只有 10 个样本（远低于 90%）→ 该日不计入，`weekends_covered` 不含它。
8. 地址用 EIP-55 混合大小写传入，仍能匹配到小写存储的行（防大小写回归）。

## 验收标准（主脑会逐条查）

1. `grep -n "unexplained_ledger_diffs=0\|missed_risk_events=0" scripts/lp_rh_readiness_v1_readonly.py`
   **无输出**。
2. 在**真实库**上跑
   `python3 scripts/lp_rh_readiness_v1_readonly.py --db reports/lp_rh/scanner.db --out /tmp/x.md --asset-address 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`，
   Stage B 的 blockers 里**出现** `UNEXPLAINED_LEDGER_DIFFS_UNAVAILABLE` 和
   `MISSED_RISK_EVENTS_UNAVAILABLE`（因为真实库这两张表都是 0 行）。
   ——这条是本包的核心证据：修之前它们不出现，修之后必须出现。
3. 全量 `python3 -m pytest tests/ -q` 通过，且新增测试条数 ≥ 8。
4. `git status --short` 里只有 `scripts/lp_rh_readiness_v1_readonly.py` 和
   `tests/test_lp_rh_readiness_v1_readonly.py` 两个文件被改动。
