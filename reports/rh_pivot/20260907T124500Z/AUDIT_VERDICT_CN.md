# PRD 验收用例审计裁决（主脑）

**取证由 worker 做（只列证据不下判定），判定由主脑做。** 本文只写判定与理由，
证据在 `AUDIT_EVIDENCE_T01_T20.json` 等文件里，每条都带 file:line 与真跑过的 pytest 输出。

## 取证质量核验（我对证据本身的检查）

对 T01–T20 这批：

| 检查项 | 结果 |
|---|---|
| 条目数与 ID 连续性 | 20 条，T01–T20 无缺 |
| `impl_sites` 的 file:line 真实存在且 snippet 与该行吻合 | **0 处问题** |
| `covering_tests` 里的测试函数确实存在 | **0 处问题** |
| 产物中混入判定词 | 2 处，均为误报（一处是引用源码 `return {"status": "PASS"}` 的 snippet，一处是描述 `live_readiness` 的说明） |

另抽验 T01 / T05 / T12 / T13 四条，逐条读了它引用的测试原文，
断言内容与 `expected` 精确对应。**取证可采信。**

---

## T01–T20 裁决

| 用例 | 判定 | 理由 |
|---|---|---|
| T01 chainId 身份闸 | **PASS** | `chain_identity_gate` 返回 `CHAIN_ID_MISMATCH`/`CHAIN_ID_UNKNOWN`；shadow 侧另有 `test_conjunct_identity_fails_on_wrong_chain` 独立断言。今晚还实证过一个报 Base 链的假提供方被正确排除 |
| T02 地址非 registry 部署 | **PASS** | `ASSET_IDENTITY_MISMATCH` 有断言 |
| T03 旧 schema 映射 | **PASS** | null／空／closing-only 均不映射为可交易 |
| T04 新嵌套 schema | **PASS** | market／extended／overnight 三种能力分别断言 |
| T05 未知 enum／新旧矛盾 | **PASS** | `UNKNOWN` 与 `SCHEMA_CONFLICT` 各有断言，无静默回退 |
| T06 attestation 过期 | **PASS** | beacon 升级使 attestation 失效有断言 |
| T07 V3/V4 分派 | **PASS** | factory+pool 与 PoolManager+PoolId 分派有断言 |
| T08 未 attest 不得升级 | **PASS** | `DISCOVERED_NOT_ATTESTED` 阻断有断言 |
| T09 V4 hooks 未支持 | **需关注** | `UNSUPPORTED_HOOK_POLICY` 已断言；但 **「网页 APR 不影响结果」无任何测试**。取证 grep 确认探针不读 APR，即行为上不会出错，**缺的是回归保护**——将来有人加 APR 读取不会被拦住 |
| T10 provider 能力矩阵 | **PASS** | 逐 venue 矩阵有断言 |
| T11 同高度不同 hash | **FAIL** | `BLOCK_HASH_DIVERGENCE` 标记有断言，**但 `expected` 的后半句「回滚受影响派生值」没有实现**。store 有 reorg 字段，没有回滚逻辑。这不是覆盖不足，是功能缺失 |
| T12 RPC 失败分类 | **PASS** | `JSONRPC_ERROR` 与原文保留有断言，不会被当成 0 余额／0 费用 |
| T13 两 URL 同后端 | **PASS** | `SAME_BACKEND_SUSPECTED` 与 `independent is False` 有断言。**但见下方「实盘尚未验证」** |
| T14 时段分类 | **PASS** | 今晚 20:00 UTC 实盘穿越 RTH→POSTMARKET，模块判定正确，首次有实盘验证 |
| T15 健康标志独立 | **PASS** | session 与 flags 两个独立返回值，不合并成一个 enum |
| T16 假期／早收 | **PASS** | `nyse-2026-v1` 日历，`is_early_close` 有断言 |
| T17–T20 STOCK 相关 | **PASS** | 乘数只乘一次、HOLIDAY 不 recenter 等均有断言 |

**小计：T01–T20 → PASS 17、需关注 1（T09）、FAIL 1（T11）。**

## 两条不能只看测试的补充说明

1. **T13 的实盘部分未验证。** 测试用合成 probe 断言了「同后端可疑」，
   但**真实的四个端点是否共用上游基础设施，我今天没能核实**
   （见 `PROVIDER_MATRIX_20260908.md` 的「还欠的两项」）。
   单元测试 PASS 不等于这条链上的独立性已证明。
2. **T11 是今晚审计挖出的第一个功能缺失**，不是文档问题。
   重组回滚会影响所有派生值（NAV、费率累加器差分、markout），
   在 Stage B 之前必须处置。已记入待办。

