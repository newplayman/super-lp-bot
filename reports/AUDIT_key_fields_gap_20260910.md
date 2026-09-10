# AUDIT：Stage A `STAGE_A_KEY_FIELDS_INCOMPLETE` 到底缺什么、怎么补（只调研）

- 任务：RH-02bh（spec `docs/specs/20260910_RH-02bh_key_fields_gap.md`）
- 性质：**只调研**。不改任何代码、不采任何数据、不动 `.db`、不发真实网络请求、不执行任何 git 命令。
- 数据快照：`reports/lp_rh/scanner.db` 表 `rh_market_states`，as-of **2026-09-10T01:30Z**，约 **10,311 行**（采集器仍在以 ~15s/行 实时增长，下文数字为该时刻快照）。
- 方法：本机无 `sqlite3` CLI，全部用 python `sqlite3` 模块以 `file:...?mode=ro` 只读打开；闸门行为用 `python3 scripts/lp_rh_readiness_v1_readonly.py --db ... --out /tmp/... --asset-address 0x52e6...` 只读运行取证（输出在 `/tmp`，未落仓库）。

## 结论速览（TL;DR）

1. 闸门 `STAGE_A_KEY_COLUMNS` 只查 **5 列**：`reference_mid`、`sample_time`、`session`、`fee_growth_global_0`、`fee_growth_global_1`，阈值各 ≥ 0.99。
2. 当前唯一卡住闸门的是 **`fee_growth_global_0/1`（21.83% < 99%）**；`reference_mid` 99.52% 勉强过线，其余 3 列 100%。
3. `fee_growth` 的低非空率是**纯历史缺口**：该列 09-09 16:05:55 才加入，**加列之后非空率 99.87%**（3 个 NULL 里 2 个是 `CHAIN_DEGRADED`、1 个是瞬时 RPC 失败）。**采集器没有 bug。**
4. 但闸门 `audit_key_field_health` 按**全表**统计、**无时间窗口**，加列前的 ~8,057 行永远无法回填。靠"等时间"稀释到 99% 需 ~914,691 行 ≈ **158.8 天**，不现实。→ 真正要动手的是**改闸门的统计窗口**，不是改采集器。
5. 其余 <100% 列（`reference_bid/ask`、`multiplier_human`、`oracle_paused`、`source_event_time`、`derived_block_*`）**都不在闸门检查范围内**，不是当前 blocker；其中 `reference_bid/ask` 属 B 类（需 REST 源）、`multiplier_human`/`oracle_paused` 属 C 类（对 crypto CORE 池语义未定义，需产品决策）。

---

## 一、逐列现状（按非空率从低到高）

`rh_market_states` 共 17 列。快照 10,311 行。

| 列 | 非空率 | 非空数 | 不同值数 | 最早→最新非空 | 类别 |
|---|---|---|---|---|---|
| `reference_bid` | 0.00% | 0 | 0 | — | **B**（兼 C） |
| `reference_ask` | 0.00% | 0 | 0 | — | **B**（兼 C） |
| `multiplier_human` | 0.00% | 0 | 0 | — | **C** |
| `oracle_paused` | 0.00% | 0 | 0 | — | **C/D** |
| `fee_growth_global_0` | 21.83% | 2251 | 2251 | 09-09T16:05:55 → 09-10T01:30 | **A（历史缺口，非 bug）** |
| `fee_growth_global_1` | 21.83% | 2251 | 2251 | 09-09T16:05:55 → 09-10T01:30 | **A（历史缺口，非 bug）** |
| `source_event_time` | 33.36% | 3440 | 3438 | 09-09T10:51:08 → 09-10T01:30 | **A（历史缺口，非 bug）** |
| `derived_block_hash` | 35.36% | 3646 | 3644 | 09-09T09:59:47 → 09-10T01:30 | **A（历史缺口，非 bug）** |
| `derived_block_number` | 35.53% | 3663 | 3655 | 09-09T09:59:47 → 09-10T01:30 | **A（历史缺口，非 bug）** |
| `reference_age_secs` | 99.40% | 10249 | 27 | 09-08T05:15 → 09-10T01:30 | **D（正确为空）** |
| `reference_mid` | 99.52% | 10261 | 10260 | 09-08T05:15 → 09-10T01:30 | **D（正确为空）** |
| `asset_address` | 100.00% | 10311 | 1 | 09-08T05:15 → 09-10T01:30 | — |
| `chain_id` | 100.00% | 10311 | 1 | 同上 | — |
| `health_flags_json` | 100.00% | 10311 | 2 | 同上 | — |
| `sample_time` | 100.00% | 10311 | 10311 | 同上 | — |
| `session` | 100.00% | 10311 | 5 | 同上 | — |
| `source_payload_hash` | 100.00% | 10311 | 10301 | 同上 | — |

