# W1 SPEC — RH 专属交易身份、合法正例和原子准入

**目标 SHA**: 18a8f39744af2d61d16737b7311d88cd88accea9
**owner-授权**: 已批 V3 taskpack（仅代码+测试，不启动服务）

## 范围

只动：
- `scripts/lp_rh_calldata_whitelist_gate_v1_readonly.py` (新增 RH 入口 + 保留旧 Base)
- `scripts/lp_rh_calldata_decoder_v1_readonly.py` (确保 ABI 解析支持 UniswapV3 mint/burn/collect)
- `scripts/lp_rh_tx_intents_writer_v1.py` (强化事务/幂等分类)
- `scripts/lp_rh_shadow_daemon_v1_readonly.py` (admission-precede + 真实 grant 路径)
- `tests/test_lp_rh_calldata_whitelist_gate_v1_readonly.py` (新增 RH 正负控制)
- `tests/test_lp_rh_tx_intents_writer_v1.py` (新增第二连接/trigger/不同 payload 拒绝)
- `tests/test_lp_rh_shadow_daemon_v1_readonly.py` (新增 admission-precede + 真实 grant E2E)

**不许动**:
- `internal/adapters/` (Go 代码)
- `tools/audit_repro/` 
- `scripts/lp_rh_paper_readiness_v1.py` (W3)
- CLAUDE.md / 任何冻结常量
- `feature/prd-v2.1-m0-shadow` 之外分支

## 必须交付

### F1: RH 专属 target 集合（不动旧 Base）

新建独立模块 `scripts/lp_rh_chain_manifest_v1_readonly.py`：
- 常量 `CHAIN_ID_RH_MAINNET = 4663` / `CHAIN_ID_RH_TESTNET = 46630`
- `RH_CORE_TARGETS: frozenset[str]`（Uniswap V3 NPM 在 RH 主网的实际地址 — 若无可靠主网地址，使用 0x0 哨兵并标注 UNVERIFIED；本轮不连 RPC，仅在 manifest 标记 "待 RPC 核验"）
- `RH_CORE_SELECTORS: frozenset[str]`（0x88316456 mint, 0x42966c68 burn, 0xfc6f7865 collect, 0xac9650d8 multicall, 0x219f5d17 increaseLiquidity, 0x0c49ccbe decreaseLiquidity）
- `verify_chain_manifest(chain_id, target, selector, role)` — 验证 role+address+selector 三元组是否在 manifest 中
- `_MANIFEST_VERSION = "rh-core-v1.0.0-unverified-2026-09-13"`
- 显式标注 "本 manifest 仅由人工/RPC 核验升级到 VERIFIED；当前为 UNVERIFIED_PENDING_RPC"

### F2: wrapper 接受 RH chain_id + 拒绝 Base

修改 `lp_rh_calldata_whitelist_gate_v1_readonly.py`:
- 顶部导入 `from scripts.lp_rh_chain_manifest_v1_readonly import RH_CORE_TARGETS, verify_chain_manifest, CHAIN_ID_RH_MAINNET`
- 新增 `_validate_rh(intent, decoded)` → 返回 (ok, reason)
- 当 `intent["chain_id"] == 4663` 时使用 RH 路径；当 == 8453 时保留旧 Base 路径；当为 None/其他值时拒绝 `whitelist_reject:unsupported_chain:<id>`
- 旧 Base target 表保留（不变），但与 RH 物理隔离

### F3: 真实 RH V3 mint calldata 正例

新建测试 fixture `tests/fixtures/rh_v3_mint_calldata.py`:
- 用 Python 直接编码 `mint((token0, token1, fee, tickLower, tickUpper, amount0Desired, amount1Desired, amount0Min, amount1Min, recipient, deadline))` 为 ABI bytes
- selector 必须 == `0x88316456`
- 提供两个样本：legal full-range 和 legal concentrated (tickLower=-887220, tickUpper=887220)
- 提供 expected_intent dict（含全部 claims: chain_id=4663, wallet, request_id, decision_id, position_id, policy_hash, code_version, snapshot_hash, expires_at）

### F4: 单因素负控制（每个负控制必须有 fail reason assertion）

