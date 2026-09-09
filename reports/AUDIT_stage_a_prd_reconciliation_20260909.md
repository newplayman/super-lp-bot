# Stage A 毕业前证据链对照 PRD 逐条核账审计报告

**审计日期**：2026-09-09  
**审计执行**：只读独立审计员  
**审计范围**：
- PRD 依据：`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md`（重点关注 §21.1、§16.2、§18.3、§20 等）
- 闸门与脚本依据：`scripts/lp_rh_readiness_v1_readonly.py`、`scripts/lp_rh_coverage_audit_v1_readonly.py`、`scripts/lp_rh_column_health_v1_readonly.py` 等
- 证据库：`reports/lp_rh/scanner.db`（只读 SQLite 查询，无任何写入或进程变动）

---

# 一、结论摘要

| # | PRD §21.1 毕业条件 | PRD 行号 | 代码是否检查 (文件:行号) | 实测当前值 | 判定 |
|---|---|---|---|---|---|
| 1 | **72 小时正向观测时长** | L1062 | `scripts/lp_rh_readiness_v1_readonly.py:44-55` (`stage_a_status`) | 观测跨度约 40.6 小时 / 72 小时 | **FAIL**（时间未到） |
| 2 | **日历 / 异常的合成测试通过** | L1062 | 根本没在毕业闸门检查；仅作为单元测试存在 (`tests/test_lp_rh_market_session_v1_readonly.py` 等) | 闸门代码**未串联**任何合成测试结果 | **根本没检查** |
| 3 | **关键字段真实生产** | L1062 | 根本没在毕业闸门检查；`column_health` 仅为独立审计脚本，未接进 `readiness` | 10 列全 NULL（`reference_bid/ask`、`multiplier_human`、`oracle_paused` 等）；`fee_growth_global_0/1` 仅 9.2% 非空（有效数据仅 4 小时） | **根本没检查**（且实测数据严重缺失） |
| 4 | **身份和能力证据清楚** | L1062 | 根本没在毕业闸门检查；`readiness` 只查 `rh_market_states` | `rh_pool_registry` 仅 1 行（且缺 hooks/pool_id），`rh_assets` 194 行但全为股票（无池代币），`rh_contract_attestations` 387 行全为股票 beacon；当前被监控的 CORE 池合约**无任何 attestation 记录** | **根本没检查**（且核心证据缺位） |
| 5 | **数据质量可计算** | L1062 | `scripts/lp_rh_readiness_v1_readonly.py:108`（仅读 `rh_source_snapshots.quality`） | 4,204 条 snapshot `quality` 均为 `"OK"`，但此检查不属于 `stage_a["passed"]` 的准出条件 | **PARTIAL**（读了但不阻断 Stage A） |
| 6 | **RPC 预算可维持** | L1062 | `scripts/lp_rh_readiness_v1_readonly.py:114-118` (`budget_status`) | DB 约 7.9 MB / 软预算 2 GiB，但 `stage_a_status` **根本没把预算作为判定入参** | **根本没检查**（只在展示区显示） |
| 7 | **无不变量违反** | L1062 | 根本没在 `stage_a_status` 检查；`invariant_violations` 被放在了 `stage_b_status` (:74) | 现存多项不变量违背风险（如 `fee_growth` 覆盖不足导致收益无法闭环），Stage A 闸门完全放行 | **根本没检查** |
| 8 | **有效数据覆盖率 ≥99%** | L1064 | `scripts/lp_rh_readiness_v1_readonly.py:44-55` (`stage_a_status`) | 当前覆盖率约 **0.9678**（阈值 0.9900） | **FAIL**（需至第 90 小时方可稀释自愈至 99%） |
| 9 | **关键状态未知时新增模拟仓位次数 = 0** | L1064 | 根本没在毕业闸门检查；`stage_a_status` 不审计 `rh_shadow_positions` 或 `rh_gate_decisions` | 历史版本中 `session="UNKNOWN"` 或 `flags=["ORACLE_UNAVAILABLE"]` 时多次拦截，但未建立「未知状态开仓次数=0」的形式化闸门断言 | **根本没检查** |

---

# 二、逐条核账

