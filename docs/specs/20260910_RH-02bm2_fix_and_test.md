# RH-02bm-2 — 修一个已定位的崩溃 + 补齐 RH-02bm 的测试

## 背景

上一个 worker 已经把三个只读审计函数写进
`scripts/lp_rh_readiness_v1_readonly.py`（工作区已有 +215 行改动，**不要回退它**），
但**测试还没写**，而且其中一个函数有一处会崩的写法。

## 第一件事：修这个崩溃（位置已定位，不用找）

`audit_weekends_covered()` 里有三处 `datetime.time.min`，例如：

```python
end_of_day = datetime.combine(day + timedelta(days=1),
                              datetime.time.min,
                              tzinfo=times[0].tzinfo)
```

`datetime` 是从 `from datetime import datetime` 导入的**类**，
`datetime.time` 是实例方法，`datetime.time.min` 抛
`AttributeError: 'method_descriptor' object has no attribute 'min'`。

主脑已在真实库上实测确认：

```
audit_weekends_covered(...) ->
  {'weekends_covered': None, 'checks_performed': [],
   'reason': "audit_exception:'method_descriptor' object has no attribute 'min'"}
```

函数外层的 `except Exception` 把这个**代码 bug 吞成了「无证据」**，
于是 `weekends_covered` 永远是 `None`，Stage B 的周末检查永远过不去，
而报出来的理由是假的。本仓库把这类缺陷叫「静默假绿/假红」，今晚已确认 26 例。

**改法**（用最不容易再出错的写法，不要用 `datetime.time.min`，
也不要 `import time`——那个名字在本文件里会引起混淆）：

```python
def _day_start(day, tzinfo):
    """该 UTC 自然日的 00:00:00。"""
    return datetime(day.year, day.month, day.day, tzinfo=tzinfo)
```

然后：
- `first_day` 分支：`span_secs = (_day_start(day + timedelta(days=1), times[0].tzinfo) - times[0]).total_seconds()`
- `last_day` 分支：`span_secs = (times[-1] - _day_start(day, times[-1].tzinfo)).total_seconds()`

## 第二件事：补测试

追加到 `tests/test_lp_rh_readiness_v1_readonly.py`。
全部用**内存 SQLite**（`sqlite3.connect(":memory:")`）自建表，不要碰真实库。

**每条断言都必须真能触发目标分支。** 本仓库已四次写出「构造的输入进不去
被测分支、于是测试永远绿」的假测试，写完请自己确认一遍。

1. `rh_journal` 表不存在 → `audit_unexplained_ledger_diffs(conn)["count"] is None`，
   Stage B blockers 含 `UNEXPLAINED_LEDGER_DIFFS_UNAVAILABLE`。
2. `rh_journal` 存在但 **0 行** → 同上。
   **这条最关键：空账本是「未知」，不是「零差异」。**
3. `rh_journal` 一条借贷不平的记录 → `count == 1`，
   blockers 含 `UNEXPLAINED_LEDGER_DIFFS`。
   （真实列名：`event_id, idempotency_key, account_debit, account_credit,
   asset, amount_raw, is_external_flow, ref_json, booked_at`——已核实，照抄即可。）
4. `rh_gate_decisions` 0 行 → `audit_missed_risk_events(conn)["count"] is None`，
   blockers 含 `MISSED_RISK_EVENTS_UNAVAILABLE`。
5. 一条 `primary_status='COMPUTED_PASS'` 的决策 + 同期
   `rh_market_states.health_flags_json='["CHAIN_DEGRADED"]'` → `count >= 1`，
   blockers 含 `MISSED_RISK_EVENTS`。
   （真实列名：`decision_id, candidate_key, target_mode, primary_status,
   terminal_bits_json, dominant_blocker, reasons_json, snapshot_ids_json,
   decided_at, derived_block_hash, derived_block_number`。）
6. 造完整的周六 + 周日样本（各 ≥90% 密度，间隔 15s）→ `weekends_covered == 2`。
7. 周六只有 10 个样本 → 该日不计入。
8. **首/末不完整日的折算分支必须被真实执行到**：造一个从周六 12:00 开始、
   到周日 12:00 结束的样本序列，断言 `weekends_covered` 有确定的数值
   且 **`reason` 不以 `audit_exception:` 开头**。
   ——这条专门防上面那个崩溃回归，**必须有**。
9. 地址用 EIP-55 混合大小写传入，仍能匹配小写存储的行。

## 不许动

- **不要回退工作区里已有的 +215 行改动**，只在其基础上修那三处 `datetime.time.min`。
- 不要改 `stage_b_status()` 本身——它的 fail-close 语义已经是对的。
- 不要改 `stage_a_status` / `coverage_for_asset` / `audit_invariant_violations` /
  `audit_key_field_health`。
- 不要碰 `scripts/lp_rh_synthetic_evidence_v1.py`（另一个 job 在处理它）。
- 不要动任何 `.db` 文件，全部只读 SQL。
- **不要执行任何 git 命令**（不要 add / commit / checkout / stash / diff --（写））。
  入库是主脑裁决后的动作。
- 单次 Write/Edit ≤150 行或 6000 字符，分次写。
- 不要整读这个 900+ 行的文件；用 `grep -n` 定位、`sed -n 'X,Yp'` 读片段。

## 验收标准（主脑会逐条查）

1. 在**真实库**上跑：
   ```
   python3 -c "
   import importlib.util,sqlite3
   s=importlib.util.spec_from_file_location('r','scripts/lp_rh_readiness_v1_readonly.py')
   m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
   c=sqlite3.connect('file:reports/lp_rh/scanner.db?mode=ro',uri=True)
   r=m.audit_weekends_covered(c, asset_address='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca')
   print(r['weekends_covered'], r['reason'])
   "
   ```
   输出的 `reason` **必须是 `OK`**，`weekends_covered` **必须是一个整数**（不是 None）。
   ——这条是本包核心证据。
2. 真实库上跑 readiness：
   ```
   python3 scripts/lp_rh_readiness_v1_readonly.py --db reports/lp_rh/scanner.db \
       --out /tmp/rdy_bm2.md --asset-address 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
   ```
   Stage B blockers 里**出现** `UNEXPLAINED_LEDGER_DIFFS_UNAVAILABLE` 和
   `MISSED_RISK_EVENTS_UNAVAILABLE`（真实库这两张表都是 0 行）。
3. `grep -n "datetime.time.min" scripts/lp_rh_readiness_v1_readonly.py` **无输出**。
4. `grep -n "unexplained_ledger_diffs=0\|missed_risk_events=0" scripts/lp_rh_readiness_v1_readonly.py` **无输出**。
5. `python3 -m pytest tests/test_lp_rh_readiness_v1_readonly.py -q` 全绿，新增 ≥9 条。
6. `git status --short` 里只有 `scripts/lp_rh_readiness_v1_readonly.py` 和
   `tests/test_lp_rh_readiness_v1_readonly.py` 被改动
   （`scripts/lp_rh_synthetic_evidence_v1.py` 是另一个 job 的新文件，会以 `??` 出现，正常）。
