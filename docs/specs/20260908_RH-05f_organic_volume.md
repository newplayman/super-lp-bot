# RH-05f：有机交易量核验（费收分母到底真不真）

## 背景与经济动机

`RH05_EVIDENCE_COMPLETE.md` 自列缺口之二：**有机交易量未核验**。
所有费收预测都建立在「池子的历史成交量会继续发生」之上。但新链早期成交量常由**极少数地址**贡献，甚至是同一地址来回对敲。这类量：

- 对敲方自己付费给自己（净支出仅为手续费），**随时可停**，不能外推；
- 高度集中的量意味着单个参与者退出就让费收归零，是**尾部风险不是基线**。

若真实有机占比只有 20%，则实测年化 27.34% 的费收上界要打到 5.5%，NetCover 结论会翻转。本包只做**离线纯函数**：主脑负责拉链上 Swap 日志喂进来。

## 只写两个文件（写到 `/tmp/codex_out/RH-05f/` 下同名子目录）

1. `scripts/lp_rh_organic_volume_v1_readonly.py`（≤320 行）
   `Decimal` 计价。缺输入 `None`，**绝不用 0 代替缺失**。不联网、不写库。

   事件形状：`{"block": int, "tx_hash": str, "log_index": int, "sender": str, "recipient": str, "amount0": Decimal-like, "amount1": Decimal-like}`。
   Uniswap V3 约定：`amount0`/`amount1` 一正一负（正=流入池）。**地址统一转小写**再比较。
   单笔名义量定义为 `abs(amount1)`（token1 计），并在 docstring 里写明这是代理量、跨池不可比。

   - `swap_direction(event) -> Optional[str]`：`"BUY0"`（amount0<0）/ `"SELL0"`（amount0>0）；两者同号或有 `None` → `None`。
   - `participant_concentration(events) -> dict`
     返回 `{"n_events","n_unique_senders","top1_share","top5_share","hhi","status"}`。
     按 `sender` 聚合名义量算份额；`hhi` = Σ(share²)，范围 0~1。空输入 → `status="INPUTS_UNAVAILABLE"` 且所有份额 `None`。
   - `round_trip_volume(events, *, window_blocks=50) -> dict`
     同一 `sender` 在 `window_blocks` 内出现**方向相反**的两笔即配成一对往返；每对计入的往返量取**两笔中较小的 `abs(amount1)`**（保守，不重复计）。每笔最多被配对一次。
     返回 `{"pair_count","round_trip_volume","total_volume","round_trip_share","status"}`。
   - `organic_volume_estimate(events, *, window_blocks=50, max_single_sender_share=Decimal("0.25"), min_events=50) -> dict`
     从总量中扣两部分：① 全部往返量；② 任一 sender 超过 `max_single_sender_share` 的**超出部分**。两者对同一笔的扣减**不得重复计算**（先扣往返，再对剩余量算集中度超额）。
     返回 `{"total_volume","round_trip_volume","concentration_excess_volume","organic_volume","organic_fraction","n_events","n_unique_senders","status","notes"}`。
     - `status`：空 → `"INPUTS_UNAVAILABLE"`；`0 < n_events < min_events` → `"INSUFFICIENT_SAMPLES"`（`organic_fraction` 为 `None`，但计数照给）；否则 `"COMPUTED"`。
     - `organic_fraction` 必须夹在 `[0, 1]`，且当 status 非 COMPUTED 时为 `None`。
   - `apply_organic_haircut(fee_apr_pct, organic_fraction) -> Optional[Decimal]`：相乘；任一为 `None` → `None`（**不是原值**：无法核验时不许乐观透传）。
   - `main()`：`--events-json --out`，纯离线。

2. `tests/test_lp_rh_organic_volume_v1_readonly.py`（≤300 行，**≥18 个测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。必测：
   - 100 笔互不相同 sender、方向随机 → `organic_fraction` 接近 1（>0.9），`hhi` 很小。
   - **单一地址完全对敲**：60 笔同一 sender 严格交替方向、金额相同 → `round_trip_share` 接近 1、`organic_fraction` 接近 0。
   - 单地址占 80% 名义量 → `concentration_excess_volume > 0`，`organic_fraction < 0.5`。
   - **不重复扣减**：构造一批既是往返、又来自超额大户的事件，断言 `round_trip_volume + concentration_excess_volume <= total_volume`（这是防重复计的硬不等式）。
   - `organic_fraction` 恒在 `[0,1]`：对上面每个场景都断言。
   - `window_blocks` 敏感性：把往返两笔的块距拉到 `window_blocks+1` → 不再配对，`pair_count == 0`。
   - 大小写地址：`0xAB..` 与 `0xab..` 必须视为同一 sender（一个专门测试）。
   - `n_events = 49 < min_events=50` → `INSUFFICIENT_SAMPLES` 且 `organic_fraction is None`。
   - 空列表 → `INPUTS_UNAVAILABLE`，所有份额 `None`（用 `is None` 断言）。
   - `apply_organic_haircut(Decimal("27.34"), None) is None`（**不是 27.34**）。**这条是本包的核心陷阱。**
   - `swap_direction` 两个 amount 同号 → `None`。

## 硬约束
不读、不改 `/opt/lpbot` 下任何文件（spec 除外，只读）。单次写 ≤120 行。写完 `ast.parse` 自检。

## 验收
```
cd /tmp/codex_out/RH-05f && PYTHONPATH=/opt/lpbot/lp-bot-v3-origin-check:/tmp/codex_out/RH-05f \
  /root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
必须真跑通、全绿、≥18 passed。把最后 15 行原样贴出来。
