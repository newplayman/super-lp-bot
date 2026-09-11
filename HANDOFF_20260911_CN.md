# 交接：RH Shadow 夜间工作（2026-09-10 夜 ~ 09-11 10:05Z）

## 0. 开场对账（下一任先跑这三条）

```bash
cd /opt/lpbot/lp-bot-v3-origin-check
git log --oneline -1                    # 应为本文档的 commit
git status --short | grep -v '^??'      # 应为空
ps -eo pid,etime,cmd | grep -E 'lp_rh_collector_v1|lp_rh_shadow_daemon' | grep -v grep
python3 -m pytest tests/ -q             # 4825 passed, 14 skipped
```

**与下面不符先报再动手。**

## 1. 一句话状态

**Stage A 只剩一个 blocker，且是纯等时间的。**

```
Stage A  hours=25.91/72  coverage=0.9981  blockers: HOURS_COVERED_INSUFFICIENT
         synthetic: OK   key_fields: 全部 passed
Stage B  days=3/14       blockers: DAYS_COVERED_INSUFFICIENT,
                                   WEEKENDS_COVERED_INSUFFICIENT
```

本轮 30 个 commit（`4d1d5e3` → HEAD），全量 **4825 passed / 0 failed**。

## 2. 运行中的生产进程（**下一任必须知道**）

| 进程 | PID | 启动参数的关键部分 |
|---|---|---|
| 采集器 | 2271374 | `RH_RPC_PRIMARY=https://robinhood-rpc.publicnode.com`<br>`RH_RPC_SECONDARY=https://rpc.ordofi.network` |
| shadow daemon | 1789399 | `--ledger-db .../scanner.db`（持久账本） |

**两者都是环境变量/参数变更，无代码改动，去掉重启即回退。**

重启命令（pid 会变，用前先 `cat reports/lp_rh/collector.pid`）：

```bash
# 采集器
kill $(cat reports/lp_rh/collector.pid)
# 等进程真退出且 pid 文件清空再启动（见 §5 踩坑 1）
RH_RPC_PRIMARY=https://robinhood-rpc.publicnode.com \
RH_RPC_SECONDARY=https://rpc.ordofi.network \
setsid /root/lp-bot/.venv/bin/python \
  /opt/lpbot/lp-bot-v3-origin-check/scripts/lp_rh_collector_v1_readonly.py \
  --db /opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/scanner.db \
  --interval-secs 15 \
  --pid-file /opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/collector.pid \
  >> /opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/collector.log 2>&1 < /dev/null &

# shadow daemon
kill $(cat reports/lp_rh/shadow_daemon.pid)
setsid /root/lp-bot/.venv/bin/python \
  /opt/lpbot/lp-bot-v3-origin-check/scripts/lp_rh_shadow_daemon_v1_readonly.py \
  --db /opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/shadow.db \
  --ledger-db /opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/scanner.db \
  --pool 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca \
  --pool-meta-json /opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/pool_meta.json \
  --samples 200 --position-usd 1000 --capital-usd 10000 \
  --horizon-hours 720 --period-secs 900 \
  --pid-file /opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/shadow_daemon.pid \
  >> /opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/shadow_daemon.log 2>&1 < /dev/null &
```

**监护需要下一任重新启动**（本会话的已关闭）：

```bash
bash /opt/lpbot/lp-bot-v3-origin-check/scripts/lp_rh_session_monitor.sh
```

## 3. ★等用户决定的三件事★

| # | 事项 | 不做的后果 | 可逆 |
|---|---|---|---|
| 1 | 跑 `scripts/lp_rh_reservation_cleanup_v1.py --apply` | **Shadow 再也不会开仓**，`q_max` 恒为负 | 否（写库，但用 release 留痕） |
| 2 | 判定窗口豁免机制 | 每次改采集器代码就重置 72 小时计时 | — |
| 3 | 重派 RH-02cn（organic 折减） | fee 持续高估 **11.42%** | 是 |

### 第 1 件最紧急

`bc780ec` 让 bucket active cap 真正生效后暴露一个死锁：

