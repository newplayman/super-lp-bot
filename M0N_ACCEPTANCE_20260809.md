# M0N 收入建模修正 + reward 证据双轨验收

**日期：** 2026-08-09

**任务包：** TP-M0N-v1

**分支：** `feat/prd-v2.1-m0-shadow`

**裁决：** **PASS / READY FOR COMMANDER REVIEW**

本裁决表示 N1 收入公式与 N2 reward A+B 双轨已通过技术验收；不表示已启动 14 天 shadow，不授权 runner、签名、广播、合并、推送或 M1。14 天起算仍要求指挥官显式下令。

## 1. 交付提交与流程纪律

| commit | 性质 | 验收 |
|---|---|---|
| `3d32989 m0n(fix-N1): correct horizon-scaled LP income` | 生产输入装配器 + 配对测试 | FIX 前缀正确 |
| `aaf195b m0n(fix-N1): add reproducible income evidence` | 只读复现工具、配对测试与锁定报告 | N1 同一证据目的 |
| `8a82002 m0n(fix-N2-N4): add reward evidence tracks and Solana fail-closed` | N2/N4 生产逻辑 + 配对测试 | FIX 前缀正确 |
| `352c148 m0n(fix-N3): correct coverage and correlation claims` | HANDOFF + correlation 报告 | 无生产代码 |
| `77c327b m0n(fix-N4): record Solana fail-closed evidence` | Solana JSON/Markdown 报告 | 无生产代码 |
| `a08b74f m0n(fix-N2): enforce reward entry veto at terminal gate` | 对抗验收发现后的生产补丁 + 配对测试 | FIX 前缀正确 |

本报告与最终 HANDOFF 更新使用单独文档提交，不夹带生产代码。

## 2. FIX-N1：收入项建模

最终装配公式为：

```text
share_ratio(H) = share(range(H)) / share(range(168h))
fee_ev_usd     = size × fee_apr_pct / 100 × fee_haircut × (H/8760) × share_ratio(H)
reward_ev_usd  = size × reward_apr_pct / 100 × (H/8760) × share_ratio(H)
```

Reward category/persistence haircut 仍在 engine 侧乘一次，输入装配器不重复乘。`position_liquidity_raw`、range policy 与 raw-liquidity share 算法未改；σ 缺失时 fee/reward 两项继续 fail-closed。

锁定报告：`reports/lp_m0n_income_validation/20260809_n1/income_validation.{json,md}`。源 DB 的 canonical logical digest 为 `31d346ba250842c67283a0f0bb73aff8b3b8885aca42a0964e80ff62ca39e2b0`，as-of `2026-08-09T11:56:19.991045+00:00`，47 条 score_json 逐行哈希均写入 JSON。报告还披露了普通 SQLite 读取误触 WAL checkpoint 的过程；逻辑内容未变，后续生成器固定使用 `mode=ro&immutable=1`。

### 2.1 机械比例

理论 `sqrt(720/168)=2.07019667803`，验收容差为相对 ±5%。

| 组 | 池 | FeeEV 720/168 | RewardEV 720/168 | 结果 |
|---|---|---:|---:|---|
| reward | VCHF-USDC | 2.081065 | 2.081065 | PASS |
| reward | WETH-AAVE | 2.084539 | 2.084539 | PASS |
| reward | WETH-USOL | 2.087905 | 2.087905 | PASS |
| no reward | WETH-CBBTC | 2.076271 | N/A（reward=0） | PASS |
| no reward | USDC-VVV | 2.105664 | N/A（reward=0） | PASS |
| no reward | WETH-USDC | 2.078290 | N/A（reward=0） | PASS |

没有任何收入项出现错误的线性 `4.286×` 或丢失时间因子的约 `0.49×`；reward=0 明记 N/A，不计算 0/0。

### 2.2 NetCover 形状与对照

- VCHF-USDC 与 WETH-AAVE 在 336h 出现内部最优；WETH-USOL 的 `H*` 位于 168h 以下，因此网格内单调下降。
- 三个 no-reward 样本在当前三档仍单调上升；报告逐池给出 IL、固定成本与 `H*=c/b`，没有把边界最优包装成内部最优。
- USDC-USDT 的 M0F/N1 H720 NetCover 为 `0.320461792→0.167696862`：reward 加上 share penalty 后下降。
- USDC-VVV 的 M0F/N1 H720 NetCover 为 `0.154034731→0.660148846`：reward 始终为 0，差异仅来自恢复 fee 的 H 时间因子。

## 3. FIX-N2：reward persistence A+B 双轨

### 3.1 B 轨（单次 DefiLlama 快照）

