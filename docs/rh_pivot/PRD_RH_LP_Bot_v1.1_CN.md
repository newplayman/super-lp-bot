# LP-Bot → Robinhood Chain 三资金桶增量转向 PRD v1.1

**副标题：基于现有 Python 只读研究管线、SQLite 与受限执行器的可执行改造规范**

| 项目 | 内容 |
|---|---|
| 文档日期／外部资料核对日 | 2026-09-07 |
| 设计输入 | B1《PROJECT_STATE_AND_ARCHITECTURE_20260907_CN.md》；B2《Robinhood_Chain_LP_Bot_50_30_20_全面转向设计文档_v1.0.md》 |
| 本版定位 | 对 B2 的工程落地修订，不是另起炉灶，也不是生产部署完成报告 |
| 默认运行模式 | READONLY；满足数据门槛后可运行隔离 SHADOW；LIVE 仍锁定 |
| 执行基线 | B1 报告的唯一活仓库 `/opt/lpbot/lp-bot-v3-origin-check`，分支 `feat/prd-v2.1-m0-shadow`，HEAD `1e1d9bd`；接手时必须复核 |
| 业务目标 | 找出小资金能够实际执行、扣全成本后仍有正收益证据的 LP 机会，而不是让三桶满仓或提高候选通过率 |
| 资金说明 | 现有已批准 M1 为 100U；50/30/20 为新策略预算设计，不自动替代旧资金权限 |
| 交付对象 | 主控 Agent／`qwen-task` 实施代理／只读审计代理／项目所有者 |

> **最重要的执行结论：保留原项目，新增 RH 研究支线；先修证据与经济评估闭环，再做少量 CORE 池的执行接入。STOCK 独立毕业，MEME 默认观察。没有合格池时，50/30/20 可以全部闲置。**
>
> 本文对 B1 的代码、进程、测试及资金状态采用“上传审计报告所述”，未直接登录该服务器复测。外部文档与网页查阅已完成；本次云端容器的直接 HTTP/RPC 探针遇到 DNS 解析失败，未取得实时链上合约、回执和 gas 样本。**这不是 RH 停机证据。** 链上证明必须由执行 Agent 在实际环境补齐，不能把本文中的地址种子当作实盘白名单。

## 阅读与证据约定

- `[B1 §n]`、`[B2 §n]`：两份用户上传文档的章节；其报告事实不等于本次重新实测。
- `[Rnn]`：本次核对的外部来源，完整索引见 §27。市场快照是网页观察，不是同一区块的链上审计。
- **“要求／本版规定／建议初值”均为本 PRD 的设计决定**，不是声称某公开项目已经实现或验证了这些能力。
- `PASS` 只说明某项验收通过；`edge_proven` 只能由独立、全成本、样本外证据升级。文档验收、单测通过、模拟成功都不等于盈利证据。

---

## 0. 本次转向批准什么，不批准什么

### 0.1 设计方向

保留 B2 的三个核心想法：资产按 CORE／STOCK／MEME 区分；50/30/20 是可闲置的风险预算；决策以可审计净收益与退出能力为中心。改变的是实施底座、资金授权方式、会计公式与上线顺序。[B2 §1–2、§53]

本版第一条真实业务闭环是：

```text
已验证的 RH 公共 AMM 池
  → 链上价格／流动性／净 LP 手续费证据
  → 实际仓位与持有期的完整往返成本
  → 终闸合取与“为何不通过”诊断
  → 可复现 Shadow 账本
  → 单独审批的极小额执行验证
```

**不把“RH 很热”当收益证明，不把“旧链 accepted=0”当 RH 无机会的证明。** 旧结论只适用于其已评估资产、时间窗、成本和资金限制；缺输入的候选尤其不能当成经济证伪。[B1 §9–10]

### 0.2 操作授权保持原状

现在可推进：文档、只读诊断、固定快照回放、增量只读脚本与配对测试、离线交易构造／本地模拟设计。禁止把这些操作扩展为真实签名、广播、生成私钥、资金转移、购买服务或启动旧 canary。

B1 的以下边界原样保留：[B1 §11]

1. 不重启／停止既有 paper runner、scanner、watchdog、断链记录器；不碰封存仓库和冻结的 `scripts/lp_long_horizon/`。
2. 不改六个受保护常量，不通过放宽阈值制造候选；不改现有已批准资金参数；不 `git push`。
3. 不删除或削弱旧测试，不清理其他项目数据，不对正在写入的旧 SQLite 做 `VACUUM`。
4. 不接入付费 RPC／数据服务；不把免费账户的存在当作该账户已经获批或配置完毕。

执行开发后续可以分包评审，但任何真实资金动作必须有**独立、限额、限时、绑定配置摘要的所有者授权**，不能凭“PRD 已同意”自动解锁。

---

## 1. 与转向稿 v1.0 的关键差异及决策

| 编号 | 原文／工程冲突 | 本版处理 | 原因与验收重点 |
|---|---|---|---|
| D01 | B2 按 Go／Rust／PostgreSQL／NATS 设计；B1 活跃实现是 Python＋SQLite | Python 增量支线；Go 冻结；沿用现有面板服务 | 不为新链重建服务栈；P0 建立真实文件与依赖图 |
| D02 | 100U 旧单仓 50–60U，但 CORE 新部署上限只有 42.5U | 新资本政策仅作 SHADOW 提案；LIVE 返回 `CAPITAL_POLICY_CONFLICT` | 必须明确替代旧最小仓位的审批，不能悄悄取较宽条件 |
| D03 | `Fee−IL−AS−滑点−冲击…` 可能重复扣损 | NAV＋外部现金流为唯一实际 PnL；IL／LVR／markout 为不同基准归因 | 同一损失只能进实际总账一次 |
| D04 | 将所有 CORE HODL 固定为 50/50 | 主基准使用实际初始 token 数量；50/50 仅可另作策略对照 | 集中流动性初始库存不一定 50/50 |
| D05 | 单一 `pool address`／factory 发现路径 | V3 用 factory＋pool address；V4 用 PoolManager＋PoolKey＋PoolId | V4 单例合约余额不能当单池 TVL |
| D06 | 直接优先 sequencer、默认原子退出 | 先证明广播和回执能力；原子退出是可选优化，分步减仓是必须支持的退路 | 直连不等于私有交易或免 MEV；swap 失败可能使原子撤池一起回滚 |
| D07 | 股票时段主要区分 RTH／盘外／周末 | 补 HOLIDAY、OVERNIGHT、UNKNOWN；时段与健康状态分开 | 2026-09-07 本身就是美国劳动节休市日 [R10] |
| D08 | API 元数据按单一固定结构读取 | 新旧 schema 双适配，未知枚举保留 UNKNOWN | 本次官方 `/assets` 实际返回结构已不同于文档示例 [R04–R05] |
| D09 | AMC 成为默认股票样例／重心 | AMC 只读事件观察；首个股票策略选择数据完整、可退出的 ETF／高流动性股币 | 不把热度、发行方身份或参考价当可兑付套利权 |
| D10 | MEME 同时 4–10 池；单池仅总资金 0.5–2% | 观察名单有上限；首轮 MEME 不进 LIVE；经济下限大于风险上限即闲置 | 小资金与免费 RPC 不适合大量尘埃仓位 |
| D11 | 风险／PnL 放在较后开发 | 资金闸、证据终闸、账本先于策略执行 | 避免策略已能发单但账本和退出能力尚未形成 |
| D12 | 废除多链／协议集中度限制 | 不删共享旧限制；新增 RH 专用政策，显式处理冲突 | 单链定位不等于单链、单协议、USDG 风险消失 |
| D13 | STOCK/STOCK 上限有 15% 与 10% 两种 | v1.1 不进 LIVE；后续只允许较严格的 ≤股票桶10%且≤总资本3% | 不借文档歧义扩大授权 |
| D14 | CORE 既禁止借桶，又作为其他桶缓冲 | 不得跨桶借资；共享钱包只是托管方式，不改变账本归属 | 任何跨桶转拨均需政策版本与显式授权 |

---

## 2. 当前工程基线与复用范围

### 2.1 现状不是待实现的空白工程

B1 报告：Python 只读研究脚本 101 个；独立执行目录有 Base／Solana 执行器但从未签名广播；Go 层冻结；SQLite scanner 持续采集。基线测试为 Python `3109 passed / 14 skipped`，Go `57 packages ok`。这些是接手复核目标，不是本 PRD 重新测试的结果。[B1 §1、§3、§8]

**最高优先级遗留问题**是 scanner 73–80% 记录因 `factory_registry_probe_incomplete` 无法计算，以及“字段没有生产者却被判经济失败”的假阴性。不能换链以后复制相同故障。[B1 §10.1–10.3]

### 2.2 文件级复用与新增规划

以下“现有文件”来自 B1，准确接口与行号由 P0 复核；“新文件”是建议路径，不声称已经存在。

| 现有文件／区域 | 复用点 | RH 改造边界 |
|---|---|---|
| `scripts/lp_rpc_pool_v1_readonly.py` | 端点健康、退避、按方法限流、健康快照 | 扩展链配置与方法能力；增加 provider 独立性和错误原因；不复制失败探针 |
| `lp_universe_screener_v1_readonly.py` | 粗筛接口与证据组织 | RH 发现入口独立；DefiLlama／Gecko 只给种子 |
| `lp_netcover_inputs_v1_readonly.py` | horizon-USD 输入契约、CLMM 装配 | 新 RH 装配器输出同一经济引擎所需字段；不得伪造缺失输入 |
| `lp_netcover_engine_v1_readonly.py` | 纯函数 NetCover、绝对利润和仓位上限闸 | 优先不修改；保留阈值与 Base 固定快照不变性 |
| `lp_swap_cost_model_v1_readonly.py` | 按实际换腿份额计成本 | 新增 RH 路由费用观测，不把全部本金都视为换腿额 |
| `lp_scanner_daemon_v1_readonly.py` | 全部终闸合取思想、漏斗产物 | 不重启旧 daemon；RH 新 runner 调用独立终闸，覆盖新增策略政策 |
| `lp_shadow_gate_v1_readonly.py` | 独立影子证据闸 | 为 RH 增加数据覆盖、账本与策略证据输入，不绕开旧闸 |
| 股票代币 universe／policy／acceptance 脚本 | instrument 归一化、缺数据与不盈利的区分 | 复用纯逻辑；不沿用 Solana 程序、账户布局或 Token-2022 指令 |
| `execution/base_m1_executor_v1.py` | 双开关、独立五检、nonce／幂等、权限边界 | 作为安全契约模板；新建 RH 受限执行适配器，不直接换 chainId 上线 |
| 面板只读服务及测试 | 已有路由、表格、报告展示 | 扩展 RH 标签页；不另建前端技术栈 |
| `tests/`、reports 规范 | 原始输出、VERDICT、回归约束 | 增加 RH 配对测试、固定 fixture 与变异测试 |
| `internal/ cmd/ pkg/`、旧运维单元 | 历史资产与隔离规则 | 冻结；不作为新策略入口，不启用旧 canary |

建议新增的只读模块：

```text
scripts/lp_rh_registry_v1_readonly.py
scripts/lp_rh_capabilities_v1_readonly.py
scripts/lp_rh_pool_probe_v1_readonly.py
scripts/lp_rh_pool_collector_v1_readonly.py
scripts/lp_rh_market_state_v1_readonly.py
scripts/lp_rh_netcover_inputs_v1_readonly.py
scripts/lp_rh_portfolio_policy_v1_readonly.py
scripts/lp_rh_terminal_gate_v1_readonly.py
scripts/lp_rh_pnl_v1_readonly.py
scripts/lp_rh_shadow_runner_v1_readonly.py
scripts/lp_rh_funnel_autopsy_v1_readonly.py
scripts/lp_rh_acceptance_v1_readonly.py
```

测试使用 `tests/test_<脚本同名>.py`。若 P0 发现可在现有模块小幅扩展，应优先复用而非为凑数量创建文件。未经审批不得让 `*_readonly.py` import 钱包／签名／广播模块；离线构造与交易执行隔离。

---

## 3. RH 生态研究对产品的具体影响

### 3.1 已核对信息，以及不能由此推导的结论