### 1. 72 小时正向观测时长
- **PRD 要求**（L1062）：`至少72小时正向观察作为初始门槛`。
- **代码实现**：`scripts/lp_rh_readiness_v1_readonly.py:44-55`
  ```python
  def stage_a_status(*, first_sample, last_sample, expected_interval_secs, actual_samples, coverage_ratio):
      hours_covered = round((_to_datetime(last_sample) - _to_datetime(first_sample)).total_seconds() / 3600.0, 2)
      hours_pass = hours_covered >= STAGE_A_MIN_HOURS # 72.0
      ...
  ```
- **实测当前值**：
  - `first_sample`: `2026-09-07T18:29:43.905663Z`
  - `last_sample`: 约 `2026-09-09T11:05:xxZ`
  - `hours_covered`: **40.6 小时** / 72.0 小时。
- **判定**：**FAIL**（时间尚未满足）。

### 2. 日历 / 异常的合成测试通过
- **PRD 要求**（L1062）：`并通过日历／异常的合成测试`。
- **代码实现**：**根本没检查**。
  - `scripts/lp_rh_readiness_v1_readonly.py` 中 `stage_a_status` 和 `graduation_verdict` 均无任何针对 pytest 测试套件运行结果、合成测试 fixture 报告或用例通过状态的读取与断言。
  - 虽然离线测试 `tests/test_lp_rh_market_session_v1_readonly.py` 覆盖了夏令时与休市等合成数据，但该要求在自动化毕业判定链路中**完全缺失接线**。
- **判定**：**根本没检查**。

### 3. 关键字段真实生产
- **PRD 要求**（L1062, L591, L802）：`关键字段真实生产`、`不得只有表没有 writer`、`不能再次出现永远没被写出的字段`。
- **代码实现**：**根本没检查**。
  - 毕业判定脚本 `lp_rh_readiness_v1_readonly.py` 仅统计 `COUNT(*)`，完全不校验字段非空率。
  - 尽管 `scripts/lp_rh_column_health_v1_readonly.py` 实现了列健康扫描，但该脚本独立存在，**未被接入 readiness 或 graduation 判定**。
- **实测当前值**：
  - `rh_market_states` 共 9,737 行，其中 10 个列完全为 NULL（`reference_bid`、`reference_ask`、`multiplier_human`、`oracle_paused` 等非空率均为 0.00%）。
  - 最致命的是经济计算核心字段 `fee_growth_global_0` 和 `fee_growth_global_1`：非空行仅约 950 行（**非空率仅 9.7%**）。这意味着过去 40.6 小时中，**仅有最新 4 小时有真实费用增长数据**，前 36 小时数据无法用于真实收益评估。
- **判定**：**根本没检查**（实测状态为重大缺陷）。

### 4. 身份和能力证据清楚
- **PRD 要求**（L1062, L793-800, §7.4 L330-337）：`身份和能力证据清楚`。每个 venue 需具备 discovery 到 reconcile 的能力状态矩阵，且具有 evidence hash 与到期时间；合约与池需有同块 attestation。
- **代码实现**：**根本没检查**。
  - `scripts/lp_rh_readiness_v1_readonly.py:273-290` 在判定 Stage A 时，**只查询了 `rh_market_states`**。对 `rh_assets`、`rh_pool_registry`、`rh_contract_attestations` 三张证据表甚至没有一条 `SELECT`。
- **实测当前值**：
  - `rh_pool_registry`：仅 1 行（当前池），且 `hooks` 和 `pool_id` 均为 NULL。
  - `rh_assets`：194 行全为股票代币元数据（来自 Robinhood REST API），当前池交易的两个原生/代币（WETH、USDG）**不在 `rh_assets` 表中**。
  - `rh_contract_attestations`：387 行全为股票代币 beacon 的同块证明，**当前 CORE 资金池合约（0x52e6...）和代币合约没有任何链上字节码/ABI/实现 attestation**。
- **判定**：**根本没检查**。

