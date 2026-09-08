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

## 进度

- [x] T01–T20 已裁决
- [ ] T21–T40 取证中
- [ ] T41–T60 排队
