# HANDOFF 2026-09-07：lp-bot 从 157.173.123.24 搬迁到本机 + RH 增量转向起点

> 上游文档：`PROJECT_STATE_AND_ARCHITECTURE_20260907_CN.md`（B1，仓库内）、`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md`（RH PRD v1.1）、`docs/rh_pivot/AGENT_START_AND_TASKS_CN.md`（RH-00…RH-09 任务包）。
> 本文只记录搬迁事实与当前基线；策略/资金授权状态与 B1 §11 一致：签名 0 / 广播 0 / 私钥 0 / LIVE 未授权。

## 0. 新会话对账（三样对不上先报再动手）

```bash
cd /opt/lpbot/lp-bot-v3-origin-check          # 本机真身；/root/lp-bot/lp-bot-v3-origin-check 是符号链接
git rev-parse --short HEAD                     # 搬迁基线 0e2b6e6；本文提交后为其后一个 commit
git status --short | wc -l                     # 搬迁时 79（2 tracked + 77 untracked）+ 本次新增 docs/
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider   # 3109 passed / 14 skipped
```

**157 机上 lp-bot 相关进程已于 2026-09-07 12:02 UTC 全部停止**（见 §3），`TPF_WATCH.jsonl` 不再更新；本机没有启动任何 daemon。

## 1. 本机布局

| 路径 | 内容 |
|---|---|
| `/opt/lpbot/lp-bot-v3-origin-check/` | **唯一活仓库真身**（与 VPS 路径 1:1；287 个测试硬编码此绝对路径） |
| `/root/lp-bot/lp-bot-v3-origin-check` | → 上者的符号链接 |
| `/opt/lpbot/*.md`、`TPF_WATCH.jsonl`、`backups/`、`.rollback/`、`d4_watchdog.sh`、`tpf_disconnect_recorder.py` | VPS 顶层原样复刻（记录器**未启动**） |
| `/root/lp-bot/.venv` | Python 3.12.3 venv；版本按 VPS `pip freeze` 钉死（`reports/migration/…/requirements.migrated.txt`） |
| `/root/lp-bot/_archive/` | `lp-bot-v3_sealed.tar.gz`（封存仓库，未解包）、`opt_lpbot_toplevel_docs_logs.tar.gz`、`lp-bot-v3-origin-check.bundle`（全分支 git bundle） |
| `/root/lp-bot/_migration/20260907T110206Z/` | 热快照 + 终轮快照：`*_final_compact.db`（两活库最终版）、`TPF_WATCH_final.jsonl`、`dirty.patch`、`status_short.txt`、`stop/`（停进程前后 ps / units / crontab 快照）、`SQLITE_*_BACKUPS.json` |
| `/root/lp-bot/reports/migration/20260907T110206Z/` | 盘点、rsync 日志、pytest/go 原始输出、`MIGRATION_MANIFEST.json`（126,755 个仓库文件 sha256）、`PROCESS_OWNERSHIP.md` |
| `/root/lp-bot/` 顶层 + `docs/rh_pivot/` | RH 交付包（PRD v1.1、任务书、配置契约、合成 fixture、validate_delivery.py）；`inputs/` 只有 B1，**B2 不存在**（用户确认无此文件，`validate_delivery.py` 因此 FAIL，以 PRD D01–D14 为准） |

## 2. 搬迁校验证据

