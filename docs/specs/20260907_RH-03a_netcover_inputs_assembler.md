# RH-03a：RH NetCover 输入装配器（复用旧引擎，不改一行）

## 背景（一段）

PRD v1.1 §11、§19 RH-03 要求：**保留 NetCover 引擎，只修输入，不放宽结果**。旧引擎 `scripts/lp_netcover_engine_v1_readonly.py` 的 `apply_netcover_gate(records, *, reward_haircut, lvr_coefficient)` 对每条 record 读取 **9 个必需 key**（缺任一即 `NETCOVER_INPUT_MISSING:<逗号拼接>` 且 `netcover_pass=False`，engine:327–336）：`fee_ev_usd, reward_ev_usd, il_ev_usd, entry_cost_usd, exit_cost_usd, gas_usd, slippage_usd, reward_conversion_cost_usd, exit_latency_loss_usd`；另读 `protocol_type`(:299)、`netcover_model_path`(:312,322)、`reward_haircut`(:344)、`lvr_coefficient`(:346)、`capital_usd`(:366)。本包新增 **RH 专用装配器**产出同一契约，让 RH 候选能进同一个引擎，**引擎与成本模型一行都不改**。

已就位可复用：`scripts/lp_rh_store_v1_readonly.py`（16 表）、`lp_rh_registry_v1_readonly.py`、`lp_rh_capabilities_v1_readonly.py`、`lp_rh_pool_probe_v1_readonly.py`、`lp_rh_bucket_ledger_v1_readonly.py`、`lp_rh_market_session_v1_readonly.py`。

## 新增文件

