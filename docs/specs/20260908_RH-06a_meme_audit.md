# RH-06a：MEME 准入审计与退出会计（离线可测）

## 背景
PRD §10.3 与 §15.1，用例 **T43**（下跌跌穿下界不得自动下移区间加风险）、**T44**（remove 成功但卖出失败 → `REMOVED_RISKY_INVENTORY`，不显示 cash closed，资产额度不释放）、**T45**（原子 exit 中 swap 回滚 → remove 亦视为未完成，独立重检后才可 remove-only）、**T46**（退出到 USDG 导致加大 USDG 风险 → 不因 action=exit 绕过资产风险方向检查）。PRD §10.3 明令：B2 允许的 5% transfer tax **首版不作为准入**，初始只接受验证为无转账税的标准行为。

## 只新建两个文件
1. `scripts/lp_rh_meme_audit_v1_readonly.py`（≤300 行）
   - `admission_check(token_facts: Mapping) -> tuple[bool, list[str]]`：逐条硬否决，返回 `(allowed, reasons)`。否决项：不可卖／不可减仓、`transfer_tax_bps` 非 0 或未知、owner 可任意 mint、可 blacklist、可改 tax、proxy 可随时换实现、LP 集中度超阈、流动性骤降、持有人集中证据缺失。**任一为 `None`（未知）→ 否决并记 `UNKNOWN_*`，不得当 False 放行。**
   - `downtrend_recenter_guard(*, price_now, range_lower, trend_slope, volume_trend) -> tuple[str, str]`：**T43**。价格跌破 `range_lower` 且趋势向下 → `("REMOVE_EVAL", "NO_DOWNTREND_RECENTER")`；**绝不返回允许下移区间的状态**。返回值只允许 `REMOVE_EVAL / HOLD / NORMAL`，不含任何 recenter-lower。
   - `exit_state_machine(*, remove_ok: bool, swap_ok: bool|None, atomic: bool) -> tuple[str, dict]`：**T44/T45**。
     - `remove_ok and swap_ok` → `CLOSED_RECONCILED`
     - `remove_ok and swap_ok is False` → **`REMOVED_RISKY_INVENTORY`**，附 `{"cash_closed": False, "asset_cap_released": False, "residual_risk": True}`
     - `atomic and swap_ok is False` → **`ATOMIC_EXIT_REVERTED`**，且 `remove` 也视为未完成（`{"remove_effective": False}`），须独立重检后才可发 remove-only
     - `swap_ok is None`（未知） → `EXIT_UNKNOWN_RECONCILE_REQUIRED`，`asset_cap_released=False`
   - `exit_direction_check(*, from_asset, to_asset, current_exposure: Mapping[str, Decimal], caps: Mapping[str, Decimal]) -> tuple[bool, str]`：**T46**。若退出目标资产的暴露已达/超上限 → `(False, "EXIT_INCREASES_CAPPED_EXPOSURE:<asset>")`。**不得因为 action 是 exit 就跳过检查。**
   - `residual_inventory_accounting(...) -> dict`：撤池后未能换出的风险币仍占资产上限、仍计入回撤与清算 NAV，返回该行以写 `rh_journal`。
   - `main()`：`--facts-json --out`，不联网。
2. `tests/test_lp_rh_meme_audit_v1_readonly.py`（≤300 行，≥16 测试）
   - `transfer_tax_bps=500`（5%）→ **拒绝**（B2 允许但 PRD 首版不接受，断言 reasons 含该项）。
   - 任一事实为 `None` → 拒绝且 reason 前缀 `UNKNOWN_`。
   - T43：跌破下界且趋势向下 → `REMOVE_EVAL`；断言返回值集合里**不存在**任何允许下移的状态。
   - T44：`remove_ok=True, swap_ok=False` → `REMOVED_RISKY_INVENTORY`，`cash_closed is False`，`asset_cap_released is False`。
   - T45：`atomic=True, swap_ok=False` → `ATOMIC_EXIT_REVERTED` 且 `remove_effective is False`。
   - `swap_ok=None` → `EXIT_UNKNOWN_RECONCILE_REQUIRED`，额度不释放。
   - T46：退出到已满额的 USDG → `(False, "EXIT_INCREASES_CAPPED_EXPOSURE:USDG")`。
   - 全部准入项齐全且合规 → `(True, [])`。

## 不许动
同 RH-03c。金额用 `Decimal`，禁止 float。

## 验收
`pytest tests/test_lp_rh_meme_audit_v1_readonly.py -q` 全绿；全量 0 failed / 14 skipped；`git diff --stat` 为空。
