# RH-05d：溢价守卫与股票时段策略闸（离线可测）

## 背景
PRD §10.2 与 §12 的溢价分档，B2 §12 给出 Shadow 初值。主脑 2026-09-08 实测（`reports/rh_pivot/20260907T124500Z/RH-05-research/REFERENCE_PRICE_AND_PREMIUM_20260908.md`）：SGOV +37bps、GLD +65bps、SPY +24bps、QQQ +20bps、NVDA +30bps、AMC −90bps，**六个全部落在 NORMAL 档**。参考价源 `GET /rhj/prices` 带 `generatedAt`（服务端时间，报价龄实测 3–4 秒）与 `isTradingHalt`。

已就位可直接 import：`lp_rh_stock_reference_v1_readonly`（`ReferenceValue`、`token_equivalent_price`、`corp_action_guard`、`exit_quote_required`）、`lp_rh_market_session_v1_readonly`（`classify_session`、`evaluate_health`、`allows_new_position`）、`lp_rh_multiplier_reader_v1_readonly`（`cross_check_api`）。

## 只新建两个文件

1. `scripts/lp_rh_premium_guard_v1_readonly.py`（≤250 行）
   - 分档常量（**PRD/B2 的 Shadow 初值，标注为未校准**）：
     ```python
     PREMIUM_BANDS = ((100, "NORMAL"), (300, "REDUCE_SIZE"), (700, "NO_NEW_WIDEN_REMOVE_EVAL"))
     # >700 -> "DISLOCATION"
     CALIBRATION_STATUS = "SHADOW_INITIAL_NOT_CALIBRATED"
     ```
   - `premium_bps(*, dex_price, reference_price) -> Decimal|None`：`reference_price <= 0` 或任一为 `None` → `None`（**不得返回 0**）。
   - `classify_premium(bps) -> tuple[str, bool]`：返回 `(档位, allows_recenter)`。`bps is None` → `("UNKNOWN", False)`。`DISLOCATION` 档 `allows_recenter` 必须为 **False**（PRD §11：禁止重新居中）。
   - `range_center(*, chainlink_or_reference, dex_twap, premium_bps, max_dex_weight_bps=100) -> tuple[Decimal, str]`：**PRD §11 核心规则**——`abs(premium_bps) > max_dex_weight_bps` 时 DEX **完全不参与** center，返回 `(reference, "DEX_EXCLUDED_PREMIUM_EXCEEDS_THRESHOLD")`；否则按权重中位数合成。**绝不允许 center 跟随 DEX 漂移。**
   - `stock_entry_gate(*, session, health_flags, premium_band, corp_action_state, reference: ReferenceValue, multiplier_agreement: str) -> tuple[bool, list[str]]`：合取。**首版只允许 `session == "RTH"`**（PRD §10.2）；`health_flags` 非空 → 拒；`premium_band != "NORMAL"` → 拒；`corp_action_state != "NORMAL"` → 拒；`reference.executable_exit_bid_for_position_size is None` → 拒并记 `INPUTS_UNAVAILABLE: EXIT_QUOTE`；`multiplier_agreement != "AGREE"` → 拒。返回全部拒绝理由，不短路。
   - `quote_freshness(*, generated_at, now, max_age_secs=60) -> tuple[str, int]`：返回 `(状态, age_secs)`；`generated_at` 为 `None` → `("UNKNOWN", -1)`。状态取 `FRESH / STALE / UNKNOWN`。**用服务端 `generatedAt`，不得用本地拉取时间**。
   - `main()`：`--quotes-json --pool-prices-json --out`，不联网。
2. `tests/test_lp_rh_premium_guard_v1_readonly.py`（≤250 行，≥16 测试）
   - **实测回归**：用主脑实测的六组真实数据（SGOV 100.99/101.36、GLD 402.75/405.35、SPY 766.98/768.86、QQQ 717.36/718.78、NVDA 230.43/231.11、AMC 2.64/2.6142）断言 `premium_bps` 落在 ±5bps 内，且六个全部 `classify_premium` 为 `NORMAL`。
   - 溢价 150bps → `REDUCE_SIZE`；400bps → `NO_NEW_WIDEN_REMOVE_EVAL`；800bps → `DISLOCATION` 且 `allows_recenter is False`。
   - `reference_price=0` → `premium_bps is None`（断言不是 0）；`classify_premium(None)` → `("UNKNOWN", False)`。
   - **center 不追 DEX**：premium 150bps（>100）→ `range_center` 返回 reference 且 reason 为 `DEX_EXCLUDED_PREMIUM_EXCEEDS_THRESHOLD`；premium 50bps → DEX 参与。
   - `stock_entry_gate`：session 非 RTH → 拒；health_flags 含任意项 → 拒；premium 非 NORMAL → 拒；corp_action 非 NORMAL → 拒；无退出报价 → 拒且理由含 `EXIT_QUOTE`；乘数不一致 → 拒。**六项各一个测试，且有一个「全部满足 → 通过」的正例。**
   - `quote_freshness`：3 秒 → FRESH；120 秒 → STALE；`None` → `("UNKNOWN", -1)`。
   - 断言 `CALIBRATION_STATUS == "SHADOW_INITIAL_NOT_CALIBRATED"`（阈值未经真实数据校准，不得当已验证）。

## 不许动
不改任何现有文件；不联网；不写活库；不碰 `lp_rh_collector_v1_readonly.py`（生产运行中）与 codex 正在写的 `lp_rh_exit_depth`/`lp_rh_funnel_autopsy`/`lp_rh_meme_audit`/`lp_rh_markout`。金额用 `Decimal`，禁止 float。不要用 TaskCreate/TaskUpdate。

## 验收
`pytest tests/test_lp_rh_premium_guard_v1_readonly.py -q` 全绿；全量 0 failed / 14 skipped；`git diff --stat` 为空。
