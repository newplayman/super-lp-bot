把 paper runner 的六个真实仓位按真实资金与 1220.40 小时持有期重放到经 J3 校正的 NetCover 后，WETH-CBBTC=0.610635、WETH-USDC(Aerodrome)=8.249658、WETH-USDC(Uniswap)=1.567880、WETH-BRETT=1.317242、USDC-SAPIEN=0.698287、VIRTUAL-USDC=0.062508，其中 3 个 >=1.0。
两个仪器逐项分歧的最大绝对额是 Aerodrome WETH-USDC 的 `reward_haircut_deduction_usd` $137.3132：paper runner 将奖励按面值全额记入而 NetCover 保留 protocol 奖励 50% haircut；更重要的是 runner 对 gas、进/出场换腿、滑点、奖励换汇、LVR 与延迟损失均为 `UNMODELED`，故不是 NetCover 经 J3 校正后仍“高估成本”，而是 paper PnL 不能代表小仓全成本可执行结果。
因此 M1 的 $100、单仓 $50–60 不能被这六池整体证明为经济成立：在该真实 1220.40h 结果下仅 3/6 在 $50/$60 已过闸，另外 3 池的观测每美元变量风险已超过调整后收入、无任何有限仓位可达 1.0；对可行的三池按现有成本结构反解，最小单仓分别为 $0.27、$2.19、$3.71，但这只是固定该次观察期的规模诊断，不是放宽 M1 的授权。

# TP-J-v1 验收记录

## 范围与红线

- 基线：`f4e550c`；本包提交依次为 `9d9f434`（J1）、`c9419d5`（J2）、`c614893`（J3）与本提交（J4）。仅 commit，未 push。
- 未改动六个受保护经济常量：`STABLE_MIN_FRAC`、`NETCOVER_SHADOW`、`NETCOVER_TINY_LIVE`、`POSITION_TVL_SHARE`、`HARD_POSITION_TVL_SHARE`、`LVR_COEFFICIENT_MODEL`；特别是 `NETCOVER_SHADOW` 始终为 1.0。
- 未重启、修改、kill 或以任何方式控制 PID 1349731 / 2077656 / 2082408 / 3783076；J1 只读 runner 的 `book_init.json`、`portfolio_state_hourly.csv` 与 `heartbeat.jsonl`。
- 无真实签名、广播、私钥生成或付费服务调用。J1/J3 使用的是已保存的 scanner SQLite 快照；J3 的固定快照通过 SQLite backup API 制作并只读重放。

## J1：双仪器对账

`reports/lp_tp_j/20260814_j1/J1_RECONCILIATION.{json,md}` 保存了六行逐项对照：每个收益/成本项都有 paper 值、NetCover 值、差异绝对额及倍数，并按绝对差异降序。paper runner 没有输出相应成本的地方均明确标为 `UNMODELED`，绝未替换为 0。

J1 的完整成本基线（旧的全额每腿）为 0.581473 / 8.066278 / 1.340943 / 1.267564 / 0.657604 / 0.060263；该基线保留不改写，以使 J3 的正确性修复可逐项复核。

## J2：分析性阳性/阴性控制

`tests/test_lp_netcover_positive_controls_v1_readonly.py` 用完整 scanner-shaped record 驱动真实 `apply_netcover_gate`，没有 mock 被测逻辑：

- 强阳性：收入 $100、总成本 $10，断言 NetCover=10 且通过。
- 临界：收入=成本=$10，断言 NetCover=1 且结果与 `NETCOVER_SHADOW` 比较器一致。
- 强阴性：手续费为 0，断言 NetCover=0 且拒绝。
- 5/50/500/5000U × 168/720/2160h 网格：对仓位和时长都单调不降，且 5000U/5U 比值落在固定成本解析式的严格容差内。

## J3：真实 CLMM 换腿口径

修复不改变阈值，而是把每一腿的名义从“全仓”改为 V3 真实库存价值份额：`xP/(xP+y)`。`scripts/lp_swap_cost_model_v1_readonly.py` 的 `clmm_token0_value_fraction` 按价格与区间计算该份额；20% 对称区间的解析值约 0.4521，不是拍脑袋写 0.5。没有 range 的旧历史敏感性产物仍以全仓处理，但明确标记为保守上界。

前后六池与 Base 固定快照的逐项审计见：

- `reports/lp_tp_j/20260814_j3/J3_LEG_COST_AUDIT.md`
- `reports/lp_tp_j/20260814_j3/J3_RECONCILIATION_CORRECTED.{json,md}`
- `reports/lp_tp_j/20260814_j3/BASE_INVARIANCE_COMPARISON.json`

同一 6,812 行 Base SQLite backup 的旧/新重放：NetCover pass 从 51 到 61（10 行因正确成本而跨过 1.0），PositionCap 3107 pass / 3705 fail 完全不变；3,245 行只有 entry/exit/slippage 数值按库存份额变化，逐行差异已保存。旧代码为 `c9419d5`，新代码为 J3 工作树；历史行只在内存中套用生产入口已有的 Base CLMM 协议映射，未写回 DB。

## J4：尺度反解

`reports/lp_tp_j/20260814_j4/J4_CAPITAL_BACKSOLVE.{json,md}` 固定真实观察期、每美元 fee/reward/IL 与 J3 成本，给出 $50/$60 下的值以及每池至 1.0 的二分反解。三个无有限解的池不是固定 gas 造成，而是变量风险项本身已经大于调整后收入，所以扩大资金不会解决。

## 最终回归

本文件最后一次编辑后，执行 `python3 -m pytest tests/ -q` 与 `go test ./...`；原始终端输出随本次交付一并报告。
