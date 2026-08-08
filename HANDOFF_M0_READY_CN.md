# LP Bot PRD v2.1 · M0 Shadow 启动就绪交接

**分支：** `feat/prd-v2.1-m0-shadow`

**状态：** WP-00～09 已由 sol 分项验收；WP-10 实现已就位，等待 sol 亲跑全量测试与真实集成 smoke。**14 天 shadow 尚未启动，§12.0 gate 尚未通过。**

**发布边界：** 未合并、未推送远端；等待指挥官 review。本文不构成 M1 放行。

## 1. WP 状态与证据

“配对测试数”是当前目标文件的 collect 数，不冒充全仓验收总数；最终通过数与全量输出由 sol 验收报告填写。

| WP | 状态 | commits | 当前配对测试数 / 验收证据 |
|---|---|---|---|
| WP-00 | DONE | `0600453 3caae9b 88f9a3d 6001355 3156a5f 849a215 10db4d8 e50220c` | vol-range 配对 6；collection quarantine、凭据清除、环境文件 ignore |
| WP-01 | DONE | `68b5bfd 7f42f78 38c66f5` | RpcPool 28；Solana 方法路由/退避/写方法阻断；sol live probe 6/6 UP |
| WP-02 | DONE | `1f98f1a b6379e4 541574c b234bed` | 引擎+replay+runner 46；60 轨迹报告 `reports/lp_il_math_replay/20260808_000000/` |
| WP-03 | DONE | `695fc1b 306699c 22185ed 92a994e 4d01bbb a51e44e 17fc81e 37763ed 0d2f6f0` | policy+replay+runner 59；7/7 replay `reports/lp_defensive_exit_replay/20260808_170228/` |
| WP-04 | DONE | `8deedca a96dfcd 1518c96 e1d6b3a 38b18f0 63c14dc 017700e 5983c55 b481fa2 f46625a` | netcover/cost/funnel/allocator 46；报告 `reports/lp_cost_sensitivity/20260808_172541/` |
| WP-05 | DONE | `2ab4d29 9a4d70c e7017b4 baf683b 4bfabdc` | instrument/anchors/session 38；周末 xStocks quote unavailable 按 fail-closed |
| WP-06 | DONE | `ec1ea15 fd4b6ab 5495410 88144b6 2643f96 bfecb5c 788af85 4d2322a 0c83aae d71ec5a d655306 9e995e9` | scanner+digest 24；真实 `--once` 已落 SQLite，unit 未安装/未启动 |
| WP-07 | DONE | `d63cb15 19f9a0e b80f51c a9f4de3 32cb308 1d3a6ed f1a5dea b425c58 bec89e7` | alerter 13；无 test token，已验 stdout 降级；全局 ≥60s throttle |
| WP-08 | DONE | `7879194 688376c b538af2 e589266` | ledger-v2 12；heartbeat/final 23 字段、退出成本语义、旧 heartbeat 兼容 |
| WP-09 | DONE | `853e590 bc586ad 39aff95 c8d35b0 9f9d5a6 74fc774 cd317fb cda1d0b 184ce07` | reward replay 10；报告 `reports/lp_reward_decay_replay/20260808_173832/` |
| WP-10 | **PENDING_SOL_ACCEPTANCE** | 关键提交 `d3c9c96 7d5a59d f5b4988 44dab96 b8441b1`（TDD 含 `8afbe25 4f4a8be`） | gate 配对测试含零噪声边界；全量与 live smoke 由 sol 亲跑 |

## 2. 指挥官批准后才可执行的启动命令

以下命令**只写在交接中，未执行**。先将 `APPROVED_ALLOCATION` 替换为 sol smoke 后人工批准、非空且确实来自 live-vetted 链路的 Base allocation。不得使用 fixture 启动 14d 观察。

### 2.1 nohup

```bash
cd /opt/lpbot/lp-bot-v3-origin-check
install -d -m 700 reports/lp_scanner reports/lp_shadow_launch
nohup python3 -u scripts/lp_scanner_daemon_v1_readonly.py \
  --db reports/lp_scanner/scanner.db \
  --coarse-interval-secs 900 --top-interval-secs 60 \
  > reports/lp_shadow_launch/scanner.log 2>&1 &
nohup python3 -u scripts/lp_portfolio_paper_runner_v1_readonly.py \
  --allocation "$APPROVED_ALLOCATION" --chain base --poll-secs 1800 \
  --gate-db reports/lp_scanner/scanner.db \
  > reports/lp_shadow_launch/runner.log 2>&1 &
```

不要把 Telegram token/chat 放命令行。若需要 Telegram，只通过进程环境的 `LPBOT_TG_TOKEN` / `LPBOT_TG_CHAT` 注入。

### 2.2 systemd

scanner 有已审计 unit；安装/启用是指挥官动作：

