# RH-02by — 虚拟开仓记进 `rh_journal`（双边记账的第一笔）

## 背景

`rh_journal` 至今 **0 行**。它的 writer `book_journal_event()` 存在
（`scripts/lp_rh_pnl_v1_readonly.py:136-153`），但**只有测试在调**——
`grep -rn "book_journal_event" scripts/` 除了定义本身没有任何生产调用。

PRD Stage B 要求「零未解释账本差异」，那条验收的数据源就是这张表
（依据 `reports/AUDIT_shadow_ledger_writer_gap_20260910.md`）。表是空的，
`audit_unexplained_ledger_diffs` 就只能返回 `None`，Stage B 永远卡在
`UNEXPLAINED_LEDGER_DIFFS_UNAVAILABLE`。

commit `f1ab502` 刚让 `rh_shadow_positions` 在虚拟开仓时落一行。
**本包在同一处记对应的两条 journal 分录。** 费用、gas、平仓是后续包，本包不做。

## 唯一任务：开仓时记两条分录

### 写在哪

`scripts/lp_rh_shadow_runner_v1_readonly.py`，就在
`insert_row(conn, "rh_shadow_positions", {...})` **成功之后**、
`position_row_written = True` 之前或之后（同一个 `if pool_key:` 块内）。
用 `grep -n "rh_shadow_positions" ` 定位。

条件与 position 行完全一致：拿不到 `pool_key` 就两者都不写。

### 记什么

虚拟建仓 = 资产从钱包转入 LP 头寸，两腿各一条：

```python
book_journal_event(
    conn,
    event_id=f"{strategy_episode}-open",
    idempotency_key=f"{strategy_episode}-open-token0",
    debit="LP_POSITION_TOKEN0",
    credit="WALLET_TOKEN0",
    asset=<token0 地址>,
    amount_raw=inv_cached.amount0_raw,
    is_external_flow=False,
    ref={"position_id": position_id, "leg": "token0",
         "opened_at": pending_position_open_at},
    now=pending_position_open_at,
)
```

token1 同理（`-open-token1` / `LP_POSITION_TOKEN1` / `WALLET_TOKEN1` /
`inv_cached.amount1_raw`）。

**`is_external_flow=False`**：这是内部腾挪，不是外部注资。
PRD D03 要求实际 PnL 只用 NAV + 外部现金流，把内部转移标成外部流会污染 PnL 归因。

### token0 / token1 地址从哪来

```python
tok0 = pool_meta.get("token0") if pool_meta else None
tok1 = pool_meta.get("token1") if pool_meta else None
```

**两个都拿不到就不记 journal**（但 `rh_shadow_positions` 那行照写——
它不依赖 token 地址），并在 step reasons 里加
`JOURNAL_NOT_BOOKED:NO_TOKEN_ADDRESSES`。
**绝不用池地址、空串或占位符顶替 asset 字段。**

先跑这条确认生产 pool_meta 里到底有没有这两个键，把输出贴进你的总结：

```bash
python3 -c "
import json; m=json.load(open('reports/lp_rh/pool_meta.json'))
print('token0=',repr(m.get('token0')),' token1=',repr(m.get('token1')))
print('keys:', sorted(m.keys()))"
```

若生产 pool_meta 里没有这两个键，**不要去改 pool_meta**，也不要从别处推导；
按上面的 fail-close 走，并在总结里明确写出「生产配置当前不会记 journal，
原因是 pool_meta 缺 token0/token1」——这个结论本身就是有价值的产出。

### 三条硬性语义

1. **不要捕获 `sqlite3.IntegrityError`。** `book_journal_event` 的 docstring
   写明重复的 `idempotency_key` 会抛（RH-INV-13：任何流水不得重复入账）。
   跨轮重跑的冲突交给 daemon 层（`_run_episode_persisted`，commit `330ab3e`），
   与 `rh_economic_evaluations` / `rh_shadow_positions` 一致。
2. 每个 episode 至多两条（复用已有的 `position_row_written` 标志，
   **不要新增第二个状态变量**）。
3. `amount_raw` 直接传 `inv_cached.amount0_raw`（Decimal），
   `book_journal_event` 内部会做 `_decimal_to_text`。**不要自己 str()、不要 int() 截断。**

## 不许动

- 不要改 `book_journal_event` 本身，也不要改 `scripts/lp_rh_pnl_v1_readonly.py`。
- 不要改 NAV / HODL / fee 计算，不要改 `inventory_for_position`。
- 不要改已有四个 writer（gate_decisions / position_marks /
  economic_evaluations / shadow_positions）的字段。
- 不要碰 `scripts/lp_rh_terminal_gate_v1_readonly.py`（另一条线正在改）。
- 不要碰 `scripts/lp_rh_readiness_v1_readonly.py`、
  `scripts/lp_rh_pool_attestation_backfill_v1.py`（工作区有别的线的改动）。
- **不要真的写 `reports/lp_rh/scanner.db`**；测试用内存库或 `tmp_path`。
- **不要重启或 kill 任何 daemon/collector 进程。**
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## `rh_journal` 真实列（照抄——本会话已有四个 worker 猜错 schema）

```
NOT NULL: event_id, account_debit, account_credit, asset, amount_raw,
          is_external_flow, booked_at
全部    : event_id, idempotency_key, account_debit, account_credit, asset,
          amount_raw, is_external_flow, ref_json, booked_at
```

`insert_row()` 会**静默丢弃**表里没有的列名，猜错只会在很久之后
以 NOT NULL 失败的形式露头。

## 测试（追加到 `tests/test_lp_rh_shadow_runner_v1_readonly.py`）

复用该文件里 RH-02bu 那几条测试的 fixture 风格（`grep -n "rh02bu2"` 找样板）。

1. 有 granted 步且 pool_meta 带 token0/token1 → `rh_journal` 恰好 **2 行**。
2. 承 1：两行的 `asset` 分别等于 pool_meta 的 token0 / token1，
   `amount_raw` 分别等于 `inv.amount0_raw` / `inv.amount1_raw`（逐字相等）。
3. 承 1：两行的 `is_external_flow` 都是 `0`。
   **这条重要**：内部腾挪被标成外部流会污染 PnL 归因（PRD D03）。
4. 承 1：两行的 `idempotency_key` 不同（否则第二条会抛 IntegrityError）。
5. 没有 granted 步 → `rh_journal` **0 行**。
6. pool_meta 缺 token0/token1 → `rh_journal` 0 行，
   但 `rh_shadow_positions` **仍有 1 行**，且 step reasons 含
   `JOURNAL_NOT_BOOKED:NO_TOKEN_ADDRESSES`。
   ——这条证明两者的 fail-close 是独立的。
7. `audit_unexplained_ledger_diffs`（在 `lp_rh_readiness_v1_readonly.py` 里，
   **只调用、不修改**）对这两条平衡分录返回 `count == 0`，不是 `None`。
   ——这条证明落库的数据真能被 Stage B 的审计消费。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿，新增 ≥7 条。
2. `grep -n "book_journal_event" scripts/lp_rh_shadow_runner_v1_readonly.py`
   能看到生产调用。
3. `grep -n "IntegrityError" scripts/lp_rh_shadow_runner_v1_readonly.py` **无输出**。
4. 全量 `python3 -m pytest tests/ -q` 通过。
5. `git status --short` 里只有
   `scripts/lp_rh_shadow_runner_v1_readonly.py` 和
   `tests/test_lp_rh_shadow_runner_v1_readonly.py` 被改动。
