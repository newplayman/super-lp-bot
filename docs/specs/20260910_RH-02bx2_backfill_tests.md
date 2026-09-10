# RH-02bx-2 — 只补测试（实现已完成，被网关中断在写测试之前）

## 现状

`scripts/lp_rh_pool_attestation_backfill_v1.py` 已经改好（工作区有 +121 行未提交改动），
新增了两个函数，主脑已在真实库上验证正确：

- `detect_registry_attestation_drift(conn)` — 只读，列出 registry 与 attestations
  结论不一致的池。真实库实测 `drift_count=1`：
  ```json
  {"pool_address": "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca",
   "registry_status": "DISCOVERED_NOT_ATTESTED",
   "attestation_status": "ATTESTED_SAME_BLOCK",
   "attestation_created_at": "2026-09-10T02:00:14Z"}
  ```
- `sync_registry_attestation_status(conn, *, records, chain_id)` — 回写 registry，
  四种情况分开计数：`updated` / `unchanged` / `skipped_not_in_registry` /
  `skipped_no_attestation`
- `plan_backfill()` 的返回里已加 `registry_drift` 键

前一个 worker 被推理网关 502 打断，**没来得及写测试**。

**本包只做一件事：写测试文件。不要改任何 `scripts/` 下的文件。**

## 唯一任务

新建 `tests/test_lp_rh_pool_attestation_backfill_v1_readonly.py`。

用 `importlib.util.spec_from_file_location` 加载被测脚本（仓库其它测试就是这么做的），
或直接 `from scripts.lp_rh_pool_attestation_backfill_v1 import ...`——
先 `head -30` 看邻近测试文件用的是哪种，照着来。

**全部用内存库（`sqlite3.connect(":memory:")`）或 `tmp_path`，
不碰真实库、不发任何网络请求**（需要 `rpc_fn` 时传一个假函数）。

建表用 `scripts/lp_rh_store_v1_readonly.py` 的 `open_store` + `migrate`，
不要自己写 CREATE TABLE。

### 表的真实列（照抄，不要猜——本会话已有三个 worker 猜错 schema）

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

`sync_registry_attestation_status` 的 `records` 参数是一个 list of dict，
每个 dict 至少有 `"address"` 键（去实现里 `record.get("address")` 那行确认）。

### 要写的测试

1. registry 有该池、attestations 有 `ATTESTED_SAME_BLOCK` →
   同步后 registry 的 `attestation_status == "ATTESTED_SAME_BLOCK"`，`updated == 1`。
2. registry 有该池、attestations 最新一行是 `FAILED` →
   registry 被改成 `FAILED`，`updated == 1`。
   **这条最重要：职责是「让两处一致」，不是「让两处都变成通过」。**
3. 同一地址两行、`created_at` 不同（旧的 `ATTESTED_SAME_BLOCK`，
   新的 `FAILED`）→ 取**新的**那行的状态。
4. attestations 里有的地址 registry 里没有 →
   `skipped_not_in_registry >= 1`，且 registry **没有新增行**
   （同步前后 `SELECT COUNT(*) FROM rh_pool_registry` 相等）。
5. registry 有该池但 attestations 里没有它 →
   registry 状态**原样不变**，`skipped_no_attestation >= 1`。
6. 地址用 EIP-55 混合大小写（如 `0x52E65b17fb6E5bA00ed806f37AfCD2Daa50271Ca`）
   传进 `records` → 仍能匹配小写存储的 registry 行并更新。
7. `detect_registry_attestation_drift`：两处一致时 `drift_count == 0`；
   不一致时 `drift_count == 1` 且 `rows[0]` 的四个键
   （`pool_address` / `registry_status` / `attestation_status` /
   `attestation_created_at`）都非空。
8. `plan_backfill` 的返回里含 `registry_drift` 键，
   且**对库零写入**：调用前后 `SELECT pool_address, attestation_status
   FROM rh_pool_registry ORDER BY pool_address` 的结果完全相同。
   （`plan_backfill` 需要 `pool_meta_path`；传 `None` 或指向 `tmp_path` 下
   自造的一个最小 json，**不要指向仓库里的 `reports/lp_rh/pool_meta.json`**。
   若它在这些输入下抛异常，用 `pytest.raises` 记录该行为并在总结里说明，
   不要为了让测试过而去改实现。）

每条测试的 docstring 写清它防的是什么回归。
**每条断言都要真能触发目标分支**——本仓库已四次写出「构造的输入进不去被测分支、
于是测试永远绿」的假测试。

## 不许动

- **不要改 `scripts/` 下的任何文件**，尤其
  `scripts/lp_rh_pool_attestation_backfill_v1.py`（实现已验收，只差测试）。
- 不要碰 `scripts/lp_rh_readiness_v1_readonly.py` 和它的测试（另一条线正在改）。
- 工作区里 `lp_silent_failure_lint_v1_readonly.py`、
  `lp_rh_readiness_v1_readonly.py`、`lp_rh_pool_attestation_backfill_v1.py`
  都有未提交改动，那是别的线的产物，**不要碰、也不要以为是自己改错了**。
- **不要执行 `--apply`**，不要写 `reports/lp_rh/scanner.db`。
- **不要执行任何 git 命令。**
- 单次 Write ≤150 行或 6000 字符，超了分次追加。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_pool_attestation_backfill_v1_readonly.py -q`
   全绿，条数 ≥ 8。
2. `git status --short` 里**只有这一个新文件**是 `??`；
   `scripts/lp_rh_pool_attestation_backfill_v1.py` 仍是 ` M`（保持前一个 worker 的改动，
   你没有再动过它）。
3. 真实库**未被修改**：`SELECT attestation_status FROM rh_pool_registry` 仍是
   `DISCOVERED_NOT_ATTESTED`。