### 逐列判定依据

**`reference_bid` / `reference_ask`（0%）— B 类（兼 C）**
- 采集器 `scripts/lp_rh_collector_v1_readonly.py:343` 硬编码 `"reference_bid": None, "reference_ask": None`；docstring（L10-15）明写 *"This collector makes no REST calls"*。
- 取值路径**存在但不在本采集器**：另一条只读管线 `scripts/lp_rh_premium_recorder_v1_readonly.py:36` 用 `PRICES_URL = "https://api.robinhood.com/rhj/prices"`（无 API key，仅 User-Agent；L160 注释 ~480 免费请求/天，429 限流退避）采 bid/ask，实测 `reports/lp_rh/premium.db` 里 `reference_bid/ask/mid` 非空率 ~98.6%。
- **但** premium recorder 只覆盖 6 个**股票** symbol（AMC/GLD/NVDA/QQQ/SGOV/SPY），**不覆盖** Stage A 观察的 WETH/USDG **CORE 池**。CORE 池是 crypto 池，REST 端点是否提供它的 bid/ask 未验证 → 叠加 **C 类**（PRD 未规定 crypto CORE 池的 bid/ask 该填什么）。
- 判定：**B 类**（需接 REST 源，采集器当前明确不做）+ **C 类**子问题（源是否对 CORE 池有此数据，需产品决策）。**不在闸门 5 列内，非当前 blocker。**

**`multiplier_human`（0%）— C 类**
- 采集器 `lp_rh_collector_v1_readonly.py:348` 硬编码 `"multiplier_human": None`。
- PRD L434（§9.2）：`multiplier_human = onchain_uiMultiplier_raw / 10^18 或 Decimal(api.currentMultiplier)` —— 这是**股票 token** 概念。CORE 池是 WETH/USDG（crypto），无对应 on-chain `uiMultiplier`，语义未定义。
- 判定：**C 类**（语义未定义，需用户产品决策）。建议定义见 §三。

**`oracle_paused`（0%）— C/D 类**
- 采集器 `lp_rh_collector_v1_readonly.py:348` 硬编码 `"oracle_paused": None`。
- PRD L468（§9.4）把 `ORACLE_PAUSED` 列为 HealthFlags 之一。但 Uniswap V3 池用 TWAP，无传统可暂停的 price oracle；对 crypto CORE 池"oracle 是否暂停"语义未定义 / 可能 N/A。
- 判定：**C 类**（语义未定义）/ **D 类**（该场景本就不该有值）。需产品决策。

**`fee_growth_global_0/1`（21.83%）— A 类（历史缺口，非 bug）**
- 采集器 `lp_rh_collector_v1_readonly.py:243-251` 经 `eth_call` 读 `feeGrowthGlobal0/1X128`，失败置 None —— **有 writer、有取值路径、且现在正常工作**。
- 低非空率纯因**列 09-09 16:05:55 才加入**：加列前 ~8,057 行物理上不可能有值。
- **加列之后非空率 99.87%**（2251/2254）。3 个 NULL：`09-09T18:05:56`(RTH,`CHAIN_DEGRADED`)、`09-09T22:11:12`(POSTMARKET,`[]`)、`09-10T01:01:05`(OVERNIGHT,`CHAIN_DEGRADED`) —— 2 个是链降级（正确为空）、1 个是瞬时 RPC 失败。
- 判定：**A 类**（有 writer 有路径且值在进），但缺口是**历史/部署产物**，不是采集器缺陷。详见 §三 特别分析。

