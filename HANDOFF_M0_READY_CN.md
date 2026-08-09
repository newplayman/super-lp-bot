# LP Bot PRD v2.1 · M0 Shadow 启动就绪交接

**分支：** `feat/prd-v2.1-m0-shadow`

**状态：** WP-00～10、M0R、M0P 与 M0F 漏斗可用性轮已完成验收；M0F 裁决为 **PASS / READY FOR COMMANDER REVIEW**，FIX-DOC/E2E 已收口。最终 scanner 为 `733→30→30→30→0`：stdout 的 `resolved=30` 是 resolver 输出数（含 14 条 fail-closed placeholder），canonical `read_funnel().resolved=16` 是成功 resolve 数；30 条 operational score 中 16 条 NetCover 有限，可计算覆盖率 `53.3%`。该 `16/30` 包含 `top` 从 10 扩至 30 的取样窗口扩大效应；衡量工程修复质量须采用同分母口径，即 M0P 的 `1/10` 到 M0F R1b 的 `4/10`。正式 R2 证据 `20260809_135500` 为同批 30 条、16 个可计算对、Spearman `r=0.473529`、`n=16`、`t=2.011613`、`df=14`、双尾 `p=0.063919`，top-K `7/10`；其 `r>=0.3` 仅达到预设业务排序阈值，不是统计显著性检验。结论应读作“边缘相关，证据不足以强推”，历史生产排序采用 `PROXY_NETCOVER` 的事实不变。**14 天 shadow 尚未启动；覆盖是否达到业务上可接受水平由指挥官判断，只有指挥官认可覆盖并显式决定起算后，14 天计时才开始。§12.0 gate 仍为 `INSUFFICIENT_EVIDENCE`，M1 未放行。**

**发布边界：** 未合并、未推送远端；等待指挥官 review。本文不构成 M1 放行。

## 指挥官决策记录 2026-08-09

- **D1 — 追认 14 个节点：** 追认 `tests/conftest.py::LEGACY_ENVIRONMENT_BOUND_NODEIDS` 中 14 个精确 nodeid 为 `legacy_environment_bound` skip；它们仍是 skip，不得写成 pass，也不得扩大为整文件忽略。
- **D2 — RWA daemon 已建：** 只读 RWA session collector、配对测试和 systemd unit 已由提交 `5b92e1f` 建立；当前仅表示实现完成，**未表示 daemon 或 14d shadow 已启动**。
- **D3 — 测试期 token：** 测试阶段沿用现有 Telegram token；进入任何真钱阶段前必须在外部强制轮换。token/chat 禁止写入源码、命令行、报告、日志、commit 或本文，亦禁止把值回写仓库。
- **D4 — M1 资金档：** M1 固定为 `1 × 50–60U`。这是后续资金档定义，不构成 M1 放行；`§12.0` gate 未通过前继续禁止真钱执行。
- **D5 — 外网只读面板：** 指挥官明确要求 panel 监听 `0.0.0.0:8899`。默认必须从环境读取不少于 32 字符的 `LPBOT_PANEL_TOKEN` 并鉴权；仅在显式 `--no-auth` 时允许无鉴权且必须留下醒目告警/访问日志。建议防火墙只放行指挥官固定出口 IP；进入任何真钱阶段前必须重新评估面板暴露的选池、仓位和策略参数风险。

## 1. WP / M0R / M0P 状态与证据

“配对测试数”是当前目标文件的 collect 数，不冒充全仓验收总数；最终通过数与全量输出由 sol 验收报告填写。

