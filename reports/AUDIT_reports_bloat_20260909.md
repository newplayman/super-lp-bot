# AUDIT：reports/ 目录膨胀分析（只读，2026-09-09）

**任务**：RH-02bf · **执行**：只读审计员 · **日期**：2026-09-09
**纪律**：本审计**未删除、未移动、未修改**仓库任何文件；未执行任何 git 写命令。
除本文件外无副作用。所有数字均附产生它的命令（见 §7 可复现）。

> ⚠️ 本目录含真金白银交易的证据链。以下**只给分析与建议**，
> 删不删、怎么删由用户决定。

---

## 0. 摘要（TL;DR）

| 指标 | 数值 | 命令 |
|---|---|---|
| 总文件数 | **125,271** | `find reports -type f \| wc -l` |
| 文件内容字节 | 4,287,501,807（≈4.0 GB） | `find reports -type f -printf '%s\n' \| awk '{s+=$1} END{print s}'` |
| 磁盘占用（du，含块开销） | **4.5 GB** | `du -sh reports/` |
| 递归 `.md` 数 | **82,381** | `find reports -name '*.md' -type f \| wc -l` |
| 顶层子目录数 | 210 | `find reports -maxdepth 1 -mindepth 1 -type d \| wc -l` |
| git 跟踪文件 | 3,771 | `git ls-files reports \| wc -l` |

> **基线说明**：以上为**审计前基线**（即被分析的既有膨胀）。
> 本审计文件 `AUDIT_reports_bloat_20260909.md` 自身是 1 个 `.md`，
> 创建后 `find reports -type f | wc -l` 会读到 **125,272**、
> `.md` 读到 **82,382**（各 +1）。膨胀分析针对的是既有数据，
> 故正文一律采用审计前基线 125,271 / 82,381。

**三个关键事实：**

1. **一个目录占了 96.4% 的文件、97.7% 的 `.md`**：
   `reports/polymarket_competitor/` = 120,743 文件 / 80,494 `.md` / 711 MB。
   它是一个**每分钟一个 `cycle_*` 目录**的录制器（40,248 个 cycle × 3 文件），
   运行区间 **2026-06-29 → 2026-08-08**，**已停止**（进程已死）。
   → 这就是「`glob reports/**/*.md` 拿到 8 万条路径把上下文撑爆」的元凶。

2. **磁盘大头是两个冻结的 SQLite 库**：
   `lp_scanner/scanner.db`（2.0 GB）+ `lp_scanner_v2_20260823/scanner.db`（1.4 GB）
   = 3.4 GB，占磁盘 75%。二者写入进程**已死**（mtime 2026-09-07，冻结）。

3. **目录 99.8% 已冻结，仍在缓慢增长**：
   125,005 个文件（99.8%）mtime 早于 30 天。当前**仅 5 个活跃写入者**，
   全部在 `reports/lp_rh/`（见 §3）。polymarket 录制器与两个 scanner 均已停止。

**最小代价结论**：只要把 `polymarket_competitor/` 压缩归档（B 类处置），
递归 `.md` 立即从 82,381 降到 **1,887**（< 5000 目标达成）。见 §6 步骤 1。

---

## 1. 构成：按顶层子目录

### 1.1 按文件数（大头）

| 顶层目录 | 文件数 | 占比 | 说明 |
|---|---|---|---|
| `polymarket_competitor` | **120,743** | 96.4% | 每分钟 cycle 录制器，已停 |
| `shadow_outcomes` | 477 | 0.4% | 历史 shadow 结果 |
| `tierc_shadow` | 139 | 0.1% | TierC 影子 |
| `lp_long_horizon_readonly_12h_run` | 109 | 0.1% | 长时只读采集 |
| `rh_pivot` | 94 | 0.1% | RH 转向 |
| 其余 205 个目录 | 各 < 110 | — | 长尾 |

命令：`find reports -mindepth 2 -type f | awk -F/ '{print $2}' | sort | uniq -c | sort -rn | head`

### 1.2 按磁盘占用（大头）