1. `scripts/lp_rh_netcover_inputs_v1_readonly.py`（**≤ 250 行**，分次写，每次 ≤150 行）
   - 顶部仓库通行 sys.path 引导（同 `lp_scanner_daemon_v1_readonly.py:38-40`）。
   - `from scripts.lp_netcover_engine_v1_readonly import POSITION_TVL_SHARE, HARD_POSITION_TVL_SHARE, position_cap_usd, ACTIVE_SHARE_LIMIT`；`from scripts.lp_netcover_inputs_v1_readonly import LVR_COEFFICIENT_MODEL`；`from scripts.lp_swap_cost_model_v1_readonly import exit_conversion_cost_usd, roundtrip_cost_usd, clmm_token0_value_fraction`。**只 import，不修改这些文件。**
   - 常量：`RH_NETCOVER_MODEL_PATH = "rh_clmm_v3_range_v1"`；`REQUIRED_ENGINE_KEYS`（就是上面 9 个，按引擎顺序）；`RH_CHAIN_ID = 4663`。
   - `MissingInput(NamedTuple)`：`field: str, reason: str`（reason 取值仅 `"NO_PRODUCER"|"CHAIN_DATA_UNAVAILABLE"|"EXTERNAL_DATA_UNAVAILABLE"|"UNSUPPORTED_PROTOCOL"`）。
   - `assemble_rh_clmm_inputs(evidence: Mapping, *, position_usd: Decimal, horizon_hours: float) -> dict`：
     - **入参 evidence 的字段名必须与 RH-01b 探针和 RH-02a 表列对齐**，至少读：`pool_key, protocol, chain_id, token0, token1, fee, tick_spacing, sqrt_price_x96, liquidity_raw, dec0, dec1, tvl_usd, active_liquidity_notional_usd, fee_apr_pct, reward_apr_pct, sigma_daily, gas_usd_estimate, attestation_status`。
     - **fail-closed 优先级**（逐条判定，命中即返回，不再往下算）：
       1. `chain_id != 4663` → `permanent_fail_closed_reason="RH_CHAIN_ID_MISMATCH"`；
       2. `attestation_status != "ATTESTED_SAME_BLOCK"` → `"DISCOVERED_NOT_ATTESTED"`；
       3. `protocol` 非 `"v3"` → `"UNSUPPORTED_PROTOCOL"`。
       三种情况均把 9 个引擎字段全部置 `None`，并写 `missing_inputs`（list[dict]，每项 `{"field":…, "reason":…}`）。**绝不填 0。**
     - 正常路径产出 9 个字段（**horizon-USD 口径**，全部 `float` 或 `None`）：
       - `fee_ev_usd` = `position_usd × fee_apr_pct/100 × horizon_hours/8760 × fee_capture_share`，其中 `fee_capture_share` 由 `clmm_token0_value_fraction` 与目标区间宽度推导；`fee_apr_pct` 缺失 → None + `MissingInput("fee_ev_usd","EXTERNAL_DATA_UNAVAILABLE")`。
       - `reward_ev_usd`：`reward_apr_pct` **未验证时为 0.0 且记 `reward_unverified_reason`**（PRD §11.2：未验证奖励收入为 0，但**基础 fee 缺失不得填 0**）；缺 `reward_apr_pct` 字段本身 → 0.0（不是 None）。
       - `il_ev_usd` = `position_usd × sigma_daily² × (horizon_hours/24) / 8`（经典近似）；`sigma_daily` 缺失 → None + MissingInput。
       - `entry_cost_usd` / `exit_cost_usd`：调 `exit_conversion_cost_usd(value_usd=..., l_active_raw=liquidity_raw, price=..., fee_tier=fee/1e6, dec0=..., dec1=...)`，`side` 分别 `"buy_base"`/`"sell_base"`；任一必需输入缺失 → 两者均 None + MissingInput(`CHAIN_DATA_UNAVAILABLE`)。
       - `slippage_usd`：由 `roundtrip_cost_usd` 与上面两项的差额得出，或直接用其 slippage 分量；输入缺失同上。
       - `gas_usd` = `gas_usd_estimate`；缺失 → None + MissingInput(`CHAIN_DATA_UNAVAILABLE`)（**RH gas 不得复用 Base 的 0.0795 历史常量**）。
       - `reward_conversion_cost_usd`：无已验证奖励时为 0.0。
       - `exit_latency_loss_usd` = `position_usd × 0.005 × horizon_hours/8760`（沿用旧模型 `EXIT_LATENCY_LOSS_APR_PCT_MODEL=0.50` 的口径，即 0.50%/年）。
     - 另写元数据：`protocol_type="clmm"`（**必须是这个字面量**，否则引擎 :299 分派失败）、`netcover_model_path=RH_NETCOVER_MODEL_PATH`、`capital_usd=float(position_usd)`、`lvr_coefficient=LVR_COEFFICIENT_MODEL`、`holding_horizon_hours`、`missing_inputs`、`rh_evidence_block_hash`、`assembled_at`（UTC RFC3339）。
   - `position_cap_for_rh(evidence, *, tier_configured_max: float) -> dict`：调旧 `position_cap_usd(tier_configured_max, pool_tvl, active_liquidity_notional, active_share_limit=ACTIVE_SHARE_LIMIT)`，返回 `{"position_cap_usd":…, "position_cap_pass":bool, "position_cap_reason":…}`；`tvl_usd` 或 `active_liquidity_notional_usd` 缺失/≤0 → `position_cap_usd=None, position_cap_pass=False, reason="INV-TVLSHARE-01_INPUT_MISSING_OR_INVALID"`。**不得自己重算 0.0005/0.001，必须走旧函数。**
   - `classify_zero_candidate(record) -> str`：返回 PRD §8.4 的唯一主状态 `COMPUTED_PASS | COMPUTED_FAIL | INPUTS_UNAVAILABLE | UNSUPPORTED | POLICY_BLOCKED`。规则：有 `permanent_fail_closed_reason` 且为 `UNSUPPORTED_PROTOCOL` → `UNSUPPORTED`；有任何 `missing_inputs` 或 9 键含 None → `INPUTS_UNAVAILABLE`；`netcover_pass is True` → `COMPUTED_PASS`；`netcover_pass is False` 且 9 键齐全 → `COMPUTED_FAIL`。**UNKNOWN/超时/无生产者一律归 `INPUTS_UNAVAILABLE`，绝不当 `COMPUTED_FAIL`。**
   - `main()`：`--evidence-json <file> --out <file>`，读一个合成 evidence 列表，装配后**调用旧 `apply_netcover_gate`**，输出每条的 9 键、`netcover`、`netcover_pass`、`rejection_reason`、`primary_status`。不联网、不写 db。
