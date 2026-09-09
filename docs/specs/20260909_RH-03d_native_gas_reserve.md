# RH-03d：native ETH 退出储备闸（T29）——防止仓位关不掉

## 审计发现

T29 取证结论（`AUDIT_EVIDENCE_T21_T40.json`）：

> grep for gas_reserve / native reserve across `scripts/lp_rh_*.py` and
> `scripts/lp_netcover_engine_v1_readonly.py` found **no gate comparing a native
> ETH balance against a gas reserve requirement**。

用例场景是「有很多 WETH 但 native ETH 不足」，期望「native gas reserve 闸失败」。

**为什么这条最危险**：WETH 是 ERC-20，付不了 gas。若开仓时把 ETH 全换成了 WETH 与
USDG 投进池子，平仓所需的 gas 就没钱付——**仓位关不掉，只能眼看它漂移**。
这是本轮审计四个缺口里唯一会造成「资金被困」的。

刚落地的 `scripts/lp_rh_gas_estimator_v1_readonly.py` 提供了真实成本估算
（实测开仓+平仓约 $0.45），本包用它算储备要求，**不要再引入任何写死的常量**。

## 只写两个文件（一包一个实质文件 + 其测试）

1. `scripts/lp_rh_gas_reserve_v1_readonly.py`（≤240 行）
   复用 `scripts.lp_rh_gas_estimator_v1_readonly` 的
   `round_trip_gas_usd` / `estimate_gas_usd` / `GAS_UNITS`，**不要重写**。

   - `RESERVE_MULTIPLIER = Decimal("3")`
     储备要求 = 一次平仓 gas × 该倍数。**注释写明理由**：平仓可能因滑点保护失败需重试，
     且 gas price 会波动；3 倍是保守起点，**不是实测校准值**。
   - `exit_gas_requirement_usd(*, gas_price_wei, native_price_usd,
     multiplier=RESERVE_MULTIPLIER) -> Optional[Decimal]`
     只算**平仓**（`GAS_UNITS["v3_burn_collect"]`），不含开仓——开仓时钱还在手上。
     任一入参缺失 → `None`（**不是 0**）。
  - `native_reserve_gate(*, native_balance_wei, gas_price_wei, native_price_usd,
     multiplier=RESERVE_MULTIPLIER) -> dict`
     返回 `{"pass": bool, "required_usd": Decimal|None, "available_usd": Decimal|None,
     "shortfall_usd": Decimal|None, "reason": str}`。
     - `native_balance_wei` 为 `None` → `pass=False`，`reason="NATIVE_BALANCE_UNKNOWN"`，
       三个金额均 `None`。**余额未知必须判失败，不得当作充足。**
     - 任一 gas 入参缺失 → `pass=False`，`reason="GAS_ESTIMATE_UNAVAILABLE"`。
     - 余额 < 要求 → `pass=False`，`reason="NATIVE_GAS_RESERVE_INSUFFICIENT"`，
       `shortfall_usd` 为差额（正数）。
     - 充足 → `pass=True`，`reason="OK"`，`shortfall_usd` 为 `Decimal(0)`。
   - `wrapped_does_not_count(*, weth_balance_wei, native_balance_wei) -> dict`
     显式表达「WETH 不能付 gas」：返回
     `{"native_usable": True, "wrapped_usable": False, "note": "..."}`，
     并在 docstring 里写明这是 T29 的核心语义。
     **该函数不得把 WETH 计入任何可用余额。**
   - `main()`：`--native-balance-wei --gas-price-wei --native-price-usd --out`，纯离线。

2. `tests/test_lp_rh_gas_reserve_v1_readonly.py`（≤220 行，**≥14 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。**不许联网。** 必测：
   - **复现 T29 场景**：`weth_balance_wei` 极大（如 10 ETH 等值）而
     `native_balance_wei=0` → 闸 `pass is False`，`reason` 为
     `NATIVE_GAS_RESERVE_INSUFFICIENT`。**这条是本包核心。**
   - 同场景断言 `wrapped_does_not_count(...)["wrapped_usable"] is False`。
   - `native_balance_wei=None` → `pass is False` 且 `reason=="NATIVE_BALANCE_UNKNOWN"`，
     `required_usd is None`（**`is None` 断言，不是 0**）。
   - `gas_price_wei=None` → `reason=="GAS_ESTIMATE_UNAVAILABLE"`，`pass is False`。
   - 用实测值算要求：`gas_price_wei=228372000`、`native_price_usd=2484` →
     `exit_gas_requirement_usd` 约 `0.2019 × 3 = 0.6057`（断言落在 0.59–0.62）。
     **这条锚定实测 gas。**
   - 余额恰好等于要求 → `pass is True`，`shortfall_usd == Decimal(0)`（边界闭区间）。
   - 余额比要求少 1 wei → `pass is False` 且 `shortfall_usd > 0`。
   - `multiplier` 可覆盖：传 `Decimal("1")` 时要求正好是单次平仓成本。
   - 所有金额是 `Decimal` 不是 float。
   - `RESERVE_MULTIPLIER` 值为 3（防止被静默改动的回归断言）。
   - 充足场景 `shortfall_usd == Decimal(0)` 而非 `None`（0 与未知要分开）。

## 不许动
**不要把本闸接进 `lp_rh_terminal_gate` 或 netcover**——接入是下一包，
要先让用户看到它在实盘余额上的判定结果。不改其他脚本。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_gas_reserve_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