| WP / M0R | 状态 | commits | 当前配对测试数 / 验收证据 |
|---|---|---|---|
| WP-00 | DONE | `0600453 3caae9b 88f9a3d 6001355 3156a5f 849a215 10db4d8 e50220c` | vol-range 配对 6；collection quarantine、凭据清除、环境文件 ignore |
| WP-01 | DONE | `68b5bfd 7f42f78 38c66f5` | RpcPool 28；Solana 方法路由/退避/写方法阻断；sol live probe 6/6 UP |
| WP-02 | DONE | `1f98f1a b6379e4 541574c b234bed` | 引擎+replay+runner 46；60 轨迹报告 `reports/lp_il_math_replay/20260808_000000/` |
| WP-03 | DONE | `695fc1b 306699c 22185ed 92a994e 4d01bbb a51e44e 17fc81e 37763ed 0d2f6f0` | policy+replay+runner 59；7/7 replay `reports/lp_defensive_exit_replay/20260808_170228/` |
| WP-04 | DONE | `8deedca a96dfcd 1518c96 e1d6b3a 38b18f0 63c14dc 017700e 5983c55 b481fa2 f46625a` | netcover/cost/funnel/allocator 49；报告 `reports/lp_cost_sensitivity/20260808_172541/` |
| WP-05 | DONE | `2ab4d29 9a4d70c e7017b4 baf683b 4bfabdc` | instrument/anchors/session 38；周末 xStocks quote unavailable 按 fail-closed |
| WP-06 | DONE | `ec1ea15 fd4b6ab 5495410 88144b6 2643f96 bfecb5c 788af85 4d2322a 0c83aae d71ec5a d655306 9e995e9` | scanner+digest 24；真实 `--once` 已落 SQLite，unit 未安装/未启动 |
| WP-07 | DONE | `d63cb15 19f9a0e b80f51c a9f4de3 32cb308 1d3a6ed f1a5dea b425c58 bec89e7` | alerter 13；无 test token，已验 stdout 降级；全局 ≥60s throttle |
| WP-08 | DONE | `7879194 688376c b538af2 e589266` | ledger-v2 12；heartbeat/final 23 字段、退出成本语义、旧 heartbeat 兼容 |
| WP-09 | DONE | `853e590 bc586ad 39aff95 c8d35b0 9f9d5a6 74fc774 cd317fb cda1d0b 184ce07` | reward replay 10；报告 `reports/lp_reward_decay_replay/20260808_173832/` |
| WP-10 | **DONE** | 关键提交 `d3c9c96 7d5a59d f5b4988 44dab96 b8441b1 b624a70 fb88eb2`（TDD 含 `8afbe25 4f4a8be ddfad55 920c85f`） | Solana+runner+ledger+RpcPool+gate 定向 93；Base + Orca account-state 各 1 tick；全量 `2660 passed, 14 skipped` |
| M0R-R1 | DONE | `792663e` | hard risk exit 可绕过 disabled policy；仅记录该修复提交，不冒充本轮全量验收 |
| M0R-R2 | DONE | `25f9e94` | fail-closed cooldown reentry 接线；仅记录该修复提交，不冒充本轮全量验收 |
| M0R-R3 | DONE | `59fcee4` | 退役 Solana registry 并归档 probe；仅记录该修复提交，不冒充本轮全量验收 |
| M0R-D2 | DONE | `5b92e1f` | 只读 RWA session collector 与 unit 已建；尚未启动 14d shadow |
| M0R-DOC | DONE | `42c79da` | D1-D4、RWA 启动式、M1 `1 × 50–60U` 与 REGULAR cent-units TODO 已收口 |
| M0P-W6 | DONE | `0541c1f 518f8db` | raw-only NetCover 9 项装配；定向 67；最终 live 734→10→10→10→0，1 条完整可计算，阈值未放宽 |
| M0P-P1 | DONE | `6b381fb 8c6ee4a` | 标准库只读 panel；定向 22；路径型密钥脱敏、固定 runner 输入与 systemd ownership 交接闭合，unit 未安装 |
| M0P-W1 | DONE | `e7b30ee c7b7e9f` | ≥50 identities 且 ≥5 roots；每 root 最多重入 3 次；原子 checkpoint 与单调 tick 防重启绕过；定向 68 |
| M0P-W3 | DONE | `a0a43ce` | 旧失效断言改为校验薄壳不重做 redaction 且转发 canonical registry |
| M0P-W4 | DONE | `4ee3860` | 4 类 runner 层 hard-risk 退出回归；W2 入场拒绝口径固化 |