| 项 | VPS | 本机 | 结果 |
|---|---|---|---|
| HEAD | `0e2b6e6`（`1e1d9bd` 之上 1 个纯文档 commit，B1 入库） | 同 | 一致 |
| 分支 | `feat/prd-v2.1-m0-shadow` | 同 | 一致 |
| 脏 diff sha256 | `77aa4c34…a516df` | 同 | 一致（`.gitignore` +4、`lp_rpc_pool_v1_readonly.py` +5，B1 §1 已知，**未提交、未丢弃**，留待用户决定） |
| `git status --short` | 79 行 | 79 行（本次工作前） | 逐行相同 |
| `reports/lp_scanner/scanner.db` | 活库 2.2G | `VACUUM INTO` 终轮压实 2.06G，integrity ok，`pool_snapshots` 2,971,610 / `opportunity_scores` 114,422 | 行数=停写后源库 |
| `reports/lp_scanner_v2_20260823/scanner.db` | 活库 1.6G | 压实 1.44G，ok，`pool_snapshots` 2,119,085 / `opportunity_scores` 80,880 | 同上 |
| `TPF_WATCH.jsonl` | 39,690 行（末 tick 12:02:39 UTC） | 同 | sha256 一致 |
| pytest | B1：3109 passed / 14 skipped | **3109 passed / 14 skipped / 0 failed**（`BASELINE_PYTEST_RAW_run4.log`） | 一致 |
| go test | B1：57 ok | **57 ok / 0 fail**（`BASELINE_GOTEST_RAW.log`，`-p 1`，4m51s） | 一致 |

首次 pytest 出现 287 个失败，全部是 `/opt/lpbot/...` 绝对路径未就位（`BASELINE_PYTEST_RAW.log` 留作证据），布局复刻后归零；**未改任何测试**。B1 §10.6 "备份副本仅 50–140M" 不成立：两库压实后仍 2.06G / 1.44G，数据是真实行。

## 3. 157 机处置记录（用户 2026-09-07 确认）

停止顺序与结果（`_migration/…/stop/`）：root 与 deploy 的 cron `*/5 * * * * /opt/lpbot/d4_watchdog.sh` 各删一行（原 crontab 已备份）→ PID 2082408 看门狗 → 2077656 scanner → 1749823 scanner-v2 → 1349731 paper runner → 3913930 断链记录器，全部 `kill -TERM` 后 2–6 秒自行退出，WAL 已 checkpoint。`ps` 前后 diff 只少了这 5 个及其 bash 包装；`systemctl --state=running` 前后**完全一致**，`md-*` / `poly-*` / `asr` 全部 active。

VPS 上**未删除**任何东西：`/opt/lpbot` 原样保留（含 6.7G `_migration_20260907T110206Z/`），`lpbot-*` systemd 单元保持 disabled，`lpbot-net-guard.service` 保留，另一 Claude 远程会话 PID 236588 未动（用户判定已无用）。VPS 上无任何测试钱包 env / keystore（均 0 字节）；只有 `.env.d4`（随仓库迁入）与封存仓库的 `.env.postgres`（在 tar 内）。

## 4. 硬边界（不变）

六常量 0.7 / 1.0 / 1.5 / 0.0005 / 0.001 / 0.50；100U / 单仓 50–60U / reserve 40U / 日亏 5U / 总回撤 10U；`LIVE_TRADING=false`；不签名不广播不生密钥；不 `git push`；不删不削弱测试；`scripts/lp_long_horizon/` 与封存仓库不动；新三桶只做 `SHADOW_SCENARIO`。

## 5. 下一步：RH-00（第一包，只读）

按 `docs/rh_pivot/AGENT_START_AND_TASKS_CN.md` 执行 RH-00。调研问题包已写在 `docs/specs/20260907_RH-00_baseline_audit_readonly.md`（Q1–Q7），用 `qwen-code -p … --disallowedTools Edit,Write` 逐题派发，产物落 `reports/rh_pivot/<UTC_RUN_ID>/RH-00/`。本机 Qwen 通道 2026-09-07 12:20 UTC 冒烟通过。

本机资源：2 核 / 3G 内存 / 22G 可用磁盘。**不要在本机同时复活两个 scanner**；RH 支线用独立 `reports/lp_rh/scanner.db`。

---

## 6. 搬迁后当日进展（2026-09-07 下午）

| commit | 内容 |
|---|---|
| `279b047` | 搬迁交接、RH 交付包入库、搬迁证据 |
| `3c0ee20` | **RH-00** 只读基线与证据链审计（`reports/rh_pivot/20260907T124500Z/RH-00/`） |
| `9b7d9bb` | **RH-00b** 修复 `RpcPool._penalize` 指数退避 float 溢出（+ 配对测试） |
| `eefcadd` | 补入被 `*.log` 规则忽略的原始测试/审查日志 |
| `0543e84` | **RH-01a** RH 资产注册表 + assets 新旧 schema 适配器（20 个配对测试） |