| 外部事实／观察 | 本版产品含义 | 不能推导什么 |
|---|---|---|
| 官方主网为 Arbitrum 技术的 Ethereum L2，chainId 4663，原生 gas 为 ETH [R01] | 使用 EVM、L2 最终性与原生 ETH 预算；46630 测试网严格区分 | “所有 EVM 执行代码只换 RPC 即可” |
| Uniswap 官方宣布 RH 上有 V2、V3、V4、UniswapX [R02] | 发现阶段识别版本；执行能力按版本单独毕业 | UniswapX、RFQ、专有做市商的全部流量都能被普通 LP 捕获 |
| RH 官方提供资产、价格与公司行动 REST，另有链上 multiplier／oracle 集成 [R04、R06] | 股票策略需要独立元数据与参考价层 | 普通 LP 获得按参考价直接申赎的权利 |
| 官方公开 RPC 限流且不建议生产独占；提供商有免费注册入口 [R01] | 优先免费分层采数；实盘必须验证独立冗余与退出额度 | 本用户已经有 API key，或免费套餐一定含 archive／足够吞吐 |
| 本次 DefiLlama 页面观察到 RH 稳定币中 USDG 占比约 67.34% [R14] | USDG 是必须单列的组合集中风险 | 页面资金规模等于可退出深度、无风险储备或 LP 收益 |
| 本次 Gecko 页面有 USDG/WETH V3 0.01% 费档候选 [R15] | 可作为首批验证种子，而非只围绕股币／MEME 开发 | 已完成链上 factory 校验、交易量全有机、此时可盈利 |

市场和部署会变化，所有地址与能力须写入版本化 manifest，过期不得继承昨日 `PASS`。

### 3.2 最新事件改变了哪些设计假设

**Gas 不再按“L2 几乎免费”处理。** Bitquery 2026-09-04 的自有链上分析观察到 8 月下旬至 9 月初 RH gas 大幅上涨，并给出不同操作成本样本。本文只将它作为拥堵风险证据，不把其中某笔 swap 费用当作今天 LP 开／关仓的固定成本。实盘前必须测得本机器人实际 calldata 的总成本分布。[R13]

**“节点看不到新区块”不等于“链停了”。** 9 月 4 日事件有早期停机报道，但 Arbitrum 随后的官方说明称是 L1 blob 市场导致批次提交延迟，非 RH 交易执行停机；部分报道作了更正。产品必须分别监控 RPC／索引器、L2 执行、排序器 feed、L1 posting/finality，不以单一网页状态一键清仓。[R12]

**股币发行方身份与底层上市公司授权不能混为一谈。** 9 月初 AMC 相关争议说明需要保留发行方状态、底层公司事件和二级市场退出风险；新闻是人工风险复核触发器，不是自动判定违法／停止兑付的事实。AMC 首版仅观察。[R16]

### 3.3 首批种子与核验要求

以下仅为公开来源中的**发现种子**：[R03、R08、R15]

```text
chainId: 4663
WETH: 0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73
USDG: 0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168
V3 factory: 0x1f7d7550b1b028f7571e69a784071f0205fd2efa
V3 position manager: 0x73991a25c818bf1f1128deaab1492d45638de0d3
V3 candidate USDG/WETH: 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
```

Agent 要证明：链 ID 正确、代码非空、资产地址与 issuer registry 对应、合约部署来源可信、factory 的 `getPool` 返回一致、token0/token1/fee/tickSpacing 正确、可读 slot0/liquidity、历史日志完整、可构造退出路由。每项记录区块号／hash、RPC provider 与 ABI 版本。**任一未完成：`DISCOVERED_NOT_ATTESTED`，不得变成 accepted。**

不在本文硬塞一个未经验证的 AMC／ETF 池地址。候选必须由运行时 registry 与真实池证据生成。

---

## 4. 公开 LP／ALM 项目：借什么，不借什么

| 项目与本次核对范围 | 可借鉴能力 | 本项目不直接采用的部分 | 落地任务 |
|---|---|---|---|
| Hummingbot Gateway／Uniswap connector；文档列有 `robinhoodchain`，CLMM 仍标 V3 [R17] | quote／交易构造与策略隔离、标准化连接器边界 | 不因为“支持 RH”就认定 V4 LP、Hook 或本项目 signer 已适配；不替换当前安全执行契约 | 用作 V3 连接器与官方 SDK 的交叉验证参考 |
| Arrakis；2026-06-15 宣布 V1/V2 弃用，当前转向 Modular [R18] | 策略管理权限与资金操作权限分离、区间／库存管理思想 | 不把已弃用 v2-core 当维护中的首选依赖；不把资金交给外部 vault 或引入管理费 | 吸收权限约束，保留自有受限执行器 |
| Gamma Hypervisor 公共代码 [R19] | 不同区间、库存配比和再平衡行为的参考案例 | 不把 Hypervisor 的收益历史、审计或 RH 部署当已核实；不复制管理人权限到钱包 | 用于审视单区间 MVP 的限制与测试场景 |
| Demeter 公共回测框架 [R20] | Python 事件回放、市场／broker 分离、V3 数学差分验证 | 不直接替代现有 NetCover，不默认内置 RH 数据或 V4 模拟 | 使用固定数据子集做第二套独立计算，查数学偏差 |
| Uniswap 官方 SDK／AI 集成资料 [R02、R21] | ABI、编码、报价、LP 计划与开发辅助 | LLM 不决定签名、不改风险阈值、不凭自然语言批准交易；工具返回 calldata 仍需独立解码 | 仅作开发和离线构造工具 |

**结论：不迁移到另一套“全能 LP 机器人”。** 原项目已积累经济闸、假阴性审计和执行安全契约。最有价值的增量是可信 RH 数据、正确 V3/V4 语义、实际持仓会计和可执行的成本估计。

引入任何第三方代码都要登记 repository、固定 commit、license、来源文件、修改范围、依赖锁文件与安全审阅结果；本次文档查阅不等于完成其源码审计。

---

## 5. 产品范围、收益假设与停走规则

### 5.1 三个待验证假设

**H1 CORE：** 真实有效费收入，在候选区间与可实现持有期内，能够覆盖库存风险、往返交易成本和保守余量。高吞吐、低池费并不天然证明 H1。

**H2 STOCK：** 在参考价可靠、退出渠道完整、时段已明确的窗口内，LP 所收手续费能够补偿其承受的信息劣势和跳空风险。不是“股价休市，所以窄区间安全”。

**H3 MEME：** 少数池的可持续有机订单流存在正净收益窗口，且可退出深度足以支持风险上限内的仓位。H3 未通过不阻止 H1 上线，也不能挪用 H1 预算去强测。

### 5.2 MVP 必做与不做

**必做：** RH discovery→attestation→cost→terminal gate→shadow→PnL 全链路；CORE 优先；STOCK 元数据／参考价／时段的只读闭环；MEME 审计与观察；全部零候选原因可解释；免费数据预算与缺数告警。

**不做：** 自建全节点、全链每笔交易采集、高频 JIT、跨链套利、对冲／杠杆、AP 一级申赎、公开 AMM 以外流量套利、自动借贷闲置资金、任意 Hook 池、自动追逐补贴、链上自部署退出合约、复杂多区间 vault。后续能力各自立项，不能挤进首版。

### 5.3 首轮范围控制

初始只读 watchlist 上限 12 个池；每轮深度核验上限 4 个；Shadow 同时活跃仓位上限 4 个，CORE 优先 1–2 个。STOCK 优先一个可证明身份、数据和退出能力的 ETF／高流动性标的，不保证一定找到。MEME live 仓位数为 0。

这些是资源控制建议初值，不是收益最优参数。增加数量先证明新增请求不损害既有仓位风险监控。配置里的观察数量、影子仓位和 live 仓位分别计数。

---

## 6. 三资金桶：政策版本、经济可行区间与库存聚合

### 6.1 当前授权与新设计必须并列显示

当前仍保留：[B1 §5]

```text
M1 = 100U
旧单仓 = 50–60U；Reserve = 40U
日亏 −5U 停新；总回撤 −10U KILL
C 档总敞口≤20U；单仓≤5U
六个受保护常量不变
```

B2 的 50/30/20 新设计在 C=100 时对应：

| 桶 | 预算 | 桶内 active 上限 | 最大 LP 部署 |
|---|---:|---:|---:|
| CORE | 50U | 85% | 42.5U |
| STOCK | 30U | 70% | 21U |
| MEME | 20U | 40% | 8U |

因此，新 CORE 上限小于旧单仓下限。**这不是让 Agent 自动把 50U 改成 42.5U 的授权。** 新增 `capital_policy_id=rh_50_30_20_proposed_v1`，默认 `approved_for_live=false`；新旧都未被明确替代的限制取交集。交集为空就不允许 LIVE。

解除冲突需所有者明确批准“RH 独立资本政策与最小仓位规则”，并绑定金额、配置 hash、期限与风险上限。无需因此停止 READONLY／SHADOW 研究。

终闸必须带 `target_mode`：研究可以在显式 `SHADOW_SCENARIO` 下反事实比较新三桶政策，虚拟预算与旧钱包完全隔离；报告标记 `SIMULATED_POLICY_ONLY`。同一候选另算 `LIVE_READINESS`，未批准的新政策仍为 `POLICY_BLOCKED`。不得把情景模拟通过写成生产终闸通过，也不能让旧政策冲突阻止所有新政策的离线研究。

### 6.2 预算基数与不得自动放大

定义：

```text
C_policy = min(已授权资本基数（扣除已批准提款）, 保守可用净资产)
Budget[b] = weight[b] × C_policy
ActiveCap[b] = Budget[b] × active_fraction[b]
```

新增外部注资、浮盈或奖励不能自动上调授权资本。保守净资产下降时预算收紧。资产价格波动导致已有仓位暂时越限，应触发 `NO_NEW / REDUCE_EVAL`，而不是把无法约束的市场价格变化伪装为“任何时候绝不超限”的断言。

虚拟预算不是额外资产。`sum(bucket NAV)+未分配托管项目=portfolio NAV`，共享钱包中的同一枚 USDG 不得同时计入多个桶的 reserve。跨桶转拨必须形成已批准的 journal 事件。

### 6.3 双重上限：LP 部署和撤池后的风险库存

桶 active cap 约束 LP 部署及已占用的开仓意图；资产集中度约束**全部钱包余额、LP 内底层余额、未完成换腿、应收费用与退出残余库存**。撤池不是自动释放全部资产风险额度。

新政策提案的资产限制：高波动股币≤总资本6%，普通股币≤8%，同一 MEME 聚合≤2%；MEME LP 总部署≤8%。LP 头寸按当前拆分的底层资产暴露计入，并做“价格越界后全部变为风险腿”的情景测试。不得按 NFT 数量拆单绕过单资产上限。

USDG 暴露跨三桶合计；WETH 暴露同样聚合。风险缓冲中的 WETH 不是原生 ETH gas 余额。

### 6.4 仓位必须同时满足经济下限和风险上限

```text
q_max = min(
  bucket_active_room,
  global_active_room,
  approved_position_cap,
  asset_exposure_room,
  POSITION_TVL_SHARE × verified_pool_TVL,
  measured_exit_depth_cap,
  spendable_cash_after_native_gas_reserve
)
```

其中 `POSITION_TVL_SHARE=0.0005`，`HARD_POSITION_TVL_SHARE=0.001` 作为不可突破的第二道检查，不能在第一道失败后拿 hard 上限替代它。候选 TVL 口径必须与池版本匹配。

经济下限由实际持有期、预计费用、全成本和绝对利润闸反解，不能统一设“最少 1U”：

```text
NetEV(q,H) = q × (每美元可得费／奖励 − 每美元库存与可变执行成本) − 固定往返成本
```

若括号内≤0，则增大仓位也不成立；若 `q_min_economic > q_max`，结果为 `COMPUTED_FAIL: SIZE_INTERVAL_EMPTY`。若退出报价拿不到，结果是 `INPUTS_UNAVAILABLE`，不是同一个经济结论。

Shadow 可比较 100／300／1000／3000U 的规模敏感性，但报告必须注明“虚拟情景，不是加资建议”；不得为了制造盈利而挪用旧资金参数。

### 6.5 原生 ETH 退出储备

每个待开仓意图必须计算：所有现有仓位在压力 gas 情景下完成 remove／collect／必要转换／撤销授权的余额需求，加有限重试。按保守总费用估算原生 ETH；不能只检查 USD 计价 reserve。

该储备包含在真实资产与资金桶账本内，不能在 NAV 外再加一份。不足则 `GAS_EXIT_RESERVE_INSUFFICIENT`，禁止新增。自动补 ETH 必须单独通过风险降低方向、金额与签名权限检查。

---

## 7. 资产、池与协议能力注册

### 7.1 资产不能由 symbol 判定

主键为 `(chain_id, token_address)`；股票另绑定 issuer、uid、underlying 标识、部署来源及元数据版本。`AMC`、`WETH`、`USDG` 字符串只作显示。需保存：decimals、运行时代码证据、proxy／implementation／管理员变更监控、冻结／暂停／transfer 限制、报价基准与来源。

