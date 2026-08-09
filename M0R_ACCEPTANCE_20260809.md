# LP Bot PRD v2.1 · M0R 最终复验报告

**日期：** 2026-08-09

**分支：** `feat/prd-v2.1-m0-shadow`

**任务包：** `TP-M0R-v1`

**裁决：** **PASS — READY FOR COMMANDER LAUNCH**

本裁决只确认 M0 paper/read-only 修复轮满足启动 14 天 shadow 的代码与证据前置条件。它不表示 shadow 已启动，不表示 §12.0 gate 已通过，也不授权 M1-A/M1-B 或任何真钱动作。

## 1. 修复范围与提交

| 修复项 | 提交 | 复验结论 |
|---|---|---|
| FIX-R1 | `792663e` | 五类 hard risk signal 在 `exit_policy_enabled=False` 时仍执行 paper 退出；soft signal 仍只记录 |
| FIX-R2 | `25f9e94` | cooldown reentry 接入 runner；时间、身份、regime、NetCover 与 absolute-profit 证据全部 fail-closed；重入创建新仓/新基线 |
| FIX-R3 | `59fcee4` | Solana 双 registry 退役为 canonical registry 的薄兼容层；live probe 归档 |
| FIX-D2 | `5b92e1f` | 新增只读 RWA collector、配对测试与锁死 systemd unit |
| FIX-DOC | `42c79da` | D1-D4、RWA 启动命令、M1 `1 × 50–60U`、REGULAR cent-units TODO 收口 |

提交前缀符合任务包约定；工作分支未合并、未推送。

## 2. 定向复验

| 范围 | 结果 |
|---|---|
| R1 policy/replay/runner | `59 passed` |
| R2 runner + exit + shadow gate + Solana + attribution | `111 passed` |
| R3 canonical registry / RpcPool / Solana connector | `96 passed` |
| D2 RWA anchors/session/collector/scanner | `81 passed` |
| DOC allocator | `16 passed`；49U=`below_min`，50U 达到 M1 最低仓位标记 |

防御退出官方 replay 位于 `reports/lp_defensive_exit_replay/20260809_m0r_acceptance/`，结果 **7/7 PASS**。

Solana 免费公共 RPC probe 位于 `reports/lp_rpc_pool_probe/20260809_053427/probe_solana.txt`：**6/6 UP**（其中 3 个端点同时支持全部已探测 heavy methods），SHA-256：

```text
14851121ab28874699a83504f77c837ff9d2a575508650b329818f7d9cebcd61
```

## 3. 全量回归

```text
pytest tests/ --collect-only -q
2708 tests collected in 1.75s

pytest tests/ -q
2694 passed, 14 skipped in 37.29s
```

collect 0 error。14 个 skip 均为 D1 追认的 `legacy_environment_bound` 精确 nodeid；没有新增 skip、整文件 ignore 或把 skip 冒充 pass。

## 4. `--once` 完整只读集成链

证据根目录：`reports/lp_m0r_acceptance/20260809/`。

### 4.1 scanner

默认完整 live funnel 使用免费 Base 公共 RPC，结果：

```text
screened=735 top=10 resolved=10 scored=10 accepted=0 sessions=0
rpc_health=DEGRADED
vetted_menu exported=0 invalid=0
```

SQLite 写入 `pool_snapshots=735`、`opportunity_scores=10`。公共 RPC 降级时 scanner 如实告警并保持 `accepted=0`；`vetted_menu_live.json` 是空数组，没有绕过 gate 生成 allocation。

### 4.2 RWA collector

RWA collector 在同一 SQLite 执行一次真实公共读取：

```text
symbols=5 available_anchors=8 available_dex_quotes=5 market_session_rows=20
market_session=PRIMARY_CLOSED: 20
```

- 5 个 Raydium quote 均可用。
- 周末 xStocks 官方锚 5/5 显式记录为 `unavailable`，没有静默空值。
- Bybit 3/5 可用、2/5 unavailable。
- Robinhood 5/5 留作发行方状态/lead 证据，`basis_bps` 5/5 为 SQL NULL，符合 INV-RWA-01，不产生跨发行商 basis。
- `CRCLx/NVDAx/QQQx/SPYx/TSLAx` 各写入 5 条 JSONL 明细。

### 4.3 runner 1-tick

live scanner 本轮 0 accepted，因此没有把 live 链路伪装成可分配。为验证 runner/SQLite 的机械接线，单 tick 明确使用历史审计 fixture：

```text
input=reports/lp_m0_integration_smoke/20260808_sol_acceptance/allocation_fixture/allocation.json
classification=fixture_only_not_live_vetted
chain=base ticks=1 rpc_health=NORMAL pools=1
shadow_positions=1 (unique source_run + position_identity)
portfolio_nav_usd=100.0 portfolio_net_usd=0.0
```

这个 fixture **不得**作为 14 天 shadow 的启动 allocation。指挥官启动时必须使用后续 live-vetted、人工批准且非空的 allocation；若仍为 0 accepted，应继续 fail-closed 等待。

## 5. 红线与范围审计

- `0ca5354..HEAD` 的改动只涉及 M0R 指定 Python、测试、文档、systemd unit 与报告。
- 未修改 Go、`scripts/lp_long_horizon/`、冻结目录 `/opt/lpbot/lp-bot-v3`，未停止既有只读长跑进程。
- 未新增钱包、私钥、助记词、签名器、approve、交易构造、广播或写 RPC 路径。
- 未新增付费端点、API key、明文 token/chat 或其他凭据。
- 未开始 M1-A TS sidecar 或 M1-B Base EVM 执行。
- Telegram 未注入真实凭据，本轮按设计降级 stdout；首条真实推送应由指挥官在启动时通过环境变量验证，任何值不得进入仓库或日志。

## 6. 启动边界与剩余事项

1. **14 天 shadow 尚未启动。** 指挥官 review 本报告后，按 `HANDOFF_M0_READY_CN.md` §2 启动 scanner、RWA collector 与批准的 paper runner。
2. **§12.0 当前仍 FAIL / evidence pending。** 14 天、50 unique positions、fee error、正净 PnL、DD 与 RPC incident gate 必须等待真实 shadow 数据。
3. **FIX-R4 不属于本次启动阻塞项。** 按任务包在 shadow 第 1 周取得真实 breach/退出轨迹后执行；不得用合成轨迹冒充。
4. **M1 仍 NOT AUTHORIZED。** 合并、推送、M1 gate 评审与真钱放行均由指挥官决定。
