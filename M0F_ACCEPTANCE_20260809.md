# LP Bot PRD v2.1 · M0F 漏斗可用性轮验收（2026-08-09）

**分支：** `feat/prd-v2.1-m0-shadow`

**文档状态：** 最终验收证据已收口于本提交。

**启动边界：** M0F 的成功标准是漏斗可计算、排序与证据边界可审计，不要求 `accepted>0`。**14 天 shadow 计时只有在最终漏斗覆盖被判定为可接受，并由指挥官显式决定起算后才开始。** 当前未启动 14 天计时，§12.0 gate 仍为 `INSUFFICIENT_EVIDENCE`，M1-A/M1-B 仍禁止开工。

## 1. 修复范围与提交

| 项目 | commit | 结论 / 正式证据 |
|---|---|---|
| FIX-R1a | `98801e1` | 逐池定位第五闸不可计算根因；`reports/lp_funnel_diagnostics/20260809_091144/` |
| FIX-R1b | `a5c26b5` | 实测深度链使同轮可计算覆盖达到 4/10；报告中的 NetCover 均为 ADD-1 前口径 |
| FIX-P2 | `9277bcc` | panel 有界并发、强 token、共享 gate 语义与真实攻击 smoke |
| ADD-1 | `cc67304` | FeeEV 区间感知、H 固定拖累感知；`reports/lp_funnel_add1/20260809_104335/` |
| FIX-R2 / ADD-2 | `0302a69` | 正式有效证据仅 `reports/lp_funnel_rerank/20260809_135500/` |
| FIX-R7 | `1b4c1bf` | 停止跟踪 90 个 Python bytecode 文件并加入 ignore |
| FIX-R6 | `7eee239` | 按 PASSIVE / TACTICAL profile 路由 ER horizon，跨 profile fail-closed |
| FIX-DOC / E2E | 本提交 | 本文与 HANDOFF；最终验收见 §9 |

所有改动维持 paper/read-only：无钱包、私钥、签名、approve、广播、写交易或付费数据端点；未放宽既有 NetCover/风险阈值。

## 2. FIX-R1a — 根因证据

R1a 以 M0P 周期 `2026-08-09T08:19:38.034782+00:00` 和只读复探 tip `49738687` 为基准。7 个已 resolve 池的 slot0/liquidity 读取均成功，因此缺失并非 429、超时或 ABI selector 不兼容。

根因分类如下：

- resolver 只探旧 Initial factory：USDC-CBMEGA、O-USDC 实际在官方 Gauges V3 唯一命中；MSUSD-MSETH 在两个官方后续 factory 命中，必须歧义关闭。
- 非稳定币对已有 pair price / active liquidity，却缺可证明的 USD quote 与 AERO reward 换汇深度；pair price 不得冒充 USD。
- WETH-USDC 的实测路径产生 `range>100%`，旧 replay 进入平方根数学域错误；正确行为是 replay 前显式永久 fail-closed，不能 clamp。
- USDC-VVV 九项输入齐全，但 NetCover 诚实低于 shadow gate；不允许为制造通过而改阈值。

逐池地址、factory 返回、swap 数与断点见 `reports/lp_funnel_diagnostics/20260809_091144/root_causes.md` / `.json`。

## 3. FIX-R1b — 覆盖恢复（ADD-1 前口径）

最终 R1b live scan 为 `733 → 10 → 10 → 10 → 0 accepted`，同一 live cohort 的完整可计算记录为 **4/10**，相对 R1a/M0P 基线 **1/10** 提升。由于免费 DefiLlama top-10 会变化，这是一项 live 能力对比，不宣称十条记录逐一配对。

| symbol | ADD-1 前 NetCover | 结果 |
|---|---:|---|
| USDC-CBMEGA | 0.422059 | 完整可计算，低于 shadow |
| O-USDC | 0.311985 | 完整可计算，低于 shadow |
| WETH-MORPHO | 0.438460 | 完整可计算，低于 shadow |
| WETH-USOL | 0.070430 | 完整可计算，低于 shadow |
| 其余 6 条 | — | `ambiguous_multi_factory_pool`，永久 fail-closed |