股票 status 不是 ACTIVE、uid／部署不一致、decimals 不一致、implementation 未经审核变化，均禁止新仓。不能把股票正规发行流程的授权 mint 当成 MEME 任意增发；但正规发行也不消除管理员、暂停、发行方和法律结构风险。[R03、R04、R06]

USDG 须追溯本链版本与发行方公布的部署／跨链模型。Paxos 官方当前文档列出 RH 的 OFT 相关结构，不能不核对就当作普通 Ethereum 桥接 ERC-20；本版不实现赎回或跨链套利。[R23]

### 7.2 V3 与 V4 分开建模

| 维度 | V3 | V4 |
|---|---|---|
| 身份 | chain＋factory＋pool address | chain＋PoolManager＋PoolId |
| 构成 | token0、token1、fee、tickSpacing | PoolKey：currency0、currency1、fee、tickSpacing、hooks |
| 状态 | pool 合约 slot0／liquidity／ticks | 经可信 StateView／官方读取方式查询对应 PoolId |
| LP 收益 | position fee-growth 与净池费 | 除净 LP fee 外还须解析动态费、protocol fee、hook 费／自定义 delta |
| 首版策略 | 完整 read-only／shadow；经济通过后优先执行 | 发现即识别；无 Hook 标准池可进入后续适配；未知 Hook 仅观察 |

V4 的 PoolManager 地址或其钱包余额不是一个池的地址／TVL。不能对 PoolId 调 `token0()` 或 factory probe，然后把必然失败记录成“不盈利”。协议未知时返回 `UNSUPPORTED_PROTOCOL`。[R09]

### 7.3 Hook 风险不能只看声明费率

V4 Hook 准入需逐一验证：权限 flags、字节码与可升级性、外部依赖、add/remove 限制、动态 LP fee、hook 收费和自定义余额变化、swap 模拟与 quote 一致性、实际到账、最坏费用上限。未知 owner／升级路径／外部调用或无法证明退出语义，均 `UNSUPPORTED_HOOK_POLICY`。

单 LP 白名单池、不能由本钱包加／减流动性的池、广告费率低但最终到账不透明的池，不进入候选收益排行榜。对这些池的检测是**防御性验证**，不实现刷量、虚假 APR 或诱导路由。

官方治理论坛的 V4 费率提案只能作为理解机制的资料，不能替代本链当区块的实际 protocol fee 状态。[R09、R24]

### 7.4 能力不是一个布尔值

每个 venue 必须具有：

```text
discovery / state_read / history_read / fee_attribution / add_quote /
remove_quote / swap_quote / simulate / unsigned_build / broadcast / reconcile
```

各项状态为 `VERIFIED / UNVERIFIED / UNSUPPORTED / DEGRADED`，包含 evidence hash 与过期时间。策略只能申请当前能力支持的动作；部署存在不等于本项目适配完毕。

---

## 8. 免费数据层与“没有候选”可解释性

### 8.1 数据来源职责

链上合约状态和真实回执负责余额／池状态／交易结果；官方 registry 与 API 负责发行身份、underlying quote 等已声明语义；indexer 负责发现与粗筛。任何 indexer APR、TVL 或 volume 单独都不能触发资金动作。

至少保留 `source_event_time`、`fetched_at`、`block_number/hash`（适用时）、provider、schema、原始 payload hash、质量状态。拉取时间不能替代服务器 `generatedAt` 或 oracle `updatedAt`。

### 8.2 初始采样预算（建议值，不代表已获得供应商额度）

| 数据 | READONLY 初值 | 限流／失败处理 |
|---|---|---|
| 官方 assets | 每 5 分钟；状态事件时加急 | ETag／内容 hash 去重；失败保留历史但标陈旧 |
| 在观察名单内的股票价格 | 最快每 15 秒 | 尊重官方缓存；未知时段不升级为正常 |
| 公司行动 REST | 每小时 | 用于解释与对账，不当作毫秒级前瞻日历 |
| 活跃观察池状态 | 每 15 秒，按 budget 降频 | 合并兼容读取；必须记录实际间隔与滞后 |
| 独立 RPC 链头健康 | 初始每 5 秒 | provider 级退避；只读降级可持续记录 |
| 池发现／粗筛 | 每 5–15 分钟 | Top-K 增量；不无界扫描新币 |
| 已授权仓位的退出报价 | 专用优先队列 | 预留请求预算，不与全网发现争抢额度 |

按方法计量实际请求／CU，批量 RPC 的每个子请求是否计费由 provider 契约决定，不能当作“一批只算一次”。若低成本数据间隔无法支持某策略的退出要求，该策略应判不支持，而不是补一个未获批的高速订阅。

最多并发 4 个外部任务作为初始资源上限；限制重试与历史 backfill 区块范围。免费 archive 不可用时使用正向采集，不伪造历史。对 archive 缺失的研究输出 `HISTORY_UNAVAILABLE`。

### 8.3 端点能力证明与互相独立

需要实测 chainId、block/hash 一致性、历史读取、日志范围、eth_call、gas estimate、WS（可选）及错误结构。主／备 URL 指向同一后端不能视为两套独立证据。READONLY 可暂用公开单点；LIVE 不允许该单点成为唯一可用数据源。[R01]

直连 sequencer feed／广播是扩展能力，不是第一版强制依赖。没有经核验的 sequencer uptime feed 地址时，记录 `UPTIME_FEED_UNAVAILABLE`；禁止抄其他 L2 地址制造健康绿灯。

### 8.4 终闸结果分类

每个候选必须归入唯一主状态，另保留全部理由：

```text
COMPUTED_PASS
COMPUTED_FAIL
INPUTS_UNAVAILABLE
UNSUPPORTED
POLICY_BLOCKED
```

`UNKNOWN`、None、请求超时、字段没有生产者不得填 0。报告同时显示“有多少已完成经济评估”“有多少经济上不合格”“有多少尚未能评估”。

`COMPUTED_PASS` 只表示该经济评估通过，**最终可部署**仍需要资产／能力／状态／资金／Shadow／执行门禁全部为 PASS。不能因为分类细化而弱化 fail-closed。

### 8.5 防止能力装饰

为每个终闸字段建立 `producer_file → schema_field → writer/table → consumer → terminal_gate → test` 映射。缺一个链接，验收 FAIL。对 `market_sessions`、`rpc_severe_incidents` 的旧空表，不假设它们已经提供证据；RH 使用独立实际写入与读取的表。[B1 §10.3]

每增加一道硬闸，都要有“删掉这一闸后，坏样本错误放行”的摘除变异测试。若全部坏样本总被别的闸挡住，则不能证明新增闸已接线。

---

## 9. 股票元数据、乘数、参考价与市场时段

### 9.1 本次发现的真实 API 兼容性问题

官方文档示例仍使用：

```text
tradingCapabilities.fractionalTradability
tradingCapabilities.allDayTradability
tradingCapabilities.extendedHoursFractionalTradability
```

但本次读取官方 `/rhj/assets` 实际响应观察到：

```json
{
  "tradingCapabilities": {
    "market": {"whole": "TRADING_STATUS_TRADABLE", "fractional": "TRADING_STATUS_TRADABLE"},
    "extended": {"whole": "TRADING_STATUS_TRADABLE", "fractional": "TRADING_STATUS_TRADABLE"},
    "overnight": {"whole": "TRADING_STATUS_TRADABLE", "fractional": "TRADING_STATUS_TRADABLE"}
  },
  "tokenDecimals": 18
}
```

上面是**观察到的结构摘录**，不是完整 API 快照或股票白名单。[R04–R05]

实现必须识别 `LEGACY_FIELDS` 与 `SESSION_NESTED` 两种结构，输出统一的 `SessionCapability`；未知字符串／缺失／null／空字符串不等于“允许交易”。当两种结构同时出现且互相矛盾，输出 `SCHEMA_SEMANTIC_CONFLICT`。

元数据交易能力描述的是底层／发行方提供的能力，不自动等于本钱包可调用的一级申赎权限或某个 DEX 的可卖出状态。后两者必须单独证实。

### 9.2 统一单位，乘数只应用一次

股票接口返回的 underlying bid/ask 与 Chainlink 的 token-equivalent price 是不同口径；链上 UI multiplier 与 API decimal string 也不能按同一 raw integer 处理。[R04、R06–R07]

本版统一模型：

```text
token_quantity = raw_balance / 10^token_decimals
multiplier_human = onchain_uiMultiplier_raw / 10^18
                 或 Decimal(api.currentMultiplier)
underlying_share_equivalent = token_quantity × multiplier_human
reference_token_price_usd = underlying_price_usd × multiplier_human
reference_stock_per_usdg = reference_token_price_usd / usdg_price_usd
```

Chainlink feed 读取时按其自己的 `decimals()` 归一化，**如果该 feed 已是 token-equivalent，则不得再乘 multiplier**。原始 token 数量、UI／股数等价数量、参考价口径在类型上分离，禁止共享一个含义不明的 `amount`。

例子（合成测试，不是市场数据）：raw balance=`2×10^18`，token decimals=18，multiplier raw=`1.25×10^18`，底层股价=$100，则持有 2 token、等价 2.5 股、单 token 参考价 $125、参考总值 $250。若 USDG=$0.98，则每 token 的 USDG 参考价约 127.5510204，而不是 125。

拆股合成例：股价 200→20、multiplier 1→10，单 token 参考价仍 200；不能记 −90% 亏损或把 raw supply 增加十倍。UI 调整不等于 ERC-20 raw balance rebase。[R06–R07、R22]

### 9.3 公允参考值不是保证成交价

内部建议命名 `ReferenceValue` 而不是可以直接套利的 `GuaranteedFairPrice`。至少同时提供：

```text
reference_bid / reference_ask / reference_mid
executable_exit_bid_for_position_size
reference_age / quote_age / source_quality / redeem_access
```

一级 mint/redeem 存在参与资格限制；本机器人没有被证明拥有这种通道。因此再大的“相对 oracle 折价”也不能直接当作无风险收益。[R07]

Chainlink 与 Robinhood 可能共享底层信息或发行方乘数，不能武断认定为两套完全独立 oracle。DEX TWAP 是市场信号，不是外部价格真相。参考源不一致时停止新增，不用加权平均把冲突隐藏掉。

### 9.4 市场时段和健康状态使用两个维度

不要把“周末”与“RPC 坏了”塞入一个互斥枚举而丢失信息。

```text
Session = RTH | PREMARKET | POSTMARKET | OVERNIGHT |
          CLOSED_WEEKDAY | WEEKEND | HOLIDAY | UNKNOWN
HealthFlags = {HALT, CORP_ACTION, ORACLE_PAUSED, ORACLE_STALE,
               API_STALE, SOURCE_DISAGREEMENT, CHAIN_DEGRADED, ...}
```

时区：存储 UTC；交易日历 `America/New_York`；面板可展示 `Asia/Tokyo`。使用有来源版本的交易日历，覆盖夏令时、提前收市与节假日。**2026-09-07 是 NYSE 劳动节休市，不能因为星期一而判 RTH。** [R10]

股票 feed 在闭市可能保留旧价格且不按盘中 heartbeat 更新。应分为 `EXPECTED_SESSION_CLOSED` 与异常 `STALE_WHILE_EXPECTED_LIVE`；二者对新开窄区间都不放行，但告警原因不能混淆。[R06]

### 9.5 公司行动与 oracle pause

由 token 合约实际 ABI 读取 `uiMultiplier()`、`newUIMultiplier()`、`effectiveAt()`、`oraclePaused()`；不要假定通用 Chainlink aggregator 也暴露 token 的暂停函数。读取失败标 UNKNOWN，不当 false。[R06]

`newUIMultiplier` 非零不一定意味着有未来事件；须比较 current/pending、effectiveAt 和当前区块时间。正在协调的 split／公司行动、有未知大幅乘数变化、oracle pause，禁止新增／重新居中；已有 LP 优先评估 remove-only。

`/corporate-actions` 是有缓存的已处理／处理中事件信息，不是已证明完整的前瞻财报／拆股日历。财报事件数据若尚未接入，不得显示“未来 24h 无财报”；显示 `EVENT_CALENDAR_UNKNOWN`。高波动单股在该状态下不进初始 LIVE。

恢复需：乘数状态清晰、pause 解除、参考源重新一致、真实退出报价有效，并通过恢复冷却期。恢复计数不能仅靠连续两次读同一份缓存实现。

---

## 10. 三类策略的最小实现

### 10.1 CORE：先证明低频持有比频繁调整更好