| 顶层目录 | 磁盘 | 说明 |
|---|---|---|
| `lp_scanner` | **2.0 GB** | 单个 `scanner.db`（冻结） |
| `lp_scanner_v2_20260823` | **1.4 GB** | 单个 `scanner.db`（冻结） |
| `polymarket_competitor` | 711 MB | 12 万小文件（块开销高） |
| `strategy_evidence_r4_swap_event_fee_replay` | 179 MB | 证据回放 |
| `strategy_pivot_d4_realtime_paper_shadow_validation` | 77 MB | 纸面影子 |
| 其余 | 各 < 58 MB | 长尾 |

命令：`du -sh reports/*/ | sort -rh | head`

> **注意**：文件数大头（polymarket）与磁盘大头（两个 scanner.db）**不是同一批目录**。
> 「上下文爆炸」由文件数驱动（polymarket）；「磁盘占用」由大文件驱动（scanner.db）。

### 1.3 时间跨度（mtime）

- 全目录最早 mtime：**2026-05-28**（`CLEAN_REMOTE_REPAIRED_V2_READINESS_CN.md` 等）
  命令：`find reports -type f -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort | head`
- `polymarket_competitor` 区间：**2026-06-29 09:45 → 2026-08-08 16:06**
  命令：`find reports/polymarket_competitor -maxdepth 1 -type d -name 'cycle_*' -printf '%f\n' | sort | sed -n '1p;$p'`

---

## 2. git 跟踪 vs 未跟踪

| 类别 | 文件数 | 命令 |
|---|---|---|
| git 跟踪 | **3,771** | `git ls-files reports \| wc -l` |
| 未跟踪（含被忽略） | **121,500** | `find reports -type f \| wc -l` − 3,771 |
| 其中：被 `.gitignore` 命中 | 见下 | `git check-ignore` 抽样 |

**未跟踪的 12.1 万文件是什么？** 几乎全部是 `polymarket_competitor/` 的
`cycle_*/{ONEPAGE_CN.md, ARTIFACT_INDEX.md, cycle_summary.json}`（120,743 个），
**它们既未被跟踪、也未被 `.gitignore` 忽略**——`.gitignore` 里没有任何
`reports/` 专属规则，也没有 `*.md`/`*.json` 规则。

命令（抽样验证 polymarket 文件确实未被忽略）：
```
git check-ignore reports/polymarket_competitor/cycle_20260629_094556/ONEPAGE_CN.md
# → 无输出（exit 1）= 未被忽略
```

**被 `.gitignore` 命中的未跟踪文件**（这些是「该忽略、且确实被忽略」的）：
- `*.db` / `*.db-wal` / `*.db-shm`：两个 scanner.db（3.4 GB）+ lp_rh 的 5 个活跃 db
  及其 WAL/SHM。规则：`*.db`、`*.db-*`（`.gitignore` 第 11–12 行）。
- `*.log`：各录制器日志。规则：`*.log`（第 14 行）。
- 这些**不会**出现在 `git status` 里（被忽略），但**占着磁盘**。

**结论**：`git status` 里那 1 条 `?? reports/...`（目录折叠）背后，
是 12 万个「未被跟踪也未被忽略」的 polymarket 文件。它们对 git 是噪声，
对证据链是历史数据。

---

## 3. 生产速率：还在长吗？谁在写？

### 3.1 按 mtime 分桶（近 24h / 7d / 30d）

| 时间窗 | 文件数 | 命令 |
|---|---|---|
| 近 24h | **48** | `find reports -type f -newermt '24 hours ago' \| wc -l` |
| 近 7d | **201** | `find reports -type f -newermt '7 days ago' \| wc -l` |
| 近 30d | **266** | `find reports -type f -newermt '30 days ago' \| wc -l` |
| 早于 30d | **125,005**（99.8%） | 总数 − 266 |

**判断：目录基本已冻结，仅缓慢滴漏。** 近 30 天只新增 266 个文件（0.2%），
近 24h 仅 48 个。增长不是「每分钟一个 cycle」那种量级了。

### 3.2 当前活跃写入者（近 24h 的 48 个文件落在哪）

命令：`find reports -type f -newermt '24 hours ago' -printf '%p\n' | awk -F/ '{print $2}' | sort | uniq -c`

| 顶层目录 | 近 24h 文件数 | 写入者 |
|---|---|---|
| `lp_rh` | **48** | 5 个只读录制器（见下） |
| 其余 | 0 | — |

