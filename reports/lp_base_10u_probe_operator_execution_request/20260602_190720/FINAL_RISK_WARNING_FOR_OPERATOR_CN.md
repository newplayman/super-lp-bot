# Final Risk Warning for Operator

- stage: `LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1`
- phase: F
- run_id: `20260602_190720`

## 操作员请直接读

### 1) 这个 probe **可能亏钱**

最坏情况下，你会损失大约 **20 USD**（10 USD 本金 + 大约 10 USD gas）。
这不是夸张，是 worst case 实际数值。

如果你 **不能从容承受 20 USD 损失**，请选 **C（停）**。

### 2) 当前 **EV 没有证明为正**

整个 LP 研究目前处于 FROZEN，`edge_proven = no`，`tiny_canary_allowed = no`。
本 probe **不是** 一个被证明会赚钱的实验。

如果你想让 bot 去 **赚钱**，请选 **C（停）** 或 **B（回去修包）**。
本 probe **不会** 让你赚钱。

### 3) 10U 是为了买 **数据**，不是为了 **盈利**

成功标准是：

- 拿到真实 tokenId
- 拿到真实 fee accrual 数据
- 拿到真实 PnL 数字（不论正负）
- 拿到 4-5 笔 tx 的真实 gas / slippage 数据

**赚钱不在成功标准里**。如果 probe 跑完亏了 5 USD 但数据都拿到了，按本 spec 是 **成功**。

### 4) 如果你 **不愿损失 10U**，**不要继续**

不要因为 "也许会赚" 就继续。当前阶段也没有"也许会赚"的根据。
直接选 **C**。

### 5) 如果你 **不愿** 给脚本未来签名权限，**不要继续**

下一阶段（A 路径）会构造 armed runner，**armed runner 是会构造 signer 的**（虽然仍受 3-gate + 2-default 控制）。
如果你不接受 "下一阶段会 build 一个能签名的工具" 这件事，请选 **C** 或 **B**。

### 6) 如果你 **不接受** tokenId / actual fee / PnL 记录失败的风险，**不要继续**

可能发生:
- mint receipt 解析失败 ⇒ tokenId 拿不到 ⇒ 手工 inspect 后决定
- positions(tokenId) 与 expected 不匹配 ⇒ manual intervention
- decreaseLiquidity 成功但 collect 失败 ⇒ tokens 卡在 NPM
- RPC 不稳定导致 fee state 时间点漏读 ⇒ actual_fee_ready = false

这些情况都可能发生在真实执行阶段。如果你不能接受这些数据不完整的可能性，请选 **C**。

### 7) 如果你 **继续**，必须理解这是 **链上真实资金实验**

不是 testnet。不是 simulation。不是 dry-run。
当代码经过若干 stage 之后真正发出 tx 那一刻，**真钱会动**。

每个被发出的 tx：
- 会消耗真实 ETH gas
- 会涉及真实 USDC 余额（来自钱包 `0xb05b...d835`）
- 会在 Base 链上产生不可撤销的状态变化
- 会被 Etherscan / blockchain explorer 永久记录
- **不可** 撤销 / 不可 undo / 不可 rollback

如果以上任何一项让你不安，请选 **C** 或 **B**。

## 简短总结

| 你的情况 | 选 |
|---|---|
| 我接受最坏 ~20 USD 损失；我懂这是数据采集；我愿意继续 | **A** |
| 我看到包里某项不对，我想先改它 | **B** |
| 上面任何一条让我不安 | **C** |

## 不选 = 默认 C

如果你不在下一个 prompt 中明确说出 A / B / C，**默认行为是 C**（停 / 等）。
"WAIT_FOR_OPERATOR_DECISION" 与 "STOP_LP_RESEARCH_NOW" 在效果上对当前阶段是等价的：**不进 armed build**。

要进 A 必须主动声明。

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
execution_allowed_now         = false
hard_disable_still_active     = true
edge_proven                   = no
tiny_canary_allowed           = no
default_when_no_choice        = C (stop / wait)
```