首批研究 WETH/USDG 等已验证主流资产对；不把所有两币池都称为 CORE。策略比较以下**有限、预注册**候选：固定宽区间、波动率区间、保持旧仓、不建仓。第一版单个头寸一个区间，避免多区间参数爆炸。

波动率使用固定间隔的 log return，明确年／日／小时量纲及持有期换算；价格跳变、缺失和低成交不能静默填平。区间通过 V3 tickSpacing 对齐，下界向外取整、上界向外取整；支持负 tick、价格倒数与不同 decimals。

持有期比较 24h／168h／720h 等有限情景；较长窗口需要对应的流动性与费用持续性、库存和退出证据。B1 的长持有历史结果不能直接外推为当前可稳定赚 30 天。[B1 §9.5]

再平衡不是触边就做：

```text
ExpectedIncrementalNet = EV(新仓，从当前时刻到剩余计划期)
                       − EV(保持旧仓，同一期限)
                       − 切换成本
```

只有保守增益超过绝对收益门槛与安全余量，并且当前所有风险闸允许，才形成意图。初始设置最短重新评估间隔与最大日调整次数，全部计入成本模型；风险退出不受“策略冷却”阻挡，但仍受执行安全限制。

### 10.2 STOCK：先做可信时段，不做“休市窄区间套利”

股票入池前追加：canonical 身份、multiplier 一致、参考价 freshness、时段允许、token/issuer 状态、退出报价与股币资产上限。初始 LIVE 政策仅考虑 RTH；盘外／隔夜／假日／周末先跑 Shadow，未独立毕业不得打开。

区间中心以可用的外部 token-equivalent 参考值约束。DEX 偏离参考值较大时，策略可以不建仓或保持无仓，不能自动把区间移到失真的 DEX spot。**在远离现价的“合理价格”摆区间也不一定赚费**：可能完全不活跃，或在价格跳变时被单向成交；此类收益必须按真实在区间时长计算。

B2 的 1%／3%／7% premium 档位保留为 Shadow 比较初值，不直接称已验证的 live 阈值。初始实盘白名单需另有“超过进入阈值一律不新开”的硬规则，随资产价差、时段和延迟校准。不能为 AMC 的极端溢价放宽阈值。

供应变化监控 raw supply、mint/burn、乘数等价 supply 三个口径。股币 AP 增发可能用于修复溢价，不是自动 rug；但它会改变 LP 库存与溢价收敛风险，因此进入 `SUPPLY_EVENT_REVIEW`，不能当“增发越多成交越好”。

STOCK/STOCK、股票/MEME、复杂双风险资产对首版 `UNSUPPORTED_PAIR_POLICY`。股票/WETH 可做独立只读研究，但未同时建立两腿 USD 参考价与退出路线前不可部署。

### 10.3 MEME：可选机会，不是必须消耗的预算

首轮只实现粗筛、风险审计、费用与退出证据采集。转入任何 MEME LIVE 前，除组合毕业外必须有独立 MEME 授权与微额测试上限。

初始准入拒绝：不可卖／不可减仓；未知税费；任意可改交易税、黑名单或升级能力未经审核；转账税／rebase 等不被适配器支持；流动性与退出报价不足；持有人／LP 集中证据缺失且无法界定风险。**B2 的“允许最高5% transfer tax”不作为首版准入，初始仅考虑验证为无转账税的标准行为。**

V3 的 LP 集中度按 NFT 头寸／受益人和有效流动性分析，不能沿用 V2 LP ERC-20 holder 表；V4 也不能把 PoolManager 当唯一 LP 而误判 100% 集中。

有机交易量只是区间估计。router 地址可能聚合大量用户，地址多也可能女巫；同资金源聚类是线索，不是事实定罪。保存 raw volume、可解释排除项、`organic_volume_low/base/high`；证据不足则折价收入或拒绝，不能无条件用洗量模型猜出高分。

跌破区间且趋势继续向下：禁止自动下移区间补仓。进入 REMOVE_EVAL，随后在安全报价范围内换回允许的低风险资产；卖不掉就记录风险库存和损失情景，不把 `remove success` 显示成“已安全退出”。

MEME 设 TTL／成交量衰减／流动性下降／退出冲击变大的退出条件；所有阈值先由 Shadow 校准。单资产 2% 是上限，不是最大亏损保证，执行失败和价格跳变可能使预估止损失效。

---

## 11. 经济引擎：保留 NetCover，修复输入而非放宽结果

### 11.1 原有六常量保持

```text
STABLE_MIN_FRAC          = 0.7
NETCOVER_SHADOW          = 1.0
NETCOVER_TINY_LIVE       = 1.5
POSITION_TVL_SHARE      = 0.0005
HARD_POSITION_TVL_SHARE = 0.001
LVR_COEFFICIENT_MODEL   = 0.50
```

来自 B1 §5.1。新模型不得在新文件中用同名不同值旁路这些约束。对旧共享函数的修复必须使用同一份固定快照做新旧逐闸差分；成本口径改变另记 model version、审核依据与授权，不能以“修 bug”为名无证据降低总成本。

### 11.2 收入输入不是 APR 抄表

对计划头寸回放有效流动性与净手续费。V3 估计需要 swap 经历的 tick、该段 active liquidity、模拟头寸 liquidity、跨 tick 行为与净 LP fee；不能按全池 TVL 占比直接乘全池 volume 得出精确收益。若头寸新增量影响价格路径或有效流动性，需做反馈情景，而非假设原交易路径必然不变。

V4 dynamic fee／hook 影响不能解析时不计入可交易机会。项目奖励只有在发行／领取资格、到账资产、领取成本、兑现路径有可核验证据时才入账；未验证宣传奖励的收入输入为 0，并显示未验证原因。不是把基础 fee 缺失也填 0。

收入必须扣除协议／hook 等不归本 LP 的份额。用户 swap 支付的总费用、链 gas 收入、钱包／聚合器收入都不是本 LP 的收益。

### 11.3 全成本输入清单

按**每个 action 的实际 calldata 与交易顺序**建预算：必要换腿的 LP/router 费用、实际 price impact、交易执行 gas、批准／撤销费用、加／减／collect、退出转换、失败与有限重试、奖励兑现费用，以及单独的库存／逆向选择风险模型。

RH gas 估算要核对 provider 的 total estimate 是否已包含 L1 data 部分。官方描述标准估计包含相应组成，不能先用总 gas 估算再机械追加一次 L1 费用。[R11]

已持有资产的入场成本不能当作所有场景都为零：提供 `FROM_USDG_CASH` 与 `FROM_EXISTING_INVENTORY` 两种实际起点，分别使用真实库存成本与策略现金流边界。旧成本模型修复的“按需换腿份额”继续保留。[B1 §3.2]

quote 必须与真实 size、币对、路径、fee tier、可用余额一致；不要用 1U 报价线性外推 100U 或默认撤池后原池仍有同样深度。撤出的流动性影响自池退出报价时，需按撤后状态模拟。

### 11.4 预测模型与实际会计严格区分

开仓前可以用经校准的 LVR／库存损耗代理成本来保守预测；这不是对实际账本重复扣减的理由。若多项风险模型覆盖同一事件，应以可解释的互斥分解或联合情景表达，而非把 IL、LVR、markout 三个完整估计相加。

旧模型的 LVR 系数仍保持 0.50；RH 数据不足时，可以输出“旧模型保守估计”与“新模型待验证”两列，但不能用尚未通过的低成本模型驱动 live。

### 11.5 终闸与输出字段

```text
terminal_eligible =
    legacy_required_conjunction
AND identity_verified
AND protocol_capabilities_sufficient
AND data_complete_and_fresh
AND profile_policy_pass
AND market_and_chain_risk_pass
AND netcover_pass
AND absolute_profit_pass
AND position_and_exit_depth_pass
AND capital_policy_pass
```

上式为逻辑契约，`legacy_required_conjunction` 必须是有真实生产者的布尔值；不能再次出现永远没被写出的字段。Shadow evidence gate 和 execution gate 在终闸后仍独立存在。[B1 §3.2、§9.6]

标准输出：`pool_key, profile, horizon, position_usd, fee_ev, reward_ev, cost_components, cost_model_version, netcover, abs_profit, q_min, q_max, terminal_bits, missing_inputs, dominant_blocker, source_snapshot_ids`。所有钱使用 Decimal，所有期限单位显式。

### 11.6 压力测试与真实经济停机条件

至少比较：收入衰减 50%；有效 fee share 减半；实测 gas p95／更高拥堵情景；退出报价价差扩大；股票开盘跳空；MEME 风险腿接近清零；USDG 脱锚；无法立即撤池。情景是预算工具，不表示各事件概率已知。

一次短窗高 APR、增加仓位、延长 H 或切换到更便宜的假想路线，都不能单独恢复失败结论。若测试期内收入保守估计持续不足，输出“保留观察／停止该策略”，不要求工程自动寻找一个能通过的参数组合。

---

## 12. PnL 与会计：唯一总账，多个解释视角

### 12.1 实际净值是总账，费用归因不是第二份余额

对同一估值时刻：

```text
NAV = 钱包中各资产的保守价值
    + LP 内本金资产价值
    + 未领取且未计入钱包的应计 LP 费用
    + 有证据且未重复计算的可领取奖励
    − 真实负债

NetPnL(t0,t1) = NAV(t1) − NAV(t0) − 净外部注资(t0,t1)
```

所有额外外部入金／提款与策略收支严格区分。组合范围内钱包间转账、同一桶 remove→wallet、collect→wallet 都是内部移动，不是新收益。若 gas 从组合外的钱包代付，必须记外部代付成本／资本流，不能“看不到就免费”。

**实际 swap 的价差、滑点和 gas 已体现在余额变化时，不再从 NAV PnL 重扣。** 仪表盘可以拆解它们，但各解释项必须可勾稽到总账。实际会计不使用“Fee−IL−AS”作为独立的总收益公式。

### 12.2 至少三种视角

1. **现金／净值结果：** USD 标记净值、已实现策略现金流、未实现风险库存变化；现金流为正不必然代表总资产盈利。
2. **HODL 基准差：** 同样的外部资金流和实际初始两腿数量，不执行 LP 的资产持有轨迹，与实际组合比较。
3. **损耗归因：** IL（指定 HODL 基准）、LVR／markout（不同参考基准）、执行差价、交易费、gas；标明哪些为模型估计、哪些为真实回执金额。

B2 对 CORE 的“50% WETH＋50% USDG”可以作为额外政策基准，但不能替代头寸实际初始数量。每次再平衡不能重置初始成本和累计亏损；增加／提款需新增基准 lot 并保存完整策略 episode。

### 12.3 LVR／IL／逆向选择不混加

LVR 与 HODL-IL 对应不同反事实基准；实际费用收益可能被信息劣势吞噬，但不能把两个完整损失口径视为必然互不重叠的成本项。[R25]

本版对单笔、fee-excluded 的 LP 成交变化定义独立诊断：

```text
markout(delta) = Δbase × ReferenceBaseUSD(t+delta)
              + Δquote × ReferenceQuoteUSD(t+delta)
AS_signed(delta) = −markout(delta)
```

这只是指定未来时点的成交标记，不是完整 LVR 的无偏估计。使用 30s／5m／30m 等预注册观察窗口（依据数据能力调整）；不能把多个 delta 的同一笔 markout 相加。保留正负值，不把所有有利成交清零只累加不利成交后再声称是实际亏损。

个体 LP 的 Δ数量应来自其在成交段实际应占份额；不得用全池成交当作本钱包损失。没有未来可信参考价时输出未完成样本，不用陈旧价格补齐。

### 12.4 估值与退出可兑现性

同时保存 `reference_nav` 与 `liquidation_nav`。前者用于可比分析；后者使用当前 size 的保守卖出报价、可得深度和费用情景。MEME 无可靠外部价格或无法卖出时不能按最后一笔刷单价估值；须给出 haircut／压力下界和未证实金额。

USDG 不是强制按 $1 估值；股票 pause 时参考价可显示旧值，但必须标记陈旧，不能由旧参考价计算“低风险正收益”。

### 12.5 会计验收

原始 token 单位勾稽必须精确一致；舍入规则逐资产声明。合成样本：collect 前后无价格变化且无 gas 时 NAV 完全不变；有 gas 时只下降一次 gas；remove 不能把本金记手续费；一笔外部注资不能记盈利。

估值差异使用绝对与相对容差双阈值，容差基于资产 decimals／报价取整／可解释 dust，而不是用“PnL 误差小于2%”掩盖几美分盈利全部来自误差。未解释差异>容差即禁止进入 live；不能给大额本金设宽阈值后容忍小额利润虚增。

---

## 13. 风险状态机与动作权限

