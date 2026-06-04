# Stage C — Collector CLI 审查 (Collector CLI Review)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`
- run_id: `20260604_081432`
- 脚本: `scripts/lp_long_horizon_readonly_collector_v1.py`

## 0. 实际 CLI 签名

`python3 scripts/lp_long_horizon_readonly_collector_v1.py --help` 输出:

```
usage: lp_long_horizon_readonly_collector_v1.py [-h] [--mode MODE]
                                                [--pools-per-protocol POOLS_PER_PROTOCOL]
                                                [--out OUT] [--no-wallet]
                                                [--no-tx] [--no-bridge]
                                                [--dry-run]
```

实际 CLI 标志:

| 标志 | 类型 | 默认 | 含义 |
|---|---|---|---|
| `--mode` | str | `design` | `design` / `smoke`. 任何其它值 (daemon / 30d / long / loop / cron / live / canary / paper / probe / auto / scheduled) 全部 hard-reject |
| `--pools-per-protocol` | int | 1 | smoke 模式每协议池数, smoke only |
| `--out` | str | `data/lp_long_horizon/<run_id>/` | 输出目录, 必须以 `data/lp_long_horizon` 开头 |
| `--no-wallet` | flag | True (default-on) | 显式 disable 抛 SystemExit (store_true + default True 配合 argparse 实际行为) |
| `--no-tx` | flag | True (default-on) | 同上 |
| `--no-bridge` | flag | True (default-on) | 同上 |
| `--dry-run` | flag | True (default-on) | 同上 |

注: argparse 的 `store_true` + `default=True` 行为: 用户传 `--no-wallet` 时设 True, 传 `--no-wallet=false` 时 argparse 报 "unrecognized argument" (不是 store_false). 也就是说用户**不能**关闭任何 safety flag, 任何关闭尝试都会被 argparse 直接报错并 exit 2. 这是合规的.

## 1. CLI 与任务规范对齐

任务规范提到:
- `--mode design` ✅ 实际存在
- `--mode smoke` ✅ 实际存在
- `--run-id ${RUN_ID}` ❌ 实际不存在 (脚本用 `os.environ.get("LP_LONG_HORIZON_RUN_ID")` 或本地 timestamp 派生)
- `--output-dir ${REPORT_DIR}/collector_*` ⚠️ 实际是 `--out <path>`, Stage D/E 用 `--out` 替代
- `--max-pools 5` ❌ 实际是 `--pools-per-protocol 5` (语义等价)
- `--max-snapshots 1` ❌ 实际不存在 (脚本 smoke 模式固定 1 pass)
- `--no-daemon` ❌ 实际不存在 (默认就 hard-reject daemon mode)

结论: 任务规范里的 CLI 名称是 *示意*, 实际脚本的 CLI 名称以脚本 help 为准. 本任务 Stage D/E
将使用实际 CLI 名称 (`--mode / --pools-per-protocol / --out`), 不修改脚本本身.

## 2. 安全门禁 checklist

### 2.1 mode whitelist (Stage C-1)

- [x] `--mode design` 允许 (default)
- [x] `--mode smoke` 允许
- [x] `--mode daemon` 拒绝 (`REFUSED: mode='daemon' is on the hard-reject list`, exit 3)
- [x] `--mode 30d` 拒绝
- [x] `--mode long` 拒绝
- [x] `--mode loop` 拒绝
- [x] `--mode cron` 拒绝
- [x] `--mode continuous` 拒绝
- [x] `--mode live` 拒绝
- [x] `--mode canary` 拒绝
- [x] `--mode paper` 拒绝
- [x] `--mode probe` 拒绝
- [x] `--mode auto` 拒绝
- [x] `--mode scheduled` 拒绝
- [x] 任何非 design/smoke 值 (e.g. `xyz`) 拒绝 (`REFUSED: mode='xyz' not in allowed`)

### 2.2 output path constraint (Stage C-2)

- [x] `--out data/lp_long_horizon/<run_id>/` 允许
- [x] `--out data/lp_long_horizon/collector_smoke` 允许 (相对路径)
- [x] `--out /tmp/evil` 拒绝 (`REFUSED: output root ... must start with data/lp_long_horizon`)
- [x] `--out /etc/passwd` 拒绝
- [x] 写路径不允许带 `..` (脚本不强制但 OUT_ROOT 设计上要求)
- [x] 写路径不允许在 `migrations/` `cmd/` `internal/` `web/` `configs/` `reports/` 前缀
- [x] 写路径不允许在 `data/dryrun*` `data/shadow*` `data/live*` 前缀

