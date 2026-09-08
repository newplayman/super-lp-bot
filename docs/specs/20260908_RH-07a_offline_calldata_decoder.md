# RH-07a：独立 calldata 解码器（纯离线，零签名零广播）

## 背景
PRD §14.3 要求「已生成的 calldata 由**独立 decoder** 校验 target、selector／command、token、recipient、amount、deadline、允许的路径」，§14.2 要求签名前重检，用例 **T48**（calldata 含非白名单 target／recipient → decoder 拒绝，simulation 成功也不能放行）、**T50**（单边 LP 的零数量腿 vs swap 最小到账无约束，区分合法 0 与缺保护，不靠简单 `!=0` 判断）。

**本包不涉及任何签名、广播、私钥、钱包**。只做字节串解析与白名单校验，纯函数，离线可测。这是 RH-07 中**唯一不需要额外授权**的部分（PRD §19 RH-07 允许「保留安全设计与离线接口」）。

## 只新建两个文件
1. `scripts/lp_rh_calldata_decoder_v1_readonly.py`（≤300 行）
   - 顶部仓库通行 sys.path 引导。**禁止 import web3/eth_account/solders/solana**，纯标准库。
   - `SELECTORS`：已知方法的 4 字节选择器与参数布局，至少覆盖
     `approve(address,uint256)=0x095ea7b3`、`transfer(address,uint256)=0xa9059cbb`、
     `exactInputSingle` / `mint` / `increaseLiquidity` / `decreaseLiquidity` / `collect` / `burn` / `multicall(bytes[])=0xac9650d8`。
     **不确定的选择器不要编造**，登记进 `UNKNOWN_SELECTORS` 并在解码时返回 `UNKNOWN_SELECTOR` 状态。
   - `decode_calldata(data: str) -> dict`：返回 `{"selector", "known": bool, "args": [...], "raw_words": n}`。按 32 字节字切分；`address` 取低 20 字节；`uint256` 取整数；`bytes[]` 递归解 multicall 的每个子调用。**长度不足或非 4 字节对齐 → `MALFORMED_CALLDATA`**。
   - `check_targets(decoded, *, target, allowlist: set[str]) -> tuple[bool, list[str]]`：**T48**。`target` 不在白名单 → 拒；multicall 内任一子调用的 target 不在白名单 → 拒；解码出的 `recipient` 参数不在 `allowlist` ∪ `{self_wallet}` → 拒。返回全部违规项，不短路。
   - `check_amount_protection(decoded, *, leg0_expected_zero: bool, leg1_expected_zero: bool) -> tuple[bool, list[str]]`：**T50 核心**。对含 `amountOutMinimum` / `amount0Min` / `amount1Min` 的调用：
     - 该腿**预期为零**（单边 LP）且 min 为 0 → **合法**，记 `LEGITIMATE_ZERO_LEG`；
     - 该腿**预期非零**但 min 为 0 → **违规** `MISSING_SLIPPAGE_PROTECTION`；
     - 无 swap 的 `collect` 不要求 minOut，若调用方硬塞一个伪造的 minOut → 记 `FABRICATED_MIN_OUT_ON_COLLECT`。
     **绝不能用 `min != 0` 一刀切判安全。**
   - `check_deadline(decoded, *, now_unix: int, max_horizon_secs: int = 300) -> tuple[bool, str]`：`deadline` 缺失 → `DEADLINE_MISSING`；`deadline <= now` → `DEADLINE_EXPIRED`；`deadline > now + max_horizon` → `DEADLINE_TOO_FAR`。
   - `check_approval(decoded) -> tuple[bool, str]`：`approve` 的 amount 等于 `2**256-1` 或 `2**255` 量级 → `UNLIMITED_APPROVAL_FORBIDDEN`（PRD §14.5）。
   - `verify_intent(decoded, *, intent: Mapping) -> tuple[bool, list[str]]`：把解码结果与意图声明比对，任一字段不一致 → 拒。要求意图含 `chain_id, wallet_id, position_id, request_id, decision_id, idempotency_key, policy_hash, code_version, snapshot_hash, calldata_hash, expires_at`；**缺任一字段直接拒**（PRD §14.1：字段不完整不接受）。
   - `main()`：`--calldata --target --allowlist-json --intent-json --out`，不联网。
2. `tests/test_lp_rh_calldata_decoder_v1_readonly.py`（≤300 行，≥20 测试）
   - `decode_calldata` 对 `approve(address,uint256)` 正确解出地址与金额；长度不对 → `MALFORMED_CALLDATA`；未知 selector → `UNKNOWN_SELECTOR` 且 `known is False`。
   - multicall 递归解出两个子调用，其中一个 target 不在白名单 → `check_targets` 拒并指名该子调用。
   - **T48**：recipient 是白名单外地址 → 拒，理由含 `RECIPIENT_NOT_ALLOWLISTED`。
   - **T50 三分支**：单边 LP 零腿 min=0 → 合法；非零腿 min=0 → `MISSING_SLIPPAGE_PROTECTION`；collect 带伪造 minOut → `FABRICATED_MIN_OUT_ON_COLLECT`。**必须三条都有独立测试。**
   - deadline 缺失／过期／过远 三例。
   - `approve` 无限额度 → `UNLIMITED_APPROVAL_FORBIDDEN`；有限额度通过。
   - `verify_intent` 缺任一必填字段 → 拒（参数化遍历 11 个字段）。
   - 源码断言：不含 `import web3`、`eth_account`、`sign`、`send_raw`、`private_key`。

## 不许动
不改任何现有文件；不联网；不写活库；不碰 `lp_rh_collector_v1_readonly.py`（生产运行中）与 `lp_rh_shadow_runner`（另一 worker 正在重写）。不要用 TaskCreate/TaskUpdate。

## 验收
`pytest tests/test_lp_rh_calldata_decoder_v1_readonly.py -q` 全绿且 ≥20；全量 0 failed / 14 skipped；`git diff --stat` 为空。
