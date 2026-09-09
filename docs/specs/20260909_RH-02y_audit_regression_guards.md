# RH-02y：补上 T09 与 T45 的回归护栏（审计「需关注」项）

## 背景

`AUDIT_VERDICT_CN.md` 的五个「需关注」中，T11 已由 RH-02k + 溯源列闭合，
剩下 T09 与 T45 **都不是功能缺陷，而是缺回归保护**——
当前行为正确，但没有任何测试拦住将来有人改坏它。

| 用例 | PRD §20 原文 | 现状 |
|---|---|---|
| **T09** | `v4存在白名单LP／自定义fee但未支持 → UNSUPPORTED，网页APR不影响结果` | `UNSUPPORTED_HOOK_POLICY` 已断言；**「APR 不影响结果」无任何测试**。实测三个模块源码里 `apr` 出现 **0 次**，即行为正确 |
| **T45** | `原子exit中swap回滚 → remove亦视为未完成；独立重检后才可remove-only` | 前半句（`remove_effective: False`）已断言；**后半句「独立重检后才可 remove-only」无测试** |

## 现场代码（已用 `ast` 抽出，**不要再 grep**）

`scripts/lp_rh_meme_audit_v1_readonly.py`：
```
def exit_state_machine(*, remove_ok: bool, swap_ok: bool | None,
                       atomic: bool) -> tuple[str, dict]:
    if atomic and swap_ok is False:
        return "ATOMIC_EXIT_REVERTED", {"remove_effective": False}
    if remove_ok and swap_ok is True:
        return "CLOSED_RECONCILED", {"cash_closed": True,
            "asset_cap_released": True, "residual_risk": False}
    if remove_ok and swap_ok is False:
        return "REMOVED_RISKY_INVENTORY", {"cash_closed": False,
            "asset_cap_released": False, "residual_risk": True}
    if swap_ok is None:
        return "EXIT_UNKNOWN_RECONCILE_REQUIRED", {"asset_cap_released": False}
    return "EXIT_INCOMPLETE", {"remove_effective": bool(remove_ok),
        "asset_cap_released": False}
```
**语义**：`atomic=True` 表示尚未独立重检；重检后调用方以 `atomic=False` 再次判定，
此时才可能进入 `REMOVED_RISKY_INVENTORY`（remove-only）。

`scripts/lp_rh_pool_probe_v1_readonly.py`：
```
def dispatch_protocol(candidate: Dict[str, object])
def probe_v3_pool(candidate: Dict[str, object], rpc: Callable, expected: int = RH_CHAIN_ID)
def probe_v4_pool(candidate: Dict[str, object], rpc: Callable, state_view=None, expected: int = RH_CHAIN_ID)
```

## 只新建一个测试文件（不改任何实现）

`tests/test_lp_rh_audit_regression_guards_v1_readonly.py`（≤240 行，**≥16 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。**不许联网。**

### T09 组：网页 APR 不得影响任何结果

- **★行为级：同一个 candidate，一份不带 APR、一份注入
  `{"apr": 999.0, "APR": "999%", "apy": 1e9, "web_apr": 42}`，
  `dispatch_protocol` 的返回**完全相等**★**
- **★同样两份输入喂给 `probe_v3_pool`（假 `rpc`），返回的 dict **逐键相等**★**
  （若返回含时间戳等易变字段，比较时排除该字段并在注释里写明排除了什么）
- 同上，`probe_v4_pool` 逐键相等。
- 注入极端 APR（负数、`None`、超长字符串）仍不改变结果（三条）。
- **★源码级守卫：读取三个模块的源码文本，断言不区分大小写地
  **不出现** `apr`：`lp_rh_pool_probe_v1_readonly.py`、
  `lp_rh_capabilities_v1_readonly.py`、`lp_rh_registry_v1_readonly.py`★**
  （三条独立断言；失败信息里写明「PRD T09：网页 APR 不得进入判定路径」）
  注意用**单词边界**匹配，避免误伤 `apr` 出现在别的单词里（如 `capr...`）。

### T45 组：原子回滚后不得直接 remove-only

- `exit_state_machine(remove_ok=True, swap_ok=False, atomic=True)`
  → 状态 `"ATOMIC_EXIT_REVERTED"` 且 `remove_effective is False`。
- **★同一入参下，状态**不等于** `"REMOVED_RISKY_INVENTORY"`★**
  （原子回滚不得被当成 remove-only）
- **★独立重检后（`atomic=False`，其余不变）才得到
  `"REMOVED_RISKY_INVENTORY"`★**——两次调用的状态**不同**，各断言一次。
- `atomic=True, swap_ok=False` 的返回里**没有** `asset_cap_released: True`
  （额度不得在未重检时释放）。
- `atomic=False, remove_ok=True, swap_ok=False` 的返回中
  `residual_risk is True` 且 `asset_cap_released is False`。
- `remove_ok=False, swap_ok=False, atomic=True` → 仍是 `ATOMIC_EXIT_REVERTED`
  （`remove_ok` 不影响原子回滚的判定）。
- `swap_ok is None` + `atomic=True` → **不是** `ATOMIC_EXIT_REVERTED`
  （`None` 是"未知"，不是"失败"，两者必须可区分）。
- `swap_ok is None` → `"EXIT_UNKNOWN_RECONCILE_REQUIRED"` 且
  `asset_cap_released is False`。
- 成功路径回归：`remove_ok=True, swap_ok=True, atomic=True`
  → `"CLOSED_RECONCILED"`、`asset_cap_released is True`。

## 不许动
**不改任何实现文件**——本包只新增测试。
不改现有测试。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_audit_regression_guards_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥16 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。
**若发现实现行为与 PRD 原文冲突，停下来报告，不要改实现迁就测试。**
