# TP-F-v1 验收记录（运行中）

F1 后以当前 scanner SQLite 最新批次（`2026-08-10T16:38:24.875047+00:00`）重跑 Base 漏斗：30 个终端记录、`accepted=0`，与 TP-E 基线 `accepted=0` 一致；本次只读重跑输出在 `reports/lp_tp_f/20260810/base_funnel_f1_rerun/`。
F4 后当前快照实际含 60 个 A/B/C 股票 CLMM（完整 universe 61，故未把任务书的 59 个硬凑数）：NetCover 为 `NETCOVER_INPUT_MISSING=23`、`ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE=22`、`RAW_SWAP_PRICE_PATH_INSUFFICIENT=10`、未产出=5，`stage2_pass=0`。
C 档 15 池三条新证据管线均已逐池落具体拒绝结论（退出 `GAPPED/NO_DATA`、无签名卖出模拟不可用、滑点模型具体缺项），因此 `pass_count=0`；没有用 `null` 加裸 `FAIL_CLOSED` 冒充证据。

## F1 — Base/EVM CLMM 生产路径回归修复

机械验收命令：

```text
$ python3 -m pytest tests/test_lp_scanner_daemon_v1_readonly.py tests/test_lp_netcover_inputs_v1_readonly.py tests/test_lp_netcover_amm_dispatch_v1_readonly.py -q
........................................................................ [ 69%]
...............................                                          [100%]
103 passed in 4.65s
```

生产路径最小完整 Base 记录（未手工设置 `protocol_type`）内联验收：

```text
$ python3 - <<'PY' ... PY
None
```

## F2 — C 档总敞口累加

机械验收命令：

```text
$ python3 -m pytest tests/test_lp_stock_tier_acceptance_v1_readonly.py -q
...                                                                      [100%]
3 passed in 0.04s
```

组合级回归用例 `test_c_batch_accumulates_passed_exposure_and_rejects_fifth_candidate`
断言同批五个完整 C 候选的前四个通过，第五个 `passed is False`，且
`failures` 包含 `7_budget_caps`。

## F3 — vetted_menu 每轮 cycle 导出

机械验收命令：

```text
$ python3 -m pytest tests/test_lp_scanner_daemon_v1_readonly.py -q
...............................................                          [100%]
47 passed in 2.39s
```

cycle 级回归用例 `test_cycle_exports_empty_vetted_menu_with_valid_json_schema`
运行一轮 `--once`，断言输出文件存在、可解析为 JSON list，且零候选时内容为 `[]`。

## F4 — Solana CLMM 经济回放

机械验收（新增/既有 stage2 单测）：

```text
$ python3 -m pytest tests/test_lp_solana_stock_stage2_v1_readonly.py -q
.........                                                                [100%]
9 passed in 0.09s
```

分段原始 stage2 输出合并校验（每段使用免费 RPC 轮巡、`--replay-limit 3`，无签名、无广播）：

```text
{"economics_reasons": {"ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE": 23, "None": 5, "PASS": 23, "RAW_SWAP_PRICE_PATH_INSUFFICIENT": 10}, "legacy_reason_count": 0, "stage2_pass_count": 0, "tier_counts": {"A": {"stage2_pass": 0, "total": 36}, "B": {"stage2_pass": 0, "total": 9}, "C": {"stage2_pass": 0, "total": 15}}, "universe_count": 61}
65 reports/lp_tp_f/20260810/stage2_clmm_f4_table.md
```

当前输入快照实际筛出 61 个 Solana CLMM 记录（其中 A/B/C 为 60 个；与任务书的 59 个不一致，未删除任何记录凑数）。旧裸原因
`CLMM_RANGE_AND_RAW_SWAP_REPLAY_REQUIRED` 计数为 0；逐池 NetCover/拒绝原因表见
`reports/lp_tp_f/20260810/stage2_clmm_f4_table.md`。

SPYX-SSX 同窗口回放验收：

```text
{"reference_fee_apr_pct": 2717.146, "relative_deviation_pct": 4.359088030887411, "spxy_ssx_fee_apr_pct": 2598.703213932264, "within_5pct": true}
```

## F5 — C 档退出、卖出模拟与滑点证据

配对单测：

```text
$ python3 -m pytest tests/test_lp_solana_stock_stage2_v1_readonly.py tests/test_lp_solana_tier_c_risk_evidence_v1_readonly.py -q
.............                                                            [100%]
13 passed in 0.13s
```

`tier_c_risk` 重跑（免费 RPC 索引不可用时保留原有 fail-closed）：