**`source_event_time`（33.36%）/ `derived_block_hash`（35.36%）/ `derived_block_number`（35.53%）— A 类（历史缺口，非 bug）**
- 分别由 `lp_rh_collector_v1_readonly.py:305-308`（块时间戳）、`274-283`（`eth_getBlockByNumber`）写入，**有 writer 有路径且现在正常**。
- 三列分别在 09-09 10:51:08 / 09-09 09:59:47 / 09-09 09:59:47 加入，加列前无值 → 纯历史缺口。
- 判定：**A 类（历史缺口，非 bug）**。**不在闸门 5 列内，非当前 blocker**；若将来纳入闸门，需与 fee_growth 相同的窗口修复。

**`reference_age_secs`（99.40%）/ `reference_mid`（99.52%）— D 类（正确为空）**
- `reference_mid` 由 sqrtPriceX96 推导；`reference_age_secs = now - block_timestamp`（`lp_rh_collector_v1_readonly.py:323-329`），无价格/时间戳时置 None。
- 实测 `reference_mid` 的 **50 个 NULL 行 100% 带 `health_flags_json=["CHAIN_DEGRADED"]`** → 链降级时推不出价格，**正确为空**。
- 判定：**D 类**。无需补。

---

## 二、闸门实际要求哪几列

`scripts/lp_rh_readiness_v1_readonly.py`：

- L46-52 `STAGE_A_KEY_COLUMNS = ("reference_mid", "sample_time", "session", "fee_growth_global_0", "fee_growth_global_1")` —— **只查这 5 列**。
- L53 `STAGE_A_KEY_COLUMNS_MIN_RATIO = Decimal("0.99")` —— 每列非空率须 ≥ 0.99。
- L331 `audit_key_field_health(conn, *, asset_address)`：按 `asset_address` 过滤后，对每列算 `non_null_count / total_rows`，**全部 ≥ 0.99 才 passed**。

**关键实现细节（决定本包结论）**：L345-349 的 `total_rows` 是 `COUNT(*) ... WHERE asset_address = ?`，即**全表行数**；L364-369 的 `non_null_count` 也是全表口径。**没有任何时间窗口 / since 过滤**。由于本库 `asset_address` 只有一个值（CORE 池），等价于对**整张表**统计。

### 5 列现状（as-of 01:30Z，全表口径）

| 列 | 非空率 | 阈值 0.99 | 结果 |
|---|---|---|---|
| `reference_mid` | 99.52% | ≥99% | **PASS**（余量仅 0.52%） |
| `sample_time` | 100.00% | ≥99% | PASS |
| `session` | 100.00% | ≥99% | PASS |
| `fee_growth_global_0` | 21.83% | ≥99% | **FAIL** |
| `fee_growth_global_1` | 21.83% | ≥99% | **FAIL** |

**当前真正卡住闸门的是 `fee_growth_global_0/1`。** `reference_mid` 虽勉强过线（99.52%），但余量只有 0.52%，且其 NULL 全部是 `CHAIN_DEGRADED`（正确为空）——若链降级占比再升一点就会跌破 99%，属**脆弱 PASS**，建议一并纳入窗口修复。

> 注：`reference_bid/ask`、`multiplier_human`、`oracle_paused`、`source_event_time`、`derived_block_*` 虽然 <100%，但**都不在 `STAGE_A_KEY_COLUMNS` 里**，对 `STAGE_A_KEY_FIELDS_INCOMPLETE` 无影响。

---

## 三、补齐路径（按代价排序）

### 3.1 卡闸门的列：`fee_growth_global_0/1`（特别分析）

**先回答 spec 的核心问题：这是"等时间"还是"要修"？**

- **采集器层面：不用修。** 加列（09-09 16:05:55）之后非空率 **99.87%**（2251/2254），3 个 NULL 中 2 个 `CHAIN_DEGRADED`（正确为空）、1 个瞬时 RPC 失败。取值路径（`eth_call` 读 `feeGrowthGlobal0/1X128`）工作正常。
- **闸门层面：要动手。** `audit_key_field_health` 按**全表**统计、无时间窗口。加列前的 ~8,057 行物理上永远没有 fee_growth，成为**永久性拖累**。

**"等时间"到底要等多久？** 设新行填充率 ≈ 0.9987，解 `(2251 + 0.9987·x) / (10311 + x) ≥ 0.99`：

