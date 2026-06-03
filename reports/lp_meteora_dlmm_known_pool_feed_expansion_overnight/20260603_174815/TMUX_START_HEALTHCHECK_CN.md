# TMUX Start + Healthcheck — Stage C

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`

## 0. tmux session 配置

```text
session_name  = lp_meteora_known_pool_expansion_20260603_174815
log_file      = reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/logs/run.log
checkpoint    = reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/checkpoint/state.json
```

## 1. 启动 (使用 Bash wrapper, 不在 tmux 内嵌)

本 runner 设计为单进程 Node.js（包含全部 stages D–J），不通过 tmux detach 运行，但 wrapper 同样支持 tmux 模式：

```bash
# tmux mode
tmux new-session -d -s lp_meteora_known_pool_expansion_20260603_174815 \
  "cd /opt/lpbot/lp-bot-v3-origin-check && \
   bash scripts/lp_meteora_dlmm_known_pool_feed_expansion_overnight_v1_readonly.sh \
     --run-id 20260603_174815 \
     --output-dir reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815 \
     --max-hours 10 \
     --max-pools 50 \
     --min-pools 20 \
     --mode all 2>&1 | tee -a reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/logs/run.log"

# or background mode (nohup fallback)
cd /opt/lpbot/lp-bot-v3-origin-check
nohup bash scripts/lp_meteora_dlmm_known_pool_feed_expansion_overnight_v1_readonly.sh \
  --run-id 20260603_174815 \
  --output-dir reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815 \
  --max-hours 10 --max-pools 50 --min-pools 20 --mode all \
  > reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/logs/nohup.log 2>&1 &
echo $! > reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/logs/runner.pid
```

## 2. 启动后 smoke check (2 分钟内必须做)

```bash
# 1. tmux session exists (if tmux mode)
tmux has-session -t lp_meteora_known_pool_expansion_20260603_174815
echo $?  # 期望 0

# 2. run.log updating
ls -la reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/logs/run.log
tail -5 reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/logs/run.log

# 3. checkpoint/state.json exists
ls -la reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/checkpoint/state.json
cat reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/checkpoint/state.json | python3 -m json.tool

# 4. no forbidden process
ps aux | egrep 'canary|lpbot-live|solana-keygen|sendTransaction|keypair' | grep -v grep
echo $?  # 期望 1 (no matches)

# 5. no wallet/keypair/transaction artifacts in any output
grep -RE "Keypair\.|sendTransaction|signer|private_key" \
  reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/ \
  | grep -v 'invalid_reason' || true
echo $?  # 期望 1 (no matches)
```

## 3. Forbidden process list

- `canary` / `canary_cycle` / `lpbot-canary`
- `lpbot-live`
- `solana-keygen`
- `solana transfer`
- 任何 `sendTransaction` / `sendRawTransaction` 调用
- 任何 `Keypair.from_secret_key` / `Keypair.generate`
- 任何 `web3.js` / `anchor.rs` / `solana.py` signer 调用

## 4. 状态码

- 0  启动成功
- 1  部分问题（per spec: 仍继续 partial）
- 2  参数错误 (fatal)
- 3  unsafe state (fatal)

## 5. Resume 行为

Runner 检测到 `checkpoint/state.json` 存在且 phase 已推进，会从上一阶段继续执行。这意味着：

- 如果 Stage E 完成后 crash，第二次启动会跳过 D 和 E，直接进入 F。
- 每次启动都会更新 `last_update` 时间戳。
- 不会重复生成已存在的 artifact。
- 不会因为 resume 而丢失数据。

## 6. 下一阶段

进入 Stage D — candidate source collection。
