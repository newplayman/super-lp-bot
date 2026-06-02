# VPS 本机安全审计

- stage: `LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1`
- phase: M
- run_id: `20260601_185436`
- environment: `vps_local`

## 禁区进程扫描

```text
ps aux | grep -iE 'canary|lpbot-live|lpbot-paper|live-order|live_order|wallet-tx|eth_sendRawTransaction'
→ no_forbidden_processes
```

`backfill|catchup|capture` 信息扫描也无匹配。**当前 VPS 上不存在任何活跃交易进程。**
唯一活跃的相关进程是只读 overnight runner（Phase C 已确认，read-only by contract）。

## 本会话动作汇总

| 维度 | 结果 |
|---|---|
| touched_trading_path | **no** |
| touched_wallet_tx_bridge_live_paper | **no** |
| wallet_or_tx_touched | **no** |
| private_keys_or_keystore_read | **no** |
| production_positions_or_shadow_tables_overwritten | **no** |
| final_verdict_overwritten | **no**（finalizer 走 running 分支，不动 `final/FINAL_VERDICT.json`） |

## 权限状态

```text
edge_proven           = no
tiny_canary_allowed   = no
can_run_probe_now     = no
```

## 文件变更归类

### 工具

- `scripts/finalize_bsc_fee_velocity_overnight_run_v1_readonly.py`（新增）
- `scripts/collect_bsc_fee_velocity_overnight_artifacts.sh`（重写为双模式，无 `--delete`，stale 警告）

### 测试

- `tests/test_finalize_bsc_fee_velocity_overnight_run_v1_readonly.py`（17 个用例）
- `tests/test_collect_bsc_fee_velocity_overnight_artifacts.py`（9 个用例）

### 报告产物

20 份新增 / 修正的报告文件，位于
`reports/lp_bsc_fee_velocity_overnight/20260601_185436/`。

### 仓库根

- `CLAUDE.md`（本会话早期 `/init` 命令产物）

### 同步进入仓库的运行产物

- `checkpoint/state.json`、`checkpoint/hourly_*.json`
- `logs/run.log`
- `data/pool_fee_velocity.csv`、`data/swap_logs_decoded.csv`
- `final/*`（与 /tmp 一致；**不覆盖**，runner 自己写的）
- `scripts/lp_bsc_fee_velocity_overnight_runner.py`、`lp_bsc_fee_velocity_overnight_backfill_v1_readonly.py`（runner 自带，作为 run 资产保留）

均以 `rsync -av`（不带 `--delete`）从 `/tmp/lp_bsc_fee_velocity_overnight_20260601_185436` 同步，
排除本会话已写入的 `VPS_LOCAL_*` / `vps_local_*` / `LOCAL_VPS_*` / `RUN_LOG_*` 等模式，避免互相覆盖。