- 需新增 **x ≈ 914,691 行**；按 ~15s/行 ≈ **158.8 天**。
- 结论：**"等时间"在工程上不成立**（Stage A 是 72h 闸门，等 5 个月无意义）。

**补齐路径（按代价从低到高）：**

1. **【推荐·代价低】改闸门统计窗口**：让 `audit_key_field_health` 只在"该列可被填充的窗口"内统计。两种等价做法：
   - (a) 按**部署感知**：只统计 `sample_time ≥ <该列首次非空时刻>`（fee_growth 即 `≥ 09-09T16:05:55Z`）的行 → 立即 99.87% PASS；
   - (b) 按**滚动窗口**：只统计最近 N 小时（N 需晚于加列时刻，如最近 24h）→ 同样 ~99.87%。
   - 动哪里：`scripts/lp_rh_readiness_v1_readonly.py:345-369`（`total_rows` 与 `non_null_count` 两个 SQL 加时间下界）+ 配套 `tests/test_lp_rh_readiness_v1_readonly.py`。
   - 代价：**低**（改 1 个函数 + 测试，无数据/网络/链改动）。
   - 附带收益：`reference_mid` 的脆弱 PASS（99.52%）在窗口内会升到 ~99.9%+，更稳。
2. **【不现实】等时间**：全表稀释到 99% 需 ~914,691 行 ≈ 158.8 天。
3. **【不可能】回填历史**：加列前的样本当时未采集 fee_growth，无法回填。

> 判定：`fee_growth_global_0/1` 属 **"要动手"，但动手的对象是闸门（统计窗口），不是采集器。** 这是本包最重要的结论。

### 3.2 非卡闸门列（供完整性，均非当前 blocker）

| 列 | 类别 | 补齐路径 | 代价 |
|---|---|---|---|
| `source_event_time` / `derived_block_hash` / `derived_block_number` | A（历史缺口） | 采集器已正常；若将来纳入闸门，需与 fee_growth 相同的窗口修复 | 低（仅当纳入闸门） |
| `reference_bid` / `reference_ask` | B（兼 C） | 需接 REST 源（`api.robinhood.com/rhj/prices`，无 key、~480 免费请求/天、429 限流）。**但**该源实测只覆盖 6 个股票 symbol，不覆盖 WETH/USDG CORE 池 → 先需产品决策"CORE 池要不要外部 bid/ask"，再决定接不接源 | 中（含产品决策 + 可能接源） |
| `multiplier_human` | C | PRD L434 定义为股票 token 概念；对 crypto CORE 池语义未定义 → **需用户产品决策** | 决策（见下建议定义） |
| `oracle_paused` | C/D | PRD L468 列为 HealthFlags；对 Uniswap V3（TWAP，无传统 oracle）语义未定义/N/A → **需用户产品决策** | 决策（见下建议定义） |
| `reference_mid` / `reference_age_secs` | D | 正确为空（`CHAIN_DEGRADED` 时无价格/时间戳），无需补 | 0 |

**C 类建议定义（供用户裁决，非本包决定）：**
- `multiplier_human`：建议对 crypto CORE 池**恒置 NULL 并在 schema 注释标明 "N/A for non-stock pools"**，或定义为一个恒 1.0 的占位（表示无杠杆/无换算）。倾向前者（NULL + 注释），避免伪造数值。
- `oracle_paused`：建议对 crypto CORE 池**恒置 `false`/NULL 并注释 "no external oracle; TWAP-based"**；若未来接入外部 oracle 再启用。
- 两者都属"该场景本就不该有值"，与 D 类边界相邻；列 C 是因为 PRD 未明文规定 crypto 池的取值，需产品拍板"是 NULL 还是占位"。

---

## 四、Stage A 距离通过还差多少

只读运行闸门（as-of 01:29Z）实测 Stage A **5 个 blocker**：
`HOURS_COVERED_INSUFFICIENT`、`COVERAGE_INSUFFICIENT`、`STAGE_A_SYNTHETIC_TESTS_UNKNOWN`、`STAGE_A_KEY_FIELDS_INCOMPLETE`、`STAGE_A_POOL_NOT_ATTESTED`。