### 13.1 风险优先级

`MANUAL_LOCK / SECURITY_INCIDENT` 优先于资本与链风险；链／关键身份风险优先于市场状态；所有风险优先于策略收益。多条 flag 可以同时保留，动作取允许集合的交集。

| 状态 | 新增／加仓 | Rebalance | Remove／collect | 风险腿兑换 |
|---|---|---|---|---|
| NORMAL | 全闸通过才允许 | 增量净收益通过才允许 | 安全执行门禁通过 | 经报价、方向与金额核验 |
| NO_NEW | 禁止 | 仅证明不增加风险的特例，默认禁止 | 可评估 | 只允许降低被限制风险 |
| ORACLE_STALE／HALT／CORP_ACTION | 对相关股票禁止 | 禁止追价／补仓 | 可在链可执行且模拟通过时进行 | 必须有有效可执行报价，不用陈旧 oracle 作唯一根据 |
| RPC_DEGRADED | 禁止 | 禁止 | 有独立可信执行证据才允许 | 不绕过 quote／模拟／nonce 检查 |
| CHAIN_EXECUTION_UNCERTAIN | 禁止 | 禁止 | 等待已提交状态对账，不盲目重发 | 不新增未知交易 |
| USDG_RISK | 禁止增加该风险 | 禁止自动加 USDG 集中度 | 评估两腿库存变化 | 不机械“全部卖回 USDG” |
| EXIT_ONLY | 禁止 | 禁止重新部署 | 允许受限减风险动作 | 必须解码并证明风险方向 |
| MANUAL_LOCK | 禁止 | 禁止 | 只按明确的事故处置授权 | 同左，禁止自动解锁 |

REMOVE 会改变 token 库存状态但不消灭市价风险；是否真减风险要同时看 LP 暴露和钱包库存。某些 swap 降低一种风险却增加另一种风险，应按明确风险目标和预算审核，不以“这是 exit”四字通行。

### 13.2 回撤限制

现有日亏 −5U／总回撤 −10U 不变。B2 的日 2% freeze／3% 降风险／5% risk-off／周8% lock 可作为新政策的**更严格提案**，必须明确每日／每周时间边界、资金流调整、HWM 和已实现＋未实现口径后再启用。

在新旧政策同时有效时取更严格限制；无法计算可靠 NAV 则停新，而不是把收益设零。`risk-off` 不等于有权绕过滑点、也不保证能够无损清仓。

### 13.3 USDG 与单链集中风险

追踪 USDG/USD 独立可用标记、可退出深度、报价分歧、发行方／跨链状态和合约变更。B2 的 30/75/150 bps 仅为 Shadow 初始分层；不是对当前 USDG 波动率的实测结论。

所有 idle USDG 也有 USDG 风险；WETH 有价格风险；链上资产有链／桥／发行方风险。系统显示“LP 部署71.5%”时，不得同时宣传其余28.5%为链外无风险现金。

### 13.4 链故障分类与恢复

分别记录：`rpc_provider_health`、`l2_execution_progress`、`sequencer_feed_health`、`l1_posting_progress`、`l1_finality_progress`。单个 provider 故障先降级该 provider；只有可信多源证据才升级链执行风险。

L1 posting 延迟可触发禁止加仓、提高最终性要求等风险动作，但不能直接称“已提交 L2 交易回滚”。恢复必须重新核对已提交交易和余额，不能只看新 block 到来就释放 pending capital。[R12]

---

## 14. 执行适配：继承安全契约，不继承链特定假设

### 14.1 权限与责任边界

研究用户无密钥读取权；策略只产生 `UnsignedIntent`；受限执行用户独立重算关键输入。对候选的网页、API 或模型文本一律按不可信数据处理，不能包含可执行 shell 或绕过白名单的 calldata 指令。

保留 B1 的签名前双开关、encrypted keystore、拒绝裸私钥环境变量、调用目标运行时校验、金额与日限额、三 ID／idempotency、独立 simulate／quote／basis／RPC／余额五检，以及 EXIT_ONLY 方向解码。[B1 §7]

额外要求：意图绑定 `chain_id, wallet_id, position_id, request_id, decision_id, idempotency_key, policy_hash, code_version, snapshot_hash, calldata_hash, expires_at`。字段不完整不接受；策略自报“simulated=true”无效。

### 14.2 签名前重检清单

依次验证：当前模式与授权有效；链和 RPC 正确；合约／ABI／router 版本在白名单；意图尚未执行；nonce 可用；资金已预留；交易 size 和方向合理；quote 与 simulation 对应同一实际 calldata；关键数据未过期；余额、allowance、gas 与退出储备足够；deadline 和适用的最小到账约束存在；policy 未被撤销。

**参数的安全语义要正确。** `slippage_bps=0` 可以表示不容忍滑点，本身不等于失去保护；危险的是应保护的正数输出被设置为无约束的 `amountOutMin=0`。完全单边的 LP 某一腿预期为0时，该腿 minimum=0 可以合法；不能据此允许两腿都不设保护。无 swap 的 collect 使用到账／权限约束，不伪造一个不存在的 swap minOut。

若模拟后关键状态或交易内容变化，重新报价／模拟。免费 archive 或 fork 不可用时，不允许假装通过；可以保持 READONLY。

### 14.3 模拟的边界

本地 fork 固定区块，验证实际 manager／router 路径、mint／increase／decrease／collect、swap、approve／revoke、目标币税费或暂停、失败时资产残留。模拟输出要包含预期 token balance delta、gas、授权变化、post-state 与所用 block hash。

只允许隔离的本地 fork／Anvil 内置测试身份或 impersonation，不向真实公网 RPC 发本地测试交易，不生成生产私钥；测试网交互也需独立批准。模拟通过只能证明当时状态下可执行，不能保证广播时不变；最小到账、有效期和签名前检查仍必须存在。

已生成的 calldata 由独立 decoder 校验 target、selector／command、token、recipient、amount、deadline、允许的路径。UniversalRouter 的版本必须匹配本链部署，不能将旧链命令编码直接拷贝过来。[R08]

### 14.4 交易状态机与崩溃恢复

```text
INTENT_CREATED → VALIDATED → CAPITAL_RESERVED → SIMULATED
 → AUTHORIZED → SIGNED → BROADCAST_SUBMITTED
 → EXECUTED_SOFT → L1_POSTED → L1_FINALIZED
```

并列异常状态：`REJECTED / EXPIRED / SIMULATION_FAILED / BROADCAST_UNKNOWN / REVERTED / REPLACED / REORG_PENDING / RECONCILIATION_REQUIRED`。

READONLY／SHADOW 永远不得越过授权签名边界。真实执行时，交易意图与 nonce 预占必须先持久化；每钱包串行分配 nonce，重启仍识别 pending。RPC 超时且不知是否收下交易时，不得立即换 nonce 重发同一资金动作；先按 hash／nonce／回执独立对账。跨 provider 可重发**同一签名交易**，不等于可以制造第二笔独立开仓。

排序器 feed 接受／看见交易不等于 execution 成功；只有核验 receipt 和实际余额／头寸状态后才计为 `EXECUTED_SOFT`。后续 L1_POSTED、L1_FINALIZED 必须有对应链上证据，不按“等够几分钟”自动改状态。L1 数据最终性与桥提款挑战窗口不是同一个概念。[R11]

### 14.5 Approval／Permit2

禁止默认无限 ERC-20 allowance；Permit2 绑定 amount、spender、nonce 和有限有效期。NFT 管理权限优先使用单头寸授权，任何 `setApprovalForAll` 需要独立的明确权限审查，不因官方 manager 就自动放行。

退出后撤销不再需要的授权，或者证明已经到期／额度耗尽；记录撤销失败与下一步处置。不能为了节约 gas 永久积累开放授权，也不能在 gas 已不足时假报 revoke 完成。批准／撤销成本计入交易与经济模型。

---

## 15. 退出状态机：默认可靠退路，原子操作后置

### 15.1 区分 LP 撤除和风险资产清算

```text
EXIT_REQUESTED
 → REMOVE_VALIDATED
 → REMOVE_SUBMITTED
 → LP_REMOVED
 → INVENTORY_RECONCILED
 → CONVERSION_QUOTED
 → CONVERSION_SUBMITTED
 → CASH_EQUIVALENT_CONFIRMED
 → APPROVAL_CLEANUP
 → CLOSED_RECONCILED
```

若转换受阻，进入 `REMOVED_RISKY_INVENTORY` 或 `PARTIAL_EXIT`。该库存仍占用资产上限、仍参与回撤／USDG风险和清算 NAV，不能自动重新开仓。

`CASH_EQUIVALENT` 是政策允许的资产集合，不永远等同 USDG。在 USDG 自身风险事件中，去哪里、能否去、增加何种替代风险必须重新核验。

### 15.2 原子退出的失败语义

只有官方合约组合确实支持所需 remove／collect／swap，并在本钱包权限和真实交易模型下通过测试，才启用原子路径。不能把“Router 支持 multicall”推断成“跨任意 NPM／Hook 原子退出都支持”。

若 swap revert 导致整笔原子交易回滚，应独立评估一个新的 remove-only 意图。它也必须有模拟、金额、nonce 与权限检查；不是偷偷拆单绕过原失败的风险闸。

初始版本**不部署自定义 LPExitExecutor**。以后确需 helper，单独定义允许的调用、临时资产托管、无持久资产残留、重入、recipient、permit 消耗与失败原子性；“交易过程中短暂持有 token”的合约不能不加限定地宣传完全无托管风险。

### 15.3 退出 SLA 是可测目标，不是止损保证

分别统计：异常被数据源反映的延迟、机器人检测延迟、排队／报价／模拟延迟、提交至回执延迟、完成转换延迟。报告 p50/p95/p99 和最大值；不能只给一个“响应100ms”却忽略 API 15秒缓存与链确认。

如果 stock 或 MEME 的风险在现有数据周期内已经超过预算，则该策略不支持当前基础设施。不能把未到达的风控数据当作“无事件”。

---

## 16. 存储、数据契约与保留策略

### 16.1 SQLite 增量隔离

初始新库使用 `reports/lp_rh/scanner.db`，与正在运行的旧 scanner.db 分开；单 writer、WAL、合理 busy timeout、schema version 与事务内写入。只读 runner 的“只读”指不触达真实钱包／链写入，并不禁止生成本地研究数据。

不要直接把 B2 的 PostgreSQL `NUMERIC/UUID/TIMESTAMPTZ` DDL 粘贴进 SQLite。所有 uint256／raw amount 以十进制 TEXT 保存并在程序中校验；Decimal 也用规范化字符串，不使用 SQLite REAL 存钱或大整数。时间存 UTC RFC3339 或统一整数单位，禁止混用秒／毫秒。

### 16.2 最小新增表与必需键

| 表 | 核心键／内容 | 必需使用者 |
|---|---|---|
| `rh_source_snapshots` | source＋payload_hash；source_event_time、fetch_time、schema、原始文件引用 | 所有证据回放 |
| `rh_assets` | chain＋address＋metadata_version；uid、multiplier、status、能力／精度 | 股票身份／时段／估值 |
| `rh_contract_attestations` | chain＋address＋block_hash＋policy；code／implementation／ABI 证据 | 池准入与执行白名单 |
| `rh_pool_registry` | chain＋protocol＋pool_key；V3 address 或 V4 PoolId／PoolKey | 发现／采数／能力分派 |
| `rh_pool_events` | chain＋block_hash＋tx_hash＋log_index | 费用回放／流动性重建／reorg |
| `rh_market_states` | asset＋sample_time＋source_snapshot；session／health flags／reference | Strategy 与终闸，不得只有表没有 writer |
| `rh_rpc_health` | provider＋method＋sample_time；latency、error、last_good_block | 数据闸／执行闸／降级 |
| `rh_economic_evaluations` | candidate＋snapshot＋model＋policy＋horizon＋size | 漏斗与终闸 |
| `rh_gate_decisions` | decision_id；逐闸输入、结果与理由 | 是否可部署的唯一审计入口 |
| `rh_shadow_positions` | strategy_episode＋position_id；初始库存、区间、虚拟 liquidity | Shadow 与 HODL 基准 |
| `rh_journal` | event_id／idempotency_key；双边账户、raw token量、外部流标记 | 组合／资金桶总账 |
| `rh_position_marks` | position＋mark_time＋price_snapshot；reference／liquidation NAV | PnL／回撤 |
| `rh_bucket_reservations` | intent_id；policy、bucket、金额、状态 | 防止并发超配 |
| `rh_tx_intents`、`rh_tx_receipts` | request／nonce／hash；状态转换、receipt、reorg | 仅执行阶段使用，默认无真实记录 |
| `rh_reconciliation_runs` | run_id；原始余额／头寸证据、差额、verdict | 启动与恢复 live gate |

