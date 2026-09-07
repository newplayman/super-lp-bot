# RH-02c：RH 正向数据采集器（可无人值守连跑 72 小时）

## 背景（一段）

PRD v1.1 §21.1 Stage A 要求**至少 72 小时正向观测**才可能毕业，这是整条路径上最长的一根杆，必须尽早开跑。主脑已于 2026-09-07 完成链上实测（证据：`reports/rh_pivot/20260907T124500Z/RH-01b/LIVE_RPC_PROBE_20260907.md`），确认了三个硬约束，本采集器必须全部遵守：

1. **只有 1 个可用 provider**：`https://rpc.mainnet.chain.robinhood.com`（p50 270ms）。`robinhood.drpc.org` 是假绿端点（`eth_chainId` 正确但所有真实方法返回 `-32601`），**禁止把它计入可用 provider**。
2. **无 archive**：历史状态只能回溯约 1000–10000 区块，再往前 `metadata is not found`。只能正向采集，**不伪造历史**。
3. **`eth_getLogs` 单次返回上限 10000 条**：span=1000 约 1322 条，span=10000 超限。需自适应二分降 span。

另：**USDG `decimals()` 为 6**，WETH 为 18，一律从链上读，禁止假设。

目标池（已通过身份闸）：`0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`，token0=WETH `0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73`，token1=USDG `0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168`，fee=100，tickSpacing=1。

存储层已就位：`scripts/lp_rh_store_v1_readonly.py`（`open_store` / `migrate` / `insert_row` / `budget_status`，16 张 `rh_*` 表）。

## 新增文件（**只许新建这些，其它文件一行都不许动**）

1. `scripts/lp_rh_collector_v1_readonly.py`（**≤ 300 行**，分次写，每次 ≤150 行）
   - 顶部仓库通行 sys.path 引导（同 `lp_scanner_daemon_v1_readonly.py:38-40`）。
   - `from scripts.lp_rh_store_v1_readonly import open_store, migrate, insert_row, budget_status, DEFAULT_DB_PATH`
   - **HTTP 层**：只用标准库 `urllib.request`，**必须设 `User-Agent: curl/8.5.0`**（Cloudflare 对 `Python-urllib` 的 POST 返回 403）。单请求 timeout 12s。**不得 import requests。**
   - `RH_RPC_PRIMARY = os.environ.get("RH_RPC_PRIMARY", "https://rpc.mainnet.chain.robinhood.com")`。
   - `rpc(method, params, *, url) -> tuple[result|None, error|None, latency_ms]`：JSON-RPC 响应含 `error` 字段时返回 `(None, error_dict, ms)`，**绝不当作 0 或空结果**（T12）。
   - **采集循环**（每轮）：
     a. `eth_blockNumber` + `eth_getBlockByNumber(latest,false)` 取 `number/hash/timestamp/baseFeePerGas`；
     b. 对目标池 `eth_call` 取 `slot0()`(`0x3850c7bd`)、`liquidity()`(`0x1a686502`)；
     c. `balanceOf(pool)` 取两代币余额（selector `0x70a08231`）；
     d. 计算 `price_token1_per_token0_human = (sqrtPriceX96/2**96)**2 * 10**dec0 / 10**dec1`，**dec0/dec1 启动时从链上 `decimals()` 读一次并缓存**；
     e. 写 `rh_pool_events`？**不**——本包不解析事件；写 `rh_rpc_health`（provider/method/sample_time/latency_ms/error/last_good_block/state）与 `rh_market_states`（asset_address 用池地址，session 填 `"UNKNOWN"`，`health_flags_json` 填本轮 flags，`reference_mid` 填 human 价格字符串，`multiplier_human` 填 None）；并写 `rh_source_snapshots`（source=`"rh_rpc:pool_state"`，`payload_hash`=本轮原始 JSON 的 sha256，`fetch_time`=UTC RFC3339，`raw_ref`=None）。
     f. **所有金额/价格以十进制字符串入库**（存储层会校验，float 会被拒）。
   - **预算与降级**：每 20 轮调一次 `budget_status`；`WARN`（≥80%）时把轮询间隔翻倍并记一条 `rh_rpc_health` state=`"BUDGET_WARN"`；`OVER`（≥100%）时**停止采集并退出码 0**，日志写明原因（PRD §16.4、T57）。
   - **限流与退避**：连续失败对同一 provider 做指数退避，**指数必须封顶**（`min(fails-1, 10)`，参考 RH-00b 的教训），单轮最多重试 3 次。
   - **CLI**：`--db <path>`（默认 `DEFAULT_DB_PATH`）、`--interval-secs`（默认 15）、`--max-rounds`（默认 0=无限）、`--pid-file`、`--once`（跑一轮就退出，供测试用）。
   - **优雅退出**：捕获 `SIGTERM`/`SIGINT`，写完当前轮后 commit 并关闭连接，退出码 0。启动时若 pid-file 存在且该 PID 仍活着 → 打印错误退出码 2（**防止双写**，PRD §16.1 单 writer）。
   - **绝不**：签名、广播、写钱包、读 `.env*`、import web3/eth_account/solders/solana/requests、访问 `robinhood.drpc.org`、碰 `reports/lp_scanner/`。
