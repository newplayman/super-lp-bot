# 退出深度计算器首次跑真实数据（2026-09-08 11:2x UTC，主脑亲跑）

输入：`POOL_TICK_STATE_LIVE.json`（区块 57,557,353，661 个已初始化 tick，385 个负 `liquidityNet`）。计算器：`scripts/lp_rh_exit_depth_v1_readonly.py`（codex 交付，29 测试）。

## 1. 结果：池深度充足

卖出 WETH 方向，滑点上限 50 bps：

| 仓位 | 可退出 | 实际冲击 | 充足 |
|---:|---:|---:|:--:|
| $50 | $50 | **0.001 bps** | ✅ |
| $5,000 | $5,000 | 0.102 bps | ✅ |
| $50,000 | $50,000 | 1.029 bps | ✅ |
| $500,000 | $500,000 | 10.416 bps | ✅ |

滑点上限扫描（仓位 $500,000）：**10 bps 上限下只能退出 $480,451**，50 bps 及以上可全额退出。冲击随规模近似线性（0.001 → 0.102 → 1.029 → 10.416），符合集中流动性在窄价格带内的预期。

单笔模拟：卖 1 WETH 得 **2,479.85 USDG**，跨 0 个 tick，冲击 0.05 bps。与池价 2,480.11 一致。

**对 PRD §6.4 的含义**：`measured_exit_depth_cap` 在本池对 100U 规模**不构成约束**——真正的约束来自 `POSITION_TVL_SHARE=0.0005`（$50 仓位需 $100k TVL）。退出深度只在大额或浅池标的上才成为瓶颈。

## 2. 一个只有真实数据能暴露的 API 陷阱

首次调用时**四个仓位全部返回 `max_exit_usd=0`、`EXIT_DEPTH_INSUFFICIENT`**，而单笔 swap 模拟却完全正常。根因：

`_state_factors` 对缺失参数的默认值是 **`decimals=0`、`price=1`**：

```python
dec0 = int(pool_state.get("token0_decimals", pool_state.get("decimals0", 0)))
input_price = explicit or (p0 if zero_for_one else p1) or Decimal(1)
```

我未传 `token0_decimals` / `token1_price_usd`，于是 $50,000 被换算成 **50,000 wei**（而非 2.02e19 wei），二分搜索在一个微不足道的数量上跑，自然返回 0。

**这是一个静默错误**：不抛异常、不报缺输入，只是把答案算成 0。而 0 在 PRD §8.4 的语义里是「深度为零、不可退出」——与真实情况（可退 50 万美元）完全相反，且方向是**危险的反面**：它会把可交易的池误判为不可退出（保守，尚可接受），但同样的默认值若出现在其它计算里可能反向。

**要求**（记入 RH-05c 后续修复）：`_state_factors` 缺 `decimals` 或价格时应返回 `None` 并让上层走 `INPUTS_UNAVAILABLE`，**不得默认成 0 位小数和 1 美元**。这与本项目已记录的三个假绿陷阱同源：USDG 6 位小数、int128 符号扩展、池 token 顺序——**全都是「不抛异常、只在部分输入上给错答案」**。

## 3. 计算器本身的正确性

传入正确参数后：

- `input_price` 由池价正确推出 **$2,480.11/WETH**（与独立测算的 2,480.11 一致）
- 冲击随规模单调递增且量级合理
- 空 `tick_data` 仍正确返回 `INPUTS_UNAVAILABLE: EXIT_QUOTE` 且 `max_exit_usd is None`（T24 红线未破）
- 跨 tick 计数、流动性耗尽标志工作正常

**结论：计算器实现正确，缺陷在参数默认值的宽容度上。**
