# RH-06b：MEME 单资产跨池／跨钱包聚合闸（T26）

## 审计发现

T26 取证：全仓 grep `2%` / cross-pool / wallet aggregation **找不到资产聚合闸**。
最接近的是 `lp_rh_meme_audit_v1_readonly.py` 的 `exit_direction_check`，
但它收一个**扁平的** `current_exposure` 映射，**不做跨池聚合**——
把同一资产拆到多个池或多个钱包即可绕过。

## PRD 的原文要求（§260，不要只看 T26 那一行）

> 同一 MEME 聚合 **≤2%**；MEME LP 总部署 ≤8%。
> **LP 头寸按当前拆分的底层资产暴露计入**，并做「**价格越界后全部变为风险腿**」的情景测试。
> **不得按 NFT 数量拆单绕过单资产上限。**

§76 D10 另有：MEME 同时 4–10 池；**单池仅总资金 0.5–2%**。

所以这道闸要算**两个**数，不是一个：**当前暴露**与**最坏情况暴露**
（价格越界后该头寸全部变成该资产）。**两者都必须受 2% 约束**，
否则一个「现在只有 1% 暴露、越界后变 3%」的组合会被放进来。

## 只写一个文件 + 其测试

1. `scripts/lp_rh_meme_aggregation_v1_readonly.py`（≤260 行）
   **不要修改 `lp_rh_meme_audit_v1_readonly.py`**，本包只新增聚合层。

   - `MAX_SINGLE_ASSET_PCT = Decimal("2")`、`MAX_MEME_TOTAL_PCT = Decimal("8")`、
     `MAX_SINGLE_POOL_PCT = Decimal("2")`
     三个常量各带注释标明出处（PRD §260 / §76 D10）。
   - `position_exposure(position) -> dict`
     `position` 形如
     `{"pool","wallet","asset","paired_asset","asset_amount_usd","paired_amount_usd","in_range"}`。
     返回 `{"asset", "current_usd", "worst_case_usd"}`：
     - `current_usd` = `asset_amount_usd`
     - **`worst_case_usd` = `asset_amount_usd + paired_amount_usd`**
       （越界后整个头寸变成单边）
     - 任一金额为 `None` → 对应输出为 `None`（**不是 0**）。
   - `aggregate_by_asset(positions) -> dict`
     按 `asset` 聚合**跨所有 pool 与 wallet**，返回
     `{资产: {"current_usd","worst_case_usd","pool_count","wallet_count","positions"}}`。
     **任一头寸金额缺失 → 该资产的对应合计为 `None`，并在
     `incomplete_assets` 列表里点名**，不得把缺失当 0 求和。
   - `aggregation_gate(positions, *, capital_usd) -> dict`
     返回
     `{"pass": bool, "violations": [...], "by_asset": {...}, "totals": {...},
       "incomplete_assets": [...]}`。
     违规项逐条形如
     `{"kind": "SINGLE_ASSET_CURRENT"|"SINGLE_ASSET_WORST_CASE"|"MEME_TOTAL"|"SINGLE_POOL",
       "asset"/"pool", "pct", "cap"}`。
     - **`incomplete_assets` 非空时 `pass` 必须为 `False`**，
       理由 `kind="EXPOSURE_INCOMPLETE"`——**算不清就不许过**。
     - `capital_usd` 为 `None` 或 `<=0` → `pass=False`，`kind="CAPITAL_UNKNOWN"`。
   - `main()`：`--positions-json --capital-usd --out`，纯离线。

2. `tests/test_lp_rh_meme_aggregation_v1_readonly.py`（≤240 行，**≥16 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。必测：
   - **复现 T26 的绕过场景**：同一资产拆成 4 个池各占总资本 0.6%
     （单池都低于 2%），聚合后 2.4% → `pass is False`，
     违规 `kind == "SINGLE_ASSET_CURRENT"`，`pct` 约 2.4。
     **这条是本包核心。**
   - **跨钱包同样不能绕**：同一资产分到 3 个钱包各 0.8% → 聚合 2.4% → 拦住。
     断言 `wallet_count == 3`。
   - **最坏情况独立受限**：当前暴露 1.5%（过）但 `worst_case` 3%（越界后）
     → `pass is False`，`kind == "SINGLE_ASSET_WORST_CASE"`。
     **这条防「现在合规、越界后超限」。**
   - `in_range` 为 False 的头寸，其 `current_usd` 与 `worst_case_usd` 相等
     （已经越界，整个头寸就是单边）。
   - 单池超 2% → `kind == "SINGLE_POOL"`。
   - MEME 总部署超 8% → `kind == "MEME_TOTAL"`。
   - 一个组合同时触发多条 → `violations` 列出全部，**不是只报第一条**。
   - 某头寸 `asset_amount_usd` 为 `None` → 该资产进 `incomplete_assets`
     且 `pass is False`（**算不清不许过**）。
   - 该资产的 `current_usd` 为 `None`（**不是把缺失当 0 求和**）。
   - `capital_usd=None` → `pass is False`，`kind=="CAPITAL_UNKNOWN"`。
   - 恰好等于 2% → 按「≤2%」语义**通过**（边界闭区间，断言 `pass is True`）。
   - 略超 2% → 拦住。
   - 空 positions → `pass is True`，`violations` 为空（没有头寸就没有违规）。
   - 三个上限常量的值分别是 2 / 8 / 2（防止被静默放宽的回归断言）。
   - 所有金额与百分比是 `Decimal` 不是 float。
   - `pool_count` 与 `wallet_count` 统计正确（去重计数）。

## 不许动
不改 `lp_rh_meme_audit_v1_readonly.py` 或任何其他脚本。
**不要把本闸接进终闸**——接入是下一包。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_meme_aggregation_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥16 全绿；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
