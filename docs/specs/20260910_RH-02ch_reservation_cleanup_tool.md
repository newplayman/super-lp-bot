# RH-02ch — 清理工具：历史 reservation 把资金桶永久堵死了

## 现状（生产，已实测）

`bc780ec` 让 bucket active cap 真正生效之后，立刻暴露一个死锁：

```
rh_bucket_reservations   23 条 PENDING，released_at 全为 NULL，合计 23000 USD
CORE bucket_active_cap   4250 USD
=> room = -18750，所有新 reservation 被拒
```

daemon 重启后第一轮的日志证实了：

```
rh-shadow-20260910200146-0: ... pos:0, journal:0, resv:0, reservations_synced:23
```

`resv:0` —— 一条都没批准。这是**正确行为**（cap 确实超了），但形成死锁：

```
历史占用堵死 cap
  -> 没有新 reservation
  -> 没有 episode 能开仓
  -> release() 无从触发（它只释放本轮 granted 的那条）
  -> 历史占用永远留着
```

这 23 条是 `bc780ec` 之前、cap 检查失效期间累积的**脏数据**，
对应的 episode 早已结束，虚拟仓位实际上并不存在。

## 唯一任务：写清理工具，**不要执行它**

新建 `scripts/lp_rh_reservation_cleanup_v1.py`。

```
python3 scripts/lp_rh_reservation_cleanup_v1.py \
    [--db reports/lp_rh/scanner.db] \
    [--older-than-hours 1] \
    [--apply]                      # 不给就是 dry-run
```

### 判据：什么算「孤儿 reservation」

一条 PENDING 且 `released_at IS NULL` 的 reservation 是孤儿，当且仅当：

1. 它的 `intent_id` 前缀里的 episode，在 `rh_shadow_positions` 里
   **没有对应的未平仓记录**，**或者**
2. 它的 `created_at` 早于 `--older-than-hours` 小时前

**两个条件都要能单独判定并分别计数**，报告里分开列。

**绝不要只按时间清理**——那会误伤一个刚开仓、正常持有的 reservation。
第 1 条是语义判据，第 2 条是兜底。

### dry-run（默认）

打印：
- 总 PENDING 条数与金额
- 判为孤儿的条数与金额，**逐条列出** intent_id / amount / created_at / 判据
- 清理后的 `reserved_total` 与 `room`（用 `bucket_active_cap(capital_usd, bucket)`，
  `capital_usd` 加一个 `--capital-usd` 参数，默认 10000）
- **明确一行**：`DRY-RUN: 未修改任何数据，加 --apply 才会写库`

退出码 0。

### `--apply`

用 `release(conn, intent_id, now=..., reason="ORPHANED_PRE_CAP_FIX")`
**逐条释放**，不要直接 `DELETE` 或 `UPDATE`：

- `release()` 是账本的既有语义，走它才能保留 `released_at` 与 `reason` 的痕迹
- **删除会毁掉证据**——这 23 条是「cap 曾经失效」的实物证据，
  本仓库的纪律是保留痕迹而非抹去（`git revert` 而非 `reset` 是同一原则）
- `release()` 返回 False（找不到）时计数并继续，最后汇总

写库前先打印将要释放的清单并要求 `--apply` 已给出；
写完后重新计算并打印 `reserved_total` / `room`，证明死锁解除。

### 幂等

重复跑 `--apply` 必须安全：已释放的（`released_at IS NOT NULL`）
不再算孤儿，第二次跑应报告 0 条待释放。

## 不许动

- **不要执行 `--apply`**。本包只交付工具；是否清理生产数据由用户决定。
  你可以（也应该）跑 dry-run 并把输出贴进总结。
- 不要改 `release()` / `try_reserve()` / `reserved_total()` /
  `bucket_active_cap()` 的任何行为。
- 不要改 `scripts/lp_rh_shadow_daemon_v1_readonly.py` /
  `scripts/lp_rh_shadow_runner_v1_readonly.py`。
- 测试一律用 `tmp_path`；对生产库只允许 `mode=ro` 读。
- **不要重启或 kill 任何进程**（采集器 1168725 / daemon 1789399 在跑生产）。
- **不要执行任何 git 命令。**
- 单次 Write ≤150 行或 6000 字符。

## 表的真实列（照抄）

```
rh_bucket_reservations
  intent_id (PK), policy_version, bucket, amount_usd, status,
  created_at, released_at

rh_shadow_positions
  strategy_episode, position_id, pool_key, profile, bucket,
  initial_token0_raw, initial_token1_raw, tick_lower, tick_upper,
  virtual_liquidity_raw, opened_at, closed_at
  PK (strategy_episode, position_id)
```

intent_id 形如 `rh-shadow-{episode}-{step_index}`。

## 测试（`tests/test_lp_rh_reservation_cleanup_v1_readonly.py`）

1. 3 条孤儿（对应 episode 无 position 记录）→ dry-run 报 3 条，
   **库未被修改**（跑前跑后 `SELECT COUNT(*) WHERE released_at IS NULL` 相同）。
2. `--apply` 后这 3 条的 `released_at` 非空、`reason` 为 `ORPHANED_PRE_CAP_FIX`，
   且行**仍然存在**（不是被删除）。
3. 一条有对应未平仓 position 的 reservation → **不算孤儿**，不被释放。
   ——这条防误伤，最重要。
4. 一条很老但有对应 position 的 → 按第 1 条判据不算孤儿
   （证明语义判据优先于时间判据）。
5. 幂等：连续两次 `--apply`，第二次报 0 条待释放，数据不变。
6. 清理后 `reserved_total` 下降、`room` 转正（断言具体数值关系，不是硬编码）。
7. `release()` 找不到 intent 时计数并继续，不中断整批。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_reservation_cleanup_v1_readonly.py -q`
   全绿，条数 ≥ 7。
2. 在**真实库**上跑 dry-run（**不加 --apply**）：
   ```
   python3 scripts/lp_rh_reservation_cleanup_v1.py --db reports/lp_rh/scanner.db
   ```
   报出 23 条左右 PENDING、判为孤儿的条数、清理后的 room。把输出贴进总结。
3. 跑完之后真实库**未被修改**：
   `SELECT COUNT(*) FROM rh_bucket_reservations WHERE released_at IS NULL`
   跑前跑后相同。
4. `git status --short` 里只有这两个新文件是 `??`。
