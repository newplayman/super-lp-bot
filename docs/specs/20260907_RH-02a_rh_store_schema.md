# RH-02a：RH 独立 SQLite 存储层与 16 张 rh_* 表（只读管线内的本地写入）

## 背景（一段）

PRD v1.1 §16.1–16.4、§19 的 RH-02、用例 T57 要求：RH 支线使用**独立**的 `reports/lp_rh/scanner.db`，与旧 `reports/lp_scanner/scanner.db` 完全分开；单 writer、WAL、合理 busy timeout、schema version、事务内写入。**禁止**把 B2 的 PostgreSQL DDL（`NUMERIC`/`UUID`/`TIMESTAMPTZ`）粘过来：所有 uint256 与 raw amount 以**十进制 TEXT** 保存并在程序中校验；金额用规范化 Decimal 字符串；**绝不用 SQLite REAL 存钱或大整数**；时间统一 UTC RFC3339 字符串或统一整数单位，禁止秒/毫秒混用。本包只做**存储层骨架**（DDL + 打开/迁移 + 类型校验 + 预算检查），不做采集、不联网、不写业务数据。

参考现有风格：`scripts/lp_scanner_daemon_v1_readonly.py` 的 `ScannerStore`（约 :417，DDL 在 `_SCHEMA` :194 起）与 `scripts/lp_shadow_gate_v1_readonly.py` 的 `GateStore`（:150）。**只读其片段学风格，不修改它们。**

## 新增文件

