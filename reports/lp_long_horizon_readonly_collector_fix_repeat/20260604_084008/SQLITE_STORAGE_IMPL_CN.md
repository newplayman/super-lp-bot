# Stage H — SQLite + JSONL Storage 实现

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1`
- run_id: `20260604_084008`

## 0. 实现文件

- `scripts/lp_long_horizon/storage/research_store.py`

## 1. ResearchStore API

```python
class ResearchStore:
    def __init__(self, out_dir: Path, *, abort_controller=None): ...
    @property sqlite_available: bool
    @property jsonl_only: bool
    @property counts: dict[str, int]
    @property sqlite_warnings: list[str]

    def write_pool_snapshot(record: dict) -> None
    def write_quote_snapshot(record: dict) -> None
    def write_fee_velocity(record: dict) -> None
    def write_liquidity_distribution(record: dict) -> None
    def write_market_regime(record: dict) -> None
    def write_actual_fee_placeholder(record: dict) -> None
    def close() -> None
    def summary() -> dict
```

## 2. 双写策略

每个 `write_*` 同时写:
- **JSONL** (always): append to `data/lp_long_horizon/<run_id>/<table>.jsonl`
- **SQLite** (if available): `INSERT INTO <table>` via prepared statement

如果 SQLite 初始化失败 (e.g. permission / disk full / 编译问题), 自动
fallback 到 JSONL-only + 记 warning. 不会 abort, 因为 JSONL 是 ground truth.

如果 SQLite 在 write 期间失败 (e.g. 后续 insert 失败), 自动降级为
JSONL-only + 记 warning. 不会中断后续写.

## 3. SQLite DDL (6 表 + 6 索引)

```sql
CREATE TABLE IF NOT EXISTS pool_snapshots (...);
CREATE TABLE IF NOT EXISTS quote_snapshots (...);
CREATE TABLE IF NOT EXISTS fee_velocity (...);
CREATE TABLE IF NOT EXISTS liquidity_distribution (...);
CREATE TABLE IF NOT EXISTS market_regime (...);
CREATE TABLE IF NOT EXISTS future_actual_fee_accrual (...);

CREATE INDEX IF NOT EXISTS idx_pool_snapshots_pool ON pool_snapshots(pool_address, snapshot_at);
CREATE INDEX IF NOT EXISTS idx_quote_snapshots_pool ON quote_snapshots(pool_address, quote_at);
CREATE INDEX IF NOT EXISTS idx_fee_velocity_pool ON fee_velocity(pool_address, window_end_at);
CREATE INDEX IF NOT EXISTS idx_liquidity_dist_pool ON liquidity_distribution(pool_address, snapshot_at);
CREATE INDEX IF NOT EXISTS idx_market_regime_at ON market_regime(regime_at);
CREATE INDEX IF NOT EXISTS idx_actual_fee_token ON future_actual_fee_accrual(token_id);
```

PRAGMA: `journal_mode=WAL`, `synchronous=NORMAL` (research-only, 不需要 ACID 严格).

## 4. JSONL fallback 行为

- 写 JSONL 失败 → `abort_controller.record_write_failure(reason)` + raise
  (写盘失败是 hard error, 不应继续)
- 写 SQLite 失败 → log warning + 关 sqlite + 后续 JSONL-only + 记 1 次 error
  (sqlite 失败不该中断 research 流程)

## 5. safety check (静态 + 运行时)

- [x] 0 wallet / signer / tx / mutation in real code
- [x] 0 bridge call
- [x] 写路径仅 `data/lp_long_horizon/<run_id>/` (caller 强制约束)
- [x] 不写 production / shadow / live / dryrun
- [x] self_check 在 import 时跑 AST+tokenize 扫描
- [x] sqlite 失败 graceful fallback

## 6. 单元测试 (Stage L)

- `test_research_store_init_creates_sqlite`
- `test_research_store_write_pool_snapshot`
- `test_research_store_write_quote_snapshot_6_notionals`
- `test_research_store_write_fee_velocity_5_windows`
- `test_research_store_write_market_regime_7`
- `test_research_store_jsonl_only_when_sqlite_fails`
- `test_research_store_close`
- `test_research_store_real_data_int_coercion`
- `test_research_store_summary`
- `test_research_store_self_check_passes`

## 7. 与上一阶段 schema 对齐 (RESEARCH_ONLY_SCHEMA_CN.md)

| 表 | DDL 字段 | R0 schema 字段 | 状态 |
|---|---|---|---|
| pool_snapshots | 22 字段 | 16 字段 + 6 extra (real_data/data_source/...) | ✅ + extra |
| quote_snapshots | 13 字段 | 11 字段 + 2 extra | ✅ + extra |
| fee_velocity | 10 字段 | 7 字段 + 3 extra (real_data/data_source/r0_phase_status) | ✅ + extra |
| liquidity_distribution | 10 字段 | 8 字段 + 2 extra | ✅ + extra |
| market_regime | 9 字段 | 7 字段 + 2 extra | ✅ + extra |
| future_actual_fee_accrual | 24 字段 | 23 字段 + 1 extra (real_data) | ✅ + extra |

## 8. 结论

SQLite + JSONL 双写 + graceful fallback 实装. 6 表 DDL + 6 索引. 不引入
wallet / tx / mutation. Stage H 通过. 进入 Stage I (real_data smoke runner).
