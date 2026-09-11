# RH-02ci — 手续费累积记进 journal（PnL 归因的另一半）

## 背景

`rh_journal` 现在只有开仓分录，每个 episode 两条：

```
LP_POSITION_TOKEN0 / WALLET_TOKEN0
LP_POSITION_TOKEN1 / WALLET_TOKEN1
```

runner 每一步都在累加手续费（`accrued += fee_usd`，约 L703），
`compute_nav` 用它算 NAV，`rh_position_marks.accrued_fee` 也存了逐步值。
但**账本里没有任何一条手续费分录**——NAV 涨了，账本说不出钱从哪来。

PRD D03 要求实际 PnL 只由 NAV 与外部现金流定义，IL/LVR/markout 只是归因。
账本要能解释 NAV 的变化，缺了手续费这一项就解释不了。

## 唯一任务：episode 结束时记一条手续费分录

### 写在哪

`scripts/lp_rh_shadow_runner_v1_readonly.py`，在 `if position_open:` 那个
episode 收尾块里（搜 `release_now`，RH-02ce 在那里调 `release()`），
**与释放 reservation 同一处**。

### 记什么

```python
book_journal_event(
    conn,
    event_id=f"{strategy_episode}-fees",
    idempotency_key=f"{strategy_episode}-fees",
    debit="LP_FEES_RECEIVABLE",
    credit="LP_FEE_INCOME",
    asset=<quote 资产：用 token1 地址>,
    amount_raw=<accrued 的 raw 形式，见下>,
    is_external_flow=False,
    ref={"position_id": f"rh-shadow-{strategy_episode}",
         "kind": "fee_accrual",
         "steps": <本轮步数>,
         "accrued_usd": str(accrued)},
    now=<episode 最后一步时间，取不到用 now_fn()>,
)
```

### 三条硬性语义

1. **`accrued == 0` 时不要记。** 零手续费不是一笔交易，记一条零额分录
   只会污染账本。在 step reasons 或 summary 里留一句即可。

2. **`amount_raw` 的量纲**：`accrued` 是 **USD**，而 `rh_journal.amount_raw`
   存的是链上原始整数（开仓那两条存的是 `inv.amount0_raw` / `amount1_raw`）。
   `quote_usd_per_token1` 把 token1 换算成 USD，所以
   **USD → token1 raw = accrued / quote * 10**dec1**。
   拿不到 `quote` 或 `dec1` 就**不要记这条**，并在 reasons 里写
   `FEE_JOURNAL_NOT_BOOKED:NO_QUOTE_OR_DEC1` —— 绝不用 1.0 兜底
   （PRD:651 明确禁止把 USDG 强制按 $1 估值，本仓库为此专门做过 fail-close）。

3. **不要捕获 `sqlite3.IntegrityError`**：同一 episode 重放会撞
   `event_id` 主键，交给 daemon 层处理，与其它 writer 一致。

### 借贷是否平衡

`audit_unexplained_ledger_diffs`（在 `lp_rh_readiness_v1_readonly.py`，
**只调用、不修改**）按 `event_id` 分组检查借贷配平。这一条是单腿分录
（一个 debit 账户 + 一个 credit 账户 + 同一金额），与开仓那两条同构，
应当继续 `count == 0`。**测试里要验证这一点**。

## 不许动

- 不要改 NAV / HODL / fee 的计算，不要改 `accrued` 的累加逻辑。
- 不要改开仓那两条分录的任何字段。
- 不要改 `release()` 的调用（RH-02ce 刚接线）。
- 不要改 `book_journal_event`（`scripts/lp_rh_pnl_v1_readonly.py`）。
- 不要碰 `scripts/lp_rh_shadow_daemon_v1_readonly.py`、
  `scripts/lp_rh_readiness_v1_readonly.py`、
  `scripts/lp_rh_reservation_cleanup_v1.py`（另一条线正在写）。
- **不要真的写 `reports/lp_rh/scanner.db`**；测试用内存库或 `tmp_path`。
- **不要重启或 kill 任何进程**（采集器 1168725 / daemon 1789399 在跑生产）。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（追加到 `tests/test_lp_rh_shadow_runner_v1_readonly.py`）

复用该文件里 RH-02by 那几条 journal 测试的 fixture 风格（`grep -n "rh02by"`）。

1. 有 granted 步、`accrued > 0` 的 episode → `rh_journal` 比开仓时**多一条**，
   `event_id` 以 `-fees` 结尾，账户为 `LP_FEES_RECEIVABLE` / `LP_FEE_INCOME`。
2. 承 1：`ref_json` 里 `kind == "fee_accrual"`，`accrued_usd` 与该 episode
   的最终 accrued 一致。
3. `accrued == 0` → **不记这条**，journal 仍只有开仓两条。
4. `pool_meta` 缺 `quote_usd_per_token1` 或 `dec1` → 不记，
   step reasons 或 summary 含 `FEE_JOURNAL_NOT_BOOKED:NO_QUOTE_OR_DEC1`，
   且开仓那两条**照常存在**（两者的 fail-close 相互独立）。
5. `audit_unexplained_ledger_diffs` 对含手续费分录的账本返回 `count == 0`
   （借贷仍配平）。
6. 没有 granted 步的 episode → journal 0 条（不记手续费，因为没开仓）。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿，新增 ≥6 条。
2. 全量 `python3 -m pytest tests/ -q` 通过。
3. `grep -n "LP_FEE_INCOME" scripts/lp_rh_shadow_runner_v1_readonly.py` 有输出。
4. `grep -n "IntegrityError" scripts/lp_rh_shadow_runner_v1_readonly.py` **无输出**。
5. `git status --short` 里只有
   `scripts/lp_rh_shadow_runner_v1_readonly.py` 和它的测试被改动。
