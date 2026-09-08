# RH-03c：gas 必须按链上状态估算，而不是任何固定常量（T34）

## 审计发现与实测

T34 取证：`gas_usd` 是 `evidence["gas_usd_estimate"]` 的**直通透传**
（`scripts/lp_rh_netcover_inputs_v1_readonly.py:128-133`），
没有 L1 data 费用项，没有重复计费检测，**也没有任何合理性校验**。

主脑实测发现自己手填的 `0.02` 低估真值约 **23 倍**（真值约 $0.4614），
并因此把资金政策结论算反了（见
`reports/rh_pivot/20260907T124500Z/CAPITAL_POLICY_CONFLICT_DECISION_CN.md` 的「重大更正」）。

**但实测的 0.4614 同样不该被写死**：Arbitrum 系 L2 的 gas 由 L1 data 费用主导，
随主网拥堵剧烈波动。

## 只新建两个文件（**一包一个实质文件**，看门狗不需要）

1. `scripts/lp_rh_gas_estimator_v1_readonly.py`（≤260 行）
   网络调用通过注入的 `call_fn` 完成，模块自身不联网。

   - `GAS_UNITS = {"v3_mint": 450000, "v3_burn_collect": 350000, "swap": 150000}`
     **注释里写明这是 Uniswap V3 的典型值，不是本链实测**，
     并说明它应当由后续包用真实 receipt 校准。
   - `estimate_gas_usd(*, gas_price_wei, native_price_usd, gas_units) -> Optional[Decimal]`
     `gas_units × gas_price_wei / 1e18 × native_price_usd`。
     任一入参为 `None` 或 `<= 0` → 返回 `None`（**不是 0**）。
   - `round_trip_gas_usd(*, gas_price_wei, native_price_usd) -> Optional[Decimal]`
     开仓 + 平仓（`v3_mint + v3_burn_collect`）。
   - `observed_gas_units(receipts) -> dict`
     从一批 receipt（`[{"gasUsed": int, "effectiveGasPrice": int}]`）算
     `{"n", "median_gas_used", "median_gas_price_wei", "p90_gas_used"}`。
     空输入 → 各项为 `None`（**不是 0**），`n` 为 0。
   - `gas_estimate_sanity(estimate_usd, observed_usd, *, max_ratio=Decimal("3")) -> dict`
     比较外部给的估计与实测：返回
     `{"ratio": Decimal|None, "verdict": "OK"|"UNDERSTATED"|"OVERSTATED"|"UNKNOWN"}`。
     `estimate < observed / max_ratio` → `UNDERSTATED`；
     `estimate > observed × max_ratio` → `OVERSTATED`；任一为 `None` → `UNKNOWN`。
     **这正是能抓住我这次 23 倍低估的那道闸。**
   - `main()`：`--receipts-json --gas-price-wei --native-price-usd --out`，纯离线。

2. `tests/test_lp_rh_gas_estimator_v1_readonly.py`（≤240 行，**≥14 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。**不许联网。** 必测：
   - `estimate_gas_usd` 用实测值复算：`gas_units=800000`、
     `gas_price_wei=232188000`、`native_price_usd=2484` → 约 `0.4614`
     （断言落在 0.46–0.47 之间）。**这条锚定实测。**
   - 任一入参 `None` → `None`（三条，各 `is None` 断言）。
   - `gas_price_wei=0` → `None`（不是 0）。
   - `observed_gas_units` 空输入 → `n==0` 且中位数 `is None`。
   - `observed_gas_units` 对 `[100,200,300]` 的中位是 200。
   - **`gas_estimate_sanity(0.02, 0.4614)` → `UNDERSTATED`**，`ratio` 约 0.043。
     **这条直接复现主脑这次的错误。**
   - `gas_estimate_sanity(0.4614, 0.4614)` → `OK`，`ratio` 约 1。
   - `gas_estimate_sanity(2.0, 0.4614)` → `OVERSTATED`。
   - 任一为 `None` → `UNKNOWN` 且 `ratio is None`。
   - 边界：`ratio` 恰为 `1/max_ratio` 与 `max_ratio` 时的归属各断言一次。
   - `GAS_UNITS` 三个键存在且均 > 0。
   - 所有金额是 `Decimal`，不是 float。

## 不许动
不改 `lp_rh_netcover_inputs_v1_readonly.py`（接入闸门是下一包的事，
要先让用户看到 sanity 检查的实测结果再决定是否强制）。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_gas_estimator_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