上述全部 NetCover 数字仅用于 R1b 覆盖率验收，明确标记为 **`口径=ADD-1前`**，已被 ADD-1 的最终经济性口径取代。实现同时满足：三官方 factory、双 token order 全探；bytecode/token0/token1/decimals/tick 验证；固定区块换汇路由取最高同名义成本；两条零流动性 watchlist 任一读失败或变成可执行即整包 fail-closed；range `==100`、`>100` 与非有限值在 replay 前拒绝。

证据：`reports/lp_funnel_depth_fix/20260809_100700/before_after.md` / `.json`；定向验证 `60 passed`。

## 4. ADD-1 — range-aware FeeEV 与 drag-aware H

FeeEV 以 168h 的七日 APR 证据为固定锚，不再按目标 H 线性放大；目标 H 只通过 `recommend_range_pct(sigma_pair, H)` 和 canonical raw position liquidity 改变费用份额。缺 pair sigma、合法 `<100%` range、内部证明的 price/L 或 decimals 时，`fee_ev_usd=None`。

三池 H7→H30 反比自检：

| pool | H7 range | H30 range | H7 FeeEV | H30 FeeEV | H30/H7 |
|---|---:|---:|---:|---:|---:|
| USDC-CBMEGA | 9.741627% | 20.167084% | 0.191802762 | 0.094188404 | 0.491069 |
| O-USDC | 5.634036% | 11.663563% | 0.133234816 | 0.065117587 | 0.488743 |
| WETH-MORPHO | 6.310430% | 13.063831% | 0.141732318 | 0.069334115 | 0.489191 |

三者接近 `sqrt(7/30)=0.483046`，均不是已废弃的线性 `30/7=4.285714` 放大。

固定拖累 H 选择使用：

```text
drag_apr = (2 × fee_tier + gas_usd / 50U) / (H / 8760) × 100
```

`DRAG_APR_MAX=15%` 只是 H-selection model constant，不是新增或放宽的入场阈值。算法从 ER-policy H 开始，仅沿本 profile 的冻结离散集合向上选择最小合格 H；若最大 H 仍超 15%，置 `high_drag_flag=true` 并继续正常 NetCover 评估，不直接接受或拒绝。

USDC-VVV 三口径对比：

| 口径 | H / source | FeeEV | NetCover | expected net yield |
|---|---|---:|---:|---:|
| ADD-1 前 | 168h / historical ER policy | 0.061290082 | 0.040912955 | -1.436770420 |
| Task A only | 168h / `ER_policy` | 0.061290082 | 0.040912955 | -1.436770420 |
| Task A+B | 720h / `drag_adjusted(from=168)` | 0.029880723 | 0.005780933 | -5.138960317 |

最终 ADD-1 live run 为 `732 → 10 → 10 → 10 → 0 accepted`、4/10 完整可计算。`reports/lp_funnel_add1/20260809_103217/` 是无效 pre-fix 诊断，正式证据仅 `20260809_104335`；定向验证 `62 passed`。

## 5. FIX-R2 / ADD-2 — Stage-1 proxy 与目标研究

正式有效结果仅来自 `reports/lp_funnel_rerank/20260809_135500/`：

- 同一 proxy-top-N 研究批次 30 条；16 个 proxy/true NetCover 完整可计算对参与相关性。
- Spearman `0.473529`，满足 `>=0.3` 且至少 8 对的双条件；production recommendation 为 `PROXY_NETCOVER`。
- top-K 命中 `7/10`。定义为 proxy 降序 top-K 与 true NetCover 降序 top-K 的交集，分母为 `min(K, 同批完整对数)`。
- 研究运行实际评估 union 47 条、最终 `accepted=0`；`proxy top-30 ∪ 所有目标标签 live rows` 仅用于研究。相关性只使用 proxy-top-30 子 cohort，目标扩展不得改善相关性。
- proxy 仅使用免费 DefiLlama Stage-1 字段、固定 M1 50U 和固定 30d 比较 H；缺 sigma/fee tier 或未知 reward category 时不可用并回退原 APR 排序。terminal NetCover 仍是唯一经济性入场闸。

