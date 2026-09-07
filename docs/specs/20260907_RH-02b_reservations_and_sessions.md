# RH-02b：资金桶原子预占 + 市场时段/健康双维度（离线可测）

## 背景（一段）

PRD v1.1 §16.3 要求资金占用必须在**数据库事务内原子完成**：检查剩余额度、插入 reservation、生成 intent 三步同一事务，两条候选不得各自读到同一份可用额度后分别全额占用（用例 **T27**）。§9.4 要求市场时段与健康状态用**两个独立维度**表达，不得塞进一个互斥枚举而丢信息；`2026-09-07` 是美国劳动节休市，纽约时间盘中时钟必须判 `HOLIDAY` 而非 `RTH`（**T15**）；夏令时切换、提前收市、周末的 UTC 映射不得偏移一小时（**T16**）。存储层已由 RH-02a 提供（`scripts/lp_rh_store_v1_readonly.py`，16 张表，`rh_bucket_reservations` 与 `rh_market_states` 已在其中）。本包只做这两块纯逻辑，**不联网、不采集、不写 `reports/lp_rh/`**。

## 新增文件

1. `scripts/lp_rh_bucket_ledger_v1_readonly.py`（**≤ 250 行**，分次写，每次 ≤150 行）
   - 顶部照抄仓库通行 sys.path 引导（同 `lp_scanner_daemon_v1_readonly.py:38-40`）；`from scripts.lp_rh_store_v1_readonly import ...` 复用 `open_store` / `migrate` / `assert_decimal_text` / `assert_utc_rfc3339`。
   - **金额一律用 `decimal.Decimal`**，入库转规范化字符串；禁止 float。
   - `BUCKETS = ("CORE", "STOCK", "MEME")`；`POLICY_ID = "rh_50_30_20_proposed_v1"`；权重 `{"CORE": "0.50", "STOCK": "0.30", "MEME": "0.20"}`；桶内 active 上限 `{"CORE": "0.85", "STOCK": "0.70", "MEME": "0.40"}`（PRD §6.1）。
   - `bucket_budget(capital_usd: Decimal, bucket) -> Decimal` = `capital × weight`；`bucket_active_cap(capital_usd, bucket) -> Decimal` = `budget × active_fraction`。
   - `reserved_total(conn, bucket, policy_version) -> Decimal`：对 `rh_bucket_reservations` 中 `status` 属于 **`("PENDING","CONFIRMED","BROADCAST_UNKNOWN")`** 的行求和（`released_at IS NULL`）。**`BROADCAST_UNKNOWN` 必须计入占用**（PRD §16.3：不释放）。
   - `try_reserve(conn, *, intent_id, bucket, amount_usd: Decimal, capital_usd: Decimal, policy_version=POLICY_ID, now: str) -> dict`：
     - 在 **`BEGIN IMMEDIATE`** 事务内：读 `reserved_total` → 计算 `room = active_cap - reserved` → 若 `amount > room` 则 `ROLLBACK` 并返回 `{"granted": False, "reason": "BUCKET_ACTIVE_CAP_EXCEEDED", "room": str(room)}`；否则插入 `rh_bucket_reservations`（`status="PENDING"`）并 `COMMIT`，返回 `{"granted": True, "reservation_id": intent_id, "room_after": str(room - amount)}`。
     - `bucket` 不在 `BUCKETS` → `ValueError("UNKNOWN_BUCKET")`；`amount_usd <= 0` → `ValueError("NON_POSITIVE_RESERVATION")`；重复 `intent_id` → `sqlite3.IntegrityError` 透传。
   - `release(conn, intent_id, *, now, reason) -> bool`：把 status 置 `RELEASED` 并写 `released_at`；**若当前 status 为 `BROADCAST_UNKNOWN` 则拒绝释放**，抛 `ValueError("CANNOT_RELEASE_BROADCAST_UNKNOWN")`（PRD §16.3、用例 T51）。
   - `set_status(conn, intent_id, status, *, now) -> None`：状态白名单 `("PENDING","CONFIRMED","BROADCAST_UNKNOWN","RELEASED","EXPIRED")`，其它抛 `ValueError`。
   - `capital_policy_conflict(capital_usd: Decimal, *, legacy_min_position: Decimal) -> dict`：当 `bucket_active_cap(capital, "CORE") < legacy_min_position` 时返回 `{"conflict": True, "code": "CAPITAL_POLICY_CONFLICT", "core_cap": "42.5", "legacy_min": "50"}`（C=100 时应精确得到 42.5 与 50，用例 **T25**）。**该函数只报告冲突，绝不自动调整任何金额。**
   - 在 `migrate` 调用点前加一行防御：若 `conn.in_transaction` 为真则抛 `RuntimeError("MIGRATE_INSIDE_TRANSACTION")`（RH-02a 遗留观察）。**这一行加在本文件的辅助函数里，不要去改 `lp_rh_store_v1_readonly.py`。**
