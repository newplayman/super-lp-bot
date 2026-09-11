GOAL:
把 `rh_position_marks.unvalued_risk_json` 里三个新增数值字段从 `float` 改成高精度字符串，消除审计证据与权威数字之间的舍入差。**这是个小包，只改一处构造与对应断言。**

## 背景

commit `b0e6682`（RH-02cn）在 `scripts/lp_rh_shadow_runner_v1_readonly.py` 的 `risk_data` 里加了三个字段：

```python
"fee_usd_raw": float(fee_usd_raw) if fee_usd_raw is not None else None,
"fee_usd_organic": float(fee_usd_organic) if fee_usd_organic is not None else None,
"organic_fraction": float(organic_fraction) if organic_fraction is not None else None,
```

三个值在内存里都是 `Decimal`，被 `float()` 截断成双精度。同一行的权威数字 `accrued_fee` 却是以 `Decimal` 存进 TEXT 列的。将来的对账（`rh_reconciliation_runs`）拿这两边比对时，这点舍入会表现为「未解释的账本差异」——而 PRD §21.2 要求它必须为 0。

实测 `organic_fraction` 的真实精度是 60 位：
`0.896235011087114303570052104776515058408741194678517500624466`
`float()` 之后只剩 17 位有效数字。

## 要做的事

1. 在 `scripts/lp_rh_shadow_runner_v1_readonly.py` 里，把这三个字段改成 `str(...)`（保留 `None` 仍为 `None`，不要变成字符串 `"None"`）。
   - 如果仓库里已有现成的 Decimal→TEXT 辅助函数（找一下 `_economic_str` 之类），**优先复用它**，与既有惯例一致。
2. 同步更新 `tests/test_lp_rh_shadow_runner_v1_readonly.py` 里所有断言这三个字段的地方。
   - 断言要比较 `Decimal(值)` 而不是字符串字面量，**不要把今天恰好算出来的那一长串数字钉进断言**——本项目已出现四次「把当前数据状态写进断言」的缺陷。
   - 例：`assert Decimal(risk["fee_usd_organic"]) == Decimal(risk["fee_usd_raw"]) * Decimal("0.9")`

## 不许动

- 只改上面两个文件。不要碰 daemon、不要碰别的测试文件。
- 不要改 `fee_usd_raw` 的算法、`compute_nav`、`hodl_benchmark`、`net_pnl`、NetCover。
- 不要写 `reports/lp_rh/` 下的任何数据库。
- **不要执行任何 git 命令。**
- **不要 kill 或重启任何进程**（PID 2271374 采集器、2571485 shadow daemon 在跑生产）。
- 单次 Write/Edit ≤150 行或 6000 字符。

## ENVIRONMENT（照做，别自己找解释器）
- 直接用 `python3`（3.12.3 + pytest 7.4.4 + pycryptodome，就是本仓库钉死的版本）。
- **不要找 venv**，`/root/lp-bot/.venv` 你没权限。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`（12 万文件）。不要整读 >300 行的文件，用 `grep -n` 与 `sed -n 'A,Bp'` 定位。

## VALIDATION
1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q`（全绿，应为 107 passed）
2. `grep -n "float(fee_usd\|float(organic_fraction" scripts/lp_rh_shadow_runner_v1_readonly.py` —— **应无输出**
3. **不要跑全量测试**（`pytest tests/ -q`）。另一个 worker 正在并行跑它，会撞车。主脑会统一跑。

最后按以下字段报告：TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
