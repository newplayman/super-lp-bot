# 一、假测试（若有）

变异方式：用 `git show <commit>^:<file>` 动态加载父版本，配合 `:memory:` SQLite 和直接 Decimal 计算；未修改文件。

| commit | 测试函数 | 为什么回退修复它也不红 |
|---|---|---|
| `12efd38` | `tests/test_lp_rh_fee_accrual_dimensional_v1_readonly.py:132` `test_first_step_accrued_zero` | 父版本第一步本来就不计 accrued，`nav == CAPITAL_USD`，该测试只验证旧行为。 |
| `9c59e2e` | `tests/test_lp_rh_first_step_accrual_v1_readonly.py:397` `test_rh02al_real_pool_meta_and_db_sanity` | `ShadowStep` 没有 `accrued_fee` 字段，:433 的列表始终为空，APR 断言永远跳过。父版本实测 `nav_start == 10000`，该测试仍为绿。 |
| `5f23276` | `tests/test_real_config_contract_v1_readonly.py:103,115,129,156` | 这些测试只验证 `pool_meta`、exit-depth 和 runner 合约，与 Stage A 新条件无关；回退 Stage A 仍为绿。 |

其余新增的 Stage A 测试在父版本会因新参数不存在而 `TypeError`；bfc6ed4 的三个测试会因 `coverage_for_asset` 等新函数不存在而导入失败，故按“回退后是否变红”标准有效，但属于较弱的 API 缺失型变异。

# 二、容差核算

输入取测试文件中的 `POSITION_USD=1000`、`PRICE=2484`、`DFG0/DFG1`（`tests/test_lp_rh_fee_accrual_dimensional_v1_readonly.py:29-52`）：

- 旧公式 fee：`27.522077388898...`
- 新公式 fee：`0.026943730019138...`
- 旧/新：`1021.4650076`

因此 `1e-12` 很容易捕获旧量纲错误；但它会漏掉相对误差小于等于 `1e-12` 的错误。

`NAV_DIFF_REL_TOL=1e-12` 的理由不完全成立：

- 当前测试 oracle 使用 float 版 `position_liquidity_raw`，而 runner 使用 Decimal 版，二者相对误差实测为 `1.1117e-15`。
- 若 oracle 也使用 Decimal liquidity，当前 Decimal 28 位上下文的误差约为 `1.83e-22`，原 `1e-20` 实际可达。
- 所以真正的问题是“float oracle 与 Decimal runner 不一致”，不是 Decimal 28 位必然达不到 `1e-20`。

`OPEN_STEP_REL_TOL=1e-25`：

- 当前 open-step 相对误差实测约 `5.76e-29`，原 `1e-40` 对当前调用链确实不可达。
- `1e-25` 能捕获大于 `1e-25` 的 mark 错误，但会漏掉更小错误。
- 另外 `tests/...first_step...:325-339` 直接重新调用 `position_value_at`，并未真正验证 runner 的 mark 接线；负 PnL 测试才是主要接线锁。

# 三、修复引入的新问题

| 文件:行号 | 问题 | 触发输入 | 建议 |
|---|---|---|---|
| `scripts/lp_rh_shadow_runner_v1_readonly.py:381-385` | 缺失 quote 没有 fail-close，而是静默默认 `1.0`。真实 `pool_meta.json` 没有 `quote_usd_per_token1`。 | `pool_meta` 缺少 quote，sample 也缺少 quote | quote 缺失应保持 `open_valid=False`；若 token1 确实是 USD 稳定币，应由上游写入显式证据。 |
| `scripts/lp_rh_shadow_runner_v1_readonly.py:379-380` | `dec0/dec1` 缺失时继续默认 `18/6`，可能把错误 decimals 当成真实值。 | `pool_meta`、sample 都缺少 `dec0` 或 `dec1` | 对 position valuation 要求 decimals 显式存在，缺失则 fail-close。 |
| `scripts/lp_rh_readiness_v1_readonly.py:165-167` | `budget.state == "WARN"` 也阻断；但 `budget_status` 的 WARN 仍低于 100% 软预算。 | `budget={"state":"WARN","fraction":0.8}` | 若 PRD 的“超预算”字面成立，只对 `OVER` 阻断；否则明确记录 WARN 阻断政策并补测试。 |
| `scripts/lp_rh_coverage_audit_v1_readonly.py:223-226`、`scripts/lp_rh_readiness_v1_readonly.py:344-346` | asset 地址按大小写敏感比较。合法 checksum-case 地址会被判定为无数据。 | 实际地址小写有 9,727 行；传入 `asset.upper()` 返回 `NO_ASSET_DATA`、0 行 | 查询统一 `LOWER(asset_address)=LOWER(?)`，并同步修改 key-health 与 MIN/MAX 查询。 |
| `scripts/lp_rh_readiness_v1_readonly.py:352-367` | `_build_state` 新增固定的全表 `column_stats` 查询；实测 SQL 从父版 5 条增至 68 条。 | 当前 `scanner.db` 约 1 万行 | 只对五个 Stage A 字段做一次聚合查询；当前约 0.0276s 增至 0.1094s，约 4 倍，但没有按样本 N+1。 |

