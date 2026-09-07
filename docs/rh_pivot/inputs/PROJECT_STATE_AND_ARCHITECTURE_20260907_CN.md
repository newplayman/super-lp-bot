# LP-Bot 项目状态与基础架构全景（2026-09-07）

> **本文档的用途**：交给另一个 AI 作为"要不要改、改哪里、不能碰什么"的判断基础。
> 每条事实都标注了核实方式（`[实测]` = 本次审计亲自跑命令核过；`[交接]` = 来自 08-14 交接且本次对账未变；`[代码]` = file:line）。
> **没有标注的句子不要当事实用。** 审计人：主脑（Fable 5.1），只读，未改任何代码。

---

## 0. 三十秒摘要

| 维度 | 状态 |
|---|---|
| 代码基线 | tip `1e1d9bd`，分支 `feat/prd-v2.1-m0-shadow`，**三周零变化** `[实测]` |
| 测试 | Python `3109 passed / 14 skipped / 0 failed`（一条宿主敏感测试见 §10.4）`[实测]`；Go 见 §8 |
| 真实资金 | **敞口 0，从未有过真实交易**：签名 0 / 广播 0 / 私钥 0 / keystore 0 字节 `[实测]` |
| 模型可信度 | **已通过阳性对照**：paper 6 仓位重放 3/6 过闸（最高 8.25）`[交接]` |
| 三条判死 | C 档"日化>1%"证伪；A 档股票×稳定币 M1 尺度不成立；Base 蓝筹 M1 尺度 accepted=0 `[交接]` |
| 最大未解风险 | live scanner **73–80% 池永久 fail-closed**（原因已从 `no_measured_usd_quote_route` 变为 `factory_registry_probe_incomplete`）`[实测]` |
| 新增运维风险 | 宿主磁盘 **1.37 G/天** 消耗，按此速率 46 天耗尽（lpbot 自身仅占 ~5G）`[实测]` |

**给 AI 的一句话**：这个项目现在的瓶颈不是"再写功能"，而是 §10 的路由失败与 §12 的优先级。任何"加功能"的改动请先对照 §11 红线。

---

## 1. 仓库与目录地图

```
/opt/lpbot/
├── lp-bot-v3-origin-check/     ← 【唯一活仓库】所有工作在这里
├── lp-bot-v3/                  ← 已封存，勿动 [交接]
├── HANDOFF_LP_BOT_20260814_CN.md   ← 当前有效交接（本文档的上游）
├── RISK_INVARIANTS.md          ← 12 条系统不变量（§5.3）
├── RECONNECT_断链对账_CN.md      ← SSH 断链后的恢复手册（§6.6）
├── 小资金高净收益 AMM LP 自动化机器人 PRD v2.1.md   ← 实现规范，最高准绳（625 行）
├── AUDIT_验收_*.md ×7           ← 历次验收审计
├── CODEX_任务包_*.md ×16        ← 历次派工任务书（codex 已退役，仅作历史）
├── 分析_*.md ×2                 ← 成本可行性核查 / 全链股票代币调研
├── TPF_WATCH.jsonl             ← 断链记录器输出（每 60s 一条，§6.5）
└── tpf_disconnect_recorder.py  ← 记录器本体
```

活仓库内关键目录 `[实测]`：

| 目录 | 内容 | 状态 |
|---|---|---|
| `scripts/lp_*_readonly.py` | **101 个** Python 只读研究管线，55,826 行 | **活跃**，全部工作在此 |
| `execution/` | 3 个 py，1,910 行：Base 执行器、Solana sidecar | 建成但**从未签名/广播** |
| `tests/test_*.py` | 135 文件，37,902 行，2,494 个测试函数 | 活跃 |
| `internal/ cmd/ pkg/` | Go 六边形单体，51,386 行生产 + 26,195 行测试 | **冻结**（§3.1） |
| `reports/` | 207 个日期子目录，2.7 G | 研究产物，只增不删 |
| `reports/lp_scanner/scanner.db` | 2.2 G SQLite | A 轨 scanner 持续写入 |
| `configs/*.toml` | dryrun/shadow/live/canary 配置 | live/canary 需 `.sha256` 旁证 |
| `scripts/lp_long_horizon/` | 冻结 `[交接]` | 勿动 |