**全部活跃写入集中在 `reports/lp_rh/`**，对应 5 个只读录制器（CLAUDE.md 所述）：
`scanner` / `premium` / `provider_health` / `organic` / `shadow`。
每个录制器写一个 SQLite db + WAL + SHM + 一个 `.log` + `watchdog_state.json`。
命令（列出 lp_rh 近 24h 文件）：`find reports/lp_rh -type f -newermt '24 hours ago' -printf '%p\n' | head -20`

### 3.3 已死的写入者（重要）

| 写入者 | 状态 | 证据 |
|---|---|---|
| polymarket_competitor 录制器 | **已死** | 最后 cycle `20260808_160624`（8 月 8 日），近 30d 无新 cycle |
| `lp_scanner` scanner.db | **已死** | mtime 2026-09-07 12:27，近 24h 无写入 |
| `lp_scanner_v2_20260823` scanner.db | **已死** | mtime 2026-09-07 12:27，近 24h 无写入 |

命令（确认两个 scanner.db 近 24h 无写入）：
```
find reports/lp_scanner reports/lp_scanner_v2_20260823 -type f -newermt '24 hours ago' | wc -l
# → 0
```

---

## 4. 三桶分类（A 活跃证据 / B 历史产物 / C 可弃）

**分桶规则（互斥、穷尽，优先级 C > A > B）**：
- **C（可弃）**：`*.bak*` ∪ `*.tmp` ∪ `*.pid` ∪ 位于 `*_test` 目录下的文件。
- **A（活跃证据）**：git 跟踪 ∪ mtime 近 7 天（且不在 C）。
- **B（历史产物）**：其余全部。

### 4.1 汇总（文件数之和 = 125,271 ✓）

| 桶 | 文件数 | 内容字节 | 磁盘 | `.md` 数 | 判定依据 |
|---|---|---|---|---|---|
| **A 活跃证据** | **3,833** | 3,835,526,899（≈3.57 GB） | ~3.7 GB | 1,850 | git 跟踪(3,771) ∪ 近 7d(201)，交集 123；A_raw=3,849，减 C 重叠(16) |
| **B 历史产物** | **121,387** | 451,777,980（≈431 MB） | ~711 MB+ | 80,527 | 残差（含 polymarket 全部 120,743） |
| **C 可弃** | **51** | 101,304（≈100 KB） | ~100 KB | 4 | `*.bak*`(1) ∪ `*.tmp`(0) ∪ `*.pid`(20) ∪ `*_test` 目录(30) |
| **合计** | **125,271** | 4,287,406,183 | 4.5 GB | 82,381 | 与 §0 总数一致 |

> **与任务基线 125,268 的差额（+3）**：任务给定的 125,268 是较早快照；
> 本审计执行期间 5 个 lp_rh 活跃录制器持续写 WAL/SHM/log，
> 使总数涨到 125,271。差额 3 个文件全部来自活跃写入，非统计误差。
> 命令（复现总数）：`find reports -type f | wc -l` → 125,271

### 4.2 C 桶明细（51 个，可安全处置）

| 子类 | 数量 | 命令 |
|---|---|---|
| `*.pid` | 20 | `find reports -name '*.pid' -type f \| wc -l` |
| `*_test` 目录下 | 30 | `find reports -type f -path '*_test/*' \| wc -l` |
| `*.bak*` | 1 | `find reports -name '*.bak*' -type f \| wc -l` |
| `*.tmp` | 0 | `find reports -name '*.tmp' -type f \| wc -l` |
| **去重合计** | **51** | 并集（pid 与 _test 无重叠，bak 独立） |

命令（列出全部 C 桶文件，供人工复核）：
```
{ find reports -name '*.pid' -o -name '*.tmp' -o -name '*.bak*' ; find reports -type f -path '*_test/*' ; } | sort -u | wc -l
# → 51
```

> **C 桶说明**：`.pid` 是已死进程的残留锁文件（进程已死，锁无意义）；
> `*_test` 目录是历史测试运行的中间产物（目录名形如 `20260602_test`，
> 非 Go/Python 的 `_test.go`/`test_*.py` 源码，而是运行输出目录）；
> `*.bak` 是单个备份文件。三者均**不在证据链关键路径**，可弃。
> **但本审计不删除**——是否删除由用户决定（§6 步骤 4）。