```
23 条 PENDING reservation = 23000 USD，CORE cap = 4250
daemon 每轮日志: resv:0, reservations_synced:23   <- 一条都没批准
q_max = -18750（绑定约束 bucket_active_room）
```

这些是 cap 失效期间累积的脏数据，对应 episode 早已结束。闭环在于：
历史占用堵死 cap → 无新 reservation → 无 episode 开仓 → `release()`
（只释放本轮自己那条）无从触发 → 历史占用永远留着。

工具已备好并验证（`8fa95ab`），dry-run 输出：

```
Total PENDING            23 (23000 USD)
Orphans (episode ended)  22 (22000 USD)
Projected reserved_total 1000 | room 3250     <- 死锁解除
```

它用 `release()` 逐条释放而非 DELETE —— 这 22 条是「cap 曾经失效」的
实物证据，该留痕。

## 4. 本轮做完的事（30 个 commit）

### 修的缺陷

| commit | 缺陷 | 关键数字 |
|---|---|---|
| `bc780ec` | **bucket cap 在 rollback 路径上完全失效** | 7000 USD 占用 vs 4250 cap，仍在放行 |
| `d957453` | 账本 rollback 漏搬三张表 | economic 卡在 181 不再增长 |
| `a2f2625` | `try_reserve` 在脏连接上必崩 | 开盘首个 granted step 会炸整轮 |
| `8e54926` | invariant 空表当「零违反」 | 六张空表，检查在对空气打勾 |
| `4d1d5e3` | Stage B 两个证据硬编码为 0 | 跑满 14 天会直接放行 |
| `bcfc3c6` | attestation 只数行数不看状态/过期 | `FAILED` 也算通过 |
| `ec234e1` | `max_impact_bps` 缺失默认 50 | 风控闸变橡皮图章 |
| `7ffbb24` | **coverage 累计口径永远到不了 0.99** | 收敛到 0.9818，改判定窗口后 0.998 |
| `48e08fb` | 监护与闸门口径差 35 小时 | 报 47h，闸门看的是 12h |

### 接线的五个「写好了但零引用」

```
T29 native gas reserve   104077e   退出储备 0.3270 USD（x3 冗余）
T31 size interval        ad8d27b   q_min/q_max 首次写进库
T34 gas estimator        f04bef5   静态 0.4005 → 实测中位数 0.2611（高估 50%）
T37 in-range fraction    d458c64   当前 1.0000（价格未越界）
organic 折减             未完成    当前高估 11.42% ← RH-02cn 需重派
```

### 新增能力

- `scripts/lp_rh_fault_injection_v1_readonly.py` — 六场景故障注入，**每个都带对照组**
- `scripts/lp_rh_graduation_evidence_v1.py` — RH-08 四份交付物，可重复生成
- `scripts/lp_rh_reorg_detector_v1_readonly.py` — reorg 离线扫描（当前 0 分歧）
- `scripts/lp_rh_reservation_cleanup_v1.py` — 孤儿清理（dry-run 默认）
- 采集器主备切换（`ee98d3d` + 部署），切换后 **1170 次 RPC 零错误**

## 5. 踩过的坑（**这些圈子不要再兜**）

### 1. 停带 pid 文件互斥的守护进程，必须等 pid 文件清空

第一次切 RPC 端点，`kill` 后只等 4 秒就启动新进程。旧进程正在优雅退出，
pid 文件还在，新进程判定 `collector already running` 直接 Exit 2；
随后旧进程才退出并清空 pid 文件 —— **结果两个都没了，断采 37 秒**。

正确做法：轮询等进程真退出 **且** pid 文件真清空，再用 `setsid` 启动。

### 2. 「构造的输入进不去目标分支」— 本轮出现 **九次**

每一次都是：测试断言看起来很严格，实际测的是一条到不了的路径。

| 表现 | 真因 |
|---|---|
| journal 测试断言 3 条，实际 2 条 | fixture 传 `fee_growth=(a,b)`，runner 读 `fee_growth_global_0/1` |
| in-range 测试「出区间」步全部在区间内 | fixture 传 `price=`，runner 读 `reference_mid` |
| reorg 测试 6/7 对空表断言 | `insert_row` 不 commit，`close()` 静默回滚 |
| 故障注入场景 1/2 对照组也失败 | 场景 2 传 `now=None`；场景 1 漏了 `reference_mid` |
| fee 分录的 fail-close 分支没触发 | meta 删了 `dec1` 但 sample 还留着，`_evidence_for` 会回退 |