使用外键／唯一索引保证幂等。逐块事件保留 block hash；发生 reorg 时回滚受影响派生结果并重新评估，不能只按 block number 去重。

### 16.3 Journal 与预算原子性

资金占用必须通过数据库事务中的原子 reservation 完成：检查剩余额度、插入 reservation、生成 intent 同一事务；两条候选不能各自读到同一份可用 20U 后分别全部占用。

失败／过期意图在完成状态核验后释放 reservation；`BROADCAST_UNKNOWN` 不释放。已实际持有的风险币从 LP 账户转到钱包库存账户，不因此释放资产集中度额度。

### 16.4 保留与磁盘

初始新增 RH 数据目录软预算 2GiB；达到80%告警，达到100%停止非必要发现／backfill，优先保留风险与对账写入能力。该值是产品初始资源政策，可在批准后调整，不是对宿主容量的重新测量。

原始大响应按内容 hash 去重和压缩；活跃仓位、成交、政策、风险事件与财务证据不得按普通缓存删除。过期研究快照可按审批保留策略归档；禁止无界写 full-market snapshots。

备份使用 SQLite backup API／一致性备份，验证可恢复与 manifest hash；不要直接复制正在写入的 db/WAL 文件组合。B1 提及宿主磁盘消耗主要来自其他项目，未经授权不清理那些目录。[B1 §10.6]

---

## 17. Dashboard 与每日决策报告

沿用已存在的只读 panel／报告服务，P0 确认实际入口。不引入新的 TypeScript 前端只是为了完成 B2 的架构图。

### 17.1 首页必须能回答的六个问题

1. 当前模式与授权是什么？是否只有 Shadow？哪一道门阻止 LIVE？
2. 三桶预算、LP 部署、钱包风险库存、预留在途资金和原生 gas 分别多少？
3. 从发现到可部署剩多少池？未计算、不盈利、不支持、政策阻挡分别多少？
4. 实际净值／现金流／HODL 差／净手续费分别是多少？哪些是虚拟、估计或陈旧值？
5. 最近的主导成本是什么？持有／不建仓／再平衡哪个保守 EV 更好？
6. 能否按当前仓位 size 退出？最近退出模拟何时完成，有没有未知交易或残余库存？

### 17.2 股票／MEME／链健康视图

股票表：asset身份、Session、health flags、DEX价、token-equivalent参考价、USDG换算价、premium、source age、multiplier、pause、supply事件、实际size退出价、成本、NetCover、拒绝原因。

MEME 表：真实可验证池身份、raw与organic估计量、有效流动性、持有人／LP集中证据质量、税费／升级权限、退出quote、TTL、是否禁止下移、估值下界。未知用“未知”，不用绿色0。

链健康表将 L2 执行、provider、feed、L1 posting/finality 分列；部署 manifest 过期、schema drift、日历未知和磁盘预算各有独立告警。

### 17.3 每日报告格式

`DAILY_DECISION.md` 必含：证据日期／完整性、已算与未算数量、三个最接近通过的候选及真正 blocker、100U 当前政策下是否有可行仓位、所有费用与风险成本、无交易是否为合理选择、必须处理的基础设施缺口。

禁止只输出“accepted=0、测试全绿”。禁止用旧 paper runner 的历史虚拟盈亏为 RH 宣传收益。[B1 §6.4]

---

## 18. 非功能要求与系统不变量

### 18.1 可复现和可追溯

同一不可变 snapshot、code version、policy version、model version 的结果必须确定性一致；随机模型必须有 seed 与预注册试验编号。不能在报告发布后悄悄换输入或只保留表现最好参数。

结果产物包含：git HEAD／工作树 diff、Python／依赖版本、原始命令及退出码、snapshot hash、策略参数、case 数量、跳过原因、PASS／WARN／FAIL、已知 blocker。配置 `.sha256` 只是摘要，不等于人的授权签名。

### 18.2 安全和资源

RPC key 经批准后仅使用受限权限配置／secret store，日志脱敏；研究用户不可访问 signer 数据。面板默认 localhost／受控内网，不暴露 unauthenticated 的资金操作接口。

首版建议外部采数并发≤4、单 writer、watchlist≤12、RH 数据软预算2GiB；实际 CPU／RSS／I/O 与 p95 采数滞后必须度量。资源不足优先停新发现，不能让庞大 backfill 饿死已有仓位的健康与退出监控。

### 18.3 新不变量（在现有不变量之上，不替代）

| ID | 必须成立的约束 |
|---|---|
| RH-INV-01 | 只读／影子进程不能访问 signer 或公网交易广播能力 |
| RH-INV-02 | schema 未知／语义矛盾不能被转换为允许新仓 |
| RH-INV-03 | 未证实身份／代码／协议能力的池不能进入可部署终态 |
| RH-INV-04 | 每个新增硬闸有生产者、有读取、有终闸合取、有摘除变异测试 |
| RH-INV-05 | 资产缺价、缺路由与经济失败是不同状态，但都不能绕过准入 |
| RH-INV-06 | 新资金政策未批准时，旧参数与保护常量不变，LIVE 不因新配置自动解锁 |
| RH-INV-07 | 预算预占包含 pending；同一原始 token 余额不得跨桶重复记账 |
| RH-INV-08 | 股币乘数在数量／价口径中按定义应用一次；Chainlink 已调整价不再乘 |
| RH-INV-09 | HOLIDAY／pause／halt／未知状态不能允许股票追随 DEX 重新居中 |
| RH-INV-10 | MEME 下跌越界不得自动下移区间加风险 |
| RH-INV-11 | remove success 不得被等同于全部现金退出；残余库存保留风险额度 |
| RH-INV-12 | 实际 NAV 内已体现的 gas／滑点／费用不能在总 PnL 再扣一次 |
| RH-INV-13 | collect／桶间内部转账／外部入金不能分别被误记为新增利润 |
| RH-INV-14 | 原子退出失败不能导致盲目补单或重新开仓 |
| RH-INV-15 | unknown broadcast／nonce 未决时不释放资金、不重复执行 |
| RH-INV-16 | 单点 RPC／索引延迟不直接证明链停机；最终性必须有证据 |
| RH-INV-17 | EXIT_ONLY 的 swap 仍受独立报价、方向、金额、收款人、有效期约束 |
| RH-INV-18 | 准入门槛只可按已批准流程改变，不以增加 accepted 为优化目标 |

---

## 19. 实施顺序与任务包

每包产出代码／配对测试／原始日志／证据／VERDICT；只在当前授权范围内工作。**一个仓库同一时间只允许一个写入 worker**；只读审计可使用固定副本。按 B1 的现有工具规范使用 `qwen-task`，不要求重新启用已退役的派工方式。[B1 §6.6]

### RH-00：基线与证据链审计（第一包，不先重构）

输入 B1、B2、本文、仓库真实代码／配置／tests。复核 repo／HEAD／dirty changes／进程实际加载版本；记录四个保护进程但不重启。识别 legacy canary 指向封存 live 二进制的风险，不启用它。

使用 SQLite 一致性备份，追踪 factory probe 失败到具体 provider／method／响应／字段生产者；选择已知能算的阳性对照与失败候选比较，区分 RPC 退化、代码未支持、schema 缺失和真实经济失败。检查无断言测试与 placeholder topic/factory，避免拷贝。

交付：`P0_EXISTING_CODE_MAP.md`、`BASELINE_RAW.log`、`FIELD_PRODUCER_MAP.md`、`LEGACY_FAILURE_AUTOPSY.json`、`PERMISSION_MATRIX.md`、`VERDICT.json`。

验收：无进程改变／无密钥与广播；每个关键字段有来源；旧模型固定快照可复现。未修完旧链全量历史问题不必无限阻挡 RH 支线，但其共享根因不能进入新适配器。

### RH-01：链／资产／协议能力注册

建立免费预算内的 RPC 方法探测、registry 新旧 schema、地址来源与 attestation、V3/V4 身份分派。使用真实响应制作脱敏 fixture；人工构造 fixture 标记 synthetic。

交付：新增 registry／capabilities／pool_probe 与测试，`RH_CAPABILITY_MATRIX.json`、`ASSET_ATTESTATIONS.json`、`SCHEMA_COMPATIBILITY.md`。

验收：canonical／同 symbol 假币区分；schema 漂移 fail-closed；V4 不走 V3 factory；未知 feed／合约不伪造绿灯。所需外部能力缺失则清晰 blocker，继续离线测试。

### RH-02：数据采集、时段和健康闭环

建立隔离 RH SQLite、真实 writer→reader→gate；有限 Top-K collector、去重／reorg、session holiday、oracle／multiplier、USDG标记、RPC独立性与预算。

交付：collector／market_state、schema migration、`DATA_COVERAGE_REPORT.md`、`RPC_BUDGET_REPORT.json`。

验收：支持2026-09-07休市样本；记录API缓存与source age；日历／价格缺失准确分类；不中断旧进程，数据目录有上限。

### RH-03：组合政策、完整成本和终闸

在旧 NetCover 的输入契约上增加 RH 装配，不改变六常量。实现三桶政策、经济可行区间、native gas reserve、full terminal conjunction、零候选原因拆分。注册 policy conflict。

交付：netcover_inputs／portfolio_policy／terminal_gate／autopsy 与配对测试；`100U_FEASIBILITY.md`、`COST_DECOMPOSITION.json`、`BASE_INVARIANCE_DIFF.json`。

验收：100U旧单仓与新桶冲突不可自动解锁；成本按实际换腿；缺输入不等于失败；所有新增闸变异测试通过；共享 Base 固定快照无未批准变化。

### RH-04：账本与单 CORE Shadow 垂直切片

实现余额／LP 本金／应计 fee／奖励互斥估值、HODL lot、费用归因、虚拟资金意图与reservation。先一个 V3 CORE 池，从输入到结果跑通，再扩展第二个。

交付：pnl／shadow_runner、`PNL_RECONCILIATION.md`、`CORE_SHADOW_BASELINE.md`、独立 V3 数学差分结果。

验收：collect不造利、入金不造利、gas只扣一次、重平衡不清历史；同快照复现；手续费收入来自有效区间而非总TVL线性假设。

### RH-05：STOCK Shadow 与事件防护

在已有会计／成本上新增股票策略，验证参考价／乘数／USDG单位、盘中／盘外／假日、halt／公司行动、AP供应事件、源冲突、足额退出quote。AMC独立事件观察，不自动设为首个 live 标的。

交付：`STOCK_SHADOW_COMPARISON.md`、`STOCK_EVENT_FIXTURES.json`、`REFERENCE_PRICE_AUDIT.md`。

验收：拆股不制造盈亏；stale／pause／halt不重新居中；参考价不是无条件成交价；股票没有过闸不阻止CORE继续评估。

### RH-06：MEME 审计与 Shadow 可选包

实现可支持行为范围、权限风险、流量质量区间、LP集中正确口径、无追跌、TTL和退出库存会计。若免费证据不足，输出NO-GO，不加入昂贵替代采数。

交付：`MEME_READINESS.md`、`FLOW_QUALITY_LIMITATIONS.md`、对应测试。

验收：可100%闲置；不可卖／移除受限／未知Hook不通过；不把女巫分类当确定事实；不生成虚假APR／刷量组件。

### RH-07：受限执行适配与恢复测试（独立开发授权）

只有在只读经济结果有实质候选后再优先投入此包；否则保留安全设计与离线接口，不持续堆执行功能。借鉴 Base 安全契约，新增 RH 执行实现；先离线 calldata 与本地 fork，无生产私钥。

交付：`EXECUTION_CONTRACT.md`、`FORK_TRANSACTION_MATRIX.json`、`NONCE_RECOVERY_REPORT.md`、`EXIT_FAILURE_REPORT.md`。

验收：双开关签名前拦截；独立重检；目标／命令解码；模拟与实际交易绑定；超时不双开；分步退出与残余库存可对账。原子退出／direct sequencer 都不是基本闭环的替代品。

### RH-08：面板、告警、回归与数据毕业

扩展现有面板与日报；完成全测试、mutation、故障注入和恢复演练。最后一次编辑后重跑全量 pytest／go test，保存原始输出；环境敏感测试单列原因，不删不降级。[B1 §11]

交付：`READINESS_DASHBOARD.md`、`FULL_TEST_RAW.log`、`FAULT_INJECTION_REPORT.md`、`GRADUATION_VERDICT.json`。

验收：用户能看到本金／shadow／actual区别，知道何处未算成、何处经济失败；全部硬门禁可追溯；live默认false。

