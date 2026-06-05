# Stage A: 当前 V2 在轨保护审计 (Read-only)

- stage: `LP_CONTINUOUS_STAGED_OBSERVATION_AND_COVERAGE_REPORT_V1`
- audit_at_utc: `2026-06-05T08:20:58Z`
- operator: agent (只读, **不** kill / **不** restart / **不** 并行 collector)

## 0. 目的

确认本轮 (Stage A → L) 不会以任何方式干扰当前正在 VPS 后台跑的 V2 6h real wallclock collector (`20260605_043726`).

V2 状态: **HEALTHY_RUNNING**, 4/6 checkpoints 已写, 预计 2026-06-05T10:51:29Z 自动 finalize.

## 1. 保护断言

| 断言 | 值 |
|---|---|
| `current_v2_not_touched` | ✅ **true** |
| `no_restart` | ✅ **true** |
| `no_parallel_collector` | ✅ **true** |
| `no_kill` | ✅ **true** |
| `no_modify_supervisor` | ✅ **true** |
| `no_modify_collector` | ✅ **true** |
| `no_modify_data_files` | ✅ **true** (V2 数据将持续原样累积) |
| `no_modify_checkpoint_files` | ✅ **true** |
| `no_modify_final_verdict` | ✅ **true** (V2 6h 后会自动写 FINAL_VERDICT, 本轮不预写) |
| `no_manual_finalize` | ✅ **true** |
| `no_commit_to_v2_dir` | ✅ **true** (本轮 commit 仅触及新 report_dir / scripts / tests) |
| `no_new_tmux_session_for_v2` | ✅ **true** |
| `no_new_tmux_session_for_observation` | ✅ **true** (本轮只设计 reporting, **不**启动 collector) |
| `no_cron_systemd_daemon` | ✅ **true** |
| `no_probe_canary_live_paper` | ✅ **true** |
| `no_wallet_keypair_signer` | ✅ **true** |
| `no_tx_send_approve_mint` | ✅ **true** |
| `no_paid_rpc_indexer` | ✅ **true** |
| `can_run_probe_now` | ✅ **false** (locked) |
| `tiny_canary_allowed` | ✅ **"no"** (locked) |
| `edge_proven` | ✅ **"no"** (locked, 与 freeze 一致) |

## 2. V2 进程实证

| 项 | 值 |
|---|---|
| tmux session | `lp_long_horizon_6h_v2_20260605_043726` (1 window, created `Fri Jun  5 06:51:15 2026`) |
| supervisor PID | `3872268` |
| supervisor ELAPSED | `03:29:40` (3h29m40s) |
| supervisor STAT | `S` (sleeping in 1h sleep — 正常状态) |
| supervisor PPID | `1` (nohup-detach, 与本 agent session 隔离) |
| supervisor cmd | `bash scripts/run_lp_long_horizon_readonly_6h_once.sh 20260605_043726` |

## 3. V2 数据累积

| ckpt dir | 时间 (local) | 状态 |
|---|---|---|
| `checkpoint_1_0451` | 06:51 | ✅ 已写 7 文件 |
| `checkpoint_2_0551` | 07:51 | ✅ 已写 7 文件 |
| `checkpoint_3_0651` | 08:51 | ✅ 已写 7 文件 |
| `checkpoint_4_0751` | 09:51 | ✅ 已写 7 文件 |
| `checkpoint_5_0851` | 10:51 待写 | ⏳ V2 仍在 sleep 中 |
| `checkpoint_6_0951` | 11:51 待写 | ⏳ (V2 supervisor 期望 6h 实际 wallclock) |
| **END_TS** | **12:51:29Z = 10:51:29Z** | ⏳ supervisor 将在 ckpt_5 + ckpt_6 完成后, sleep REMAINING 直到 END_TS, 然后进入 finalize 块 |

注意: V2 supervisor 用 END_TS-based loop, 实际 wallclock = 6h, 不会因任何"提前结束"bug 漏掉 sleep. V1 的两个 bug 都已修.

## 4. tmux 现状

- `lp_long_horizon_6h_v2_20260605_043726`: **1 window, alive** (V2 tail)
- `work`: 1 window attached (V2 启动前已存在, 与本轮无关)
- `work-lp`: 1 window attached (V2 启动前已存在, 与本轮无关)

**本轮未启动任何新 tmux session**.

## 5. 禁止进程 (forbidden process) 检查

```
ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|eth_sendTransaction|keypair' | grep -v grep
→ (空) ✅ 无禁止进程
```

## 6. 范围声明 (本轮 A→L)

| 允许 | 禁止 |
|---|---|
| 设计 continuous staged observation spec | 启动 V3 / 12h / 24h / 72h / 7d 新 run |
| 新增 / 修改 reporting 脚本 (本轮新脚本**不**影响 V2 supervisor 行为) | 修改 V2 supervisor (`scripts/run_lp_long_horizon_readonly_6h_once.sh`) |
| 新增 coverage manifest spec | 修改 V2 collector (`scripts/lp_long_horizon_readonly_collector_v1.py`) |
| 新增 fee estimation explanation report | 写 V2 data_dir / V2 report_dir / V2 FINAL_VERDICT |
| 新增 node report schema + generator | commit V2 数据 (本轮 commit 仅触及新 report_dir / scripts / tests) |
| 新增 range/tick/bin sensitivity spec | kill V2 supervisor / tmux |
| 新增 pytest 验证本轮 schemas | 启动 daemon / cron / systemd |
| git add 本轮新文件, commit + push | probe / canary / live / paper |
| | 读 wallet / keypair / signer / 私钥 |
| | 发送 transaction / approve / mint / swap / bridge |
| | 接 paid RPC / paid indexer |

## 7. 结论

V2 在轨保护断言全部成立. V2 在 VPS 后台独立跑 6h, 本轮 (Stage A→L) 完全在其外部做"连续观察 + 节点报告 + 覆盖范围"的设计与实现, 不会触碰 V2 任何状态.

**Stage A PASS** → 进入 Stage B (输入证据审计).