## 2. 指挥官批准后才可执行的启动命令

以下命令**只写在交接中，未执行**。先将 `APPROVED_ALLOCATION` 替换为 sol smoke 后人工批准、非空且确实来自 live-vetted 链路的 Base allocation。不得使用 fixture 启动 14d 观察。

### 2.1 nohup

```bash
cd /opt/lpbot/lp-bot-v3-origin-check
install -d -m 700 reports/lp_scanner reports/lp_scanner/rwa_sessions reports/lp_shadow_launch reports/lp_panel reports/lp_portfolio_paper_runner/latest
nohup python3 -u scripts/lp_scanner_daemon_v1_readonly.py \
  --db reports/lp_scanner/scanner.db \
  --coarse-interval-secs 900 --top-interval-secs 60 \
  > reports/lp_shadow_launch/scanner.log 2>&1 &
nohup python3 -u scripts/lp_rwa_collector_daemon_v1_readonly.py \
  --db reports/lp_scanner/scanner.db \
  --jsonl-dir reports/lp_scanner/rwa_sessions --interval-secs 30 \
  > reports/lp_shadow_launch/rwa_collector.log 2>&1 &
test "${#LPBOT_PANEL_TOKEN}" -ge 32
nohup python3 -u scripts/lp_panel_server_v1_readonly.py \
  --host 0.0.0.0 --port 8899 \
  --db reports/lp_scanner/scanner.db \
  --heartbeat reports/lp_portfolio_paper_runner/latest/heartbeat.jsonl \
  --portfolio-csv reports/lp_portfolio_paper_runner/latest/portfolio_state_hourly.csv \
  --rwa-jsonl-dir reports/lp_scanner/rwa_sessions \
  --probe-dir reports/lp_rpc_pool_probe \
  --access-log reports/lp_panel/access.log \
  > reports/lp_shadow_launch/panel.log 2>&1 &
nohup python3 -u scripts/lp_portfolio_paper_runner_v1_readonly.py \
  --allocation "$APPROVED_ALLOCATION" --chain base --poll-secs 1800 \
  --gate-db reports/lp_scanner/scanner.db \
  --out reports/lp_portfolio_paper_runner/latest \
  > reports/lp_shadow_launch/runner.log 2>&1 &
```

不要把 Telegram token/chat 放命令行。若需要 Telegram，只通过进程环境的 `LPBOT_TG_TOKEN` / `LPBOT_TG_CHAT` 注入。

### 2.2 systemd

scanner 有已审计 unit；安装/启用是指挥官动作：

```bash
sudo install -d -o lpbot -g lpbot -m 0700 /opt/lpbot/lp-bot-v3-origin-check/reports/lp_panel
sudo install -d -o lpbot -g lpbot -m 0700 /opt/lpbot/lp-bot-v3-origin-check/reports/lp_scanner
sudo install -d -o lpbot -g lpbot -m 0700 /opt/lpbot/lp-bot-v3-origin-check/reports/lp_scanner/rwa_sessions
sudo install -d -o lpbot -g lpbot -m 0700 /opt/lpbot/lp-bot-v3-origin-check/reports/lp_portfolio_paper_runner/latest
sudo chown -R lpbot:lpbot /opt/lpbot/lp-bot-v3-origin-check/reports/lp_scanner
sudo chown -R lpbot:lpbot /opt/lpbot/lp-bot-v3-origin-check/reports/lp_panel
sudo chown -R lpbot:lpbot /opt/lpbot/lp-bot-v3-origin-check/reports/lp_portfolio_paper_runner/latest
sudo install -m 0644 deploy/systemd/lpbot-scanner-shadow.service /etc/systemd/system/lpbot-scanner-shadow.service
sudo install -m 0644 deploy/systemd/lpbot-rwa-collector-shadow.service /etc/systemd/system/lpbot-rwa-collector-shadow.service
sudo install -m 0644 deploy/systemd/lpbot-panel-shadow.service /etc/systemd/system/lpbot-panel-shadow.service
sudo systemctl daemon-reload
test "${#LPBOT_PANEL_TOKEN}" -ge 32
sudo --preserve-env=LPBOT_PANEL_TOKEN systemctl import-environment LPBOT_PANEL_TOKEN
sudo systemctl enable --now lpbot-scanner-shadow.service
sudo systemctl enable --now lpbot-rwa-collector-shadow.service
sudo systemctl enable --now lpbot-panel-shadow.service
sudo systemctl status lpbot-scanner-shadow.service --no-pager
sudo systemctl status lpbot-rwa-collector-shadow.service --no-pager
sudo systemctl status lpbot-panel-shadow.service --no-pager
```

