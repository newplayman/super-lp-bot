# RH-02L：接受 REST `generatedAt` 作新鲜度依据（用户已授权）

## 授权与边界

用户 2026-09-09 拍板：**接受 REST `generatedAt`**，附两个条件——
1. **单点数据源风险必须显式记进 attestation**；
2. **REST 失联时立刻 fail-closed**。

本包只建**下游裁决能力**，**不改** `lp_rh_market_session_v1_readonly.py`
（接线是下一包，那个模块有 4113 个测试依赖，单独一包才可验）。

## 现有接口（已用 `ast` 抽出，**不要再 grep**）

`scripts/lp_rh_market_session_v1_readonly.py`（239 行）：
```
HEALTH_FLAGS = ('HALT','CORP_ACTION','ORACLE_PAUSED','ORACLE_UNAVAILABLE',
                'ORACLE_STALE','API_STALE','SOURCE_DISAGREEMENT', ...)
def evaluate_health(*, oracle_paused, oracle_updated_at, api_generated_at, now,
                    halt, corp_action_pending, sources_disagree, chain_degraded,
                    oracle_heartbeat_secs: int = 36) -> list[str]
def stale_reason(session: str, oracle_age_secs, heartbeat_secs) -> str
def allows_new_position(session: str, flags: list[str]) -> bool
```

## REST 契约（实测硬事实，直接用，不要按 PRD 假设写）

`GET https://api.robinhood.com/rhj/prices` → 容器键是 **`quotes`**（不是 `prices`）。
字段 `tokenSymbol` / `bid` / `ask` / `generatedAt`（**纳秒，9 位小数**）/
`isTradingHalt` / `mintBurnUsdVolume`。**报价龄实测 15–20 秒**；突发请求 429，约 95 秒恢复。
RH 链股票代币**不引用任何链上价格源**，`oracle_updated_at` 恒为 `None`。

## 只新建两个文件（一包一个实质文件）

### 1. `scripts/lp_rh_reference_freshness_v1_readonly.py`（≤260 行，不联网）

- `MAX_REST_AGE_SECS = 60`
  注释写明出处：**实测报价龄 15–20 秒，取 3 倍余量**；不是拍脑袋常量。
- `parse_generated_at(value) -> Optional[datetime]`
  接受纳秒 9 位小数的 ISO 串、`int`/`float` 纪元秒、`datetime`。
  **无法解析 → `None`，绝不返回 `now`**。
- `resolve_freshness(*, oracle_updated_at, api_generated_at, now,
  max_rest_age_secs=MAX_REST_AGE_SECS, oracle_heartbeat_secs=36) -> dict`
  返回 `{"source","age_secs","verdict","single_source_risk","reasons"}`：
  `source` ∈ `ONCHAIN_ORACLE` / `REST_GENERATED_AT` / `NONE`；
  `verdict` ∈ `FRESH` / `STALE` / `UNAVAILABLE`。
  - oracle 可用且龄 ≤ `oracle_heartbeat_secs` → `ONCHAIN_ORACLE` / `FRESH`,
    `single_source_risk=False`（链上源人人可验）。
  - oracle 为 `None`、REST 龄 ≤ `max_rest_age_secs` → `REST_GENERATED_AT` /
    `FRESH`，**`single_source_risk=True`**。
  - **★oracle 为 `None` 且 REST 也为 `None`/不可解析 → `NONE` / `UNAVAILABLE`★**
    （fail-closed，绝不放行）。
  - **★oracle 为 `None` 且 REST 超龄 → `REST_GENERATED_AT` / `STALE`★**（fail-closed）。
  - 时间戳在**未来**超过 5 秒 → `UNAVAILABLE`，`reasons` 含 `FUTURE_TIMESTAMP`
    （服务端时钟不可信时不放行）。
- `build_attestation(resolution, *, now, chain_id, endpoint) -> dict`
  必含键：`single_source_risk`（bool）、`source`、`age_secs`、`verdict`、
  `endpoint`、`chain_id`、`authorized_by`（固定串 `"user-decision-20260909"`）、
  `fail_closed_on_loss`（**恒 `True`**）、`attested_at`。
  **`single_source_risk` 为真当且仅当 `source == "REST_GENERATED_AT"`。**
- `main()`：`--resolution-json --out`，纯离线。

### 2. `tests/test_lp_rh_reference_freshness_v1_readonly.py`（≤240 行，**≥16 测试**）

顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
**不许联网**，全部用注入的 `now` 与构造的时间戳。必测：

- oracle 可用且新鲜 → `ONCHAIN_ORACLE` / `FRESH` 且 `single_source_risk is False`。
- oracle 为 `None` + REST 龄 20 秒 → `REST_GENERATED_AT` / `FRESH`
  且 **`single_source_risk is True`**。
- **★两者都为 `None` → `UNAVAILABLE`，断言 `verdict != "FRESH"`★**
- **★REST 龄 120 秒（> 60）→ `STALE`，断言 `verdict != "FRESH"`★**
- REST 时间戳不可解析（乱串）→ `UNAVAILABLE`，**不是** `FRESH`。
- REST 时间戳在未来 60 秒 → `UNAVAILABLE` 且 `reasons` 含 `FUTURE_TIMESTAMP`。
- 未来 2 秒（≤5 秒容差）→ 仍 `FRESH`。
- `parse_generated_at` 解析纳秒 9 位小数串，且**保留亚秒精度**。
- `parse_generated_at` 对 `None` / `""` / `"abc"` 各返回 `None`（三条断言）。
- 边界：REST 龄**恰为** 60 秒 → 归属断言一次；恰为 61 秒 → `STALE`。
- oracle 存在但超 heartbeat（龄 100 > 36）且 REST 新鲜 →
  断言 source 的归属与 `single_source_risk` 一致（不得两个源都标 False）。
- `build_attestation` 在 REST 源下 `single_source_risk is True`。
- `build_attestation` 在链上源下 `single_source_risk is False`。
- `build_attestation` **恒含 `fail_closed_on_loss is True`**（两种源各断言一次）。
- `build_attestation` 含 `authorized_by == "user-decision-20260909"`。
- `main` 不带 `--out` 时不写任何文件且返回 0。

## 不许动
不改 `lp_rh_market_session_v1_readonly.py`、不改任何现有测试、不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_reference_freshness_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥16 全绿；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
