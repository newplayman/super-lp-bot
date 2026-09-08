# RH-05c：V3 退出深度计算器（tick 数学，离线可测）

## 背景

PRD v1.1 §11.3 与用例 **T24** 要求：**参考价可读但无足额退出报价时必须判 `INPUTS_UNAVAILABLE: EXIT_QUOTE`，不是无风险折价**。§6.4 的 `q_max` 含一项 `measured_exit_depth_cap`。§15.3 要求退出 SLA 可测。当前所有 RH 模块**都没有退出深度计算**，这是终闸 `position_and_exit_depth_pass` 恒为 False 的根因，也是 RH-05 最后一个证据缺口。

主脑已实测目标池（`0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`）：token0=WETH(18)、token1=USDG(6)、fee=100、tickSpacing=1、`sqrtPriceX96=3953938817749275760872870`、`tick=-198118`、`liquidity=10661985504065420007`、池内 5,910.53 WETH + 17,166,110.29 USDG。四个 ETF 池亦已 ATTESTED（见 `reports/rh_pivot/20260907T124500Z/RH-05-research/POOL_ATTESTATION_AND_FEES_20260908.md`）。

**注意**：`liquidity()` 只给**当前 tick 的活跃流动性**，不是全池。跨 tick 需要 `ticks(tick)` 的 `liquidityNet`。真实退出必须考虑跨 tick 后流动性变化，**不得假设恒定流动性**（那会系统性高估可退出深度）。

## 新增文件

1. `scripts/lp_rh_exit_depth_v1_readonly.py`（**≤ 300 行**）
   - 顶部仓库通行 sys.path 引导。**所有价格与金额用 `Decimal` 或整数，禁止 float 参与金额计算**（tick 数学中间量可用整数）。
   - **V3 数学（精确整数实现，不要近似）**：
     - `sqrt_price_x96_at_tick(tick: int) -> int`：`1.0001**(tick/2) * 2**96`，用整数幂或 `Decimal` 高精度实现，误差 < 1e-12 相对。
     - `tick_at_sqrt_price_x96(sqrt_price_x96: int) -> int`：反函数，向下取整。
     - `amount0_delta(sqrt_a: int, sqrt_b: int, liquidity: int, round_up: bool) -> int` 与 `amount1_delta(...)`：Uniswap V3 标准公式
       ```
       amount0 = L * (sqrt_b - sqrt_a) * 2**96 / (sqrt_a * sqrt_b)
       amount1 = L * (sqrt_b - sqrt_a) / 2**96
       ```
       （`sqrt_a <= sqrt_b`，`round_up` 控制取整方向。）
   - `dataclass TickRange`：`tick_lower, tick_upper, liquidity_net`。
   - `simulate_exit_swap(*, sqrt_price_x96, current_tick, tick_spacing, fee_pips, liquidity, tick_data: Sequence[TickRange], amount_in: int, zero_for_one: bool) -> dict`：
     沿价格方向逐 tick 推进，每段用当前 `liquidity` 计算可消耗量，跨过 tick 时按 `liquidity_net` 更新流动性（`zero_for_one` 时减、反向时加）。返回
     `{"amount_out": int, "sqrt_price_after": int, "tick_after": int, "ticks_crossed": int, "liquidity_exhausted": bool, "effective_price": Decimal, "price_impact_bps": Decimal, "fee_paid": int}`。
     **`tick_data` 不足以覆盖所需范围时 `liquidity_exhausted=True`，且 `amount_out` 只反映已覆盖部分**——调用方必须视为深度不足，不得当作可全额退出。
   - `exit_depth_for_size(*, position_value_usd: Decimal, max_impact_bps: Decimal, **pool_state) -> dict`：二分搜索在给定滑点上限内可退出的最大规模。返回 `{"max_exit_usd": Decimal|None, "impact_at_size_bps": Decimal|None, "sufficient": bool, "reason": str}`。
     - `tick_data` 为空或不足 → `{"max_exit_usd": None, "sufficient": False, "reason": "INPUTS_UNAVAILABLE: EXIT_QUOTE"}`（**T24：绝不返回 0 或乐观估计**）。
     - 可退出规模 < `position_value_usd` → `sufficient=False`，`reason="EXIT_DEPTH_INSUFFICIENT"`。
   - `measured_exit_depth_cap(...) -> Decimal|None`：供 PRD §6.4 的 `q_max` 使用；无数据返回 `None`（不是 0，也不是无穷）。
   - **不联网**。池状态与 tick 数据由调用方注入（主脑会用真实 RPC 抓取后喂进来）。
   - `main()`：`--pool-state-json <file> --position-usd <x> --max-impact-bps <y> --out <file>`。