2. `scripts/lp_rh_market_session_v1_readonly.py`（**≤ 250 行**）
   - `Session` 取值：`RTH | PREMARKET | POSTMARKET | OVERNIGHT | CLOSED_WEEKDAY | WEEKEND | HOLIDAY | UNKNOWN`（PRD §9.4）。
   - `HealthFlag` 取值集合：`HALT, CORP_ACTION, ORACLE_PAUSED, ORACLE_STALE, API_STALE, SOURCE_DISAGREEMENT, CHAIN_DEGRADED`。**Session 与 HealthFlags 是两个独立返回值，绝不合并成一个枚举。**
   - 内置**有版本号的**交易日历常量 `CALENDAR_VERSION = "nyse-2026-v1"`，含 2026 年 NYSE 全休市日（至少：01-01 元旦、01-19 马丁路德金日、02-16 华盛顿诞辰、04-03 耶稣受难日、05-25 阵亡将士纪念日、06-19 六月节、07-03 独立日提前收市观察日、07-04 独立日、**09-07 劳动节**、11-26 感恩节、11-27 感恩节次日提前收市、12-24 平安夜提前收市、12-25 圣诞）。提前收市日单列 `EARLY_CLOSE_DAYS`（13:00 ET 收市）。
   - `classify_session(dt_utc: datetime, *, calendar=None) -> tuple[str, dict]`：把 UTC 转 `America/New_York`（用 `zoneinfo.ZoneInfo`，Python 3.12 自带；**不得手写固定 -5/-4 偏移**）；周六周日 → `WEEKEND`；日历休市日 → `HOLIDAY`；工作日按 ET 时间分段 `04:00–09:30 PREMARKET`、`09:30–16:00 RTH`（提前收市日 `09:30–13:00`）、`16:00–20:00 POSTMARKET`、`20:00–04:00 OVERNIGHT`；无法判定 → `UNKNOWN`。第二个返回值是 `{"calendar_version":…, "et_local":…, "is_early_close":…}`。
   - `evaluate_health(*, oracle_paused, oracle_updated_at, api_generated_at, now, halt, corp_action_pending, sources_disagree, chain_degraded, oracle_heartbeat_secs=3600, api_stale_secs=300) -> list[str]`：按上面枚举返回**排序后的** flag 列表；`None` 输入视为未知，产生对应 flag 而非静默通过。
   - `stale_reason(session: str, oracle_age_secs, heartbeat_secs) -> str`：闭市时段返回 `EXPECTED_SESSION_CLOSED`，盘中超心跳返回 `STALE_WHILE_EXPECTED_LIVE`，正常返回 `FRESH`（PRD §9.4：两者都不放行新窄区间，但原因必须分开）。
   - `allows_new_position(session, flags) -> bool`：仅 `RTH` 且 flags 为空才 True（PRD §10.2 初始 LIVE 政策只考虑 RTH）。
   - 两个脚本各带 `main()`：`--self-test` 打印若干判定结果并退出 0（不联网、不写 db）。
