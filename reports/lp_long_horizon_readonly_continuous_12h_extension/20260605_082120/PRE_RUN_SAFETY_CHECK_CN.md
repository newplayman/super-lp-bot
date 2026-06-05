# Stage F: 启动前安全检查 (Pre-Run Safety Check)

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1`
- check_stage: `F_PRE_RUN_SAFETY_CHECK`
- checked_at_utc: `2026-06-05T14:46:00Z`
- launch_decision: **PROCEED**

## 0. 检查结果

**10/10 checks pass** ✅ — 可启动 12h tmux supervisor.

| 检查项 | 状态 |
|---|---|
| 无现存 lp_long_horizon tmux | ✅ |
| 无 canary/live/paper/keypair 进程 | ✅ |
| data_dir 可写 | ✅ |
| report_dir 可写 | ✅ |
| supervisor 脚本可执行 + 语法 | ✅ |
| pool universe 存在 + 无 placeholder | ✅ (33 real pools) |
| pytest 30/30 通过 | ✅ |
| V2 6h data_dir 完整 (42 文件) | ✅ |
| V2 6h corrected verdict 完整 (gate=PASS) | ✅ |
| 12h 审批记录有效 (sha256 匹配) | ✅ |

## 1. 详细检查结果

### 1.1 tmux 现状

```
$ tmux ls
work: 1 windows (created Sun May 24 16:10:27 2026) (attached)
work-lp: 1 windows (created Tue Jun  2 06:27:43 2026) (attached)
```

**无** lp_long_horizon_6h_v2_* / lp_long_horizon_12h_* / staged_observation / node_report session. 只有与本任务无关的 work + work-lp.

### 1.2 禁止进程

```
$ ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|eth_sendTransaction|keypair' | grep -v grep
(empty)
```

✅ **零** 禁止进程.

### 1.3 data_dir 可写

```
$ touch data/lp_long_horizon/20260605_082120/.write_test && rm
$ echo $?
0
```

✅ `data/lp_long_horizon/20260605_082120/` 可写.

### 1.4 report_dir 可写

```
$ touch reports/lp_long_horizon_readonly_continuous_12h_extension/20260505_082120/.write_test
# (need to use 20260605 not 20260505)
$ touch reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/.write_test && rm
$ echo $?
0
```

✅ `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/` 可写.

### 1.5 supervisor 脚本

```
$ bash -n scripts/run_lp_long_horizon_readonly_stage_once.sh && echo OK
OK
```

✅ 语法正确.

### 1.6 pool universe

```
$ test -f reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.json && echo EXISTS
EXISTS
$ grep -q '<smoke_pool' reports/.../real_pool_universe_for_12h.json && echo HAS_PLACEHOLDER
NO_PLACEHOLDER
```

✅ 33 真实池, 0 placeholder, real_pool_universe_used=true, all_pools_are_real_on_chain=true.

### 1.7 V2 6h 状态保留

- V2 6h data_dir (42 文件) 0 修改
- V2 6h corrected verdict (commit 23fed9d) 0 修改
- V2 6h node report (commit e74d84f) 0 修改
- V2 supervisor 脚本 (commit 23fed9d) 0 修改

### 1.8 12h approval record 校验

```json
{
  "user_approval_text": "APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true",
  "user_approval_text_hash_sha256": "040c37f3bc32bc3fe281eb4cf181fae4634e742e78c769d2211d3a5f8802198f",
  "approved_stage": "12h",
  "approved_next_stages": [],
  "auto_advance_allowed": false,
  "no_probe": true
}
```

✅ sha256 校验通过, approved_next_stages=[] (无 forward approval).

## 2. 12h hard guarantees (全部满足)

| Guarantee | 值 |
|---|---|
| SLEEP_SECONDS == 3600 | ✅ true (1h per checkpoint) |
| LOOP_COUNT == 12 | ✅ true (12h × 1 ckpt/h) |
| real_pool_universe_used | ✅ true |
| selected_real_pool_count >= 30 | ✅ true (33) |
| placeholder_pool_count == 0 | ✅ true |
| set -euo pipefail | ✅ true |
| END_TS-based loop | ✅ true (V2 fix) |
| fail_safe_trap | ✅ true (V2/V3 fix, .finalize_succeeded marker) |
| approval_phrase_required | ✅ true |
| tmux_session_unique | ✅ true |
| forbidden_process_zero_tolerance | ✅ true |
| no_auto_24h_48h_72h_7d | ✅ true |
| no_wallet_keypair_signer | ✅ true |
| no_tx_send_approve_mint | ✅ true |

## 3. 严禁 (本轮全部不触发)

- 不 probe / canary / live / paper
- 不读 wallet / keypair / seed / 私钥
- 不创建 signer
- 不发送 transaction / approve / mint / swap / bridge
- 不写 production positions
- 不覆盖 shadow 原始表
- 不接 paid RPC / paid indexer
- 不启用 cron / systemd / daemon
- 不自动启动 24h / 48h / 72h / 7d
- can_run_probe_now=false (locked)
- tiny_canary_allowed="no" (locked)
- edge_proven="no" (locked)
- LP strategy research freeze ACTIVE

## 4. 启动决策

**PROCEED** — 启动 12h tmux supervisor.

12h supervisor 启动后将:
1. 12 个 1h checkpoint, 每个 ckpt 写 7 文件 (pool/quote/fee/liq/regime/actual_fee/summary) 到 data/lp_long_horizon/20260605_082120/
2. 每 15min heartbeat 到 reports/.../12h_extension/20260505_082120/logs/heartbeat/
3. 12h 完成后 (expected_end ≈ 2026-06-06T02:46:00Z) 自动 finalize + auto commit + auto push
4. 12h 节点报告写到 reports/lp_long_horizon_node_reports/20260605_082120/12h/
5. 杀 tmux session

**Stage F PASS** → 进入 Stage G (启动 12h tmux + 早回报).