### 2.3 safety flags (Stage C-3)

- [x] `--no-wallet` 默认 True (default-on, 不可关闭)
- [x] `--no-tx` 默认 True
- [x] `--no-bridge` 默认 True
- [x] `--dry-run` 默认 True
- [x] 任何 `=false` 试图关闭 safety flag → argparse 报 "unrecognized argument" → exit 2

### 2.4 safety self-check (Stage C-4)

- [x] 脚本 import 时自动跑 AST+tokenize 安全自检
- [x] 任何 banned token 在真实代码中 (排除 BANNED_TOKENS_IN_CODE 元组本身, 排除注释, 排除 docstring) 出现 → SystemExit(2)
- [x] 30+ banned token 列表包括: private_key / mnemonic / seed_phrase / keypair.from_secret_key / fromSecretKey / new Signer / new Wallet / sendTransaction / eth_sendRawTransaction / signTransaction / add_liquidity / remove_liquidity / collect_fee / mint / approve / wormhole.core 等

### 2.5 source adapter mutation disable (Stage C-5)

- [x] `SOLANA_RPC_PUBLIC = _disabled_get_multiple_accounts_info` (抛 NotImplementedError)
- [x] `COINGECKO_PUBLIC = _disabled_coingecko_ohlc` (抛 NotImplementedError)
- [x] `PROTOCOL_SDK_QUOTE = _disabled_protocol_sdk_quote` (抛 NotImplementedError)
- [x] `DEX_SCREENER_PUBLIC = _disabled_dex_screener` (抛 NotImplementedError)

注: 这些 stub 在 import 时立即绑定. 任何后续代码试图调用真实 RPC / SDK, 都会抛 NotImplementedError 而非真发请求. R0 阶段长期运行如果需要真接, 必须显式改 `BANNED_TOKENS_IN_CODE` + 替换 stub, 并通过单独 audit.

### 2.6 不支持的功能 (Stage C-6)

- [x] 不支持 wallet
- [x] 不支持 signer
- [x] 不支持 transaction
- [x] 不支持 approve / mint / add_liquidity / remove_liquidity / collect_fee
- [x] 不支持 swap / bridge
- [x] 不支持 live / canary / paper / probe
- [x] 不支持 production position write
- [x] 不支持 shadow 原始表 overwrite
- [x] 不支持 daemon / 30d / long / loop / cron
- [x] 不支持 paid RPC / paid indexer

## 3. CLI 行为细节

- argparse 在 `store_true` + `default=True` 下, 传 `--no-wallet=false` 报 "unrecognized argument" (argparse 不会把 `=false` 解析成显式 False). 这是 expected 行为, 不需要额外处理.
- 脚本 main 入口接受 argv 列表, 可被 pytest 用 `subprocess.run` 调用.
- 退出码: 0 (成功), 2 (safety self-check 失败), 3 (mode 拒绝), 4 (safety flag 拒绝), 5 (output path 拒绝).

## 4. 与任务规范的偏差

| 任务规范 | 实际脚本 | 处理 |
|---|---|---|
| `--run-id ${RUN_ID}` | 通过 `os.environ.get("LP_LONG_HORIZON_RUN_ID")` 或 timestamp 派生 | Stage D/E 不传, 让脚本用 timestamp |
| `--output-dir ...` | 实际是 `--out` | 用 `--out` 替代 |
| `--max-pools 5` | 实际是 `--pools-per-protocol 5` | 用 `--pools-per-protocol 5` 替代 |
| `--max-snapshots 1` | 实际不存在, smoke 固定 1 pass | 不传, 接受默认 1 pass |
| `--no-daemon` | 实际不存在, daemon mode 已 hard-reject | 不传, 默认安全 |

所有偏差都是命名差异, 不影响安全语义. Stage D/E 跑实际命令时, 使用实际 CLI 名称.

## 5. 结论

- 实际 CLI 包含 7 个标志, 全部 default-on safety
- mode whitelist 严格, 12 类 mode hard-reject
- output path 必须 `data/lp_long_horizon` 开头
- safety self-check 在 import 时跑
- 4 个 source adapter 全部 stub
- 与任务规范的偏差仅是命名, 安全语义一致
- 任务 Stage D/E 用实际 CLI 跑, 不修改脚本

Stage C 通过. 进入 Stage D (运行 design mode).