在 `tests/test_lp_rh_calldata_whitelist_gate_v1_readonly.py` 中新增：
1. `test_rh_legal_mint_passes` — 用 F3 fixture，断言 ok=True
2. `test_rh_legal_collect_passes` — selector=0xfc6f7865, ok=True
3. `test_rh_legal_multicall_with_inner_mint_passes` — multicall 含一个 mint 子调用
4. `test_rh_wrong_chain_8453_rejected` — chain_id=8453 with RH target → `whitelist_reject:chain_mismatch`
5. `test_rh_wrong_target_rejected` — target=0xdeadbeef → `target_not_whitelisted`
6. `test_rh_wrong_selector_rejected` — selector=0xdeadbeef → `selector_not_whitelisted`
7. `test_rh_wrong_recipient_rejected` — recipient=0xaaaa... → `recipient_not_whitelisted`
8. `test_rh_expired_deadline_rejected` — past deadline → `deadline_expired`
9. `test_rh_calldata_hash_mismatch_rejected` — wrong hash → `calldata_hash_mismatch`
10. `test_rh_multicall_with_unknown_inner_selector_rejected` — multicall 内含 0xdeadbeef → `multicall_inner_reject`
11. `test_rh_missing_min_protection_rejected` — amount0Min=0 + amount1Min=0 → `missing_slippage_protection`（multicall 之外）
12. `test_rh_value_mismatch_rejected` — expected_value_wei 不同于 actual → `value_mismatch`

### F5: admission-precede + 真实 grant E2E

新建 `tests/test_lp_rh_shadow_daemon_v1_readonly.py::TestAdmissionPrecedeAndRealGrant`:
- `test_admission_reject_leaves_no_journal` — 配置 cfg 使 admission fail，但 verify_calldata=True + 合法 calldata → 仍走 admission-precede fail → 断言 rh_journal 行数 == 0
- `test_admission_reject_leaves_no_position_marks` — 同上断言 rh_position_marks 无虚拟 LP 行
- `test_admission_reject_leaves_reservations_consistent` — 同上断言 rh_bucket_reservations 状态不是 PENDING 泄漏
- `test_real_grant_writes_position_and_journal` — 配置 partial size 100/1000 + verify_calldata=True + 合法 RH calldata → 断言 rh_tx_intents state=VALIDATED/WHITELIST_PASSED + rh_position_marks 有 entry 行 + rh_journal 有 debit/credit 行
- `test_unverified_manifest_blocks_entry` — RH manifest 标记 UNVERIFIED_PENDING_RPC 时 admission 必须 fail（不允许拿未核验地址当合法）

### F6: 文件 SQLite 事务/第二连接/trigger/幂等内容冲突

新建 `tests/test_lp_rh_tx_intents_writer_v1.py::TestFileSqliteTransactionMatrix`:
- `test_writer_does_not_autocommit_inside_caller_transaction` — 已在 V2 测过，**保留**
- `test_second_connection_sees_no_uncommitted_data` — 开两个 sqlite3.connect，第二个连接在事务中 insert 第一个连接的行时**不可见**
- `test_integrity_error_on_different_payload_returns_conflict` — 同 idempotency_key 但 chain_id/wallet/calldata_hash 改变 → 抛 IntegrityError，writer 不当作 idempotent_hit
- `test_unique_idempotency_key_same_payload_is_idempotent_hit` — 同 key + 同 payload → writer 返回 idempotent_hit=True，不写新 row
- `test_trigger_abort_propagates` — schema 加 trigger RAISE(ABORT) 在 update_state → writer.update_state 抛 IntegrityError
- `test_concurrent_reservations_dont_overcommit` — 两 writer 同 episode 并发 → 第二个进入 writer 时第一个已完成 commit，第二个的 reservation 不重复（依赖 unique constraint on intent_id）

## 验收命令

```bash
# 1. 文件写入 ≤150 行/6000 字符/次
# 2. 单元测试
python -m pytest tests/test_lp_rh_calldata_whitelist_gate_v1_readonly.py -v --tb=short -p no:cacheprovider
python -m pytest tests/test_lp_rh_tx_intents_writer_v1.py -v --tb=short -p no:cacheprovider
python -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py -v --tb=short -p no:cacheprovider
# 3. 全量回归（含 V2 已修 53 baseline）
python -m pytest tests/ -q --tb=line -p no:cacheprovider --junitxml=/tmp/w1_junit.xml
# 4. 不能新增 baseline fail
# 5. silent_failure_lint 不能新增 hit
python -m pytest tests/test_lp_silent_failure_lint_v1_readonly.py::test_repo_fail_on_new_clean -v --tb=short -p no:cacheprovider
```

## 风险与边界

- 不连任何 RPC；RH 主网地址用占位 0x0 + manifest 标 UNVERIFIED
- 不启动 daemon
- 不创建私钥
- 不放宽六个常量
- 修旧 runner 层（A 类 39 fail）不在 W1 范围
- 不动 Go 代码

## 输出要求

每完成一个 F 分块运行对应 pytest，贴最后 10 行。最后一次全量回归贴最后 5 行 + 总 fail/pass/skip 计数与 V2 基线对比。