DefiLlama 的 `apyMean30d`、`apyBase7d` 与变化百分比描述总 APY/错配窗口，不是 reward-only 实测历史；`count` 也不作为真实 reward 持续时长。实现因此只给有限信任：

| 档位 | entry | factor | 最高信任 |
|---|---:|---:|---|
| `SURROGATE_STRONG` | 可继续接受其余闸评估 | 0.25 | 仅 6h-equivalent，永不 trusted |
| `SURROGATE_WEAK` | 否，仅 shadow | 0 | fail-closed |
| `SURROGATE_ABSENT` | 否（fee-only 除外） | 0 | fail-closed |

每条记录显式写 `reward_persistence_evidence_source=surrogate_defillama/absent`；surrogate 不填 canonical measured duration。

### 3.2 A 轨（scanner 自有观测）

`scanner.db` 新增 `reward_observations(as_of,pool,chain,apy_reward,apy_base,tvl_usd,source)`。正式 Base 当轮落 30 行，Solana 当轮落 100 行；与 snapshot/score 同事务写入。判定 cutoff 在 screen 前冻结，查询严格 `as_of < cutoff`，所以当轮 observation 不能给自己作证。

真实持续时长按 pool UUID + chain 隔离，只计算正 reward 的连续 suffix；至少两样本，最大 gap 0.5h，零/无效/gap/stale 都会截断或失效。只有 scanner 自有历史连续满 24h 才覆盖 B 轨并成为 `TRUSTED_24H`、factor 1.0；少于 24h 回 B 轨。SQLite 重启后历史保留。外部预填 `999h + measured_observation` 会在 scanner ingress 被剥离。

### 3.3 对抗验收发现与修复

独立探针发现旧终闸只合取前四闸和 NetCover，没有再次合取 `entry_eligible`；若 WEAK/ABSENT 的其余闸全部通过，理论上可被错误 accepted。该问题在正式 Base 证据前被发现，旧批次 `reports/lp_m0n_acceptance/20260809_base_once/` 立即作废并停止；其数据库只有 schema、0 score，不作为证据。

`a08b74f` 修复两层边界：

1. `_enforce_fifth_gate` 的最终 `vetted = prior_vetted && netcover_pass && entry_eligible is not False`，且 pre-NetCover 的 entry 位与 block reasons 为权威，终端适配器不能翻转或清空；
2. `_score_row` 再以同一 entry veto 保护数据库 `accepted`。

回归证明 STRONG 在其他闸通过时仍可接受；WEAK/ABSENT 即使 NetCover 数学 PASS 也保持 false，并保留精确 `ENTRY_INELIGIBLE:*` 理由。

## 4. FIX-N3：表述与统计

- 工程修复质量采用同分母 `1/10→4/10`；`16/30` 明确包含 `top=10→30` 的采样窗口扩大效应。
- 正式相关报告补齐 `r=0.473529411765, n=16, t=2.011613379223, df=14, two-sided p=0.063919071827`。
- `r>=0.3` 是预设业务排序阈值，不是统计显著性检验；`p>0.05`，结论降级为“边缘相关，证据不足以强推”。
- 14 条歧义记录的工程状态改为 `blocked_pending_authoritative_pool_mapping`；历史数据库中的原始 `PERMANENT_FAIL_CLOSED` 字符串不篡改。

## 5. FIX-N4：Solana TACTICAL 生产诊断

正式证据：`reports/lp_m0n_n4/20260809_solana_once_top100/`。

```text
[scanner] as_of=2026-08-09T15:48:44.753135+00:00 screened=1958 top=100 resolved=100 scored=100 accepted=0 sessions=0
[scanner] vetted_menu exported=0 invalid=0 out=.../vetted_menu.json
```

- Raydium 94、Orca 6；100/100 `profile=TACTICAL`。
- 100/100 `authoritative_pool_mapping_missing`，逐池 status 为 BLOCKED/fail-closed。
- `holding_horizon_hours`、source 与 ER-policy H 100/100 为 `None`；没有把 DefiLlama UUID/symbol 猜成链上 pool account，也没有调用 EVM RPC/Q96 路径。
- reward observations 100；reward source 为 absent 99、surrogate strong 1；accepted 0、菜单 `[]`。
- DB SHA-256 `56dea0aa606de04f1d56c4f42ca9a321380c30f19b0df14e165c760643fa6846`；menu SHA-256 `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`。

本项 PASS 的含义是“真实候选能完成一轮并逐池给出诚实根因”，不是“Tactical H 已由真实链上证据算出”。缺少权威 UUID→Solana pool account 映射及协议适配器仍是已知限制。

## 6. 修复后 Base 正式 E2E

