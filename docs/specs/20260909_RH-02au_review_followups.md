# RH-02au：今晚三个修复的审查跟进（一真回归 + 两处收尾）

独立审查（`reports/REVIEW_tonight_fixes_20260909.md`）对今晚 8 个修复给出
5 个 ACCEPT、3 个「需修补」。主脑已逐条复现，**判定与审查略有出入，以下为准**。

## 一、真回归（必须修）：gas 闸门校验了它自己声明不关心的输入

`scripts/lp_rh_gas_reserve_v1_readonly.py` 的 `wrapped_does_not_count`，
其**全部语义就是「WETH 余额不计入 gas 储备」**。RH-02an 给它加了输入校验后：

```
wrapped_does_not_count(weth_balance_wei=None, native_balance_wei=0)
  修复前  {'native_usable': True, 'wrapped_usable': False, 'note': 'WETH is an E...'}
  修复后  {'pass': False, 'native_usable': False, 'wrapped_usable': False, ...}
```

**一个声明「我不看这个值」的函数，因为这个值缺失而失败了。** 这是回归。
（合法整数输入下新旧一致，所以主脑的差分测试没抓到——审查抓到了。）

修法：`wrapped_does_not_count` **只校验 `native_balance_wei`**。
`weth_balance_wei` 缺失、为 None、甚至非有限，都不应影响这个函数的结论——
它本来就要把 WETH 判为不可用。

## 二、同一函数的返回结构不稳定

失败时新增了 `pass` / `reason` 两个键，正常返回却没有这两个键，
调用方 `result.get("pass")` 在正常路径上拿到 `None`。

修法：统一 schema。要么两种路径都带 `pass`，要么失败路径也不带、
改用既有的 `native_usable` / `wrapped_usable` 表达。**选一个并保持一致**，
在 docstring 里写明返回哪些键。

## 三、`external_net_flow=None` 抛 TypeError（既有缺陷，不是本轮引入）

主脑实测：**修复前后都抛** `TypeError: conversion from NoneType to Decimal`。
所以这不是 RH-02ap 的回归，是原本就在的问题——但 JSON 里 `null` 极常见
（`{"external_net_flow": null}` 是完全正常的序列化结果），值得一并修。

修法：`scripts/lp_rh_pnl_v1_readonly.py` 里把「键不存在」与「值为 None」
**统一视为不可用**，走 RH-02ap 已经建立的 `net_pnl=None` + `net_pnl_reason` 路径。
`fee_income` / `gas_paid` / `price_move_effect` 的 None 同样按缺失处理
（标记归因不可对账，不影响总额）。

## 四、`live_allowed` 畸形值时授权提示为空（小瑕疵，不是回归）

`scripts/lp_rh_readiness_v1_readonly.py` 的 `graduation_verdict`：
`live_gate={"blockers": [], "live_allowed": "yes"}` 时
**旧版返回 PASS**（更危险），新版返回 FAIL（正确），
但 `explicitly_not_authorized` 是空列表，读报告的人看不出为什么 FAIL。

修法：判定与提示用同一个条件——`live_gate.get("live_allowed") is not True`
时既 FAIL 也填充 `explicitly_not_authorized`，或先校验该字段必须是 bool
并在提示里点名「live_allowed 不是布尔」。

## 不许动

`scripts/lp_rh_shadow_runner_v1_readonly.py`（另有线在改）、
`scripts/lp_rh_coverage_audit_v1_readonly.py`（另有线在改）、任何 `.db`。
三个测试文件**只允许新增测试**。

## 验收标准

1. `wrapped_does_not_count(weth_balance_wei=None, native_balance_wei=0)`
   返回值与**修复前的 HEAD~ 版本完全一致**（可用 `git show 6399aa0~1:scripts/lp_rh_gas_reserve_v1_readonly.py` 对照）。
2. `wrapped_does_not_count` 正常输入的返回值也与修复前一致。
3. `native_reserve_gate` 的 Infinity / NaN / 负数拦截**不得回退**（RH-02an 的核心成果）。
4. `external_net_flow=None` → `net_pnl is None` + 有 reason，**不抛异常**。
5. `external_net_flow="0"` 与省略键的行为均不变（RH-02ap 的成果不得回退）。
6. `graduation_verdict` 遇 `live_allowed="yes"` → FAIL **且** `explicitly_not_authorized` 非空。
7. `graduation_verdict` 遇 `live_allowed=True` 且无 blocker → 仍 PASS（防回归）。
8. 三个模块的既有测试全绿：
   `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_gas_reserve_v1_readonly.py tests/test_lp_rh_pnl_v1_readonly.py tests/test_lp_rh_readiness_v1_readonly.py -q -p no:cacheprovider`

## 纪律

- 不要执行任何 git 写命令（`git show` 只读可用）。
- 不要重启 daemon，不要动 crontab。