| Blocker | 当前值 | 等时间 / 要动手 | 若要动手，动什么 | 预估代价 |
|---|---|---|---|---|
| `HOURS_COVERED_INSUFFICIENT` | 44.24 / 72 h | **等时间** | 无。09-08 05:15 起算，满 72h = 09-11 05:15（约 28h 后到） | 0（纯等待） |
| `COVERAGE_INSUFFICIENT` | 0.9709 < 0.99 | **等时间（边界）/ 可能要动手** | 覆盖率 = 实际样本 / (时间跨度/15s)。早期 6h 桶 89.7% 拖累全表；近期 6h 桶 96–100%。随早期数据被稀释，全表比率趋近 ~98.7%。**可能需与 key-fields 相同的窗口修复**才能稳过 99% | 低（若需窗口修复）/ 0（若自然达标） |
| `STAGE_A_SYNTHETIC_TESTS_UNKNOWN` | 未标记 passed | **要动手** | 运行 PRD §21.1 条件 2 的合成日历/异常测试，并以 `--synthetic-tests-passed` 传入闸门 | 中（需编写/运行合成测试） |
| `STAGE_A_KEY_FIELDS_INCOMPLETE` | fee_growth 21.83% < 99% | **要动手** | 改 `audit_key_field_health` 统计窗口（§3.1 路径 1）；加列后 99.87% 立即 PASS | **低**（改 1 函数 + 测试） |
| `STAGE_A_POOL_NOT_ATTESTED` | 池在 registry、不在 attestations | **要动手** | 池 `0x52e6...` 在 `rh_pool_registry`（1 行匹配）但**不在** `rh_contract_attestations`（0 匹配）。需为该池补 contract attestation（`code_hash`/`abi_version`/`implementation`/`attestation_status`） | 中（需采集并写入 attestation 证据） |

**小结**：5 个 blocker 中
- **1 个纯等时间**（hours，~28h 后自然达成）；
- **1 个边界等时间**（coverage，可能需窗口修复）；
- **3 个要动手**（synthetic tests、key-fields 窗口、pool attestation）。

其中**代价最低、且是本包主题**的是 `STAGE_A_KEY_FIELDS_INCOMPLETE`：改闸门统计窗口即可，**无需改采集器、无需采数据、无需等 158 天**。

---

## 附：取证命令（可复现，全部只读）

```bash
# 逐列非空率 / 不同值 / 首末非空（python sqlite3，只读）
python3 -c "import sqlite3; c=sqlite3.connect('file:reports/lp_rh/scanner.db?mode=ro',uri=True); ..."

# fee_growth 加列后非空率
#   WHERE sample_time >= '2026-09-09T16:05:55Z'  →  2251/2254 = 99.87%

# reference_mid NULL 与 CHAIN_DEGRADED 相关性
#   reference_mid IS NULL 共 50 行，100% 带 ["CHAIN_DEGRADED"]

# 闸门 5 blocker + key_field_health（只读运行，输出落 /tmp）
python3 scripts/lp_rh_readiness_v1_readonly.py \
  --db reports/lp_rh/scanner.db --out /tmp/readiness_out.md \
  --asset-address 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
#   → Stage A blockers: HOURS_COVERED_INSUFFICIENT, COVERAGE_INSUFFICIENT,
#     STAGE_A_SYNTHETIC_TESTS_UNKNOWN, STAGE_A_KEY_FIELDS_INCOMPLETE, STAGE_A_POOL_NOT_ATTESTED
```

## 未完成项与原因

- **未验证 `api.robinhood.com/rhj/prices` 是否返回 WETH/USDG CORE 池的 bid/ask**：spec 纪律禁止发真实网络请求，故仅依据 premium recorder 的既有代码与 `premium.db` 实测（只覆盖 6 个股票 symbol）推断。若后续要坐实 B 类路径，需一次受控的只读网络探测（超出本包授权）。
- **未实际运行合成日历/异常测试**：属 `STAGE_A_SYNTHETIC_TESTS_UNKNOWN` 的补齐动作，是"要动手"项，不在本"只调研"包范围内。
- **C 类（`multiplier_human`/`oracle_paused`）的最终取值**：需用户产品决策，本包仅给出建议定义，未代为拍板。
