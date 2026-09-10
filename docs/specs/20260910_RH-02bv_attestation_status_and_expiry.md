# RH-02bv — attestation 存在 ≠ attestation 有效

## 缺陷（主脑已核实，不要重新调研）

`scripts/lp_rh_readiness_v1_readonly.py` 的 `audit_pool_attestation()`
（搜 `def audit_pool_attestation` 定位，约 L679）这样判断「池已认证」：

```python
att_row = conn.execute(
    "SELECT COUNT(*) FROM rh_contract_attestations WHERE LOWER(address) = LOWER(?)",
    (asset_address,)
).fetchone()
has_attestation = (att_row[0] > 0) if att_row else False
```

**它只数行数。** 没有看：

1. `attestation_status` 的**值**——只要表里有该地址的任意一行，
   哪怕状态是 `FAILED` / `MISMATCH` / 任何非通过状态，闸门都认为「已认证」
2. `expires_at`——过期的 attestation 照样算数

`STAGE_A_POOL_NOT_ATTESTED` 是 Stage A 的九条件之一。这个判断松了，
就等于「链上身份核验」这道闸门只要求「有人往表里写过一行」。

**当前恰好没暴露**：库里 390 行全是 `ATTESTED_SAME_BLOCK`、`expires_at` 全为 NULL。
但 PRD T06（L998）明确要求 **implementation 变化使 attestation 过期**——
一旦那条路径产生非通过状态或过期时间，这里就会静默放行。
这是本仓库已确认 27 例「静默假绿」的同一形态。

## 要做的事

只改 `audit_pool_attestation()`。

### 1. 看状态值

只有 **`ATTESTED_SAME_BLOCK`** 算通过。定义成模块级常量：

```python
ATTESTATION_PASSING_STATUSES = frozenset({"ATTESTED_SAME_BLOCK"})
```

取该地址**最新一行**（按 `created_at DESC`）的 `attestation_status`：

- 行不存在 → `missing.append("rh_contract_attestations")`（现有行为，保留）
- 状态不在通过集合里 → `missing.append(f"attestation_status={<实际值>}")`
- 状态为 NULL/空 → `missing.append("attestation_status_unknown")`

**不要因为「只见过 ATTESTED_SAME_BLOCK 一种值」就假定其它值不会出现**——
本仓库反复栽在「把当前数据状态当成不变量」上。

### 2. 看过期

同一行的 `expires_at`：

- 为 NULL → **不算过期**（当前 390 行都是 NULL，这是「不设过期」的正常表达）
- 非 NULL 且 **早于**「判定时刻」→ `missing.append("attestation_expired")`

「判定时刻」用一个新的可选参数 `now: Optional[str] = None`，
默认取 `datetime.now(timezone.utc)`。测试要靠它注入固定时刻，
**不要在测试里 monkeypatch 系统时间**。

时间解析复用文件里已有的 `_to_datetime()`。
`expires_at` 解析不出来 → `missing.append("attestation_expires_at_invalid")`
（**fail-close：解析不了不等于没过期**）。

### 3. 返回值里带上证据

在返回的 dict 里加三个字段，便于报告和排查：

```python
"attestation_status": <实际状态值或 None>,
"attestation_expires_at": <原始值或 None>,
"attestation_checked_at": <判定时刻 ISO8601>,
```

## 不许动

- 不要改 `rh_pool_registry` 那半段判断（token0/token1/fee/tick_spacing），
  只动 attestations 这半段。
- **地址比较必须继续用 `LOWER(address) = LOWER(?)`**——本仓库因 EIP-55
  混合大小写栽过一次，合法输入曾使系统永不毕业。
- 不要改 `stage_a_status` / `_build_state` 的其它部分。
- 不要改 `audit_invariant_violations` / `audit_weekends_covered` /
  `audit_unexplained_ledger_diffs` / `audit_missed_risk_events` /
  `audit_key_field_health` / `resolve_judgment_window`
  （commit `4d1d5e3` / `8e54926` / `7ffbb24` 刚验收入库）。
- 不要碰 `scripts/lp_rh_shadow_runner_v1_readonly.py`（另一条线正在改）。
- 不要碰 `scripts/lp_silent_failure_lint_v1_readonly.py`（另一条线刚改完待验收）。
- 不要动任何 `.db`；测试用内存库或 `tmp_path`。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 表的真实列（已核实，照抄——本会话已有三个 worker 猜错 schema）

```
rh_contract_attestations
  NOT NULL: chain_id, address, block_hash, policy_version,
            attestation_status, created_at
  全部    : chain_id, address, block_hash, policy_version, code_hash,
            implementation, abi_version, attestation_status, evidence_json,
            expires_at, created_at
```

`insert_row()` 会**静默丢弃**表里没有的列名，所以猜错的列不会当场报错，
只会在很久之后以 NOT NULL 失败的形式露头。

## 测试（追加到 `tests/test_lp_rh_readiness_v1_readonly.py`）

内存库或 `tmp_path`，每条都要真能触发目标分支。

1. 状态 `ATTESTED_SAME_BLOCK`、`expires_at` 为 NULL → `passed is True`。
   （**这条最重要：修复不能把当前正常的生产状态判成失败**）
2. 状态 `FAILED` → `passed is False`，`missing` 里能看到实际状态值。
3. 状态 `MISMATCH` → 同上。
4. 状态为 NULL/空串 → `missing` 含 `attestation_status_unknown`。
5. `expires_at` 早于注入的 `now` → `missing` 含 `attestation_expired`。
6. `expires_at` 晚于注入的 `now` → **不算过期**，`passed is True`。
7. `expires_at` 是无法解析的字符串（如 `"soon"`）→
   `missing` 含 `attestation_expires_at_invalid`（fail-close）。
8. 同一地址两行、`created_at` 不同、旧行 `ATTESTED_SAME_BLOCK`
   新行 `FAILED` → 取**新行**，`passed is False`。
   ——这条证明取的是最新一行，不是任意一行。
9. 地址用 EIP-55 混合大小写传入，仍能匹配小写存储的行。

## 验收标准（主脑会逐条查）

1. 真实库上跑：
   ```
   python3 scripts/lp_rh_readiness_v1_readonly.py --db reports/lp_rh/scanner.db \
       --out /tmp/rdy_bv.md --asset-address 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
   ```
   Stage A blockers **不含** `STAGE_A_POOL_NOT_ATTESTED`
   （生产那行是 `ATTESTED_SAME_BLOCK` + `expires_at` NULL，应当照常通过），
   其余 blockers 与修复前一致：
   `HOURS_COVERED_INSUFFICIENT`、`STAGE_A_SYNTHETIC_TESTS_UNKNOWN`、
   `STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE`。
   ——**这条是「没有误伤生产」的证据。**
2. `python3 -m pytest tests/test_lp_rh_readiness_v1_readonly.py -q` 全绿，新增 ≥9 条。
3. `grep -n "SELECT COUNT(\*) FROM rh_contract_attestations" scripts/lp_rh_readiness_v1_readonly.py`
   **无输出**（只数行数的写法必须消失）。
4. `git status --short` 里只有
   `scripts/lp_rh_readiness_v1_readonly.py` 和
   `tests/test_lp_rh_readiness_v1_readonly.py` 被改动。