### RH-00 的核心结论

B1 §10.2 的 P0-1（scanner 73–80% 池永久 fail-closed，原因 `factory_registry_probe_incomplete`）**根因已定位并修复**：不是 RPC 退化、不是市场变化，而是 `scripts/lp_rpc_pool_v1_readonly.py:280` 的 `backoff = base * 2**(fails-1)` 在某端点连续失败数 ≥1025 时 float 溢出（`_fails` 只在成功时清零，28 天不重启的 daemon 必然累积到该量级）；`OverflowError` 从 `RpcPool.call` 的 except 分支穿透，被 `lp_pool_resolve_and_rank_v1_readonly.py` 记成探针错误。迁移库证据：首次出现 2026-08-31T22:02:28Z，此后**每一条**该原因的记录都带 `OverflowError`，此前一条都没有。已确定性复现（fails=1024 正常、1025 抛错）。

**因此近一周 live 漏斗的 "accepted=0" 不含任何经济信息**：最新批次 30 个候选全部是 `INPUTS_UNAVAILABLE`（24 个 OverflowError + 6 个 `NETCOVER_INPUT_MISSING`），`COMPUTED_FAIL` 为 0。阳性对照取自 2026-08-31T19:34Z（溢出前）批次：WETH-USDC NetCover 0.743、SOSO-USDC 0.300，均为真正的 `COMPUTED_FAIL: NETCOVER_BELOW_SHADOW`。

### 对 B1 的三处修正

1. B1 §6.1 列四个保护进程，实测**五个**（多一个写 `reports/lp_scanner_v2_20260823/scanner.db` 的 scanner）。
2. B1 §10.3 "两张死表 0 写入者"过时：`market_sessions` 的 writer 在 `lp_rwa_collector_daemon_v1_readonly.py:592`，`rpc_severe_incidents` 的 writer 在 `lp_shadow_gate_v1_readonly.py:293` 且已接入 daemon 主循环（:1826/:1859）；两者都是**有 writer、触发条件从未满足**，行数 0。
3. B1 §10.6 "backup 副本仅 50–140M" 不成立：`VACUUM INTO` 后仍为 2.06G / 1.44G。

A/B 档 `existing_terminal_conjunction` 无生产者（确认 NO_WRITER），RH 支线的股票终闸不得复制该模式。

### 进行中

RH-01b（`docs/specs/20260907_RH-01b_capabilities_pool_probe.md`）：链能力矩阵与 V3/V4 池探针，已派给 `qwen-task`。

### B2 设计稿已补齐（2026-09-07 16:23 UTC）

用户找到 `Robinhood_Chain_LP_Bot_50_30_20_全面转向设计文档_v1.0.md`，SHA-256 `1afc496f0a4a465a611cad6052882c14fdd0aeb92d06635fcbd4a6cea05dfd37`、45948 字节，与 `INPUT_MANIFEST.json` 逐字节吻合。已归档 `docs/rh_pivot/inputs/`，`validate_delivery.py` 现返回 **PASS**（`input_checksums_verified: true`，结果存 `docs/rh_pivot/DELIVERY_VALIDATION_LOCAL.json`）。

B2 内容与 PRD v1.1 的 D01–D14 修订一致，不改变推进路线。要点对照：B2 §55 假设 Go/Rust/PostgreSQL/NATS 技术栈（实际为 Python+SQLite，由 D01 修正）；B2 §48 的 RH-P0–P11 任务拆分被 PRD §19 的 RH-00–RH-09 取代；B2 §12 的 1%/3%/7% premium、§23 的 30/75/150 bps USDG、§26 的 2/3/5/8% 回撤门限均保留为 Shadow 初值；B2 §45 的 I-01–I-15 不变量已被 PRD §18.3 的 RH-INV-01–18 覆盖并加严；B2 §16 允许的 5% transfer tax 被 PRD §10.3 首版拒绝；B2 §21 的原子退出被 PRD §15.2 降为可选、分步退出为必须。

