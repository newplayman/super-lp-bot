# LP Bot PRD v2.1 · M0P 验收报告

**日期：** 2026-08-09

**分支：** `feat/prd-v2.1-m0-shadow`

**范围：** TP-M0P-v1（W6 / P1 / W1 / W3 / W4 / DOC）
**裁决：** **PASS / READY FOR COMMANDER REVIEW**

M0P 修复与只读验收已完成。live scanner 的 NetCover 第五闸已经能够真实计算；本次市场结果仍为 `accepted=0`，没有放宽任何阈值，也没有用默认值填补未知输入。因不存在非空 live-vetted allocation，paper runner 按任务契约未启动；14 天 shadow 与 M1 均未获授权。

## 1. 交付与提交

| FIX | commit | 结果 |
|---|---|---|
| W3 | `a0a43ce` | registry 薄壳断言改为检查 canonical 转发及无本地 redaction 实现 |
| W4 | `4ee3860` | 补齐 4 类 runner 层 hard-risk 退出回归；W2 口径固化 |
| W1 | `e7b30ee` | 仓位闸同时要求 ≥50 unique identities 与 ≥5 root pools；每 root 最多重入 3 次 |
| P1 | `6b381fb` | 标准库只读 panel、配对测试与未安装的 hardened systemd unit |
| W6 | `0541c1f` | NetCover 9 项 USD 输入装配并接入真实 scanner |

## 2. W6 live scanner 与拒绝漏斗

执行了真实 read-only `scanner --once`，归档目录为 `reports/lp_netcover_inputs/20260809_073030/`：

```text
[scanner] screened=734 top=10 resolved=10 scored=10 accepted=0
fully_calculable_netcover_records=1
```

完整可计算样例：

```text
symbol=USDC-VVV
holding_horizon_hours=168
fee_ev_usd=0.06129008219178084
reward_ev_usd=0.0
il_ev_usd=0.9348140139088524
entry_cost_usd=0.15
exit_cost_usd=0.15
gas_usd=0.0795
slippage_usd=0.0013967232710139776
reward_conversion_cost_usd=0.0
exit_latency_loss_usd=0.004794520547945206
netcover_ratio=0.03428025155511409
netcover_gate_status=BELOW_SHADOW
rejection_reason=NETCOVER_BELOW_SHADOW
```

逐池拒绝分布：

```text
NETCOVER_BELOW_SHADOW: 1
NETCOVER_INPUT_MISSING: entry/exit/slippage/reward_conversion: 4
NETCOVER_INPUT_MISSING: fee/reward/IL/entry/exit/slippage/reward_conversion/latency: 4
NETCOVER_INPUT_MISSING: fee/reward/IL/reward_conversion/latency: 1
```

INV-GATE-01 复核：shadow / enter 阈值仍为 `1.0 / 1.5`；没有针对 accepted 数量选宽松 H、仓位或成本，未知深度/价格/波动率仍为 `None` 并 fail-closed。同池同参数的 NetCover、净收益和 absolute-profit 结论与旧 cost-sensitivity 路径一致。

W6 定向验收：

```text
65 passed in 6.57s
```

## 3. panel 端到端 smoke

面板使用运行时随机 token 在临时 `127.0.0.1:18891` 启动；token 未输出、未归档、未写入命令行或报告。curl 摘要：

```text
GET /api/state.json without auth -> 401
GET /api/state.json with X-Panel-Token -> 200
GET / with X-Panel-Token -> 200
POST /api/state.json -> 405
gate_checks=6
initial_funnel=734,10,7,10,0
```

面板保持只读连接期间并发执行 scanner：

```text
[scanner] screened=734 top=1 resolved=1 scored=1 accepted=0
GET /api/state.json after scanner -> 200
post_funnel=734,1,0,1,0
database_status=OK
access_log_lines=6
query_token_logged=false
token_value_logged=false
```

因此面板没有阻塞 SQLite 写入。systemd unit 只落在 `deploy/systemd/`，未安装、未启用。P1 定向测试为 `21 passed`，`py_compile` 与 `systemd-analyze verify` 均通过。

## 4. gate 与 runner 决策

生成的 §12.0 gate 报告位于 `reports/lp_m0p_acceptance/20260809/gate_report.{md,json}`：

```text
overall_status=INSUFFICIENT_EVIDENCE
unique_position_identities=0
unique_root_pools=0
rpc_severe_unresolved=0 (PASS)
其余五项=UNKNOWN
```

live scanner `accepted=0`，所以 exporter 没有非空 live-vetted allocation。依任务包要求，本轮没有启动 runner，也没有用 fixture 冒充 live 证据。14 天 shadow 尚未启动。

## 5. 测试证据

定向回归：

```text
W3 + W4 + exit/runner 相关：142 passed
W1 gate + runner：68 passed
P1 panel：21 passed
W6 scanner + resolver + NetCover + cost sensitivity：65 passed
```

sol 亲跑全量：

```text
$ pytest tests/ --collect-only -q
2761 tests collected in 1.42s

$ pytest tests/ -q
2747 passed, 14 skipped in 54.45s
```

14 个 skip 与 D1 追认的精确 `legacy_environment_bound` nodeid 清单一致；collection error 为 0。

## 6. 红线与发布边界

- 仍为 paper/read-only；未增加钱包、私钥、签名、approve、广播、写交易或付费端点。
- 未修改 Go、`scripts/lp_long_horizon/`、冻结目录 `/opt/lpbot/lp-bot-v3`，未开展 M1-A / M1-B。
- panel 默认监听 `0.0.0.0:8899` 是 D5 明确决策；默认强制 ≥32 字符 env token、GET 白名单、脱敏、限流和只读数据源。正式启动前建议防火墙只放行指挥官固定出口 IP。
- 没有安装 systemd unit、没有推送或合并、没有停止既有 paper runner PID 1349731。
- `/opt/lpbot/` 下重复的 M0R 任务包副本按任务包要求保持不动，仍需由指挥官自行删除。

最终结论：M0P 功能与验收完成，真实漏斗结果已诚实归档。可由指挥官评审后决定是否启动 scanner + RWA collector + panel 的 14 天 shadow；runner 必须继续等待非空 live-vetted allocation。此结论不授权 M1 或任何真钱动作。