**未提交改动**（自 08-11 起一直存在，良性，需决定提交或丢弃）`[实测]`：
- `scripts/lp_rpc_pool_v1_readonly.py` +5 行：`health_snapshot()` 增加逐端点失败计数（codex TP-H 遗留）；
- `.gitignore` +4 行：`.codex/`、`.agents/` 沙箱挂载点。

---

## 2. 项目在做什么（一段话说清）

用**小资金（M1 = 100U）**在 AMM 集中流动性池做 LP，靠一套**只读研究管线**从 DefiLlama 全网快照中找到"手续费+奖励能覆盖全部成本"的池（NetCover ≥ 1.0），再经**执行侧安全契约**开仓。
项目至今处于**研究/影子阶段**：管线建成并经校准，执行器建成但被双开关锁死，**没有任何真钱进过市场**。
过去一个月的核心成果不是候选，而是**把"为什么没有候选"查到了底**（§9）。

---

## 3. 架构分层

### 3.1 两层，方向单一

```
┌──────────────────────────────────────────────────────────┐
│  Python 只读研究层  scripts/lp_*_readonly.py  【活跃】      │
│  DefiLlama → Stage1 → scanner → NetCover → 终闸 → 报告      │
│  + Solana 股票 stage2 支链  + C 档 shadow 观测              │
└──────────────────────────────────────────────────────────┘
                 │ 完全独立，不调用 ↓
┌──────────────────────────────────────────────────────────┐
│  Go 六边形单体  cmd → core → ports ← adapters  【冻结】      │
│  dryrun/shadow/live 三模式 build-tag 隔离                    │
└──────────────────────────────────────────────────────────┘
                 │ 独立于两者 ↓
┌──────────────────────────────────────────────────────────┐
│  execution/  Base M1 执行器 + Solana M1 sidecar  【锁死】    │
│  LIVE_TRADING=false 双开关；签名前拦截；零广播               │
└──────────────────────────────────────────────────────────┘
```

- Go 层是项目早期（≤2026-05-31 冻结）的产物，有完整的 mode isolation、10 条不变量的属性测试。**Python 研究线不调用 Go** `[Qwen B 核实]`；唯一耦合是 shell 运维胶水：`scripts/refresh_and_sync_tierc_holder_snapshot.sh:8`（`go run -tags=shadow ./cmd/lpbot --base-tierc-holder-snapshot-refresh`）、`scripts/run-phase0-verdict.sh`（`bin/lpbot-backtest`）、`scripts/canary_cycle.sh`（归档）。仓库 `CLAUDE.md` 明写 LP 研究冻结、`edge_proven=no`——但 08 月起的 PRD v2.1 线是**经指挥官批准的重启**，走 `feat/prd-v2.1-m0-shadow` 分支。
- Python 层的铁律：脚本命名 `lp_<domain>_<version>_readonly.py`，配对测试 `tests/test_<同名>.py`，**不碰钱包、不写链**。

### 3.2 漏斗主链（Base）`[代码]`

| 环节 | 文件 | 关键点 |
|---|---|---|
| 粗筛 Stage1（0 RPC） | `lp_universe_screener_v1_readonly.py` `score_pool :316` `main :502` | DefiLlama 快照；TVL≥150K（Base）；股票专用 20K |
| 采数 daemon | `lp_scanner_daemon_v1_readonly.py`（PID 2077656） | 写 `pool_snapshots / opportunity_scores / reward_observations`；`:658` 为 Base 记录打 `protocol_type="clmm"`（TP-F F1 修复） |
| 输入装配（9 个 horizon-USD 字段） | `lp_netcover_inputs_v1_readonly.py` `assemble_netcover_inputs :1404`（CLMM `:824`） | 按 `protocol_type` 严格分派 CLMM / AMM；缺失 → `NETCOVER_PROTOCOL_TYPE_INVALID` fail-closed |
| 经济判定（纯函数） | `lp_netcover_engine_v1_readonly.py` `evaluate_netcover :175` `apply_netcover_gate :283` `absolute_profit_gate :232` `position_cap_usd :256` | NetCover = (fee_ev+reward_ev) / 全成本；`cover >= NETCOVER_SHADOW` 落点 `:219` |
| 成本模型 | `lp_swap_cost_model_v1_readonly.py` | TP-J J3 修正：换腿按 V3 库存份额（`clmm_token0_value_fraction`），非全额 |
| **终闸合取** | `lp_scanner_daemon_v1_readonly.py` `_enforce_fifth_gate :1242` | `vetted = prior_vetted AND (netcover_pass AND NOT permanent_reason AND position_cap_pass) AND (entry_eligible is not False)`，回写 `opportunity_scores.vetted`。解剖脚本 `lp_funnel_autopsy_v1_readonly.py` 按七闸复算：resolution / asset_quality / yield_cover / multiwindow_stable / entry_eligible / NetCover / PositionCap |
| 产物 | `reports/lp_tp_j/20260814_base_rerun/AUTOPSY.json` 等 | `accepted_recomputed`、`decay` 各闸存活数、`netcover_failures` |
| 影子证据闸（独立于入场终闸） | `lp_shadow_gate_v1_readonly.py` `evaluate_shadow_gate :325` | PRD v2.1 §12.0 纸面影子证据，写 `reports/lp_shadow_gate/latest/gate_report.md` |