**教训：写完测试要反向确认——把被测代码改坏，测试是否变红。**
本轮对 T32、`max_impact_bps`、元测试都做了这个反向验证。

### 3. 把「当前数据状态」写进断言 — 出现 **四次**

- `approx(0.9987)` 钉住 fee_growth 非空率 → 采集器继续跑就漂出去
- `approx(0.9678)` 钉住 coverage → 改判定窗口后失效
- `assert ms == 350` 钉住延迟 → 二进制浮点下是 349
- `gas_usd == 0.40` 钉住 fixture 里的值 → 实际是 0.01

**断言行为，不要断言数据库今天恰好装着的数字。**

### 4. 聚合掩盖分组结构

我把 `rh_position_marks` 778 行 / 241 个不同 `mark_time` 当成缺陷报出去，
**是误判**。按 episode 拆开看每个 episode 内部零重复——`position_id` 含
episode，跨 episode 同一时刻各一行是主键允许且语义正确的。
更正记录在 `AUDIT_shadow_ledger_writer_gap_20260910.md` 末尾。

### 5. gemini-worker 不适合联网调研

派了三路（vps104 / research13 / research66）找 RPC 端点，**全部无产出**：
vps104 用 ripgrep 在 `/tmp` 里翻本地文件，research 两路 `exit_code=0`
但 stdout 为空、报告取不回来。**这类工作主脑自己 curl 更快**，
本轮的端点数据全是这么来的，约 10 分钟。

### 6. 已排除的方向

- **reorg**：扫描 9573 个有效样本、6880 个不同区块哈希，**0 组分歧**。
  不是「没查」，是「查过没有」。检测器已就位，将来有分歧会抓到。
- **in-range 高估**：实测 `fraction = 1.0000`，**当前高估为 0**。
  机制已接（`d458c64`），价格越界时会自动折减。
- **premium 时间序列**：RH-05 报告说「仅有单点快照」，实际
  `premium.db` 已有 **7632 行**，六个标的各 1272 条。缺口自己填上了。

## 6. 下一任的建议顺序

1. **先问用户 §3 的三件事**，第 1 件不解决 Shadow 不会开仓
2. 重派 RH-02cn（spec 已写好：`docs/specs/20260911_RH-02cn_organic_fee_discount.md`）
3. `HOURS_COVERED_INSUFFICIENT` 还差 46 小时，期间可做：
   - `q_max` 缺的三项约束（`global_active_room` / `approved_position_cap` /
     `asset_exposure_room`）—— 补齐后才能把 `q_max` 接进终闸
   - `rh_reconciliation_runs` 仍为 0 行（PRD §21.2 的对账证据）
   - RH-07（T51-T54 受限执行与恢复）—— 按授权延期，未开始

## 7. 一个已知的设计循环

合成测试证据绑定 HEAD，**而提交证据文件本身会改变 HEAD**，
于是刚生成的证据在下一个 commit 后就变成 `STALE_CODE_VERSION`。

本文档提交后会再次发生。解法之一是让 `code_version` 只跟踪
`scripts/` 与 `tests/` 的最后一次改动，而不是整个仓库的 HEAD。
**未实施，留给下一任判断。**

重新生成的命令：

```bash
python3 scripts/lp_rh_synthetic_evidence_v1.py \
  --out reports/lp_rh/synthetic_tests_evidence.json
```

## 8. 真钱安全（未变）

**从来没有任何文档批准过真钱。** `GRADUATION_VERDICT.json` 的
`tiny_live_authorized` 硬编码为 `false`，且三闸全过时仍会在
`verdict_reasons` 里写明「代码判定通过不等于所有者批准」。

`LIVE_GATE` 当前两条阻断：`SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE`、
`CAPITAL_POLICY_NOT_APPROVED`。注意第一条——虽然采集器已接主备两个端点，
但 `usable_provider_count` 的判定口径是另一回事，**没有因为部署主备而自动满足**。