2. `tests/test_lp_rh_collector_v1_readonly.py`（≤ 250 行），**全部用注入的假 rpc callable，不联网**，至少 12 个测试：
   - JSON-RPC 返回 `{"error":{...}}` → 该轮记 `rh_rpc_health.error` 非空、`last_good_block` 保持上一次值，**不写 0**（T12）。
   - 价格换算：给定 `sqrtPriceX96=3953938817749275760872870`、dec0=18、dec1=6，断言 human 价格在 `2490.0 ~ 2491.0` 之间（实测 2490.58）；若误用 dec0=dec1=18 则结果 <1e-6（写成对照断言，证明精度处理正确）。
   - `--once` 模式跑一轮后 `rh_market_states` / `rh_rpc_health` / `rh_source_snapshots` 各增加 1 行。
   - 同一轮的 `payload_hash` 幂等：重复插入同 `(source, payload_hash)` 抛 `IntegrityError` 被捕获且不中断循环。
   - budget `WARN` 时间隔翻倍；`OVER` 时循环退出且退出码 0（用 monkeypatch 把 `budget_status` 打桩）。
   - pid-file 已被活进程占用 → 退出码 2。
   - SIGTERM 后能干净退出（用 `--once` 或打桩信号处理器验证）。
   - 退避指数封顶：连续失败 2000 次后不抛 `OverflowError`，冷却时间等于上限。
   - 源码断言：`grep` 该脚本**不含** `drpc`、不含 `import requests`、含 `curl/8.5.0`。

## 不许动什么

- 不改任何现有脚本/测试/配置/六常量/`.gitignore`；**尤其不许碰 `scripts/lp_rh_netcover_inputs_v1_readonly.py` 或 `tests/test_lp_rh_netcover_inputs_v1_readonly.py`（另一个 worker 正在写这两个文件）**。
- 不启动任何常驻进程（启动由主脑做）。
- 单次 Write/Edit ≤150 行或 6000 字符；不整读 >300 行文件。
- **不要用 TaskCreate/TaskUpdate 工具**，直接干活。

## 验收标准

- [ ] `git status --short` 新增只有 `scripts/lp_rh_collector_v1_readonly.py` 与 `tests/test_lp_rh_collector_v1_readonly.py`；`git diff --stat` 为空。
- [ ] 脚本 ≤300 行；新测试 ≥12 个且全绿。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` 0 failed、14 skipped。
- [ ] `grep -nE 'drpc|import requests' scripts/lp_rh_collector_v1_readonly.py` 零命中；`grep -c 'curl/8.5.0'` ≥1。
- [ ] `python scripts/lp_rh_collector_v1_readonly.py --db /tmp/rh_c.db --once --pid-file /tmp/rh_c.pid` 不带 PYTHONPATH 退出码 0（**允许联网跑真实一轮**），且 `/tmp/rh_c.db` 三张表各 ≥1 行。

## 验证命令（仓库根 `/opt/lpbot/lp-bot-v3-origin-check`）

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_collector_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
env -u PYTHONPATH /root/lp-bot/.venv/bin/python scripts/lp_rh_collector_v1_readonly.py --db /tmp/rh_c.db --once --pid-file /tmp/rh_c.pid && echo ONCE_OK
/root/lp-bot/.venv/bin/python -c "import sqlite3;c=sqlite3.connect('/tmp/rh_c.db');[print(t, c.execute(f'select count(*) from {t}').fetchone()[0]) for t in ('rh_market_states','rh_rpc_health','rh_source_snapshots')]"
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
grep -nE 'drpc|import requests' scripts/lp_rh_collector_v1_readonly.py || echo NO_FORBIDDEN
git diff --stat; git status --short | grep -E 'lp_rh_collector'
```
