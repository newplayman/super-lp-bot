# RH-02bn — Stage A 判定窗口：把「累计覆盖率」换成「当前采集代码之后的覆盖率」

## 用户已批准（2026-09-10）

主脑提出三个选项，用户答「以上 abc 都同意」。本包实现的是**方案 C**，
并把 A 的兜底思想与 B 的信息保留一起容纳进去（见「三个口径怎么并存」）。

## 缺陷

`scripts/lp_rh_readiness_v1_readonly.py` 的 Stage A 覆盖率是**无窗口的累计比率**
（L122-131）：

```python
hours_covered    = (last - first).total_seconds() / 3600.0
expected_samples = hours_covered * 3600.0 / expected_interval_secs
coverage_ratio   = actual_samples / expected_samples
```

历史缺口一旦产生就永久留在分子里，**后续再完美的采集也抹不掉**。

实测（as-of 2026-09-10T02:33Z）：累计 `coverage_ratio = 0.9715`，缺 309.6 个样本，
全部来自 09-08 早期部署不稳与几次改代码重启。而窗口内覆盖率随窗口变短而变好
（近 6h = 0.9965），说明**采集器现在是健康的**。

要把累计比率爬回 0.99：

| 今后速率 | 还需 |
|---|---|
| 完美 240/h | 83.7 h = 3.49 天 |
| 近 6h 实测 239.2/h | 128.2 h = 5.34 天 |
| 近 24h 实测 235.6/h | **永远达不到**（收敛到 0.9818） |

这是一道**「静默假红」**——看着像在等时间，实际可能等不到。
它与已修的 `fee_growth` 缺口（按 `first_populated_time` 划窗）**完全同构**。

## 方案：判定窗口 = 采集侧代码最后一次变更之后

### 为什么以「采集侧代码」为界

Stage A 判的是**数据覆盖与关键字段健康**，也就是「这批数据是怎么采出来的」。
采集器或 schema 一变，之前的数据就是**另一套口径采的**，不该与新数据混算。
闸门自身的变更不改变已采数据的质量，**不应该重置计时**——所以白名单里
只放采集侧，不放 readiness 自己，也不放 shadow runner / inventory。

实测这个界定的效果（主脑已验证，不用重新算）：

```
采集侧最后变更 = f3fb67f @ 2026-09-09T16:05:41Z
                 ("feat(rh-02ac): collect feeGrowthGlobal so the loop can value what it opens")
窗口内 2549 行 / 全量 10607 行
窗口 hours    = 10.642        （累计口径是 45.30）
窗口 coverage = 0.9981   PASS （累计口径是 0.9715  FAIL）
```

**净效果是 Stage A 变得更远，不是更近**：`HOURS_COVERED` 从「还差 26.7 小时」
变成「还差 61.4 小时」，但 `COVERAGE` 从「可能永远到不了」变成「已达标」。
这个窗口起点与 `fee_growth` 的 `first_populated_time`（09-09T16:05:55）几乎重合，
因为正是同一次 commit 加的那两列——不是巧合，是同一个口径变更。

### 三个口径怎么并存

| 口径 | 用途 | 是否参与 blockers |
|---|---|---|
| **判定窗口**（本包新增） | Stage A 的 `hours_covered` / `coverage_ratio` | **是**，唯一判定依据 |
| **累计**（现有行为） | 并列显示为 `cumulative_hours` / `cumulative_coverage_ratio` | **否**，只作参考 |
| **最近 72h 滑动**（兜底信息） | 显示为 `recent_72h_coverage_ratio` | 否 |

三个都算、都显示，但**只有判定窗口那个进 blockers**。这样信息不丢，
口径也不会被人挑着用。

## 要做的事

改 `scripts/lp_rh_readiness_v1_readonly.py`。

### 1. 新增窗口解析

```python
COLLECTION_CODE_PATHS = (
    "scripts/lp_rh_collector_v1_readonly.py",
    "scripts/lp_rh_store_v1_readonly.py",
)

def resolve_judgment_window(repo_root: str) -> dict:
    """判定窗口起点 = 采集侧代码最后一次 commit 的时间（UTC）。

    返回 {"window_start": "<ISO8601 Z>" | None,
          "code_version": "<short sha 12>" | None,
          "source": "git log -1 -- <COLLECTION_CODE_PATHS>",
          "reason": "<拿不到时写清楚为什么>"}
    """
```

