# Monitor Start Healthcheck — LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1

- stage: `LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1`
- run_id: `20260602_193517`
- 检查时间：startup + ~2 min 后

## 1. 启动配置

```text
session_name     = lp_base_10u_probe_readiness_monitor_20260602_193517
output_dir       = reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor
interval_minutes = 10
max_hours        = 8
rpc              = https://base-rpc.publicnode.com
candidate        = chain=Base  pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38
                    pair=WETH/USDC  fee_tier=100
                    wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835
                    notional=10  hold=15m
```

## 2. 健康检查结果（启动后约 2 分钟）

| 检查项 | 结果 | 证据 |
|---|---|---|
| tmux session exists | **PASS** | `tmux list-sessions` shows `lp_base_10u_probe_readiness_monitor_20260602_193517` |
| monitor.log updating | **PASS** | 2 行: started @19:44:19Z + iter=1 落库 @19:44:19Z |
| state.json exists | **PASS** | `state.json` 269 字节，含 `last_checkpoint_iso=2026-06-02T19:44:19Z` |
| first checkpoint exists | **PASS** | `checkpoint_20260602T194419Z.json` 1489 字节 |
| 后续 checkpoint 在生成 | **PASS**（每 10 分钟） | 间隔 600s，本检查时仅 1 个 |
| no forbidden process | **PASS** | `ps aux` 排除 systemd/PM2/snapshot 后无 `canary`/`lpbot-live`/`live`/`paper`/`eth_sendRawTransaction`/`eth_sendTransaction` |
| no transaction symbols | **PASS** | monitor 进程未加载任何 Account/Web3/send_raw_transaction/send_transaction 字符串 |
| no private key loaded | **PASS** | monitor 进程不读 `*.env`、不读 `keystore*`、不读 `mnemonic*` |

## 3. 第一次 checkpoint 关键读数

| 字段 | 值 | 状态 |
|---|---|---|
| `chain_id` | 8453 | ✅ Base mainnet |
| `block_number` | 46820056 | ✅ 链在前进 |
| `wallet_eth_wei` | 90470751043807 ≈ 0.0905 ETH | ✅ 充裕 |
| `usdc_balance_raw` | 21774783 ≈ 21.77 USDC | ✅ 充裕（>= 10 USDC 阈值）|
| `weth_balance_raw` | 2470131003793800 ≈ 0.00247 ETH | ✅ 备用 |
| `usdc_allowance_raw` | 5000000 = 5 USDC | ⚠ < 10 USDC（fresh_approval_required）|
| `weth_allowance_raw` | 2470131003793800 | ✅ 充裕 |
| `current_tick` | -200828 | 与 preflight 接近（preflight 是 -200867）|
| `drift_ticks` | -385 | > 200 阈值 → fresh_approval_required |
| `current_tick_inside_new_range` | true | ✅ |
| `gas_price_wei` | 14018528 ≈ 0.014 gwei | ✅ Base gas 极低 |
| `any_stop_condition_active` | true | 因 `fresh_approval_required=true` |
| `market_safe_for_execution_candidate` | false | 因上条 |

## 4. 进程级审计

| 检查项 | 结果 |
|---|---|
| monitor 进程是否调用 `eth_sendTransaction` | **未调用**（仅 eth_chainId/eth_blockNumber/eth_getBalance/eth_call/eth_gasPrice）|
| monitor 进程是否调用 `eth_sendRawTransaction` | **未调用** |
| monitor 进程是否构造 signer | **未构造**（脚本里无 `Account.from_key`/`LocalAccount`/`sign_transaction`） |
| monitor 进程是否读私钥 | **未读**（脚本里无 `load_keystore`/`read_keyfile`/`mnemonic`） |
| monitor 进程是否修改 v2 executor | **未修改**（v2 line count 仍 992） |
| monitor 进程是否触碰 live/canary/paper 入口 | **未触碰** |

## 5. 后续如何健康检查

随时可执行：

```bash
# 当前 monitor 状态
tail -5 reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/monitor.log
cat reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/state.json
ls -la reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/checkpoints/ | tail -5

# monitor 是否仍在跑
tmux list-sessions | grep lp_base_10u_probe_readiness_monitor_20260602_193517
pgrep -af lp_base_10u_probe_readiness_monitor_v1

# 安全再扫
ps aux | egrep 'canary|lpbot-live|eth_sendRawTransaction|eth_sendTransaction' | grep -v grep || echo "no forbidden processes"
```

## 6. 已知非阻断问题

- `tickSpacing()` selector `0x6b4d3867` 在 armed runner v1 preflight 模式 revert；monitor 改为不读 `tickSpacing`（只看 slot0 + liquidity）。这是已知的 Base V3 池差异，无影响。
- 第一次 checkpoint `fresh_approval_required=true` 属预期（USDC allowance 5 USDC < 10 USDC）。任何 armed runner 真要发，必须先重新做 approveExact；本阶段仍然不签不发。

## 7. 下一动作（本阶段不执行）

明早用户回来后，运行：

```bash
python3 scripts/lp_base_10u_probe_readiness_monitor_v1.py \
  --run-id 20260602_193517 \
  --output-dir reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor \
  --finalize
```

或读：

```bash
cat reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/final_monitor_summary.json
```

根据 `recommended_operator_action` 决定下一步（见 FINAL_MONITOR_SUMMARY_CN.md）。
