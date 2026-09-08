# RH-05b：链上乘数读取器与 beacon attestation（离线可测）

## 背景（一段）

主脑 2026-09-08 实测（证据：`reports/rh_pivot/20260907T124500Z/RH-05-research/STOCK_TOKEN_ABI_DISCOVERY_20260908.md`）推翻了 PRD §9.5 的 ABI 假设并找到真实入口：

- PRD 假设的 `uiMultiplier()` / `newUIMultiplier()` / `effectiveAt()` / `oraclePaused()` **全部 revert**，不存在。
- 股票代币是 **beacon 代理**：EIP-1967 `implementation` 槽为 0，`beacon` 槽 = `0xe10b6f6b275de231345c20d14ab812db62151b00`；`beacon.implementation()`（selector `0x5c60da1b`）返回 `0xb35490d6f9163de4f80d88dc75c3516eb64c5ae2`（11,614 B）。**194 个代币共用同一实现**。
- 真实 selector（主脑交叉验证）：
  | selector | 语义 | 证据 |
  |---|---|---|
  | `0xa60bf13d` | 乘数，1e18 定点 | 15/15 与 API `currentMultiplier` 精确一致 |
  | `0x97a4064f` | **乘数最后生效时间戳**（Unix 秒） | 12/12 与「乘数≠1」集合精确重合，182 个乘数为 1 的返回 0 |
  | `0x5c975abb` | `paused()`（OZ 标准） | 当前样本全为 0 |
  | `0xdc767007` | 与 `0xa60bf13d` 同值 | **UNVERIFIED**，无 pending 样本可区分 |
  | `0x9bea6429` | 疑为乘数调整后供应量 | **UNVERIFIED**，QQQ 恰等 totalSupply 但 GLD/SPY 不等 |

`scripts/lp_rh_stock_reference_v1_readonly.py`（纯计算，已提交）需要一个**数据来源层**把这些链上值喂给它。本包做该层，**注入式 RPC，不联网**（真实抓取由主脑做）。

## 新增文件

1. `scripts/lp_rh_multiplier_reader_v1_readonly.py`（**≤ 250 行**）
   - 顶部仓库通行 sys.path 引导；金额与乘数一律 `Decimal`；禁止 float。
   - 常量（**必须用这些实测值，不得自创**）：
     ```python
     SEL_MULTIPLIER      = "0xa60bf13d"
     SEL_MULT_EFFECTIVE  = "0x97a4064f"
     SEL_PAUSED          = "0x5c975abb"
     SEL_DECIMALS        = "0x313ce567"
     SEL_TOTAL_SUPPLY    = "0x18160ddd"
     SEL_BEACON_IMPL     = "0x5c60da1b"
     EIP1967_BEACON_SLOT = "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"
     EIP1967_IMPL_SLOT   = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
     KNOWN_BEACON        = "0xe10b6f6b275de231345c20d14ab812db62151b00"
     UNVERIFIED_SELECTORS = {"0xdc767007": "same value as multiplier; no pending sample to distinguish",
                             "0x9bea6429": "matches totalSupply on QQQ only; unconfirmed"}
     ```
   - `dataclass OnChainMultiplier`：`token, multiplier_human: Decimal|None, effective_at_unix: int|None, paused: bool|None, decimals: int|None, total_supply_raw: int|None, read_errors: list[str], block_number: int|None`。
   - `read_multiplier(token, *, rpc_fn, block="latest") -> OnChainMultiplier`：逐 selector `eth_call`。**任一读取失败 → 对应字段 `None` 并把错误记进 `read_errors`，绝不填 0 或 False**（PRD §9.5：读取失败标 UNKNOWN）。`multiplier_human = raw / 10**18`。`effective_at_unix` 为 0 时表示**从未变更**，转为 `None` 并在 `read_errors` 之外单列（不是错误）。
   - `resolve_beacon(token, *, rpc_fn) -> dict`：读两个槽；若 `implementation` 槽非零 → 直接代理；若 `beacon` 槽非零 → 调 `beacon.implementation()` 取实现地址。返回 `{"proxy_kind": "BEACON"|"DIRECT"|"UNKNOWN", "beacon", "implementation", "matches_known_beacon": bool}`。**`beacon != KNOWN_BEACON` 时 `matches_known_beacon=False`，调用方须视为 attestation 失效。**
   - `detect_multiplier_change(previous: OnChainMultiplier, current: OnChainMultiplier) -> tuple[bool, str]`：`effective_at_unix` 变化 → `(True, "MULTIPLIER_EFFECTIVE_AT_CHANGED")`；乘数值变化但时间戳未变 → `(True, "MULTIPLIER_VALUE_CHANGED_WITHOUT_TIMESTAMP")`（**异常，须告警**）；都没变 → `(False, "STABLE")`。任一方有 `None` 字段 → `(True, "UNKNOWN_CANNOT_COMPARE")`（保守）。
   - `cross_check_api(onchain: OnChainMultiplier, api_current_multiplier: str|None) -> tuple[str, str]`：两者相等 → `("AGREE","")`；不等 → `("SOURCE_DISAGREEMENT", 描述)`；任一为 None → `("UNKNOWN", 描述)`。**用于 PRD §9.3「参考源不一致时停止新增，不用加权平均把冲突隐藏掉」。**
   - `attestation_record(token, onchain, beacon_info, *, now) -> dict`：产出可直接写 `rh_contract_attestations` 的行（`chain_id/address/block_hash/policy_version/code_hash/implementation/attestation_status/evidence_json/expires_at/created_at`）。`matches_known_beacon` 为 False 或有 `read_errors` → `attestation_status="DISCOVERED_NOT_ATTESTED"`，否则 `"ATTESTED_SAME_BLOCK"`。
   - `main()`：`--fixture <json>`（离线回放）、`--out <file>`。不联网。