ADD-2 目标表没有 pool id，因此不使用陈旧 APR 猜池，而将每个 `Base / aerodrome-slipstream / symbol` 标签扩展到所有当次 live 精确匹配。结论如下：

| symbol | live / coarse | terminal / calculable | best true NetCover | accepted | 结论 |
|---|---:|---:|---:|---:|---|
| USDC-AVAIL | 1 / 0 | 1 / 1 | 0.278670 | 0 | live，但未过 coarse TVL；研究-only |
| CADC-USDC | 1 / 0 | 1 / 1 | 1.357083 | 0 | 数学 NetCover pass 也不得绕过 coarse gate |
| MSUSD-USDC | 2 / 1 | 2 / 2 | 1.073247 | 0 | 一条缺 reward persistence；另一条研究-only |
| XSGD-USDC | 1 / 0 | 1 / 1 | 1.653330 | 0 | 数学 NetCover pass 也不得绕过 coarse gate |
| VCHF-USDC | 1 / 0 | 1 / 1 | 0.189685 | 0 | live，但未过 coarse TVL；研究-only |
| WETH-USDC | 7 / 2 | 7 / 3 | 0.320386 | 0 | 多地址/歧义与研究-only 混合，不能猜 pool id |
| WETH-CBBTC | 4 / 3 | 4 / 1 | 0.150045 | 0 | 多地址/歧义与研究-only 混合 |
| USDC-CBBTC | 7 / 4 | 7 / 3 | 0.935979 | 0 | reward persistence、歧义与研究-only 混合 |

目标标签只是验证集合，**从不进入 allowlist、不绕过 coarse gate、不直接改变 production rank、更不直接 accepted**。若标签不在 live universe，必须报告 `NOT_IN_LIVE_UNIVERSE`，不得编造。

三次试跑均已显式作废，不能与正式证据混用：

1. `20260809_111500`：错误地跨 screened project 扩展目标，运行中止。
2. `20260809_113000`：terminal 汇总未独立复验精确 target identity，运行中止。
3. `20260809_114000`：CADC-USDC / XSGD-USDC 研究-only 行错误进入 operational accepted；整轮连同相关性全部 invalidated。

正式 135500 运行记录逻辑只读 RPC `5579` 次，重试前保守上界 `9585`；无钱包、签名、广播、付费数据、阈值变更或 daemon。

## 6. FIX-P2 — public panel 边界加固

panel 默认 `request_queue_size=16`、`max_threads=16`，以 `BoundedSemaphore` 限制工作线程；并发槽满时立即返回 503，连接结束后在 `finally` 释放槽。token 不仅要求长度，还拒绝低熵/重复模式，错误提示只给出 `openssl rand -hex 32` 生成方法。panel 与 gate 共享同一个 `_REENTRY_SUFFIX` 与 `MIN_UNIQUE_ROOT_POOLS` 定义，避免安全语义漂移；no-auth 警告保持可见输出顺序。

真实进程 smoke：missing token 401、正确 token 200、POST 405、path traversal 404、`"a"×32` 弱 token 启动退出 1；服务 SIGINT 退出 0，无残留 panel 进程。确定性慢连接回归验证第二连接立即 503，槽释放后恢复 200。证据为 `reports/lp_panel_hardening/20260809_102707/`；定向 pytest `30 passed`。

## 7. FIX-R6 — profile horizon 路由

ER regime 先由已测 sigma/ER 产生，再按记录自身 profile 映射：

| profile | range-bound | neutral | trending | 合法离散集合 |
|---|---:|---:|---:|---|
| PASSIVE | 168h | 336h | 720h | 168 / 336 / 720h |
| TACTICAL | 6h | 24h | 72h | 6 / 12 / 24 / 72h |

TACTICAL 的 12h 不是 ER 基础候选，只能由 ADD-1 固定拖累逻辑从 6h 向上选择。候选预填的跨 profile H/drag 会先清除；未知 profile、缺实测 sigma/ER 或 profile 不合法 H 均不猜测，保持缺失并 fail-closed。

## 8. FIX-R7 — Python bytecode 卫生