```text
$ python3 scripts/lp_solana_tier_c_risk_evidence_v1_readonly.py ... --fail-closed-rpc-reason 'F5 free RPC indexed holder data unavailable; no substitute used'
{"pool_count": 15, "pass_count": 0}
```

逐池字段完整性校验：

```text
{'tier_c_count': 15, 'missing_fields': 0, 'bare_fail_closed': 0}
```

未能构造可由协议官方 quote builder 提供的无签名 sell 交易包时，卖出模拟保持
`FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE`；没有签名、广播或生成私钥。

15 个 C 池逐池三条管线（`stage2_clmm_f5.json`）如下；`sell_simulation_ok` 均为
`false`，`known_honeypot/sell_tax_pct` 未在无签名模拟失败时虚构为通过值：

| 池 | 退出 verdict / 原因 | 卖出模拟 | 退出滑点原因 |
|---|---|---|---|
| CRCLX-IDLE | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| GLDX-IDLE | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| GLDX-XAUT0 | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| GLDX-XAUT0 | NO_DATA / RAW_SWAP_PRICE_PATH_INSUFFICIENT | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| GOOGLX-IDLE | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| MCDX-FRIES | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| MSTRX-ABTC | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| QQQX-ETHICS | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| QQQX-IDLE | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| SPCX-SPCXX | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| SPCXX-BOT | NO_DATA / RAW_SWAP_PRICE_PATH_INSUFFICIENT | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | EXIT_SLIPPAGE_MODEL_UNAVAILABLE |
| SPCXX-PROMETHEUS | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| SPCXX-URANUS | NO_DATA / RAW_SWAP_PRICE_PATH_INSUFFICIENT | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | EXIT_SLIPPAGE_MODEL_UNAVAILABLE |
| SPYX-SSX | GAPPED / ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |
| SPYX-STONK | NO_DATA / RAW_SWAP_PRICE_PATH_INSUFFICIENT | FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE | ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE |

## F6 — sidecar 独立预检与 EXIT_ONLY 方向核验

```text
$ python3 -m pytest tests/test_solana_m1_sidecar_e3.py -q
................................                                         [100%]
32 passed in 0.35s
```

对抗覆盖包括：plan 自报 `wallet_balance_ok=True` 而 `getBalance` 返回零余额时，报告
`preflight_all_pass=False`；以及 `EXIT_ONLY` 下 `reduces_risk=True`、但真实 token-account
mint 方向把持仓腿作为输出时，在签名前以 `direction increases` 拒绝。quote 仅接受本次
无签名 `simulateTransaction.returnData` 的非零返回，basis 读取当前非可执行 pool account，
余额读取 `getBalance` 和所有声明的 `getTokenAccountBalance`；缺少任一独立证据均 fail-closed。

## F7 — 卫生批次

```text
$ python3 -m pytest tests/test_lp_stock_tier_policy_v1_readonly.py tests/test_lp_stock_e5_position_report_v1_readonly.py tests/test_lp_stock_token_universe_v1_readonly.py tests/test_lp_stock_tier_acceptance_v1_readonly.py -q
..............................................................           [100%]
62 passed in 0.19s
```

`POSITION_TVL_SHARE` 与 `HARD_POSITION_TVL_SHARE` 现在只从 NetCover 引擎导入，且
`grep -n "0.0005\\|0.001" scripts/lp_stock_tier_policy_v1_readonly.py scripts/lp_stock_e5_position_report_v1_readonly.py`
无输出；其余卫生闸均为收紧，不增加候选。

## 最终全量回归（原始输出）

```text
$ python3 -m pytest tests/ -q
........................................................................ [  2%]
........................................................................ [  4%]
........................................................................ [  6%]
........................................................................ [  9%]
........................................................................ [ 11%]
........................................................................ [ 13%]
........................................................................ [ 16%]
........................................................................ [ 18%]
......s...........................s.....s.ss....s....................... [ 20%]
........................................................................ [ 23%]
........................................................................ [ 25%]
........................................................................ [ 27%]
........................................................................ [ 30%]
........................................................................ [ 32%]
......................s................................................. [ 34%]
........................................................................ [ 37%]
....s........................s.......................................... [ 39%]
............s........................................................... [ 41%]
........s...................................s........................... [ 44%]
............s......................................................s.... [ 46%]
........................................................................ [ 48%]
........................................................................ [ 51%]
........................................................................ [ 53%]
........................................................................ [ 55%]
........................................................................ [ 58%]
........................................................................ [ 60%]
........................................................................ [ 62%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 99%]
..                                                                       [100%]
3084 passed, 14 skipped in 60.91s (0:01:00)
```