正式目录：`reports/lp_m0n_acceptance/20260809_base_once_postfix/`。

```text
[scanner] as_of=2026-08-09T16:14:33.474230+00:00 screened=730 top=30 resolved=30 scored=30 accepted=0 sessions=0
[tg-fallback] event=rpc_degraded ... UNKNOWN -> DEGRADED; new entries blocked
[scanner] vetted_menu exported=0 invalid=0 out=.../vetted_menu.json
```

| 指标 | 结果 |
|---|---:|
| pool snapshots | 730 |
| opportunity scores / reward observations | 30 / 30 |
| finite NetCover | 16/30 |
| NetCover PASS / vetted / accepted | 0 / 0 / 0 |
| entry eligible | 14/30 |
| surrogate strong / weak / fee-only N/A | 12 / 16 / 2 |
| mapping blocked / NetCover below / reward weak | 14 / 9 / 7 |

逐池明细由同目录 `base_acceptance.{json,md}` 锁定。关键目标池：

- MSUSD-USDC（resolved `0x7501...10fb`）：M0F `REWARD_PERSISTENCE_MISSING` → M0N `SURROGATE_STRONG`、source `surrogate_defillama`、factor 0.25、entry true；最终因 NetCover `0.419744309<1.0` 为 `NETCOVER_BELOW_SHADOW`。stable 亦为 false，accepted 0。
- canonical USDC-CBBTC（resolved `0x4e96...e778`）：M0F `REWARD_PERSISTENCE_MISSING` → M0N `SURROGATE_WEAK`、factor 0、entry false；最终精确理由 `ENTRY_INELIGIBLE:REWARD_PERSISTENCE_SURROGATE_WEAK`，NetCover `0.107043792`，accepted 0。
- 另两条 USDC-CBBTC DefiLlama leads 仍因 multi-factory 歧义为 `blocked_pending_authoritative_pool_mapping`，没有猜映射。

正式 scanner DB SHA-256 为 `1e546b7a61f5b104ddba6b20fa65c8b402ab3550981db6daf394b151db1be8ea`；空 menu SHA-256 为 `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`。

## 7. Gate、测试与红线

Gate stdout：

```text
INSUFFICIENT_EVIDENCE reports/lp_m0n_acceptance/20260809_base_once_postfix/gate_report.md
```

0 unique position identities、0 unique root pools；duration、fee error、PnL、drawdown 均 UNKNOWN；未关闭严重 RPC incident 为 0、该子闸 PASS。gate JSON/Markdown SHA-256 分别为 `b7a71eed7078118becea5950c8899b6374e44841999c2b8f3494f79787d54ad9` / `eb7dcae804cb07bd078bc26cbe7e04e1ceac9dfb34239ae949a666326cf4208e`。

- 全量：`2858 passed, 14 skipped in 140.81s`；总计 2872 tests，0 collection error。14 skips 仍是既有精确历史环境 nodeids，没有新增 skip。
- N1/N2 独立定向复核 120 passed；终闸联合相关回归 188 passed；N4 相关测试及 DB 交叉断言通过。
- 相对 `1e207af`，任务包点名的三个阈值保护文件 `lp_netcover_engine`、`lp_tier_range_policy`、`lp_multiwindow_stability` diff 为空。
- Go、`scripts/lp_long_horizon/`、M1、依赖清单与 `/opt/lpbot/lp-bot-v3` 封存仓均 0 改动；tracked `.pyc=0`。
- 新增生产差异无私钥、签名、approve、广播、写交易、付费端点、明文凭据或新依赖。
- 既有 paper PID `1349731` 存活，cwd `/opt/lpbot/lp-bot-v3-origin-check`；正式 Base/Solana `--once` 均已退出，没有启动常驻 scanner、panel 或 runner。

## 8. 最终裁决与启动边界

**PASS / READY FOR COMMANDER REVIEW。** N1 公式与机械比例通过；N2 A+B 双轨可审计、surrogate 不能冒充 measured，且对抗验收发现的终闸 entry 漏洞已修复；N3/N4/N5 均按任务包收口。`accepted=0` 是当前候选的映射、reward 证据与 NetCover 各闸给出的诚实结果，不作为失败，也不被人为改阈值；同轮另行观测到 RPC `DEGRADED`，但不把它冒充某条 score 的拒绝原因。

N1+N2 技术验收条件已经满足，但 **14 天 shadow 仍未开始**：还缺指挥官显式命令。HANDOFF 只写入“采数模式”命令，没有执行；runner 仍要求非空、人工批准且来自 live-vetted 链路的 allocation。M1-A/M1-B 继续禁止开工。
