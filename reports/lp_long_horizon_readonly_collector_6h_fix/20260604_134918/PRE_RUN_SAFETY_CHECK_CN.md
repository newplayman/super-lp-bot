# Stage F — 启动前安全自检 (Pre-Run Safety Check)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1`
- run_id: `20260604_134918`

## 0. 检查结果

**PASS** — 全部 8 项自检通过, 可启动 tmux session.

## 1. 自检项 (8 项)

### 1.1 tmux session 唯一性

```
$ tmux ls 2>/dev/null | grep 'lp_long_horizon' || echo "(no existing)"
(no existing lp_long_horizon tmux session)
```

✅ **PASS** — 没有已有 lp_long_horizon tmux session, 不会触发 duplicate_collector_process
abort (exit 7).

### 1.2 canary / live / paper 进程

```
$ ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|eth_sendTransaction|keypair' | grep -v grep
(no forbidden process)
```

✅ **PASS** — 没有 canary / live / paper / sendTransaction / keypair 进程.

### 1.3 wallet / signer 进程

```
$ ps aux | egrep 'wallet|keypair|signer|signTransaction|sendTransaction' | grep -v grep
(no wallet/keypair process)
```

✅ **PASS** — 没有 wallet / signer / keypair 进程.

### 1.4 数据目录可写

```
DATA_DIR=data/lp_long_horizon/20260604_134918
$ [[ -d "$DATA_DIR" && -w "$DATA_DIR" ]] && echo "[ok] writable"
[ok] writable
$ touch "$DATA_DIR/.write_test" && rm "$DATA_DIR/.write_test" && echo "[ok] write test passed"
[ok] write test passed
```

✅ **PASS** — `data/lp_long_horizon/20260604_134918/` 存在且可写.

### 1.5 报告目录可写 (6h_run)

```
REPORT_DIR=reports/lp_long_horizon_readonly_collector_6h_run/20260604_134918
$ [[ -d "$REPORT_DIR" && -w "$REPORT_DIR" ]] && echo "[ok] writable"
[ok] writable
$ touch "$REPORT_DIR/.write_test" && rm "$REPORT_DIR/.write_test" && echo "[ok] write test passed"
[ok] write test passed
```

✅ **PASS** — `reports/lp_long_horizon_readonly_collector_6h_run/20260604_134918/` 存在且可写.

### 1.6 报告目录可写 (6h_fix, Stage A 报告)

```
FIX_DIR=reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918
$ [[ -d "$FIX_DIR" && -w "$FIX_DIR" ]] && echo "[ok] writable"
[ok] writable
```

✅ **PASS** — `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/` 存在且可写.

### 1.7 collector help 可执行

```
$ python3 scripts/lp_long_horizon_readonly_collector_v1.py --help
usage: lp_long_horizon_readonly_collector_v1.py [-h] [--mode MODE]
                                                [--pools-per-protocol POOLS_PER_PROTOCOL]
                                                [--out OUT] [--no-wallet]
                                                [--no-tx] [--no-bridge]
                                                [--dry-run]
```

✅ **PASS** — collector `--help` 返回 0, 7 个 flags 全部正常.

### 1.8 supervisor 脚本可执行 + approval record 存在

```
$ ls -la scripts/run_lp_long_horizon_readonly_6h_once.sh
-rwxr-xr-x 1 root root 27580 Jun  4 15:57 scripts/run_lp_long_horizon_readonly_6h_once.sh

$ ls -la reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/MANUAL_APPROVAL_RECORDED.json
-rw-r--r-- 1 root root 2217 Jun  4 15:52 .../MANUAL_APPROVAL_RECORDED.json
```

✅ **PASS** — supervisor 脚本可执行 (rwxr-xr-x), approval record 存在.

## 2. supervisor 脚本 hard guard (Stage E 实装)

supervisor 启动时**hard reject**:
- `SLEEP_SECONDS < 3600` → exit 8 (short mode forbidden)
- `LOOP_COUNT != 6` → exit 9 (override forbidden)
- approval phrase mismatch → exit 11
- existing tmux session → exit 13
- forbidden process detected → exit 14
- unwritable data dir → exit 15
- unwritable report dir → exit 16

任何一项失败, supervisor 立即 exit, 写 supervisor.log 标注, **不**进 tmux session.

## 3. 关键确认

- [x] 没有已有 lp_long_horizon 采集 tmux
- [x] 没有 canary / live / paper 进程
- [x] 没有 wallet / keypair 进程
- [x] 数据目录可写 (data/lp_long_horizon/20260604_134918/)
- [x] 报告目录可写 (6h_run + 6h_fix)
- [x] collector help 可执行
- [x] supervisor 脚本可执行 + approval record 存在
- [x] supervisor 脚本 hard guard 实装 (SLEEP_SECONDS=3600 + LOOP_COUNT=6 强制)

## 4. 结论

**8/8 自检项全部 PASS**. Stage F 通过. 进入 Stage G (启动真实 6h tmux + smoke check + 早回报).
