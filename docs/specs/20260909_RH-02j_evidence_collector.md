# RH-02j：证据采集器——填满另两张空表

## 背景

`RH-02h`（提交 `54eed3b`）落地了写入器，主脑已用它真实写入 `rh_pool_registry`（1 行）。
但 `rh_assets` 与 `rh_contract_attestations` 仍是 0 行，**因为缺数据源**：
前者要 REST `/rhj/assets` 的响应，后者要链上探测产出的 attestation。

本包补上这个采集器。**这是 Stage A「身份和能力证据清楚」的最后一块。**

## 先解决一个架构问题：单写者纪律

PRD §16.2 规定 RH store **单 writer**，而 `scanner.db` 的现任写者是采集器。

**本包的处置（spec 已定，不要自行更改）**：
本采集器写 `scanner.db`，但**只碰三张证据表**
（`rh_assets` / `rh_pool_registry` / `rh_contract_attestations`），
与采集器写的三张表（`rh_market_states` / `rh_rpc_health` / `rh_source_snapshots`）
**完全不相交**。SQLite WAL 会把两个写者串行化，逻辑上无冲突。

**必须有一条测试断言本采集器从不写采集器那三张表**（前后逐表 COUNT 比对）。
这条不是形式主义——它是「两个写者共存」这个决定唯一的安全保障。

## 已核实的数据源事实（直接用，不要另猜）

- REST `https://api.robinhood.com/rhj/assets`——**注意不是 `/rhj/prices`**。
  `/rhj/prices` 的容器键是 `quotes`；`/rhj/assets` 的结构需实测确认，
  **先用 `--dry-run` 打印前两条记录的键再写映射**。
- 该 REST **会限流**（`/rhj/prices` 实测突发返回 429，等约 95 秒恢复），
  退避 5/15/45/90 秒，周期不低于 300 秒。
- 股票代币共用 beacon `0xe10b6f6b275de231345c20d14ab812db62151b00`，
  `implementation()` 返回值入 attestation；**一次 beacon 升级会同时使 194 个代币的
  attestation 过期**（PRD §7.1 的 P0 监控点）。
- 乘数选择器 `0xa60bf13d`（1e18 定点），暂停 `0x5c975abb`。
  **PRD §9.5 假设的 `currentMultiplier()` / `oraclePaused()` 在链上 revert，不要用。**
- CORE 种子池 `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`，chainId 4663。

## 只写一个文件 + 其测试

1. `scripts/lp_rh_evidence_collector_v1_readonly.py`（≤300 行）
   复用 `scripts.lp_rh_evidence_writer_v1_readonly` 的三个 write 函数，**不要重写**。
   网络调用通过注入的 `fetch_fn` / `rpc_fn` 完成，**模块自身的默认实现用 urllib**，
   但测试必须能注入假函数。

   - `collect_assets(fetch_fn) -> list`：拉 `/rhj/assets`，返回资产记录列表。
     容器键**以实测为准**，取不到时返回 `[]` 并记原因，**不要抛**。
   - `collect_attestations(rpc_fn, addresses, *, beacon) -> list`
     对每个地址取 `eth_getCode` 的 code_hash、beacon 的 `implementation()`、
     当前 `block_hash`，组装成 `write_attestations` 要的形状。
     **任一取不到 → 该地址跳过并计数，不得用空串填必填列**
     （写入器会抛，这里要在之前就拦住）。
   - `run_once(conn, *, fetch_fn, rpc_fn, chain_id, policy_version) -> dict`
     依次调三个写入函数，返回
     `{"assets": {...}, "pool_registry": {...}, "attestations": {...}, "errors": [...]}`。
     **单个环节失败不得中断其余环节**。
   - `main()`：`--db --period-secs 300 --pid-file --once --dry-run`。
     `--dry-run` **只打印不写库**（含 REST 响应的前两条记录的键，便于确认结构）。
     循环 deadline 从**本轮起点**算。`SIGTERM`/`SIGINT` 优雅退出并删 pid 文件。

2. `tests/test_lp_rh_evidence_collector_v1_readonly.py`（≤260 行，**≥14 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
   **内存 SQLite + 注入的假 `fetch_fn`/`rpc_fn`，不许联网、不许写 `reports/`。** 必测：
   - **★本采集器从不写采集器那三张表**（`rh_market_states` / `rh_rpc_health` /
     `rh_source_snapshots` 前后 COUNT 完全相同）。**这条是单写者共存的唯一保障。**
   - `collect_assets` 在容器键缺失时返回 `[]` 且不抛。
   - `collect_attestations`：某地址取不到 code_hash → 该地址被跳过并计数，
     **不进入写入**（断言写入器未收到该记录）。
   - 某地址取不到 `block_hash` → 同样跳过（必填列）。
   - `run_once`：`collect_assets` 抛异常时，`pool_registry` 与 `attestations`
     **仍然执行**，异常记入 `errors`。
   - `run_once` 返回的三个子结果各含 `written`/`skipped`/`missing_fields`。
   - `--dry-run` 不写库（前后 COUNT 比对）且返回 0。
   - `--once` 写库且返回 0。
   - chain_id 非 4663 → 三个写入都 skip（身份闸在写入层已有，这里回归断言）。
   - beacon `implementation()` 取不到 → attestation 的 `implementation` 列为 `None`
     （**可选列，可为 None；不是跳过整条**）。
   - 空资产列表 → `written == 0`，不抛。
   - REST 返回 429 → 退避后重试，注入假 `sleep_fn` 断言退避递增且**不真 sleep**。
   - deadline 从本轮起点算（注入假时钟与 `sleep_fn` 断言）。
   - 幂等：连续两次 `run_once` 不产生重复行。

## 不许动
不改写入器与其他脚本。不碰采集器那三张表。测试不联网、不真 sleep。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。
**不要启动任何常驻进程**——上线由主脑负责。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_evidence_collector_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
