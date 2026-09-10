# RH-02bx — 两个真相源打架：registry 说没认证，attestations 说认证了

## 缺陷（codex 指出，主脑已核实）

同一个池，两处状态互相矛盾：

```
rh_pool_registry.attestation_status  = 'DISCOVERED_NOT_ATTESTED'
rh_contract_attestations             = 390 行，全部 'ATTESTED_SAME_BLOCK'
                                       （该池那行：expires_at=NULL, created_at=2026-09-10T02:00:14Z）
```

`scripts/lp_rh_pool_attestation_backfill_v1.py` 的 `apply_backfill()`（L157-186）
只调 `write_attestations()` 写 `rh_contract_attestations`，
**从不回写 `rh_pool_registry.attestation_status`**。所以 backfill 一 apply，
registry 那一列就永久停在 `DISCOVERED_NOT_ATTESTED`。

当前**没有直接消费者**读那一列（`audit_pool_attestation` 读的是 attestations 表），
所以此刻没有造成错误结论。但两个真相源长期分叉，迟早有人读到陈旧的那个——
而且方向可能是任意的：读 registry 会得到错误的否定，
若将来 attestation 过期而 registry 停在 ATTESTED，则是错误的肯定。

PRD 把 `sources_disagree` 列为必须显式处理的健康标志，两个内部表打架属于同一类。

## 要做的事

只改 `scripts/lp_rh_pool_attestation_backfill_v1.py`。

### 1. `apply_backfill` 写完 attestations 后回写 registry

新增一个函数：

```python
def sync_registry_attestation_status(conn, *, records, chain_id) -> dict:
    """把 rh_contract_attestations 的结论回写到 rh_pool_registry.attestation_status。

    只对 registry 里确实存在的 pool_address 生效；registry 没有的地址跳过并计数
    （backfill 会给 token0/token1/beacon 等非池地址也做认证，那些本来就不该进 registry）。
    """
```

规则：

- 按 `LOWER(pool_address) = LOWER(?)` 匹配（**本仓库因 EIP-55 大小写栽过一次**）
- registry 里没有该地址 → 计入 `skipped_not_in_registry`，**不要 INSERT 新行**
  （backfill 的职责不是造 registry 记录）
- 有该行 → 把 `attestation_status` 更新为该地址在
  `rh_contract_attestations` 里**最新一行**（`created_at DESC`）的
  `attestation_status`
- 返回 `{"updated": n, "unchanged": n, "skipped_not_in_registry": n, "details": [...]}`

在 `apply_backfill` 的返回 dict 里加 `"registry_sync": <上面的返回值>`。

### 2. `plan_backfill`（dry-run）里报告分歧

dry-run 不写任何东西，但应当**看得见**分歧。新增一个只读函数：

```python
def detect_registry_attestation_drift(conn) -> dict:
    """列出 registry 与 attestations 结论不一致的池。只读，不修改。"""
```

返回 `{"drift_count": n, "rows": [{"pool_address":..., "registry_status":...,
"attestation_status":..., "attestation_created_at":...}, ...]}`。

把它放进 `plan_backfill` 返回的 dict 里，键名 `"registry_drift"`。

### 3. 不要偷偷放宽

- registry 里该地址**没有**对应 attestation 行时，**不要**把状态改成任何值，
  保持原样并计入 `skipped_no_attestation`。
- attestation 的最新状态是**任何**值（包括 `FAILED`）都照实回写——
  这个函数的职责是「让两处一致」，不是「让两处都变成通过」。

## 不许动

- **不要执行 `--apply`**，不要真的写 `reports/lp_rh/scanner.db`。
  本包只改代码；是否 apply 是主脑与用户的决定。
- 不要改 `collect_attestations` / `write_attestations` / `resolve_target_addresses`
  的行为，也不要改 RPC 调用次数（当前 dry-run 估算是 6 次，不要变）。
- 不要碰 `scripts/lp_rh_readiness_v1_readonly.py`（另一条线正在改）。
- 不要碰 `scripts/lp_rh_shadow_runner_v1_readonly.py`（另一条线正在改）。
- 不要碰 `scripts/lp_silent_failure_lint_v1_readonly.py`（工作区已有另一条线的改动，
  那不是你改错了）。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 表的真实列（已核实，照抄——本会话已有三个 worker 猜错 schema）

```
rh_pool_registry
  全部: chain_id, protocol, pool_key, pool_address, pool_id, token0, token1,
        fee, tick_spacing, hooks, attestation_status, discovered_at

rh_contract_attestations
  NOT NULL: chain_id, address, block_hash, policy_version,
            attestation_status, created_at
  全部    : chain_id, address, block_hash, policy_version, code_hash,
            implementation, abi_version, attestation_status, evidence_json,
            expires_at, created_at
```

`insert_row()` 会**静默丢弃**表里没有的列名，猜错的列只会在很久之后
以 NOT NULL 失败的形式露头。

## 测试（`tests/test_lp_rh_pool_attestation_backfill_v1_readonly.py`；没有就新建）

内存库或 `tmp_path`，**不碰真实库、不发任何网络请求**（`rpc_fn` 用假函数注入）。

1. registry 有该池、attestations 有 `ATTESTED_SAME_BLOCK` →
   同步后 registry 的 `attestation_status` == `ATTESTED_SAME_BLOCK`，`updated == 1`。
2. registry 有该池、attestations 最新一行是 `FAILED` →
   registry 被改成 `FAILED`（**照实回写，不是只写通过状态**），`updated == 1`。
3. 同一地址两行、`created_at` 不同 → 取**新的**那行的状态。
4. attestations 里有的地址 registry 里没有 →
   `skipped_not_in_registry >= 1`，且 registry **没有新增行**。
5. registry 有该池但 attestations 里没有它 →
   registry 状态**原样不变**，计入 `skipped_no_attestation`。
6. 地址用 EIP-55 混合大小写 → 仍能匹配小写存储的行。
7. `detect_registry_attestation_drift` 在两处一致时 `drift_count == 0`；
   在不一致时列出该行且 `drift_count == 1`。
8. `plan_backfill` 的返回里含 `registry_drift` 键，且**没有对库做任何写入**
   （跑前跑后对 registry 做一次 `SELECT` 比对，断言完全相同）。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_pool_attestation_backfill_v1_readonly.py -q`
   全绿，条数 ≥ 8。
2. 在**真实库**上跑 dry-run（**不加 `--apply`**）：
   ```
   python3 scripts/lp_rh_pool_attestation_backfill_v1.py --dry-run 2>&1 | tail -20
   ```
   输出里能看到 `registry_drift`，且 `drift_count >= 1`
   （真实库当前就是分歧状态：registry 说 `DISCOVERED_NOT_ATTESTED`，
   attestations 说 `ATTESTED_SAME_BLOCK`）。
   把这段输出贴进总结。
   ——如果该脚本的 dry-run 需要网络，改用只读 python 片段直接调
   `detect_registry_attestation_drift(conn)` 并贴输出。
3. 跑完之后 `rh_pool_registry` 的内容**没有变化**
   （dry-run 不得写库；用 `SELECT attestation_status FROM rh_pool_registry` 前后比对）。
4. 全量 `python3 -m pytest tests/ -q` 通过。
5. `git status --short` 里只有
   `scripts/lp_rh_pool_attestation_backfill_v1.py` 和它的测试文件被改动。