2. `tests/test_lp_rh_netcover_inputs_v1_readonly.py`（≤ 250 行），至少 16 个测试：
   - **契约对齐**：装配结果的键集合 ⊇ `REQUIRED_ENGINE_KEYS`；把结果直接喂给真实 `apply_netcover_gate`，断言**不出现** `NETCOVER_INPUT_MISSING`（正常路径）。
   - **T32**：`fee_apr_pct` 缺失 → `fee_ev_usd is None` 且 `missing_inputs` 含 `fee_ev_usd`，喂引擎后 `rejection_reason` 以 `NETCOVER_INPUT_MISSING:` 开头、`netcover_pass is False`；对照组：`fee_apr_pct=0.0`（合法计算得 0）→ `fee_ev_usd == 0.0`、9 键齐全、引擎给出 `COMPUTED_FAIL` 而非 missing。**两者 `primary_status` 必须不同**（`INPUTS_UNAVAILABLE` vs `COMPUTED_FAIL`）。
   - **T33**：`reward_apr_pct` 存在但 `reward_verified=False` → `reward_ev_usd == 0.0` 且记 `reward_unverified_reason`，不因此把 `fee_ev_usd` 也置 0。
   - **T01 侧**：`chain_id=46630` → `RH_CHAIN_ID_MISMATCH`，9 键全 None。
   - 未 attested 的池 → `DISCOVERED_NOT_ATTESTED`，9 键全 None，`primary_status=="INPUTS_UNAVAILABLE"`。
   - `protocol="v4"` → `UNSUPPORTED_PROTOCOL`，`primary_status=="UNSUPPORTED"`。
   - **常量不旁路**：`position_cap_for_rh` 的结果与直接调 `position_cap_usd(...)` 完全相等（同参数）；断言模块内**没有**字面量 `0.0005` / `0.001`（`grep` 源码断言）。
   - `lvr_coefficient` 输出恒等于 `LVR_COEFFICIENT_MODEL`（0.50）。
   - `gas_usd_estimate` 缺失 → `gas_usd is None`（**不得回落到 Base 的 0.0795**）；断言模块源码不含 `0.0795`。
   - `classify_zero_candidate` 五种状态各一例。
   - `main --evidence-json` 跑一份含 3 条（正常/缺输入/未 attested）的合成 fixture，退出码 0，输出三条 `primary_status` 分别正确。fixture 放 `tests/fixtures/rh/synthetic/netcover_evidence.json`，标 `"data_kind": "SYNTHETIC_NOT_CHAIN_DATA"`。

## 不许动什么

- **绝不修改** `lp_netcover_engine_v1_readonly.py`、`lp_netcover_inputs_v1_readonly.py`、`lp_swap_cost_model_v1_readonly.py` 或任何现有脚本/测试/配置；只 import。
- 不改六常量，不在本模块内写死 `0.0005`/`0.001`/`0.50`/`0.0795` 等常量数值（必须 import）。
- 不联网、不读 `.env*`、不写 `reports/lp_rh/`、不 import web3/eth_account/solders/solana/requests。
- 不实现终闸合取、不实现三桶政策（那是 RH-03b）。
- 单次 Write/Edit ≤150 行或 6000 字符；不整读 >300 行文件，用 `grep -n` / `sed -n` 取片段。
- **不要用 TaskCreate/TaskUpdate 工具**，直接干活。

## 验收标准

- [ ] `git status --short` 新增只有 1 脚本 + 1 测试 + 1 fixture；`git diff --stat` 为空。
- [ ] 脚本 ≤250 行；新测试 ≥16 个且全绿。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` = 当前基线 + 新增数，0 failed，14 skipped。
- [ ] `grep -nE '0\.0005|0\.001|0\.0795|\b0\.50\b' scripts/lp_rh_netcover_inputs_v1_readonly.py` 零命中（常量只能 import）。
- [ ] 装配结果喂真实 `apply_netcover_gate` 正常路径不产生 `NETCOVER_INPUT_MISSING`。

## 验证命令（仓库根 `/opt/lpbot/lp-bot-v3-origin-check`）

```bash
env -u PYTHONPATH /root/lp-bot/.venv/bin/python scripts/lp_rh_netcover_inputs_v1_readonly.py --evidence-json tests/fixtures/rh/synthetic/netcover_evidence.json --out /tmp/rh_nc.json && head -c 800 /tmp/rh_nc.json
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_netcover_inputs_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
grep -nE '0\.0005|0\.001|0\.0795|\b0\.50\b' scripts/lp_rh_netcover_inputs_v1_readonly.py || echo NO_HARDCODED_CONSTANTS
wc -l scripts/lp_rh_netcover_inputs_v1_readonly.py
git diff --stat; git status --short | grep -E 'lp_rh_netcover'
```
