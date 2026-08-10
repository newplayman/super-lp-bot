# TP-E 验收：股票代币宇宙 + A/B/C 三档 + Solana 执行解禁

按当前真实链上验证口径（而非 DefiLlama 收益转述），保守宇宙 A/B/C 分别 91/10/15 池，能过各自完整终闸的是 **0/0/0**；Solana 68 池中 59 池成功解析并通过 pool owner、program executable、vault 与 mint owner 校验，但全部是 CLMM 且缺完整区间回放，不能放行。
Solana sidecar 的确定性“构建 + `simulateTransaction`”管线测试通过，三大 DEX program 也已在主网验证；但候选级主网 dry-run 因 `accepted=0` 且没有真实钱包余额证据而**没有走通**，本轮签名 0、广播 0。
C 档当前 15/15 池已落第一笔只读观测，跨度 0 小时、满足 ≥48h 持续性的池为 0；独立小时采样进程已启动，现阶段不能对收益可持续几天作结论。

## 验收结论

| FIX | 结论 | 核心证据 |
|---|---|---|
| E1 股票宇宙 | **PASS** | 117 个保守识别池；发行商/标的/协议/分档落表；5 池人工核对；unknown 与刷量嫌疑如实报告 |
| E2 AMM 路径 | **PASS** | v2 IL、无 CLMM range/share_ratio、仓位摊薄、720h 上限、协议错配 fail-closed 均有测试 |
| E3 Solana sidecar | **PARTIAL** | 安全契约与主网 program 验证完成；无合格候选/钱包证据，故候选级公网 simulation 未宣称成功 |
| E4 A/B/C 闸 | **PASS（通过数 0）** | A/B 保留既有合取；B 加双边波动；C 七闸完整且缺证据拒绝；采用方案 1（5U/20U） |
| E5 小池仓位 | **PASS（可投资仓位 0）** | 股票粗筛 20k；0.05%/0.10% 不变；117 池逐池报告；无实测深度的仓位为 0U |
| E6 C shadow | **IN PROGRESS** | 15/15 初始样本，0h/0 个 48h；独立进程持续小时采样 |
| E7 Solana Stage-2 | **PARTIAL** | 59/68 链上身份验证；真实协议聚合与 3 笔 SPYX-SSX swap 回放；CLMM 完整 IL replay 尚缺 |

整体判定：**TP-E 部分通过。** 工程安全边界已经具备，但 E3 候选 dry-run、E6 的 48h 时间条件和 E7 的 CLMM 完整链上经济回放均未达到硬验收，因此“Solana 执行解禁”当前只表示代码路径完成并保持双开关锁定，不代表实盘许可。

## E1：当前股票代币宇宙

当前免费 DefiLlama 快照 15,594 条记录，经“允许漏、不允许错”的显式 instrument 目录与 DEX/TVL≥20k 约束后得到 117 池：

| 档 | 当前池数 | Solana | 定义 |
|---|---:|---:|---|
| A | 91 | 43 | 股票 × 稳定币 |
| B | 10 | 9 | 股票 × 主流币 |
| C | 15 | 15 | 股票 × 其他 |
| 股票×股票 | 1 | 1 | 独立研究类，不套 A/B/C 预算 |

- `issuer=unknown`：33 池；unknown instrument 33 个。unknown 不会被拿去与 Backed/Ondo/Robinhood 同标的混算 basis。
- `vol1d/TVL > 1.5`：7 池。SPYX-SSX=1.8997、SPYX-STONK=1.8168，均命中刷量嫌疑。
- 5 池人工复核的 issuer 与协议类型全部正确，详见 `MANUAL_REVIEW_5.md`。
- 当前是 117 而非调研的 126：识别器拒绝把所有 `*X/*ON` 泛化为股票（例如 GMX/FLUX），且市场快照已漂移。这个差异没有通过猜测补齐。
- 调研把 `raydium-amm` 统一视作恒定乘积；当前 52 个股票 Raydium 记录的 `poolMeta` 全为 `Concentrated`，官方协议 API 也返回 CLMM program。因此当前这些池严格标成 `clmm`，不按 project slug 猜架构。