3. `tests/test_lp_rh_bucket_ledger_v1_readonly.py`（≤ 250 行）与 `tests/test_lp_rh_market_session_v1_readonly.py`（≤ 250 行），全部用 `tmp_path` 临时库，**绝不碰 `reports/lp_rh/`**。

   bucket_ledger 至少 10 个测试：
   - C=100 时 `bucket_active_cap` 精确为 `CORE 42.5 / STOCK 21 / MEME 8`（用 `Decimal` 相等断言，不用 float 近似）。
   - **T27**：两次 `try_reserve` 争用同一额度——先占 40U（CORE，C=100，cap 42.5），再占 10U 必须 `granted=False` 且 `reason=="BUCKET_ACTIVE_CAP_EXCEEDED"`；库中只有 1 条 PENDING。
   - `BROADCAST_UNKNOWN` 状态的 reservation **计入**占用（占满后新 reserve 被拒）。
   - `release` 对 `BROADCAST_UNKNOWN` 抛 `CANNOT_RELEASE_BROADCAST_UNKNOWN`；对 `PENDING` 成功且释放后额度回到可用。
   - `try_reserve` 金额 0 或负数抛 `NON_POSITIVE_RESERVATION`；未知 bucket 抛 `UNKNOWN_BUCKET`；重复 intent_id 抛 `IntegrityError`。
   - **T25**：`capital_policy_conflict(Decimal("100"), legacy_min_position=Decimal("50"))` 返回 `conflict=True`、`core_cap="42.5"`，且函数**不修改**任何输入。
   - `migrate` 在已有未决事务的连接上抛 `MIGRATE_INSIDE_TRANSACTION`。

   market_session 至少 10 个测试：
   - **T15**：`2026-09-07 14:30 UTC`（= ET 10:30，星期一盘中）→ `HOLIDAY`，不是 `RTH`；且 `allows_new_position` 为 False。
   - **T16**：夏令时——`2026-03-08 14:35 UTC` 与 `2026-11-01 14:35 UTC` 分别落在 DST 切换前后，断言 ET 本地时间与 session 判定正确，UTC 转换不偏移一小时；提前收市日 `2026-11-27 18:30 UTC`（ET 13:30）→ `POSTMARKET` 而非 `RTH`；周六 → `WEEKEND`。
   - 正常工作日 ET 10:00 → `RTH`；ET 05:00 → `PREMARKET`；ET 17:00 → `POSTMARKET`；ET 22:00 → `OVERNIGHT`。
   - `evaluate_health` 在 `oracle_paused=True` 时含 `ORACLE_PAUSED`；`oracle_updated_at=None` 时含 `ORACLE_STALE`（未知不静默通过）；全正常时返回空列表。
   - `stale_reason` 三种取值各一例。
   - `allows_new_position("RTH", ["ORACLE_STALE"])` 为 False。
   - 返回的 session 与 flags 是**两个独立值**（断言函数签名/返回结构，不是一个合并枚举）。

## 不许动什么

- 不改任何现有脚本（**包括 `lp_rh_store_v1_readonly.py`**）、旧测试、配置、六常量、`.gitignore`。
- 不联网、不 curl/wget、不读 `.env*`、不 import web3/eth_account/solders/solana/requests/pytz（用标准库 `zoneinfo`）。
- 不写 `reports/lp_rh/`；不实现采集、RPC、终闸、NetCover。
- 不使用 float 表示金额；不手写时区偏移。
- 单次 Write/Edit ≤150 行或 6000 字符；不整读 >300 行文件，用 `grep -n` / `sed -n` 取片段。
- **不要用 TaskCreate/TaskUpdate 工具**，直接干活。

## 验收标准

- [ ] `git status --short` 新增只有 2 个脚本 + 2 个测试文件；`git diff --stat` 为空。
- [ ] 四个文件各自 ≤250 行。
- [ ] 两个新测试文件全绿，合计 ≥20 个测试。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` = 3174 + 新增数，0 failed，14 skipped。
- [ ] `2026-09-07 14:30 UTC` 判定为 `HOLIDAY`；C=100 的 CORE cap 为 `42.5` 且与旧 50U 下限冲突被显式报告。
- [ ] `grep -nE 'float\(|import pytz|timedelta\(hours=-[45]\)' scripts/lp_rh_bucket_ledger_v1_readonly.py scripts/lp_rh_market_session_v1_readonly.py` 零命中。

## 验证命令（仓库根 `/opt/lpbot/lp-bot-v3-origin-check`）

```bash
env -u PYTHONPATH /root/lp-bot/.venv/bin/python scripts/lp_rh_market_session_v1_readonly.py --self-test && echo SESSION_OK
env -u PYTHONPATH /root/lp-bot/.venv/bin/python scripts/lp_rh_bucket_ledger_v1_readonly.py --self-test && echo LEDGER_OK
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_bucket_ledger_v1_readonly.py tests/test_lp_rh_market_session_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
wc -l scripts/lp_rh_bucket_ledger_v1_readonly.py scripts/lp_rh_market_session_v1_readonly.py tests/test_lp_rh_bucket_ledger_v1_readonly.py tests/test_lp_rh_market_session_v1_readonly.py
git diff --stat; git status --short | grep -E 'lp_rh_(bucket|market)'
```