2. `tests/test_lp_rh_multiplier_reader_v1_readonly.py`（≤ 250 行），**全部注入假 `rpc_fn`，不联网**，至少 16 个测试：
   - CRWD 场景：`0xa60bf13d` 返回 `4e18` → `multiplier_human == Decimal("4")`；`0x97a4064f` 返回 `1782999000` → `effective_at_unix == 1782999000`。
   - 乘数为 1 的代币：`0x97a4064f` 返回 0 → `effective_at_unix is None`，且**不进 `read_errors`**（从未变更不是错误）。
   - 读取失败：`0xa60bf13d` revert → `multiplier_human is None`，`read_errors` 非空，**不得为 0**。
   - `paused` 读取失败 → `paused is None`（**不是 False**）。
   - `resolve_beacon`：impl 槽为 0、beacon 槽为 `KNOWN_BEACON` → `proxy_kind=="BEACON"`、`matches_known_beacon is True`。
   - beacon 槽为**其它地址** → `matches_known_beacon is False`（升级检测）。
   - impl 槽非零 → `proxy_kind=="DIRECT"`。
   - `detect_multiplier_change` 四种情形各一例，含「值变但时间戳没变」的异常分支。
   - `cross_check_api`：一致 / 不一致 / None 三例；不一致时返回 `SOURCE_DISAGREEMENT`。
   - `attestation_record`：beacon 不匹配 → `DISCOVERED_NOT_ATTESTED`；有 read_errors → 同样；全正常 → `ATTESTED_SAME_BLOCK`。
   - 源码断言：`UNVERIFIED_SELECTORS` 中的两个 selector **不得**被 `read_multiplier` 调用（`grep` 断言它们只出现在常量字典里）。
   - 断言模块不含 `uiMultiplier`、`oraclePaused` 等 PRD 假设但不存在的字符串（除注释说明外）。

## 不许动什么

- 不改任何现有脚本/测试；**不许碰 `scripts/lp_rh_collector_v1_readonly.py`（生产运行中）**、`lp_rh_shadow_runner_v1_readonly.py`（另一 worker 正在写）、`lp_rh_stock_reference_v1_readonly.py`。
- 不联网、不写活库、不读 `.env*`、不用 float。
- **不得使用 `0xdc767007` 与 `0x9bea6429`** 做任何判定（它们是 UNVERIFIED，只登记不使用）。
- 不要用 TaskCreate/TaskUpdate 工具；单次 Write/Edit ≤150 行。

## 验收标准

- [ ] `git status --short` 新增只有 1 脚本 + 1 测试；`git diff --stat` 为空。
- [ ] 脚本 ≤250 行；新测试 ≥16 个且全绿。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` 0 failed、14 skipped。
- [ ] `grep -nE 'float\(' scripts/lp_rh_multiplier_reader_v1_readonly.py` 零命中。
- [ ] 读取失败时相关字段为 `None` 而非 0/False，有测试断言。

## 验证命令

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_multiplier_reader_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
grep -nE 'float\(' scripts/lp_rh_multiplier_reader_v1_readonly.py || echo NO_FLOAT
git diff --stat; git status --short | grep -E 'lp_rh_multiplier'
```