上述绝对路径的 `install -d` 是 systemd 启动前置：它们必须属于 `lpbot:lpbot` 且权限为 `0700`，否则 unit 的 `User=lpbot` 与可写预检会 fail-closed。由于 `install -d` 不会修正已有 `scanner.db` 等文件的 owner，紧随其后的 ownership 交接必须保留，且 `chown -R` 仅允许指向上述 scanner、panel 和 runner/latest 三个明确子树，禁止对仓库根或 `reports/` 根执行。panel unit 只使用服务管理器继承的 `LPBOT_PANEL_TOKEN` 环境变量；启动前必须用上述 `systemctl import-environment LPBOT_PANEL_TOKEN` 把当前 shell 中的变量导入 system manager，`--preserve-env` 仅传递环境变量而不把值放进命令行。不要把 token 值写入 unit、命令行、shell history 或报告。主机防火墙建议仅允许指挥官出口 IP，例如 `ufw allow from <COMMANDER_PUBLIC_IP> to any port 8899 proto tcp`，禁止对所有来源放行 8899。

paper runner 暂无常驻 unit，避免把 allocation 路径静态写死。指挥官可用 transient unit（命令仍未执行）：

```bash
sudo systemd-run --unit=lpbot-paper-shadow \
  --property=User=lpbot --property=Group=lpbot \
  --property=WorkingDirectory=/opt/lpbot/lp-bot-v3-origin-check \
  --property=NoNewPrivileges=yes \
  /usr/bin/python3 -u scripts/lp_portfolio_paper_runner_v1_readonly.py \
  --allocation "$APPROVED_ALLOCATION" --chain base --poll-secs 1800 \
  --gate-db reports/lp_scanner/scanner.db \
  --out reports/lp_portfolio_paper_runner/latest
```

nohup 与 transient unit 两种启动方式都必须保留上述显式 `--out reports/lp_portfolio_paper_runner/latest`；panel 与 `lpbot-panel-shadow.service` 只读取该固定目录，不会自动猜测 runner 的时间戳目录。不得在同一固定目录上并发启动第二个 runner。

## 3. scanner → allocator → runner 的可审计路径

```bash
python3 -u scripts/lp_scanner_daemon_v1_readonly.py --once \
  --db reports/lp_scanner/scanner.db \
  --vetted-menu-out reports/lp_m0_integration_smoke/vetted_menu_live.json
python3 -u scripts/lp_portfolio_allocator_v1_readonly.py \
  --ranked reports/lp_m0_integration_smoke/vetted_menu_live.json \
  --total 50 --min-position-usd 50 \
  --out reports/lp_m0_integration_smoke/allocation_live
python3 -u scripts/lp_portfolio_paper_runner_v1_readonly.py \
  --allocation reports/lp_m0_integration_smoke/allocation_live/allocation.json \
  --chain base --max-ticks 1 --poll-secs 1800 \
  --gate-db reports/lp_scanner/scanner.db \
  --out reports/lp_m0_integration_smoke/base_runner_1tick
```