### 3.3 Solana 股票代币支链 `[代码]`

| 环节 | 文件 |
|---|---|
| 宇宙识别（A/B/C 分档、issuer 归一化、刷量标记） | `lp_stock_token_universe_v1_readonly.py` |
| 三档策略与 C 档七闸 | `lp_stock_tier_policy_v1_readonly.py` `evaluate_c_gate`（合取 `:238`，自检 `len(details)==7` `:239`） |
| 终态验收 | `lp_stock_tier_acceptance_v1_readonly.py`（含 `0_because_computed_and_failed` / `0_because_inputs_unavailable` 拆分） |
| Stage2 链上验证 + CLMM 经济回放 | `lp_solana_stock_stage2_v1_readonly.py`（sigma 5 分钟分桶×√288 `:59-60`；dust 过滤；`assemble_clmm_stage2_netcover` **真实评估阈值** `:941+`） |
| C 档退出/持有人/币龄证据 | `lp_solana_tier_c_risk_evidence_v1_readonly.py` |
| C 档 48h 持续性观测 | `lp_stock_tier_c_shadow_v1_readonly.py`（已完成，§9.2） |
| Solana 执行 sidecar | `execution/solana_m1_sidecar_v1.py`（909 行） |

### 3.4 免费 RPC 层 `[代码]`
`lp_rpc_pool_v1_readonly.py` `class RpcPool :219`：免费端点表 `:68-180`（base / eth / arbitrum / optimism / solana 五链，Base 约 10 个：mainnet.base.org、drpc、lava、publicnode、1rpc、meowrpc、blastapi、zan、nodies…；Solana 6 个）。健康端点 round-robin `call :343`；失败退避 `_penalize :277` = `RPC_COOLDOWN_BASE`(默认 2s) × 2^(fails−1)，封顶 `RPC_COOLDOWN_MAX`(默认 300s)；按端点/方法限速 `_pace_request :319`；全失败抛 `RpcPoolExhaustedError`；`health_snapshot :287` 输出 `NORMAL/DEGRADED`。UA 伪装 `curl/8.5.0` `:202`（规避 403）。**无任何付费端点或 API key** `[实测 grep + Qwen B]`。

---

## 4. 数据存储 `[实测]`

`reports/lp_scanner/scanner.db`（2.2 G，3,768 个批次，2026-08-08 → 今）：

| 表 | 行数 | 状态 |
|---|---:|---|
| `pool_snapshots` | 2,933,834 | 活跃，**无界增长**（§10.6） |
| `opportunity_scores` | 113,012 | 活跃，终闸结果 |
| `reward_observations` | 113,010 | 活跃，TRUSTED_24H 信任等级依据 |
| `market_sessions` | 0 | **死表**：0 写入者、2 读取者 |
| `rpc_severe_incidents` | 0 | **死表**：0 写入者、4 读取者 |
| `shadow_gate_observations` | 0 | 有写入者但 shadow 模式未运行 |
| `shadow_positions` | 0 | 同上 |

