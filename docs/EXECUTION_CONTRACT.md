# LP-Bot RH 执行契约规范（EXECUTION_CONTRACT.md）

> **文档版本**：v1.0  
> **生效阶段**：RH-07 阶段一（RH-07a–RH-07e）及后续全量执行生命周期  
> **上游准绳**：`PRD_RH_LP_Bot_v1.1_CN.md`（§14 执行适配、§15 退出状态机、§16.2–16.3 存储与预算、§19 交付物1、§20 用例清单 T47–T54）  
> **工程对齐**：`HANDOFF_20260911_2_CN.md`（§12 路线图）、`PROJECT_STATE_AND_ARCHITECTURE_20260907_CN.md`、`RISK_INVARIANTS.md`  
> **红线纪律**：只读阶段与阶段一**绝不生成私钥、绝不签名、绝不广播、不接付费 RPC**；`LIVE_TRADING=false`，`tiny_live_authorized=false`。

---

## 目录

- [§0 契约声明与不可变前置约束](#0-契约声明与不可变前置约束)
- [§1 意图生命周期（Intent Lifecycle）](#1-意图生命周期intent-lifecycle)
  - [1.1 状态机全景图](#11-状态机全景图)
  - [1.2 逐状态进入条件、证据、离开与拒绝点](#12-逐状态进入条件证据离开与拒绝点)
- [§2 状态机的证据要求（按状态列字段）](#2-状态机的证据要求按状态列字段)
  - [2.1 存储模型与表结构关联](#21-存储模型与表结构关联)
  - [2.2 逐状态必需字段矩阵](#22-逐状态必需字段矩阵)
  - [2.3 核心证据断言与判定规则](#23-核心证据断言与判定规则)
- [§3 白名单与拒绝点（Whitelists & Rejection Points）](#3-白名单与拒绝点whitelists--rejection-points)
  - [3.1 Target 合约白名单](#31-target-合约白名单)
  - [3.2 Recipient 接收方白名单](#32-recipient-接收方白名单)
  - [3.3 Selector 选择器白名单](#33-selector-选择器白名单)
  - [3.4 Size 单笔上限](#34-size-单笔上限)
  - [3.5 Deadline 有效期窗口](#35-deadline-有效期窗口)
  - [3.6 Min_Out 最小到账下限与滑点保护（T50）](#36-min_out-最小到账下限与滑点保护t50)
  - [3.7 Gas 估算天花板](#37-gas-估算天花板)
  - [3.8 Policy Version 一致性](#38-policy-version-一致性)
  - [3.9 模拟通过不可作为白名单绕过证据（T48 红线）](#39-模拟通过不可作为白名单绕过证据t48-红线)
- [§4 闸门与签名前双开关（T47）](#4-闸门与签名前双开关t47)
  - [4.1 双开关架构原则与调用顺序](#41-双开关架构原则与调用顺序)
  - [4.2 开关 A：Policy Gate（策略合规闸）](#42-开关-apolicy-gate策略合规闸)
  - [4.3 开关 B：Intent Gate（证据与状态完整性闸）](#43-开关-bintent-gate证据与状态完整性闸)
  - [4.4 签名前不可变前置断言（Pre-Sign Hard Invariant）](#44-签名前不可变前置断言pre-sign-hard-invariant)
- [§5 占位与未决（Placeholders and Deferred Items）](#5-占位与未决placeholders-and-deferred-items)
  - [5.1 MEV 与交易提交策略占位](#51-mev-与交易提交策略占位)
  - [5.2 L1/L2 Finality 分层阈值占位（T53/T54）](#52-l1l2-finality-分层阈值占位t53t54)
  - [5.3 深度重组与 Nonce 恢复占位（T51/T52）](#53-深度重组与-nonce-恢复占位t51t52)
  - [5.4 残余库存与分步清算占位（T44/T45）](#54-残余库存与分步清算占位t44t45)
  - [5.5 占位状态下的安全兜底机制](#55-占位状态下的安全兜底机制)
- [附录：核心术语中英文对齐表](#附录核心术语中英文对齐表)

---

## §0 契约声明与不可变前置约束

1. **先契约后实现 [PRD §19 交付物1]**：本契约是 RH-07 全生命周期执行代码（`rh_tx_intents` writer、calldata builder、白名单 decoder 接线、双开关闸门、fork 演练、nonce 恢复）的唯一定义源。任何代码实现不得偏离本规范。
2. **机械翻译原则**：本契约内所有的「必须」、「严禁」、「拒绝点」均必须能直接映射为 Python 代码中的显式断言（`assert`）或抛出指定的结构化异常（`ContractViolationError`），禁止含有模糊的、依赖人工经验主观判定的灰色边界。
3. **Fail-Closed 闭环 [PRD §14.1]**：任何证据缺失、格式损坏、校验未通过的意图，必须立即阻断流转并显式标记拒绝原因，严禁静默跳过（No Silent Skip）、严禁缺省放行。
4. **资金预算事务一致性 [PRD §16.3]**：意图创建、校验、拒绝、释放与数据库中的 `rh_bucket_reservations` 状态强绑定，保持事务原子性。

---

## §1 意图生命周期（Intent Lifecycle）

### 1.1 状态机全景图

```
                ┌──────────────────────────────────────────────────┐
                │                     [DRAFT]                      │
                └────────────────────────┬─────────────────────────┘
                                         │ (本地模拟验证通过)
                                         ▼
                ┌──────────────────────────────────────────────────┐
                │                   [SIMULATED]                    │
                └──────────┬─────────────────────────────┬─────────┘
                           │                             │ (双开关 A+B 校验失败)
 (双开关 A+B 校验通过)      │                             ▼
                           │                    ┌──────────────────┐
                           ▼                    │    [REJECTED]    │◄───┐ (任一环节违规拒绝)
                ┌──────────────────────┐        └────────┬─────────┘    │
                │  [POLICY_APPROVED]   │                 │ (对账清理)    │
                └──────────┬───────────┘                 ▼              │
                           │                    ┌──────────────────┐    │
                           │ (执行用户内存签名)   │    [ARCHIVED]    │    │
                           ▼                    └──────────────────┘    │
                ┌──────────────────────┐                                │
                │       [SIGNED]       │────────────────────────────────┤
                └──────────┬───────────┘                                │
                           │ (提交节点广播)                              │
                           ▼                                            │
                ┌──────────────────────┐                                │
                │     [BROADCAST]      │                                │
                └────┬────────────┬────┘                                │
                     │            │                                     │
      (L2 收据验证成功)│            │ (链上 Revert / 丢单)                 │
                     ▼            ▼                                     │
           ┌───────────┐    ┌────────────┐                              │
           │[CONFIRMED]│    │  [FAILED]  │                              │
           └─────┬─────┘    └─────┬──────┘                              │
                 │                │                                     │
                 │ (检测到深浅重组) │ (未决丢单/分叉重组)                    │
                 ▼                ▼                                     │
           ┌─────────────────────────────┐                              │
           │       [REORG_PENDING]       │                              │
           └──────────────┬──────────────┘                              │
                          │                                             │
             ┌────────────┴────────────┐                                │
             ▼                         ▼                                │
      (在新分叉上被打包确认)     (交易在新分叉中永久失效)                      │
       [CONFIRMED]                [REVERTED] ───────────────────────────┘
```

### 1.2 逐状态进入条件、证据、离开与拒绝点

#### 1.2.1 DRAFT（草稿状态）[PRD §14.1, §16.2]
- **定义**：策略引擎生成的未签名意图雏形，已绑定核心三 ID 与 calldata 哈希，但尚未进行本地模拟。
- **进入条件**：
  - 前置状态：无（初始状态创建）。
  - 必须由只读研究策略或退出逻辑显式发起。
- **证据要求**：
  - `request_id`：UUID4 规范格式，全局唯一，非 NULL。
  - `idempotency_key`：幂等主键（`chain_id:wallet_id:position_id:decision_id:calldata_hash`），UNIQUE 约束。
  - `chain_id`：必须为 8453（Base Mainnet），INTEGER NOT NULL。
  - `wallet_id`：已配置的白名单钱包地址，42 字符十六进制，非 NULL。
  - `position_id`：头寸识别码（新增开仓可为临时确定性哈希），非 NULL。
  - `calldata_hash`：原始未签名 calldata 的 SHA256 十六进制字符串，非 NULL。
  - `policy_hash`：当前生效资本与风控政策快照哈希，非 NULL。
  - `expires_at`：UTC RFC3339 格式时间戳，必须满足 `expires_at > created_at`。
  - `created_at`：UTC RFC3339 格式时间戳，非 NULL。
  - **原子预留**：同一事务内向 `rh_bucket_reservations` 插入一条状态为 `PENDING` 的记录。
- **离开条件**：
  - 合法后继：`SIMULATED`、`REJECTED`。
- **拒绝点（Rejection Points）**：
  - `[REJ-0101]` **字段缺失**：11 个意图绑定字段缺失任一项 → 抛出 `ValueError("INTENT_FIELD_MISSING:<field>")`，不写库 [PRD §14.1]。
  - `[REJ-0102]` **幂等碰撞**：`idempotency_key` 在 `rh_tx_intents` 已存在 → 捕获 `sqlite3.IntegrityError`，拒绝创建，返回已有意图状态，严禁重复开单 [PRD §16.2, T51]。
  - `[REJ-0103]` **Calldata 畸形**：十六进制格式错误或长度不够 4 字节选择器 → 抛出 `ContractViolationError("MALFORMED_CALLDATA")`，标记 `REJECTED`。
  - `[REJ-0104]` **资金超配**：尝试在 `rh_bucket_reservations` 中原子锁定额度时，当前桶已用额度 + 本笔 `amount_usd` > `CORE_ACTIVE_CAP` → 抛出 `RuntimeError("CAPITAL_EXCEEDED_ACTIVE_CAP")`，标记 `REJECTED` [PRD §16.3, T27]。
  - `[REJ-0105]` **预先过期**：创建时即发现 `expires_at <= now_utc` → 抛出 `ValueError("INTENT_ALREADY_EXPIRED")`，标记 `REJECTED`。

#### 1.2.2 SIMULATED（本地模拟通过）[PRD §14.3, T49]
- **定义**：意图在本地 fork（固定区块高度）完成模拟执行，无 revert，且产出了确定性的余额变化与 gas 估计。
- **进入条件**：
  - 前置状态：必须为 `DRAFT`。
  - 策略自报“`simulated=true`”无效，必须由受限执行模块亲自调用 fork RPC 产出证据 [PRD §14.1]。
- **证据要求**：
  - `simulation_block_hash`：模拟执行时锚定的具体区块哈希（66 字符），非 NULL。
  - `simulation_block_number`：模拟执行的整数区块高度，非 NULL。
  - `simulated_gas_limit`：模拟消耗的 gas 数量（十进制 TEXT 记录）。
  - `simulated_balance_deltas_json`：JSON 格式记录的资产收支变化（必须包含两腿代币增减与 native gas 扣减）。
  - `simulated_at`：UTC RFC3339 格式时间戳。
- **离开条件**：
  - 合法后继：`POLICY_APPROVED`、`REJECTED`。
- **拒绝点（Rejection Points）**：
  - `[REJ-0201]` **执行 Revert**：模拟返回执行失败（revert / out of gas / invalid opcode）→ 记录 revert reason，状态置为 `REJECTED`，释放预留资金 [PRD §14.3]。
  - `[REJ-0202]` **Gas 超过天花板**：模拟 gas 按当前单价折算 USD > `MAX_GAS_USD` → 抛出 `ContractViolationError("GAS_EXCEEDS_CEILING")`，状态置为 `REJECTED`。
  - `[REJ-0203]` **意外资产外溢**：模拟结果中非目标代币余额发生扣减或目标代币收入为 0（在非合法单边场景下）→ 抛出 `ContractViolationError("UNEXPECTED_BALANCE_DRAIN")`，状态置为 `REJECTED`。

#### 1.2.3 POLICY_APPROVED（双开关批准）[PRD §14.2, T47, T48]
- **定义**：意图已通过签名前双开关（开关 A 策略白名单合规闸 + 开关 B 证据完整性与状态机闸），完全具备签名资格。
- **进入条件**：
  - 前置状态：必须为 `SIMULATED`。
  - 严禁从 `DRAFT` 绕过 `SIMULATED` 直接跳入 `POLICY_APPROVED`。
- **证据要求**：
  - `gate_a_verdict`：必须为 `"PASS"`，非 NULL。
  - `gate_b_verdict`：必须为 `"PASS"`，非 NULL。
  - `approval_chain_json`：包含开关 A 与开关 B 执行时间戳、校验规则哈希、执行者身份（无私钥环境）的审计链 JSON。
  - `approved_at`：UTC RFC3339 格式时间戳。
  - `policy_version`：必须严格匹配 `RH_BUCKET_POLICY_VERSION`（当前 `rh_50_30_20_proposed_v1`）。
- **离开条件**：
  - 合法后继：`SIGNED`、`REJECTED`。
- **拒绝点（Rejection Points）**：
  - `[REJ-0301]` **开关 A 阻断**：目标合约、接收方、选择器不在白名单，或金额/期限违规 → 记录违规项清单，状态变迁至 `REJECTED` [PRD §14.2, T48]。
  - `[REJ-0302]` **开关 B 阻断**：证据字段残缺、哈希与原始数据不一致、模拟与当前环境脱钩（T49）→ 状态变迁至 `REJECTED` [PRD §14.2, T49]。
  - `[REJ-0303]` **政策版本漂移**：`intent.policy_hash` 与当前系统生效 policy 不一致 → 抛出 `ContractViolationError("POLICY_VERSION_MISMATCH")`，状态置为 `REJECTED`。

#### 1.2.4 SIGNED（已签名）[PRD §14.1, §14.4]
- **定义**：由拥有安全隔离 Keystore 的执行用户在本地独立完成签名的意图。
- **进入条件**：
  - 前置状态：**必须且只能为 `POLICY_APPROVED`**。
  - 任何试图对 `DRAFT`、`SIMULATED` 或 `REJECTED` 意图执行签名的行为均属于重大越权违规。
- **证据要求**：
  - `signed_tx_hash`：签名后的交易唯一哈希（66 字符十六进制），非 NULL。
  - `signer_address`：执行签名者的公共地址（与 `wallet_id` 严格一致），非 NULL。
  - `nonce`：为此笔交易分配的单调递增整数 nonce，非 NULL。
  - `signed_at`：UTC RFC3339 格式时间戳。
  - `approval_chain_json`：继承自上一状态并封印签名流水号。
- **离开条件**：
  - 合法后继：`BROADCAST`、`REJECTED`。
- **拒绝点（Rejection Points）**：
  - `[REJ-0401]` **绕过闸门签名**：进入签名模块时检查 `state != "POLICY_APPROVED"` → 抛出致命异常 `PreSignGateBypassAttemptError`，中断进程并触发最高级告警。
  - `[REJ-0402]` **非白名单签名者**：Keystore 解密出的公共地址与意图 `wallet_id` 不符 → 抛出 `SecurityViolationError("UNAUTHORIZED_SIGNER")`，标记 `REJECTED`。
  - `[REJ-0403]` **Nonce 跳号或重复**：所用 nonce 不等于该钱包在数据库记录的 `max(nonce) + 1` → 抛出 `ContractViolationError("NONCE_ORDER_VIOLATION")`，阻止交易并标记 `REJECTED` [PRD §14.4, T52]。

#### 1.2.5 BROADCAST（已广播提交）[PRD §14.4, T51]
- **定义**：已签名交易已通过选定的 RPC 节点或私有 Sequencer 接口提交至网络或内存池。
- **进入条件**：
  - 前置状态：必须为 `SIGNED`。
  - Nonce 预占与交易意图必须已在 SQLite 中完成物理落盘持久化（`PRAGMA synchronous = FULL` 或 WAL checkpoint）。
- **证据要求**：
  - `broadcast_tx_hash`：广播成功的交易哈希（与 `signed_tx_hash` 严格一致）。
  - `rpc_endpoint`：接收广播的 RPC 提供方脱敏标识（如 `alchemy_base_primary`）。
  - `broadcast_at`：UTC RFC3339 格式时间戳。
  - `submission_attempt_count`：提交尝试次数（整数，初始为 1）。
- **离开条件**：
  - 合法后继：`CONFIRMED`、`FAILED`、`REORG_PENDING`。
- **拒绝点与超时处理（Rejection Points & Timeout Rules）**：
  - `[REJ-0501]` **广播网络超时 / UNKNOWN**：RPC 发生 HTTP 504 / 超时，无法确认节点是否收录 → 状态**严禁直接置为 FAILED**，严禁释放 reservation，严禁换用新 nonce 重发同一资金动作！状态维持在 `BROADCAST` 并挂载 `BROADCAST_UNKNOWN` 标记，转入独立对账轮询 [PRD §14.4, §16.3, T51, INV-RH-15]。
  - `[REJ-0502]` **节点返回明确拒收**：节点返回 `nonce too low` 或 `replacement transaction underpriced` 或 `insufficient funds for gas * price + value` → 记录错误码，状态转入 `FAILED`。

#### 1.2.6 CONFIRMED（已确认成交）[PRD §14.4, §16.2]
- **定义**：交易已被 L2 包含进规范区块，返回 status=1 的 TransactionReceipt，且在 `rh_tx_receipts` 表中成功记账。
- **进入条件**：
  - 前置状态：必须为 `BROADCAST` 或 `REORG_PENDING`（重组后重新确认）。
  - 必须由真实的链上 receipt 证实，不得依靠"发出满 5 秒假装成交"。
- **证据要求**：
  - `block_number`：交易被包含的整数区块高度，非 NULL。
  - `block_hash`：交易所在区块的哈希值（66 字符），非 NULL。
  - `confirmations`：当前观测到的确认块数（≥ 1），非 NULL。
  - `finality_class`：确认等级（如 `"L2_SOFT_CONFIRMED"`）。
  - `gas_used`：链上实际消耗 gas，十进制 TEXT 记录。
  - `actual_receipt_status`：链上状态码，必须为整数 `1`。
  - `observed_at`：UTC RFC3339 格式时间戳。
  - **原子更新**：`rh_bucket_reservations` 的状态由 `PENDING` 更新为 `CONFIRMED`。
- **离开条件**：
  - 合法后继：`REORG_PENDING`（若后续发生链分叉重组）。正常情况下为稳定终态。
- **拒绝点（Rejection Points）**：
  - `[REJ-0601]` **伪造收据 / 状态为 0**：获取到的收据中 `status == 0`（On-chain Revert）→ 严禁进入 `CONFIRMED`，强制流转至 `FAILED` 并记录 gas 损耗 [PRD §14.4]。
  - `[REJ-0602]` **Receipt 字段缺失**：缺少 `block_hash` 或 `gas_used` → 抛出 `IntegrityError("RECEIPT_INCOMPLETE")`，保持在对账等待中。

#### 1.2.7 FAILED（执行失败 / 链上回滚）[PRD §14.4, §15.2, T44]
- **定义**：交易在链上被打包但执行 revert（status=0），或在节点中被永久丢弃。
- **进入条件**：
  - 前置状态：必须为 `BROADCAST`。
  - 拥有权威链上 receipt 且 status=0，或节点确认该 nonce 已被其他有效交易填补。
- **证据要求**：
  - `failed_tx_hash`：失败交易的哈希。
  - `failure_reason`：revert 原因字符串或节点拒绝响应。
  - `gas_burned`：链上回滚实际消耗并损失的 gas 费用（十进制 TEXT）。
  - `failed_at`：UTC RFC3339 格式时间戳。
- **离开条件**：
  - 合法后继：`REORG_PENDING`（若失败状态所属区块本身被重组）、`REJECTED` / `ARCHIVED`。
- **拒绝点与处置（Rejection & Action Rules）**：
  - `[REJ-0701]` **残余库存防护**：在退出场景下，若 removeLiquidity 成功但换币 swap 失败，严禁标记为 cash closed，必须转为 `REMOVED_RISKY_INVENTORY`，保留风险敞口记账 [PRD §15.1, T44]。
  - `[REJ-0702]` **资金预留释放**：确认交易彻底死亡且未动用本金后，在同一个数据库事务中将 `rh_bucket_reservations` 置为 `RELEASED`，释放本金配额，已消耗 gas 记入 `rh_journal` 损耗。

#### 1.2.8 REORG_PENDING（分叉重组未决）[PRD §14.4, §16.2, T52]
- **定义**：探测到之前打包该交易的区块哈希与当前规范链（Canonical Chain）不一致，交易归属处于未决状态。
- **进入条件**：
  - 前置状态：必须为 `CONFIRMED` 或 `FAILED`。
  - 由 `lp_rh_reorg_detector` 产出链分叉比对证据。
- **证据要求**：
  - `prior_block_hash`：之前记录的旧区块哈希，非 NULL。
  - `prior_block_number`：旧区块高度，非 NULL。
  - `reorg_detected_at`：探测到重组的 UTC RFC3339 时间戳。
  - `reorg_depth`：重组回滚的区块深度（整数），非 NULL。
  - `replacement_tx_hash`：在新分叉链上的对应交易哈希（若尚在 mempool 可为 NULL）。
- **离开条件**：
  - 合法后继：`CONFIRMED`（交易在新链上重新被打包生效）、`REVERTED`（交易在新链上被 drop 或 revert）。
- **拒绝点（Rejection Points）**：
  - `[REJ-0801]` **重组期间释放资金**：处于 `REORG_PENDING` 期间，严禁将对应 `rh_bucket_reservations` 标记为 `RELEASED` 或 `EXPIRED`，必须保持锁定防止资金被双花或超配 [PRD §16.3]。
  - `[REJ-0802]` **重组期间发起新单**：该钱包在该 nonce 决议前，严禁利用后续 nonce 签署任何新意图 → 抛出 `ReorgLockoutError("WALLET_FROZEN_IN_REORG")`。

#### 1.2.9 REVERTED（重组后永久失效）[PRD §14.4]
- **定义**：经历重组后，原交易未被新规范链收录且已超时过期，或在新链上执行 revert。
- **进入条件**：
  - 前置状态：必须为 `REORG_PENDING`。
  - 新规范链高度已推进超过安全深度（如 64 个区块），且未见该交易。
- **证据要求**：
  - `revert_evidence_json`：记录重组新旧链哈希对比、扫描区块范围的证据包。
  - `reverted_at`：UTC RFC3339 格式时间戳。
  - `loss_usd_gas`：因重组损失的 gas 折算金额。
- **离开条件**：
  - 合法后继：`ARCHIVED`。
- **处置要求**：
  - 释放对应 `rh_bucket_reservations`，并在 `rh_journal` 中记入一笔冲正分录。

#### 1.2.10 REJECTED（被拒绝状态）[PRD §14.1, §14.2]
- **定义**：意图在签名之前被双开关、白名单、数值上限或模拟环节主动拒绝的非可逆中间/终态。
- **进入条件**：
  - 前置状态：`DRAFT`、`SIMULATED`、`POLICY_APPROVED`。
- **证据要求**：
  - `reject_code`：标准化的拒绝错误码（如 `TARGET_NOT_ALLOWLISTED`、`MISSING_SLIPPAGE_PROTECTION` 等）。
  - `reject_reason`：人类可读的结构化详细违规原因。
  - `rejected_at`：UTC RFC3339 格式时间戳。
  - `rejected_by_gate`：拦截该意图的闸门标识（`"GATE_A"`、`"GATE_B"`、`"SIMULATION"` 或 `"PRE_CHECK"`）。
- **离开条件**：
  - 合法后继：`ARCHIVED`。
- **处置要求**：
  - **原子释放**：同一事务内向 `rh_bucket_reservations` 更新 `status = 'RELEASED'`，`released_at = rejected_at`。

#### 1.2.11 ARCHIVED（已归档状态）[PRD §16.4]
- **定义**：生命周期彻底完结的意图记录，只读保留用于历史审计，不参与任何活跃状态比对。
- **进入条件**：
  - 前置状态：`REJECTED`、`CONFIRMED`（结算归档后）、`REVERTED`。
- **证据要求**：
  - `archived_at`：UTC RFC3339 格式时间戳。
  - `cleanup_verified`：布尔值 1，代表预留额度、临时状态已 100% 对账清理完毕。
- **离开条件**：
  - 无（最终状态，不可变）。

---

## §2 状态机的证据要求（按状态列字段）

### 2.1 存储模型与表结构关联

意图生命周期的证据分散并持久化于 SQLite 存储层的 3 张核心表：
1. `rh_tx_intents`：主意图表（PK `request_id`，UNIQUE `idempotency_key`）。
2. `rh_bucket_reservations`：资金桶原子预留表（PK `intent_id`），跟踪资金占用生命周期。
3. `rh_tx_receipts`：链上回执与重组标记表（PK `(request_id, tx_hash)`）。

除上述固定列外，所有状态转换必须在其扩展数据字典（或 JSON 字段）中提供自包含证据。**任何状态缺少对应必填字段，该状态即判定为非法（Invalid State）**，校验函数必须抛出 `StateEvidenceIncompleteError`。

### 2.2 逐状态必需字段矩阵

| 状态名称 (State) | 必需非空字段集合 (Required Non-NULL Fields) | 字段物理归属 (Table / Payload) | 缺失时拒绝码 (Error Code) | 校验判定规则 (Mechanical Assertion) |
|---|---|---|---|---|
| **DRAFT** | `request_id`<br>`idempotency_key`<br>`chain_id`<br>`wallet_id`<br>`position_id`<br>`calldata_hash`<br>`policy_hash`<br>`expires_at`<br>`created_at`<br>`bucket`<br>`amount_usd` | `rh_tx_intents`<br>+ `rh_bucket_reservations` | `STATE_EVIDENCE_INCOMPLETE:DRAFT:<field>` | `assert all(intent.get(k) is not None for k in DRAFT_FIELDS)`<br>`assert intent["chain_id"] == 8453`<br>`assert intent["expires_at"] > intent["created_at"]` |
| **SIMULATED** | 继承 DRAFT 全量字段<br>+ `simulation_block_hash`<br>+ `simulation_block_number`<br>+ `simulated_gas_limit`<br>+ `simulated_balance_deltas_json`<br>+ `simulated_at` | `rh_tx_intents` (payload)<br>+ `simulation_evidence_json` | `STATE_EVIDENCE_INCOMPLETE:SIMULATED:<field>` | `assert simulation_block_hash.startswith("0x") and len(simulation_block_hash) == 66`<br>`assert int(simulated_gas_limit) > 0`<br>`assert isinstance(json.loads(balance_deltas), dict)` |
| **POLICY_APPROVED** | 继承 SIMULATED 全量字段<br>+ `gate_a_verdict`<br>+ `gate_b_verdict`<br>+ `policy_version`<br>+ `approval_chain_json`<br>+ `approved_at` | `rh_tx_intents` (payload)<br>+ 审计证据包 | `STATE_EVIDENCE_INCOMPLETE:POLICY_APPROVED:<field>` | `assert intent["gate_a_verdict"] == "PASS"`<br>`assert intent["gate_b_verdict"] == "PASS"`<br>`assert intent["policy_version"] == RH_BUCKET_POLICY_VERSION` |
| **SIGNED** | 继承 POLICY_APPROVED 全量<br>+ `signed_tx_hash`<br>+ `signer_address`<br>+ `nonce`<br>+ `signed_at` | `rh_tx_intents` (`signed_tx_hash`, `nonce`)<br>+ 签名回执记录 | `STATE_EVIDENCE_INCOMPLETE:SIGNED:<field>` | `assert signed_tx_hash.startswith("0x") and len(signed_tx_hash) == 66`<br>`assert signer_address.lower() == intent["wallet_id"].lower()`<br>`assert isinstance(intent["nonce"], int) and intent["nonce"] >= 0` |
| **BROADCAST** | 继承 SIGNED 全量字段<br>+ `broadcast_tx_hash`<br>+ `rpc_endpoint`<br>+ `broadcast_at`<br>+ `submission_attempt_count` | `rh_tx_intents` (payload)<br>+ 广播提交记录 | `STATE_EVIDENCE_INCOMPLETE:BROADCAST:<field>` | `assert broadcast_tx_hash == signed_tx_hash`<br>`assert len(rpc_endpoint) > 0`<br>`assert submission_attempt_count >= 1` |
| **CONFIRMED** | `request_id`<br>`tx_hash`<br>`block_number`<br>`block_hash`<br>`confirmations`<br>`finality_class`<br>`gas_used`<br>`actual_receipt_status`<br>`observed_at` | `rh_tx_receipts`<br>+ `rh_bucket_reservations`<br>(status="CONFIRMED") | `STATE_EVIDENCE_INCOMPLETE:CONFIRMED:<field>` | `assert receipt["status"] == "1" or receipt["actual_receipt_status"] == 1`<br>`assert block_hash.startswith("0x") and len(block_hash) == 66`<br>`assert int(receipt["gas_used"]) > 0` |
| **FAILED** | `request_id`<br>`failed_tx_hash`<br>`failure_reason`<br>`gas_burned`<br>`failed_at` | `rh_tx_receipts`<br>+ `rh_tx_intents` (payload) | `STATE_EVIDENCE_INCOMPLETE:FAILED:<field>` | `assert len(failure_reason) > 0`<br>`assert assert_decimal_text(gas_burned, "gas_burned")` |
| **REORG_PENDING** | `request_id`<br>`prior_block_hash`<br>`prior_block_number`<br>`reorg_detected_at`<br>`reorg_depth` | `rh_tx_receipts`<br>(reorg_detected=1)<br>+ reorg 审计记录 | `STATE_EVIDENCE_INCOMPLETE:REORG_PENDING:<field>` | `assert prior_block_hash.startswith("0x")`<br>`assert int(reorg_depth) >= 1` |
| **REVERTED** | `request_id`<br>`revert_evidence_json`<br>`reverted_at`<br>`loss_usd_gas` | `rh_tx_intents` (payload)<br>+ `rh_journal` 冲正记录 | `STATE_EVIDENCE_INCOMPLETE:REVERTED:<field>` | `assert len(json.loads(revert_evidence_json)) > 0`<br>`assert Decimal(loss_usd_gas) >= 0` |
| **REJECTED** | `request_id`<br>`reject_code`<br>`reject_reason`<br>`rejected_at`<br>`rejected_by_gate` | `rh_tx_intents` (state="REJECTED")<br>+ `rh_bucket_reservations`<br>(status="RELEASED") | `STATE_EVIDENCE_INCOMPLETE:REJECTED:<field>` | `assert len(reject_code) > 0`<br>`assert rejected_by_gate in ("GATE_A", "GATE_B", "SIMULATION", "PRE_CHECK")` |
| **ARCHIVED** | `request_id`<br>`archived_at`<br>`cleanup_verified` | `rh_tx_intents` (state="ARCHIVED") | `STATE_EVIDENCE_INCOMPLETE:ARCHIVED:<field>` | `assert cleanup_verified == 1 or cleanup_verified is True` |

### 2.3 核心证据断言与判定规则

代码实现中必须暴露独立的证据校验函数 `assert_state_evidence(state: str, row: Mapping)`。任何缺失字段必须抛出如下格式的异常，禁止吞掉异常或返回默认值：

```python
class StateEvidenceIncompleteError(Exception):
    \"\"\"Raised when an intent lacks required evidence fields for its state.\"\"\"
    pass

def assert_state_evidence(state: str, record: Mapping[str, Any]) -> None:
    required_fields = REQUIRED_EVIDENCE_BY_STATE.get(state)
    if required_fields is None:
        raise ValueError(f"UNKNOWN_STATE: {state}")
    
    missing = [f for f in required_fields if record.get(f) is None]
    if missing:
        raise StateEvidenceIncompleteError(
            f"STATE_EVIDENCE_INCOMPLETE:{state}:{missing[0]} (all_missing={missing})"
        )
```

---

## §3 白名单与拒绝点（Whitelists & Rejection Points）

### 3.1 Target 合约白名单 [PRD §14.1, §14.3, T48]

- **规则**：Calldata 的直接交互目标地址（`target`），以及 Multicall 内部的所有子调用目标地址，必须严格存在于 Target 白名单集合中。严禁与任何未登记的外部合约交互。
- **Base 主网（Chain ID: 8453）已知白名单**：
  1. `aerodrome_router` (Aerodrome Universal Router / SwapRouter)
  2. `pool_manager` (Uniswap V4 PoolManager / Aerodrome Slipstream CLPool)
  3. `nft_manager` (NonfungiblePositionManager, Uniswap V3 / Aerodrome CL)
  4. `weth9` (Canonical WETH9 on Base: `0x42000000000000000000000000000006`)
  5. `usdc` (Native USDC on Base: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- **判定与拒绝行为**：
  - 若主 target 不在白名单 → 抛出 `ContractViolationError("TARGET_NOT_ALLOWLISTED")`。
  - 若 Multicall 子调用 target 不在白名单 → 抛出 `ContractViolationError("SUBCALL_TARGET_NOT_ALLOWLISTED:<path>")`。
  - **处置**：直接标记意图状态为 `REJECTED`，拒绝码登记为 `TARGET_NOT_ALLOWLISTED`，同一事务内释放资金预留。

### 3.2 Recipient 接收方白名单 [PRD §14.3, T48]

- **规则**：Calldata 中任何资产接收方参数（如 `recipient`、`to`、`recipient` in `mint`/`collect`/`exactInputSingle`）必须严格限定为当前机器人的白名单地址。
- **允许的接收方集合**：
  1. `self_wallet`：当前运行钱包的公共地址（`wallet_id`）。
  2. `treasury_address`：已批准的资金库归集地址。
  3. `deployer_address`：已批准的部署者维护地址。
- **判定与拒绝行为**：
  - 若解析出的 recipient 地址不在白名单集合内 → 抛出 `ContractViolationError("RECIPIENT_NOT_ALLOWLISTED:<path>.recipient")`。
  - **严禁行为**：严禁代币接收方设置为 `address(0)`、外部不可信合约、或任何未经验证的第三方地址。
  - **处置**：直接置为 `REJECTED`，不进入任何签名流。

### 3.3 Selector 选择器白名单 [PRD §14.3]

- **规则**：Calldata 的前 4 字节方法选择器，以及 Multicall 解析后的每个子调用的方法选择器，必须严格落在以下 9 个已知选择器闭集中：
  1. `0x095ea7b3`：`approve(address spender, uint256 amount)`
  2. `0xa9059cbb`：`transfer(address recipient, uint256 amount)`
  3. `0x04e45aaf`：`exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))`
  4. `0x88316456`：`mint((address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256))`
  5. `0x219f5d17`：`increaseLiquidity((uint256,uint256,uint256,uint256,uint256,uint256))`
  6. `0x0c49ccbe`：`decreaseLiquidity((uint256,uint128,uint256,uint256,uint256))`
  7. `0xfc6f7865`：`collect((uint256,address,uint128,uint128))`
  8. `0x42966c68`：`burn(uint256)`
  9. `0xac9650d8`：`multicall(bytes[])`
- **判定与拒绝行为**：
  - 遇到任何未登记的选择器 → 登记进 `UNKNOWN_SELECTORS`，抛出 `ContractViolationError("UNKNOWN_SELECTOR:<selector>")`。
  - 禁止使用任何 fallback、receive 或带钩子参数的未定形函数。
  - **处置**：状态置为 `REJECTED`。

### 3.4 Size 单笔上限 [PRD §14.1, §16.3]

- **规则**：单笔交易的 USD 价值（`amount_usd`）必须满足：
  $$\text{amount\_usd} \le \text{CORE\_ACTIVE\_CAP} \times \text{LEG\_FRACTION}$$
- **参数标准基准**：
  - `CORE_ACTIVE_CAP`：当前 CORE 桶活动资金上限（当前默认 42.50 USD，由 100 USD × 50% 预算 × 85% 活动比例推导）。
  - `LEG_FRACTION`：单腿最大资金占比（基准设定为 `0.50`，即单笔最多动用活动上限的 50% = 21.25 USD；保守模式下为 `0.30` = 12.75 USD）。
- **判定与拒绝行为**：
  - 若 `amount_usd > CORE_ACTIVE_CAP * LEG_FRACTION` → 抛出 `ContractViolationError("SIZE_EXCEEDS_LEG_CAP")`。
  - 若 `amount_usd <= Decimal("0")` → 抛出 `ValueError("NON_POSITIVE_AMOUNT")`。
  - **处置**：拒绝该意图，写 `status = 'REJECTED'`，释放任何预分配额度。

### 3.5 Deadline 有效期窗口 [PRD §14.2]

- **规则**：Calldata 中包含的 `deadline` 参数（Unix 秒时间戳）必须位于严格的未来安全窗口内：
  $$\text{now\_unix} < \text{deadline} \le \text{now\_unix} + \text{MAX\_DEADLINE\_SECS}$$
- **常量定义**：`MAX_DEADLINE_SECS = 300`（5 分钟）。
- **判定与拒绝行为**：
  - 若方法应有 deadline 却解析不到 → 抛出 `ContractViolationError("DEADLINE_MISSING")`。
  - 若 `deadline <= now_unix` → 抛出 `ContractViolationError("DEADLINE_EXPIRED")`。
  - 若 `deadline > now_unix + MAX_DEADLINE_SECS` → 抛出 `ContractViolationError("DEADLINE_TOO_FAR")`（防止因长超时导致交易在未来极端不利行情下被打包）。
  - **处置**：状态置为 `REJECTED`。

### 3.6 Min_Out 最小到账下限与滑点保护（T50）[PRD §14.2, T50]

- **核心语义保护**：区分「合法的 0 数量腿」与「缺保护的 0」，严禁简单以 `!= 0` 一刀切判定安全。
- **三分支判定规则**：
  1. **合法单边 LP 零数量腿**：完全单边挂单的 LP，若策略明确预期某腿输入为 0（`leg0_expected_zero=True`），则该腿 `amount0Min == 0` 是合法的，标记通过理由为 `LEGITIMATE_ZERO_LEG`。
  2. **缺失滑点保护的非零腿**：策略预期该腿非零（`leg0_expected_zero=False`），但 calldata 中 `amount0Min == 0`；或者 Swap 交易中 `amountOutMinimum == 0` → 抛出致命违规 `ContractViolationError("MISSING_SLIPPAGE_PROTECTION")`。
  3. **Collect 伪造 minOut 违规**：无 Swap 行为的纯手续费提取（`collect`），本身只具有提取到账上限约束，若调用方硬塞入一个伪造的 `minOut` → 判定为协议语义篡改，抛出 `ContractViolationError("FABRICATED_MIN_OUT_ON_COLLECT")`。
- **底线阈值约束**：
  - 对于需保护的腿：$$\text{min\_out} \ge \text{quote\_min\_out} \times \text{MIN\_OUT\_FLOOR}$$
  - 常量：`MIN_OUT_FLOOR = Decimal("0.995")`（最大允许 50 bps 滑点损耗）。
- **处置**：任何滑点保护违规直接置为 `REJECTED`，严禁放行。

### 3.7 Gas 估算天花板 [PRD §14.2]

- **规则**：单笔交易所消耗的全部 gas 成本（含 L2 Execution Gas + L1 Data Gas）折算为 USD 后，必须小于等于绝对天花板：
  $$\text{simulated\_gas\_usd} \le \text{MAX\_GAS\_USD}$$
- **常量定义**：`MAX_GAS_USD = Decimal("0.50")`（Base L2 常态单笔交互费用通常在 $0.01–$0.15，超过 $0.50 视为网络拥堵或代码异常）。
- **判定与拒绝行为**：
  - 若模拟结果显示 gas 超过该上限 → 抛出 `ContractViolationError("GAS_EXCEEDS_CEILING")`，状态置为 `REJECTED`。

### 3.8 Policy Version 一致性 [PRD §14.1, §14.2]

- **规则**：意图携带的 `policy_version` 必须与系统当前生效的常量完全相等：
  $$\text{intent.policy\_version} == \text{RH\_BUCKET\_POLICY\_VERSION}$$
- **当前生效版本**：`"rh_50_30_20_proposed_v1"`。
- **判定与拒绝行为**：
  - 若版本不匹配 → 抛出 `ContractViolationError("POLICY_VERSION_MISMATCH")`，状态置为 `REJECTED`。

### 3.9 模拟通过不可作为白名单绕过证据（T48 红线）[PRD §14.3, T48]

- **核心红线**：**白名单违规与模拟执行结果完全正交解耦**。
- 即使本地 fork 模拟、Anvil 节点或 `eth_call` 返回 `success = true`，或者甚至模拟出丰厚盈利，只要触发 §3.1–§3.8 任一拒绝点（如目标合约不在白名单、滑点无保护、接收方异常），**必须无条件在签名前立即拒绝**！
- 严禁任何「因为模拟通过了，所以宽松放行」的代码逻辑分支。

---

## §4 闸门与签名前双开关（T47）

### 4.1 双开关架构原则与调用顺序

根据 PRD §14.1、§14.2 及用例 **T47**，在任何私钥接触待签名字节之前，必须顺序通过两道彼此完全独立的硬件级/函数级保护开关：
- **开关 A（Policy Gate，策略安全闸）**：主检**内容合规性**（目标、方法、金额、期限、滑点、Gas）。
- **开关 B（Intent Gate，意图与状态闸）**：主检**状态与证据完整性**（证据字段、哈希绑定、状态跃迁、资金预留、授权串）。

```
[Unsigned Calldata] ──► [ 开关 A: Policy Gate ]
                              │ (PASS)
                              ▼
                        [ 开关 B: Intent Gate ]
                              │ (PASS)
                              ▼
                        [ 授权模式校验 (T47) ]
                              │ (LIVE_TRADING == true)
                              ▼
                        [ 内存 Keystore 签名模块 ]
```

- **不可变调用协议**：
  1. 开关 A 必须在开关 B 之前执行。
  2. 开关 A 若失败，直接短路（Short-circuit），不再执行开关 B，立即标记意图为 `REJECTED` 并释放资金。
  3. 只有开关 A 和开关 B **双双返回 PASS**，且外部显式授权满足时，才允许将意图送入签名。

### 4.2 开关 A：Policy Gate（策略合规闸）

```python
def evaluate_policy_gate(
    decoded_call: Mapping[str, Any],
    policy_config: Mapping[str, Any],
    quote_context: Mapping[str, Any],
) -> GateResult:
    \"\"\"开关 A：全面校验白名单、金额上限、期限、滑点及 Gas 天花板。\"\"\"
```

- **输入参数**：
  1. `decoded_call`：由独立解码器（`lp_rh_calldata_decoder_v1_readonly`）解析出的纯净结构体。
  2. `policy_config`：当前生效的策略配置与合约白名单字典。
  3. `quote_context`：模拟时刻的真实链上报价快照。
- **内部校验流水线**：
  - [A-1] 校验 `target` 与所有 `subcall_targets` 是否属于 `policy_config["allowlist_targets"]`。
  - [A-2] 校验所有 `recipient` 是否属于 `policy_config["allowlist_recipients"]`。
  - [A-3] 校验所有 `selector` 是否属于已知 `SELECTORS`。
  - [A-4] 校验交易 USD 规模是否 $\le \text{CORE\_ACTIVE\_CAP} \times \text{LEG\_FRACTION}$。
  - [A-5] 校验 `deadline` 是否在 `[now + 1, now + MAX_DEADLINE_SECS]` 范围内。
  - [A-6] 校验各腿 min_out 是否满足 T50 滑点保护约束（无伪造 minOut、无裸 0）。
  - [A-7] 校验 ERC-20 `approve` 额度是否小于 $2^{255}$（绝对禁止无限授权，PRD §14.5）。
  - [A-8] 校验估算 Gas USD 是否 $\le \text{MAX\_GAS\_USD}$。
  - [A-9] 校验 `policy_version` 是否等于 `RH_BUCKET_POLICY_VERSION`。
- **输出格式**：
  `GateResult(verdict="PASS"|"REJECT", failure_reasons=[...], evaluated_at=...)`。

### 4.3 开关 B：Intent Gate（证据与状态完整性闸）

```python
def evaluate_intent_gate(
    intent_row: Mapping[str, Any],
    raw_calldata: str,
    conn: sqlite3.Connection,
) -> GateResult:
    \"\"\"开关 B：全面校验证据完整性、哈希防篡改、状态跃迁合法性及资金预留状态。\"\"\"
```

- **输入参数**：
  1. `intent_row`：`rh_tx_intents` 表中当前行数据。
  2. `raw_calldata`：准备交付签名的完整十六进制 Calldata 字节串。
  3. `conn`：SQLite 存储层连接句柄。
- **内部校验流水线**：
  - [B-1] **前置状态检查**：当前状态必须为 `SIMULATED`，拟变迁状态必须为 `POLICY_APPROVED`。
  - [B-2] **字段完整性检查**：按 §2.2 矩阵逐一断言 11 个意图绑定字段全部非 NULL [PRD §14.1]。
  - [B-3] **哈希绑定检查**：断言 `sha256(raw_calldata) == intent_row["calldata_hash"]`，防止构建与签名数据脱节。
  - [B-4] **模拟与实际绑定（T49）**：校验模拟时采用的报价与当前最新报价漂移未超限，且模拟对应的 `calldata_hash` 与当前完全一致。若发生变更，原模拟作废，必须重检 [PRD §14.2, T49]。
  - [B-5] **原子资金预留检查**：查询 `rh_bucket_reservations` 表，断言该 `intent_id` 存在一条 `status = "PENDING"` 且 `released_at IS NULL` 的有效记录，且预留金额与意图完全吻合 [PRD §16.3]。
  - [B-6] **Nonce 单调性初检**：断言拟使用的 nonce 大于当前链上已确认 nonce，且不与数据库中其他 `PENDING`/`BROADCAST` 意图冲突 [PRD §14.4]。
- **输出格式**：
  `GateResult(verdict="PASS"|"REJECT", failure_reasons=[...], evaluated_at=...)`。

### 4.4 签名前不可变前置断言（Pre-Sign Hard Invariant）

任何签名函数（无论在 Python 测试桩还是在独立执行器中）必须以硬编码方式在入口处植入以下断言，**没有任何传参开关可以绕过**：

```python
def sign_intent_transaction(
    intent: Mapping[str, Any],
    keystore: Any,
) -> SignedTx:
    \"\"\"核心签名入口：受限签名前断言保护。\"\"\"
    
    # 1. 检查全局实盘授权开关 (T47)
    if not CONFIG.LIVE_TRADING:
        raise PreSignBlockedError("T47_BLOCKED: LIVE_TRADING is False. Signing strictly forbidden.")
    if not CONFIG.TINY_LIVE_AUTHORIZED:
        raise PreSignBlockedError("T47_BLOCKED: tiny_live_authorized is False. Signing strictly forbidden.")
    
    # 2. 检查意图状态机位置
    if intent.get("state") != "POLICY_APPROVED":
        raise PreSignBlockedError(f"ILLEGAL_PRE_SIGN_STATE: expected POLICY_APPROVED, got {intent.get('state')}")
        
    # 3. 检查双开关凭证
    if intent.get("gate_a_verdict") != "PASS":
        raise PreSignBlockedError("GATE_A_NOT_PASSED: Cannot sign intent without Policy Gate approval.")
    if intent.get("gate_b_verdict") != "PASS":
        raise PreSignBlockedError("GATE_B_NOT_PASSED: Cannot sign intent without Intent Gate approval.")
        
    # 4. 检查签名者与意图绑定
    if keystore.address.lower() != intent.get("wallet_id", "").lower():
        raise SecurityViolationError("SIGNER_WALLET_MISMATCH: Keystore address does not match intent wallet.")
        
    # 5. 执行只读内存签名...
    ...
```

---

## §5 占位与未决（Placeholders and Deferred Items）

为了保证架构演进的清晰性，本契约在阶段一（RH-07a–RH-07e）显式定义部分「故意留空」与占位模块。**这些留空不是疏忽，而是严格按照 PRD §19 路线图设立的分阶段里程碑**。后续维护者严禁将这些留空误认为「遗漏的代码」而随意填补未经验证的逻辑。

### 5.1 MEV 与交易提交策略占位

- **所属里程碑**：Phase B / Stage C（实盘探索阶段）。
- **留空内容**：
  - 私有 RPC 节点集成（如 Flashbots Protect、Builder 直接提交、MEV-Share 回扣端点）。
  - 动态 Tip / Priority Fee 阶梯加价策略。
  - 基于 PBS（Proposer-Builder Separation）的私密防夹交易打包。
- **当前阶段约束与兜底**：
  - 阶段一与阶段二仅允许使用离线构造器、脱敏测试夹具以及本地 Anvil / Hardhat Fork 节点。
  - 不得配置任何收费 RPC 节点密钥；广播模块在非实盘模式下统一走 Mock 提交，返回虚拟确定性哈希。

### 5.2 L1/L2 Finality 分层阈值占位（T53/T54）

- **所属里程碑**：RH-07k（L1/L2 最终性分层交付包）。
- **留空内容**：
  - Base L2 Sequencer Batch 提交到 Ethereum L1 合约的交易包含证据解析。
  - L1 最终确认（`L1_FINALIZED`）的 64 个 epoch 状态断言算法。
  - 欺诈证明（Fault Proof）窗口期的状态跟踪。
- **当前阶段约束与兜底 [PRD §14.4, T53, T54]**：
  - 阶段一状态机在收到规范 L2 Receipt（`status=1`）后，止步于 `CONFIRMED` 状态。
  - **T54 红线**：严禁仅凭「在内存池中等待了超过 N 分钟」而无 L1 链上包含证据，就自动将交易状态由 `CONFIRMED` 标记为 `L1_FINALIZED`。
  - **T53 保护**：若仅出现 L1 Batch Posting 滞后，但 L2 多源节点仍在稳定产块并确认交易，系统只发出分层告警（Layered Alert），不得误判为 L2 执行全面停机。

### 5.3 深度重组与 Nonce 恢复占位（T51/T52）

- **所属里程碑**：RH-07i（Nonce 持久化与崩溃恢复包）。
- **留空内容**：
  - 深度大于 3 个区块的级联重组自动回滚重算引擎。
  - 进程在签名后、广播中途遭遇硬 Kill（SIGKILL）时的复杂跨节点 Nonce 探活对账状态机。
- **当前阶段约束与兜底 [PRD §14.4, §16.3, T51, T52]**：
  - 阶段一实现了基础状态 `REORG_PENDING`。
  - 一旦触发重组或广播状态未知（`BROADCAST_UNKNOWN`），系统一律**Fail-Closed 冻结**：立即停止派发该钱包后续任何意图，严禁更换 Nonce 重发同一动作，严禁释放对应资金预留，必须等待离线对账脚本（`lp_rh_reconciliation_v1.py`）仲裁判定。

### 5.4 残余库存与分步清算占位（T44/T45）

- **所属里程碑**：RH-07j（退出失败与残余库存会计包）。
- **留空内容**：
  - 流动性撤除（`decreaseLiquidity`/`collect`）成功后，自动将波动代币换回 USDG/USDC 的连续清算 Swap 链路。
  - 针对无深度代币的限价分批解套挂单算法。
- **当前阶段约束与兜底 [PRD §15.1, §15.2, T44, T45]**：
  - 阶段一只定义单一步骤原子动作。
  - 退出动作若发生「流动性移除成功，但换币 Swap 失败」，系统状态必须强制落在 `REMOVED_RISKY_INVENTORY`，**绝对严禁标记为 `cash closed` 或资金闭环退出**，风险资产必须全额计入当前清算 NAV 与回撤敞口。

### 5.5 占位状态下的安全兜底机制

| 占位模块名称 | 对应任务包 | 临时阻断判定 (Guard Assertion) | 违规后果 |
|---|---|---|---|
| **私密广播与 MEV** | Phase B | `assert not intent.get("is_private_bundle")` | 抛出 `FeatureNotImplementedError` |
| **L1 最终性自动升级** | RH-07k | `assert intent.get("state") != "L1_FINALIZED"` | 抛出 `FinalityEvidenceMissingError` |
| **重组自动重签** | RH-07i | `assert intent.get("state") != "AUTO_RESIGN"` | 抛出 `ReorgLockoutError`，人工介入 |
| **多跳原子退出** | RH-07j | `assert not intent.get("is_composite_exit")` | 仅允许分步独立意图提交与对账 |

---

## 附录：核心术语中英文对齐表

| 英文术语 | 中文标准对齐 | 定义解释 |
|---|---|---|
| **`rh_tx_intents`** | 交易意图表 | 记录受限执行生命周期的核心 SQLite 表 |
| **`rh_bucket_reservations`** | 资金桶预留表 | 记录三桶额度原子锁定与释放的记账表 |
| **`rh_tx_receipts`** | 交易收据表 | 记录链上真实回执、实际 gas 损耗与重组标记的表 |
| **`idempotency_key`** | 幂等主键 | 防止同一资金决策被重复创建意图的全局唯一键 |
| **`calldata_hash`** | 调用数据哈希 | 未签名字节串的 SHA256，用于在生命周期各环节防篡改 |
| **`Policy Gate (开关 A)`** | 策略合规闸 | 签名前第一道开关，校验白名单、规模、滑点与 Gas |
| **`Intent Gate (开关 B)`** | 意图与状态闸 | 签名前第二道开关，校验证据完整性、哈希一致性与资金锁定 |
| **`T47 Dual Switch`** | T47 双开关机制 | 签名前强制双重通过的硬件级拦截机制 |
| **`T50 Legitimate Zero`** | T50 合法零数量腿 | 允许单边 LP 保护腿合法为 0，与无保护裸 0 严格区分 |
| **`REORG_PENDING`** | 重组未决状态 | 检测到链上分叉时，冻结资金与 Nonce 的中间保护状态 |
| **`REMOVED_RISKY_INVENTORY`** | 撤池残余风险库存 | 退出时流动性已撤除但未成功兑换为稳定币的真实敞口 |