- exporter 只接受 SQLite 最新 cycle 中 `accepted=1` 且 score_json 同时证明 `vetted=true`、`netcover_pass=true` 的记录，并加 `scanner_evidence_origin=live_opportunity_scores`。
- 若真实 scanner `accepted=0`，链路应诚实停在 0 allocation；这是有效结果，不得用 fixture 冒充 live-vetted。
- 审计 fixture 只允许标 `fixture_only_not_live_vetted`，用于验证 bridge/allocator 机械接线。
- allocator 的 M1 默认配置明确记录 `min_position_usd=50`；该阈值只产生 `below_min` 标记，不替代或放宽 runtime hard gates。依据 `reports/lp_cost_sensitivity/20260808_172541/`：同一历史样例 25U 为 `SKIP`、50U 为 `PASS`。
- sol 的完整 stdout/JSON 归档：`reports/lp_m0_integration_smoke/SOL_ACCEPTANCE_20260808.md` 与 `reports/lp_m0_integration_smoke/evidence_20260808/`；旧 `PENDING_SOL_SMOKE.md` 仅为兼容索引。
- Solana runner 已通过 WP01 免费 RpcPool 对真实 Orca Whirlpool 完成 account-state 1-tick：显式 `protocol=orca_whirlpool` / `solana_adapter=orca_whirlpool_account_v1`，校验 owner、base64、653-byte space、discriminator、正 sqrt/liquidity 与 decimal price。该 tick 是账户状态 observation，`amount1=0`、`n_swaps=0`、fees=0；不是 swap event decoder 或 fee evidence。

## 4. §12.0 gate 报告读法

runner 每个成功 tick 自动写同一 `scanner.db`：

- `shadow_positions`：按唯一 `(source_run, position_identity)` 计模拟仓，重复 tick 不增加仓数；gate 另把尾部 `:reentry:N` 归并为 root pool，仓位闸同时要求 ≥50 unique identities 与 ≥5 unique root pools。同池重入不能刷过覆盖广度；runner 每个 root 最多重入 3 次。
- `shadow_gate_observations`：portfolio NAV、fee prediction/actual/error、shadow PnL、running-peak DD、RPC health 与 evidence status。
- `rpc_severe_incidents`：`EXIT_ONLY` / `KILLED` 开严重故障，只有 `NORMAL` 闭环；`DEGRADED` 只观察、不误闭环。

随时生成：

```bash
python3 -u scripts/lp_shadow_gate_v1_readonly.py \
  --db reports/lp_scanner/scanner.db \
  --out reports/lp_shadow_gate/latest/gate_report.md \
  --json-out reports/lp_shadow_gate/latest/gate_report.json
```

硬 gate（代码显式常量，严格不等号）：≥14d；≥50 unique positions；fee 预测误差 `<20%`；shadow net PnL `>0`；max DD `<8%`；未处理严重 RPC `=0`。PnL 判定边界先把绝对值 `<=1e-9 USD` 的浮点消去噪声保守归零，原始和保留为报告 `raw_value`；因此 0 或微小正噪声不得通过 `>0`。

fee 误差公式：

```text
abs(sum(actual_fee_usd) - sum(predicted_fee_usd))
/ sum(predicted_fee_usd) * 100
```

fee 预测来自 allocation 冻结的 `fee_apr_onchain × in-range capital-time / year`。任一仓缺失、非有限、零/负预测值时结果为 `UNKNOWN`，不是 0%；overall 为 `INSUFFICIENT_EVIDENCE`。runner 的 gate DB 持久化失败采用 hard-fail，避免继续产生“看似完整但未入 gate DB”的假证据；scanner 的 RPC incident 辅助写失败会 stderr 明示但不推翻已经原子提交的 scanner cycle。

Shadow 五问在 14d 数据前均为 **PENDING_EVIDENCE**，不得提前作答：显示 APR 最易骗人的池型、Reward APR 持续期、xStocks 最佳 Fee/IL session、窄/宽 range 增益、自动退出是否 outperform HODL/50:50 LP。

## 5. 已知限制与禁止事项

