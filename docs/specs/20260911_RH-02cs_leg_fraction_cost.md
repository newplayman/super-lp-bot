GOAL:
修复 RH 成本模型的一条 PRD 验收 FAIL：换腿成本按 100% 仓位收取，未按实际换腿比例折算。

## 已确认的事实（直接用，不用重查）

PRD §19 RH-03 的验收原文写着「**成本按实际换腿**」。当前实现不满足：

```
scripts/lp_rh_netcover_inputs_v1_readonly.py:23
    from scripts.lp_swap_cost_model_v1_readonly import (
        clmm_token0_value_fraction, exit_conversion_cost_usd, roundtrip_cost_usd,)
    ← clmm_token0_value_fraction 被 import 了，但全文再无第二次出现，从未调用

scripts/lp_rh_netcover_inputs_v1_readonly.py:122-123
    entry_cost_usd = exit_conversion_cost_usd(pos, liquidity_raw, price, fee_tier, d0, d1, side="buy_base")
    exit_cost_usd  = exit_conversion_cost_usd(pos, liquidity_raw, price, fee_tier, d0, d1, side="sell_base")
    ← 两次都把 100% 仓位金额 pos 传进去
```

**旧链的同名代码是对的**，移植到 RH 时丢了这个区分，可以照抄它的写法：
- `scripts/lp_netcover_inputs_v1_readonly.py:694` 调用了 `clmm_token0_value_fraction(float(state[0]), range_pct)`
- `scripts/lp_netcover_calibration_v1_readonly.py:132` 有显式开关：
  `fraction = 1.0 if legacy_full_position_legs else clmm_token0_value_fraction(...)`

实测影响：entry+exit 换腿成本当前 0.203733 USD，占正成本合计 3.447806 的 **5.9%**。

## ★本包的特殊风险：它把闸门往「更容易通过」的方向推★

修完之后成本变小、NetCover 变大、更多候选会通过终闸。
PRD §0.2 明令「**不通过放宽阈值制造候选**」。所以这个包的测试标准比平时更高：

**算不出换腿比例时，必须回退到 1.0（即按 100% 收全额成本），这是保守侧。**
绝不能回退到某个猜测值、也不能跳过成本。
——注意这与 organic 折减那个包的 fail-close 方向一致：**都是往保守的一侧倒**。
organic 算不出就不折减（收入不虚高）；换腿比例算不出就按全额（成本不虚低）。

## 要做的事

只改 `scripts/lp_rh_netcover_inputs_v1_readonly.py` 与
`tests/test_lp_rh_netcover_inputs_v1_readonly.py`。

1. 在算 `entry_cost_usd` / `exit_cost_usd` 之前，用 `clmm_token0_value_fraction`
   算出该仓位实际需要换腿的比例。**先读 `scripts/lp_swap_cost_model_v1_readonly.py`
   里这个函数的签名与语义，以及 `lp_netcover_inputs_v1_readonly.py:690-700` 的用法**，
   照既有惯例调用，不要自己发明参数。
2. 把折算后的金额传给 `exit_conversion_cost_usd`，而不是 `pos`。
3. **fail-close**：比例算不出、为 None、或不在 (0, 1] 区间 → **用 1.0**（全额），
   并在返回的成本分项里加一个标记字段（例如 `leg_fraction_status`），
   取值 `"COMPUTED"` 或 `"FALLBACK_FULL_POSITION:<原因>"`。
   **标记与回退必须同时发生，只做一半等于没做。**
4. 把实际用到的比例也记进成本分项（例如 `leg_fraction`），便于审计修正幅度。
5. `roundtrip_cost_usd` 那一行（125 行附近）如果同样按 100% 传，一并按相同方式处理；
   如果它内部已经自己折算了，**不要重复折算**——先读它的实现确认，在报告里说明你的判断依据。

## 不许动

- 不要改 `scripts/lp_swap_cost_model_v1_readonly.py`（那是共享成本模型）。
- 不要改六个受保护常量、不要改 NetCover 的阈值、不要改 `il_ev` / `lvr_ev` / `gas` 等其他成本分项。
- 不要改旧链的 `lp_netcover_inputs_v1_readonly.py`（只读它抄写法）。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动它们会把 Stage A 的 72 小时判定窗口清零。
- 不要写 `reports/lp_rh/` 下的任何数据库；测试用 `tmp_path`。
- **不要执行任何 git 命令。不要 kill 或重启任何进程**（PID 2271374 采集器、2575799 shadow daemon 在跑生产）。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（≥6 条新增）

写完把被测代码临时改坏，确认测试真的变红，再改回来。本项目已九次出现
「测试构造的输入进不去被测代码」，典型原因是 fixture 键名与被测代码读的键名对不上。

1. 给定一个已知比例（例如 0.3）→ entry/exit 成本恰好是全额的 0.3 倍
2. 比例算不出（输入缺失）→ **回退 1.0**，成本与修改前完全一致，且 `leg_fraction_status`
   为 `FALLBACK_FULL_POSITION:*`（**不是静默回退**）
3. 比例为 None / 0 / 1.5 → 三种都回退 1.0 并标记（**注意 0 也要拒绝**：
   零换腿意味着零成本，那是结论不是输入）
4. 比例 = 1.0（真的需要全额换腿）→ 结果与修改前一致，`status` 为 `COMPUTED`
5. `leg_fraction` 与 `leg_fraction_status` 都出现在返回的成本分项里
6. 回归保护：NetCover 的其他成本分项（il_ev / lvr_ev / gas / exit_latency）**数值不变**

## ENVIRONMENT（照做，别自己找解释器）
- 直接用 `python3`（3.12.3 + pytest 7.4.4 + pycryptodome，本仓库钉死的版本）。
- **不要找 venv**（`/root/lp-bot/.venv` 无权限）。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`（12 万文件）。不要整读 >300 行的文件。
- 先读代码先改，**全量测试只在最后跑一次**。

## VALIDATION（命令与输出尾部原样贴进报告）
1. `python3 -m pytest tests/test_lp_rh_netcover_inputs_v1_readonly.py -q`（全绿，新增 ≥6 条）
2. `grep -n "clmm_token0_value_fraction" scripts/lp_rh_netcover_inputs_v1_readonly.py`（应有生产调用，不止 import 那一行）
3. `python3 -m pytest tests/ -q`（**最后才跑**；基线 4860 passed / 14 skipped / 0 failed）
4. 在报告里明确写出：修改前后 entry_cost_usd / exit_cost_usd 的数值对比，以及你对
   `roundtrip_cost_usd` 是否需要同样处理的判断与依据。

最后按以下字段报告：TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