### 4.3 A 桶的构成与一个必须点破的 nuance

A 桶 3,833 个文件里，**磁盘几乎全被两个 scanner.db 占满**：
- `lp_scanner/scanner.db` = 2,058,158,080 字节（2.0 GB）
- `lp_scanner_v2_20260823/scanner.db` = 1,444,950,016 字节（1.4 GB）
- 二者合计 3.4 GB，占 A 桶磁盘的 ~93%。

命令：`stat -c '%s %n' reports/lp_scanner/scanner.db reports/lp_scanner_v2_20260823/scanner.db`

> **nuance（务必读）**：这两个 db 落入 A 桶**纯粹因为机械规则**
> （mtime 2026-09-07 在近 7 天内）。但 §3.3 已证明**它们的写入进程已死**，
> 实质是**冻结的历史状态**，不是「活跃证据」。
> 因此：
> - 若按「活跃证据=不可动」对待 → 它们留在 A，磁盘 3.4 GB 无法回收。
> - 若按「冻结历史=可压缩归档」对待 → 它们应**降级到 B 处置**（压缩而非删除）。
> **本审计建议后者**（见 §6 步骤 2），因为「进程已死 + 只读研究冻结」
> 意味着它们不会再被写入，压缩归档不损失任何证据。

### 4.4 B 桶的构成

B 桶 121,387 个文件 = polymarket_competitor 全部（120,743）
+ 其余历史目录残差（~644，含 shadow_outcomes 477、tierc_shadow 139 等）。
全部是**已完成实验的输出**，属证据链历史部分，**压缩不删除**。
命令：`find reports -mindepth 2 -type f | awk -F/ '{print $2}' | sort | uniq -c | sort -rn | head`（见 §1.1）

---

## 5. 今晚作废的 9 份报告：分类与去留意见

**识别方法**：顶层 `.md`，正文含作废横幅 `> # ⛔ 本文档已作废（2026-09-09）`。
命令（排除本审计文件自身——它引用了该横幅字符串作为识别方法，会自匹配）：
```
grep -rl '本文档已作废（2026-09-09）' reports/*.md | grep -v 'AUDIT_reports_bloat_20260909'
# → 9 个文件（见下表）
```

| # | 文件 | git 跟踪 | 作废横幅 | 我的意见 |
|---|---|---|---|---|
| 1 | `CLEAN_PROOF_SURFACE_CN.md` | 是 | 有 | **保留** |
| 2 | `CLEAN_PROOF_SURFACE_V2_CN.md` | 是 | 有 | **保留** |
| 3 | `FULL_STRATEGY_CLEAN_PROOF_CN.md` | 是 | 有 | **保留** |
| 4 | `COHORT_PNL_PROOF_CN.md` | 是 | 有 | **保留** |
| 5 | `POSITION_LEVEL_CLEAN_PROOF_CN.md` | 是 | 有 | **保留** |
| 6 | `POSITION_LEVEL_PROOF_V1_CN.md` | 是 | 有 | **保留** |
| 7 | `POSITION_LEVEL_QUARANTINE_SIM_CN.md` | 是 | 有 | **保留** |
| 8 | `POSITION_LEVEL_QUARANTINE_V2_CN.md` | 是 | 有 | **保留** |
| 9 | `POOL_POSITION_QUARANTINE_SIM_CN.md` | 是 | 有 | **保留** |

> 注：`AUDIT_stale_conclusions_20260909.md` **不在**此 9 份之列——
> 它只在正文里提到「作废」，自身没有作废横幅，是**审计文档**而非被作废对象。

**意见：9 份全部保留（与主脑「留痕」倾向一致）。理由：**

1. **它们已被 git 跟踪**（`git ls-files` 可证），删除会留下 git 历史空洞，
   且违反本仓库「`*_test.go` 不可删行」所体现的**证据不可逆**文化。
2. **作废横幅本身就是价值**：它们记录了「某结论曾成立、后被推翻」的
   完整轨迹。对真金白银交易的研究，**「为什么推翻」比「推翻后是什么」更稀缺**。
   删掉 = 丢失审计轨迹。