2. `tests/test_lp_rh_exit_depth_v1_readonly.py`（≤ 300 行），至少 18 个测试，全部离线：
   - **数学正确性**：`sqrt_price_x96_at_tick(0) == 2**96`；`tick_at_sqrt_price_x96(sqrt_price_x96_at_tick(t)) == t` 对 t ∈ {-887272, -198118, -1, 0, 1, 100000, 887272} 全部成立（往返一致）。
   - 用主脑实测值验证：`tick_at_sqrt_price_x96(3953938817749275760872870) == -198118`。
   - `amount0_delta` / `amount1_delta` 的对称性与单调性：liquidity 加倍 → 金额加倍；区间加宽 → 金额单调增。
   - **单 tick 内 swap**：给足够 liquidity 且 amount_in 很小 → `ticks_crossed == 0`，`price_impact_bps` 很小（< 10）。
   - **跨 tick swap**：构造 3 段 tick_data，amount_in 足够大 → `ticks_crossed >= 1`，且流动性按 `liquidity_net` 正确增减（断言 `sqrt_price_after` 落在预期区间）。
   - **深度耗尽**：tick_data 只覆盖一小段，amount_in 超出 → `liquidity_exhausted is True`。
   - **T24 核心**：`tick_data=[]` → `exit_depth_for_size` 返回 `sufficient=False` 且 `reason == "INPUTS_UNAVAILABLE: EXIT_QUOTE"`，**`max_exit_usd is None`**（断言它不是 0）。
   - 可退出规模不足 → `reason == "EXIT_DEPTH_INSUFFICIENT"`，`sufficient is False`。
   - `measured_exit_depth_cap` 无数据 → `None`（断言 `is None`，不是 0、不是 inf）。
   - **滑点上限生效**：`max_impact_bps=10` 得到的 `max_exit_usd` 严格小于 `max_impact_bps=100` 的结果。
   - **方向性**：`zero_for_one=True` 与 `False` 在同一池状态下给出不同的 `sqrt_price_after` 方向（一个降一个升）。
   - **恒定流动性假设是错的**：构造一个「跨 tick 后流动性骤降」的 tick_data，断言本实现算出的 `amount_out` **严格小于**「假设流动性恒定」的朴素算法结果，并在测试里写明这正是防止高估退出深度的关键。
   - 源码断言：无 `float(` 参与金额；无联网 import。

## 不许动什么

- 不改任何现有脚本/测试/配置；不许碰 `scripts/lp_rh_collector_v1_readonly.py`（生产运行中）。
- 不联网、不写活库、不读 `.env*`。
- 不实现策略、不实现终闸接线（后续包）。
- 单次 Write/Edit ≤150 行；不整读 >300 行文件。

## 验收标准

- [ ] `git status --short` 新增只有 1 脚本 + 1 测试；`git diff --stat` 为空。
- [ ] 新测试 ≥18 个且全绿；全量 `pytest tests/ -q -p no:cacheprovider` 0 failed、14 skipped。
- [ ] tick 往返一致性测试通过；实测值 `-198118` 能被还原。
- [ ] `tick_data=[]` 时返回 `INPUTS_UNAVAILABLE: EXIT_QUOTE` 且 `max_exit_usd is None`（不是 0）。
- [ ] 「跨 tick 流动性骤降」测试证明本实现不高估深度。

## 验证命令

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_exit_depth_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
git diff --stat; git status --short | grep -E 'lp_rh_exit_depth'
```