其他数据：`/var/lib/lpbot-strategy/stock-tier-c-shadow/{observations.db,latest.json}`（C 档观测终态，412K）；`reports/lp_tp_h/20260811/h5_checkpoints/*.json`（A 档 33 池逐池结果）；`reports/lp_tp_j/`（校准与 Base 复验）。

---

## 5. 闸门、常量与不变量

### 5.1 六个关键常量（**任何改动需指挥官放行，且只能收紧**）`[实测]`

| 常量 | 值 | 位置 |
|---|---|---|
| `STABLE_MIN_FRAC` | 0.7 | `lp_multiwindow_stability_v1_readonly.py:37` |
| `NETCOVER_SHADOW` | 1.0 | `lp_netcover_engine_v1_readonly.py:18` |
| `NETCOVER_TINY_LIVE` | 1.5 | `:19` |
| `POSITION_TVL_SHARE` | 0.0005 | `:24` |
| `HARD_POSITION_TVL_SHARE` | 0.001 | `:26` |
| `LVR_COEFFICIENT_MODEL` | 0.50 | `lp_netcover_inputs_v1_readonly.py:94` |

### 5.2 M1 资金与 C 档参数（指挥官已决）`[交接]`
M1 = 100U；单仓 50–60U；Reserve 40U；日亏 −5U 停新；总回撤 −10U KILL。
C 档：总敞口 ≤20U，单仓 ≤5U（`lp_stock_tier_policy_v1_readonly.py:32-33`），KILL 不放宽。

### 5.3 系统不变量（`/opt/lpbot/RISK_INVARIANTS.md`）`[实测]`
INV-COST-01（预期净利不足成本安全倍数禁开仓）· INV-EXIT-01/02（risk-off 语义 / 退出必过 quote+滑点闸）· **INV-GATE-01（阈值只能被证据收紧）** · **INV-GATE-02（终态 accepted 必须合取全部终闸位）** · INV-IL-01/02（三口径账本 / HODL 基线）· INV-RPC-01/02（DEGRADED 禁新增 / EXIT_ONLY 只减风险）· INV-RWA-01（instrument 归一化后才算 basis）· INV-TVLSHARE-01。

---

## 6. 运行中的基础设施 `[实测 2026-09-07 11:35]`

### 6.1 进程

| PID | 是什么 | 运行时长 | 对待方式 |
|---|---|---|---|
| `1349731` | paper runner（6 池，$10,000 虚拟资金） | **74 天** | 只读其输出；绝不重启 |
| `2077656` | A 轨 scanner daemon | 28 天，**从未重启** | 内存中是 08-09 的旧代码；重启会加载当前磁盘代码 |
| `2082408` | scanner 看门狗 `scripts/night_scanner_watchdog.sh` | 28 天 | 最多重启 20 次；停 scanner 需先停它 |
| `3913930` | 断链状态记录器 | 27 天 | 每 60s 写 `/opt/lpbot/TPF_WATCH.jsonl`，只快照不干预 |
| ~~3783076~~ | C 档 48h 观测 | 已完成退出（跑满 55.1h） | 数据完整 |

### 6.2 systemd 单元（全部 lpbot 交易单元均 disabled/inactive）

| 单元 | enabled / active | 关键字段 |
|---|---|---|
| `lpbot-base-m1-executor.service` | disabled / inactive | `User=lpbot-executor`，`LIVE_TRADING=false` |
| `lpbot-solana-m1-sidecar.service` | disabled / inactive | `User=lpbot-solana-executor`，`LIVE_TRADING=false` |
| `lpbot-canary.service` | disabled / inactive | **危险遗留**：`ExecStart=/opt/lpbot/lp-bot-v3/bin/lpbot-live`（指向**已封存仓库**的 live 二进制），`Restart=always`；配套 `configs/config.canary.toml` 为 `mode=live canary=true`、**`[live] enabled=true`**、`max_order_usd=20`。**绝不 enable** `[Qwen B]` |
| `lpbot-shadow.service` | disabled / inactive | Go shadow 模式历史单元，`ExecStartPre=validate-shadow-binary.sh` |
| `lpbot-net-guard.service` | **enabled / active**（05-23 起） | 与交易无关：iptables 把 Redis/Supabase 端口锁到 localhost |