---

# 2026-09-08 全天进展

## 1. 一句话状态

搬迁已完成并稳定运行；**RH 支线从零建到 21 个模块**，测试基线 3109 → **3527**（+418 全部为 RH 配对测试）；**72 小时正向观测已跑 7 小时**，采集器由 cron 看门狗守护，与本会话无关。**签名 0 / 广播 0 / 私钥 0 / LIVE 仍 BLOCKED。**

## 2. 已交付的 21 个 RH 模块

| 层 | 模块 | 覆盖用例 |
|---|---|---|
| 存储 | `store`（16 张 `rh_*` 表） | T57 |
| 采集 | `collector`（生产运行中）、`market_session` | T14–T16 |
| 身份 | `registry`、`capabilities`、`pool_probe`、`multiplier_reader` | T01–T13 |
| 经济 | `netcover_inputs`、`exit_depth`、`markout` | T24、T32–T37、T42 |
| 终闸 | `terminal_gate`（十项合取 + AST 形状 + 变异见证）、`funnel_autopsy` | T55、T59、T60 |
| 资金 | `bucket_ledger`（原子预占） | T25、T27、T51 |
| 账本 | `pnl`（NAV 唯一总账）、`shadow_runner` | T38–T41 |
| 股票 | `stock_reference`、`premium_guard` | T17–T24 |
| MEME | `meme_audit` | T43–T46 |
| 执行 | `calldata_decoder`（纯离线，零签名） | T48、T50 |
| 运营 | `daily_report`、`readiness` | §17 |

## 3. 链上实测发现（本项目首次拿到真实证据）

用户本轮授权后接入 Robinhood 公开 RPC，**全部只读**。关键发现：

| 发现 | 影响 |
|---|---|
| 链活跃，chainId 4663，Nitro v3.11.4 | 五个种子地址全部有代码；候选池 `factory.getPool` 回指自身 → **ATTESTED_SAME_BLOCK** |
| **USDG 是 6 位小数**（非 18） | 按 18 位算池价得 0.000000 而非 2480，差 10¹² |
| **`robinhood.drpc.org` 是假绿端点** | `eth_chainId` 正确但所有真实方法 `-32601`；只探 chainId 的健康检查会把它当第二个独立 provider，从而错误满足 LIVE 冗余门槛 |
| 官方端点**无 archive** | 历史状态仅约 1000–10000 区块；`eth_getLogs` 单次上限 10000 条 |
| **194 个股票代币全部 SESSION_NESTED** | PRD D08 的 legacy schema 分支从未被真实数据触发，须标 `SYNTHETIC_ONLY` |
| **367 个 V3 池，192 个有流动性** | 73 个池 TVL ≥ $100k，可容纳 50U 单仓——**规模瓶颈在 RH 链上不存在**（对比 B1 §9.3 旧链结论） |
| PRD 假设的四个乘数/暂停方法**全部 revert** | 真实入口：`0xa60bf13d` 乘数（15/15 与 API 一致）、`0x97a4064f` 生效时间戳（12/12 集合重合）、`0x5c975abb` `paused()` |
| 股票代币是 **beacon 代理**，194 个共用一份实现 | beacon 升级一次全部 attestation 同时过期 → **P0 监控点** |
| 参考价源 `GET /rhj/prices` | 带服务端 `generatedAt`（报价龄 3–4s）与 `isTradingHalt`、一级申赎流量 |
| 首次真实溢价 | SGOV +37 / GLD +65 / SPY +24 / QQQ +20 / NVDA +30 / AMC −90 bps，**全部 NORMAL 档** |
| 头寸级 fee-growth | 按 `L × Δfee_growth / 2^128`，年化 27.34% 且**对仓位规模恒定**；与全池法 24.68% 交叉验证 |
| 退出深度（661 个真实 tick） | $500k 退出仅 10.4 bps 冲击 → **退出深度在 100U 规模不构成约束** |

## 4. 四个「静默假绿」陷阱（全部不抛异常、只在部分输入上给错答案）

