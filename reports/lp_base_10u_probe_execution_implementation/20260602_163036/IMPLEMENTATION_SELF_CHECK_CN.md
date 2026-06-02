# Implementation Self-Check 报告

- stage: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`
- phase: J
- run_id: `20260602_163036`

## 5 个 self-check case 全部通过

| # | mode | exit | result | 关键观察 |
|---|---|---|---|---|
| J1 | `preflight` | 0 | **PASS** | drift_ticks=-281; proposed [-200924, -200524]; dry_run_only=True; no_send=True; execution_enabled=False |
| J2 | `print-unsigned` | 0 | **PASS** | unsigned_only=True; no_signature=True; no_send=True; tick_lower=-200924 (**DYNAMIC, NOT legacy -200643**); deadline now+3600 |
| J3 | `validate-approval` (valid) | 0 | **PASS** | valid=True; **executes_now=False; authorization_granted=False; all_three_gates=False** (gate_3 missing because no `--i-understand` flag) |
| J4 | `execute-guarded` (with all 3 gates) | **1** | **PASS** | stderr: `EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE`; send_attempted=False; tx_signed=False; tx_broadcasted=False |
| J5 | `implementation-self-check` | 0 | **PASS** | no_tx_sent=True; no_signature_created=True; no_signer_constructed=True; no_*_executed=True; execute_guarded_correctly_disabled=True |

## ⚠️ 重要发现

**即使** `execute-guarded` 模式被调用 + 3 个 gate 全过 + 2 个 safety default 全 hold (`--dry-run-only=True, --no-send=True`) + 第二道 flag `--i-understand-this-sends-real-transactions` 已设：

- 脚本**仍 abort 1**
- stderr: `EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE`
- **不发送任何 tx**（send_attempted=False, tx_signed=False, tx_broadcasted=False）

**这是本 stage 的硬性设计**：send 在 implementation build stage **永远被阻止**；只有未来 `LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1` 之后的下下阶段才允许 send。

## 关键观察

### 动态 tick range
- **J1** drift_ticks=-281（与 frozen -200443 偏差 281 ticks，超 200 阈值）
- **J2** 用 dynamic range `[-200924, -200524]`（**不是** legacy `[-200643, -200243]`）
- 这证明 v2 在 runtime 重新计算 tick range；**没有**用 frozen

### Deadline 实时生成
- **J2** `mint.deadline_iso = "2026-06-02T17:58:58Z"`（now+3600）
- **不是** legacy 2099-01-01 placeholder 4070908800

### Approval gate
- **J3** valid=True（regex 匹配 + cross-check 通过）但 executes_now=False
- **关键**：成功 parse 不授权执行

### Safety flags 全部 intact
- `no_tx_sent`, `no_signature_created`, `no_signer_constructed`, `no_wallet_client_created` 全部 True
- `execute_guarded_correctly_disabled` True

## 安全

```text
wallet_or_tx_touched   = false
can_run_probe_now      = false
tiny_canary_allowed    = no
executor_will_run_this_round = false
send_attempted         = false (in this self-check)
tx_signed              = false
tx_broadcasted         = false
```