### 6.3 主机隔离
`/etc/lpbot-solana-executor/` 0700，`keystore.json` 与 `password` **均 0 字节**（从未生成密钥），owner `lpbot-solana-executor`（nologin）；策略用户 `lpbot-strategy` 不可读。环境变量中无任何私钥/助记词 `[实测]`。

### 6.4 paper runner 现状
6 池 Base（WETH-CBBTC / WETH-USDC×2 / WETH-BRETT / USDC-SAPIEN / VIRTUAL-USDC），$10,000 虚拟本金。净值 $0.69（06-24）→ $1,596.95（08-14）→ **$1,769.39（09-07，tick 3564）**。
**注意**：它对 gas / 换腿 / 滑点 / 奖励换汇 / LVR / 延迟损失**全部未建模**（TP-J J1 结论），其 PnL 不是全成本可执行结果。

### 6.5 断链记录器
本机就是 `157.173.123.24`，Claude 经不稳的 SSH 接入。记录器每 60s 写 git tip / 脏改动 / 四进程存活 / codex 是否在跑 / C 档进度 / 磁盘余量。**断链后第一条命令**：`tail -3 /opt/lpbot/TPF_WATCH.jsonl | python3 -m json.tool`。

### 6.6 派工与长任务纪律
- 长任务一律 `setsid nohup … > /opt/lpbot/<name>.log 2>&1 < /dev/null &`，验证 PPID=1；会话内后台任务会随 Claude 退出被清理；
- setsid 会丢完成通知 → 另挂等待器 `while kill -0 <PID>; do sleep 60; done`；
- **codex 已退役**（2026-09-02 起）；代码派 `~/.local/bin/qwen-task`，只读研究派 `qwen-code -p … --disallowedTools Edit,Write`；
- 不并发跑两个 worker 于同一仓库。

---

## 7. 执行侧安全契约（建成、锁死、经对抗审计）`[交接 + 实测]`

两个执行器（`execution/base_m1_executor_v1.py`、`execution/solana_m1_sidecar_v1.py`）共同契约：
1. `LIVE_TRADING` 默认 false（`base:725`、`solana:683`）+ 启动确认串**双开关**；未解锁调用广播即 raise，且拦截点**在签名之前**；
2. 私钥只走 encrypted keystore；裸私钥环境变量被拒（`FORBIDDEN_SECRET_ENV_KEYS`）；keystore 0600/owner 校验；
3. 指令白名单 `open/increase/decrease/collect/close/swap`；program id **运行时链上校验**，失败即拒；
4. 单笔/日 cap、滑点上限、deadline/blockhash、三 ID + idempotency 必填、ledger 强制回填；
5. 五检（simulate/quote/basis/RPC/余额）——TP-H F6 已把 quote/basis/余额改为链上独立计算（不再透传自报值）；
6. kill switch → EXIT_ONLY，swap 方向经指令解析核验（TP-H F6）；
7. Token-2022 Scaled UI：raw/accounting/UI 三态分离。

**至今：签名 0、广播 0、私钥生成 0、付费服务 0。**

---

## 8. 规模与测试基线 `[实测]`

| 项 | 值 |
|---|---|
| commits | 734（本分支自 `fec4acc` 起 26 个） |
| Python 研究脚本 | 101 个 / 55,826 行 |
| execution/ | 3 个 / 1,910 行 |
| Python 测试 | 135 文件 / 37,902 行 / 2,494 个测试函数 |
| Go | 51,386 行生产 / 26,195 行测试（冻结） |
| pytest | **3109 passed / 14 skipped / 0 failed**（14 个 skip 为环境绑定 nodeid） |
| go test | **57 packages ok / 0 fail / exit 0**（未缓存全量重跑 ~20 分钟；`wallet/keystore` 单包 196s） |
| reports/ | 207 目录 / 2.7 G；scanner.db 2.2 G |
| 磁盘 | `/` 193G，剩 59G（70% 用） |

---

## 9. 已证实 / 已证伪结论（带证据路径）

### 9.1 模型可信：阳性对照通过 `[交接：TP-J]`
paper 6 仓位按真实资金与 1220.4h 持有期重放（`reports/lp_tp_j/`）：**WETH-USDC(Aero) 8.25 / WETH-USDC(Uni) 1.57 / WETH-BRETT 1.32** / USDC-SAPIEN 0.70 / WETH-CBBTC 0.61 / VIRTUAL-USDC 0.06。**3/6 过闸——项目史上第一次。** 两仪器分歧根源：paper 对全部执行成本未建模，不是 NetCover 高估。