`.gitignore` 已加入 `__pycache__/` 与 `*.py[cod]` 等规则；提交从 Git index 移除 **90 个**历史跟踪的 `.pyc`，不删除用户的本地可再生 bytecode。当前 `git ls-files '*pyc'` 为 `0`，后续 pytest 不应再制造 tracked pyc diff。

## 9. 最终 E2E / 全量验收

最终代码 live scanner `--once` 的 as-of 为 `2026-08-09T12:55:47.359625+00:00`，stdout 为 **`733 → 30 → 30 → 30 → 0 accepted`**。operational 30 条 score 中：

- **16/30** 有有限 NetCover，可计算覆盖率 **53.3%**；panel 与 canonical `_read_funnel` 均解析为 16，口径一致。
- **14/30** 显式 `permanent_fail_closed_reason=ambiguous_multi_factory_pool`，没有默认值或猜池绕过。
- 30 条 `stage1_ranking_method` 全部为 `PROXY_NETCOVER`；最终 `accepted=0`，`vetted_menu.json=[]`。
- MSUSD-USDC 的 NetCover 为 `1.035762`，数学 gate 为 PASS，但 `entry_eligible=false`，原因为 `REWARD_PERSISTENCE_MISSING`；stable gate 亦为 false，因此 `vetted=false`、`accepted=false`。这证明 proxy 与第五闸不会绕过前置入场资格或稳定性闸。

正式证据目录为 `reports/lp_m0f_acceptance/20260809/`；其中 `scanner.db` 是按约定忽略的 runtime artifact，提交证据为 gate report 与空 `vetted_menu.json`。

panel 最终真实进程攻击 smoke：无 token 401、正确 token 200、POST 405、path traversal 404；弱 token 启动 exit 1 且含 `openssl rand -hex 32` 提示；强 token server 经 Ctrl-C exit 0，无 panel/scanner 残留进程。专门的连接耗尽用例为 `1 passed, 29 deselected`，验证占满唯一 worker 时返回 503 并在释放后恢复。

§12.0 gate 最终仍为 **`INSUFFICIENT_EVIDENCE`**：0 unique identities、0 unique root pools；未关闭严重 RPC incident 为 0，该子闸 PASS。`accepted=0` 和空 live-vetted menu 下不启动 runner，不能用 fixture 代替。

测试与 collection：

- `pytest tests/ --collect-only -q`：**2836 collected，0 error**。
- `pytest tests/ -q`：**2822 passed, 14 skipped in 96.70s**；14 个仍是 D1 精确历史环境 nodeid skip，不冒充 pass，0 failed。

红线与仓库卫生：

- 任务包列明的 4 个阈值保护文件 diff 为 0；Go 源码 diff 0，M1 源码 diff 0。
- `scripts/lp_long_horizon/` 源码 diff 0；唯一相关变化是 R7 将历史 tracked pyc 移出 index。
- danger-path 扫描 0，新增依赖 0；本轮唯一新增外部 URL 是官方 Aerodrome deployment 证据。
- frozen repo 内今日 mtime 变化为 0；3 个历史 dirty artifact 原样保留，没有冒充本轮改动或擅自清理。
- tracked pyc 为 0。
- 既有长跑进程 PID `1349731` 存活且 cwd 正确；本轮没有停止或替换它。验收结束后无 scanner/panel 残留。
- FIX-DOC/E2E 已收口于本提交；未合并、未推送远端。

## 10. 验收裁决

**PASS / READY FOR COMMANDER REVIEW。** R1a、R1b、ADD-1、R2/ADD-2、P2、R6、R7 与最终 E2E 已按 fail-closed 和只读边界验收通过，并由本提交收口。

`accepted=0` 不构成单独失败条件；本轮关键是输入、排序、缺失理由和研究/生产边界可审计。最终 **16/30（53.3%）** 的可计算覆盖是否已达到业务上“可接受”的起跑水平，仍由指挥官判断。14 天 shadow 尚未启动；只有指挥官认可覆盖并显式决定起算后才开始计时。合并、推送与 M1 放行也仍是独立指挥官决定。
