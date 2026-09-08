# RH-05a：股票代币参考价与公司行动守卫（离线可测）

## 背景（一段）

PRD v1.1 §9.2 规定股票代币的统一模型，§9.5 规定公司行动与 oracle pause 守卫，用例 T17–T24 逐条对应。主脑已实测（`reports/rh_pivot/20260907T124500Z/RH-05-research/`）：194 个股票代币全部 18 位小数、100% 为 `SESSION_NESTED` schema、12 个 `currentMultiplier ≠ 1`（**CRWD 恰为 4.0**，全链唯一整数倍拆股）、41 条公司行动全部是现金分红、`pendingMultiplier` 当前全空。四个 ETF 池已 `ATTESTED_SAME_BLOCK`。

本包只做**纯计算与守卫逻辑**，不联网（真实抓取由主脑做，已存快照 `RH_ASSETS_SNAPSHOT.json`）。

## 新增文件

1. `scripts/lp_rh_stock_reference_v1_readonly.py`（**≤ 250 行**）
   - 顶部仓库通行 sys.path 引导；金额一律 `Decimal`，禁止 float。
   - **PRD §9.2 的统一模型，逐条实现**：
     ```
     token_quantity              = raw_balance / 10**token_decimals
     multiplier_human            = onchain_uiMultiplier_raw / 10**18  或  Decimal(api.currentMultiplier)
     underlying_share_equivalent = token_quantity * multiplier_human
     reference_token_price_usd   = underlying_price_usd * multiplier_human
     reference_stock_per_usdg    = reference_token_price_usd / usdg_price_usd
     ```
   - `token_equivalent_price(*, underlying_price_usd, multiplier_human, source_is_already_token_equivalent: bool) -> Decimal`：**当 `source_is_already_token_equivalent` 为 True 时直接返回 `underlying_price_usd`，绝不再乘乘数**（T18：Chainlink feed 已是 token-equivalent 则不得重复应用）。
   - `usdg_normalized_price(token_price_usd, usdg_price_usd) -> Decimal`：`usdg_price_usd <= 0` 抛 `ValueError("USDG_PRICE_INVALID")`（T19）。
   - `split_preserves_reference(*, before_underlying, before_multiplier, after_underlying, after_multiplier) -> bool`：断言 `before_underlying*before_multiplier == after_underlying*after_multiplier`（T20：拆股后单 token 参考价不变，raw 余额不变，不得记 -90% 亏损）。
   - `dataclass ReferenceValue`：`reference_bid, reference_ask, reference_mid, executable_exit_bid_for_position_size, reference_age_secs, quote_age_secs, source_quality, redeem_access`。**命名必须是 `ReferenceValue` 而非 `GuaranteedFairPrice`**（PRD §9.3：参考价不是保证成交价）。`redeem_access` 默认 `"NOT_PROVEN"`。
   - `corp_action_guard(*, current_multiplier, pending_multiplier, effective_at, now, oracle_paused) -> tuple[str, list[str]]`：返回 `(state, reasons)`。规则：`oracle_paused is True` → `"ORACLE_PAUSED"`；`pending_multiplier` 非空且 `effective_at` 在未来 → `"CORP_ACTION_GUARD"`；`current_multiplier` 或 `oracle_paused` 为 `None`（读取失败）→ `"UNKNOWN"`（**不得当 False**，T21）；`pending == current` 且无未来事件 → `"NORMAL"`（T22：不虚构公司行动，但仍核对 pause）。
   - `allows_new_or_recenter(state) -> bool`：仅 `"NORMAL"` 为 True；`ORACLE_PAUSED` / `CORP_ACTION_GUARD` / `UNKNOWN` 全为 False（T21：禁止新增与重新居中）。
   - `stale_classification(*, session, oracle_age_secs, heartbeat_secs) -> str`：复用 `lp_rh_market_session.stale_reason`（**import 不重写**），返回 `EXPECTED_SESSION_CLOSED` / `STALE_WHILE_EXPECTED_LIVE` / `FRESH`（T23：两者都不放行新窄区间但原因分开）。
   - `exit_quote_required(reference: ReferenceValue) -> tuple[bool, str]`：`executable_exit_bid_for_position_size is None` → `(False, "INPUTS_UNAVAILABLE: EXIT_QUOTE")`（T24：参考价可读但无足额退出报价，**不是无风险折价**）。
   - `load_assets_snapshot(path) -> dict[str, dict]`：读主脑存的 `RH_ASSETS_SNAPSHOT.json`，按 `tokenSymbol` 索引。
   - `main()`：`--snapshot <file> --symbol <SYM> --underlying-usd <x> --out <file>`，不联网。
2. `tests/test_lp_rh_stock_reference_v1_readonly.py`（≤ 250 行），至少 16 个测试：
   - **T17**：`raw=2e18, decimals=18, multiplier_raw=1.25e18, underlying=100` → token 数 2、等价股数 2.5、单 token 价 125、总值 250（Decimal 精确）。
   - **T18**：`source_is_already_token_equivalent=True` 且 underlying 已是 125、乘数 1.25 → 结果**仍是 125**，不是 156.25。
   - **T19**：USDG=0.98、token 价 125 → `≈127.5510204081632653`（容差 1e-8）；USDG=0 抛 `USDG_PRICE_INVALID`。
   - **T20**：`200×1 == 20×10` → True；`200×1 vs 20×9` → False。
   - **T21**：`oracle_paused=True` → `ORACLE_PAUSED` 且 `allows_new_or_recenter` False；`oracle_paused=None` → `UNKNOWN` 且同样 False。
   - **T22**：`pending == current` 且 `effective_at` 为 None → `NORMAL`，`reasons` 不含虚构事件。
   - **T23**：三种 stale 分类各一例。
   - **T24**：`executable_exit_bid_for_position_size=None` → `(False, "INPUTS_UNAVAILABLE: EXIT_QUOTE")`。
   - **真实数据回归**：从 `RH_ASSETS_SNAPSHOT.json` 读 **CRWD**，断言 `currentMultiplier == "4.000000000000000000"`，用它跑 `token_equivalent_price`（`source_is_already_token_equivalent=False`，underlying=100）得 400；再以 True 得 100。**这是全链唯一整数倍拆股的实测对照。**
   - 类名断言：模块中**不存在** `GuaranteedFairPrice`，存在 `ReferenceValue`；`redeem_access` 默认 `"NOT_PROVEN"`。
   - `grep` 源码断言无 `float(`。

## 不许动什么

- 不改任何现有脚本/测试；**不许碰 `scripts/lp_rh_collector_v1_readonly.py`（生产运行中）**、`lp_rh_shadow_runner_v1_readonly.py`（另一 worker 正在写）。
- 不联网、不写活库、不读 `.env*`、不使用 float 表示金额。
- 不实现 STOCK 策略与区间逻辑（那是后续包）。
- 不要用 TaskCreate/TaskUpdate 工具；单次 Write/Edit ≤150 行。

## 验收标准

- [ ] `git status --short` 新增只有 1 脚本 + 1 测试；`git diff --stat` 为空。
- [ ] 脚本 ≤250 行；新测试 ≥16 个且全绿。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` 0 failed、14 skipped。
- [ ] `grep -c 'GuaranteedFairPrice' scripts/lp_rh_stock_reference_v1_readonly.py` 为 0；`grep -nE 'float\(' ` 零命中。
- [ ] CRWD 实测对照测试通过。

## 验证命令

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_stock_reference_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
grep -c 'GuaranteedFairPrice' scripts/lp_rh_stock_reference_v1_readonly.py
git diff --stat; git status --short | grep -E 'lp_rh_stock_reference'
```