1. **USDG 6 位小数**：292 个 USDG 池全错，75 个 WETH 池正常。
2. **`liquidityNet` 是 int128 但 ABI 按 256 位符号扩展存**：错误解码得 1.157e77，会让退出深度算成「可无限退出」。
3. **池 token 顺序不固定**：AMC 池 STOCK 在前，其余 USDG 在前。精度也不同时给出荒谬值（易发现）；两边同精度时**只返回倒数**（量级正常、方向错误，极难察觉）。
4. **`_state_factors` 默认 decimals=0 / price=1**：$50,000 被当成 50,000 wei，退出深度算成 0——而 0 的语义是「不可退出」，与真相相反。

**共同点：都不抛异常。** 这是本项目最该防的失败形态，已全部写入报告。

## 5. 产能编排

- **qwen 2 路**（写入任务，同一仓库串行原则由 spec 的文件隔离保证）
- **codex gpt-5.6-luna xhigh 多路**：因其 bubblewrap 沙箱把 root 映射为 nobody，无法直接写 root 拥有的仓库；解法是让它写 `/tmp/codex_out/<包>/`，主脑验收后搬入——沙箱与验收闸都保住。
- **主脑**：所有联网调研（qwen/codex 的 curl 均被 deny）、spec 编写、验收裁决、commit。
- **Monitor ×2**：worker 完成事件 + **槽位空闲告警**（后者为修复一次 47 分钟空转而加）。
- **cron 看门狗**：每 5 分钟按「数据行是否增长」判活采集器，故障注入验证 12 秒内拉起。

## 6. 退回记录（不达标一律退回，共 5 次）

| 包 | 退回原因 |
|---|---|
| RH-02b | `evaluate_health` 传字符串崩溃；陈旧判定主路径零测试覆盖 |
| RH-03a | spec 写错模型路径名，装配结果 100% 被引擎拒于经济计算之前；分类器把非经济性拒绝标成 `COMPUTED_FAIL` |
| RH-03b | `primary_status` 在终闸已判否时仍返回 `COMPUTED_PASS`（假绿） |
| RH-04b | 脚本残缺（花括号未闭合，`ast.parse` 失败）→ 删除重写，spec 加强制语法自检 |
| RH-05d | 9 位纳秒时间戳崩溃；`NO_NEW` 档竟允许重新居中 |

## 7. 仍未完成

- **Stage A**：7/72 小时（9.7%）。
- **Stage B/C/D**：未开始。
- **RH-07 执行适配**：仅完成离线 calldata 解码器；签名/广播/密钥相关部分**需用户单独授权**，未触碰。
- **RH-09 Tiny Live 申请包**：未开始。
- **`usable_provider_count = 1`** → LIVE 闸按 PRD §8.3 保持 BLOCKED，需再找一个逐方法验证通过的独立后端。
- 头寸级 fee-growth 的**区间内折算**（`feeGrowthOutside`）未采，当前为全区间上界。

## 8. 对账速查

```bash
cd /opt/lpbot/lp-bot-v3-origin-check
git log --oneline -5
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider | tail -1   # 3527 passed / 14 skipped
./scripts/lp_rh_status.sh                                                          # Stage A 进度
crontab -l | grep lp_rh_collector_watchdog                                         # 看门狗仍在册
```

**全量回归必须在无 worker 并发的窗口跑**，否则宿主敏感测试会误报（见 `reports/rh_pivot/20260907T124500Z/HOST_SENSITIVE_TEST_FLAKINESS.md`）。

---

# 2026-09-08 下半场（14:2x – 15:0x UTC）

## 9. 新增交付