- 全系统仍是 paper/read-only；无钱包、私钥、签名、approve、广播或写交易路径。
- `reward_income_realized` 是 paper simulated claim；reward marked/realized/price PnL 已拆分，但没有 farm/gauge on-chain claim 证据。
- `lvr_estimate`、`exit_latency_loss` 是模型估计，不是 observed execution；退出记录 `depth_model` 或 `flat_placeholder` 成本 basis。
- `PRIMARY_CLOSED` 永远 shadow-only，不与 REGULAR 平均后转正。
- `tvl_worsening` / `liquidity_worsening` 的硬动作是 v1 §23 入场拒绝，不进入存量仓 hard-risk 直通；存量仓不会仅因 TVL/流动性衰减自动退出，相关风险由入场筛选承担。
- Reward persistence 缺失/无效/负值 fail-closed；`<6h` 不 ENTER，6–24h haircut，≥24h 才 trusted。
- 14 条 `ambiguous_multi_factory_pool` 的工程状态是 `blocked_pending_authoritative_pool_mapping`：当前继续 fail-closed，但它们是等待权威 pool/factory 映射后可修复的阻断项，不应描述为不可恢复的“永久关闭”。数据库和历史报告中的 `PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool` 是当次运行留下的原始历史字段，本轮不篡改。
- Telegram 未配置 `LPBOT_TG_TOKEN/LPBOT_TG_CHAT` 时降级 stdout、不崩溃；尚未发送真实测试消息。按 D3，测试阶段沿用现有 token，但进入真钱阶段前必须在外部强制轮换；任何 token/chat 值禁止回写源码、命令行、报告、日志或 commit。
- Base public RPC 与 Solana public RPC 都有可变限流；没有付费 fallback。任何付费 RPC 只允许生成建议报告，必须指挥官人工批准。
- 当前 Solana coverage 是经 registry 的真实 Orca account-state runner tick，并已进入 ledger-v2/gate；它不解码 swap event，也不产生 fee evidence。M0 不允许借机实现 M1 TS sidecar。
- Raydium 市场快照是单次 top-1000 page，`hasNextPage=true`，页外池 unavailable/unverified；Orca 当次 page `next=null`。详见 `MARKET_SNAPSHOT_M0.md`。
- Cost sensitivity 使用历史 swap/模型参数，不保证未来收益；已验收的历史结论是 25U 不经济，50U 起才在该样例过 gate。
- M0P 最终代码 live scanner 本次 `screened=734`、`scored=10`、`accepted=0`；其中 1 条候选九项输入完整、NetCover `0.040912955191278286` 并按原阈值诚实拒绝，其余继续因真实数据缺失 fail-closed。没有 live-vetted allocation，因此 paper runner 未启动，禁止用 fixture 代替。
- 14d shadow 启动、gate 评审、合并、推送、M1 放行均由指挥官决定。**M1-A 签名 sidecar / M1-B EVM 执行严格禁止开工。**

## 6. sol 原 M0 验收

测试卫生说明：全量中的 14 个 `legacy_environment_bound` 节点是**精确 nodeid skip，不是 pass**。其中 6 个锁定已结束的 2026-06-05 in-flight PID/4-of-6/固定文件计数，1 个把冻结合法 `COMPRESSED_PASS` 错写成只接受 `PASS`，7 个会把指挥官要求保留的只读 paper PID 1349731 误判为禁用进程。同文件其余测试照常运行；未忽略整文件、未改冻结报告、未改 `scripts/lp_long_horizon/`、未停止进程。精确清单与理由在 `tests/conftest.py::LEGACY_ENVIRONMENT_BOUND_NODEIDS`。

- `pytest tests/ -q`: sol 在 Solana runner 实现后亲跑，`2660 passed, 14 skipped in 37.51s`
- `pytest tests/ --collect-only -q`: sol 在实现后亲跑，`2674 tests collected in 1.06s`，0 error
- 定向 Solana+runner+ledger+RpcPool+gate：`93 passed`
- Base 1-tick + SQLite gate row：完成；输入为显式 `fixture_only_not_live_vetted` 的历史真实 WETH-USDC，只证明集成接线
- Solana Orca account-state 1-tick + 23 字段 + SQLite gate row：完成；live account slot `438047910`，RPC `NORMAL`，`n_swaps=0`、fees=0
- 集成详情与哈希：`reports/lp_m0_integration_smoke/SOL_ACCEPTANCE_20260808.md`
- 最终裁决：WP-10 `DONE`；14d shadow 未启动，gate `FAIL`，M1 **NOT AUTHORIZED**