实现：`git log -1 --format=%H%x09%cI -- <COLLECTION_CODE_PATHS>`，
`cwd=repo_root`，`capture_output=True`。

**fail-close**：不是 git 仓库、git 不可用、命令非零退出、输出为空
→ 三个字段全 `None` 并写 `reason`。**绝不返回一个猜测的时间，
也绝不静默退回全量口径**——那正是本仓库已确认 26 例静默假绿的模式。

### 2. `stage_a_status()` 增参与判定改口径

新增两个关键字参数（都放在 `*` 之后）：

- `judgment_window: dict`（`resolve_judgment_window` 的返回值）
- `cumulative: dict`（累计口径的 `{"hours_covered","coverage_ratio","actual_samples","expected_samples"}`）

判定逻辑改为：

- `judgment_window["window_start"] is None`
  → blocker **`JUDGMENT_WINDOW_UNRESOLVED`**，且 `passed=False`。
  （这是新增的 fail-close，务必有测试）
- 否则 `hours_covered` / `coverage_ratio` 用**窗口内**的值判定，
  阈值不变（72 小时 / 0.99）。

返回 dict 里新增（不删任何现有键）：
`judgment_window_start`、`judgment_code_version`、
`cumulative_hours`、`cumulative_coverage_ratio`、`recent_72h_coverage_ratio`。

### 3. `coverage_for_asset()` 支持窗口

给它加一个可选参数 `since: Optional[str] = None`；
非 None 时 SQL 加 `AND sample_time >= ?`。
**地址比较继续用 `LOWER(asset_address) = LOWER(?)`**（本仓库踩过 EIP-55 的坑）。

### 4. `_build_state()` 接线

调用 `resolve_judgment_window()`（`repo_root` 从 `--repo` 参数或
脚本所在目录的上一级推出），分别算窗口内、累计、近 72h 三组覆盖，
一起传给 `stage_a_status()`。把 `judgment_window` 结果也放进
`state["judgment_window"]` 供报告渲染。

### 5. CLI 与报告

- 新增 `--judgment-window-start <ISO8601>`：**显式覆盖**窗口起点（测试与人工排查用）。
  给了这个参数就不查 git，`code_version` 记为 `"OVERRIDE"`。
- 新增 `--repo <path>`：仓库根，默认脚本所在目录的上一级。
- Markdown 报告的 Stage A 那行下面加一行，形如：

```
  - 判定窗口: 自 2026-09-09T16:05:41Z 起 (code_version=f3fb67f...), 窗口内 2549 行
  - 参考(不判定): 累计 hours=45.30 coverage=0.9715 | 近72h coverage=0.9832
```

## 不许动

- **不要改阈值**：`STAGE_A_MIN_HOURS = 72`、覆盖率 `0.99` 一个字都不能动。
  本包只改「用哪段数据算」，不改「算出来要多少才算过」。
- 不要动 `audit_key_field_health`（它已按 `first_populated_time` 划窗，是对的）。
- 不要动 `stage_b_status` / `live_gate_status` / `audit_invariant_violations`。
- 不要动任何 `.db`，全部只读 SQL。
- **不要执行任何 git 命令去改仓库状态**（脚本内部调 `git log` 只读是本包要求的；
  但你自己不要 add / commit / checkout / stash）。
- 单次 Write/Edit ≤150 行或 6000 字符，分次改。
- 不要整读这个 800+ 行的文件。关键段：L97-200 `stage_a_status`、
  L698-770 `_build_state`、`coverage_for_asset` 用 `grep -n` 定位。

## 测试（追加到 `tests/test_lp_rh_readiness_v1_readonly.py`）

每条都必须**在修复前会失败**——本仓库已四次写出「构造的输入进不去目标分支」
的永远绿测试，务必先确认断言真能触发。

1. `resolve_judgment_window` 指向非 git 目录（`tmp_path`）
   → `window_start is None` 且 `reason` 非空。
2. 承 1：`stage_a_status` 拿到该结果 → blockers 含 `JUDGMENT_WINDOW_UNRESOLVED`，
   `passed is False`。**这条是本包的 fail-close 核心。**