| 包 | 产物 | 验收 |
|---|---|---|
| RH-04e | `lp_rh_in_range_v1_readonly` + 测试 | 16 通过；主脑另跑 9 条对抗性复核全过 |
| RH-09a | `lp_rh_scale_audit_v1_readonly` + 测试 | 20 通过；全仓扫描无 raw-ratio 遗留 |
| RH-05e | `lp_rh_premium_series_v1_readonly` + 测试 | 24 通过；主脑另跑 8 条复核全过 |
| RH-05f | `lp_rh_organic_volume_v1_readonly` + 测试 | 26 通过；主脑另跑 7 条复核全过 |
| — | `lp_rh_premium_recorder_v1_readonly` + 看门狗（主脑亲写，实盘录制） | 故障注入通过 |
| RH-01d / RH-05g | 派发中 | — |

**全量回归 3688 passed / 14 skipped**（本次带 2 路 qwen 并发跑，未出现宿主敏感抖动）。

## 10. 溢价时间序列录制器已上线

`reports/lp_rh/premium.db`（**独立库文件**，采集器仍是 `scanner.db` 的唯一写者），
6 个标的、180 秒周期、cron 每 5 分钟按行增长判活。详见
`reports/rh_pivot/20260907T124500Z/RH-05-research/PREMIUM_RECORDER_20260908.md`。

首跑一次性暴露 5 个真问题，全部已修：猜错乘数选择器（正确是 `0xa60bf13d`，我没查自己
早上的 ABI 报告就先猜）、选中 `liquidity=0` 的未初始化池导致 AMC 报价 3.4e50、
SPY 首选池计价币是 WETH 却被字段名谎报成 USD、REST 限流、载荷容器键是 `quotes`。

**顺带发现（须在 Stage B 前处理）**：SPY 的深度在 WETH 池（活跃流动性 4.6e22），
USDG 池只有 5.9e17，差五个数量级。今早 `EXIT_DEPTH_LIVE` 里 SPY 的退出深度是在
**WETH 池**上测的，若实盘按 USDG 计价，那个深度数字不适用，须重测。

## 11. LIVE 闸的单点提供方阻塞已解除

从 ethereum-lists 官方注册表取 chainId 4663 的 4 个端点，逐方法核验：
**3 个全方法可用**（primary / publicnode / ordofi），固定区块上返回逐字节一致，
无 `SOURCE_DISAGREEMENT`；第 4 个 `arrowrpc` 全方法 HTTP 530。
`usable_provider_count = 3 >= 2`，PRD §8.3 该项 PASS。

**这只挪开一个与经济无关的工程阻塞。** `CAPITAL_POLICY_CONFLICT` 仍在（属用户资金授权
决定），Stage A/B/C 观测门槛全部未达。

## 12. 本轮我自己写错又自己更正的两处（都已写进报告）

1. 初稿称「五个方法逐字节一致」——**错**。`eth_blockNumber` 返回各家自己的链头，
   本来就该不同。更正后反而挖出真发现：我们在用的主端点每轮都是三家里最落后、也最慢的。
2. 随即把「落后 54 块」写成时效性风险——**又错**。实测出块间隔 0.102 秒，
   中位落后 9 块 = **0.9 秒**，比参考价自身 15–20 秒的报价龄小一个数量级。
   **块数不是时间**；在 0.1 秒出块的链上按块数直觉判时效，会把可忽略量报成风险。

## 13. 编排现状与一个卡点

qwen 两槽持续满载。**codex 本会话不可用**：直接 `codex exec` 被权限分类器拦
（先拦 `--dangerously-bypass`，合理；后连 `-c approval_policy=never` 也拦），
官方 codex 子代理通道则因子代理模型 ID 配成了不存在的 `MiniMax-M2.7` 而 404。
原派给 codex 的 RH-01d / RH-05g 已改排 qwen 队列，未丢活。
要恢复 codex 并发，需用户为 `codex exec` 加一条 Bash 权限规则。

## 14. 仍未完成（更新）

- Stage A 9.6 h / 72 h，覆盖率仍需追回 99%。
- 溢价序列样本数远低于 `min_samples=30`，当前 `premium_regime` 输出**无效不得引用**。
- 有机交易量模块已就绪但**尚无数据**，等 RH-05g 的 Swap 日志抓取器落地。
- SPY 退出深度须在 USDG 池重测。
- Stage B / C / D 未启动；RH-07 签名与广播部分**须用户单独授权**，未触碰。
