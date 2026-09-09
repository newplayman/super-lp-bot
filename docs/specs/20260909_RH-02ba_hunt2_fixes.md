# RH-02ba：修第二轮静默假绿扫描的 5 条发现

完整证据在 `reports/AUDIT_silent_failure_hunt2_20260909.md`，每条都有复现输入。
本 spec 只摘要，**动手前请读那份报告的对应小节**。

## 总原则

这个项目已确认 **22 例**同族缺陷，共同特征是「不抛异常、数字照样出来、结论全废」。
**修法一律是：拿不到数据就 fail-close（返回 None / INPUTS_UNAVAILABLE 并点名），
绝不用 0 / 1 / True 之类的默认值顶替。** 每个模块照抄它自己既有的失败表达方式。

## 五条

### 1. `scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py:58-64,259-260,303-316`
`PRICES_USD.get(symbol, Decimal("0"))` —— 只硬编码了 5 个代币
（WBNB/USDT/USDC/BUSD/DAI），**未知代币价格默认 0**。
后果：`vol = max(vol0, vol1)`，两边都未命中时整个交易对的
`volume_usd_proxy` 与 `pool_fee_usd_proxy` **算成 0**，相对误差 **-100%**，不报任何异常。
修：未知资产价格返回 `None`，该 pool/window 标记 `INPUTS_UNAVAILABLE`，
**严禁 0 作为价格参与乘积**。

### 2. `scripts/lp_survival_horizon_ev_model_v1_readonly.py:96-101`
```python
if capacity_proxy <= 0:
    return notional * 0.01          # 缺字段时硬塞 100 bps
return notional * (SLIPPAGE_BPS_AT_FULL_CAPACITY/10000.0) * max(0.0, 1.0 - capacity_proxy)
```
两个问题：`capacity_proxy = 1.0` 时滑点**恒为 0**（满容量无滑点，不成立）；
缺 `capacity_N` 字段时 `cap = pool.get(cap_field, 0.0) or 0.0` 变成 0，
滑点从 0 跳到 100 bps，**跳跃 200 倍**。
修：缺字段 → `None` 并中断，不要当成「容量为 0」；
满容量的滑点不得为 0（用实际深度曲线或保底 bps，理由写进注释）。

### 3. `scripts/strategy_pivot_d4_realtime_paper_shadow_validation.py:283-288`
### 4. `scripts/lp_survival_out_of_range_risk_v1_readonly.py:86-87`
### 5. `scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py:165-173`
这三条的触发条件、错幅与建议修法**见报告对应小节**，照它的建议修。
第 5 条与第 1 条同文件，一并处理。

## 每条都要有的测试

对每一条：
- 一条测试证明**缺数据时 fail-close**（不再返回那个错误的默认值）；
- 一条测试证明**数据齐备时行为与修改前完全一致**（防回归）。
用 `git show HEAD:<文件路径>` 加载旧版做对照，把两组实际数值贴进报告。

## 不许动

`scripts/lp_rh_*`（RH 线今晚全部改过，已入库）、任何 `.db`、`reports/` 下任何文件。
既有测试文件**只允许新增测试**。

## 验收标准

1. 五条的复现输入逐个验证：修改前给错误答案、修改后 fail-close。把两组输出贴进报告。
2. 防回归：每个被改函数的正常输入，新旧结果逐键一致。
3. 全量 `pytest tests/ -q -p no:cacheprovider | tail -3`，
   基线 **4582 passed / 0 failed**，不得新增 failed。
4. `git status --short | grep -v '^??'` 只应出现你改的那几个文件。

## 坑（今晚踩过三次，别再踩）

- **配置文件里的值类型不可信**：`pool_meta.json` 的 `input_price_usd` 是字符串 `"2484.0"`。
  取任何配置值都要显式转换并 fail-close。
- **不要读不存在的键**：写 `x.get("key")` 前先确认 `key` 真的会出现在 `x` 里。
  今晚有两个 worker 分别栽在 `pool_meta["input_price_usd"]` 的类型和
  `budget.get("over_budget")` 这个不存在的键上，**六个测试全绿而生产必崩**。
- **测试至少要有一个用例走真实数据**（真实文件 / 真实 db），不要全用手写 fixture。

## 纪律

- **不要执行任何 git 命令**（`git show` 只读可用）。
- 不要重启 daemon，不要动 crontab，不要发真实网络请求。
- 单次写入 ≤ 150 行；不要整读 >300 行的文件。
