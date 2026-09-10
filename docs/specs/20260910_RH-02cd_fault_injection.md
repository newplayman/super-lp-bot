# RH-02cd — 故障注入演练：证明闸门在故障时真的会拦

## 背景

PRD §19 的 RH-08 要求 `FAULT_INJECTION_REPORT.md`，四个交付物目前**全部不存在**：

```
READINESS_DASHBOARD.md      不存在
FULL_TEST_RAW.log           不存在
FAULT_INJECTION_REPORT.md   不存在      <- 本包
GRADUATION_VERDICT.json     不存在
```

本仓库已确认 **27 例「静默假绿」**——不抛异常、数字照出、量级正常、结论全废。
单元测试证明「函数在构造输入下的行为」，故障注入要证明的是另一件事：
**故障真的发生时，闸门链条端到端地拦住了，而不是悄悄给出一个好看的结论。**

而且今晚**真的发生了一次**：上游 RPC 超时，生产库里留下了实证：

```
rh_rpc_health 里 TimeoutError      100 条
health_flags 含 DEGRADED 的样本    186 条
fee_growth_global_0 为 NULL       8095 条
```

## 唯一任务

新建 `scripts/lp_rh_fault_injection_v1_readonly.py`，注入下列故障并**断言闸门反应**，
产出 `reports/lp_rh/FAULT_INJECTION_REPORT.md`。

### 六个场景（每个都要：注入 → 跑闸门 → 断言拦住了 → 记录理由）

| # | 注入 | 期望闸门反应 |
|---|---|---|
| 1 | `fee_growth_global_0/1` 大量置 NULL（模拟 RPC 读不到） | `audit_key_field_health` 的该列 `passed is False`，Stage A 出现 `STAGE_A_KEY_FIELDS_INCOMPLETE` |
| 2 | 样本 `health_flags_json = '["CHAIN_DEGRADED"]'` | `compute_conjuncts` 的 `market_and_chain_risk_pass is False`，该步不 eligible |
| 3 | `pool_meta` 的 quote 证据过期（`observed_at` 超出 `ttl_secs`） | `validate_quote_evidence` 返回 `(None, <理由>)`，该 episode 的 NAV 全为 None |
| 4 | `rh_contract_attestations` 最新一行状态改成 `FAILED` | `audit_pool_attestation` 的 `passed is False`，Stage A 出现 `STAGE_A_POOL_NOT_ATTESTED` |
| 5 | 合成测试证据的 `code_version` 与 HEAD 不符 | `audit_synthetic_tests` 的 `passed is False`，reason `SYNTHETIC_EVIDENCE_STALE_CODE_VERSION`，Stage A 出现 `STAGE_A_SYNTHETIC_TESTS_FAILED` |
| 6 | 六张账本表全空 | `audit_invariant_violations` 的 `violations_count is None`（**不是 0**），Stage A 出现 `STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE` |

**每个场景还要跑一次「对照组」**：不注入故障时，同一个断言的对象**不应**出现该 blocker。
只证明「注入后红了」不够——还要证明「不注入时是绿的」，否则可能是恒红。

### 场景 1 附加：与今晚的真实故障对照

场景 1 是今晚真实发生过的。报告里单列一节，把注入结果与生产库的真实数据并列：

```bash
# 只读查询，允许对生产库执行
python3 -c "
import sqlite3
c=sqlite3.connect('file:reports/lp_rh/scanner.db?mode=ro',uri=True)
print(c.execute(\"select count(*) from rh_rpc_health where error like '%TimeoutError%'\").fetchone())
"
```

说明「注入实验预测的闸门反应」与「真实故障时闸门的实际反应」是否一致。
真实故障时 `STAGE_A_KEY_FIELDS_INCOMPLETE` 确实回来了（主脑当时观察到
`fee_growth_global_0 ratio=0.98869 < 0.99`），这是这份报告最有价值的一条证据。

### CLI

```
python3 scripts/lp_rh_fault_injection_v1_readonly.py [--out reports/lp_rh/FAULT_INJECTION_REPORT.md] [--json]
```

退出码：全部场景「注入后确实被拦 + 对照组确实不拦」→ 0；任一不符 → 1。
**任何一个场景没能拦住，就是一个真缺陷**，报告里要显著标出，不要淡化。

## 硬性约束

- **绝对不能写生产库**。所有注入都在 `tempfile` 或 `tmp_path` 建的临时库上做。
  对 `reports/lp_rh/scanner.db` **只允许 `mode=ro` 只读查询**。
- **不要修改 `reports/lp_rh/pool_meta.json`**；需要变体就在内存里 copy 一份改。
- **不要修改任何现有 `scripts/`**——本包只新建一个脚本 + 一个测试文件 + 一份报告。
- **不要重启或 kill 任何进程**（采集器 1168725 / daemon 1221417 在跑生产）。
- 不要发任何网络请求。
- **不要执行任何 git 命令。**
- 单次 Write ≤150 行或 6000 字符，脚本超了分次写。

## 各表真实列（照抄——本会话已有五个 worker 猜错 schema）

```
rh_market_states  NOT NULL: asset_address, sample_time, chain_id, session,
                            health_flags_json
                  其它    : source_payload_hash, reference_bid, reference_ask,
                            reference_mid, reference_age_secs, multiplier_human,
                            oracle_paused, derived_block_hash,
                            derived_block_number, source_event_time,
                            fee_growth_global_0, fee_growth_global_1

rh_contract_attestations  NOT NULL: chain_id, address, block_hash,
                                    policy_version, attestation_status, created_at
```

`insert_row()` 会静默丢弃表里没有的列名，猜错只会在很久之后以 NOT NULL 失败露头。

被测函数都在 `scripts/lp_rh_readiness_v1_readonly.py` 与
`scripts/lp_rh_shadow_runner_v1_readonly.py` 里，用
`importlib.util.spec_from_file_location` 加载，**只读取、不修改**。
注意 runner 正被另一条线改动，**不要依赖它的行内实现细节**，只调公开函数。

## 测试（`tests/test_lp_rh_fault_injection_v1_readonly.py`）

1. 六个场景各一条：注入后被拦（断言具体的 blocker 常量名，不要断言字符串子串）。
2. 六个对照组各一条：不注入时该 blocker **不出现**。
3. 脚本对生产库零写入：跑完之后
   `reports/lp_rh/scanner.db` 的 mtime 与跑之前相同
   （或更稳妥：断言脚本源码里对 scanner.db 的打开方式全部含 `mode=ro`）。
4. `--json` 输出可解析，含每个场景的 `injected` / `blocked` / `control_clean` 三个布尔。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_fault_injection_v1_readonly.py -q` 全绿，条数 ≥ 12。
2. 真跑一次：
   `python3 scripts/lp_rh_fault_injection_v1_readonly.py --out /tmp/FI.md`
   退出码 0，`/tmp/FI.md` 生成，六个场景都标注为「注入后被拦、对照组干净」。
   把报告的场景汇总表贴进你的总结。
3. `grep -n "scanner.db" scripts/lp_rh_fault_injection_v1_readonly.py` 的每一处
   都带 `mode=ro`。
4. 生产库未被修改：跑前跑后
   `SELECT COUNT(*) FROM rh_market_states` 的差值只应来自采集器的正常写入
   （报告里说明这一点即可，不必断言相等）。
5. `git status --short` 里只有这两个新文件是 `??`
   （`scripts/lp_rh_shadow_runner_v1_readonly.py` 有另一条线的改动，不要碰）。