### RH-09：Tiny Live 请求包（不是自动执行包）

准备每个 profile 独立的候选、经济证据、拟用资金政策、单笔／日／总损失上限、地址与执行版本、退出路径、授权到期、监控负责人和失败处置说明。所有者批准之前签名／广播均为0。

微额“验管路”只能证明该规模的交易与会计可用，不能直接证明目标规模盈利。不能按 B2 的“最终资金5%–10%”机械缩小到费用吞噬收益的尘埃仓位；规模须同时满足已批准风险上限与该阶段验证目的。

交付：`TINY_LIVE_APPROVAL_REQUEST.md` 和待签审批记录模板。审批中任何缺项、政策冲突或证据过期，结果保持 `NOT_AUTHORIZED`。

---

## 20. 必测用例矩阵

本表是最低覆盖，不是测试数量指标。每个测试必须断言具体结果；仅“不抛异常”或“非 None”不足以验收。Synthetic fixture 与真实抓取 fixture 分目录，不伪装为实测数据。

| Case ID | 输入／故障 | 预期结果 |
|---|---|---|
| T01 | chainId46630／1／错误4663响应混入 | mainnet身份闸FAIL，禁止候选升级 |
| T02 | symbol正确但地址不是registry部署 | `ASSET_IDENTITY_MISMATCH` |
| T03 | assets为旧schema | 明确映射；null／空／closing-only不变成普通可交易 |
| T04 | assets为实际观察的新嵌套schema | 正确区分market／extended／overnight能力 |
| T05 | 未知enum／新旧语义矛盾 | UNKNOWN／CONFLICT，禁止新仓，不静默回退 |
| T06 | 已审核proxy implementation变化 | attestation过期，no-new，生成安全事件 |
| T07 | V3候选factory getPool不匹配 | 身份FAIL，不调用经济成功终闸 |
| T08 | V4 PoolId送入V3探针 | 明确协议分派，不报告factory缺失的经济失败 |
| T09 | v4存在白名单LP／自定义fee但未支持 | UNSUPPORTED，网页APR不影响结果 |
| T10 | 用PoolManager总余额当V4单池TVL | 数据契约拒绝／测试断言失败 |
| T11 | block number相同、hash不一致 | 标记分歧／重组；回滚受影响派生值 |
| T12 | RPC请求成功但JSON-RPC error字段存在 | 失败分类，不能当0余额／0费用 |
| T13 | 两URL属于同一provider后端 | 冗余不足，不能满足live多源门槛 |
| T14 | HTTP200但价格generatedAt未推进 | source stale，不能由fetch_time刷新健康 |
| T15 | 2026-09-07纽约时间盘中时钟 | HOLIDAY，不是RTH |
| T16 | 夏令时切换／提前收市／周末 | 日历映射正确，UTC转换不偏移一个小时 |
| T17 | raw2e18，multiplier1.25e18，underlying100 | token2／等价股数2.5／总值250 |
| T18 | Chainlink已是125，再遇multiplier1.25 | 仍125，不是156.25 |
| T19 | USDG=$0.98，股币参考$125 | 参考比价≈127.5510204 USDG/token |
| T20 | 拆股200→20、multiplier1→10 | 单token参考值仍200；raw余额不变 |
| T21 | token oraclePaused=true但feed可调用 | 禁止新增／recenter；保留旧价的陈旧标记 |
| T22 | newMultiplier等于current且无未来有效事件 | 不虚构公司行动；仍核对pause状态 |
| T23 | 闭市feed不更新 vs盘中异常不更新 | 原因分开，但两者不让新窄区间通过 |
| T24 | 参考报价可读但无足额DEX退出quote | `INPUTS_UNAVAILABLE: EXIT_QUOTE`，不是无风险折价 |
| T25 | 100U旧单仓50下限＋CORE42.5上限 | `CAPITAL_POLICY_CONFLICT`，不自动改金额 |
| T26 | MEME单资产跨多个池／钱包累计超2% | 资产聚合闸阻挡，不能拆单绕过 |
| T27 | 两意图并发读到同一剩余额度 | 原子reservation只允许可容纳的意图 |
| T28 | 价格上升导致存量超cap | NO_NEW／REDUCE_EVAL；不错误声称 admission bug |
| T29 | 有很多WETH但native ETH不足 | native gas reserve闸失败 |
| T30 | 单位资本净边际收益≤0 | 报告无有限经济仓位，不推荐加资解决 |
| T31 | q_min大于q_max | 经济可行区间为空，合法0配置 |
| T32 | 未知fee输入 vs合法计算fee=0 | 前者缺输入；后者可以经济FAIL；报告区分 |
| T33 | reward仅来自广告APR | 未验证reward收入不计，保留证据等级 |
| T34 | 总gas估计已含L1 data | 总成本不再次追加同一L1费用 |
| T35 | 两腿实际只换30%本金 | 换腿成本使用真实30%，不按100%重复计算 |
| T36 | 未来数据在当时不可获得 | 回放不允许前视；决策使用当时可见快照 |
| T37 | 极高volume但头寸全程out-of-range | 应计费为0／符合实际跨tick路径，不分摊全池APR |
| T38 | collect，价不变，gas=0 | 钱包增量与未领fee减少相抵，NAV不变 |
| T39 | collect，gas=0.10USD | NAV只下降0.10，不再扣一遍费用归因 |
| T40 | 外部入金10USD、无交易 | NAV增10，PnL为0 |
| T41 | 下跌后recenter | 累计亏损与HODL初始lot不被重置 |
| T42 | 同笔markout在30s／5m／30m | 分列，不三次累计同一亏损 |
| T43 | MEME下跌跌穿下界 | 不自动下移／补仓，进入受限退出流程 |
| T44 | 下跌池卖出失败但remove成功 | `REMOVED_RISKY_INVENTORY`，不显示cash closed |
| T45 | 原子exit中swap回滚 | remove亦视为未完成；独立重检后才可remove-only |
| T46 | 退出USDG导致加大USDG风险 | 不因action=exit绕过资产风险方向检查 |
| T47 | LIVE_TRADING=false／授权串错误 | 拦截在签名前；无签名副作用 |
| T48 | calldata含非白名单target／recipient | decoder拒绝，simulation成功也不能放行 |
| T49 | quote之后calldata／size／policy变化 | 原模拟失效；重新检查 |
| T50 | 单边LP的零数量腿 vs swap最小到账无约束 | 区分合法0与缺保护，不靠简单`!=0`判断全部安全 |
| T51 | 广播HTTP超时、链上已有同nonce | UNKNOWN→对账，禁止重复开仓和释放reservation |
| T52 | crash在持久化nonce／提交／回执任一阶段 | 恢复不重签重复意图，最终账本一致 |
| T53 | 仅L1posting滞后，L2多源继续推进 | 分层告警，不伪造execution停机结论 |
| T54 | 只有等待时长无L1证据 | 不自动进入L1_FINALIZED |
| T55 | 每道新增硬闸单独被摘除 | 对应危险样本出现错误放行，证明测试能抓漏接 |
| T56 | 旧Base模型同一SQLite快照新旧计算 | 未批准的逐闸结果差异=0 |
| T57 | RH数据库／日志达预算 | 停非必要采集，风险证据优先；不删除旧项目资料 |
| T58 | 策略用户尝试读keystore或导入signer | 权限／依赖测试拒绝，默认包保持只读 |
| T59 | 旧terminal字段无writer | producer-map验收FAIL，不把候选当经济证伪 |
| T60 | 策略0合格池／MEME全闲置 | 正常可解释结果，不强制下单完成配比 |

新用例可以增补，但不能用增补来替换原测试。B1 中宿主敏感进程扫描测试可能被审计命令自身触发，应保存完整现场、在无冲突环境复测；不得把真正签名／广播进程加入白名单消除失败。[B1 §10.4]

---

## 21. Read-only／Shadow／Tiny Live 毕业门槛

### 21.1 Stage A：数据与证据

至少72小时正向观察作为初始门槛，并通过日历／异常的合成测试。需要：关键字段真实生产、身份和能力证据清楚、数据质量可计算、RPC预算可维持、无不变量违反。72小时本身不证明盈利，也不强求完成所有股票季节事件。

**数据覆盖率分母必须是计划应观测的窗口**，不能删掉坏窗口后报告100%。初始目标：被选中用于收益评估的窗口，有效数据覆盖≥99%；关键状态未知时新增模拟仓位次数=0。未达到覆盖要求时可继续采集，但不毕业。

### 21.2 Stage B：Shadow

至少14个完整日，覆盖一个周末；股票还需足够的真实RTH／盘外样本，并用真实日历或合成事件覆盖休市、split、halt、pause、报价失效。仅跑到14天不自动PASS。[B2 §49–50，按本版补充]

同时满足：

- 未解释的账本差异=0；关键不变量违反=0；已知严重事件漏闸=0。
- 所有收益结果使用可获得数据、实际有效区间、费用净分成、预计往返成本及延迟；有独立数学／费用核验。
- 每个拟上实盘 profile 单独给出全成本正收益证据、HODL差异、退出压力情景和样本外结果。CORE通过不替STOCK／MEME担保。
- 参数在评价窗口前冻结；训练／调参窗口与评价窗口分离。报告区块重采样／时段分组不确定性、最差日和收益集中度，不把短样本正均值说成确定正EV。
- 保守情景下 NetCover 满足既有 `NETCOVER_TINY_LIVE=1.5` 与绝对利润门槛，实际size退出路径可复现；证据不够就是WARN，不靠加仓解决。

统计显著性不足时可申请**单独的验管路实验**，但审批文件须明确其目的不是证明盈利，并设可完全承受的损失预算。不能把该实验写成已经毕业的生产策略。

### 21.3 Stage C：Tiny Live

前置：Stage B对应profile通过、RH资金政策已批准、账户与合约权限验证、至少两套独立可用数据／执行证据路径、全流程本地fork／故障演练、净值对账通过、明确操作者和事故处置方案。

初始仅一个 CORE 池／一个资金动作闭环：开仓→观察→撤池／必要换腿→授权清理→完整会计。具体金额由已批准policy和实际成本决定，本文不将100U自动投入，也不授意增加本金。

观察至少30天作为扩容申请的一个条件，仍须：实际全成本净收益为正、HODL差可解释、费用／库存损耗可勾稽、无漏kill／重复交易／失控授权、退出在真实执行约束下可完成。不能让一个上涨周期的beta收益掩盖LP本身持续亏损。

### 21.4 Stage D：扩大与独立停止

扩大按profile、池、资本三维分别审批，不能一次放开全部50/30/20。正收益小样本不能自动指数加仓；每次增加后重新检查price impact、有效流动性占比和退出容量。

任一情况立即冻结扩容：收益主要来自未兑现奖励、成本明显高于回放、oracle／API语义漂移、未解释对账差、依赖免费能力不可维持、退出库存累积。不存在“为了按期交付必须开始交易”。

---

## 22. 迁移、回滚与旧系统保护

### 22.1 默认是旁路增量，不是替换运行中系统

在唯一活仓库按项目允许的本地分支／提交规则增量开发。切换分支／创建worktree会不会影响后台脚本读取文件，先由P0查清；未经确认不改变旧运行进程依赖路径。不得为了隔离又偷偷创建第二个“活仓库”成为新事实源。

RH使用独立数据库与报告目录；旧scanner可继续运行。需要常驻新collector时单独确认资源预算与运维启动权限，禁止默认搭载到旧watchdog或改旧systemd单元。旧paper只读观察，不拿来决定RH实盘。

### 22.2 软件回滚和资产回滚不同

只读阶段：停用新入口（按授权操作）、恢复旧配置引用，保留快照和报告。不得删除故障证据。

执行阶段：先进入EXIT_ONLY／锁定新意图，核对nonce、pending交易、真实余额和头寸，然后决定软件版本。**不能恢复旧DB快照就当链上交易没发生**；否则可能重复开仓或丢失负债。真实资金处置受当前有效风险与签名授权约束。

### 22.3 发布产物

每个本地commit附：变化清单、受影响接口、schema migration和回退说明、测试原始日志、Base不变性、profile gate verdict、尚未授权事项。禁止git push；没有实际运行的测试不标PASS。

---

## 23. 决策记录：哪些可直接推进，哪些保留人工签署

