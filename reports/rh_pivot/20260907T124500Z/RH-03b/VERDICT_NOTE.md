# RH-03b 主脑裁决：第一轮 REJECT，第二轮 ACCEPT

## 第一轮退回（2026-09-08 06:45）

十项合取式本身正确，退回只针对 `primary_status`：政策阻挡与缺生产者的记录仍报 `COMPUTED_PASS`。`dominant_blocker` 对了而 `primary_status` 错了，是更危险的一半——只读 status 的消费者会被误导成"算过且通过"。

## 第二轮验收（主脑独立复现，不依赖 worker 自报）

十项逐一置 False，`primary_status` 无一为 `COMPUTED_PASS`：

| 置 False 的闸 | terminal_eligible | primary_status |
|---|---|---|
| `capital_policy_pass` | False | **POLICY_BLOCKED** |
| `protocol_capabilities_sufficient` | False | **UNSUPPORTED** |
| 其余八项 | False | COMPUTED_FAIL |

| 用例 | 结果 |
|---|---|
| 全十项 True | `eligible=True`、`COMPUTED_PASS`、`simulated_policy_only=False` |
| **T59** 缺 `legacy_required_conjunction` | `INPUTS_UNAVAILABLE` + `reasons=['LEGACY_CONJUNCTION_NO_PRODUCER']`，**不是**经济证伪 |
| **T25** `LIVE_READINESS` + 政策冲突 | `POLICY_BLOCKED`，`simulated_policy_only=False` |
| **T25** 同记录 `SHADOW_SCENARIO` | `eligible=True` 但 `simulated_policy_only=True`（PRD §6.1：情景模拟通过不得写成生产终闸通过） |
| 非法 target_mode | `ValueError: UNKNOWN_TARGET_MODE` |

测试 42 个全绿（10 个函数参数化展开），`all([` 零命中，AST 形状测试锁死十项合取——增删任一项都会失败，强制显式更新不变量。

**裁决：ACCEPT。**
