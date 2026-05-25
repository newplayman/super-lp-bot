# Base Canary 运维 Runbook

更新时间：2026-05-23

目标：
- 把 Base canary 的“检查、执行、观测、退出”收成固定入口
- 降低手工拼命令造成的误操作

## 1. 前置条件

- 已存在 `.env.postgres`
- 已存在 `.env.canary`
- 二进制可执行：`./bin/lpbot-live`
- 配置文件默认：`configs/config.canary.toml`

默认脚本都会自动加载：
- `.env.postgres`
- `.env.canary`

## 2. 只做安全 readiness，不广播交易

命令：

```bash
scripts/canary_readiness_report.sh
```

作用：
- 校验 `POSTGRES_DSN/DATABASE_URL`
- 校验 binary / config 是否存在
- 运行 `--canary-preflight`
- 默认不广播 mint / exit
- 结束后直接打印最近 canary event / open position / 可选 exit preflight 摘要

如果要额外验证某个已存在 NFT 的退出预估：

```bash
LPBOT_CANARY_RUN_EXIT_PREFLIGHT=YES \
LPBOT_CANARY_TOKEN_ID=<token_id> \
scripts/canary_readiness_report.sh
```

## 3. 跑一轮 Base canary 闭环

命令：

```bash
LPBOT_CONFIRM_CANARY_CYCLE=YES \
scripts/canary_cycle.sh
```

默认行为：
- `preflight`
- `prepare`
- `mint`
- `reconcile_mint`
- `exit_preflight`
- 默认不广播 `exit`
- 结束后直接打印最近仓位、事件、退出预估摘要

如果要同一轮里把退出也广播：

```bash
LPBOT_CONFIRM_CANARY_CYCLE=YES \
LPBOT_CANARY_CYCLE_EXIT=YES \
scripts/canary_cycle.sh
```

## 4. 只做退出

已知 `token_id` 时：

```bash
LPBOT_CONFIRM_CANARY_EXIT=YES \
./bin/lpbot-live --config=configs/config.canary.toml --canary-exit --token-id=<token_id>
```

只做退出预估：

```bash
./bin/lpbot-live --config=configs/config.canary.toml --canary-exit-preflight --token-id=<token_id>
```

## 5. 观测入口

- Dashboard：`http://<vps-ip>:9090/?token=<DashboardToken>`
- Prometheus metrics：`http://<vps-ip>:9092/metrics`

### 5.1 期望/实现利润差异证据（建议每次 cycle 后补跑）

```bash
scripts/canary_profitability_evidence.sh
```

可选参数（环境变量）：

```bash
LPBOT_CANARY_EVIDENCE_WINDOW_HOURS=168 \
LPBOT_CANARY_EVIDENCE_ROW_LIMIT=50 \
LPBOT_CANARY_EVIDENCE_POOL_ID=<pool_id> \
LPBOT_CANARY_EVIDENCE_OUTPUT=run/audits/xxx.md \
./scripts/canary_profitability_evidence.sh
```

输出字段主要用于对账：

- `preflight_expected_net_usd` 与 `realized_net_usd`
- `net_error_usd`
- 费用拆分（`fee/il/swap/gas/slippage`）
- 预估/关闭相关 tx 与最新事件

### 5.2 关闭/开启 cycle 后自动证据

`scripts/canary_cycle.sh` 默认会自动执行一次 `scripts/canary_profitability_evidence.sh`（窗口默认 168 小时）。

可用环境变量：

- `LPBOT_CANARY_RUN_EVIDENCE=NO`：关闭自动执行
- `LPBOT_CANARY_EVIDENCE_GATE=YES`：开启门禁风控阈值
- `LPBOT_CANARY_MAX_AVG_NET_ERROR_USD=<abs>`
- `LPBOT_CANARY_MAX_TOTAL_NET_ERROR_USD=<abs>`
- `LPBOT_CANARY_MAX_MISSING_LEDGER_ROWS=<abs>`
- `LPBOT_CANARY_EVIDENCE_WINDOW_HOURS=168`
- `LPBOT_CANARY_EVIDENCE_ROW_LIMIT=50`
- `LPBOT_CANARY_EVIDENCE_POOL_ID=<pool_id>`

重点看：
- `base_canary.opened / closed`
- `base_canary.active_token_id`
- `positions`
- `position_marks`
- `exit_preflights`
- `transactions`

## 6. 失败时怎么看

### mint 失败

看：
- `canary_preflight`
- `canary_prepare`
- `canary_mint`
- `transactions`

常见原因：
- 余额不足
- allowance 不足
- pool gate / quality gate 拦截
- rpc / gas / broadcast 失败

### close / collect / rebalance 失败

现在 live canary-safe 路径会把失败状态写成：
- `exit_failed`
- `rejected`

看：
- `positions.status`
- `transactions.status`
- dashboard 的 `execution flow`

## 7. 当前统一入口

- 安全 readiness：`scripts/canary_readiness_report.sh`
- 闭环执行：`scripts/canary_cycle.sh`
- 环境装载包装：`scripts/run_canary_with_env.sh`
- 收益审计：`scripts/canary_profitability_evidence.sh`

原则：
- 先 `readiness`
- 再 `cycle`
- 再看 dashboard / metrics / db 结果