### 5. 数据质量可计算
- **PRD 要求**（L1062, §8.1 L347）：`数据质量可计算`，保留 `source_event_time`、`fetched_at`、provider、schema、原始 payload hash、质量状态。
- **代码实现**：`scripts/lp_rh_readiness_v1_readonly.py:108`。
  - 仅做展示：`SELECT source, fetch_time, source_event_time, quality FROM rh_source_snapshots ORDER BY fetch_time DESC LIMIT 50`。
  - 但在 `stage_a_status` 计算中，**完全没有校验 quality 字段**（未断言 BAD/STALE 比例）。
- **实测当前值**：
  - `rh_source_snapshots` 中 `quality` 字段 100% 为 `"OK"`。
- **判定**：**PARTIAL**（虽有字段记录并在控制台展示，但未作为毕业准出硬性闸门）。

### 6. RPC 预算可维持
- **PRD 要求**（L1062, §18.2 L872）：`RPC预算可维持`，RH 数据软预算 2GiB，度量实际滞后与请求。
- **代码实现**：`scripts/lp_rh_readiness_v1_readonly.py:114-118` (`budget_status`)。
  - 仅返回 `{"used_bytes": ..., "limit_bytes": ..., "warning": ..., "over_budget": ...}` 并供 dashboard 打印。
  - `stage_a_status` 函数签名根本不接受 `budget_status`，**即使超预算也不会阻断 Stage A `passed=True`**。
- **实测当前值**：
  - 数据库大小 7.9 MB / 2,147,483,648 字节（软预算 2 GiB），占比 0.37%，预算完全健康。
- **判定**：**根本没检查**（只读展示，未形成闸门联动）。

### 7. 无不变量违反
- **PRD 要求**（L1062, §18.3 RH-INV-01~18）：`无不变量违反`。
- **代码实现**：**根本没检查**。
  - `scripts/lp_rh_readiness_v1_readonly.py` 把 `invariant_violations` 作为参数传给了 `stage_b_status(:74)`，而在 `stage_a_status(:44)` 中**完全没有该参数**。代码假设 Stage A 阶段不需要审计不变量。
- **实测当前值**：
  - 缺乏针对 RH-INV-01 ~ RH-INV-18 的自动化核验器。
- **判定**：**根本没检查**。

### 8. 有效数据覆盖率 ≥99%
- **PRD 要求**（L1064）：`被选中用于收益评估的窗口，有效数据覆盖≥99%`，分母必须是计划应观测的窗口。未达到覆盖要求时可继续采集，但不毕业。
- **代码实现**：`scripts/lp_rh_readiness_v1_readonly.py:44-55` 配合 `scripts/lp_rh_coverage_audit_v1_readonly.py:203-212`。
  - 严格以时间跨度 `(last - first) / interval` 作为分母。
- **实测当前值**：
  - 覆盖率当前实测为 **0.9678**（即 96.78% < 99.00%）。
  - 根据 `reports/rh_pivot/20260907T124500Z/STAGE_A_COVERAGE_FORECAST_20260909.md` 测算，由于早期每轮循环存在约 1 秒系统漂移，累积亏空约 52 分钟，必须连续满额采集至第 **87.5~90 小时**，方能将总窗口覆盖率稀释拉升至 99.03% 以上。
- **判定**：**FAIL**（当前覆盖率未达标）。

### 9. 关键状态未知时新增模拟仓位次数 = 0
- **PRD 要求**（L1064）：`关键状态未知时新增模拟仓位次数=0`。
- **代码实现**：**根本没检查**。
  - `lp_rh_readiness_v1_readonly.py` 没有任何对 `rh_shadow_positions` 开仓记录与其对应的 `rh_market_states` 健康标记（`health_flags_json` / `session`）进行关联对账的逻辑。
- **判定**：**根本没检查**。

---

# 三、五张证据表现状

在 `reports/lp_rh/scanner.db` 中对 PRD §16.2 规定的关键证据表进行实测审计：