1. `scripts/lp_rh_store_v1_readonly.py`（≤ 350 行，分次 Write/Edit，每次 ≤150 行）
   - 顶部照抄仓库通行的 sys.path 引导（同 `lp_scanner_daemon_v1_readonly.py:38-40`）。
   - `SCHEMA_VERSION = 1`；`DEFAULT_DB_PATH = REPO_ROOT / "reports/lp_rh/scanner.db"`；`SOFT_BUDGET_BYTES = 2 * 1024**3`；`WARN_FRACTION = 0.80`。
   - `open_store(path=DEFAULT_DB_PATH, *, read_only=False) -> sqlite3.Connection`：创建父目录；`PRAGMA journal_mode=WAL`、`PRAGMA busy_timeout=30000`、`PRAGMA foreign_keys=ON`；只读模式用 `file:...?mode=ro` URI。
   - `migrate(conn) -> int`：建表（`CREATE TABLE IF NOT EXISTS`）与索引；把 `SCHEMA_VERSION` 写进 `PRAGMA user_version`；已是当前版本则幂等返回。**所有 DDL 在一个事务内。**
   - **16 张表**（列名照抄下表，类型只允许 `TEXT` / `INTEGER`；**任何金额、raw amount、价格、乘数一律 TEXT**）：

     | 表 | 主键 / 唯一约束 | 必需列（除主键外） |
     |---|---|---|
     | `rh_source_snapshots` | PK `(source, payload_hash)` | `source_event_time TEXT`, `fetch_time TEXT NOT NULL`, `schema_kind TEXT`, `raw_ref TEXT`, `quality TEXT` |
     | `rh_assets` | PK `(chain_id, address, metadata_version)` | `symbol_display TEXT`, `uid TEXT`, `underlying TEXT`, `decimals INTEGER`, `multiplier_raw TEXT`, `status TEXT`, `capability_json TEXT`, `source_payload_hash TEXT`, `updated_at TEXT NOT NULL` |
     | `rh_contract_attestations` | PK `(chain_id, address, block_hash, policy_version)` | `code_hash TEXT`, `implementation TEXT`, `abi_version TEXT`, `attestation_status TEXT NOT NULL`, `evidence_json TEXT`, `expires_at TEXT`, `created_at TEXT NOT NULL` |
     | `rh_pool_registry` | PK `(chain_id, protocol, pool_key)` | `pool_address TEXT`, `pool_id TEXT`, `token0 TEXT`, `token1 TEXT`, `fee TEXT`, `tick_spacing INTEGER`, `hooks TEXT`, `attestation_status TEXT NOT NULL`, `discovered_at TEXT NOT NULL` |
     | `rh_pool_events` | PK `(chain_id, block_hash, tx_hash, log_index)` | `block_number INTEGER NOT NULL`, `pool_key TEXT NOT NULL`, `event_type TEXT NOT NULL`, `amount0_raw TEXT`, `amount1_raw TEXT`, `liquidity_raw TEXT`, `tick INTEGER`, `observed_at TEXT NOT NULL` |
     | `rh_market_states` | PK `(asset_address, sample_time)` | `chain_id INTEGER NOT NULL`, `source_payload_hash TEXT`, `session TEXT NOT NULL`, `health_flags_json TEXT NOT NULL`, `reference_bid TEXT`, `reference_ask TEXT`, `reference_mid TEXT`, `reference_age_secs INTEGER`, `multiplier_human TEXT`, `oracle_paused INTEGER` |
     | `rh_rpc_health` | PK `(provider, method, sample_time)` | `latency_ms INTEGER`, `error TEXT`, `last_good_block INTEGER`, `state TEXT NOT NULL` |
     | `rh_economic_evaluations` | PK `(candidate_key, snapshot_id, model_version, policy_version, horizon_hours, position_usd)` | `fee_ev TEXT`, `reward_ev TEXT`, `cost_components_json TEXT`, `netcover TEXT`, `abs_profit TEXT`, `q_min TEXT`, `q_max TEXT`, `missing_inputs_json TEXT`, `evaluated_at TEXT NOT NULL` |
     | `rh_gate_decisions` | PK `decision_id` | `candidate_key TEXT NOT NULL`, `target_mode TEXT NOT NULL`, `primary_status TEXT NOT NULL`, `terminal_bits_json TEXT NOT NULL`, `dominant_blocker TEXT`, `reasons_json TEXT`, `snapshot_ids_json TEXT`, `decided_at TEXT NOT NULL` |
     | `rh_shadow_positions` | PK `(strategy_episode, position_id)` | `pool_key TEXT NOT NULL`, `profile TEXT NOT NULL`, `bucket TEXT NOT NULL`, `initial_token0_raw TEXT`, `initial_token1_raw TEXT`, `tick_lower INTEGER`, `tick_upper INTEGER`, `virtual_liquidity_raw TEXT`, `opened_at TEXT NOT NULL`, `closed_at TEXT` |
     | `rh_journal` | PK `event_id`；UNIQUE `idempotency_key` | `account_debit TEXT NOT NULL`, `account_credit TEXT NOT NULL`, `asset TEXT NOT NULL`, `amount_raw TEXT NOT NULL`, `is_external_flow INTEGER NOT NULL`, `ref_json TEXT`, `booked_at TEXT NOT NULL` |
     | `rh_position_marks` | PK `(position_id, mark_time)` | `price_snapshot_id TEXT`, `reference_nav TEXT`, `liquidation_nav TEXT`, `accrued_fee TEXT`, `unvalued_risk_json TEXT` |
     | `rh_bucket_reservations` | PK `intent_id` | `policy_version TEXT NOT NULL`, `bucket TEXT NOT NULL`, `amount_usd TEXT NOT NULL`, `status TEXT NOT NULL`, `created_at TEXT NOT NULL`, `released_at TEXT` |
     | `rh_tx_intents` | PK `request_id`；UNIQUE `idempotency_key` | `chain_id INTEGER NOT NULL`, `wallet_id TEXT`, `position_id TEXT`, `nonce INTEGER`, `state TEXT NOT NULL`, `calldata_hash TEXT`, `policy_hash TEXT`, `expires_at TEXT`, `created_at TEXT NOT NULL` |
     | `rh_tx_receipts` | PK `(request_id, tx_hash)` | `block_hash TEXT`, `block_number INTEGER`, `status TEXT NOT NULL`, `gas_used TEXT`, `reorg_detected INTEGER NOT NULL DEFAULT 0`, `observed_at TEXT NOT NULL` |
     | `rh_reconciliation_runs` | PK `run_id` | `started_at TEXT NOT NULL`, `finished_at TEXT`, `evidence_json TEXT`, `delta_json TEXT`, `verdict TEXT NOT NULL` |

     索引至少：`rh_pool_events(pool_key, block_number)`、`rh_market_states(asset_address, sample_time DESC)`、`rh_rpc_health(provider, sample_time DESC)`、`rh_gate_decisions(candidate_key, decided_at DESC)`、`rh_journal(booked_at)`。
   - `assert_decimal_text(value, field) -> str`：接受 `str` 且匹配 `^-?\d+(\.\d+)?$`；`int` 转 str；`float` **抛 `TypeError("REAL_NOT_ALLOWED_FOR_MONEY: <field>")`**；`None` 原样放行（缺输入不是 0）。
   - `assert_utc_rfc3339(value, field) -> str`：必须形如 `YYYY-MM-DDTHH:MM:SS(.ffffff)?Z` 或 `+00:00`；否则抛 `ValueError("NON_UTC_TIMESTAMP: <field>")`。
   - `insert_row(conn, table, row: Mapping) -> None`：表名必须在白名单内（否则 `ValueError("UNKNOWN_TABLE")`）；按每表登记的"金额列"清单逐列过 `assert_decimal_text`，按"时间列"清单过 `assert_utc_rfc3339`；`INSERT` 用参数化占位符（禁止字符串拼接值）。
   - `budget_status(path=DEFAULT_DB_PATH) -> dict`：返回 `{"bytes":…, "soft_budget_bytes":…, "fraction":…, "state": "OK"|"WARN"|"OVER"}`；`fraction >= 0.80` → WARN；`>= 1.0` → OVER。
   - `main()`：`--db <path>`（默认 DEFAULT_DB_PATH）、`--init` 建库并打印 `{"schema_version":…, "tables":[…], "budget":{…}}`、`--status` 只读打印同结构。**不启动任何常驻进程。**