---

## T21–T60 裁决（2026-09-09 01:4x UTC 补全）

取证质量核验同 T01–T20：三批共 60 条，**`impl_sites` 的 file:line 与 snippet
逐条核验为真、`covering_tests` 全部真实存在，三批合计 0 处问题**。

### 全局结果

| 批次 | COVERED | PARTIAL | NOT_COVERED |
|---|---:|---:|---:|
| T01–T20 | 18 | 2 | 0 |
| T21–T40 | 13 | 3 | 4 |
| T41–T60 | 15 | 2 | 3 |
| **合计** | **46** | **7** | **7** |

### 七个 NOT_COVERED 的裁决

| 用例 | 判定 | 理由与处置 |
|---|---|---|
| **T29** native ETH 储备 | **FAIL（最高危）** | 全仓无任何比较原生余额与 gas 储备的闸。WETH 付不了 gas，开仓后可能**无钱平仓、仓位困死**。这是七个里唯一会造成资金被困的。已写 `RH-03d`，在跑 |
| **T34** gas 含 L1 data | **FAIL** | `gas_usd` 纯直通、无 L1 data 项、无合理性校验。**我因此把自己手填的 0.02 用了一整天，真值 0.4614，低估 23 倍，并算反了资金政策结论。** 已落地 `RH-03c` 估算器与 sanity 闸（`e0dcb04`） |
| **T26** MEME 跨池聚合 | **FAIL** | 只有单资产上限，无跨池/跨钱包聚合，可拆单绕过。MEME 桶尚未启用且可能 NO-GO，优先级低于前两条 |
| **T31** 空区间分类 | **FAIL（分类缺失）** | `q_min`/`q_max` 只是数据库列，无人计算。空区间会被误读成缺数据。已写 `RH-03e`，在跑 |
| **T53** L1 posting 滞后 | **不判 FAIL** | 属 RH-07 执行层。**本项目未获签名/广播授权，该层至今未触碰**，无实现是符合预期的，不是缺陷 |
| **T54** 仅等待时长无 L1 证据 | **不判 FAIL** | 同 T53 |
| **T56** 旧 Base 快照逐闸差分 | **需关注** | 无实现。这是回归护栏而非运行时功能：缺了它，将来改闸门无法证明「对旧 Base 快照的判定未变」。Stage B 前应补 |

### 七个 PARTIAL 的裁决

| 用例 | 判定 | 缺的是什么 |
|---|---|---|
| T09 v4 hooks | 需关注 | 策略正确，缺「网页 APR 不影响结果」的回归保护 |
| **T11** 重组回滚 | **FAIL** | 标记有、回滚无。**追查发现根因是六个派生表无区块溯源，回滚此前根本不可能写**。已落地 `RH-02f`（`95222e0`）补上溯源与只读定位；**回滚本身仍未实现，判定维持 FAIL** |
| T21 oracle 暂停 | PASS | 状态机与闸门均有断言，取证的保留意见不影响结论 |
| T32 未知 fee vs 合法 0 | PASS | `None` 与 `0` 已区分且有断言 |
| T36 未来数据不可得 | PASS | `run_episode` 逐样本推进，第 i 步不引用后续样本，有断言 |
| T45 原子 exit 回滚 | 需关注 | `ATOMIC_EXIT_REVERTED` 有断言，独立性那半句无测试 |
| T57 预算闸 | PASS | `budget_status` 与采集器 WARN/OVER 行为均有断言 |

## 最终结论

**PASS 46 · 需关注 4 · FAIL 5 · 不适用 2（未授权的执行层）**

五个 FAIL 里，**T29 与 T34 有直接资金风险**，且 T34 已经实际造成了一次错误结论
（见 `CAPITAL_POLICY_CONFLICT_DECISION_CN.md` 的重大更正）。
T11 与 T31 是分类/护栏缺失，T26 依附于尚未启用的 MEME 桶。

**处置状态**：T34 已修复并实盘验证；T29、T31 spec 已派发；T11 前置条件已补齐、
回滚待实现；T26 与 T56 待排期。

## 这次审计真正的价值

它抓到的不是「算错了」，而是**「这个数从哪来」**。
T34 那条用例本身平平无奇，但顺着它去核对，发现撑起当天全部经济结论的
`gas_usd_estimate = 0.02` **没有任何出处**——而每一步计算都是对的。
**一个没有出处的常量比一个算错的公式更危险，因为它不会在任何测试里报错。**
