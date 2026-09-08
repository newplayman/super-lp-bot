# RH-04a：NAV 账本与 HODL 基准（离线可测）

## 背景（一段）

PRD v1.1 §12 规定**唯一总账是 NAV，不是 `Fee − IL − AS` 公式**。§12.1：`NetPnL(t0,t1) = NAV(t1) − NAV(t0) − 净外部注资`；实际 swap 的价差、滑点、gas 已体现在余额变化里，**不得从 NAV PnL 再扣一次**（RH-INV-12）。§12.2 要求三视角：现金/净值结果、HODL 基准差、损耗归因。§12.4 要求同时保存 `reference_nav` 与 `liquidation_nav`。用例 T38–T42 逐条对应。D04 明确：HODL 基准用**实际初始 token 数量**，不是 50/50。

存储层已就位：`rh_journal`（双边记账、`idempotency_key` 唯一、`is_external_flow` 标记）、`rh_position_marks`（`reference_nav` / `liquidation_nav`）、`rh_shadow_positions`（初始库存、区间、虚拟流动性）。终闸与装配器已就位。

## 新增文件

1. `scripts/lp_rh_pnl_v1_readonly.py`（**≤ 250 行**，分次写）
   - 顶部仓库通行 sys.path 引导；复用 `lp_rh_store_v1_readonly` 的 `open_store/migrate/insert_row/assert_decimal_text`。
   - **金额一律 `decimal.Decimal`**，入库转规范化字符串；禁止 float 参与金额运算。
   - `dataclass NavSnapshot`：`position_id, mark_time, wallet_value, lp_principal_value, accrued_fees, verified_rewards, liabilities, reference_nav, liquidation_nav, unvalued_assets: list[str]`。
   - `compute_nav(*, wallet, lp_principal, accrued_fees, verified_rewards, liabilities) -> Decimal`：即 §12.1 的五项加减。任一入参为 `None` → 抛 `ValueError("NAV_INPUT_MISSING: <field>")`（**缺输入不得当 0**）。
   - `net_pnl(nav_t1, nav_t0, external_net_flow) -> Decimal` = `nav_t1 - nav_t0 - external_net_flow`。
   - `hodl_benchmark(*, initial_token0_raw, initial_token1_raw, dec0, dec1, price_t1_token1_per_token0, quote_usd_per_token1) -> Decimal`：按**实际初始两腿数量**估值（D04），不做 50/50 假设。
   - `book_journal_event(conn, *, event_id, idempotency_key, debit, credit, asset, amount_raw, is_external_flow, ref, now)`：薄封装 `insert_row`，重复 `idempotency_key` 让 `IntegrityError` 透传（**内部转账与外部注资都不得重复入账**，RH-INV-13）。
   - `classify_flow(kind: str) -> bool`：返回 `is_external_flow`。`{"deposit","withdrawal","external_gas_sponsor"}` → True；`{"collect","remove_liquidity","add_liquidity","bucket_transfer","swap"}` → **False**（collect 与桶间转账是内部移动，不是新收益）。未知 kind 抛 `ValueError("UNKNOWN_FLOW_KIND")`。
   - `attribution(*, nav_delta, fee_income, gas_paid, price_move_effect) -> dict`：返回**归因视图**，并断言 `abs(sum(components) - nav_delta) <= tolerance`，不一致时在返回值里标 `reconciled=False` 与 `unexplained`。**归因只是解释，不得改变总账。**
   - `liquidation_nav(*, reference_nav, haircut_by_asset: Mapping[str, Decimal], unvalued: list[str]) -> tuple[Decimal, list[str]]`：对无可靠外部价的资产**不按最后成交价估值**，计入 `unvalued` 并从 NAV 扣除（§12.4）。
   - `main()`：`--events-json <file> --out <file>`，读合成事件序列，输出每步 NAV、PnL、HODL 差与归因。不联网、不写活库。
2. `tests/test_lp_rh_pnl_v1_readonly.py`（≤ 250 行），至少 16 个测试，**全部用 `tmp_path` 临时库**：
   - **T38**：collect、价格不变、gas=0 → 钱包增量与未领费用减少相抵，**NAV 完全不变**（`Decimal` 精确相等，不用近似）。
   - **T39**：collect、gas=0.10 → NAV **只下降 0.10**，且归因里 gas 只出现一次（不得再从费用归因里扣一遍，RH-INV-12）。
   - **T40**：外部入金 10、无交易 → NAV 增 10，`net_pnl` 为 **0**。
   - **T41**：下跌后 recenter → 累计亏损与 HODL 初始 lot **不被重置**（同一 `strategy_episode` 前后 `hodl_benchmark` 的初始数量不变）。
   - **T42**：同一笔成交在 30s/5m/30m 三个 markout 窗口 → 分列三项，**不得三次累加同一笔亏损**（断言三者之和 ≠ 单笔亏损×3 的错误写法，且各自独立存储）。
   - `classify_flow("collect")` 为 False、`classify_flow("deposit")` 为 True、未知 kind 抛错。
   - `compute_nav` 任一入参 None → `NAV_INPUT_MISSING`，且**不返回 0**。
   - 重复 `idempotency_key` → `IntegrityError`（内部转账不得重复入账）。
   - `hodl_benchmark` 用实际初始数量：给 `initial_token0_raw != initial_token1_raw` 对应的 50/50 值，断言结果**不等于** 50/50 假设的结果。
   - `liquidation_nav`：某资产无价 → 进 `unvalued` 且从 NAV 扣除，**不按最后成交价估值**。
   - `attribution` 在分项和总账不符时 `reconciled=False` 且 `unexplained` 非零。
   - 金额传 float → 存储层抛 `REAL_NOT_ALLOWED_FOR_MONEY`。

## 不许动什么

- 不改任何现有脚本/测试/配置/六常量；**尤其不许碰 `scripts/lp_rh_collector_v1_readonly.py`（正在生产运行，已跑 1.6h 观测）**。
- 不联网、不写 `reports/lp_rh/`（活库）、不读 `.env*`。
- 不使用 float 表示金额；不实现 Shadow runner（那是 RH-04b）。
- 不要用 TaskCreate/TaskUpdate 工具；单次 Write/Edit ≤150 行。

## 验收标准

- [ ] `git status --short` 新增只有 1 脚本 + 1 测试 + 可能的 fixture；`git diff --stat` 为空。
- [ ] 脚本 ≤250 行；新测试 ≥16 个且全绿。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` 0 failed、14 skipped。
- [ ] T38 的 NAV 不变是 `Decimal` 精确相等，不是容差内近似。
- [ ] `grep -nE 'float\(' scripts/lp_rh_pnl_v1_readonly.py` 零命中。

## 验证命令

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_pnl_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
grep -nE 'float\(' scripts/lp_rh_pnl_v1_readonly.py || echo NO_FLOAT
git diff --stat; git status --short | grep -E 'lp_rh_pnl'
```