```text
$ go test ./...
ok  	github.com/lpbot/lpbot/adapters/broadcast/disabled	(cached)
?   	github.com/lpbot/lpbot/adapters/bus/inproc	[no test files]
?   	github.com/lpbot/lpbot/adapters/bus/nats	[no test files]
?   	github.com/lpbot/lpbot/adapters/store/postgres	[no test files]
?   	github.com/lpbot/lpbot/adapters/store/sqlite	[no test files]
ok  	github.com/lpbot/lpbot/cmd/lpbot	(cached)
ok  	github.com/lpbot/lpbot/cmd/lpbot-backtest	(cached)
?   	github.com/lpbot/lpbot/cmd/lpbot-cli	[no test files]
?   	github.com/lpbot/lpbot/cmd/lpbot-migrate-postgres	[no test files]
ok  	github.com/lpbot/lpbot/cmd/lpbot-recon	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/alerter/log	(cached)
?   	github.com/lpbot/lpbot/internal/adapters/alerter/telegram	[no test files]
ok  	github.com/lpbot/lpbot/internal/adapters/bus/inproc	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/chain/base	(cached)
?   	github.com/lpbot/lpbot/internal/adapters/chain/base/abi	[no test files]
ok  	github.com/lpbot/lpbot/internal/adapters/chain/solana	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/birdeye	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/defillama	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/dexscreener	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/solana	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/datasource/subgraph	(cached)
?   	github.com/lpbot/lpbot/internal/adapters/holderconcentration/basescan	[no test files]
?   	github.com/lpbot/lpbot/internal/adapters/mev/flashbots	[no test files]
ok  	github.com/lpbot/lpbot/internal/adapters/mev/flashbots-protect	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/mev/jito	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/pool/aerodrome	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/pool/pancakeswap_v3_solana	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/pool/raydium_clmm	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/pool/uniswap_v3	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/pool/whirlpool	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/rpc	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/simulator/anvil	0.017s
ok  	github.com/lpbot/lpbot/internal/adapters/simulator/sol_rpc	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/store/postgres	8.289s
ok  	github.com/lpbot/lpbot/internal/adapters/store/postgres/migrator	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/store/sqlite	(cached)
?   	github.com/lpbot/lpbot/internal/adapters/store/sqlite/sqlcgen	[no test files]
ok  	github.com/lpbot/lpbot/internal/adapters/wallet/keystore	(cached)
ok  	github.com/lpbot/lpbot/internal/adapters/wallet/kms	(cached)
?   	github.com/lpbot/lpbot/internal/adapters/wallet/none	[no test files]
ok  	github.com/lpbot/lpbot/internal/core/audit	(cached)
ok  	github.com/lpbot/lpbot/internal/core/execution	(cached)
ok  	github.com/lpbot/lpbot/internal/core/loop	(cached)
ok  	github.com/lpbot/lpbot/internal/core/pnl	(cached)
ok  	github.com/lpbot/lpbot/internal/core/reconcile	(cached)
ok  	github.com/lpbot/lpbot/internal/core/reporting	(cached)
ok  	github.com/lpbot/lpbot/internal/core/risk	(cached)
ok  	github.com/lpbot/lpbot/internal/core/scanner	(cached)
ok  	github.com/lpbot/lpbot/internal/core/simulation	(cached)
ok  	github.com/lpbot/lpbot/internal/core/strategy	(cached)
ok  	github.com/lpbot/lpbot/internal/core/tierc	(cached)
ok  	github.com/lpbot/lpbot/internal/core/watchdog	(cached)
ok  	github.com/lpbot/lpbot/internal/domain	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/config	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/decimal_db	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/health	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/idgen	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/log	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/metrics	(cached)
?   	github.com/lpbot/lpbot/internal/platform/redis	[no test files]
ok  	github.com/lpbot/lpbot/internal/platform/timex	(cached)
ok  	github.com/lpbot/lpbot/internal/platform/trace	(cached)
ok  	github.com/lpbot/lpbot/internal/ports	(cached)
ok  	github.com/lpbot/lpbot/pkg/decimal	(cached)
ok  	github.com/lpbot/lpbot/pkg/il	(cached)
ok  	github.com/lpbot/lpbot/pkg/tickmath	(cached)
?   	github.com/lpbot/lpbot/scripts/aggregate-verdict	[no test files]
ok  	github.com/lpbot/lpbot/tests/chaos	(cached)
?   	github.com/lpbot/lpbot/tests/fork	[no test files]
ok  	github.com/lpbot/lpbot/tests/property	(cached)
ok  	github.com/lpbot/lpbot/tests/property/mocks	(cached)
```
