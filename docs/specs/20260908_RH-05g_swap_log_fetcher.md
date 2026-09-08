# RH-05g：Swap 日志抓取与解码（给有机交易量模块喂真数据）

## 背景

RH-05f 的 `lp_rh_organic_volume_v1_readonly` 能判断成交量里有多少是对敲与单点集中，但**目前没有数据源**：它需要 `[{"block","tx_hash","log_index","sender","recipient","amount0","amount1"}]`，而链上只有原始 `eth_getLogs` 返回。本包补上这一段。

`amount0` / `amount1` 是 **int256 补码**，正负各半。**把补码当无符号读，会把每一笔卖单读成 ~1.15e77 的天量买单**，于是「总成交量」被放大 60 个数量级而方向全错。这与本仓已发生过的两次「原始比值当归一化价格」是同一族失败：数值出来了、程序不报错、结论全废。

本包只做**离线纯逻辑**，网络通过注入的 `call_fn` 完成，模块自身不联网。

## 常量（已用 keccak 算准，直接抄，不要自己猜）
- `SWAP_TOPIC0 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"`
  （`Swap(address,address,int256,int256,uint160,uint128,int24)`）
- `sender` 与 `recipient` 是 **indexed**，在 `topics[1]` / `topics[2]`；
  `amount0, amount1, sqrtPriceX96, liquidity, tick` 依次在 `data` 的第 0~4 个 32 字节字。

## 只写两个文件（写到 `/tmp/codex_out/RH-05g/` 下同名子目录）

1. `scripts/lp_rh_swap_logs_v1_readonly.py`（≤300 行）

   - `decode_int256(word_hex) -> int`
     32 字节字按**二进制补码**解码：最高位为 1 则减 `2**256`。
   - `decode_swap_log(log) -> Optional[dict]`
     输入 `eth_getLogs` 的一条 log（`{"address","topics","data","blockNumber","transactionHash","logIndex"}`）。
     - `topics[0]` 不等于 `SWAP_TOPIC0` → 返回 `None`（不抛）。
     - `topics` 少于 3 个或 `data` 不足 5 个字 → 返回 `None`。
     - 地址从 topic 取低 20 字节并**转小写**。
     - 返回 `{"block": int, "tx_hash": str, "log_index": int, "sender","recipient",
        "amount0": int, "amount1": int, "sqrt_price_x96": int, "liquidity": int, "tick": int}`。
       `blockNumber` / `logIndex` 是十六进制字符串，须转 int。`tick` 也是补码有符号。
   - `split_range(from_block, to_block, max_span) -> list[tuple[int,int]]`
     闭区间切块，最后一块可短；`max_span <= 0` 抛 `ValueError`；`from > to` 返回 `[]`。
   - `fetch_swaps(pool, from_block, to_block, call_fn, *, max_span=2000, max_depth=6) -> dict`
     `call_fn(params_dict)` 返回 log 列表或抛异常。
     - 异常消息里含 `"more than"` / `"too many"` / `"range"` / `"limit"`（不分大小写）→
       把该区间**对半拆**重试，递归深度上限 `max_depth`；到顶仍失败则把该区间记入 `failed_ranges`，
       **继续处理其余区间**，绝不整体放弃。
     - 按 `(tx_hash, log_index)` 去重。
     - 返回 `{"events": [...], "requested_blocks": int, "covered_blocks": int,
        "failed_ranges": [[a,b],...], "coverage_frac": Decimal|None, "status": str}`。
       `status`：无失败区间 → `"COMPLETE"`；部分失败 → `"PARTIAL"`；全失败 → `"INPUTS_UNAVAILABLE"`。
       **`coverage_frac` 在 `INPUTS_UNAVAILABLE` 时为 `None`，不是 0**——覆盖率未知与覆盖率为零不是一回事。
   - `to_organic_events(events) -> list[dict]`
     转成 RH-05f 期望的形状：`amount0` / `amount1` 转 `Decimal`，其余字段原样带上。
   - `main()`：`--pool --from-block --to-block --out`，默认 `call_fn` 用 urllib（带 `User-Agent`），
     `--dry-run` 用假 `call_fn` 不联网。

2. `tests/test_lp_rh_swap_logs_v1_readonly.py`（≤300 行，**≥20 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。全部用假 `call_fn`，**不许联网**。必测：
   - `decode_int256("0x" + "00"*31 + "01") == 1`。
   - `decode_int256("0x" + "ff"*32) == -1`。**补码负数，这条是本包核心陷阱。**
   - `decode_int256("0x" + "80" + "00"*31) == -(2**255)`（最负值边界）。
   - 一条真实形状的 Swap log（`amount0` 正、`amount1` 负）解出**一正一负**，且 `amount1 < 0`。
   - `topics[0]` 是 Mint 的 topic
     （`0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde`）
     → `decode_swap_log` 返回 `None`（用 `is None` 断言）。
   - `topics` 只有 1 个 → `None`；`data` 只有 2 个字 → `None`。
   - 地址大小写：topic 里是大写 hex → 解出的 `sender` 全小写。
   - `blockNumber="0x1e"` → `block == 30`（十六进制转换，别当十进制）。
   - 负 `tick`（补码）解出负数。
   - `split_range(100, 105, 2) == [(100,101),(102,103),(104,105)]`；
     `split_range(100, 100, 2) == [(100,100)]`；`split_range(105, 100, 2) == []`；
     `max_span=0` 抛 `ValueError`。
   - 假 `call_fn` 对 span>1000 抛 `"query returned more than 10000 results"` →
     `fetch_swaps` 自动对半拆并最终 `status == "COMPLETE"`，事件数正确。
   - 某一子区间**无论怎么拆都失败** → `status == "PARTIAL"`，`failed_ranges` 非空，
     其余区间的事件**仍然返回**（断言 `events` 非空）。
   - 全部区间失败 → `status == "INPUTS_UNAVAILABLE"` 且 `coverage_frac is None`（**不是 0**）。
   - 同一 `(tx_hash, log_index)` 出现两次 → 去重后只留 1 条。
   - `to_organic_events` 产出的字段名与 RH-05f 的 `organic_volume_estimate` 入参形状一致，
     且 `amount0`/`amount1` 是 `Decimal`。

## 硬约束
不读、不改 `/opt/lpbot` 下任何文件（spec 除外）。测试不得发起真实网络请求。单次写 ≤120 行。写完 `ast.parse` 自检。

## 验收
```
cd /tmp/codex_out/RH-05g && PYTHONPATH=/opt/lpbot/lp-bot-v3-origin-check:/tmp/codex_out/RH-05g \
  /root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
必须真跑通、全绿、≥20 passed，贴尾部 15 行。