3. 构造内存库：窗口前有大量缺口、窗口后满格
   → 窗口内 `coverage_ratio >= 0.99` 且 blockers **不含** `COVERAGE_INSUFFICIENT`；
   同一份数据的 `cumulative_coverage_ratio < 0.99`。
   **这条同时证明「窗口生效了」和「累计口径仍被如实计算」。**
4. 承 3：`hours_covered` 用的是**窗口内**跨度，不是全量跨度
   （断言它明显小于 `cumulative_hours`）。
5. 阈值没被动过：窗口内 hours=71.9 → 仍有 `HOURS_COVERED_INSUFFICIENT`；
   窗口内 coverage=0.9899 → 仍有 `COVERAGE_INSUFFICIENT`。
6. `--judgment-window-start` 覆盖生效，且 `code_version == "OVERRIDE"`。
7. 地址用 EIP-55 混合大小写传入仍能匹配小写存储的行。
8. `recent_72h_coverage_ratio` 与 `cumulative_coverage_ratio` 都出现在返回 dict 里，
   且**都不影响** blockers（构造一个近 72h 很差但窗口内很好的库来证明）。

## 验收标准（主脑会逐条查）

1. 在**真实库**上跑：
   ```
   python3 scripts/lp_rh_readiness_v1_readonly.py --db reports/lp_rh/scanner.db \
       --out /tmp/rdy_bn.md --asset-address 0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
   ```
   Stage A blockers **不再含 `COVERAGE_INSUFFICIENT`**，
   仍含 `HOURS_COVERED_INSUFFICIENT`（窗口内约 10.6 小时 < 72）。
   报告里能看到 `判定窗口: 自 2026-09-09T16:05:41Z 起`。
   ——这条是本包的核心证据。
2. `grep -n "STAGE_A_MIN_HOURS = 72" scripts/lp_rh_readiness_v1_readonly.py` 仍在，
   覆盖率阈值 `0.99` 未被改动（`git diff` 里不得出现阈值行）。
3. 全量 `python3 -m pytest tests/ -q` 通过，新增测试 ≥ 8 条。
4. `git status --short` 里只有 `scripts/lp_rh_readiness_v1_readonly.py` 和
   `tests/test_lp_rh_readiness_v1_readonly.py` 被改动。

---

## 派发时补充（2026-09-10 04:20，主脑加）

本 spec 写于 commit `4d1d5e3` 之前。此后 `lp_rh_readiness_v1_readonly.py`
已两次入库改动，**上面引用的行号全部作废**，请用 `grep -n` 重新定位：

- `grep -n "def stage_a_status" scripts/lp_rh_readiness_v1_readonly.py`
- `grep -n "def coverage_for_asset" scripts/lp_rh_readiness_v1_readonly.py`
- `grep -n "def _build_state" scripts/lp_rh_readiness_v1_readonly.py`

**这两次入库的成果不许破坏**（改坏了会被退回）：

- `4d1d5e3` — `audit_weekends_covered` / `audit_unexplained_ledger_diffs` /
  `audit_missed_risk_events` 三个只读审计，空表返回 `None` 而非 `0`
- `8e54926` — `audit_invariant_violations` 的 `unavailable_checks`，
  以及新常量 `STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE`

改完必须确认这两条仍然成立（真实库上）：

```
audit_invariant_violations(conn)["violations_count"] is None
audit_weekends_covered(conn, asset_address=...)["reason"] == "OK"
```

**另外**：真实库现在的 Stage A blockers 是四个——
`HOURS_COVERED_INSUFFICIENT`、`COVERAGE_INSUFFICIENT`、
`STAGE_A_SYNTHETIC_TESTS_UNKNOWN`、`STAGE_A_INVARIANT_VIOLATIONS_UNAVAILABLE`。
本包做完之后，`COVERAGE_INSUFFICIENT` 应当**消失**，其余三个**保持**。
验收标准第 1 条按这个对。

**写测试时注意真实列名**（上一个包在这里栽过——`insert_row` 会静默丢弃
不存在的列，于是只暴露成 NOT NULL 失败）：

```
rh_market_states  NOT NULL: asset_address, sample_time, chain_id, session,
                            health_flags_json
```
