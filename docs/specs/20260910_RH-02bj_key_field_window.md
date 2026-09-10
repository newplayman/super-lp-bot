# RH-02bj：关键字段健康度要按「该列存在之后」统计，不是全表

## 调研结论（`reports/AUDIT_key_fields_gap_20260910.md`）

`STAGE_A_KEY_FIELDS_INCOMPLETE` 的唯一卡点是 `fee_growth_global_0/1` 的 **21.83%**。
但那是**纯历史缺口，不是采集器的 bug**：

```
该列 2026-09-09T16:05:55 才加入
加列之后的非空率 99.87%（3 个 NULL：2 个 CHAIN_DEGRADED + 1 个瞬时 RPC 失败）
加列之前的 ~8,057 行永远不可能有值
```

而 `audit_key_field_health` 按**全表**统计、**无时间窗口**，
于是要靠新样本把 21.83% 稀释到 99%，需要约 **914,691 行 ≈ 158.8 天**。

**闸门把「这列从来没有过」和「这列现在采不到」混为一谈了。**
前者是模式演进的正常产物，后者才是数据质量问题。

## 你要做的

改 `scripts/lp_rh_readiness_v1_readonly.py` 的 `audit_key_field_health`：

### 一、按列各自的「首次有值时刻」划窗口

对每个受检列，先求出它的 `MIN(sample_time) WHERE <col> IS NOT NULL`，
**只统计该时刻之后的行**的非空率。

一列若**从未有过值**（全表 NULL），不能因此判为「通过」——
那是最严重的情形。必须**明确阻断**，理由点名该列，
且与「有值但非空率不足」区分开（例如 `KEY_FIELD_NEVER_POPULATED`
与 `KEY_FIELD_INCOMPLETE`）。**这一条是本包的关键**：
按「首次有值之后」统计，天然会把「从没有值」的列变成空窗口，
若不特判就会算出「0 行里 0 个 NULL = 100% 通过」——
**那正是这个项目已确认 24 例的那一族缺陷**（空集合当成全部满足）。

### 二、窗口信息要可见

返回值里带上每列的：首次有值时刻、窗口内行数、窗口内非空率。
dashboard 上要能看出「这列是新加的，只统计了最近 N 行」，
否则下一个人会以为闸门在看全部历史。

### 三、不要放宽阈值

阈值仍是 0.99。本包**只改统计口径，不改标准**。
改完后 `fee_growth` 应当以 99.87% 通过；若不通过，**贴出实测值**，不要调阈值。

## 不许动

`scripts/lp_rh_coverage_audit_v1_readonly.py`（覆盖率是另一套口径，不要顺手改）、
`scripts/lp_rh_shadow_runner_v1_readonly.py`、任何 `.db`、
`reports/` 下任何文件、`scripts/lp_silent_failure_lint_v1_readonly.py`。
`tests/test_lp_rh_readiness_v1_readonly.py` **只允许新增测试**。

## 验收标准

1. **用真实库跑**：`fee_growth_global_0/1` 应以约 **99.87%** 通过，
   `STAGE_A_KEY_FIELDS_INCOMPLETE` 从 blockers 中消失。贴出完整 blockers 列表。
   （其余 blocker 应仍在：时长、覆盖率、attestation、合成测试证据。）
2. **从未有值的列必须阻断**：构造一个该列全 NULL 的内存库，
   断言判定为不通过且理由是 `KEY_FIELD_NEVER_POPULATED`（或你定的等价常量），
   **不是 100% 通过**。这条是本包最重要的测试。
3. **窗口边界**：构造「首次有值之后仍有 NULL」的库，
   断言只统计窗口内、且非空率算对。
4. **防回归**：一个所有列自始至终 100% 非空的库，判定与改动前一致。
5. 全量 `pytest tests/ -q -p no:cacheprovider | tail -3`：
   基线 **4659 passed / 0 failed**，不得新增 failed。
6. 改完后跑一次
   `/root/lp-bot/.venv/bin/python scripts/lp_silent_failure_lint_v1_readonly.py --fail-on-new`，
   **退出码应为 0**。若报新增，说明你写了新的高危模式，自己先看一眼。

## 坑（今晚踩过多次）

- `rh_market_states` 的 NOT NULL 列：`asset_address`/`sample_time`/`chain_id`/
  `session`/`health_flags_json` —— 测试插入必须带全，否则 IntegrityError。
- 测试至少一个用例走**真实** `reports/lp_rh/scanner.db`。
- 构造「触发缺陷」的输入前，先确认它真的能走到那条分支。

## 纪律

- **不要执行任何 git 命令**，不要重启 daemon，不要动 crontab。
- 单次写入 ≤ 150 行。
