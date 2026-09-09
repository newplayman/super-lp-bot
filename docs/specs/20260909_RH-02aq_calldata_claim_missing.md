# RH-02aq：calldata 意图校验把「缺失的 claim」当成「不冲突」

## 铁证（来自 reports/AUDIT_silent_failure_hunt_20260909.md 第 1 条）

`scripts/lp_rh_calldata_decoder_v1_readonly.py:242-251`：
校验只对**存在于 `decoded` 里的字段**做 `if x in claims` 比对，
`decoded` 缺失的字段直接跳过，等于**未校验但判定为通过**。

复现：`decode_calldata("0x42966c68" + "00"*32)` 配一个完整 `intent`
→ 返回 `(True, [])`，而实际上 **11 个意图字段一个都没被验证**。

这是「拼错的键与真缺数据不可区分」（本项目已确认的第 7 种模式）在
**交易意图校验**上的实例——它的职责恰恰是「广播前确认这笔 calldata
干的就是我们想干的事」。缺一个 claim 就等于那一维没有被检查。

## 你要做的

1. 先读该文件搞清楚 `decoded` / `claims` / `intent` 三者的结构与来源
   （`sed -n '200,277p'`，不要整读）。
2. 改成：**intent 里声明的每一个字段，都必须在 decoded 里有对应的 claim**。
   任一缺失 → 返回不通过，理由用该模块既有风格，点名
   `INTENT_CLAIM_MISSING: <字段名>`（多个就都列出来）。
3. 已有的「值不一致」判定保持原样，不要改它的语义。
4. 审计报告还建议「同时校验原始 calldata hash」——
   **这条不做**（超出本包范围，需要先确定 hash 的来源与存放位置，
   由主脑另行决定）。只做 claim 完整性。

## 不许动

`scripts/lp_rh_shadow_runner_v1_readonly.py`、
`scripts/lp_rh_readiness_v1_readonly.py`、`scripts/lp_rh_gas_reserve_v1_readonly.py`
（都刚被改过或正在被改）、任何 recorder / daemon、任何 `.db`。
`tests/test_lp_rh_calldata_decoder_v1_readonly.py` **只允许新增测试**。

## 验收标准

1. 复现输入 `decode_calldata("0x42966c68" + "00"*32)` + 完整 intent
   → **不再返回 `(True, [])`**，理由里点名缺失的字段。
2. **防回归**：decoded 与 intent 完全匹配的正常用例，
   行为与修改前完全一致（返回通过）。这条必须有。
3. decoded 有字段但值不一致 → 仍报原有的不一致错误（原行为不回退）。
4. intent 声明了 N 个字段、decoded 只有 N-1 个 → 报缺失，且点名的是**那一个**。
5. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_calldata_decoder_v1_readonly.py -q -p no:cacheprovider`
   全绿，原有测试全部仍在。

## 交付格式（只读沙箱，写不了文件）

```
===FILE:scripts/lp_rh_calldata_decoder_v1_readonly.py===
===FILE:tests/test_lp_rh_calldata_decoder_v1_readonly.py===
===END===
```

标记独占一行、一字不差，文件内容不要用 markdown 代码围栏包裹。
动笔前先跑一遍复现输入确认缺陷存在，并把实际返回值写进说明。
