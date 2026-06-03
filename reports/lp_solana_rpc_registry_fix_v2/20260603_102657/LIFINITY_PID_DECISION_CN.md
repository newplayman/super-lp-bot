# Lifinity PID Decision — Stage G

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2`
- run_id: `20260603_102657`

## 0. 关键结果

```text
lifinity_status          = deferred
reason                   = no_oficial_source_available
does_not_block_p0_p1     = true
priority                 = P2 (not in Meteora DLMM P0 critical path; not in Orca/DAMM v2 P1 critical path)
```

## 1. V1 finding 复述

V1 (20260603_093136) 报告:
- `docs.lifinity.io` 404
- 无公开 GitHub source
- 标记为 `unknown`, per spec 不阻塞 P0/P1

## 2. V2 re-probe 详情

### 2.1 docs.lifinity.io (V2 实测)

| URL | HTTP | 字节 |
|---|---|---|
| `https://docs.lifinity.io` | 200 | 305741 |
| `https://docs.lifinity.io/` | 200 | 305741 |
| `https://docs.lifinity.io/introduction` | 404 | 151051 |
| `https://docs.lifinity.io/developer-guide` | 404 | 151031 |
| `https://docs.lifinity.io/developers` | 404 | 151047 |
| `https://docs.lifinity.io/protocol` | 404 | 151043 |
| `https://docs.lifinity.io/addresses` | 404 | 151045 |
| `https://docs.lifinity.io/deployment` | 404 | 151047 |
| `https://docs.lifinity.io/mainnet` | 404 | 151041 |
| `https://docs.lifinity.io/program` | 404 | 151041 |
| `https://docs.lifinity.io/smart-contract` | 404 | 151029 |
| `https://lifinity.io` | 200 | 18285 |
| `https://lifinity.io/docs` | 404 | 20521 |

**更正 V1 finding**: `docs.lifinity.io` 实际**不**返 404 (V1 可能是测量瞬时失败, 或 cache stale). V2 找到它返 200, 但:
- 这是个 SPA (Next.js, JS 渲染), HTML 中**不**含可机读内容
- 所有 9 个 common subpath (introduction, developer-guide, addresses, ...) 全部 404
- 没有任何 subpage 公开 program id
- 全文 (305KB) 搜索 base58 (43-44 chars) 0 匹配

### 2.2 GitHub source 探测

```
REPO 'lifinity/dex'             HTTP 404
REPO 'lifinity/v1'              HTTP 404
REPO 'lifinity/lifinity'        HTTP 404
REPO 'lifinity/amm'             HTTP 404
REPO 'lifinity/ammv2'           HTTP 404
REPO 'lifinity/contracts'       HTTP 404
REPO 'Lifinity-finance/contracts' HTTP 404
REPO 'lifinity-dex/contracts'   HTTP 404
REPO 'lifinity-protocol/lifinity-dex' HTTP 404
```

`lifinity` GitHub org **存在**, 但所有 repos 都是:
- `lifinity/coding_challenges` (John Crickett 编码挑战)
- `lifinity/launch_school` (LS 练习)
- `lifinity/pygame_asteroids` (pygame 练习)
- `lifinity/sst_notes` (SST 笔记 app)
- `lifinity/static_site_gen` (静态站点生成器练习)

→ **无任何 DEX / AMM / Solana 协议代码**. Lifinity 协议**不**在 GitHub 上以开源形式存在.

### 2.3 GitHub code search 其它 lifinity repos

```
ChangeYourself0613/Solana-Arbitrage-Bot (第三方套利)
miya9022/lifinity-cpi-swap (非官方, 无法认证)
Baldeep1102/lifinity (无 description, 第三方)
olety/Lifinity-Flares-Sales-Bot (twitter bot, 第三方)
giewan/LifinityDex (4-字 desc "data routing / ApexCore" - 看起来是 spam 命名, 不是真 Lifinity)
```

→ 全部是**第三方** (个人) repos, 不可作 Level A source.

## 3. 决策

per spec "如果 docs 404 或没有官方 source: lifinity_status = deferred, reason = official_source_unavailable, do not block P0/P1, 不得用非官方来源硬填 pid":

- **lifinity_status = deferred** ✓
- **reason = official_source_unavailable** ✓
- **does_not_block_p0_p1 = true** ✓
- **Lifinity P2** → 不在 critical path
- **Lifinity 真实情况**: 协议**可能**存在 (有 lifinity.io 域名和 docs 网站), 但**不**以开源 / 机器可读方式发布 program id. 在不违反 "no memory hardcode" 的前提下, 没办法获取 verified pid.

## 4. 与 V1 一致性

- V1: unknown (1/6 unknown)
- V2: deferred (1/6 deferred)
- 数量一致 (1/6 not-verified); 标签从 "unknown" 改 "deferred" 以反映 "确认无 source, 长期延后" 的实情.
- Lifinity **不**影响 Meteora DLMM (P0), **不**影响 Meteora DAMM v2 / Orca (P1), **不**影响 Raydium CLMM (P2 verified).

## 5. Follow-up (operator input required)

- 候选 1: operator 从 lifinity.io 人工找 program id (浏览器渲染后能看到)
- 候选 2: operator 查 Solscan / Solana Explorer 找 deployed program
- 候选 3: 接受 deferred; Lifinity 永远不进入 connector (本项目只 P0/P1/P2 选 verified)
- 候选 4: spec 允许在 1/6 持续 deferred 情况下, 协议层做"不参与"决定 (从 P2 列表移除)

## 6. 不在本阶段做

- ❌ 不从第三方 GitHub fork 找 pid
- ❌ 不从模型记忆硬编码
- ❌ 不 webfetch blog / Twitter / 论坛
- ❌ 不跑 GPA
- ❌ 不接 wallet / 不读 keypair

## 7. 安全断言

```text
this_stage_only_did_source_audit    = true
this_stage_did_not_hard_code_pid   = true
this_stage_did_not_run_gpa         = true
solana_wallet_or_keypair_touched   = false
can_run_probe_now                  = false
v2_line_count_unchanged            = true (992)
```

## 8. 下一阶段

进入 Stage H: Registry v3 update — 合并 V1 + V2 新信息.