### 9.2 C 档"日化>1%"证伪 `[交接；数据 /var/lib/lpbot-strategy/stock-tier-c-shadow/latest.json]`
55.1h 实测，15 池：初始 APY 28700%→保住 35%、6599%→32%、2829%→31%、1911%→48%；42% 以下那批保住 95–148%。**越夸张塌得越快，无例外。**

### 9.3 A 档股票×稳定币在 M1 尺度不成立 `[交接；数据 reports/lp_tp_h/20260811/h5_checkpoints/]`
36 池跑 33，25 池算出实数：最高 0.106（INTCX-USDC）、中位 0.0078。仓位拉到上限 + H=720h 最有利配置，最高 **0.480**。根因：1% 费档 + reward=0 + 仓位被 TVL 占比闸压到 5–60U。反解需 82%–5364% 费率 APR。

### 9.4 Base 蓝筹 M1 尺度 accepted=0（用修正后成本模型复验）`[交接；reports/lp_tp_j/20260814_base_rerun/AUTOPSY.json]`
731→92→30 终端记录→0；最好 WETH-USDC 0.808。此前 LVR 系数五档敏感性全 0。

### 9.5 结构性结论
- **持有期是主导杠杆，不是仓位规模**：同批池 H=168h 全灭；H=1220h 3 池过闸，且可行三池反解最小单仓仅 $0.27/$2.19/$3.71；另三池"无有限仓位可达 1.0"（每美元变量风险 > 调整后收入）。
- 能赚钱的配置画像：**低费档（0.084–0.45%）+ 高 reward（12–154%）+ 大仓位 + 长持有**；股票 A 档三项全反。
- 固定成本 = 2×池费档，与仓位大小几乎无关（08-09 分析，本轮再次成立）。

### 9.6 尚无结论（不要当结论用）
- **B 档（股票×主流币）9–10 池从未被经济评估**——无稳定腿无法锚定 USD 深度，是代码限制非经济结论；
- **A/B 档终闸结构上永远不过** `[Qwen A 交叉核实]`：`lp_stock_tier_acceptance_v1_readonly.py:79` 读取 `existing_terminal_conjunction`，但 `lp_solana_stock_stage2_v1_readonly.py` 从不产出该字段 → 该合取项恒 False（fail-closed 方向安全，但 A/B 的 `terminal_pass=0` 至今仍含一个「没算成」分量；TP-E 审计已指出、未修）；
- 当前时点这 3 个过闸的 paper 池**能否投**——那是 51 天历史窗口重放；
- Solana swap 采样约 6h 属盘中窗口，**看不到隔夜跳空**（股票代币主要风险）。

---

## 10. 已知缺陷、死胡同、假绿、环境敏感

### 10.1 假阴性事故族（本项目最高频形态，8 个变体）
共同病征：**闸没算出数被当成"经济上不过"**，而真结论恰好也是 0，故假阴性与真结论同值，测试绿、报告诚实、数字属实，唯独结论含义错。已修的 7 个（`entry_eligible` 漏合取 / scanner 不设 `protocol_type` / C 档 20U 敞口不累加 / vetted_menu daemon 模式不可达 / 组装器 Base 专用标签+稳定币表 / sigma 量纲 / dust swap 污染）+ 1 个**假阳性**（stage2 netcover 只检查输入非空却判 PASS，已修）。
**审计方法**：对每个"没通过"的字段反向问"谁生产它"，全仓库 grep 生产者；生产者不存在或恒为 None 即假阴性。

### 10.2 【P0 未解】live scanner 大面积永久 fail-closed `[实测]`
最新批次 30 行中 **22–24 行 `PERMANENT_FAIL_CLOSED`**（73–80%，08-11 曾达 90%），当前原因**全部**为 `factory_registry_probe_incomplete`（08-14 时为 `no_measured_usd_quote_route`）。scanner 进程 28 天未重启 → 与代码改动无关，是数据/RPC 层退化。**在查清前，任何基于 live 漏斗的"没有候选"都不可信。** 名单含 paper 能算出数的 WETH-CBBTC / WETH-USDT。