证据：`reports/lp_stock_token_universe/20260810_e1/`。

## E2：恒定乘积与 CLMM 分派

- `protocol_type` 只接受 `amm_constant_product` 或 `clmm`；unknown、声明路径与调用路径不一致均 fail-closed。
- AMM IL 使用 `2√k/(1+k)-1` 的损失幅度；k=1 为 0，k=4/0.25 为 20%。
- AMM fee EV 为 `size × fee_apr × haircut × H/8760 × TVL/(TVL+size)`；最后一项保留新增仓位带来的池占比摊薄，不乘 CLMM `share_ratio`。
- AMM 无区间、出界或集中度输入；holding horizon 上限固定 720h，超过即缺项拒绝，防止 H 成为免费杠杆。
- 在固定价格路径与固定成本下，测试验证 AMM NetCover 随 H 单调递增。

当前股票 Raydium 样本都是 CLMM，所以 E2 的 AMM 实现是能力储备，未被错误用于这批候选。

## E3：Solana sidecar

### 安全契约

- action 白名单：`open/increase/decrease/collect/close/swap`；Raydium AMM v4、Raydium CLMM、Orca Whirlpool program 显式映射。
- 硬编码 program 不是信任根：每次计划都要用 `getAccountInfo` 验证 executable、loader owner 与 slot；交易中实际调用的 program 必须和 protocol/action 一致。
- `LIVE_TRADING=false` 默认；环境开关 + 启动确认串双开关必须在 signer 之前通过。
- raw secret 环境变量拒绝；加密 keystore 只允许外部 signer 边界；0600/owner 校验。
- 单笔/daily cap、滑点、deadline、blockhash 余量、pool/mint allowlist、三个决策/idempotency 字段、最终 ledger 回填全部 fail-closed。
- kill switch 进入 `EXIT_ONLY`，只允许 decrease/collect/close 与明确减风险的 swap。
- Token-2022/Scaled UI 将 raw、accounting、UI 三种数量分开；价格必须声明 per-UI 或 per-accounting，未来 multiplier 按链上生效时间切换。

### 主机与主网证据

- `lpbot-solana-executor` 与 `lpbot-strategy` 是不同的 nologin 用户；策略用户不能读取 executor keystore。
- `/etc/lpbot-solana-executor`、`/var/lib/lpbot-solana-executor` 为 0700；keystore/password 为 0600、0 字节空占位，没有生成密钥。
- systemd unit 已安装但 `disabled/inactive`，`LIVE_TRADING=false`。
- Raydium AMM/CLMM、Orca 三个 program 在 slot 438427989 均 `executable=true`，owner 是 upgradeable BPF loader。
- Token-2022 program 使用官方 `Tokenz...PxuEb`；Orca 使用链上 pool owner 对应的 `whir...uctyCc`，均有常量回归测试。

确定性 dry-run 测试覆盖完整构建和模拟成功返回；真实候选级 mainnet simulation 没有通过，因为五检中的 accepted candidate 与 wallet balance 不存在。没有用假余额或任意指令伪造 PASS。

证据：`reports/lp_solana_m1_dry_run/20260810_e3/`。

## E4：A/B/C 配置与 C 七闸

采用任务包默认方案 1：A 预算≤50U、B≤30U、C 总敞口≤20U；C 单仓≤5U，不修改 −10U 总 KILL。

- A：91/91 缺完整既有终闸合取和绝对利润证据，0 通过；其中 32 个 issuer unknown 还缺 instrument 归一化。
- B：10/10 缺既有终闸、绝对利润和双边波动加严证据，0 通过；1 个 issuer unknown。
- C：15 池的 5U/20U 预算本身均不超限，但退出回放、非池持有人集中度、卖出 simulation、48h 持续性、配对腿币龄与 ≤200bps 深度退出均未形成完整证据，0 通过。

C 持有人采集器已实现 `getTokenLargestAccounts` + mint supply，并只排除已链上确认的本池 vault；现有免费 RPC 实测分别返回 429、超时或未启用 Program-Id index，因此本轮 15 池全部按缺证据拒绝，没有用第三方估值替代。

完整机器判定：`reports/lp_stock_tp_e/20260810/tier_acceptance.json`。

