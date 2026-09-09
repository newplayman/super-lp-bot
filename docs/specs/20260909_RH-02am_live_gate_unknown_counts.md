# RH-02am：LIVE 放行闸门把「未知」当成「零次未授权操作」

## 铁证（主脑已核实，不需要你重新调研）

`scripts/lp_rh_readiness_v1_readonly.py:120-121`：

```python
if signatures or broadcasts or keys_created:
    blockers.append("UNAUTHORIZED_ACTION_DETECTED")
```

`None or None or None` → `False` → 不加 blocker → **`live_allowed=True`, `blockers=[]`**。

复现输入：`usable_provider_count=2`、`capital_policy_approved=True`、
`signatures=broadcasts=keys_created=None` → 返回 `live_allowed=True`。

docstring 明写「zero unauthorized signatures / broadcasts / keys」，
但 **`None`（从未采集到）与 `0`（确认为零）在这里不可区分**。
这是**放行真钱的闸门**，用户是实盘操盘者，这条的危害级别最高。

**同一个函数里前两个检查都显式处理了 `None`**
（`usable_provider_count is None or < 2`、`capital_policy_approved is None`），
**唯独这三个计数漏了**——作者显然意识到过这个问题，第三处忘了。

## 你要做的

改 `live_gate_status`，语义按下面这条定死（这是主脑的裁决，不要自创）：

**三个计数必须每一个都是「非负整数」且值为 0，才算通过。**

- 任一为 `None` → blocker `UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE`
- 任一不是整数类型（含 `bool`、`str`、`float`）→ 同一个 blocker
  （`True` 是 `int` 的子类，必须显式排除，否则 `signatures=True` 会被当成 1 而"正确"阻断，
  但 `keys_created=False` 会被当成 0 而错误放行）
- 任一为负数 → 同一个 blocker
- 全部为 0 → 不加 blocker
- 任一 > 0 → 保留原有的 `UNAUTHORIZED_ACTION_DETECTED`

两个 blocker 可以同时出现（一个未知、另一个 > 0 时）。

**顺带检查同文件的 `graduation_verdict` 与 `stage_b_status`**：
它们是否也有「`None` 被布尔化后当成安全值」的同类问题？
有就一并修（同样的语义：未知 ≠ 安全），没有就在报告里写明你查过且为什么安全。

## 不许动

`scripts/lp_rh_gas_reserve_v1_readonly.py`（另一条线正在改它）、
任何其它 `scripts/`、任何 `.db`、`pool_meta.json`。
`tests/test_lp_rh_readiness_v1_readonly.py` **只允许新增测试，不许改既有测试**。

## 验收标准

1. `live_gate_status(usable_provider_count=2, capital_policy_approved=True,
   signatures=None, broadcasts=None, keys_created=None)`
   → `live_allowed is False` 且 blockers 含 `UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE`。
2. 三个计数分别单独为 `None` 的三种情况都要有测试。
3. `signatures=0, broadcasts=0, keys_created=0` → `live_allowed is True`（其余条件干净时）。
4. `keys_created=False` → **必须阻断**（bool 不是合法计数）。
5. `signatures=-1` → 必须阻断。
6. `signatures=1` → 仍然 `UNAUTHORIZED_ACTION_DETECTED`（原有行为不回退）。
7. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_readiness_v1_readonly.py -q -p no:cacheprovider`
   全绿，且**原有测试全部仍在**。

## 交付格式（你在只读沙箱里，写不了文件）

最后一条消息只包含两个文件的完整内容，标记独占一行、一字不差：

```
===FILE:scripts/lp_rh_readiness_v1_readonly.py===
（完整内容，不要用 markdown 代码围栏包裹）
===FILE:tests/test_lp_rh_readiness_v1_readonly.py===
（完整内容，不要用 markdown 代码围栏包裹）
===END===
```

动笔前先用 python 实际跑一遍复现输入确认缺陷存在。
若你认为主脑的裁决语义有问题，**在文件内容之前先用文字说明**，不要擅自改语义。
