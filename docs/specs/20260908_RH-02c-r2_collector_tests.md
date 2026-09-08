# RH-02c 第二轮：为已上线的采集器补配对测试

## 背景（一段）

`scripts/lp_rh_collector_v1_readonly.py`（327 行）**已经在生产运行**，正在跑 PRD §21.1 Stage A 的 72 小时正向观测（PID 见 `reports/lp_rh/collector.pid`，cron 看门狗每 5 分钟守护）。第一轮 worker 只交付了常量与辅助函数、没有主循环，主脑补完并上线，**配对测试仍然欠着**。本包只补测试，**不许改采集器一行代码**——它正在跑，改了会破坏正在积累的观测。

采集器已验证的真实行为（主脑实测）：链上读到 `dec0=18, dec1=6`；价格 2476–2482 USDG；`kill -KILL` 后看门狗 12 秒拉起。

## 只许新建一个文件

`tests/test_lp_rh_collector_v1_readonly.py`（≤ 250 行），**全部用注入的假 `rpc_fn` callable，绝不联网**，全部用 `tmp_path` 临时库，**绝不碰 `reports/lp_rh/`**（那是活库）。

先用 `grep -n 'def ' scripts/lp_rh_collector_v1_readonly.py` 读出真实签名再写断言，不要猜。关键可注入点：`collect_round(conn, *, dec0, dec1, last_good_block, rpc_fn)`、`run(db_path, *, interval_secs, max_rounds, pid_file, once, rpc_fn)`、`compute_price_human(sqrt_price_x96, dec0, dec1)`、`backoff_seconds(fails, ...)`、`pid_file_is_free(path)`、`read_decimals(token, rpc_fn)`。

至少 12 个测试：

1. **价格精度（本项目最贵的坑）**：`compute_price_human(3953938817749275760872870, 18, 6)` 结果在 `2490.0 ~ 2491.0` 之间；同一 sqrtPrice 用 `(18, 18)` 得到的值 `< 1e-6`。断言两者比值约 `1e12`，注释写明 USDG 是 6 位小数。
2. **T12 JSON-RPC error 不当 0**：假 `rpc_fn` 对 `eth_getBlockByNumber` 返回 `(None, {"code":-32601,"message":"..."}, 12)`，其余正常 → `collect_round` 写入的 `rh_rpc_health.error` 非空、`last_good_block` **等于传入的 `last_good_block`**（保持上次值，不是 0 也不是 None）。
3. 全部方法失败 → `rh_rpc_health.state == "EXIT_ONLY"`；部分失败 → `"DEGRADED"`；全成功 → `"NORMAL"`。
4. 一轮成功后 `rh_market_states` / `rh_rpc_health` / `rh_source_snapshots` **各恰好增加 1 行**。
5. `rh_market_states.reference_mid` 是十进制字符串且可被 `Decimal` 解析；`session` 为 `"UNKNOWN"`；`chain_id` 为 4663。
6. **快照幂等**：连续两轮返回**完全相同**的原始数据 → 第二轮 `rh_source_snapshots` 不增行（IntegrityError 被吞），但 `rh_market_states` 仍增行，且循环不中断。
7. **退避封顶**：`backoff_seconds(2000)` 不抛异常且等于 `backoff_seconds(11)`（指数封顶 `BACKOFF_MAX_EXP=10`）。
8. **pid-file 防双写**：pid 文件写入当前进程 PID → `pid_file_is_free` 为 False；`run(..., pid_file=<该文件>)` 返回 **2**。
9. pid 文件内容是不存在的 PID（如 `999999`）→ `pid_file_is_free` 为 True。
10. **预算闸**：monkeypatch `budget_status` 返回 `{"state":"OVER",...}`，`run` 以 `max_rounds=25` 跑，断言在第 20 轮附近提前退出且**返回码 0**（T57：达预算停采集，不是崩溃）。
11. `read_decimals` 在 RPC 报错时返回 `None`；`run` 在 `token1` decimals 读不到时返回 **3**（拒绝猜精度）。
12. **源码守卫**：读脚本源码断言不含 `drpc`、不含 `import requests`、不含 `web3`；含 `curl/8.5.0`。

## 不许动什么

- **绝不修改 `scripts/lp_rh_collector_v1_readonly.py`**（正在生产运行）、看门狗、状态脚本或任何其它现有文件。
- 不联网、不写 `reports/lp_rh/`、不读 `.env*`、不 import requests/web3。
- 不要用 TaskCreate/TaskUpdate 工具；单次 Write/Edit ≤150 行。

## 验收标准

- [ ] `git status --short` 新增只有 `tests/test_lp_rh_collector_v1_readonly.py`；`git diff --stat` 为空。
- [ ] 新测试 ≥12 个且全绿。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` 0 failed、14 skipped。
- [ ] 跑完测试后 `reports/lp_rh/scanner.db` 的行数**只增不减**（测试没碰活库）。

## 验证命令

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_collector_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
git diff --stat; git status --short | grep -E 'lp_rh_collector'
```