2. `tests/test_lp_rh_store_v1_readonly.py`（≤ 250 行），全部用 `tmp_path` 建临时库，**绝不碰 `reports/lp_rh/`**。至少 14 个测试：
   - `migrate` 后 16 张表全部存在（逐一断言表名），`PRAGMA user_version == 1`，重复 `migrate` 幂等且不报错。
   - `PRAGMA journal_mode` 为 `wal`；`PRAGMA foreign_keys` 为 1。
   - 每张表的 declared type 里**没有 `REAL`**（查 `PRAGMA table_info`，断言 `type` 只属于 {TEXT, INTEGER}）。
   - `assert_decimal_text(1.5, "x")` 抛 `TypeError` 且消息含 `REAL_NOT_ALLOWED_FOR_MONEY`；`assert_decimal_text("123456789012345678901234567890", "x")` 通过（超 int64 的 uint256 十进制串）；`assert_decimal_text(None,"x") is None`。
   - `assert_utc_rfc3339("2026-09-07T12:00:00Z")` 通过；`"2026-09-07 12:00:00"`、`"2026-09-07T12:00:00+02:00"`、`1757246400`（整数秒）均抛 `ValueError`。
   - `insert_row` 往 `rh_journal` 插入浮点 `amount_raw` 被拒；插入合法行成功；**重复 `idempotency_key` 抛 `sqlite3.IntegrityError`**。
   - `rh_pool_events` 同一 `(chain_id, block_hash, tx_hash, log_index)` 重复插入抛 `IntegrityError`；**block_number 相同但 block_hash 不同的两行可以共存**（T11 的 reorg 前提：按 hash 去重不按 number）。
   - `insert_row(conn, "not_a_table", {})` 抛 `ValueError("UNKNOWN_TABLE")`。
   - `budget_status` 在小库上返回 `state=="OK"`；用 `monkeypatch` 把 `SOFT_BUDGET_BYTES` 调到极小后返回 `WARN` 或 `OVER`。
   - `main(--init)` 在 tmp 路径退出码 0 且输出含 16 个表名。

## 不许动什么

- **不改任何现有脚本、测试、配置**；不动六常量；不碰 `reports/lp_scanner/`、`reports/lp_scanner_v2_20260823/` 或任何旧 db；不动 `.gitignore`。
- 不联网、不 curl/wget、不读 `.env*`、不 import web3/eth_account/solders/solana/psycopg2。
- 不写 PostgreSQL 类型（`NUMERIC`/`UUID`/`TIMESTAMPTZ`/`SERIAL`）；不使用 SQLite `REAL` 存钱或大整数。
- 不实现采集、不实现 gate 逻辑、不实现 reservation 原子扣减（那是 RH-02b）。
- 单次 Write/Edit ≤150 行或 6000 字符；不整读 >300 行文件，用 `grep -n` / `sed -n` 取片段。
- **不要用 TaskCreate/TaskUpdate 工具**，直接干活。

## 验收标准

- [ ] `git status --short` 新增只有 `scripts/lp_rh_store_v1_readonly.py` 与 `tests/test_lp_rh_store_v1_readonly.py`；`git diff --stat` 为空（无已跟踪文件改动）。
- [ ] 新测试 ≥14 个且全绿。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` = 3150 + 新增数，0 failed，14 skipped。
- [ ] `grep -nE 'REAL|NUMERIC|TIMESTAMPTZ|UUID|SERIAL' scripts/lp_rh_store_v1_readonly.py` 只在报错消息/注释里出现，DDL 中零命中。
- [ ] `python scripts/lp_rh_store_v1_readonly.py --db /tmp/rh_test.db --init` 不带 PYTHONPATH 退出码 0，输出列出 16 张表。

## 验证命令（仓库根 `/opt/lpbot/lp-bot-v3-origin-check`）

```bash
env -u PYTHONPATH /root/lp-bot/.venv/bin/python scripts/lp_rh_store_v1_readonly.py --db /tmp/rh_test.db --init && echo INIT_OK
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_store_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
grep -nE '\bREAL\b|NUMERIC|TIMESTAMPTZ|UUID|SERIAL' scripts/lp_rh_store_v1_readonly.py || echo NO_FORBIDDEN_TYPES
git diff --stat; git status --short | grep -E 'lp_rh_store'
```