| 表名 | 当前行数 | 关键列非空率 | PRD 明确完整性要求 | 现状核评 |
|---|---:|---|---|---|
| `rh_market_states` | **9,737** | `sample_time` (100%), `reference_mid` (99.4%), `reference_age_secs` (99.3%), `fee_growth_global_0/1` (**9.24%**), `reference_bid/ask` (**0%**), `multiplier_human` (**0%**), `oracle_paused` (**0%**) | PRD §16.2: `asset＋sample_time＋source_snapshot；session／health flags／reference；Strategy 与终闸，不得只有表没有 writer` | **严重缺损**：10 列完全全空。核心经济回放依赖的 `fee_growth` 列仅在最近约 4 小时有值。 |
| `rh_assets` | **194** | 全部 12 列均为 **100.00%** | PRD §16.2: `chain＋address＋metadata_version；uid、multiplier、status、能力／精度` | **范围偏差**：只存了 Robinhood 官方 194 个美股代币，**当前正向观测的 CORE 池底层资产（WETH / USDG）完全未入库**。 |
| `rh_contract_attestations` | **387** | `address`, `block_hash`, `policy_version`, `created_at` (100%); `abi_version` (**0%**), `evidence_json` (**0%**), `expires_at` (**0%**) | PRD §16.2: `chain＋address＋block_hash＋policy；code／implementation／ABI 证据；池准入与执行白名单` | **核心缺位**：387 行全为股票 beacon 合约证明，**当前正向观测的 Uniswap V3 Pool 合约地址（0x52e6...）无任何 attestation 记录**；且 3 个关键列 100% 全空。 |
| `rh_pool_registry` | **1** | `chain_id`, `protocol`, `pool_key`, `pool_address`, `token0`, `token1`, `fee`, `tick_spacing` (100%); `pool_id` (**0%**), `hooks` (**0%**) | PRD §16.2: `chain＋protocol＋pool_key；V3 address 或 V4 PoolId／PoolKey；发现／采数／能力分派` | **正常单池**：仅包含当前 CORE 池（0x52e6...），V3 协议下 `pool_id` 与 `hooks` 为 NULL 符合预期。 |
| `rh_source_snapshots` | **4,204** | `source`, `payload_hash`, `fetch_time`, `quality` (100%); `source_event_time` (98.3%); `raw_ref` (**0%**) | PRD §16.2: `source＋payload_hash；source_event_time、fetch_time、schema、原始文件引用；所有证据回放` | **基本正常**：快照完备，除 `raw_ref` 全空外，能够支撑源数据可溯源性。 |

---

# 四、四个未定义空列：PRD 有无定义

在先前的列健康审计中，以下 4 个列被发现 100% 为 NULL：
1. `rh_contract_attestations.abi_version`
2. `rh_contract_attestations.evidence_json`
3. `rh_contract_attestations.expires_at`
4. `rh_source_snapshots.raw_ref`

对照 PRD 全文检索与条款核对结果如下：

### 1. `abi_version`（PRD §16.2、§14.2）
- **PRD 是否定义**：**只有概念提及，无具体枚举或格式定义**。
  - PRD §14.2 提及「合约／ABI／router 版本在白名单」，§16.2 提及「code／implementation／ABI 证据」。
  - 但 PRD **从未定义 `abi_version` 应该填什么**（例如是填 ABI 文件的 sha256、npm 包版本如 `@uniswap/v3-core@1.0.0`、还是编译器元数据 hash）。
- **性质认定**：**产品与设计决策缺口**。代码未填不是 bug，而是产品未定义其标准格式。

### 2. `evidence_json`（PRD §7.4、§16.2）
- **PRD 是否定义**：**定义了语义目标，未定义 JSON Schema**。
  - PRD §7.4 规定能力证据包含「evidence hash 与过期时间」，§16.2 规定保存「code／implementation／ABI 证据」。
  - 但对于 `evidence_json` 内部的字段契约（如是否包含 `bytecode_hash`、`storage_root`、`rpc_provider`、`probe_tx_hash`），PRD 完全留空。
- **性质认定**：**产品契约缺口**。在没有规范 schema 的情况下，工程上只能留空，避免填入非标结构。

### 3. `expires_at`（PRD §7.4、§14.1、§20 T06）
- **PRD 是否定义**：**逻辑上有要求，但未给出只读研究期的过期时间计算规则**。
  - PRD §7.4 规定「各项状态包含 evidence hash 与过期时间」，§14.1 规定意图需携带 `expires_at`，T06 规定 proxy implementation 变化导致 attestation 过期。
  - 但对于链上 immutable 合约或 proxy 合约的只读 attestation，其有效 TTL 是固定天数（如 7 天、30 天）还是基于 block number 判定，PRD 未作规定。