## E5：20k 粗筛与逐池仓位

规则保持：

`PositionCap = min(档位上限, TVL×0.0005, 实测退出深度×0.02, TVL×0.001)`

以及：

`ExpectedNetProfit ≥ max(1U, 5×RoundTripCost)`

股票专用 Stage-1 粗筛降到 20k，只扩大“进入链上核验”的候选集合；0.05% 常规占比、0.10% 硬上限与绝对利润闸均未改变，所以不是放宽最终闸。

117 池均有逐池行。由于当前 59 个已解析 Solana 池都是 CLMM，尚无完整 range/active-depth/IL 回放；其余池也没有对应 Stage-2 深度，故不把 DefiLlama TVL 猜成退出深度，117 个仓位均为 0U、绝对利润通过 0。证据：`reports/lp_stock_tp_e/20260810/e5_position_report.json`。

## E6：C 档收益持续性

- 当前 C 池：15；已观测：15；≥48h：0。
- 第一笔 SPYX-SSX：APY 2828.71%、TVL 31,555、24h volume 59,946；附 3 笔真实 swap 抽样。
- 当前 C 最高初始 APY 为 28,700.31%，但单点高收益不等于持续收益。
- 观测跨度 0h，因此套利抹平、激励耗尽或 rug 三种原因现在都不能归因。
- 独立 `lpbot-strategy` 只读进程 PID 3783076 已按 3600s 周期运行；运行库位于 `/var/lib/lpbot-strategy/stock-tier-c-shadow/`。

E4 的 ≥48h 闸只接受本地至少 3 个样本且跨度≥48h、收益保持初始值 50% 以上的证据；DefiLlama 的 rolling 7d/30d 字段不冒充本地观测。

## E7：Solana Stage-2

- Solana universe：68（A43/B9/C15/股票×股票1）。
- 官方 Raydium/Orca pair API + TVL 唯一匹配：59；随后 59/59 通过链上 owner/executable/vault/mint 验证。
- 未解析 9：7 个缺精确两腿地址，2 个官方池 TVL 与快照差异超过 15%；均未猜地址。
- 解析结果：59 个均为 CLMM；A/B/C 链上身份验证数分别 34/9/15。
- RPC 终态 `NORMAL`（6/6 free endpoints，无 impaired）。
- SPYX-SSX bounded replay：3/3 最近交易识别为真实 swap；链上确认 TVL 31,427.78、24h volume 57,345.06、重算 fee APR 2717.146%。
- INTCX-USDC：TVL 36,224.98、重算 fee APR 117.699%；WSOL-SPYX：128.535%；SPYX-STONK：625.477%。这些是协议真实聚合并经链上身份交叉验证，不是最终收益承诺。

所有池仍因 CLMM range/active liquidity/完整 swap-path IL replay 缺失而 `stage2_pass=0`。高 APR 没有绕过经济模型或 E4 专属风险闸。

证据：`reports/lp_stock_tp_e/20260810/stage2.json`、`stage2_swap_replay_spyx_ssx.json`。

## 仍需完成

1. E6 累积满 48h 后重算 15 个 C 池的收益衰减与原因归因。
2. 为当前 CLMM 股票池补 position range、active liquidity 与完整 swap replay，才能计算真实 IL/NetCover/退出深度。
3. 获取可核验的 Solana 非池持有人集中度、币龄和卖出 simulation；免费 RPC 缺索引时继续拒绝。
4. 出现完整过闸候选且指挥官配置真实钱包余额后，执行候选级 mainnet `simulateTransaction`；仍不得签名/广播，除非逐次另行放行。

## 回归验证

- Python 全量：`3068 passed, 14 skipped`。
- Go 全量：`go test ./...` 通过。
- 补丁完整性：`git diff --check` 通过；提交前继续以精确路径暂存，排除原有 `.gitignore`、历史报告、Polymarket 文件与 C 档运行时 SQLite 数据库。

## 安全

- 保护 PID 1349731、2077656、2082408 未停止或重启。
- 新增 E6 只读进程不加载钱包。
- 真实钱包/私钥生成 0；keystore 加载 0；签名 0；广播 0；付费服务 0；git push 0。
