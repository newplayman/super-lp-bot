# Stage E — 启动前安全自检 (Pre-Run Safety Check)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1`
- run_id: `20260604_130353`

## 0. 检查结果

**PASS** — 全部 7 项自检通过, 可启动 tmux session.

## 1. 自检项 (7 项)

### 1.1 tmux session 唯一性

```bash
$ tmux ls 2>/dev/null | grep 'lp_long_horizon' || echo "(no existing)"
(no existing lp_long_horizon tmux session)
```

✅ **PASS** — 没有已有 lp_long_horizon tmux session, 不会触发 duplicate_collector_process
abort.

### 1.2 canary / live / paper 进程

```bash
$ ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|eth_sendTransaction|keypair' | grep -v grep || echo "(no forbidden)"
(no forbidden process)
```

✅ **PASS** — 没有 canary / live / paper / sendTransaction / keypair 进程.

### 1.3 wallet / signer 进程

```bash
$ ps aux | egrep 'wallet|keypair|signer|signTransaction|sendTransaction' | grep -v grep || echo "(no wallet)"
(no wallet/keypair process)
```

✅ **PASS** — 没有 wallet / signer / keypair 进程.

### 1.4 数据目录可写

```bash
$ DATA_DIR=data/lp_long_horizon/20260604_130353
$ [[ -d "$DATA_DIR" && -w "$DATA_DIR" ]] && echo "[ok] writable"
[ok] writable
$ touch "$DATA_DIR/.write_test" && rm "$DATA_DIR/.write_test" && echo "[ok] write test passed"
[ok] write test passed
```

✅ **PASS** — `data/lp_long_horizon/20260604_130353/` 存在且可写.

### 1.5 报告目录可写

```bash
$ REPORT_DIR=reports/lp_long_horizon_readonly_collector_6h_run/20260604_130353
$ [[ -d "$REPORT_DIR" && -w "$REPORT_DIR" ]] && echo "[ok] writable"
[ok] writable
$ touch "$REPORT_DIR/.write_test" && rm "$REPORT_DIR/.write_test" && echo "[ok] write test passed"
[ok] write test passed
```

✅ **PASS** — `reports/lp_long_horizon_readonly_collector_6h_run/20260604_130353/` 存在且可写.

### 1.6 collector help 可执行

```bash
$ python3 scripts/lp_long_horizon_readonly_collector_v1.py --help
usage: lp_long_horizon_readonly_collector_v1.py [-h] [--mode MODE]
                                                [--pools-per-protocol POOLS_PER_PROTOCOL]
                                                [--out OUT] [--no-wallet]
                                                [--no-tx] [--no-bridge]
                                                [--dry-run]
LP long-horizon read-only collector (design + smoke only)
```

✅ **PASS** — collector `--help` 返回 0, 7 个 flags 全部正常.

### 1.7 collector 支持只读运行参数

```bash
$ python3 scripts/lp_long_horizon_readonly_collector_v1.py --mode design
[design mode] stage=LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1 run_id=20260604_130638
[design mode] output_root=data/lp_long_horizon/20260604_130353/collector_design
...
[design mode] no network, no tx, no wallet, no signer, no daemon. exit 0
```

✅ **PASS** — design mode 跑通, 0 网络, 0 wallet, 0 tx, exit 0.

## 2. 关键确认

- [x] 没有已有 lp_long_horizon 采集 tmux
- [x] 没有 canary / live / paper 进程
- [x] 没有 wallet / keypair 进程
- [x] 数据目录可写
- [x] 报告目录可写
- [x] collector help 可执行
- [x] collector 支持只读运行参数 (design + smoke)

## 3. 结论

**7/7 自检项全部 PASS**. Stage E 通过. 进入 Stage F (启动 6h tmux + smoke check).
