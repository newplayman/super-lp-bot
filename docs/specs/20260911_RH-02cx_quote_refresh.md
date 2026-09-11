GOAL:
新建 `scripts/lp_rh_quote_refresh_v1.py`,重新观测 USDG/USD 汇率并写回
`reports/lp_rh/pool_meta.json` 的 `quote_usd_per_token1`。

## 为什么(实测,直接用)

Shadow **已经 11.7 小时产不出任何 NAV**。开盘后 17 个通过闸门的步,仓位标记全是同一个原因:

```
rh_position_marks.unvalued_risk_json →  reason: QUOTE_EVIDENCE_EXPIRED   (17/17)
```

根因是 `pool_meta.json` 里的报价证据过期了:

```json
"quote_usd_per_token1": {
  "value": "1.0",
  "source": "coingecko:global-dollar/usd (simple/price, free tier, no key)",
  "observed_at": "2026-09-10T01:50:10Z",
  "ttl_secs": 86400,
  "note": "TTL 24h; on expiry the runner reports QUOTE_EVIDENCE_EXPIRED and produces no NAV rather than reusing a stale rate."
}
```

`observed_at` + 24h 已于 `2026-09-11T01:50:10Z` 到期。
**这个 fail-close 设计是对的,不要去改它。** 缺的是一次新的观测。

## 照抄现成范式

`scripts/lp_rh_gas_refresh_v1_readonly.py` 是同一家族的先例,**先完整读它**(约 250 行),
照它的结构写:
- 模块本身**不做网络 I/O**,通过注入的 `fetch_fn` 拿数据(它注入的是 `rpc_fn`)
- `apply_to_pool_meta(path, refresh, *, backup=True)`:原子写(临时文件 + rename),
  写前把原文件备份成 `<path>.bak-<UTC时间戳>`
- 任何输入缺失或不合理 → 状态 `UNAVAILABLE`,**`apply_to_pool_meta` 什么都不写**
- 金额一律 `Decimal`

## 要做的事

新建 `scripts/lp_rh_quote_refresh_v1.py`:

1. 纯函数 `build_quote_refresh(raw_payload, *, now)`:
   从 CoinGecko simple/price 的响应里取出 USDG/USD 汇率,返回
   `{"status": "OK"|"UNAVAILABLE:<原因>", "quote": {...} | None, ...}`。
   `quote` 的结构必须与现有字段完全一致:`value`(字符串)、`source`、`observed_at`(当前 UTC RFC3339)、
   `ttl_secs`、`note`,另加:
   - `depeg_pct`:偏离 1.0 的百分比,用 `Decimal` 算,存字符串
   - `raw_fragment`:响应里取值的那一小段(便于审计,**不要存整个响应**)

2. **fail-close(本包的核心)**:下列情况一律 `UNAVAILABLE:<原因>` 且**不写文件**:
   - 请求失败 / 非 200 / 响应不是合法 JSON
   - 响应里找不到目标字段
   - 取到的值不是正数、或无法转成 `Decimal`
   - 取到的值**超出 (0.1, 10.0) 这个荒谬性区间**(只挡明显的垃圾值)
   **绝对不要在任何失败路径上写入 1.0。** 把「测不出汇率」当成「它还值 1 美元」,
   正是这个仓库反复出现的静默假绿形状,也正是现有 note 明确拒绝的做法。
   注意:**真实脱锚(例如 0.97)必须照实写入并在 `depeg_pct` 里体现,不许被当成异常挡掉。**

3. **`ttl_secs` 保持 86400,不许延长。**

4. CLI:`--pool-meta`(默认 `reports/lp_rh/pool_meta.json`)、`--apply`(**默认 dry-run**)、
   `--timeout-secs`(默认 10)。
   dry-run 打印将要写入的内容与 `depeg_pct`,**不碰文件**。
   CLI 负责实际发起 HTTPS 请求(免费档、无 key),模块函数不负责。
   请求要带 `User-Agent` 头(本机实测:某些端点对默认的 `Python-urllib` 直接返回 403)。

## 不许动

- **不要改 `scripts/lp_rh_shadow_runner_v1_readonly.py`**(另一个任务正在改它),
  也不要改 quote 的过期判定逻辑(`validate_quote_evidence`)——那个 fail-close 是对的。
- 不要改 `pool_meta.json` 里 `quote_usd_per_token1` 以外的任何字段。
- 不要改 `scripts/lp_rh_gas_refresh_v1_readonly.py`(只读它抄结构)。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动它们会把 Stage A 的 72 小时判定窗口清零。
- **不要用 `--apply` 跑生产文件。** 你只做到 dry-run 为止,主脑会自己决定何时 apply。
- 不要接入任何**付费**数据源,只用免费无 key 的端点。
- **不要执行任何 git 命令。不要 kill 或重启任何进程**
  (PID 2271374 采集器、2685886 shadow daemon 在跑生产)。
- 测试一律用 `tmp_path` 造 pool_meta 副本,**不要读写生产文件**。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试(新建 `tests/test_lp_rh_quote_refresh_v1_readonly.py`,≥8 条)

**写完把被测代码临时改坏,确认测试真的变红,再改回来。**

1. 正常响应(1.0001)→ `status OK`,`value` 正确,`observed_at` 是当前时间,`ttl_secs == 86400`
2. **真实脱锚 0.97 → 照常写入**,`depeg_pct` 约 -3%(**不许被当异常挡掉**)
3. 请求失败 / 非 JSON → `UNAVAILABLE:*`,`apply_to_pool_meta` **不写文件**(比对 mtime 与内容)
4. 响应缺目标字段 → `UNAVAILABLE:*`,不写
5. 值为 0 / 负数 / 非数字 → 三种都 `UNAVAILABLE:*`,不写
6. 值为 50.0(荒谬)→ `UNAVAILABLE:*`,不写
7. **任何失败路径上,写出的文件里都不得出现新的 `"value": "1.0"`**
   (专门断言这一条:构造一个原本 quote 已被删掉的 pool_meta,失败后文件里仍然没有 quote)
8. `--apply` 成功时:生成了 `.bak-*` 备份、原文件被原子替换、
   `quote_usd_per_token1` 以外的字段**逐字节不变**
9. dry-run 默认不写文件

## ENVIRONMENT(照做,别自己找解释器)
- 直接用 `python3`(3.12.3 + pytest 7.4.4 + pycryptodome,本仓库钉死的版本)。
- **不要找 venv**(`/root/lp-bot/.venv` 无权限)。**不要 pip install**,用标准库 `urllib.request`。
- **不要改任何全局配置**。不要读 `reports/polymarket_competitor`。不要整读 >300 行的文件
  (`lp_rh_gas_refresh_v1_readonly.py` 是例外,它约 250 行,可以整读)。

## VALIDATION(命令与输出尾部原样贴进报告)
1. `python3 -m pytest tests/test_lp_rh_quote_refresh_v1_readonly.py -q`(全绿,≥8 条)
2. `python3 scripts/lp_rh_quote_refresh_v1.py --pool-meta reports/lp_rh/pool_meta.json`
   (**dry-run**,贴出完整输出,包括实际取到的汇率与 `depeg_pct`)
3. `git status --short`(只读地看;`pool_meta.json` **必须未被修改**)
4. **不要跑全量测试**(另有 worker 并行跑,会撞车)。主脑会统一跑。

最后按以下字段报告:TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