| 事项 | 本版决定 |
|---|---|
| 是否重写工程 | 否；Python＋SQLite增量 |
| 是否保留50/30/20 | 是，作为可闲置预算结构 |
| 当前是否可自动改旧100U规则 | 否；新policy仅shadow，live冲突显式阻断 |
| 六常量是否改变 | 否 |
| 第一个业务闭环 | 少量已验证V3 CORE；数据→经济→账本→Shadow |
| STOCK是否必须等CORE赚到钱才能做研究 | 否，可并行只读；但独立毕业，不能借CORE成功背书 |
| MEME是否必须花20%预算 | 否；默认live关闭，允许全闲置 |
| 是否允许未知Hook | 否；仅观察，不认定经济证伪 |
| 是否新建Go/Rust／NATS／PostgreSQL | 否 |
| 是否付费RPC／自建节点 | 否；先测免费可行性，不足报告blocker |
| 是否修改／重启原进程 | 否，需单独批准 |
| 是否启用旧canary | 否 |
| 是否已核验今天全部池／合约／gas | 否；浏览证据与链上attestation分开 |
| 是否授权签名／广播／生成密钥 | 否 |
| 是否保证盈利 | 否；以完整成本与可退出性实证决定继续或停止 |

需要签署的未来决策最少化为三类：**资本政策替代、执行开发／部署权限、限额真实资金试验**。其他只读研究可在既有允许范围推进，不反复询问已明确的基础偏好。

---

## 24. Agent 接手后的第一份报告必须回答什么

执行第一包时，不需要等用户重新解释项目。直接以 B1＋B2＋本PRD为输入，在原仓库读取并交付：

```text
1. 实际HEAD／分支／dirty changes／既有进程与文档是否一致？
2. 哪些“已实现模块”真的被当前Python研究层调用？
3. factory_registry_probe_incomplete 的每个最小可复现根因是什么？
4. 每个终闸字段由谁生产？是否还存在无writer或恒None？
5. RH的免费数据能力实际有哪些？哪些未知／不可用？
6. 当前可证明的V3／V4／资产身份有哪些？
7. 在100U旧授权与新三桶提案下，为什么可以／不能下单？
8. 第一条CORE Shadow闭环最少需要改哪些文件？
9. 旧Base固定快照是否保持不变？
10. 哪些操作仍未授权？
```

**首包完成标准不是“设计很完整”，而是输出一份可追溯的最小改动清单和阻断原因，让后续每个改动都能对应到真实代码和测试。**

配套《AGENT_START_AND_TASKS_CN.md》提供可直接交给主控 Agent 的任务指令；配套 TOML 只用于实现新配置契约，不是旧程序可直接加载的生产配置。

---

## 25. 需求追溯与验收责任

| 需求族 | 主章节 | 主任务 | 主要测试 | 通过所需证据 |
|---|---|---|---|---|
| 原工程保护 | §0、§2、§22 | RH-00／08 | T47、T56、T58 | HEAD／diff／权限与全回归日志 |
| 零候选可解释 | §8、§11 | RH-00／03 | T12、T32、T55、T59 | producer map＋autopsy＋mutation |
| 三桶与资金授权 | §6、§13 | RH-03 | T25–T31、T60 | 政策冲突与原子reservation测试 |
| 链／协议／资产身份 | §3、§7 | RH-01 | T01–T13 | 同块attestation／能力矩阵 |
| 股票单位／市场制度 | §9、§10.2 | RH-02／05 | T14–T24 | API真实fixture＋日历／split测试 |
| 真实经济可执行性 | §10–§11 | RH-03／04 | T30–T37 | 成本／有效费收入／样本外结果 |
| 实际PnL不重扣 | §12 | RH-04 | T38–T42 | raw余额／fees／NAV勾稽 |
| MEME退出与可选性 | §10.3、§15 | RH-06 | T43–T46、T60 | 退出失败／残余库存测试 |
| 受限执行与恢复 | §14–§15 | RH-07 | T47–T54 | fork、decoder、nonce恢复 |
| 可运营与可回退 | §16–§18、§22 | RH-08 | T11、T52、T57 | 数据预算、告警、恢复与原始日志 |

主控 Agent 对范围／接口负责；实施 Agent 对代码与测试负责；独立只读审计者对接线、假绿、成本／会计及权限负责。策略批准与资金签署始终属于项目所有者，不由模型分配给自己。

---

## 26. 本次研究的限制与接下来必须补齐的事实

**已完成：** 阅读两份完整上传文档；核对官方网络、股票API和乘数语义、Uniswap部署／版本资料；比较Hummingbot、Arrakis、Gamma、Demeter等公开方案；核对近期gas、链状态报道差异和交易日历；形成增量PRD、任务书、配置契约与验收矩阵。

**没有完成，也不作虚假声明：** 未登录用户VPS，未读取真实仓库源码；未重跑其3109项Python／57包Go测试；未从本次容器取得成功RPC回执／字节码／实时gas；未验证具体AMC或ETF池身份／收益；未取得用户provider key／套餐能力；未部署／签名／广播。

本次容器直连失败原因为DNS解析，不代表RH链故障；网页工具读取到官方assets响应，但不等于已在用户运行环境完成可复现完整数据落盘。执行Agent必须留存新的原始响应与区块证据。**在证据缺口补齐之前，结论是“可执行只读改造”，不是“某个池现在值得实盘”。**

---

## 27. 来源索引与核对范围

统一核对日期为2026-09-07；除明确列出的发布时间，页面无固定发布日期的不另造日期。下面URL使用代码形式便于Agent原样检索。源码参考未构成完整安全审计；网页支持的事实与本文工程提案分开。

### 内部输入

**B1** `PROJECT_STATE_AND_ARCHITECTURE_20260907_CN.md`。用户上传，状态审计；项目路径／权限／测试与缺陷的主基线。

**B2** `Robinhood_Chain_LP_Bot_50_30_20_全面转向设计文档_v1.0.md`。用户上传，目标设计；预算桶／profile／风险愿景的基线，冲突按本版D01–D14处理。

### 官方链与资产资料

**R01 — RH连接与节点。** 官方 `https://docs.robinhood.com/chain/connecting/`。核对4663／46630、ETH、端点、公开RPC限制及提供商说明；未证明用户已获得相关服务。

**R02 — Uniswap上线RH。** 官方2026-07-02发布，`https://blog.uniswap.org/robinhood-chain-is-live`。核对V2／V3／V4／UniswapX及公开集成；不是任何单池收益证明。

**R03 — RH Token Contracts。** 官方 `https://docs.robinhood.com/chain/contracts/`。WETH／USDG地址种子；本文未重新链上核验字节码。

**R04 — RH Stock Token APIs。** 官方 `https://docs.robinhood.com/chain/stock-token-apis/`。核对REST语义、缓存、字段结构、公司行动接口用途。

**R05 — 官方assets实际响应。** `https://api.robinhood.com/rhj/assets`。2026-09-07通过网页读取的JSON观察；新嵌套session schema与tokenDecimals。文中摘录不等于完整原始快照。

**R06 — Chainlink RH Tokenized Equities。** 官方 `https://docs.chain.link/data-feeds/tokenized-equity-feeds/robinhood`。核对token-equivalent价、乘数、token oracle pause与闭市feed行为。

**R07 — Building with Stock Tokens。** 官方 `https://docs.robinhood.com/chain/building-with-stock-tokens/`。核对raw／UI语义及一级申赎资格边界。

**R08 — Uniswap部署与Router版本。** 官方 `https://developers.uniswap.org/docs/protocols/v3/deployments/v3-robinhood-chain-deployments`；`https://developers.uniswap.org/docs/trading/swapping-api/supported-chains`。部署种子与链级版本参考，须与实际ABI／字节码复核。

**R09 — Uniswap V4机制。** 官方 `https://developers.uniswap.org/docs/sdks/v4/guides/pool-data`；`https://developers.uniswap.org/docs/protocols/v4/guides/state-view`；`https://developers.uniswap.org/docs/protocols/v4/guides/custom-accounting`；`https://developers.uniswap.org/docs/protocols/v4/concepts/dynamic-fees`。池身份、状态读取、hook delta／动态费；不代表任意hook获准使用。

**R10 — NYSE交易日历。** 官方 `https://www.nyse.com/trade/hours-calendars`。2026-09-07劳动节休市与时段核对；策略仍须运行时维护日历版本。

**R11 — RH Gas／Finality。** 官方 `https://docs.robinhood.com/chain/gas-and-fees/`；`https://docs.robinhood.com/chain/transaction-finality/`。费用组成与最终性层级；不是本钱包实时费用测量。

### 当前生态观察与事件

**R12 — 9月4日posting延迟说明。** Arbitrum官方社交账号检索结果 `https://x.com/arbitrum/status/2095939844987891760`；更正报道（2026-09-05）`https://m.cnyes.com/news/id/6598508`。官方原帖正文通过搜索索引可读，直接页面读取受限；本文不作独立故障取证结论。

**R13 — Bitquery自有链上分析。** 2026-09-04，`https://bitquery.io/investigations/robinhood-chain-gas-price-25x`。8月下旬至9月初gas上升观察；仅作为压力场景依据，非今天固定成本。

**R14 — DefiLlama RH链页面。** `https://defillama.com/chain/robinhood-chain`。本次页面观察USDG在RH稳定币中的占比约67.34%；可能缓存／不同步，不可直接触发交易。

**R15 — GeckoTerminal候选页。** `https://www.geckoterminal.com/robinhood/pools/0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`。本次页面标为USDG/WETH UniswapV3 0.01%；仅发现种子。未使用页面APR作为盈利证据。

**R16 — AMC事件报道。** Barron's，2026-09-04，`https://www.barrons.com/articles/amc-stock-robinhood-attack-vile-c3cc9d42`。仅用于说明发行方／底层公司事件风险，不将争议观点当法律结论或池安全证明。

### 公开工程与研究

**R17 — Hummingbot Uniswap connector。** 官方 `https://hummingbot.org/exchanges/gateway/uniswap/`。支持网络含robinhoodchain，CLMM列V3；未证明V4 LP支持。

**R18 — Arrakis版本弃用通知。** 官方2026-06-15，`https://arrakis.finance/blog/v1-v2-deprecation`。V1/V2弃用与Modular方向；不建议以旧v2-core作为当前默认依赖。

**R19 — Gamma Hypervisor。** 作者仓库 `https://github.com/GammaStrategies/hypervisor`。区间／仓位管理架构参考；未做本次完整合约安全审计。

**R20 — Demeter。** 作者仓库 `https://github.com/zelos-alpha/demeter`。Python DeFi回测、V3模型参考；RH数据适配、退出成本与执行验证仍需本项目完成。

**R21 — Uniswap AI集成资料。** 官方仓库 `https://github.com/Uniswap/uniswap-ai`。开发／规划辅助，不授予模型交易和资金权限。

**R22 — ERC-8056。** 规范页面 `https://eips.ethereum.org/EIPS/eip-8056`。UI multiplier与raw accounting区分；应以具体部署实现为准。

**R23 — USDG本链部署信息。** Paxos官方 `https://docs.paxos.com/guides/stablecoin/usdg/mainnet`。核对RH USDG版本与跨链模型，不假设普通用户可直接一级兑付。

**R24 — V4 protocol-fee治理讨论。** Uniswap治理论坛 `https://gov.uniswap.org/t/temp-check-activate-v4-protocol-fees/26162`。这是提案／讨论，不能当作RH已生效参数。

**R25 — LVR研究。** 作者论文摘要，Milionis等，`https://arxiv.org/abs/2208.06046`。用于区分loss-versus-rebalancing与其他基准；本文会计与测试为工程设计，不声称论文证明本策略盈利。

---

## 28. 最终验收结论模板

```text
VERDICT: PASS | WARN | FAIL
SCOPE: READONLY | SHADOW | EXECUTION_BUILD | TINY_LIVE_REQUEST
ACTUAL_REPO_HEAD:
SOURCE_SNAPSHOT_HASHES:
POLICY_VERSION:
MODEL_VERSION:

Baseline preserved:
Protected constants unchanged:
Protected processes untouched:
Keys created / signatures / broadcasts: 0 / 0 / 0  (只读与影子阶段必须为0)

Candidates discovered:
Economics computed:
Computed positive:
Computed negative:
Inputs unavailable:
Unsupported:
Policy blocked:
Terminal eligible:

CORE evidence:
STOCK evidence:
MEME evidence:
PnL reconciliation:
Exit feasibility:
Mutation tests:
Base fixed-snapshot invariance:
Raw test logs:

Capital policy approved for live: false  (未经独立授权保持false)
Unresolved blockers:
Next allowed task:
Explicitly not authorized:
```

**本版的成功不是把一个三桶机器人“写完”，而是让旧工程更快、可靠地回答：在当前100U授权与可获得的数据条件下，哪些RH公共池真的能做、用多大仓位、持有多久、退出要付多少、哪里赚了钱，以及什么时候必须不做。**