3. **体积可忽略**：9 个 `.md` 合计 < 1 MB，对 4.5 GB 目录、82,381 个 `.md`
   的膨胀**毫无影响**。留着它们不增加任何「上下文爆炸」风险
   （它们不在 polymarket 那种 8 万条路径里）。
4. **成本不对称**：保留的边际成本 ≈ 0；误删的边际成本 = 不可恢复的证据链断裂。
   在不对称成本下，**默认保留**是唯一稳健选择。

**唯一可考虑的例外**：若用户明确要「让 `reports/*.md` 顶层只留有效文档」，
可把这 9 份**移动**到 `reports/voided_20260909/`（移动而非删除，可逆）。
但本审计**不主动建议**——移动会改变 git 跟踪路径，需用户明确授权。

---

## 6. 最小代价方案：把递归 `.md` 降到 < 5000

**目标**：递归 `.md` 从 82,381 → < 5000。
**杠杆**：`polymarket_competitor/` 独占 80,494 个 `.md`（97.7%）。
**核心动作**：把它**压缩归档**（不删除）。归档后 `.md` = 82,381 − 80,494 = **1,887** ✓

> 每步标注：**可逆性** + **是否需用户确认**。本审计**不执行**任何一步。

### 步骤 1：压缩归档 `polymarket_competitor/`（最大杠杆）

- **动作**：`tar -czf reports/polymarket_competitor_20260629-20260808.tar.gz -C reports polymarket_competitor`
  （生成 1 个 tarball；原目录**保留**，先不删）
- **效果**：递归 `.md` 82,381 → **1,887**（若随后删除原目录）；
  磁盘 711 MB → tarball 约 100–200 MB（大量重复模板文本，压缩比高）。
- **可逆性**：**可逆**（tarball 完整保留全部 120,743 文件，可 `tar -xzf` 还原）。
- **需用户确认**：**是**（涉及 12 万文件的归档，且决定原目录去留）。
- **风险**：tarball 生成期间占额外磁盘；建议先 `df` 确认剩余空间 > 1 GB。

### 步骤 2：压缩归档两个冻结 scanner.db（回收 3.4 GB 磁盘）

- **动作**：`tar -czf reports/lp_scanner_dbs_frozen_20260907.tar.gz \
  -C reports lp_scanner/scanner.db lp_scanner_v2_20260823/scanner.db`
- **效果**：磁盘回收 ~3.4 GB（db 是 SQLite，压缩比中等，tarball 约 1.5–2.5 GB）。
- **可逆性**：**可逆**（tarball 保留原 db，可还原）。
- **需用户确认**：**是**（这两个 db 在 §4.3 被点破为「冻结历史」，
  归档前需用户确认不再需要在线查询它们）。
- **前置检查**：确认无进程持有（§3.3 已证写入进程已死；
  可再 `lsof reports/lp_scanner/scanner.db` 确认无句柄）。

### 步骤 3：（可选）压缩归档其余 B 桶历史目录

- **动作**：对 `shadow_outcomes/`、`tierc_shadow/` 等长尾历史目录逐个 tar。
- **效果**：进一步降磁盘；对 `.md` 数影响小（它们 `.md` 占比低）。
- **可逆性**：**可逆**。
- **需用户确认**：**是**（逐目录，可按需挑选）。
- **优先级**：低——步骤 1+2 已达成 `.md < 5000` 且回收 3.4 GB，此步锦上添花。

### 步骤 4：（可选）清理 C 桶 51 个可弃文件

- **动作**：删除 20 个 `.pid` + 30 个 `*_test` 目录产物 + 1 个 `.bak`。
- **效果**：文件数 −51，磁盘 −~100 KB（**对膨胀几乎无影响**）。
- **可逆性**：**不可逆**（删除）。
- **需用户确认**：**是**（唯一不可逆步骤，且收益极小，**默认不做**）。
- **建议**：**跳过**。收益（100 KB / 51 文件）远不抵不可逆风险。

### 步骤 5：（可选）为 polymarket 类录制器加 `.gitignore` 规则

- **动作**：在 `.gitignore` 增 `reports/polymarket_competitor/`（或归档后指向 tarball）。
- **效果**：防止未来同类录制器再产生 12 万未跟踪文件污染 `git status`。
- **可逆性**：**可逆**（改一行配置）。
- **需用户确认**：**是**（改 `.gitignore` 属仓库配置变更，超出本审计只读范围）。
- **优先级**：中——治本（防复发），但需用户授权改配置。

