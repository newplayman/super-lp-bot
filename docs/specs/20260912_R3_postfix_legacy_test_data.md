# R3 Post-fix: 收尾 26 个旧测试的 conjunct 门适配

## Context（为什么做）

R3 7 包（Package A-G）整改已 commit 前的本地工作树。R2 9 个测试套全过（39/39）。

但 `python3 -m pytest tests/` 全量跑出 **78 失败**，对比基线（commit 6fda329 pre-R3）的 13 失败：

- **13 失败**：基线就在 `tests/test_lp_rh_reconciliation_v1_readonly.py`（R2-05 selector fail-close 改造前就坏的，**保留**）
- **39 失败**：在 `tests/test_lp_rh_shadow_runner_v1_readonly.py`（per 用户先前指示"不要为兼容旧测试回退"）
- **26 新失败** ← 本 spec 范围

26 新失败是同一类问题：R3 Package C 加固了 conjunct 门（要求 `reference_age_secs`、`source_event_time`、`source_payload_hash`、`fee_growth_global_0/1`、`attestation_status` 等），而旧测试的 `_sample` helper 没补这些字段，导致 position 永远不开 → 所有断言"accrued > 0"、"net_pnl < 0"、"nav > 10000" 都失败，TypeError NoneType 大量出现。

## 范围

需要修的 8 个文件，26 个测试：

1. `tests/test_rh07_0_copy_new_rows_state_merge.py` — 1 test
2. `tests/test_rh07_0_release_no_independent_commit.py` — 1 test
3. `tests/test_rh07_fixall_a_f03_full_cost_nav.py` — 1 test（**已修**：l_pos 改 1e15）
4. `tests/test_lp_rh_first_step_accrual_v1_readonly.py` — 11 tests
5. `tests/test_lp_rh_replay_clock_v1_readonly.py` — 4 tests
6. `tests/test_lp_rh_quote_provenance_v1.py` — 3 tests
7. `tests/test_lp_rh_fee_accrual_dimensional_v1_readonly.py` — 3 tests
8. `tests/test_lp_rh_shadow_daemon_v1_readonly.py` — 2 tests

## 不动

- ❌ `tests/test_lp_rh_shadow_runner_v1_readonly.py`（39 失败，per 用户"不要为兼容旧测试回退"）
- ❌ `tests/test_lp_rh_reconciliation_v1_readonly.py`（13 失败，基线就在失败）
- ❌ R3 7 包的源码改动（已通过 R2 测试验证）
- ❌ R2-01~R2-09 测试文件

## 修法（统一模式）

### 模式 A：测试 `_sample(idx, ...)` helper 加 4 个 conjunct 字段

参考 `tests/test_rh07_fix_c_r2_01_full_cost_wired.py:31` 的 `_cost_sample`：

```python
def _sample(idx, **overrides):
    s = { ...原有字段... }
    # R3 conjunct 门收紧后必须
    s["reference_age_secs"] = 5
    s["source_event_time"] = f"2026-09-08T17:59:{55 + idx:02d}Z"
    s["source_payload_hash"] = f"hash-{idx}"
    s["fee_growth_global_0"] = ...
    s["fee_growth_global_1"] = ...
    s["attestation_status"] = "ATTESTED_SAME_BLOCK"
    return s
```

如果 helper 已存在 attestation_status，保持；只补缺失字段。

### 模式 B：测试缺 conjunct 字段但 sample 构造不在 helper

直接在每个 sample 字典里加上面 4 字段（reference_age_secs、source_event_time、source_payload_hash、fee_growth_global_0/1、attestation_status）。

### 模式 C：quote / quote_as_of 时间错位

测试若用了未来或远古的 `quote_as_of`，runner 会判 stale。统一改成 `2026-09-08T18:00:00Z` 当下时间。

## 具体文件清单

| 文件 | 失败测试数 | helper 名 | 缺什么 |
|---|---|---|---|
| `test_rh07_0_copy_new_rows_state_merge.py` | 1 | `_sample` | reference_age_secs、source_event_time、source_payload_hash、attestation_status |
| `test_rh07_0_release_no_independent_commit.py` | 1 | 内联 | 同上 |
| `test_lp_rh_first_step_accrual_v1_readonly.py` | 11 | `_sample_at` / `_make_sample` 等 | 同上（部分还要 fee_growth_global_0/1） |
| `test_lp_rh_replay_clock_v1_readonly.py` | 4 | 类似 | 同上 |
| `test_lp_rh_quote_provenance_v1.py` | 3 | 类似 | attestation_status、reference_age_secs |
| `test_lp_rh_fee_accrual_dimensional_v1_readonly.py` | 3 | 类似 | 同上 |
| `test_lp_rh_shadow_daemon_v1_readonly.py` | 2 | 类似 | 同上 |

## 红线

- ❌ 不改 `scripts/lp_rh_*` 任何源码
- ❌ 不动 `tests/test_rh07_fix_c_*.py`（R2 测试）
- ❌ 不动 `tests/test_lp_rh_shadow_runner_v1_readonly.py`、`tests/test_lp_rh_reconciliation_v1_readonly.py`（39+13 已知失败）
- ❌ 不增加新测试文件
- ❌ 不删测试
- ✅ 只在旧测试的 `_sample` / 内联 sample 字典里补 conjunct 字段

## 验证

```bash
# 每个修过的文件单独跑
for f in test_rh07_0_copy_new_rows_state_merge.py test_rh07_0_release_no_independent_commit.py test_lp_rh_first_step_accrual_v1_readonly.py test_lp_rh_replay_clock_v1_readonly.py test_lp_rh_quote_provenance_v1.py test_lp_rh_fee_accrual_dimensional_v1_readonly.py test_lp_rh_shadow_daemon_v1_readonly.py; do
    python3 -m pytest tests/$f -q --tb=line 2>&1 | tail -3
done

# 全量
python3 -m pytest tests/ -q --tb=no 2>&1 | tail -3
```

## 期望

- 26 个失败全部修好
- 13 失败（reconciliation）保持不变
- 39 失败（shadow_runner）保持不变（per 用户指示）
- 全量通过率 = (4948+26+6) / (4948+78) ≈ 99.4%
- 不准引入新的失败

## 风险

- 旧测试可能 hardcode 了特定的 nav/net_pnl 数值，conjunct 通过后这些数值变了 → 需要同步更新断言。处理：先跑测试看实际值，调整期望（**仅在 conjunct 通过是真正的修复**时调整）。
- `_sample` helper 可能在多个测试间复用，改一处需确认所有调用方不破。

## 红线（CLAUDE.md 同样适用）

- ❌ `rm -rf`、删文件
- ❌ `git reset --hard`、force push
- ❌ 修改生产配置 / 启动 daemon / 下单
- ❌ commit / push（commit/push 由主脑自己来）

## 输出要求

worker 完成后必须输出：
1. `git diff --stat` （改了哪些文件、加了多少行）
2. 每个改过的文件单独跑 pytest 的最后 3 行（pass/fail/skip 摘要）
3. 全量 pytest 的最后 3 行
4. 任何无法修的、需主脑裁决的例外