### 10.3 死表 `[实测]`
`market_sessions`、`rpc_severe_incidents` 有读取者无写入者——读一张永远空的表，属"能力装饰"。

### 10.4 宿主敏感测试 `[实测]`
`tests/test_p0_postgres_shadow_audit_v1.py::test_safety_no_forbidden_process` 扫全机 `ps aux` 找 `private_key/mnemonic/sendTransaction/canary…`；**任何进程的命令行含这些词即失败**，包括审计者自己的 grep。本次并行审计时它失败一次，单独重跑通过。不是代码退化。

### 10.5 两个长期未提交改动（§1）——良性，需决策。

### 10.8 残留桩、占位数据与假绿测试 `[Qwen B 扫描，主脑抽核]`
- **恒绿空测试**：`tests/test_lp_base_probe_dry_run_builder_v1_readonly.py:264` `test_no_lpbot_untagged_binary_invocation` 函数体为 `for …: pass`——**什么都不断言**，是最强形式的假绿；
- **弱断言测试**：`tests/test_lp_panel_server_v1_readonly.py:231`（仅不抛异常）、`tests/test_lp_netcover_inputs_v1_readonly.py:777`（仅 `is not None`）等；
- **占位数据被当真跑的风险**：`scripts/strategy_pivot_d4_realtime_paper_shadow_validation.py:95` `ALGEBRA_SWAP_TOPIC` 为硬编码占位 topic（非真实 Aerodrome topic）——该旧管线若被运行，swap 检测会静默失败；`scripts/lp_evm_v3_pool_readiness_probe_v1_readonly.py:37,40` PancakeSwap factory 地址标注 placeholder；
- **死胡同字段族**：`lp_scanner_daemon_v1_readonly.py:1509-1513` 写入 `reward_observation_history_*` 五个字段，全仓库无读取者；
- **有意的 fail-closed 桩（安全，非假绿）**：`lp_base_10u_probe_executor_v1.py:657+` 六个执行方法抛 `ExecutionDisabledInBuildStage`；`lp_long_horizon_readonly_collector_v1.py:206` import 即桩化。
- 真实代码中 **无 TODO/FIXME**。

### 10.6 磁盘 `[实测]`
记录器 27.7 天：100.55G → 62.71G，**1.37 G/天**，46 天耗尽。
宿主级占用 `[实测 du]`：`/var/lib/docker` 13G（其中 `containers/` **9.0G**，疑为容器 json 日志无轮转）、`/root` 12G、`/home` 12G、`/opt/lpbot` 5.5G、`/var/log` 0.8G、journal 0.2G。
**lpbot 自身 5.5G 不是消耗主力。** 顶层 du `[实测]`：`/opt` 60G（其中 **`/opt/marketdata` 42G、`/opt/asr` 9G**，均为同宿主其他项目；lpbot 5.5G）、`/tmp` 26G（`/tmp/asr-*` 构建缓存 ~5G 等）、`/var` 18G、`/root` 13G、`/home` 12G。**1.37 G/天的消耗主力在 marketdata / asr，不在 lpbot。**
lpbot 侧两个可控点：① `pool_snapshots` 2.9M 行无保留策略；② **`scanner.db` 文件 2.2G 但 `sqlite3` backup 副本仅 50–140M** → 文件绝大部分是空闲页，可 `VACUUM` 回收约 2G——但 daemon 正在写入，**必须先停看门狗与 scanner 再做**（§11 红线，需指挥官放行）。

### 10.7 时钟
08-11 曾观察到系统时钟与 paper runner CSV 时间戳相差约 3 天后自行对齐（`systemd-timesyncd` 在跑）。跨天推理时以链上 block/slot 为准。

---

## 11. 改动红线（给 AI 的操作边界）

**未经指挥官本轮显式放行，绝对不做**：
1. 真实签名 / 广播 / 生成私钥 / 接入钱包 / 把 `LIVE_TRADING` 置 true / enable 任何 `lpbot-*-executor|sidecar` 单元；
2. 改 §5.1 六常量、§5.2 资金参数；**放宽任何阈值以提高通过率**（INV-GATE-01）；
3. kill / restart §6.1 四个进程（paper runner 74 天数据、scanner 28 天数据不可再生）；
4. 动 `/opt/lpbot/lp-bot-v3`、`scripts/lp_long_horizon/`；
5. 接入任何付费 RPC / 数据源；
6. `git push`（本项目一贯只 commit）；删除或削弱既有测试（CI 亦禁止 `*_test.go` 删行）。