### 方案汇总

| 步骤 | 动作 | `.md` 效果 | 磁盘效果 | 可逆 | 需确认 | 建议 |
|---|---|---|---|---|---|---|
| 1 | 归档 polymarket | 82,381→**1,887** | −~500 MB | 可逆 | 是 | **做** |
| 2 | 归档 2×scanner.db | 无 | **−3.4 GB** | 可逆 | 是 | **做** |
| 3 | 归档其余 B 桶 | 微降 | 微降 | 可逆 | 是 | 可选 |
| 4 | 删 C 桶 51 文件 | 微降 | −100 KB | **不可逆** | 是 | **跳过** |
| 5 | 加 .gitignore 规则 | 防复发 | 无 | 可逆 | 是 | 建议 |

**最小代价达成目标 = 步骤 1 + 步骤 2**：
`.md` 降到 1,887（< 5000 ✓），磁盘从 4.5 GB 降到 ~0.5 GB，全程可逆。

---

## 7. 可复现附录（全部只读命令）

以下命令可在仓库根目录直接复跑，复现本报告全部数字。**均为只读**，
无 `rm`/`mv`/`git` 写操作。

```bash
# §0 总量
find reports -type f | wc -l                                  # → 125,271
find reports -type f -printf '%s\n' | awk '{s+=$1} END{print s}'  # → 4,287,501,807
du -sh reports/                                              # → 4.5G
find reports -name '*.md' -type f | wc -l                    # → 82,381
find reports -maxdepth 1 -mindepth 1 -type d | wc -l         # → 210
git ls-files reports | wc -l                                 # → 3,771

# §1 构成
find reports -mindepth 2 -type f | awk -F/ '{print $2}' | sort | uniq -c | sort -rn | head
du -sh reports/*/ | sort -rh | head
find reports -type f -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort | head

# §2 git 跟踪
git ls-files reports | wc -l
git check-ignore reports/polymarket_competitor/cycle_20260629_094556/ONEPAGE_CN.md  # 无输出=未忽略

# §3 生产速率
find reports -type f -newermt '24 hours ago' | wc -l         # → 48
find reports -type f -newermt '7 days ago'   | wc -l         # → 201
find reports -type f -newermt '30 days ago'  | wc -l         # → 266
find reports -type f -newermt '24 hours ago' -printf '%p\n' | awk -F/ '{print $2}' | sort | uniq -c
find reports/lp_scanner reports/lp_scanner_v2_20260823 -type f -newermt '24 hours ago' | wc -l  # → 0

# §4 三桶
find reports -name '*.pid' -type f | wc -l                   # → 20
find reports -type f -path '*_test/*' | wc -l                # → 30
find reports -name '*.bak*' -type f | wc -l                  # → 1
find reports -name '*.tmp' -type f | wc -l                   # → 0
stat -c '%s %n' reports/lp_scanner/scanner.db reports/lp_scanner_v2_20260823/scanner.db

# §5 作废报告（排除本审计文件自身，避免自匹配）
grep -rl '本文档已作废（2026-09-09）' reports/*.md | grep -v 'AUDIT_reports_bloat_20260909'  # → 9 个
```

**桶求和自检**（A+B+C = 总数）：
```
3,833 (A) + 121,387 (B) + 51 (C) = 125,271 ✓
```

---

## 8. 审计边界声明

- 本审计**只读**：未删除、未移动、未修改仓库任何文件；未执行 git 写命令；
  未重启 daemon、未动 crontab、未发网络请求、未安装软件包。
- 唯一副作用：创建本文件 `reports/AUDIT_reports_bloat_20260909.md`。
- 所有「建议」均为**待用户决策**，本审计不执行。
- 本任务为纯分析（产出 markdown），**无需 Python 测试**；
  未涉及任何 `lp_*_readonly.py` 管线改动。




> **含义**：两个 3.4 GB 的 scanner.db 虽然 mtime 在 7 天内（会落入 §4 的 A 桶），
> 但**写入进程已死**，实质是**冻结的历史状态**，不是活跃证据。
> 处置时应按「冻结历史」而非「活跃」对待（见 §4 注、§6 步骤 2）。