## 7. sol M0R 复验（2026-08-09）

- `pytest tests/ --collect-only -q`：`2708 tests collected`，0 error。
- `pytest tests/ -q`：`2694 passed, 14 skipped`；14 个 skip 与 D1 追认的精确 nodeid 一致，未新增 skip。
- 防御退出 replay：`reports/lp_defensive_exit_replay/20260809_m0r_acceptance/`，`7/7 PASS`。
- live scanner `--once`：735 个快照、10 个机会评分、0 accepted；公共 Base RPC 为 `DEGRADED`，按 fail-closed 不生成 live allocation。
- RWA collector `--once`：同库新增 20 个 `market_sessions` 行；周末 5 个 xStocks 锚显式 unavailable，Robinhood 5/5 basis 为 NULL。
- runner 1-tick：只用 `fixture_only_not_live_vetted` 验证机械接线，同库新增 1 个唯一 `shadow_positions`；该 fixture 不可用于 14d 启动。
- 红线扫描通过：没有新增私钥、签名、广播、付费端点或明文凭据；未触碰 Go、`scripts/lp_long_horizon/`、M1-A/M1-B。
- M0R 裁决：**PASS / READY FOR COMMANDER LAUNCH**。启动 14d shadow、注入 Telegram 环境并验证首条真实推送仍是指挥官动作；R4 按任务包留到 shadow 第 1 周真实轨迹出现后执行。

## 8. sol M0P 复验（2026-08-09）

- `pytest tests/ --collect-only -q`：`2769 tests collected`，0 error。
- `pytest tests/ -q`：`2755 passed, 14 skipped`；skip 数与 D1 精确清单一致。
- W6 最终代码 live scanner：734 screened、10 resolved/scored、0 accepted；USDC-VVV 九项输入完整，NetCover `0.040912955191278286`、`BELOW_SHADOW`，证明第五闸可计算且未放宽；显式零/伪 provenance 不再受信。
- panel 最终代码临时端口 smoke：无鉴权 `401`、鉴权 JSON/HTML `200`、POST `405`；panel 在读库时并发 scanner 成功写入，访问日志不含 token/query 值，RPC 只显示 origin；unit 仅写入仓库，未安装。
- §12.0 gate：`INSUFFICIENT_EVIDENCE`，0 identities / 0 root pools；当前没有非空 live-vetted allocation，runner 按契约不启动。
- 详细证据：`M0P_ACCEPTANCE_20260809.md` 与 `reports/lp_m0p_acceptance/20260809/`。
- M0P 当时裁决：**PASS / READY FOR COMMANDER REVIEW**。该历史裁决不替代后续 M0F 最终验收；14 天计时仍须先满足本文顶部的“漏斗覆盖可接受 + 指挥官显式决定”双条件，runner 仍须等待真实非空 live-vetted allocation。

## 9. M0F 漏斗可用性轮（2026-08-09）

完整分项数据、目标表、无效试跑与最终验收见 `M0F_ACCEPTANCE_20260809.md`。本节只保留交接所需结论。