本批新增 `.get()` 中，`budget.get("state")`、`coverage` 返回字段、`audit_*` 返回字段均真实存在；未发现再次读取 `over_budget`。唯一实质问题是 quote/decimals 的默认路径。

# 四、Stage A 闸门是否永久关闭（证据输入的可获得性）

不是 `stage_a_status()` 函数本身永久关闭；直接传入完整证据可以通过：

```python
synthetic_tests_passed=True
invariant_violations=0
unknown_state_positions=0
```

但真实 dashboard 路径永久带着 invariant blocker：

- `_build_state` 虽声明了 `invariant_violations` 参数：`scripts/lp_rh_readiness_v1_readonly.py:494-496`
- CLI 只解析并传递 `synthetic_tests_passed`：`:577-585`
- 仓库没有生产调用方提供 `invariant_violations`
- 因此 `stage_a_status(... invariant_violations=None)` 必然触发 `STAGE_A_INVARIANT_VIOLATIONS`：`:169-173`

真实库实测 Stage A blockers 包含：

```text
HOURS_COVERED_INSUFFICIENT
COVERAGE_INSUFFICIENT
STAGE_A_KEY_FIELDS_INCOMPLETE
STAGE_A_POOL_NOT_ATTESTED
STAGE_A_INVARIANT_VIOLATIONS
```

synthetic evidence 有合理入口；invariant evidence 没有。建议增加只读 invariant audit，并由 `_build_state` 计算传入。

# 五、fail-close 在真实数据上丢弃了多少步（实测比例）

一次只读快照、真实 `reports/lp_rh/scanner.db`：

- loader 输入：9,658 步
- `reference_mid IS NULL` 被跳过：49 步
- fee-growth 两腿同时存在：1,646 步
- 有 NAV：1,646 步
- 无 NAV：8,012 步，占 **82.957%**

对应代码为 `scripts/lp_rh_shadow_runner_v1_readonly.py:477-520` 和 `:412-441`。

具体到三类输入：

- `range_pct`：真实 `pool_meta.json` 有值，当前没有因此丢步。
- `price`：49/9,707 原始行无价格，约 **0.506%** 被 loader 丢弃。
- `quote`：真实 `pool_meta.json` 缺失，但代码在 `:384-385` 默认 1.0，因此当前没有丢步；这违反声称的 quote fail-close。若严格修复为缺 quote 阻断，则当前真实数据的 9,658 步将全部失去 NAV，直到上游补 quote 证据。

# 六、两份 liquidity 实现的一致性与去留建议

数学公式一致：

- Decimal 版本：`scripts/lp_rh_v3_inventory_v1_readonly.py:34-104`
- float 版本：`scripts/lp_v3_fee_share.py:3-30`

多组输入的相对差异主要来自 float：

| 输入 quote | 相对差异 |
|---:|---:|
| 1.00 | `1.11e-15` |
| 0.99 | `1.12e-15` |
| 1.01 | `1.01e-15` |
| 2.30 | `2.24e-15` |
| 0.997 | `5.45e-16` |
| 0.50 | `4.25e-16` |

因此现在算的是同一个 `L_raw`，包括 quote≠1；但不是同精度结果。

建议保留两层边界：

- RH replay/NAV：只保留 Decimal `inventory_for_position`，负责两腿、mark 和精确 liquidity。
- 旧 BSC/netcover 接口：保留 `position_liquidity_raw` 作为 float 兼容包装，但内部最好复用同一份核心公式，并要求调用方显式传 quote。

# 七、总体判断

| commit | 判断 | 理由 |
|---|---|---|
| `12efd38` | 需修补 | 量纲修复正确，但新增的第一步测试对父逻辑无鉴别力。 |
| `9c59e2e` | 需修补 | 市价重估和窗口对齐正确，但 quote 缺失会静默默认，真实 sanity 测试还会漏过旧公式。 |
| `5f23276` | 需修补 | Stage A 判定逻辑正确，但 dashboard 没有 invariant evidence 来源，实际闸门永久阻断。 |
| `bfc6ed4` | 需修补 | 资产过滤逻辑正确，但合法大小写地址会被误判为无数据。 |
| `4c889c2` | 需修补 | 按资产接线正确，但继承了大小写敏感导致的过度阻断。 |
| `e66cabe` | ACCEPT | quote 对 liquidity 的缩放数学正确，含 quote≠1 和非法 quote 防护。 |
| `5201b79` | ACCEPT | 模块级 Decimal 污染已清除，计算点改为局部精度；未发现新增行为回归。 |