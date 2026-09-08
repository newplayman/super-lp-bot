# 股票代币合约真实 ABI 实测（2026-09-08 08:0x UTC，主脑亲跑）

## 1. PRD §9.5 假设的四个方法**全部不存在**

PRD §9.5 要求「由 token 合约实际 ABI 读取 `uiMultiplier()`、`newUIMultiplier()`、`effectiveAt()`、`oraclePaused()`」。对 CRWD / SGOV / GLD / SPY / QQQ 逐个 `eth_call`，**四个方法全部 `execution reverted`**。

这**不是** PRD 的错——PRD 原文已写明「不要假定通用 Chainlink aggregator 也暴露 token 的暂停函数」「读取失败标 UNKNOWN，不当 false」。实测证明这条防御是必要的：按文档名字硬编码 selector 会让每个股票代币的乘数读取永久失败，而 fail-closed 会把它们全判成 `INPUTS_UNAVAILABLE`。

## 2. 真实结构：**beacon 代理**，不是 EIP-1967 直接代理

```
股票代币 (283 B)  ──delegatecall──▶  beacon 0xe10b6f6b275de231345c20d14ab812db62151b00
                                        └─ implementation() ─▶ 0xb35490d6f9163de4f80d88dc75c3516eb64c5ae2 (11,614 B)
```

- EIP-1967 的 `implementation` 槽为 **0**，`beacon` 槽为 `0xe10b…1b00`。只查 implementation 槽会得到零地址而误判「无实现」。
- 194 个股票代币**共用同一个 beacon**，即共用同一份实现。**含义：beacon 一次升级会同时改变全部 194 个代币的行为**，这是 PRD §7.1「proxy／implementation／管理员变更监控」必须盯住的单点。

## 3. 从实现字节码枚举出真实方法，并交叉验证乘数

在实现合约字节码里提取 73 个 PUSH4 候选 selector，逐个通过代理调用，得到 **16 个可调用的无参 view 方法**。其中：

| selector | 返回（CRWD） | 判定 |
|---|---|---|
| `0xa60bf13d` | `4000000000000000000` | **乘数**（1e18 定点） |
| `0xdc767007` | `4000000000000000000` | 乘数（同值，疑为别名或 pending 口径） |
| `0x5c975abb` | `0` | **`paused()`**（OpenZeppelin Pausable 标准 selector） |
| `0x313ce567` | `18` | `decimals()` |
| `0x18160ddd` | `52861750000000000000` | `totalSupply()` |
| `0x97a4064f` | `1782999000` | 待定（疑为时间戳或价格，需再验） |

**交叉验证 15 个代币，链上 `0xa60bf13d / 1e18` 与 API `currentMultiplier` 精确一致 15/15**：

| 代币 | API `currentMultiplier` | 链上 `0xa60bf13d/1e18` |
|---|---|---|
| CRWD | 4.000000000000000000 | 4 |
| SGOV | 1.005101770003214918 | 1.005101770003214918 |
| CCL | 1.021486444855206408 | 1.021486444855206408 |
| AAPL | 1.000566080061092436 | 1.000566080061092436 |
| ORCL | 1.002210914971013375 | 1.002210914971013375 |

（其余 10 个同样精确一致，无一例外。）

## 4. 对实现的四条要求

1. **乘数用 `0xa60bf13d` 读链上值，API 作交叉校验**。两者不一致 → `SOURCE_DISAGREEMENT`，禁止新仓（PRD §9.3）。不得只信 API。
2. **暂停状态用 `0x5c975abb`（`paused()`）**，不是 PRD 假设的 `oraclePaused()`。当前 15 个样本全为 `0`（未暂停）。
3. **beacon 升级监控是 P0**：`0xe10b…1b00` 的 `implementation()` 返回值必须入 `rh_contract_attestations` 并逐轮比对；一旦变化，**全部 194 个代币的 attestation 同时过期**（T06）。
4. `newUIMultiplier()` / `effectiveAt()` 无对应方法 → 未来公司行动只能从 REST `/rhj/corporate-actions` 获取（当前 41 条全是现金分红，`pendingMultiplier` 全空）。链上无前瞻乘数信号，`CORP_ACTION_GUARD` 必须依赖 API，且该依赖须显式记录为**单点数据源风险**。

## 5. 未决

- `0xdc767007` 与 `0xa60bf13d` 返回同值，需在 `pendingMultiplier` 非空的代币上区分（当前全链无此样本，**无法验证**，记 `UNVERIFIED`）。
- `0x97a4064f` 返回 `1782999000`，量级像 Unix 时间戳（2026-07-01 前后）也像定点价格，**未确认，不得使用**。
- Chainlink 股票 feed 地址尚未定位，token-equivalent 参考价仍缺（RH-05 证据 ②）。