- **R1a / R1b：** 逐池确认旧 factory registry、非稳定币 USD quote/AERO 换汇深度、`range>=100%` 数学域与 multi-factory 歧义根因。同分母工程覆盖由 M0P 的 `1/10` 提升到 R1b live `733→10→10→10→0` 的 `4/10` 完整可计算；其中 NetCover 数字全部是 **ADD-1 前口径**，仅用于覆盖率验收，不是最终经济性。
- **ADD-1：** FeeEV 固定锚定 168h 七日证据，并按目标区间的 canonical liquidity share 比例调整；三池 H30/H7 为 `0.491069 / 0.488743 / 0.489191`，接近 `sqrt(7/30)`。USDC-VVV 的 pre-ADD-1 / Task A / Task A+B NetCover 分别为 `0.040912955 / 0.040912955 / 0.005780933`，最终下降被诚实保留。
- **R2 / ADD-2：** 只有 `reports/lp_funnel_rerank/20260809_135500/` 是正式证据：同批 30、完整对 16、Spearman `r=0.473529`、`n=16`、`t=2.011613`、`df=14`、双尾 `p=0.063919`，top-K `7/10`。`r>=0.3` 是业务排序阈值而非显著性检验；因 `p>0.05`，结论降级为“边缘相关，证据不足以强推”。历史 recommendation/生产排序为 `PROXY_NETCOVER` 的事实不变。八个审计目标按 exact chain/project/symbol 扩展到所有 live 匹配，只作研究验证，绝不 allowlist 或绕过 coarse/final gate；`111500`、`113000`、`114000` 三轮已显式作废。
- **P2：** panel 默认 queue/thread `16/16`，工作线程有界、过载 503、弱/重复 token 拒绝并提示 `openssl rand -hex 32`；真实 smoke 为 401/200/405/404、弱 token exit 1、无残留进程。
- **R6：** PASSIVE 的 range-bound/neutral/trending 映射 `168/336/720h`；TACTICAL 映射 `6/24/72h`，12h 只可由固定拖累逻辑从 6h 向上选择。未知或跨 profile 证据 fail-closed。
- **R7：** `.gitignore` 已覆盖 Python bytecode，90 个历史跟踪 `.pyc` 已移出 index，`git ls-files '*pyc'` 为 0。
- **最终 E2E：** scanner as-of `2026-08-09T13:51:03.533470+00:00`，`733→30→30→30→0`；stdout 的 30 个 resolver 输出包含 14 个 fail-closed placeholder，canonical `read_funnel()` 成功 resolve 16。`16/30` finite NetCover 包含 `top=10→30` 的取样窗口扩大效应；工程修复质量仍以同分母 `1/10→4/10` 衡量。14/30 `ambiguous_multi_factory_pool` 当前为 `blocked_pending_authoritative_pool_mapping` 并继续 fail-closed，不代表不可修复的永久关闭；30/30 使用 `PROXY_NETCOVER`。MSUSD-USDC 虽 NetCover `1.010796` 数学 PASS，仍因 `REWARD_PERSISTENCE_MISSING` 与 stable gate false 保持 `vetted/accepted=false`；DB、`score_json`、panel 均显式给出 `ENTRY_INELIGIBLE:REWARD_PERSISTENCE_MISSING`，最终 menu 为空。正式最终证据为 `reports/lp_m0f_acceptance/20260809_reason_fixed/`。
- **最终测试与安全：** collection `2843`、0 error；全量 `2829 passed, 14 skipped in 130.54s`。panel 真实 smoke 401/200/405/404、弱 token exit 1、强服务 Ctrl-C exit 0、无残留，503 专项 `1 passed, 31 deselected`。gate 为 `INSUFFICIENT_EVIDENCE`、0 identities / 0 roots、未关闭严重 RPC 0。四个阈值保护文件、Go、long_horizon 源码和 M1 源码均 0 diff；danger/dependency 0，frozen 今日 mtime 0，PID 1349731 存活且 cwd 正确。

M0F 没有放宽 NetCover/风险阈值，没有启动 daemon 或 14 天计时，没有新增钱包、签名、广播、付费端点或 M1 执行路径。最终裁决为 **PASS / READY FOR COMMANDER REVIEW**；`accepted=0` 是诚实结果，不等于已获准起跑。16/30 覆盖是否可接受、是否起算 14 天 shadow、合并、推送与 M1 放行均由指挥官独立决定。

## 10. M0N 提交流程纪律（FIX-N5）

- 生产代码提交 `3d32989 m0n(fix-N1): correct horizon-scaled LP income` 与 `8a82002 m0n(fix-N2-N4): add reward evidence tracks and Solana fail-closed` 均使用 `FIX` 前缀，与其代码变更性质一致。
- 后续 `DOC` 提交只允许包含文档与报告，不得夹带生产代码或测试变更。
