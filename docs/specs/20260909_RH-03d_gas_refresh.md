# RH-03d：用动态估算刷新 pool_meta 的 gas，并且拿不到数据时绝不写

## 为什么这一项现在必须做

`reports/lp_rh/pool_meta.json` 的 `gas_usd_estimate` **此刻仍是 `0.02`**
（文件时间 09-09 00:14）。这正是被证伪的那个值：实测真值 **$0.4614**，低估 23 倍，
曾把资金政策结论算反。shadow daemon 在启动时把它读进内存，
`_POOL_EVIDENCE_KEYS` 再把它喂给 `assemble_rh_clmm_inputs`。

RH-03c 已经建好估算器（`scripts/lp_rh_gas_estimator_v1_readonly.py`，已入库 `e0dcb04`），
但**没有任何东西把它的结果写回 pool_meta**。本包补上这一段，且**不写死任何 gas 常量**——
包括 0.4614，那也只是当时 gas price 下的快照。

## 可直接调用的接口（已用 `ast` 抽出，**不要再 grep**）

`scripts/lp_rh_gas_estimator_v1_readonly.py`：
```
GAS_UNITS = {'v3_mint': 450000, 'v3_burn_collect': 350000, 'swap': 150000}
def estimate_gas_usd(*, gas_price_wei, native_price_usd, gas_units) -> Optional[Decimal]
def round_trip_gas_usd(*, gas_price_wei, native_price_usd) -> Optional[Decimal]
def observed_gas_units(receipts) -> dict     # {"n","median_gas_used","median_gas_price_wei","p90_gas_used"}
def gas_estimate_sanity(estimate_usd, observed_usd, *, max_ratio=Decimal("3")) -> dict
                                             # {"ratio","verdict": OK|UNDERSTATED|OVERSTATED|UNKNOWN}
```

`pool_meta.json` 现有 22 个键（**一个都不许丢**）：
`active_liquidity_notional_usd, attestation_status, current_tick, dec0, dec1, fee,
fee_apr_pct, fee_pips, gas_usd_estimate, input_price_usd, liquidity, liquidity_raw,
max_impact_bps, protocol, range_pct, sigma_daily, sqrt_price_x96, tick_data,
tick_spacing, token0_decimals, token1_decimals, tvl_usd`

## 只新建一个实质文件 + 其测试

### 1. `scripts/lp_rh_gas_refresh_v1_readonly.py`（≤260 行）

**模块自身不联网**：链上数据通过注入的 `rpc_fn(method, params) -> Any` 取得，
`native_price_usd` 由调用方以参数给入（本包不负责找 ETH 价格源）。

- `collect_gas_inputs(rpc_fn, *, receipt_sample=8) -> dict`
  取 `eth_gasPrice`，取最新区块（`eth_getBlockByNumber`，**方法名必须写全**，
  参数 `["latest", True]`），从中取最多 `receipt_sample` 笔交易的
  `gasUsed`/`effectiveGasPrice` 交给 `observed_gas_units`。
  返回 `{"gas_price_wei","block_number","observed","errors"}`。
  **任何一步失败都进 `errors` 并把对应值置 `None`，不抛、不填 0。**
- `compute_refresh(inputs, *, native_price_usd, current_estimate) -> dict`
  用 `round_trip_gas_usd` 算新值；用 `gas_estimate_sanity(current_estimate, new_value)`
  比较旧值与新值。返回
  `{"new_gas_usd","sanity","provenance","verdict"}`，
  `verdict` ∈ `REFRESHED` / `UNAVAILABLE`。
  `provenance` 必含 `gas_price_wei`、`native_price_usd`、`block_number`、
  `receipt_n`、`gas_units_total`、`computed_at`。
  **`new_gas_usd` 为 `None` 时 `verdict` 必须是 `UNAVAILABLE`。**
- `apply_to_pool_meta(path, refresh, *, backup=True) -> dict`
  **`verdict != "REFRESHED"` 时一个字节都不写**，返回 `{"written": False, ...}`。
  写入必须**原子**：写同目录临时文件 → `os.replace`（daemon 可能正在读，
  绝不能让它读到半个文件）。`backup=True` 时先把原文件复制成
  `<path>.bak-<UTC 时间戳>`。
  **只改 `gas_usd_estimate` 一个键**，并新增 `gas_provenance`（dict）；
  其余 22 个键**原样保留**，键的顺序不作要求但数量与值必须一致。
- `main()`：`--pool-meta --native-price-usd --receipt-sample --dry-run --apply`。
  **`--apply` 不给就只打印不写**（默认只读）。

### 2. `tests/test_lp_rh_gas_refresh_v1_readonly.py`（≤240 行，**≥16 测试**）

顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
**不许联网**，全部用假 `rpc_fn` 与 `tmp_path` 下的临时 JSON。必测：

- 正常路径：假 `rpc_fn` 给 `gas_price_wei=232188000`、8 笔 receipt，
  `native_price_usd=2484` → `new_gas_usd` 落在 **0.46–0.47**（锚定实测值）。
- **★`eth_gasPrice` 抛异常 → `verdict == "UNAVAILABLE"`，`new_gas_usd is None`，
  且 `apply_to_pool_meta` 返回 `written is False`、**文件字节数与内容完全不变**★**
- **★区块没有交易（receipts 为空）→ `observed` 各项为 `None`（不是 0），
  不得因此把 `new_gas_usd` 算成 0★**
- **★`native_price_usd` 为 `None` / `0` / 负数 → `UNAVAILABLE`，不写★**（三条）
- `sanity` 对 `current_estimate=0.02` 与新值 0.4614 给出 `UNDERSTATED`
  （**这条复现本次的真实处境**）。
- 原子写：`apply_to_pool_meta` 之后重新加载 JSON，断言
  **22 个原有键全部存在且值不变**，只有 `gas_usd_estimate` 变了，
  且多出 `gas_provenance`。
- `backup=True` 时生成 `.bak-` 文件且其内容等于原文件。
- `backup=False` 时不生成备份文件。
- `provenance` 六个键齐全且 `gas_price_wei`/`block_number` 等于注入值。
- 幂等：同样输入连跑两次，第二次文件内容与第一次相同（除 `computed_at`）。
- `main` 不带 `--apply` 时**文件不变**（断言 mtime 与内容均不变）。
- `main` 带 `--dry-run` 时返回 0 且不写。
- 金额用 `Decimal`，写进 JSON 时转成 float 或字符串均可，但**不得丢精度到 2 位以下**。

## 不许动
不改 `lp_rh_gas_estimator_v1_readonly.py`、不改 shadow daemon/runner、
不改 `lp_rh_netcover_inputs_v1_readonly.py`。**不写死任何 gas 常量**。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_gas_refresh_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥16 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。
