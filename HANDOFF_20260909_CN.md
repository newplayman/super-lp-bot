# HANDOFF 2026-09-09 05:xx UTC — 通宵段结束，新会话从此接上

## 0. 新会话开场三件事（对不上先报再动手）

```bash
cd /opt/lpbot/lp-bot-v3-origin-check
git log --oneline -3                              # 应见 3cc84f9 附近
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider | tail -1   # 4085 passed / 14 skipped
./scripts/lp_rh_status.sh                         # Stage A 进度
for n in collector premium_recorder provider_health_recorder organic_recorder shadow_daemon; do
  echo "$n: $(cat reports/lp_rh/$n.pid)"; done    # 五个都应在跑
crontab -l | grep -c lp_rh                        # 应为 5
```

## 1. 当前状态

| 项 | 值 |
|---|---|
| 今日提交 | 57 个 |
| RH 模块 | 42 个 |
| 全量测试 | **4085 passed / 14 skipped** |
| Stage A | 24.5 h / 72 h，**覆盖率 96.18%（门槛 99%）** |
| 活进程 | 5/5，cron 看门狗 5 条，全部经故障注入验证 |
| 签名 / 广播 / 动资金 | **0 / 0 / 0** |

五条数据序列：

```
Stage A 采集    5667 行 / 24.5h     溢价序列   1830 行 / 15.2h
提供方可用性      49 行 / 11.5h     有机成交量   29 行 / 10.1h
Shadow 闭环      25 行 /  5.5h
```

## 2. 审计已完成：PRD 60 条全部走完

`reports/rh_pivot/20260907T124500Z/AUDIT_VERDICT_CN.md`
证据在同目录三个 `AUDIT_EVIDENCE_T*.json`（file:line + 真跑过的 pytest 输出，0 判定词）。

**PASS 46 · 需关注 5 · FAIL 0（原 4 个已全部处置）· 不适用 2**

| 原 FAIL | 处置 |
|---|---|
| T34 gas 无校验 | 已修 + 实盘验证 |
| T29 native 储备闸缺失 | 已修 |
| T31 空区间未分类 | 已修 |
| T26 MEME 跨池聚合 | 已修 |
| T11 重组回滚 | 能力已实现，**接线在跑**（RH-02k）→ 暂判需关注 |

T53/T54 判「不适用」：属执行层，本项目未获签名授权、至今未触碰。

## 3. 本夜最重要的发现：四个没有出处的硬编码常量

**共同点：都不抛异常、都通过全部测试。**

| 常量 | 损害 | 状态 |
|---|---|---|
| `gas_usd_estimate = 0.02` | 真值 0.4614，低估 23 倍，**把资金政策结论算反** | 已修 + sanity 闸 |
| `eth_getBlock`（方法名不存在） | **提供方数量自造成 0** | 已修 + 静态守卫 |
| `timeout = 30` | 同一请求 30s 失败 / 90s 拿 22,281 条，**丢 70,400 块** | 已修 + 正在追回 |
| `reference_age_secs = 0` | **freshness 闸形同虚设** | 已修 + 自证其罪测试 |

每个修复都配了防复发测试。另有两个「看着有数据其实没有」的列：
`session` 硬编码 `"UNKNOWN"`（4361 行）、`reference_mid` 装的是 DEX 池价不是参考价。

## 4. 等你决定的事

### 4.1 三个政策问题（`DECISIONS_PENDING_CN.md`）

1. **无链上 oracle 时，REST `generatedAt` 能否作新鲜度依据**
   ——这是 Shadow 闭环唯一剩下的阻塞项。
2. **资金政策**：结论已**翻转**。实测 gas 后最小可行仓位 **$57**，
   而 100U 本金给 CORE 的上限只有 $42.5。**需 $135–$161 本金**
   （取均值还是最差窗口）。三种有机估计下 $42.5 与 $50 全部 FAIL。
3. **`MARGINAL` 置信度是否该影响 LVR haircut**
   ——实测 GLD 盘后以 ratio 1.74 拿到 `haircut = 0`（无损耗），
   是建立在勉强够格信号上的乐观读数。

### 4.2 五项已建成但刻意未接线的闸门

gas sanity、native 储备、空区间分类、regime confidence、MEME 聚合。
**接线等于改变「什么情况下允许开仓」，那是你的资金政策决定。**
（重组回滚是例外——它只作废数据、永不放进新东西，所以我接了。）

### 4.3 一个预算问题

注册表里 chainId 4663 的四个端点**已全部试完**，只有 ordofi 一家全能力可用。
要解除 LIVE 的 `SINGLE_PROVIDER` 阻塞，只能找注册表之外的端点
**或接受付费归档节点**——后者需你的预算授权。

## 5. Stage A 的毕业时间表被推翻两次

1. **覆盖率**：96.18%，跑到 72h 只有 98.78%，**需约 90h**。
   缺口是每轮多花 1 秒的系统性漂移（不是断档），已自愈（现稳定 15.000s），
   历史亏空不可追回。PRD §21.1 堵死三条取巧路（不能删坏小时／不能滚动窗口／不能重启时钟）。
2. **两个与时间无关的阻塞**：
   - `reference_age_secs` 写死 0 → **已修**，新样本 age=2
   - **五张证据表全空** → 写入器已落地（`rh_pool_registry` 已有 1 行），
     `rh_assets` 与 `rh_contract_attestations` 仍 0 行，**RH-02j 在填**

**在 RH-02j 落地前，不要按「第 90 小时毕业」做计划。**

## 6. 在跑的两个包

| 包 | 内容 | 已跑 |
|---|---|---|
| RH-02j | 证据采集器，填最后两张空表 | 32 分钟 |
| RH-02k | 重组解析——先定孤块再回滚 | 6 分钟 |

两者都有明确验收标准写在各自 spec 里（`docs/specs/20260909_*.md`）。

## 7. 派活纪律（三次确认，已入记忆）

**qwen worker 可靠产出的上限是「一包一个实质文件」。** 三文件包失败三次，
共浪费约 5 小时；拆包后 RH-01c / RH-05i-b / RH-04g-b 全部一次通过。
另：**接口先用 `ast` 抽出来贴进 spec**，RH-04f 三轮里两轮预算全花在 grep 签名上。

## 8. 我自己犯的错（已更正，留档）

1. **提供方数量报了四次**（3→0→0→1），**每次都是我的仪器错**，不是链上变化。
2. 两次把测试数字写进 commit message 才去跑，已 amend。
3. 冤枉过 worker 一次：报 `pool_meta_hash_of(None)` 崩溃是 bug 并动手改了，
   事实是 `required=True` 该路径不可达，worker 是对的，已撤回。
4. spec 写错一条断言（要求「±2000 的 in-range 严格大于 ±100」，行情平静时不可能成立）。
5. 故障注入脚本用了 `PPID` 这个 bash 只读变量，杀掉 organic 录制器后中断未重启
   ——顺着这个事故反而查出**两个看门狗本来就是坏的**（重启命令参数不全、进程秒退、
   却照样记 `RESTARTED`）。五个已全部加「重启后核实存活」并逐个验证。