- **性质认定**：**产品策略缺口**。当前离线 probe 代码未写入过期时间，是因为产品未定义只读证据的 TTL 策略。

### 4. `raw_ref`（PRD §16.2）
- **PRD 是否定义**：**未定义物理引用格式**。
  - PRD §16.2 表中描述为「原始文件引用」。
  - 但在 SQLite 单库存储架构下，快照 payload 已经被哈希并作为上下文处理，系统并未在本地文件系统为每次 snapshot 落地一个独立磁盘文件，因此没有 `file://` 路径可供引用。
- **性质认定**：**架构实现与设计不匹配**。若 PRD 要求必须有磁盘文件路径，需建立本地 blob store；否则该列属于冗余字段。

---

# 五、距离毕业还差什么

按 PRD 的字面要求核算，Stage A 要想合规毕业，**不能仅靠挂机等待时间**。必须清晰区分「等时间就能满足」与「需要额外工程/产品决策」：

```
+---------------------------------------------------------------------------------------------------+
|                                 Stage A 毕业距离差距清单                                          |
+----------------------------------------------------+----------------------------------------------+
|                A. 等时间就能满足                   |            B. 需要额外工程 / 产品决策        |
|               (纯日历 / 挂机运行)                  |           (不补齐则毕业闸门形同虚设)         |
+----------------------------------------------------+----------------------------------------------+
| 1. 观测时长达到 72 小时                            | 1. 经济有效数据时长严重不足 (决策)           |
|    - 当前 40.6h / 72.0h                            |    - fee_growth 只有约 4h 有效数据，PRD 要求  |
|    - 仍需平稳运行约 31.4 小时                      |      72h 用于收益评估；是重新计算 72h 还是   |
|                                                    |      接受前 36h 费用缺失？                   |
| 2. 数据覆盖率追回到 ≥99.00%                        |                                              |
|    - 当前 0.9678                                   | 2. 将 7 项 PRD 硬指标接线进 readiness (工程) |
|    - 因前期周期漂移亏空 52 分钟，需挂机至约        |    - 日历/异常合成测试通过断言               |
|      第 87.5 ~ 90 小时才能将总覆盖率拉升至 99.03%  |    - 列健康/关键字段非空率检查接入准出门槛   |
|    - 需再平稳挂机约 47 ~ 50 小时                   |    - 预算与不变量违反纳入 Stage A 阻断       |
|                                                    |    - 未知状态新增模拟仓位=0 形式化核对       |
|                                                    |                                              |
|                                                    | 3. 补齐当前观测池的身份与能力证据 (工程)     |
|                                                    |    - rh_pool_registry 当前池缺 hooks/pool_id |
|                                                    |    - rh_assets 补充池底层代币 WETH/USDG      |
|                                                    |    - rh_contract_attestations 补入 0x52e6 池 |
|                                                    |      合约与代币合约的同块 attestation        |
|                                                    |                                              |
|                                                    | 4. 裁定 4 个未定义列的填充标准 (产品决策)    |
|                                                    |    - 裁定 abi_version 的格式标准             |
|                                                    |    - 裁定 evidence_json 的 Schema 结构       |
|                                                    |    - 裁定只读 attestation 的 TTL (expires_at)|
|                                                    |    - 裁定 raw_ref 是否保留为 NULL            |
+----------------------------------------------------+----------------------------------------------+
```

### 审计结论：
**当前 Stage A 的自动化毕业脚本 `scripts/lp_rh_readiness_v1_readonly.py` 存在严重的「假准入」风险**：它只检查了时间长度与纯行数覆盖率（且两者当前均为 FAIL），而把 PRD §21.1 明确要求的「关键字段真实生产」、「身份和能力证据清楚」、「合成测试通过」、「不变量无违反」完全抛在闸门之外。

即使再过 50 小时，时间与覆盖率双双跨过阈值，若上述「B 栏」问题未获决策与修复，**系统依然无法构成 PRD 所要求的可信数据毕业证据链**。