```bash
sudo install -m 0644 deploy/systemd/lpbot-scanner-shadow.service /etc/systemd/system/lpbot-scanner-shadow.service
sudo systemctl daemon-reload
sudo systemctl enable --now lpbot-scanner-shadow.service
sudo systemctl status lpbot-scanner-shadow.service --no-pager
```

paper runner 暂无常驻 unit，避免把 allocation 路径静态写死。指挥官可用 transient unit（命令仍未执行）：

```bash
sudo systemd-run --unit=lpbot-paper-shadow \
  --property=User=lpbot --property=Group=lpbot \
  --property=WorkingDirectory=/opt/lpbot/lp-bot-v3-origin-check \
  --property=NoNewPrivileges=yes \
  /usr/bin/python3 -u scripts/lp_portfolio_paper_runner_v1_readonly.py \
  --allocation "$APPROVED_ALLOCATION" --chain base --poll-secs 1800 \
  --gate-db reports/lp_scanner/scanner.db
```

## 3. scanner → allocator → runner 的可审计路径

```bash
python3 -u scripts/lp_scanner_daemon_v1_readonly.py --once \
  --db reports/lp_scanner/scanner.db \
  --vetted-menu-out reports/lp_m0_integration_smoke/vetted_menu_live.json
python3 -u scripts/lp_portfolio_allocator_v1_readonly.py \
  --ranked reports/lp_m0_integration_smoke/vetted_menu_live.json \
  --total 100 --out reports/lp_m0_integration_smoke/allocation_live
python3 -u scripts/lp_portfolio_paper_runner_v1_readonly.py \
  --allocation reports/lp_m0_integration_smoke/allocation_live/allocation.json \
  --chain base --max-ticks 1 --poll-secs 1800 \
  --gate-db reports/lp_scanner/scanner.db \
  --out reports/lp_m0_integration_smoke/base_runner_1tick
```

- exporter 只接受 SQLite 最新 cycle 中 `accepted=1` 且 score_json 同时证明 `vetted=true`、`netcover_pass=true` 的记录，并加 `scanner_evidence_origin=live_opportunity_scores`。
- 若真实 scanner `accepted=0`，链路应诚实停在 0 allocation；这是有效结果，不得用 fixture 冒充 live-vetted。
- 审计 fixture 只允许标 `fixture_only_not_live_vetted`，用于验证 bridge/allocator 机械接线。
- sol 的完整 stdout/JSON 承载位置：`reports/lp_m0_integration_smoke/PENDING_SOL_SMOKE.md`。
- Solana 仅可经 WP01 RpcPool 做 `getSlot` / `getAccountInfo` 真实探活。当前 Python runner 没有 Raydium/Orca swap decoder，不能宣称完成 Solana LP 1-tick；这是已知 coverage gap，不以模拟数据遮盖。

## 4. §12.0 gate 报告读法

runner 每个成功 tick 自动写同一 `scanner.db`：

- `shadow_positions`：按唯一 `(source_run, position_identity)` 计模拟仓，重复 tick 不增加仓数。
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
- Reward persistence 缺失/无效/负值 fail-closed；`<6h` 不 ENTER，6–24h haircut，≥24h 才 trusted。
- Telegram 未配置 `LPBOT_TG_TOKEN/LPBOT_TG_CHAT` 时降级 stdout、不崩溃；尚未发送真实测试消息。旧 Telegram token 必须由指挥官在外部立即轮换，禁止在报告/commit 回显旧值。
- Base public RPC 与 Solana public RPC 都有可变限流；没有付费 fallback。任何付费 RPC 只允许生成建议报告，必须指挥官人工批准。
- 当前 Solana coverage 是 registry + 真实只读 slot/account，不是 runner CLMM swap/fee tick；M0 不允许借机实现 M1 TS sidecar。
- Raydium 市场快照是单次 top-1000 page，`hasNextPage=true`，页外池 unavailable/unverified；Orca 当次 page `next=null`。详见 `MARKET_SNAPSHOT_M0.md`。
- Cost sensitivity 使用历史 swap/模型参数，不保证未来收益；已验收的历史结论是 25U 不经济，50U 起才在该样例过 gate。
- 14d shadow 启动、gate 评审、合并、推送、M1 放行均由指挥官决定。**M1-A 签名 sidecar / M1-B EVM 执行严格禁止开工。**

## 6. sol 最终验收待填

- `pytest tests/ -q`: `PENDING_SOL_ACCEPTANCE`
- `pytest tests/ --collect-only -q`: `PENDING_SOL_ACCEPTANCE`
- Base live 1-tick + SQLite gate row: `PENDING_SOL_SMOKE`
- Solana WP01 slot/account probe: `PENDING_SOL_SMOKE`
- 红线扫描与 diff review: `PENDING_SOL_ACCEPTANCE`
- 最终裁决：`PENDING_SOL_ACCEPTANCE`