**允许直接做**：只读诊断、跑测试、写文档、在 `scripts/lp_*_readonly.py` + 配对测试内扩展只读管线。

**改动前必做**：
- 新增闸 → 必须进终闸合取并有摘除变异测试（INV-GATE-02）；
- 触及共用成本/装配模型 → **固定快照法**复核 Base 不变性（`sqlite3` backup 复制 `scanner.db`，新旧代码跑同一份，`netcover_failures` 与 `decay` 逐闸对照；**活库每 60s 在变，直接比会得假差异**）；
- 任何"0 个候选"结论 → 先按 §10.1 方法排除假阴性，报告必须拆分 `0_because_computed_and_failed` / `0_because_inputs_unavailable`；
- 最后一次编辑后重跑全量 `pytest` 与 `go test`，贴原始输出。

---

## 12. 未决事项（按优先级）

| 级别 | 事项 | 依据 |
|---|---|---|
| **P0-1** | 查清 live scanner 73–80% `factory_registry_probe_incomplete`：端点退化？探针逻辑？市场变化？ | §10.2 |
| **P0-2** | 磁盘：确认宿主级消耗来源；lpbot 侧给 `pool_snapshots` 设保留策略 | §10.6 |
| P1 | B 档（股票×主流币）给非稳定腿一个可核验参考价，使其可被经济评估 | §9.6 |
| P1 | 把持有期 H 纳入候选筛选维度（当前全按 168h），配套长持有风险闸 | §9.5 |
| P1 | A 档剩余 3 池 + 8 个未算出池补跑（不改变结论） | §9.3 |
| P2 | 死表清理或补写入；两个未提交改动决策；`FAIL_CLOSED:PASS` 归因顺序普查其他脚本 | §10.3/10.5 |
| 决策 | C6 smoke（10–20U 只验管路）与真实签名放行——**仅指挥官** | §5.2 |

---

## 附录 A：接手 / 对账速查
```bash
cd /opt/lpbot/lp-bot-v3-origin-check
git rev-parse --short HEAD                       # 应为 1e1d9bd
tail -3 /opt/lpbot/TPF_WATCH.jsonl | python3 -m json.tool
ps -o pid,etime,cmd -p 1349731,2077656,2082408,3913930
python3 -m pytest tests/ -q                      # 3109 passed / 14 skipped
```
三样对不上先报告、不要动手。

## 附录 B：文档索引（/opt/lpbot/）
PRD v2.1（准绳）· RISK_INVARIANTS.md · HANDOFF_LP_BOT_20260814_CN.md · RECONNECT_断链对账_CN.md · AUDIT_验收_TP-E_2026-08-10_CN.md（六代理审计范本）· 分析_NetCover可行性核查 · 分析_全链股票代币LP调研 · 仓库内 `E/F/G/H/I/J_ACCEPTANCE_*.md`（各包验收原始输出）。

## 附录 C：本次审计的核实方法
- 主脑亲自：对账（git/进程/记录器）、规模基线、六常量、systemd/keystore/env 安全状态、scanner.db 表行数与路由失败趋势、磁盘趋势与归属、pytest 全量（3109）与失败用例复现、go test 全量（57 ok）、DB backup 体积对比。
- Qwen A（只读，15KB）：Python 研究层架构地图与终闸表达式——与主脑记忆交叉一致，纠正 3 处行号，补 `_enforce_fifth_gate`、`lp_shadow_gate`、A/B `existing_terminal_conjunction` 缺口。
- Qwen B（只读，10KB）：systemd/configs/RPC/桩与假绿/Go 耦合——补 canary 单元指向封存二进制、恒绿空测试、占位 topic、死胡同字段族。
- 两路 Qwen 均因 `--disallowedTools` 含不存在的 `MultiEdit` 打了一条无害警告；实际以 `Edit,Write` 禁写生效。
- 审计副产物已清理：三份快照库副本（scratchpad）与临时 worktree。
